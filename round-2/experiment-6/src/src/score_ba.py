#!/usr/bin/env python3
"""CPU: v1 label + oracle for the iteration-1 ban-arm SCREEN generations (vLLM, Qwen, T1/T2; READ-ONLY inputs).

Gives offmenu_correct for the Qwen screen bans (C4 'displacement settings') and the vLLM baseline/placebo pass
rates. Output: data/scored/ba_vllm/<task>/<condition>.jsonl
"""
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BA, SCORED, append_jsonl, read_jsonl  # noqa: E402
from runner import score_records  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")

CONDS = ["baseline", "placebo", "ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5", "ban_rare",
         "para1_r1", "para2_r1"]


@logger.catch(reraise=True)
def main(workers: int = 2) -> None:
    for t in ("T1", "T2"):
        for c in CONDS:
            out = SCORED / "ba_vllm" / t / f"{c}.jsonl"
            src = read_jsonl(BA / "data/gen" / t / f"{c}.jsonl")
            have = {r["seed"] for r in read_jsonl(out)}
            recs = [dict(id=r["id"], model="ba_vllm", task=t, setting=c, family="ba_screen", seed=r["seed"],
                         text=r["output_text"], ntoks=len(r["output_token_ids"]),
                         hit_max=r["finish_reason"] == "length", banned=r.get("banned") or [])
                    for r in src if r["seed"] not in have]
            for i in range(0, len(recs), 50):
                rows = score_records(recs[i:i + 50], workers=workers)
                for row, r in zip(rows, recs[i:i + 50]):
                    row["banned"] = r["banned"]
                append_jsonl(out, rows)
            logger.info(f"{t}/{c}: scored {len(recs)} new")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
