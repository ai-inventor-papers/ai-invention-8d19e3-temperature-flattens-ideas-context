#!/usr/bin/env python3
"""Residual-stream cache (HF transformers; separate process from vLLM).

For every generation: teacher-forced forward pass over prompt + output (truncated after the commitment window,
which is exact for a causal model), mean-pool hidden_states[l] for l in LAYERS over the commitment WINDOW
(output tokens [c, c+16]) and the PRE-COMMIT span ([c-16, c-1]). hidden_states[36] is AFTER the final RMSNorm
in HF Qwen2 (HF appends the normed last state), hidden_states[l<36] are raw block outputs.

Usage: python src/activations.py [--only T1/baseline,...] [--check]
"""
from __future__ import annotations

import argparse
import gc
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import ACTS, GEN, LAYERS, LOGS, MODEL, TASK_KIND, DATA  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
LOGS.mkdir(parents=True, exist_ok=True)
logger.add(LOGS / "activations.log", rotation="30 MB", level="DEBUG")

LEX_GRAPH = re.compile(r"bfs|breadth|dfs|depth|dijkstra|a\*|a-star|astar|\ba star\b|heuristic|bellman|spfa|floyd|"
                       r"bidirectional|uniform.cost|iterative deepening|greedy best|deque|heapq|priorityqueue|"
                       r"popleft|stack", re.I)
# 'tim' restricted to timsort/tim sort: a bare 'tim' prefix matches 'time'/'optimal' in nearly every answer
LEX_SORT = re.compile(r"quick|merge|heap|insertion|selection|bubble|shell|counting|radix|bucket|\btim\s?sort|"
                      r"pivot|partition", re.I)
WIN = 16
FALLBACK_MAX = 600


def token_spans(tok, out_ids: list[int], text: str) -> list[tuple[int, int]] | None:
    pieces = [tok.decode([i], skip_special_tokens=True) for i in out_ids]
    if "".join(pieces) == text:
        spans, pos = [], 0
        for p in pieces:
            spans.append((pos, pos + len(p)))
            pos += len(p)
        return spans
    # incremental decode fallback (multi-byte chars split across tokens)
    spans, prev = [], 0
    for k in range(len(out_ids)):
        cur = len(tok.decode(out_ids[:k + 1], skip_special_tokens=True))
        spans.append((prev, cur))
        prev = cur
    return spans


def commit_pos(tok, rec: dict) -> tuple[int, bool]:
    lex = LEX_GRAPH if TASK_KIND[rec["task"]] == "graph" else LEX_SORT
    text = rec["output_text"]
    m = lex.search(text)
    if m is None:
        return -1, True
    spans = token_spans(tok, rec["output_token_ids"], text)
    for k, (a, b) in enumerate(spans):
        if b > m.start():
            return (k, False) if k < FALLBACK_MAX else (-1, True)
    return -1, True


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


