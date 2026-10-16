#!/usr/bin/env python3
"""vLLM generation for all phases. Resumable: skips any (task, condition) file that is already complete.

Usage:
  python src/generate.py --phase pilot|baseline|comention|forced|bans|topup
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
from protocol import (GEN, LOGS, MAX_TOKENS, MODEL, N_BAN, N_BASELINE, N_COMENTION, N_FORCED, TASKS,  # noqa: E402
                      TEMPERATURE, TOP_K, TOP_P, DATA, ROOT, bannable, user_message)

# No system C compiler on the run host: Triton JIT needs one, so point CC at the ziglang shim.
os.environ.setdefault("CC", str(ROOT / "tools" / "cc"))

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
LOGS.mkdir(parents=True, exist_ok=True)
logger.add(LOGS / "generate.log", rotation="30 MB", level="DEBUG")


def count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines() if line.strip())


def build_jobs(phase: str) -> list[dict]:
    """Each job: task, condition, banned (list), seeds (list), out (Path)."""
    jobs: list[dict] = []
    if phase == "pilot":
        for t in TASKS:
            jobs.append(dict(task=t, condition="baseline", banned=[], seeds=list(range(20)),
                             out=GEN / t / "pilot.jsonl"))
    elif phase == "baseline":
        for t in TASKS:
            jobs.append(dict(task=t, condition="baseline", banned=[], seeds=list(range(N_BASELINE)),
                             out=GEN / t / "baseline.jsonl"))
    elif phase == "comention":
        for t in TASKS:
            jobs.append(dict(task=t, condition="comention", banned=[], seeds=list(range(N_COMENTION)),
                             out=GEN / t / "comention.jsonl"))
    elif phase == "forced":
        for t in TASKS:
            for c in bannable(t):
                jobs.append(dict(task=t, condition=f"forced_{c}", banned=[], seeds=list(range(N_FORCED)),
                                 out=GEN / t / f"forced_{c}.jsonl"))
    elif phase in ("bans", "topup"):
        plan = json.loads((DATA / "ban_plan.json").read_text())
        for t, conds in plan.items():
            for cond, banned in conds.items():
                if phase == "bans":
                    jobs.append(dict(task=t, condition=cond, banned=banned, seeds=list(range(N_BAN)),
                                     out=GEN / t / f"{cond}.jsonl"))
                elif t in ("T1", "T2") and cond in ("ban_r1", "ban_r2", "ban_r3", "ban_r4"):
                    jobs.append(dict(task=t, condition=cond, banned=banned, seeds=list(range(N_BAN, 2 * N_BAN)),
                                     out=GEN / t / f"{cond}__topup.jsonl"))
    else:
        raise ValueError(phase)
    return jobs


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, help="pilot|baseline|comention|forced|bans|topup|all")
    args = ap.parse_args()
    from transformers import AutoTokenizer
    from vllm import LLM

    tok = AutoTokenizer.from_pretrained(MODEL)
    # enforce_eager: no torch.compile / CUDA graphs (no C toolchain; also saves minutes of startup)
    llm = LLM(MODEL, dtype="bfloat16", gpu_memory_utilization=0.85, max_model_len=2048, seed=0,
              enable_prefix_caching=True, enforce_eager=True)
    phases = ["baseline", "comention", "forced", "plan", "bans"] if args.phase == "all" else [args.phase]
    for ph in phases:
        if ph == "plan":
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "src" / "label.py"), "--no-oracle", "--plan",
                            "--files", "T1/baseline,T2/baseline,T3/baseline"], check=True)
            continue
        run_phase(llm, tok, ph)


def run_phase(llm, tok, phase: str) -> None:
    from vllm import SamplingParams

    jobs = [j for j in build_jobs(phase) if count_lines(j["out"]) < len(j["seeds"])]
    if not jobs:
        logger.info(f"phase {phase}: nothing to do")
        return
    logger.info(f"phase {phase}: {len(jobs)} jobs, {sum(len(j['seeds']) for j in jobs)} generations")

    prompts, params, meta = [], [], []
    for j in jobs:
        umsg = user_message(j["task"], j["condition"], j["banned"])
        text = tok.apply_chat_template([{"role": "user", "content": umsg}], tokenize=False,
                                       add_generation_prompt=True)
        ids = tok(text, add_special_tokens=False)["input_ids"]
        logger.info(f"[{j['task']}/{j['condition']}] rendered prompt: {text!r}")
        for s in j["seeds"]:
            prompts.append({"prompt_token_ids": ids})
            params.append(SamplingParams(temperature=TEMPERATURE, top_p=TOP_P, top_k=TOP_K,
                                         max_tokens=MAX_TOKENS, seed=s, logprobs=0))
            meta.append(dict(task=j["task"], condition=j["condition"], banned=j["banned"], seed=s,
                             user_message=umsg, prompt_text=text, prompt_token_ids=ids, out=str(j["out"])))

    t0 = time.time()
    outs = llm.generate(prompts, params, use_tqdm=True)
    dt = time.time() - t0
    ntok = sum(len(o.outputs[0].token_ids) for o in outs)
    logger.info(f"generated {len(outs)} seqs, {ntok} tokens in {dt:.1f}s -> {ntok / dt:.0f} tok/s")

    by_file: dict[str, list[dict]] = {}
    for m, o in zip(meta, outs):
        c = o.outputs[0]
        lps = []
        for tid, d in zip(c.token_ids, c.logprobs or []):
            lps.append(float(d[tid].logprob) if d is not None and tid in d else None)
        rec = dict(id=f"{m['task']}|{m['condition']}|{m['seed']}", task=m["task"], condition=m["condition"],
                   banned=m["banned"], seed=m["seed"], user_message=m["user_message"],
                   prompt_text=m["prompt_text"], prompt_token_ids=m["prompt_token_ids"],
                   output_text=c.text, output_token_ids=list(c.token_ids), sampled_logprobs=lps,
                   finish_reason=c.finish_reason)
        by_file.setdefault(m["out"], []).append(rec)
    for f, recs in by_file.items():
        p = Path(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        recs.sort(key=lambda r: r["seed"])
        p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        trunc = sum(r["finish_reason"] == "length" for r in recs)
        logger.info(f"wrote {p} ({len(recs)} recs, truncated={trunc})")
    stats_p = DATA / "gen_timing.jsonl"
    with stats_p.open("a") as fh:
        fh.write(json.dumps(dict(phase=phase, n=len(outs), tokens=ntok, seconds=dt)) + "\n")


if __name__ == "__main__":
    main()
