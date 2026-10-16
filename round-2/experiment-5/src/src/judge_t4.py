#!/usr/bin/env python3
"""T4 classifier audit: an LLM judge (OpenRouter openai/gpt-4.1-mini, T=0), blind to the rule label, labels 60
programs stratified by the v1+T4 label (baseline + forced). Reports agreement and Cohen's kappa.
Budget: running sum of usage.cost, hard cap $0.50; any 403 'AI Inventor per-run OpenRouter budget' aborts the batch.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import extract_code  # noqa: E402
from protocol import ROOT  # noqa: E402
from protocol_t4 import TAXONOMY_SELECT  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "judge_t4.log", rotation="30 MB", level="DEBUG")
CAP = 0.50
MODEL_ID = "openai/gpt-4.1-mini"
DEFS = """Classes (pick exactly one; the idea the program actually IMPLEMENTS, ignoring comments and names):
- Quickselect: partitions around a pivot and continues into ONE side compared against k (recursive or iterative).
- Heap_select: uses a heap (heapq.nsmallest, heapify + k pops, size-k heap, custom heap) to obtain the k-th smallest.
- Sort_index: sorts the whole list (sorted(), .sort(), or a full sorting algorithm such as quicksort/bubble) and indexes [k-1].
- Median_of_medians: deterministic selection with groups of 5 and a median-of-medians pivot.
- Partial_selection: k passes each extracting/selecting the current minimum (partial selection sort, repeated min/remove).
- Counting_bucket: counts value frequencies / buckets and walks cumulative counts to reach k.
- Binary_search_value: binary search over the VALUE range, counting elements <= mid.
- Builtin: numpy.partition/argpartition, statistics, pandas nsmallest.
- Other: anything else (brute-force counting of smaller elements, etc.).
Reply with JSON only: {"label": "<class>", "confidence": <0..1>}"""


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def sample_programs(n: int, seed: int, exclude: set[str]) -> list[dict]:
    pool = []
    for p in sorted((ROOT / "data" / "conf" / "gen" / "T4").glob("*.jsonl")):
        if not (p.stem == "baseline" or p.stem.startswith("forced_")):
            continue
        labs = {r["id"]: r for r in load_jsonl(ROOT / "data" / "conf" / "labels" / "T4" / p.name)}
        for r in load_jsonl(p):
            lab = labs[r["id"]]["label"]
            if lab == "Unparseable" or r["id"] in exclude:
                continue
            code, _ = extract_code(r["output_text"])
            if code:
                pool.append(dict(id=r["id"], rule=lab, code=code[:6000]))
    rng = random.Random(seed)
    by = {}
    for x in pool:
        by.setdefault(x["rule"], []).append(x)
    for v in by.values():
        rng.shuffle(v)
    out = []
    while len(out) < n and any(by.values()):  # round-robin stratification over rule labels
        for k in sorted(by):
            if by[k] and len(out) < n:
                out.append(by[k].pop())
    return out


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


async def judge_all(items: list[dict]) -> tuple[list[dict], float, bool]:
    from openai import AsyncOpenAI, PermissionDeniedError
    client = AsyncOpenAI(base_url=os.environ["OPENROUTER_BASE_URL"], api_key=os.environ["OPENROUTER_API_KEY"])
    sem = asyncio.Semaphore(8)
    spent = {"cost": 0.0, "abort": False}

    async def one(x: dict) -> dict:
        async with sem:
            if spent["abort"] or spent["cost"] >= CAP:
                return dict(x, judge=None, error="skipped (budget/abort)")
            try:
                r = await client.chat.completions.create(
                    model=MODEL_ID, temperature=0, max_tokens=60,
                    messages=[{"role": "system", "content": "You classify Python programs that find the k-th smallest element."},
                              {"role": "user", "content": DEFS + "\n\nProgram:\n```python\n" + x["code"] + "\n```"}],
                    extra_body={"usage": {"include": True}})
            except PermissionDeniedError as e:
                if "AI Inventor per-run OpenRouter budget" in str(e):
                    spent["abort"] = True
                logger.error(f"403: {str(e)[:200]}")
                return dict(x, judge=None, error="403")
            except Exception as e:  # noqa: BLE001 - network errors are logged and the item skipped
                logger.error(f"judge error: {str(e)[:200]}")
                return dict(x, judge=None, error=str(e)[:200])
            cost = float(getattr(r.usage, "cost", 0) or (r.usage.model_extra or {}).get("cost", 0) or 0)
            spent["cost"] += cost
            txt = r.choices[0].message.content or ""
            logger.debug(f"{x['id']} rule={x['rule']} -> {txt[:200]}")
            try:
                j = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
                lab = j.get("label")
                lab = lab if lab in TAXONOMY_SELECT else "Other"
                return dict(x, judge=lab, confidence=j.get("confidence"), cost=cost)
            except (json.JSONDecodeError, AttributeError):
                return dict(x, judge="Other", confidence=None, cost=cost, error="unparsed")
    res = await asyncio.gather(*[one(x) for x in items])
    return list(res), spent["cost"], spent["abort"]


@logger.catch(reraise=True)
def main() -> None:
    items = sample_programs(60, 0, set())
    res, cost, abort = asyncio.run(judge_all(items))
    ok = [r for r in res if r.get("judge")]
    agree = sum(r["judge"] == r["rule"] for r in ok) / max(1, len(ok))
    kap = cohen_kappa([r["rule"] for r in ok], [r["judge"] for r in ok]) if ok else None
    out = dict(model=MODEL_ID, n_requested=len(items), n_judged=len(ok), agreement=agree, cohen_kappa=kap,
               accept=bool(kap is not None and kap >= 0.6), cost_usd=cost, aborted=abort,
               rule_label_counts=dict(Counter(r["rule"] for r in items)),
               confusion=dict(Counter(f"{r['rule']}->{r['judge']}" for r in ok)),
               items=[{k: v for k, v in r.items() if k != "code"} for r in res])
    (ROOT / "results" / "t4_classifier_audit.json").write_text(json.dumps(out, indent=1))
    bp = ROOT / "results" / "budget.json"
    b = json.loads(bp.read_text()) if bp.exists() else {"openrouter_calls": []}
    b["openrouter_calls"].append(dict(step="t4_judge_audit", model=MODEL_ID, n=len(ok), cost_usd=cost))
    b["total_usd"] = sum(x["cost_usd"] for x in b["openrouter_calls"])
    bp.write_text(json.dumps(b, indent=1))
    logger.info(f"judge audit: n={len(ok)} agreement={agree:.3f} kappa={kap} cost=${cost:.4f} accept={out['accept']}")


if __name__ == "__main__":
    main()
