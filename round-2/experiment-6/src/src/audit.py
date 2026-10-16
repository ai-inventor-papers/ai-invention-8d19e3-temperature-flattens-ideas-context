#!/usr/bin/env python3
"""C1 label audit: 100 gemma programs stratified by v1 label, judged blind by openai/gpt-4.1-mini (T=0) through
OpenRouter. Reports agreement, Cohen's kappa and a confusion matrix per task. The classifier is NOT changed.

Budget: stops at $0.45 (running total of usage.cost) or on the first 403 'AI Inventor per-run OpenRouter budget'.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import extract_code  # noqa: E402
from common import GEMMA, LOGS, RESULTS, read_jsonl, write_json  # noqa: E402
from protocol import DISPLAY, taxonomy  # noqa: E402
from runner import gens_path, load_scored  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(LOGS / "audit.log", rotation="30 MB", level="DEBUG")

MODEL = "openai/gpt-4.1-mini"
CAP = 0.45
N = 100
PRICE_IN, PRICE_OUT = 0.4e-6, 1.6e-6
STATE = dict(cost=0.0, stop=False, calls=0)


def sample_items() -> list[dict]:
    rng = random.Random(2026)
    pool = []
    for t in ("T1", "T2"):
        for p in sorted((gens_path(GEMMA, t, "x").parent).glob("*.jsonl")):
            st = p.stem
            if st == "smoke":
                continue
            lab = {r["seed"]: r["label"] for r in load_scored(GEMMA, t, st)}
            for g in read_jsonl(p):
                L = lab.get(g["seed"])
                if L is None or L == "Unparseable":
                    continue
                pool.append(dict(task=t, setting=st, seed=g["seed"], label=L, text=g["text"]))
    by = {}
    for it in pool:
        by.setdefault((it["task"], it["label"]), []).append(it)
    chosen = []
    for k in sorted(by):
        rng.shuffle(by[k])
        chosen += by[k][:5]
    rest = [it for k in sorted(by) for it in by[k][5:]]
    rng.shuffle(rest)
    chosen += rest[: max(0, N - len(chosen))]
    return chosen[:max(N, len(chosen))] if len(chosen) <= N else chosen[:N]


def prompt(it) -> str:
    tax = taxonomy(it["task"])
    opts = "\n".join(f"- {c}: {DISPLAY.get(c, c)}" for c in tax)
    code, _ = extract_code(it["text"])
    code = (code or it["text"])[:6000]
    return (f"Classify which algorithm this Python code implements. Judge from the code's logic, not from names or "
            f"comments. Choose exactly one label from:\n{opts}\n\nCode:\n```python\n{code}\n```\n\n"
            'Reply with only JSON: {"label": "<one label from the list>"}')


async def judge(client, sem, it) -> None:
    async with sem:
        if STATE["stop"] or STATE["cost"] >= CAP:
            return
        try:
            r = await client.chat.completions.create(model=MODEL, temperature=0, max_tokens=30,
                                                     messages=[{"role": "user", "content": prompt(it)}],
                                                     extra_body={"usage": {"include": True}}, timeout=60)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "AI Inventor per-run OpenRouter budget" in msg or "403" in msg:
                STATE["stop"] = True
                logger.error(f"budget refusal -> stopping batch: {msg[:200]}")
            else:
                logger.warning(f"judge error: {msg[:200]}")
            return
        if STATE["stop"]:
            return
        u = r.usage
        c = getattr(u, "cost", None)
        if c is None:
            extra = getattr(u, "model_extra", None) or {}
            c = extra.get("cost")
        if c is None:
            c = u.prompt_tokens * PRICE_IN + u.completion_tokens * PRICE_OUT
        STATE["cost"] += float(c)
        STATE["calls"] += 1
        txt = r.choices[0].message.content or ""
        m = re.search(r'"label"\s*:\s*"([^"]+)"', txt)
        lab = m.group(1) if m else txt.strip()
        tax = taxonomy(it["task"])
        it["judge"] = lab if lab in tax else "Other"
        logger.debug(f"{it['task']}/{it['setting']}/{it['seed']}: v1={it['label']} judge={it['judge']} raw={txt[:80]}")


def kappa(a, b) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


async def run() -> dict:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=os.environ["OPENROUTER_BASE_URL"], api_key=os.environ["OPENROUTER_API_KEY"])
    items = sample_items()
    logger.info(f"audit: {len(items)} programs; est cost ~${len(items) * 1500 * PRICE_IN:.3f}")
    sem = asyncio.Semaphore(4)
    await asyncio.gather(*(judge(client, sem, it) for it in items), return_exceptions=True)
    done = [it for it in items if "judge" in it]
    out = dict(model=MODEL, n_sampled=len(items), n_judged=len(done), cost_usd=STATE["cost"],
               stopped_on_budget=STATE["stop"], tasks={})
    for t in ("T1", "T2"):
        d = [it for it in done if it["task"] == t]
        a, b = [x["label"] for x in d], [x["judge"] for x in d]
        conf = Counter(f"{x}->{y}" for x, y in zip(a, b))
        k = kappa(a, b)
        out["tasks"][t] = dict(n=len(d), agreement=sum(x == y for x, y in zip(a, b)) / max(1, len(d)), kappa=k,
                               confusion=dict(conf.most_common()), label_limited=bool(k < 0.6))
    allv = [(x["label"], x["judge"]) for x in done]
    out["pooled_kappa"] = kappa([x for x, _ in allv], [y for _, y in allv])
    out["items"] = [{k: v for k, v in it.items() if k != "text"} for it in done]
    return out


if __name__ == "__main__":
    res = asyncio.run(run())
    write_json(RESULTS / "audit.json", res)
    logger.info(json.dumps({k: v for k, v in res.items() if k != "items"}))
