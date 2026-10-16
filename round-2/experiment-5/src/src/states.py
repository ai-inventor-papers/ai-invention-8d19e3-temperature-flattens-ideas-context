#!/usr/bin/env python3
"""HF activations (bf16, sdpa, model on cuda). Layer index l in 1..35 = hidden_states[l] (raw block output);
hidden_states[36] is post-final-norm and is excluded from projections.

1a PROMPT STATE: one forward pass per distinct prompt (batch 1): suf = hs[1..35][-5:] float32 [35,5,d] and
   umean = mean over the user-message token positions [35,d].
1b GENERATED WINDOW: teacher-force stored outputs, window [c, c+16] at the commitment token (ban-arm regex;
   fallback first 32 tokens), mean per layer, float16.

Usage:
  python src/states.py screen                 # screen prompt states + baseline/forced windows (all layers) + checks
  python src/states.py band --layers 20,21,22 # windows of all other screen conditions at the band layers
  python src/states.py prompts --jobs data/conf/jobs_X.json --out acts/prompt_states_conf_X  # prompt states only
  python src/states.py conf --layers 20,21,22 --root data/conf   # windows of confirmation generations
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import activations as A  # noqa: E402  (its import resets loguru sinks; configure ours after)
from loguru import logger  # noqa: E402
from protocol import MODEL, ROOT, TASK_KIND, TASKS  # noqa: E402
from protocol_ext import user_message  # noqa: E402

try:  # torch>=2.14 triton overrides need a C compiler; harmless on older torch
    from torch._native import registry as _native_registry
    _native_registry.deregister_op_overrides(disable_dsl_names=["triton"])
except (ImportError, AttributeError, TypeError):
    pass

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "states.log", rotation="30 MB", level="DEBUG")
ACTS = ROOT / "acts"
NL = 35  # layers 1..35
S_SUFFIX = 5
LEX_SELECT = re.compile(r"quickselect|quick select|heap|sort|median|partition|pivot|binary search|count|bucket|"
                        r"select|nsmallest|min\(", re.I)


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def load_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda")
    model.eval()
    return tok, model


def render(tok, umsg: str) -> str:
    return tok.apply_chat_template([{"role": "user", "content": umsg}], tokenize=False, add_generation_prompt=True)


def user_span(ids: list[int], tok) -> tuple[int, int]:
    """[a, b) token span of the user message: after '<|im_start|>user\\n', before the final '<|im_end|>'."""
    im_start = tok.convert_tokens_to_ids("<|im_start|>")
    starts = [i for i, t in enumerate(ids) if t == im_start]
    a = starts[-2] + 3  # <|im_start|> user \n
    b = len(ids) - S_SUFFIX
    return a, b


@torch.inference_mode()
def prompt_states(tok, model, prompts: dict[str, str], check_user: dict[str, str] | None = None) -> dict:
    """prompts: name -> rendered text. Returns {name: (suf [35,5,d] f32, umean [35,d] f32)}."""
    out = {}
    for name, text in prompts.items():
        ids = tok(text, add_special_tokens=False)["input_ids"]
        a, b = user_span(ids, tok)
        if check_user is not None:
            assert tok.decode(ids[a:b]) == check_user[name], (tok.decode(ids[a:b]), check_user[name])
        hs = model.model(input_ids=torch.tensor([ids], device="cuda"), output_hidden_states=True).hidden_states
        st = torch.stack([hs[l][0] for l in range(1, NL + 1)])  # [35, T, d]
        out[name] = (st[:, -S_SUFFIX:].float().cpu().numpy(), st[:, a:b].float().mean(1).cpu().numpy())
        del hs, st
    return out


@torch.inference_mode()
def batch_drift(tok, model, texts: list[str]) -> float:
    """max |suffix state (batch 16, left padded) - batch 1| over 10 prompts, relative to the mean norm."""
    tok.padding_side = "left"
    texts16 = (texts * 2)[:16]
    enc = tok(texts16, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
    pos = (enc["attention_mask"].cumsum(-1) - 1).clamp(min=0)
    hs = model.model(**enc, position_ids=pos, output_hidden_states=True).hidden_states
    rel = []
    single = prompt_states(tok, model, {str(i): t for i, t in enumerate(texts)})
    for i, t in enumerate(texts):
        b16 = torch.stack([hs[l][i, -S_SUFFIX:] for l in range(1, NL + 1)]).float().cpu().numpy()
        s1 = single[str(i)][0]
        rel.append(float(np.abs(b16 - s1).max() / np.linalg.norm(s1, axis=-1).mean()))
    return float(np.max(rel))


def commit_pos(tok, rec: dict) -> tuple[int, bool]:
    if rec["task"] != "T4":
        return A.commit_pos(tok, rec)
    text = rec["output_text"]
    m = LEX_SELECT.search(text)
    if m is None:
        return -1, True
    spans = A.token_spans(tok, rec["output_token_ids"], text)
    for k, (_, b) in enumerate(spans):
        if b > m.start():
            return (k, False) if k < A.FALLBACK_MAX else (-1, True)
    return -1, True


@torch.inference_mode()
def gen_windows(tok, model, recs: list[dict], layers: list[int], check: int = 0) -> dict:
    """Window mean per layer for each record: [n, len(layers), d] float16, c_pos, fallback, ids, align diffs."""
    n, d = len(recs), model.config.hidden_size
    window = np.zeros((n, len(layers), d), np.float16)
    cpos = np.zeros(n, np.int32)
    fb = np.zeros(n, bool)
    seqs = []
    for i, r in enumerate(recs):
        c, f = commit_pos(tok, r)
        no = len(r["output_token_ids"])
        w0, w1 = (0, min(31, max(no - 1, 0))) if (f or no == 0) else (c, min(c + A.WIN, no - 1))
        cpos[i], fb[i] = c, f
        np_ = len(r["prompt_token_ids"])
        ids = r["prompt_token_ids"] + r["output_token_ids"][: w1 + 1]
        if len(ids) <= np_:
            ids, w0, w1 = r["prompt_token_ids"], -1, -1
        seqs.append(dict(i=i, ids=ids, np=np_, w=(w0, w1)))
    order = sorted(range(n), key=lambda k: len(seqs[k]["ids"]))
    bs, k, diffs = 32, 0, []
    pad = tok.pad_token_id if tok.pad_token_id is not None else 151643
    while k < n:
        batch = [seqs[j] for j in order[k:k + bs]]
        maxlen = max(len(s["ids"]) for s in batch)
        inp = torch.full((len(batch), maxlen), pad, dtype=torch.long)
        att = torch.zeros((len(batch), maxlen), dtype=torch.long)
        for b, s in enumerate(batch):  # right padding: positions are exact for every row
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
        for b, s in enumerate(batch):
            w0, w1 = s["w"]
            a0 = s["np"] + w0 if w0 >= 0 else len(s["ids"]) - 1
            a1 = s["np"] + w1 if w1 >= 0 else len(s["ids"]) - 1
            window[s["i"]] = torch.stack([hs[l][b, a0:a1 + 1].float().mean(0) for l in layers]).cpu().numpy() \
                .astype(np.float16)
        if check and len(diffs) < check:
            logits = model.lm_head(hs[-1]).float().log_softmax(-1)
            for b, s in enumerate(batch):
                if len(diffs) >= check:
                    break
                r = recs[s["i"]]
                no = len(s["ids"]) - s["np"]
                if no <= 0 or not r.get("sampled_logprobs"):
                    continue
                pos = torch.arange(s["np"] - 1, s["np"] - 1 + no, device=logits.device)
                tgt = torch.tensor(r["output_token_ids"][:no], device=logits.device)
                hf = logits[b, pos, tgt].cpu().numpy()
                vl = np.array([x if x is not None else np.nan for x in r["sampled_logprobs"][:no]], float)
                diffs.append(float(np.nanmean(np.abs(hf - vl))))
            del logits
        del outm, hs
        k += len(batch)
    return dict(window=window, c_pos=cpos, fallback=fb, ids=np.array([r["id"] for r in recs]), diffs=diffs)


def save_npz(path: Path, **arrs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **arrs)


def screen_files(task: str) -> list[str]:
    return sorted(p.stem for p in (ROOT / "data" / "gen" / task).glob("*.jsonl") if p.stem != "comention")


def forced_records(task: str, cond: str) -> list[dict]:
    recs = load_jsonl(ROOT / "data" / "gen" / task / f"{cond}.jsonl") if (ROOT / "data" / "gen" / task / f"{cond}.jsonl").exists() else []
    ext = ROOT / "data" / "conf" / "gen" / task / f"{cond}.jsonl"
    return recs + (load_jsonl(ext) if ext.exists() else [])


def stage_screen(tok, model) -> dict:
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())
    stats: dict = {"tasks": {}}
    all_layers = list(range(1, NL + 1))
    for t in TASKS:
        conds = screen_files(t)
        prompts, users = {}, {}
        for c in conds:
            r = json.loads((ROOT / "data" / "gen" / t / f"{c}.jsonl").read_text().splitlines()[0])
            prompts[c], users[c] = r["prompt_text"], r["user_message"]
            assert r["prompt_text"] == render(tok, user_message(t, c, plan[t].get(c, [])))
        for p in sorted((ROOT / "data" / "conf" / "gen" / t).glob("forced_*.jsonl")):
            if p.stem not in prompts:
                r = json.loads(p.read_text().splitlines()[0])
                prompts[p.stem], users[p.stem] = r["prompt_text"], r["user_message"]
        t0 = time.time()
        ps = prompt_states(tok, model, prompts, users)
        if t == "T1":  # determinism (batch 1 twice) + batch drift
            again = prompt_states(tok, model, {k: prompts[k] for k in list(prompts)[:5]})
            stats["prompt_state_bitwise_repeat"] = bool(all(np.array_equal(again[k][0], ps[k][0]) for k in again))
            stats["batch16_drift_rel_max"] = batch_drift(tok, model, [prompts[k] for k in list(prompts)[:10]])
        save_npz(ACTS / f"prompt_states_screen_{t}.npz", **{f"{k}__suf": v[0] for k, v in ps.items()},
                 **{f"{k}__umean": v[1] for k, v in ps.items()})
        logger.info(f"{t}: prompt states for {len(ps)} prompts in {time.time() - t0:.1f}s")
        # windows at all layers for baseline + forced (stored + extension)
        st = {}
        for c in ["baseline"] + sorted({k for k in prompts if k.startswith("forced_")}):
            recs = load_jsonl(ROOT / "data" / "gen" / t / "baseline.jsonl") if c == "baseline" else forced_records(t, c)
            t0 = time.time()
            res = gen_windows(tok, model, recs, all_layers, check=50 if c == "baseline" else 0)
            save_npz(ACTS / "gen" / t / f"{c}.npz", window=res["window"], c_pos=res["c_pos"], fallback=res["fallback"],
                     ids=res["ids"], layers=np.array(all_layers))
            st[c] = dict(n=len(recs), fallback_rate=float(res["fallback"].mean()), seconds=time.time() - t0)
            if res["diffs"]:
                st[c]["align_mean_abs_logprob_diff"] = float(np.mean(res["diffs"]))
                st[c]["align_n"] = len(res["diffs"])
            logger.info(f"{t}/{c}: {st[c]}")
            gc.collect()
            torch.cuda.empty_cache()
        stats["tasks"][t] = st
    return stats


def stage_band(tok, model, layers: list[int], root: Path, sub: str) -> dict:
    stats = {}
    for p in sorted((root / "gen").glob("*/*.jsonl")):
        t, c = p.parent.name, p.stem
        if c in ("comention",) or "__mini" in c:
            continue
        if sub == "screen" and (c == "baseline" or c.startswith("forced_")):
            continue
        if sub == "conf" and c.startswith("forced_") and t != "T4":
            continue  # T1-T3 forced extension already pooled with the screen forced files
        out = ACTS / ("gen" if sub == "screen" else "gen_conf") / t / f"{c}.npz"
        recs = load_jsonl(p)
        if out.exists():
            try:
                z = np.load(out)
                if len(z["ids"]) == len(recs) and list(z["layers"]) == layers:
                    continue
            except (OSError, KeyError, ValueError):
                pass
        res = gen_windows(tok, model, recs, layers)
        save_npz(out, window=res["window"], c_pos=res["c_pos"], fallback=res["fallback"], ids=res["ids"],
                 layers=np.array(layers))
        stats[f"{t}/{c}"] = dict(n=len(recs), fallback_rate=float(res["fallback"].mean()))
        logger.info(f"{t}/{c}: n={len(recs)} fallback={res['fallback'].mean():.2f}")
    return stats


def stage_prompts(tok, model, jobs_path: Path, out_prefix: str) -> None:
    jobs = json.loads(jobs_path.read_text())
    by_task: dict[str, dict] = {}
    for j in jobs:
        um = user_message(j["task"], j["condition"], j.get("banned") or [])
        by_task.setdefault(j["task"], {})[j["condition"]] = (render(tok, um), um)
    for t, d in by_task.items():
        ps = prompt_states(tok, model, {k: v[0] for k, v in d.items()}, {k: v[1] for k, v in d.items()})
        suf_ids = {tuple(tok(v[0], add_special_tokens=False)["input_ids"][-5:]) for v in d.values()}
        assert len(suf_ids) == 1 and tok.decode(list(next(iter(suf_ids)))) == "<|im_end|>\n<|im_start|>assistant\n"
        save_npz(ROOT / f"{out_prefix}_{t}.npz", **{f"{k}__suf": v[0] for k, v in ps.items()},
                 **{f"{k}__umean": v[1] for k, v in ps.items()})
        logger.info(f"{t}: prompt states for {len(ps)} prompts -> {out_prefix}_{t}.npz (suffix identity OK)")


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["screen", "band", "prompts", "conf"])
    ap.add_argument("--layers", default="")
    ap.add_argument("--jobs", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--root", default="data/conf")
    args = ap.parse_args()
    free, total = torch.cuda.mem_get_info(0)
    logger.info(f"VRAM free {free / 1e9:.1f}/{total / 1e9:.1f} GB")
    torch.cuda.set_per_process_memory_fraction(min(0.9, (free - 0.5e9) / total))
    tok, model = load_model()
    layers = [int(x) for x in args.layers.split(",")] if args.layers else []
    if args.stage == "screen":
        stats = stage_screen(tok, model)
        (ROOT / "results").mkdir(exist_ok=True)
        (ROOT / "results" / "activation_checks.json").write_text(json.dumps(stats, indent=1))
    elif args.stage == "band":
        stats = stage_band(tok, model, layers, ROOT / "data", "screen")
        (ROOT / "results" / "activation_checks_band.json").write_text(json.dumps(stats, indent=1))
    elif args.stage == "prompts":
        stage_prompts(tok, model, ROOT / args.jobs, args.out)
    else:
        stats = stage_band(tok, model, layers, ROOT / args.root, "conf")
        p = ROOT / "results" / "activation_checks_conf.json"
        old = json.loads(p.read_text()) if p.exists() else {}
        old.update(stats)
        p.write_text(json.dumps(old, indent=1))


if __name__ == "__main__":
    main()
