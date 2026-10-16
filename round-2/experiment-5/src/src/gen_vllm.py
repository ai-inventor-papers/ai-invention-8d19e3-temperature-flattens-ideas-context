#!/usr/bin/env python3
"""vLLM generation for screen extensions and confirmation conditions (same SamplingParams/record schema as the
ban arm's generate.py). Resumable: skips any job whose output file is already complete.

Usage: python src/gen_vllm.py --jobs data/conf/jobs_X.json [--frozen results/frozen_predictors.json ...]
Job: {task, condition, banned, seeds, out}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze import assert_frozen  # noqa: E402
from protocol import MAX_TOKENS, MODEL, TEMPERATURE, TOP_K, TOP_P, ROOT  # noqa: E402
from protocol_ext import user_message  # noqa: E402

os.environ.setdefault("CC", str(ROOT / "tools" / "cc"))
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
(ROOT / "logs").mkdir(exist_ok=True)
logger.add(ROOT / "logs" / "gen_vllm.log", rotation="30 MB", level="DEBUG")


def count_lines(p: Path) -> int:
    return sum(1 for x in p.read_text().splitlines() if x.strip()) if p.exists() else 0


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--frozen", nargs="*", default=[])
    ap.add_argument("--limit", type=int, default=0, help="mini mode: only the first N seeds per job")
    args = ap.parse_args()
    for f in args.frozen:
        assert_frozen(ROOT / f)
    jobs = json.loads(Path(args.jobs).read_text())
    for j in jobs:
        j["out"] = ROOT / j["out"]
        if args.limit:
            j["seeds"] = j["seeds"][: args.limit]
            j["out"] = j["out"].with_name(j["out"].stem + f"__mini{args.limit}.jsonl")
    todo = [j for j in jobs if count_lines(j["out"]) < len(j["seeds"])]
    if not todo:
        logger.info("nothing to do")
        return
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(MODEL, dtype="bfloat16", gpu_memory_utilization=0.85, max_model_len=2048, seed=0,
              enable_prefix_caching=True, enforce_eager=True)
    prompts, params, meta = [], [], []
    for j in todo:
        umsg = user_message(j["task"], j["condition"], j.get("banned") or [])
        text = tok.apply_chat_template([{"role": "user", "content": umsg}], tokenize=False, add_generation_prompt=True)
        ids = tok(text, add_special_tokens=False)["input_ids"]
        logger.info(f"[{j['task']}/{j['condition']}] n={len(j['seeds'])} prompt: {umsg!r}")
        for s in j["seeds"]:
            prompts.append({"prompt_token_ids": ids})
            params.append(SamplingParams(temperature=TEMPERATURE, top_p=TOP_P, top_k=TOP_K, max_tokens=MAX_TOKENS,
                                         seed=s, logprobs=0))
            meta.append(dict(task=j["task"], condition=j["condition"], banned=j.get("banned") or [], seed=s,
                             user_message=umsg, prompt_text=text, prompt_token_ids=ids, out=str(j["out"])))
    t0 = time.time()
    outs = llm.generate(prompts, params, use_tqdm=False)
    dt = time.time() - t0
    ntok = sum(len(o.outputs[0].token_ids) for o in outs)
    logger.info(f"generated {len(outs)} seqs, {ntok} tokens in {dt:.1f}s -> {ntok / dt:.0f} tok/s")
    by_file: dict[str, list[dict]] = {}
    for m, o in zip(meta, outs):
        c = o.outputs[0]
        lps = [float(d[t].logprob) if d is not None and t in d else None for t, d in zip(c.token_ids, c.logprobs or [])]
        rec = dict(id=f"{m['task']}|{m['condition']}|{m['seed']}", task=m["task"], condition=m["condition"],
                   banned=m["banned"], seed=m["seed"], user_message=m["user_message"], prompt_text=m["prompt_text"],
                   prompt_token_ids=m["prompt_token_ids"], output_text=c.text, output_token_ids=list(c.token_ids),
                   sampled_logprobs=lps, finish_reason=c.finish_reason, engine="vllm")
        by_file.setdefault(m["out"], []).append(rec)
    for f, recs in by_file.items():
        p = Path(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        recs.sort(key=lambda r: r["seed"])
        p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        logger.info(f"wrote {p.relative_to(ROOT)} ({len(recs)}, truncated={sum(r['finish_reason'] == 'length' for r in recs)})")
    with (ROOT / "data" / "gen_timing.jsonl").open("a") as fh:
        fh.write(json.dumps(dict(phase=Path(args.jobs).stem, n=len(outs), tokens=ntok, seconds=dt, gpu="L4")) + "\n")


if __name__ == "__main__":
    main()
