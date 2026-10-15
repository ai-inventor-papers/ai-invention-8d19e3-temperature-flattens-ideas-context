#!/usr/bin/env python3
"""Score every generation that has no scored record yet (recovery after an interrupted scoring thread)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.common import GENS, SCORED, Scorer, append_jsonl, read_jsonl, setup_logging
from loguru import logger

setup_logging("score_backlog")
sc = Scorer()
for t in ("T1", "T3"):
    for p in sorted((GENS / t).glob("*.jsonl")):
        if p.stem.endswith("_list"):
            continue
        done = {r["idx"] for r in read_jsonl(SCORED / t / p.name)}
        back = [r for r in read_jsonl(p) if r["idx"] not in done]
        if back:
            append_jsonl(SCORED / t / p.name, sc.score_records(back))
            logger.info(f"scored backlog {t}/{p.stem}: {len(back)}")
