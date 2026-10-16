#!/usr/bin/env python3
"""All vLLM generation of this artifact (Qwen2.5-3B-Instruct, bf16, enforce_eager, prefix caching, per-request seed).

Modes:
  trunc   STEP 4b: continue 150 truncated grid rows from their own 768 tokens (+20 from-scratch regenerations)
  redraw  STEP 5 : C1 confirmation re-draw on the P1 baseline prompt at max_tokens 1536 (refuses without a valid
                   frozen C1 file) + extra unseeded T=0.7 block (seeds 1100..1299) + 5 unseeded greedy repeats/task
  seeds   STEP 6b: 120 fresh seed strings x 3 tasks x (greedy + 5 x T=0.7) (refuses without a valid frozen C3 file)
  Combine with commas: --modes trunc,redraw
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENS, INPUTS, MODEL, RESULTS, ROOT, TEMPS, read_jsonl, setup_logging, write_jsonl  # noqa: E402

os.environ.setdefault("CC", str(ROOT / "tools" / "cc"))
MAX_TOK = 1536


def make_llm():
    from vllm import LLM
    t0 = time.time()
    llm = LLM(MODEL, dtype="bfloat16", gpu_memory_utilization=0.85, max_model_len=4096, seed=0,
              enable_prefix_caching=True, enforce_eager=True, max_num_seqs=256)
    logger.info(f"vLLM loaded in {time.time() - t0:.0f}s")
    return llm


def sp(T: float, topk: int, max_tokens: int, seed):
    from vllm import SamplingParams
    if T == 0:
        return SamplingParams(temperature=0.0, max_tokens=max_tokens, logprobs=0)
    return SamplingParams(temperature=T, top_p=1.0, top_k=topk if topk > 0 else -1, max_tokens=max_tokens,
                          seed=seed, logprobs=0)


def run(llm, prompts: list[list[int]], params: list, metas: list[dict], desc: str) -> list[dict]:
    t0 = time.time()
    outs = llm.generate([{"prompt_token_ids": p} for p in prompts], params, use_tqdm=False)
    dt = time.time() - t0
    recs = []
    ntok = 0
    for m, o in zip(metas, outs):
        c = o.outputs[0]
        ntok += len(c.token_ids)
        recs.append(dict(m, text=c.text, token_ids=list(c.token_ids), n_tokens=len(c.token_ids),
                         finish_reason=c.finish_reason))
    tr = sum(r["finish_reason"] == "length" for r in recs)
    logger.info(f"[{desc}] {len(recs)} gens, {ntok} tokens in {dt:.0f}s ({ntok / max(dt, 1e-9):.0f} tok/s), "
                f"truncated {tr}/{len(recs)}")
    return recs


def p1_prompt_ids(tok, task: str, prefix: str | None = None) -> tuple[str, list[int]]:
    from protocol import user_message
    umsg = user_message(task, "baseline")
    if prefix is not None:
        umsg = prefix + "\n\n" + umsg
    text = tok.apply_chat_template([{"role": "user", "content": umsg}], tokenize=False, add_generation_prompt=True)
    return text, tok(text, add_special_tokens=False)["input_ids"]


def check_p1_rendering(tok) -> dict:
    """T4: rendered P1 baseline/placebo prompts must equal the stored ban-arm prompt_text exactly."""
    from protocol import user_message
    res = {}
    for t in ("T1", "T2", "T3"):
        for cond in ("baseline", "placebo"):
            row = read_jsonl(INPUTS / "ban" / "gen" / t / f"{cond}.jsonl")[0]
            text = tok.apply_chat_template([{"role": "user", "content": user_message(t, cond)}], tokenize=False,
                                           add_generation_prompt=True)
            ids = tok(text, add_special_tokens=False)["input_ids"]
            res[f"{t}/{cond}"] = dict(text_equal=text == row["prompt_text"], ids_equal=ids == row["prompt_token_ids"])
    assert all(v["text_equal"] and v["ids_equal"] for v in res.values()), res
    return res


# ----------------------------------------------------------------------------- modes
def mode_trunc(llm, tok) -> None:
    prompts_cfg = json.loads((INPUTS / "grid" / "config" / "prompts.json").read_text())
    raw = [r for r in read_jsonl(INPUTS / "grid" / "data" / "raw_grid.jsonl")
           if r["cond"] == "grid" and r["finish_reason"] == "length"]
    rng = random.Random(11)
    chosen = []
    for T in TEMPS:
        pool = [r for r in raw if r["T"] == T]
        # spread over (task, topk): round-robin over shuffled strata
        strata = {}
        for r in pool:
            strata.setdefault((r["task"], r["topk"]), []).append(r)
        for v in strata.values():
            rng.shuffle(v)
        keys = sorted(strata)
        rng.shuffle(keys)
        k = 0
        picked = []
        while len(picked) < 25 and any(strata.values()):
            key = keys[k % len(keys)]
            if strata[key]:
                picked.append(strata[key].pop())
            k += 1
        chosen += picked
    logger.info(f"trunc: chose {len(chosen)} truncated rows: {Counter(r['T'] for r in chosen)}")
    prompts, params, metas = [], [], []
    for r in chosen:
        ids = prompts_cfg[r["task"]]["ids"]
        prompts.append(ids + r["token_ids"])
        params.append(sp(r["T"], r["topk"], 1280, r["seed"]))
        metas.append(dict(id=f"trunc|{r['task']}|grid|{r['T']}|{r['topk']}|{r['seed']}|{r['sample_idx']}",
                          source="trunc_cont", task=r["task"], T=r["T"], topk=r["topk"], seed=r["seed"],
                          idx=r["sample_idx"], prefix_text=r["text"], prefix_n_tokens=len(r["token_ids"])))
    recs = run(llm, prompts, params, metas, "trunc continuation")
    write_jsonl(GENS / "trunc_cont.jsonl", recs)
    # secondary: 20 regenerated from scratch at the same seed with max_tokens 2048
    sub = rng.sample(chosen, 20)
    prompts = [prompts_cfg[r["task"]]["ids"] for r in sub]
    params = [sp(r["T"], r["topk"], 2048, r["seed"]) for r in sub]
    metas = [dict(id=f"truncregen|{r['task']}|grid|{r['T']}|{r['topk']}|{r['seed']}|{r['sample_idx']}",
                  source="trunc_regen", task=r["task"], T=r["T"], topk=r["topk"], seed=r["seed"],
                  idx=r["sample_idx"], orig_token_ids=r["token_ids"]) for r in sub]
    recs = run(llm, prompts, params, metas, "trunc regen 2048")
    for r in recs:
        r["prefix_reproduced"] = r["token_ids"][:768] == r["orig_token_ids"][:768]
        r["n_common_prefix"] = next((i for i, (a, b) in enumerate(zip(r["token_ids"], r["orig_token_ids"]))
                                     if a != b), min(len(r["token_ids"]), len(r["orig_token_ids"])))
    write_jsonl(GENS / "trunc_regen.jsonl", recs)


def mode_redraw(llm, tok) -> None:
    from freeze import verify
    fz = verify(RESULTS / "frozen_c1_temperature.json")
    logger.info(f"frozen C1 sha256 = {fz['sha256']}")
    pid = {}
    for t in ("T1", "T2", "T3"):
        text, ids = p1_prompt_ids(tok, t)
        pid[t] = (text, ids)
    # mini check: T1 at T in {0.3, 1.6}, n=10
    mp_, mpar, mm = [], [], []
    for T in (0.3, 1.6):
        for i in range(10):
            mp_.append(pid["T1"][1]); mpar.append(sp(T, -1, MAX_TOK, 1000 + i))
            mm.append(dict(T=T))
    mrec = run(llm, mp_, mpar, mm, "mini T1 {0.3,1.6} x10")
    from classify import classify_text
    mlabs = Counter((r["T"], classify_text(r["text"], "graph")["label"]) for r in mrec)
    logger.info(f"mini labels: {dict(mlabs)}; truncation {sum(r['finish_reason'] == 'length' for r in mrec)}/20")
    prompts, params, metas = [], [], []
    for t in ("T1", "T2", "T3"):
        topks = [10, -1] if t in ("T1", "T2") else [-1]
        for T in TEMPS:
            for k in topks:
                for i in range(100):
                    prompts.append(pid[t][1]); params.append(sp(T, k, MAX_TOK, 1000 + i))
                    metas.append(dict(id=f"redraw|{t}|grid|{T}|{k}|{1000 + i}|{i}", source="redraw", task=t,
                                      cond="grid", T=T, topk=k, seed=1000 + i, idx=i, wording="P1"))
        for i in range(200):
            prompts.append(pid[t][1]); params.append(sp(0.7, -1, MAX_TOK, 1100 + i))
            metas.append(dict(id=f"redraw|{t}|extra07|0.7|-1|{1100 + i}|{100 + i}", source="redraw", task=t,
                              cond="extra07", T=0.7, topk=-1, seed=1100 + i, idx=100 + i, wording="P1"))
        for i in range(5):
            prompts.append(pid[t][1]); params.append(sp(0.0, -1, MAX_TOK, None))
            metas.append(dict(id=f"redraw|{t}|greedy|0.0|-1|None|{i}", source="redraw", task=t, cond="greedy",
                              T=0.0, topk=-1, seed=None, idx=i, wording="P1"))
    recs = run(llm, prompts, params, metas, "redraw")
    write_jsonl(GENS / "redraw.jsonl", recs)


def mode_seeds(llm, tok) -> None:
    from freeze import verify
    fz = verify(RESULTS / "frozen_c3_seeds.json")
    strings = fz["body"]["fresh_strings"]
    prompts, params, metas = [], [], []
    for t in ("T1", "T2", "T3"):
        for s in strings:
            _text, ids = p1_prompt_ids(tok, t, prefix=s["string"])
            base = dict(task=t, seed_string=s["string"], seed_kind=s["kind"], wording="P1", source="seedsfresh",
                        topk=-1, idx=s["idx"])
            prompts.append(ids); params.append(sp(0.0, -1, MAX_TOK, None))
            metas.append(dict(base, id=f"seedsfresh|{t}|seed_greedy|0.0|-1|None|{s['idx']}", cond="seed_greedy",
                              T=0.0, seed=None))
            for r in range(5):
                sd = 1000 + 5 * s["idx"] + r
                prompts.append(ids); params.append(sp(0.7, -1, MAX_TOK, sd))
                metas.append(dict(base, id=f"seedsfresh|{t}|seed_t07|0.7|-1|{sd}|{s['idx']}", cond="seed_t07",
                                  T=0.7, seed=sd))
    recs = run(llm, prompts, params, metas, "fresh seeds")
    write_jsonl(GENS / "seeds_fresh.jsonl", recs)


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", required=True)
    args = ap.parse_args()
    setup_logging("gpu_gen")
    modes = args.modes.split(",")
    # refuse early (before loading the model) when a frozen file is missing/tampered
    from freeze import verify
    if "redraw" in modes:
        verify(RESULTS / "frozen_c1_temperature.json")
    if "seeds" in modes:
        verify(RESULTS / "frozen_c3_seeds.json")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    logger.info(f"P1 rendering check: {check_p1_rendering(tok)}")
    llm = make_llm()
    for m in modes:
        {"trunc": mode_trunc, "redraw": mode_redraw, "seeds": mode_seeds}[m](llm, tok)


if __name__ == "__main__":
    main()
