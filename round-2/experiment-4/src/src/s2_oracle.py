#!/usr/bin/env python3
"""STEP 2: sandboxed execution oracle (ban-arm src/oracle.py, 50 instances, RLIMIT_AS 1GB / CPU 10s) over every
program in gens/programs.jsonl (plus optional extra item files). Resumable: appends to results/oracle_results.jsonl
in chunks and skips ids already present.

Status: no_code | load_error | not_callable | timeout | fail | pass.
T1 'passed' = every test returns a VALID path (start..goal along edges; any length) on unweighted graphs and grids,
so DFS can pass T1; 'shortest_rate' is reported separately. T2: sorted output equals sorted(input) on all tests.
T3: path cost (or returned distance) equals the reference Dijkstra distance on all weighted tests.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENS, ORACLE_PATH, detect_cpus, read_jsonl, setup_logging  # noqa: E402


def status_of(res: dict, eligible: bool) -> str:
    if not eligible:
        return "no_code"
    err = str(res.get("error") or "")
    if err == "no_code":
        return "no_code"
    if "timeout" in err.lower() or "TimeoutErr" in err:
        return "timeout"
    if res.get("passed"):
        return "pass"
    if not res.get("callable"):
        return "load_error" if res.get("load_error") else "not_callable"
    return "fail"


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--programs", default=str(GENS / "programs.jsonl"))
    ap.add_argument("--workers", type=int, default=max(1, min(10, detect_cpus() - 4)))
    ap.add_argument("--chunk", type=int, default=400)
    ap.add_argument("--limit", type=int, default=0, help="only first N pending (scaling test)")
    ap.add_argument("--only-prefix", default="", help="comma list of id prefixes to restrict to")
    args = ap.parse_args()
    setup_logging("s2_oracle")
    from oracle import run_many
    done = {r["id"] for r in read_jsonl(ORACLE_PATH)}
    progs = read_jsonl(Path(args.programs))
    pend = [p for p in progs if p["id"] not in done]
    if args.only_prefix:
        pref = tuple(args.only_prefix.split(","))
        pend = [p for p in pend if p["id"].startswith(pref)]
    if args.limit:
        pend = pend[: args.limit]
    logger.info(f"oracle: {len(progs)} programs, {len(done)} done, {len(pend)} pending, workers={args.workers}")
    t0 = time.time()
    for s in range(0, len(pend), args.chunk):
        chunk = pend[s: s + args.chunk]
        items = [(p["code"] if p["oracle_eligible"] else "", p["task"]) for p in chunk]
        res = run_many(items, workers=args.workers)
        with ORACLE_PATH.open("a") as fh:
            for p, r in zip(chunk, res):
                st = status_of(r, p["oracle_eligible"])
                fh.write(json.dumps(dict(id=p["id"], status=st, passed=st == "pass",
                                         pass_frac=float(r.get("pass_frac") or 0.0),
                                         shortest_rate=r.get("shortest_rate"), convention=r.get("convention"),
                                         error=(str(r.get("error"))[:120] if r.get("error") else None),
                                         load_error=(str(r.get("load_error"))[:120] if r.get("load_error")
                                                     else None))) + "\n")
        el = time.time() - t0
        rate = (s + len(chunk)) / el
        logger.info(f"oracle {s + len(chunk)}/{len(pend)} in {el:.0f}s ({rate:.2f}/s, "
                    f"ETA {(len(pend) - s - len(chunk)) / max(rate, 1e-9) / 60:.1f} min)")


if __name__ == "__main__":
    main()
