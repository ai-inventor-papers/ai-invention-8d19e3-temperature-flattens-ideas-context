#!/usr/bin/env python3
"""Label confirmation / extension generations with v1 (T1-T3) or v1+T4 (T4) and run the execution oracle.

Writes <gen_dir>/../labels/{task}/{cond}.jsonl (same row order as the gen file). Resumable per file.
Usage: python src/label_conf.py [--root data/conf] [--files T1/forced_BFS,...] [--no-oracle]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import CLASSIFIER_VERSION, classifier_hash, classify_text  # noqa: E402
from classify_t4 import CLASSIFIER_T4_VERSION, classifier_t4_hash, classify_t4  # noqa: E402
from protocol import ROOT, TASK_KIND  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "label_conf.log", rotation="30 MB", level="DEBUG")


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def label_records(recs: list[dict], task: str, run_oracle: bool = True, workers: int = 16) -> list[dict]:
    rows, codes = [], []
    for r in recs:
        c = classify_t4(r["output_text"]) if task == "T4" else classify_text(r["output_text"], TASK_KIND[task])
        banned = r.get("banned") or []
        rows.append(dict(id=r["id"], task=task, condition=r["condition"], seed=r["seed"], banned=banned,
                         label=c["label"], multi=c["multi"], multi_labels=c["multi_labels"], raw_labels=c["raw_labels"],
                         is_python=c["is_python"], lang=c["lang"], oracle_eligible=c["oracle_eligible"],
                         violation=c["label"] in banned, finish_reason=r.get("finish_reason"),
                         n_out_tokens=len(r.get("output_token_ids") or []), engine=r.get("engine", "vllm"),
                         classifier=(f"{CLASSIFIER_T4_VERSION}:{classifier_t4_hash()}" if task == "T4"
                                     else f"{CLASSIFIER_VERSION}:{classifier_hash()}")))
        codes.append(c["code"] if c["oracle_eligible"] else "")
    if run_oracle:
        if task == "T4":
            from oracle_t4 import run_many as run_t4
            res = run_t4(codes, workers=workers)
            for row, o in zip(rows, res):
                row.update(oracle_status=o.get("status"), oracle_pass=bool(o.get("passed")),
                           oracle_pass_0idx=bool(o.get("pass_0idx")), oracle_callable=o.get("callable"),
                           oracle_n_pass=o.get("n_pass"))
        else:
            from oracle import run_many
            res = run_many([(c, task) for c in codes], workers=workers)
            for row, o in zip(rows, res):
                row.update(oracle_callable=bool(o.get("callable")), oracle_pass=bool(o.get("passed")),
                           oracle_pass_frac=float(o.get("pass_frac") or 0.0), oracle_convention=o.get("convention"))
    return rows


def label_file(p: Path, out: Path, run_oracle: bool = True) -> Path:
    recs = load_jsonl(p)
    if out.exists() and len(load_jsonl(out)) == len(recs):
        return out
    task = p.parent.name
    rows = label_records(recs, task, run_oracle=run_oracle)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    cnt = Counter(x["label"] for x in rows)
    pr = sum(x.get("oracle_pass", False) for x in rows) / max(1, len(rows))
    logger.info(f"{task}/{p.stem}: n={len(rows)} pass={pr:.2f} {dict(cnt.most_common())}")
    return out


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/conf")
    ap.add_argument("--files", default="")
    ap.add_argument("--no-oracle", action="store_true")
    args = ap.parse_args()
    root = ROOT / args.root
    for p in sorted((root / "gen").glob("*/*.jsonl")):
        key = f"{p.parent.name}/{p.stem}"
        if args.files and key not in args.files.split(","):
            continue
        if "__mini" in p.stem and not args.files:
            continue
        label_file(p, root / "labels" / p.parent.name / p.name, run_oracle=not args.no_oracle
                   and p.stem != "comention")


if __name__ == "__main__":
    main()
