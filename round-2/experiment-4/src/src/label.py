#!/usr/bin/env python3
"""Label every generation with the frozen rule classifier + run the execution oracle.

Writes data/labels/{task}/{condition}.jsonl (one row per generation; same order as data/gen).
Also: --plan builds data/ban_plan.json (ranks from baseline counts, ties by co-mention; RARE class).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import CLASSIFIER_VERSION, classifier_hash, classify_text, parse_list_names  # noqa: E402
from oracle import run_many  # noqa: E402
from protocol import DATA, GEN, LOGS, TASK_KIND, TASKS, bannable  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
LOGS.mkdir(parents=True, exist_ok=True)
logger.add(LOGS / "label.log", rotation="30 MB", level="DEBUG")
LAB = DATA / "labels"


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def label_file(p: Path, run_oracle: bool = True) -> Path:
    out = LAB / p.parent.name / p.name
    recs = load_jsonl(p)
    if out.exists() and len(load_jsonl(out)) == len(recs):
        return out
    task = p.parent.name
    kind = TASK_KIND[task]
    rows = []
    for r in recs:
        c = classify_text(r["output_text"], kind)
        banned = r.get("banned") or []
        rows.append(dict(id=r["id"], task=task, condition=r["condition"], seed=r["seed"], banned=banned,
                         label=c["label"], multi=c["multi"], multi_labels=c["multi_labels"],
                         raw_labels=c["raw_labels"], is_python=c["is_python"], lang=c["lang"],
                         oracle_eligible=c["oracle_eligible"], violation=c["label"] in banned,
                         finish_reason=r["finish_reason"], n_out_tokens=len(r["output_token_ids"]),
                         _code=c["code"]))
    if run_oracle:
        items = [(row["_code"] if row["oracle_eligible"] else "", task) for row in rows]
        res = run_many(items, workers=8)
        for row, o in zip(rows, res):
            row["oracle_callable"] = bool(o.get("callable"))
            row["oracle_pass"] = bool(o.get("passed"))
            row["oracle_pass_frac"] = float(o.get("pass_frac") or 0.0)
            row["oracle_shortest_rate"] = o.get("shortest_rate")
            row["oracle_convention"] = o.get("convention")
    for row in rows:
        row.pop("_code")
        row["classifier"] = f"{CLASSIFIER_VERSION}:{classifier_hash()}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    cnt = Counter(x["label"] for x in rows)
    pr = sum(x.get("oracle_pass", False) for x in rows) / max(1, len(rows))
    logger.info(f"{task}/{p.stem}: n={len(rows)} pass={pr:.2f} {dict(cnt.most_common())}")
    return out


def comention_lists(task: str) -> list[list[str]]:
    p = GEN / task / "comention.jsonl"
    return [parse_list_names(r["output_text"], TASK_KIND[task]) for r in load_jsonl(p)]


def build_plan() -> dict:
    plan, meta = {}, {}
    for t in TASKS:
        rows = load_jsonl(LAB / t / "baseline.jsonl")
        cnt = Counter(r["label"] for r in rows)
        com = Counter(c for lst in comention_lists(t) for c in set(lst))
        bann = bannable(t)
        ranked = sorted(bann, key=lambda c: (-cnt.get(c, 0), -com.get(c, 0), bann.index(c)))
        nonzero = [c for c in ranked if cnt.get(c, 0) >= 1]
        filled = []
        if len(nonzero) < 5:
            filled = [c for c in ranked if cnt.get(c, 0) == 0][: 5 - len(nonzero)]
            logger.warning(f"{t}: only {len(nonzero)} bannable classes with count>=1; filled by co-mention: {filled}")
        top = (nonzero + filled)[:5]
        N = sum(v for k, v in cnt.items() if k != "Unparseable")
        rates = {c: cnt.get(c, 0) / N for c in bann}
        in_band = [c for c in bann if 0.01 <= rates[c] <= 0.05 and c not in top[:4]]
        if in_band:
            rare = min(in_band, key=lambda c: abs(rates[c] - 0.03))
            rare_rule = "in [1%,5%], closest to 3%"
        else:
            nz = [c for c in bann if rates[c] > 0 and c not in top[:4]]
            if nz:
                rare = min(nz, key=lambda c: abs(rates[c] - 0.03))
                rare_rule = "no class in [1%,5%]: nonzero closest to 3% (excluding ranks 1-4)"
            else:
                zero = [c for c in ranked if c not in top]
                rare = max(zero, key=lambda c: com.get(c, 0)) if zero else top[-1]
                rare_rule = "no nonzero class outside ranks 1-4: most co-mentioned zero-rate class"
        plan[t] = {"ban_r1": [top[0]], "ban_r2": [top[1]], "ban_r3": [top[2]], "ban_r4": [top[3]],
                   "ban_top3": top[:3], "ban_top5": top[:5], "ban_rare": [rare], "placebo": [],
                   "para1_r1": [top[0]], "para2_r1": [top[0]]}
        meta[t] = dict(counts=dict(cnt), comention_doc_freq=dict(com), ranked=ranked, top5=top,
                       filled_by_comention=filled, rare=rare, rare_rule=rare_rule, rare_rate=rates[rare],
                       n_classes_ge3pct=sum(r >= 0.03 for r in rates.values()))
        logger.info(f"{t}: top5={top} rare={rare} ({rare_rule}) counts={dict(cnt.most_common())}")
    (DATA / "ban_plan.json").write_text(json.dumps(plan, indent=1))
    (DATA / "ban_plan_meta.json").write_text(json.dumps(meta, indent=1))
    return plan


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", default="", help="comma list of task/condition; default all")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--no-oracle", action="store_true")
    args = ap.parse_args()
    for p in sorted(GEN.glob("*/*.jsonl")):
        if p.stem == "comention":
            continue
        key = f"{p.parent.name}/{p.stem}"
        if args.files and key not in args.files.split(","):
            continue
        label_file(p, run_oracle=not args.no_oracle)
    if args.plan:
        build_plan()


if __name__ == "__main__":
    main()