@torch.no_grad()
def process_file(model, tok, path: Path, out: Path, check: bool) -> dict:
    recs = load_jsonl(path)
    n = len(recs)
    L = len(LAYERS)
    d = model.config.hidden_size
    window = np.zeros((n, L, d), np.float16)
    pre = np.full((n, L, d), np.nan, np.float16)
    cpos = np.zeros(n, np.int32)
    fb = np.zeros(n, bool)
    seqs = []
    for i, r in enumerate(recs):
        c, f = commit_pos(tok, r)
        no = len(r["output_token_ids"])
        if f or no == 0:
            w0, w1 = 0, min(31, max(no - 1, 0))
        else:
            w0, w1 = c, min(c + WIN, no - 1)
        cpos[i], fb[i] = c, f
        p0, p1 = (max(0, c - WIN), c - 1) if (not f and c >= 4) else (None, None)
        np_ = len(r["prompt_token_ids"])
        ids = r["prompt_token_ids"] + r["output_token_ids"][: w1 + 1]
        if len(ids) <= np_:  # empty output: pool the last prompt token
            ids = r["prompt_token_ids"]
            w0 = w1 = -1
        seqs.append(dict(i=i, ids=ids, np=np_, w=(w0, w1), p=(p0, p1)))
    order = sorted(range(n), key=lambda k: len(seqs[k]["ids"]))
    bs = 32
    k = 0
    diffs = []
    while k < n:
        batch = [seqs[j] for j in order[k:k + bs]]
        maxlen = max(len(s["ids"]) for s in batch)
        inp = torch.full((len(batch), maxlen), tok.pad_token_id, dtype=torch.long)
        att = torch.zeros((len(batch), maxlen), dtype=torch.long)
        for b, s in enumerate(batch):
            inp[b, : len(s["ids"])] = torch.tensor(s["ids"])
            att[b, : len(s["ids"])] = 1
        try:
            outm = model.model(input_ids=inp.cuda(), attention_mask=att.cuda(), output_hidden_states=True)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            bs = max(1, bs // 2)
            logger.warning(f"OOM -> batch {bs}")
            continue
        hs = outm.hidden_states
        stack = torch.stack([hs[l] for l in LAYERS], 1)  # [B, L, T, d]
        for b, s in enumerate(batch):
            w0, w1 = s["w"]
            a0 = s["np"] + w0 if w0 >= 0 else len(s["ids"]) - 1
            a1 = s["np"] + w1 if w1 >= 0 else len(s["ids"]) - 1
            window[s["i"]] = stack[b, :, a0:a1 + 1].float().mean(1).cpu().numpy().astype(np.float16)
            p0, p1 = s["p"]
            if p0 is not None:
                pre[s["i"]] = stack[b, :, s["np"] + p0:s["np"] + p1 + 1].float().mean(1).cpu().numpy() \
                    .astype(np.float16)
        if check and len(diffs) < 50:
            last = hs[-1]
            logits = model.lm_head(last).float().log_softmax(-1)
            for b, s in enumerate(batch):
                if len(diffs) >= 50:
                    break
                r = recs[s["i"]]
                no = len(s["ids"]) - s["np"]
                if no <= 0:
                    continue
                pos = torch.arange(s["np"] - 1, s["np"] - 1 + no, device=logits.device)
                tgt = torch.tensor(r["output_token_ids"][:no], device=logits.device)
                hf = logits[b, pos, tgt].cpu().numpy()
                vl = np.array([x if x is not None else np.nan for x in r["sampled_logprobs"][:no]], float)
                diffs.append(float(np.nanmean(np.abs(hf - vl))))
            del logits
        del outm, hs, stack
        k += len(batch)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, window=window, precommit=pre, c_pos=cpos, fallback=fb, ids=np.array([r["id"] for r in recs]))
    res = dict(file=str(path.relative_to(DATA.parent)), n=n, fallback_rate=float(fb.mean()))
    if diffs:
        res["align_mean_abs_logprob_diff"] = float(np.mean(diffs))
        res["align_n"] = len(diffs)
    return res


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--check", action="store_true", help="alignment check on first 50 seqs of each file")
    ap.add_argument("--include-pilot", action="store_true")
    args = ap.parse_args()
    from transformers import AutoModelForCausalLM, AutoTokenizer

    free, total = torch.cuda.mem_get_info(0)
    logger.info(f"VRAM free {free / 1e9:.1f}/{total / 1e9:.1f} GB")
    torch.cuda.set_per_process_memory_fraction(min(0.9, (free - 0.5e9) / total))
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    files = []
    for p in sorted(GEN.glob("*/*.jsonl")):
        cond = p.stem
        if cond == "comention" or (cond == "pilot" and not args.include_pilot):
            continue
        key = f"{p.parent.name}/{cond}"
        if args.only and key not in args.only.split(","):
            continue
        files.append(p)
    stats_p = DATA / "acts_stats.jsonl"
    for p in files:
        out = ACTS / p.parent.name / f"{p.stem}.npz"
        n = sum(1 for x in p.read_text().splitlines() if x.strip())
        if out.exists():
            try:
                if len(np.load(out)["ids"]) == n:
                    continue
            except (OSError, ValueError, KeyError):
                pass
        t0 = time.time()
        res = process_file(model, tok, p, out, check=args.check or p.stem in ("baseline", "pilot"))
        res["seconds"] = time.time() - t0
        logger.info(json.dumps(res))
        with stats_p.open("a") as fh:
            fh.write(json.dumps(res) + "\n")
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
