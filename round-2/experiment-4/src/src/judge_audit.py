#!/usr/bin/env python3
"""Blind LLM-judge audit of the v1 rule classifier (and the influence-arm AST classifier) on 200 stratified programs.

Judge input = extracted code with comments/docstrings stripped (classify.strip_code); no prose, prompt or T.
Judges: openai/gpt-4.1-mini (primary), google/gemini-2.5-flash-lite (second family), temperature 0, OpenRouter.
Budget: hard stop at $0.90 running total (usage.cost); a 403 'AI Inventor per-run OpenRouter budget' cancels all.
  judge_audit.py --pilot   (10 programs)   |   judge_audit.py   (all 200; resumes from results/judge_raw.jsonl)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENS, LABELS_PATH, RESULTS, read_jsonl, save_json, setup_logging  # noqa: E402

JUDGES = ["openai/gpt-4.1-mini", "google/gemini-2.5-flash-lite"]
CAP = 0.90
RARE = {"IDDFS", "Greedy_best_first", "Bidirectional", "Bellman_Ford", "SPFA", "Floyd_Warshall", "Heap", "Shell",
        "Counting", "Radix", "Bucket", "Tim_hybrid", "Insertion"}
TAX = {"graph": ["BFS", "DFS", "IDDFS", "Dijkstra", "A_star", "Greedy_best_first", "Bidirectional", "Bellman_Ford",
                 "SPFA", "Floyd_Warshall"],
       "sort": ["Quick", "Merge", "Heap", "Insertion", "Selection", "Bubble", "Shell", "Counting", "Radix", "Bucket",
                "Tim_hybrid", "Builtin"]}
KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}


class BudgetStop(Exception):
    pass


def sample_programs(n: int = 200, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    progs = {p["id"]: p for p in read_jsonl(GENS / "programs.jsonl")}
    rows = [r for r in read_jsonl(LABELS_PATH) if r["label"] != "Unparseable" and progs.get(r["id"], {}).get("code")]
    rng.shuffle(rows)
    chosen, ids = [], set()

    def take(pool, k):
        for r in pool:
            if len([c for c in chosen if c in pool]) >= k or len(chosen) >= n:
                break
            if r["id"] not in ids:
                chosen.append(r)
                ids.add(r["id"])
    take([r for r in rows if r["label"] == "Other"], 40)
    for c in sorted(RARE):
        take([r for r in rows if r["label"] == c], 5)
    take([r for r in rows if r["T"] >= 1.3], 80 - sum(1 for c in chosen if c["T"] >= 1.3))
    rest = [r for r in rows if r["id"] not in ids]
    chosen += rest[: n - len(chosen)]
    for r in chosen:
        from classify import strip_code
        r["stripped"] = strip_code(progs[r["id"]]["code"])[0][:6000]
    chosen = chosen[:n]
    rng.shuffle(chosen)
    return chosen


def prompt_for(r: dict) -> str:
    opts = TAX[KIND[r["task"]]] + ["Other"]
    return ("Which algorithm does this code implement? Judge only the implemented logic. Choose exactly one of: "
            + ", ".join(opts) + ". Reply with JSON only: {\"label\": <one option>, \"confidence\": <0-1>}.\n\n"
            "```python\n" + r["stripped"] + "\n```")


async def run_all(items: list[dict], done: set, raw_path: Path, spent0: float) -> float:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=os.environ["OPENROUTER_BASE_URL"], api_key=os.environ["OPENROUTER_API_KEY"])
    sem = asyncio.Semaphore(8)
    state = dict(spent=spent0, stop=False)
    lock = asyncio.Lock()

    async def one(r, judge):
        async with sem:
            if state["stop"] or state["spent"] >= CAP:
                return
            try:
                resp = await client.chat.completions.create(
                    model=judge, temperature=0, max_tokens=60, response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": "You classify code. Output a single JSON object and "
                               "nothing else. Never explain. If the code is incomplete or unclear, answer Other."},
                              {"role": "user", "content": prompt_for(r)}],
                    extra_body={"usage": {"include": True}}, timeout=90)
            except Exception as e:  # noqa: BLE001 - classify by message below
                msg = str(e)
                if "AI Inventor per-run OpenRouter budget" in msg:
                    state["stop"] = True
                    logger.error("budget 403: stopping all judge calls")
                    return
                logger.warning(f"{judge} {r['id']}: {msg[:160]}")
                return
            if state["stop"]:
                return
            txt = resp.choices[0].message.content or ""
            cost = float(getattr(resp.usage, "cost", 0.0) or (resp.usage.model_extra or {}).get("cost", 0.0) or 0.0)
            m = re.search(r"\{.*\}", txt, re.S)
            lab = None
            if m:
                try:
                    lab = json.loads(m.group(0)).get("label")
                except json.JSONDecodeError:
                    lab = None
            async with lock:
                state["spent"] += cost
                with raw_path.open("a") as fh:
                    fh.write(json.dumps(dict(id=r["id"], judge=judge, raw=txt[:300], label=lab, cost=cost)) + "\n")
            logger.debug(f"{judge} {r['id']} -> {lab} (${cost:.5f}, total ${state['spent']:.4f})")
    await asyncio.gather(*[one(r, j) for r in items for j in JUDGES if (r["id"], j) not in done])
    return state["spent"]


def analyse(items: list[dict], raw: list[dict]) -> dict:
    from sklearn.metrics import cohen_kappa_score
    from s1_label import kappa_ci, confusion
    jl = defaultdict(dict)
    for x in raw:
        jl[x["id"]][x["judge"]] = x["label"]
    valid = lambda r, j: jl[r["id"]].get(j) is not None  # noqa: E731
    out = dict(n_items=len(items), parse_rate={j: sum(valid(r, j) for r in items) / len(items) for j in JUDGES})
    both = [r for r in items if valid(r, JUDGES[0]) and valid(r, JUDGES[1])]
    j1 = [jl[r["id"]][JUDGES[0]] for r in both]
    j2 = [jl[r["id"]][JUDGES[1]] for r in both]
    out["judge1_vs_judge2"] = kappa_ci(j1, j2)
    out["v1_vs_judge1"] = kappa_ci([r["label"] for r in both], j1)
    out["v1_vs_judge1"]["confusion_v1_rows_judge_cols"] = confusion([r["label"] for r in both], j1)
    out["v1_vs_judge2"] = kappa_ci([r["label"] for r in both], j2)
    agree = [r for r, a, b in zip(both, j1, j2) if a == b]
    out["v1_acc_on_judge_agreement"] = dict(n=len(agree), acc=sum(r["label"] == jl[r["id"]][JUDGES[0]]
                                                                   for r in agree) / max(1, len(agree)))
    g = [r for r in both if r.get("ast_label") and not str(r["ast_label"]).startswith("error")]
    out["ast_vs_judge1"] = kappa_ci([r["ast_label"] for r in g], [jl[r["id"]][JUDGES[0]] for r in g])
    out["ast_acc_on_judge_agreement"] = dict(
        n=sum(1 for r in g if r in agree),
        acc=sum(r["ast_label"] == jl[r["id"]][JUDGES[0]] for r in g if r in agree) / max(1, sum(1 for r in g
                                                                                                 if r in agree)))
    out["per_task_v1_vs_judge1"] = {t: kappa_ci([r["label"] for r in both if r["task"] == t],
                                                [jl[r["id"]][JUDGES[0]] for r in both if r["task"] == t])
                                    for t in ("T1", "T2", "T3")}
    out["strata"] = dict(by_label=dict(Counter(r["label"] for r in items)), by_T=dict(Counter(r["T"] for r in items)),
                         by_source=dict(Counter(r["source"] for r in items)))
    return out


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()
    setup_logging("judge_audit")
    items = sample_programs()
    raw_path = RESULTS / "judge_raw.jsonl"
    raw = read_jsonl(raw_path)
    done = {(x["id"], x["judge"]) for x in raw if x["label"] is not None}
    spent = sum(x["cost"] for x in raw)
    todo = items[:10] if args.pilot else items
    spent = asyncio.run(run_all(todo, done, raw_path, spent))
    raw = read_jsonl(raw_path)
    # keep the last valid answer per (id, judge)
    last = {}
    for x in raw:
        if x["label"] is not None or (x["id"], x["judge"]) not in last:
            last[(x["id"], x["judge"])] = x
    res = analyse(todo, list(last.values()))
    res["spend_usd"] = sum(x["cost"] for x in raw)
    res["sample_seed"] = 7
    summary = dict(n=len(todo), spend_usd=res["spend_usd"], parse_rate=res["parse_rate"],
                   kappa_judge_judge=res["judge1_vs_judge2"].get("kappa"),
                   kappa_v1_judge1=res["v1_vs_judge1"].get("kappa"), kappa_v1_judge1_ci=res["v1_vs_judge1"].get(
                       "kappa_ci"), kappa_v1_judge2=res["v1_vs_judge2"].get("kappa"),
                   kappa_ast_judge1=res["ast_vs_judge1"].get("kappa"),
                   v1_acc_on_judge_agreement=res["v1_acc_on_judge_agreement"],
                   ast_acc_on_judge_agreement=res["ast_acc_on_judge_agreement"])
    res["summary"] = summary
    save_json(RESULTS / ("judge_audit_pilot.json" if args.pilot else "judge_audit.json"), res)
    logger.info(f"judge audit: {summary}")


if __name__ == "__main__":
    main()
