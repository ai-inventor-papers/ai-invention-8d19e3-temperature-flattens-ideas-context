#!/usr/bin/env python3
"""S2 / S6 generation with vLLM.

Modes:
  t0     reproducibility + chat-template check (testing plan T0)
  mini   10 samples/cell at T in {0.3, 1.6}, top-k none (testing plan T2)
  grid   full 3 tasks x 6 T x 2 top-k x n=100 grid + greedy + 20-request repeat
  ext    n=300 extension for top-k none cells (sample_idx 100..299)
  seeds  S6: 60 seed strings x 3 tasks: greedy + one T=0.7 sample (seed = string index)
Raw generations are written to data/raw_<mode>.jsonl.
"""

from __future__ import annotations

import argparse
import time

from loguru import logger

from common import (CONFIG, DATA, MAX_TOKENS, N_EXT, N_PER_CELL, TASKS, TEMPS, TOPKS, load_json, save_json,
                    setup_logging, write_jsonl)


def row(out, **meta) -> dict:
    o = out.outputs[0]
    return {**meta, "text": o.text, "token_ids": list(o.token_ids), "n_tokens": len(o.token_ids),
            "finish_reason": o.finish_reason}


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["t0", "mini", "grid", "ext", "seeds"])
    ap.add_argument("--max_tokens", type=int, default=MAX_TOKENS)
    args = ap.parse_args()
    setup_logging(f"s2_generate_{args.mode}")
    from vllm_util import generate, make_llm, sp
    prompts = load_json(CONFIG / "prompts.json")
    pid = {t: prompts[t]["ids"] for t in TASKS}
    llm = make_llm()
    t_start = time.time()
    rows: list[dict] = []
    if args.mode == "t0":
        reqs, params, meta = [], [], []
        for rep in range(2):
            for t in TASKS:
                for i in range(4):
                    reqs.append(pid[t]); params.append(sp(0.7, -1, 256, seed=i))
                    meta.append({"task": t, "rep": rep, "sample_idx": i})
        outs = generate(llm, reqs, params, "t0")
        texts = {}
        for m, o in zip(meta, outs):
            texts.setdefault((m["task"], m["sample_idx"]), []).append(o.outputs[0].text)
        same = sum(1 for v in texts.values() if v[0] == v[1])
        logger.info(f"T0 seed reproducibility: {same}/{len(texts)} identical")
        g = generate(llm, [pid[t] for t in TASKS], [sp(0.0, -1, 64, None) for _ in TASKS], "t0-greedy")
        save_json(DATA / "t0_check.json", {"repro_identical": same, "repro_total": len(texts),
                                            "greedy_first64": {t: list(o.outputs[0].token_ids) for t, o in zip(TASKS, g)},
                                            "greedy_text": {t: o.outputs[0].text for t, o in zip(TASKS, g)}})
        for t, o in zip(TASKS, g):
            logger.info(f"greedy {t}: {o.outputs[0].text[:200]!r}")
        return
    if args.mode == "mini":
        reqs, params, meta = [], [], []
        for t in TASKS:
            for T in (0.3, 1.6):
                for i in range(10):
                    reqs.append(pid[t]); params.append(sp(T, -1, args.max_tokens, seed=i))
                    meta.append({"task": t, "T": T, "topk": -1, "sample_idx": i, "seed": i, "cond": "grid"})
        outs = generate(llm, reqs, params, "mini")
        rows = [row(o, **m) for m, o in zip(meta, outs)]
    elif args.mode in ("grid", "ext"):
        reqs, params, meta = [], [], []
        idx_range = range(N_PER_CELL) if args.mode == "grid" else range(N_PER_CELL, N_EXT)
        topks = TOPKS if args.mode == "grid" else [-1]
        for t in TASKS:
            for T in TEMPS:
                for k in topks:
                    for i in idx_range:
                        reqs.append(pid[t]); params.append(sp(T, k, args.max_tokens, seed=i))
                        meta.append({"task": t, "T": T, "topk": k, "sample_idx": i, "seed": i, "cond": "grid"})
        if args.mode == "grid":
            for t in TASKS:
                reqs.append(pid[t]); params.append(sp(0.0, -1, args.max_tokens, None))
                meta.append({"task": t, "T": 0.0, "topk": -1, "sample_idx": 0, "seed": None, "cond": "greedy"})
            # reproducibility repeat: 20 requests re-issued inside the same batch
            for j in range(20):
                t = TASKS[j % 3]; T = TEMPS[j % 6]; k = TOPKS[j % 2]
                reqs.append(pid[t]); params.append(sp(T, k, args.max_tokens, seed=j))
                meta.append({"task": t, "T": T, "topk": k, "sample_idx": j, "seed": j, "cond": "repeat"})
        outs = generate(llm, reqs, params, args.mode)
        rows = [row(o, **m) for m, o in zip(meta, outs)]
        if args.mode == "grid":
            base = {(r["task"], r["T"], r["topk"], r["sample_idx"]): r["token_ids"] for r in rows if r["cond"] == "grid"}
            rep = [r for r in rows if r["cond"] == "repeat"]
            same = sum(1 for r in rep if base[(r["task"], r["T"], r["topk"], r["sample_idx"])] == r["token_ids"])
            save_json(DATA / "repro_grid.json", {"identical": same, "total": len(rep)})
            logger.info(f"grid bit-reproducibility: {same}/{len(rep)}")
    elif args.mode == "seeds":
        sd = load_json(CONFIG / "seeds.json")
        reqs, params, meta = [], [], []
        for t in TASKS:
            for s in sd["prompts"][t]:
                for kind, T in (("seed_greedy", 0.0), ("seed_t07", 0.7)):
                    reqs.append(s["ids"]); params.append(sp(T, -1, args.max_tokens, seed=s["idx"] if T > 0 else None))
                    meta.append({"task": t, "T": T, "topk": -1, "sample_idx": s["idx"], "seed": s["idx"] if T > 0 else None,
                                 "cond": kind, "seed_string": s["string"], "seed_kind": s["kind"]})
        outs = generate(llm, reqs, params, "seeds")
        rows = [row(o, **m) for m, o in zip(meta, outs)]
    write_jsonl(DATA / f"raw_{args.mode}.jsonl", rows)
    n_len = sum(1 for r in rows if r["finish_reason"] == "length")
    logger.info(f"wrote {len(rows)} rows; finish=length: {n_len} ({n_len / max(1, len(rows)):.1%}); "
                f"elapsed {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
