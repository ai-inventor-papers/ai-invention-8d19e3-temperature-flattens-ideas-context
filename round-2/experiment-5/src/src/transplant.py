#!/usr/bin/env python3
"""STEP 6: causal transplant C2c with HF forward hooks (custom KV-cached decode loop).

PositionedAdd: at layer l_a (= first layer of the frozen band; hidden_states index, i.e. output of
model.model.layers[l_a-1]), in PREFILL ONLY, h[:, -5:, :] += V[5, d]. With left padding the last 5 positions
are the aligned chat-template suffix '<|im_end|>\\n<|im_start|>assistant\\n' for every row. Generated tokens
read the edited K/V of the suffix positions; no change at generated steps (primary variant).

Sampling: per-sample inverse-CDF with pre-drawn uniforms U[seed][step] (common random numbers, as in the
influence arm's SeededSampler), T=0.7, top-p 1, top-k off; CodeStop ON (stop once a ```python block closes);
max_new 640. Cells (n=60, seeds 1000..1059): REF_ban, TRANSPLANT, RESTORE, RAND_1..5, OFFTARGET (+ REF_placebo
per task), secondary SUFFIX_CEILING and ALLPOS for 2 bans, layer sweep for T1 ban_r1.

Usage: python src/transplant.py test | run [--n 60] [--only primary|random|secondary|sweep]
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
from loguru import logger  # noqa: E402
from freeze import assert_frozen  # noqa: E402
from protocol import MODEL, ROOT  # noqa: E402
from protocol_ext import user_message  # noqa: E402

try:
    from torch._native import registry as _native_registry
    _native_registry.deregister_op_overrides(disable_dsl_names=["triton"])
except (ImportError, AttributeError, TypeError):
    pass

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "transplant.log", rotation="30 MB", level="DEBUG")
OUT = ROOT / "data" / "transplant"
EOS = (151645, 151643)
PY_CLOSED_RE = re.compile(r"```[ \t]*(?:python|py|Python|python3)[ \t]*\n.*?```", re.S)
TEMP = 0.7
MAX_NEW = 640
PRE_BANS = [("T1", "ban_r1"), ("T1", "ban_r4"), ("T1", "ban_top3"), ("T2", "ban_rare"), ("T2", "ban_top5"),
            ("T3", "ban_r1")]
OFFTARGET = {("T1", "ban_r1"): "ban_r4", ("T1", "ban_r4"): "ban_r1", ("T1", "ban_top3"): "ban_r1",
             ("T2", "ban_rare"): "ban_top5", ("T2", "ban_top5"): "ban_rare", ("T3", "ban_r1"): "ban_top3"}
SECONDARY = [("T1", "ban_r1"), ("T2", "ban_top5")]
SWEEP_LAYERS = [8, 18]
KNOCK_BANS = [("T1", "ban_r1"), ("T1", "ban_r4"), ("T2", "ban_top5"), ("T2", "ban_rare")]


def load_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda")
    model.eval()
    return tok, model


def render(tok, umsg: str) -> str:
    return tok.apply_chat_template([{"role": "user", "content": umsg}], tokenize=False, add_generation_prompt=True)


def uniforms_for(seed: int, n: int) -> torch.Tensor:
    g = torch.Generator(device="cpu").manual_seed(int(seed))
    return torch.rand(n, generator=g, dtype=torch.float64)


def backtick_ids(tok) -> torch.Tensor:
    ids = [i for t, i in tok.get_vocab().items() if "`" in tok.convert_tokens_to_string([t])]
    return torch.tensor(sorted(ids), device="cuda")


class Hooks:
    """Per-row prefill suffix add at chosen layers, optional all-position add, optional suffix overwrite."""

    def __init__(self, model):
        self.layers = model.model.layers
        self.handles = []
        self.add_suffix: dict[int, torch.Tensor] = {}  # l -> [B, 5, d] float32
        self.add_all: dict[int, torch.Tensor] = {}  # l -> [B, d] float32 (prefill all positions + every step)
        self.set_suffix: dict[int, tuple[torch.Tensor, torch.Tensor]] = {}  # l -> (rows mask [B], target [B,5,d])
        self.capture: dict[int, torch.Tensor] = {}
        self.capture_layers: list[int] = []

    def __enter__(self):
        ls = set(self.add_suffix) | set(self.add_all) | set(self.set_suffix) | set(self.capture_layers)
        for l in sorted(ls):
            self.handles.append(self.layers[l - 1].register_forward_hook(self._hook(l)))
        return self

    def __exit__(self, *exc):
        for h in self.handles:
            h.remove()
        self.handles = []
        for layer in self.layers:
            assert not layer._forward_hooks and not layer._forward_pre_hooks, "hook leak"

    def _hook(self, l: int):
        def hook(module, inp, out):
            hs = out[0] if isinstance(out, tuple) else out
            S = hs.shape[1]
            mod = False
            if S > 1 and l in self.add_suffix:
                hs = hs.clone()
                hs[:, -5:, :] = (hs[:, -5:, :].float() + self.add_suffix[l]).to(hs.dtype)
                mod = True
            if l in self.add_all:
                hs = hs.clone() if not mod else hs
                hs[:] = (hs.float() + self.add_all[l][:, None, :]).to(hs.dtype)
                mod = True
            if S > 1 and l in self.set_suffix:
                rows, tgt = self.set_suffix[l]
                hs = hs.clone() if not mod else hs
                cur = hs[:, -5:, :]
                hs[:, -5:, :] = torch.where(rows[:, None, None], tgt.to(hs.dtype), cur)
                mod = True
            if S > 1 and l in self.capture_layers:
                self.capture[l] = hs.detach().float().clone()
            if mod:
                return (hs,) + tuple(out[1:]) if isinstance(out, tuple) else hs
            return None
        return hook


@torch.inference_mode()
def generate(tok, model, texts: list[str], seeds: list[int], hooks: Hooks, tick: torch.Tensor,
             max_new: int = MAX_NEW, code_stop: bool = True, knock: list[tuple[int, int]] | None = None) -> dict:
    """knock[i] = (a, b): after prefill, generated tokens of row i cannot attend to prompt columns
    [T-a, T-b) counted from the right (the ban/placebo sentence); prefill itself is untouched."""
    from transformers import DynamicCache
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
    attn = enc["attention_mask"]
    pos = (attn.cumsum(-1) - 1).clamp(min=0)
    B = attn.shape[0]
    U = torch.stack([uniforms_for(s, max_new) for s in seeds]).to("cuda")
    cache = DynamicCache()
    done = torch.zeros(B, dtype=torch.bool, device="cuda")
    out_ids = torch.full((B, max_new), tok.pad_token_id, dtype=torch.long, device="cuda")
    n_gen = torch.zeros(B, dtype=torch.long, device="cuda")
    t0 = time.time()
    with hooks:
        o = model(input_ids=enc["input_ids"], attention_mask=attn, position_ids=pos, past_key_values=cache,
                  use_cache=True, logits_to_keep=1)
        logits = o.logits[:, -1]
        cur_pos = pos[:, -1:]
        if knock:
            T = attn.shape[1]
            attn = attn.clone()
            for i, ab in enumerate(knock):
                if ab is not None and ab[0] > ab[1]:
                    attn[i, T - ab[0]:T - ab[1]] = 0
        for step in range(max_new):
            p = torch.softmax(logits.float() / TEMP, dim=-1).double()
            cdf = torch.cumsum(p, dim=-1)
            u = U[:, step:step + 1] * cdf[:, -1:]
            nxt = torch.searchsorted(cdf, u).clamp(max=p.shape[-1] - 1)
            bad = p.gather(1, nxt) <= 0
            if bool(bad.any()):
                nxt = torch.where(bad, torch.argmax(p, dim=-1, keepdim=True), nxt)
            nxt = nxt[:, 0]
            nxt = torch.where(done, torch.full_like(nxt, tok.pad_token_id), nxt)
            out_ids[:, step] = nxt
            n_gen += (~done).long()
            done = done | torch.isin(nxt, torch.tensor(EOS, device="cuda"))
            if code_stop:
                hit = torch.isin(nxt, tick) & ~done
                for i in torch.nonzero(hit).flatten().tolist():
                    txt = tok.decode(out_ids[i, :step + 1].tolist(), skip_special_tokens=True)
                    if PY_CLOSED_RE.search(txt):
                        done[i] = True
            if bool(done.all()):
                break
            attn = torch.cat([attn, torch.ones((B, 1), dtype=attn.dtype, device="cuda")], 1)
            cur_pos = cur_pos + 1
            o = model(input_ids=nxt[:, None], attention_mask=attn, position_ids=cur_pos, past_key_values=cache,
                      use_cache=True)
            logits = o.logits[:, -1]
    dt = time.time() - t0
    texts_out, ids_out = [], []
    for i in range(B):
        ids = out_ids[i, :int(n_gen[i])].tolist()
        ids_out.append(ids)
        texts_out.append(tok.decode(ids, skip_special_tokens=True))
    del cache, o, logits, enc
    return dict(texts=texts_out, ids=ids_out, seconds=dt, hit_max=[len(x) >= max_new for x in ids_out])


# ------------------------------------------------------------------------------------------------ vectors
def load_ps(task: str) -> dict:
    z = np.load(ROOT / "acts" / f"prompt_states_screen_{task}.npz")
    out: dict = {}
    for k in z.files:
        c, part = k.rsplit("__", 1)
        out.setdefault(c, {})[part] = z[k]
    return out


def suffix_delta(ps: dict, cond: str, l: int, massive: list[int]) -> np.ndarray:
    d = ps[cond]["suf"][l - 1] - ps["placebo"]["suf"][l - 1]  # [5, d]
    if massive:
        d = d.copy()
        d[:, massive] = 0
    return d


def random_like(delta: np.ndarray, seed: int, massive: list[int]) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = rng.standard_normal(delta.shape)
    if massive:
        r[:, massive] = 0
    r = r / np.linalg.norm(r, axis=1, keepdims=True) * np.linalg.norm(delta, axis=1, keepdims=True)
    return r


def plan_ban_text(task: str, cond: str) -> str:
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())
    return user_message(task, cond, plan[task][cond])


def build_cells(frozen: dict, which: set[str]) -> list[dict]:
    """Each cell: task, ban, cell, text (user message), spec dict for hooks."""
    l_a = frozen["band"][0]
    massive = frozen["massive_dims"]
    cells = []
    pss = {t: load_ps(t) for t in ("T1", "T2", "T3")}
    if "primary" in which:
        for t in ("T1", "T2", "T3"):
            cells.append(dict(task=t, ban="placebo", cell="REF_placebo", text=user_message(t, "placebo"), spec={}))
    for t, b in PRE_BANS:
        ps = pss[t]
        D = suffix_delta(ps, b, l_a, massive)
        ban_txt, pl_txt = plan_ban_text(t, b), user_message(t, "placebo")
        if "primary" in which:
            cells += [dict(task=t, ban=b, cell="REF_ban", text=ban_txt, spec={}),
                      dict(task=t, ban=b, cell="TRANSPLANT", text=pl_txt, spec={"add_suffix": {l_a: D}}),
                      dict(task=t, ban=b, cell="RESTORE", text=ban_txt, spec={"add_suffix": {l_a: -D}})]
        if "random" in which:
            for i in range(1, 6):
                cells.append(dict(task=t, ban=b, cell=f"RAND_{i}", text=pl_txt,
                                  spec={"add_suffix": {l_a: random_like(D, 777 + i, massive)}}))
            Do = suffix_delta(ps, OFFTARGET[(t, b)], l_a, massive)
            cells.append(dict(task=t, ban=b, cell="OFFTARGET", text=pl_txt, spec={"add_suffix": {l_a: Do}}))
        if "secondary" in which and (t, b) in SECONDARY:
            tgt = {l: ps[b]["suf"][l - 1] for l in range(1, 36)}
            cells.append(dict(task=t, ban=b, cell="SUFFIX_CEILING", text=pl_txt, spec={"set_suffix": tgt}))
            cells.append(dict(task=t, ban=b, cell="ALLPOS", text=pl_txt, spec={"add_all": {l_a: D.mean(0)}}))
        if "knockout" in which and (t, b) in KNOCK_BANS:
            cells.append(dict(task=t, ban=b, cell="KNOCKOUT_BAN", text=ban_txt, spec={"knock": True}))
            cells.append(dict(task=t, ban=b, cell="KNOCKOUT_PLACEBO_SENT", text=pl_txt, spec={"knock": True}))
        if "sweep" in which and (t, b) == ("T1", "ban_r1"):
            for l in SWEEP_LAYERS:
                cells.append(dict(task=t, ban=b, cell=f"TRANSPLANT_L{l}", text=pl_txt,
                                  spec={"add_suffix": {l: suffix_delta(ps, b, l, massive)}}))
    return cells


def make_hooks(model, rows: list[dict], d: int) -> Hooks:
    """rows: list of cell specs (one per batch row)."""
    H = Hooks(model)
    B = len(rows)
    for key in ("add_suffix", "add_all"):
        ls = sorted({l for r in rows for l in r["spec"].get(key, {})})
        for l in ls:
            shape = (B, 5, d) if key == "add_suffix" else (B, d)
            V = np.zeros(shape, np.float32)
            for i, r in enumerate(rows):
                if l in r["spec"].get(key, {}):
                    V[i] = r["spec"][key][l]
            getattr(H, key)[l] = torch.tensor(V, device="cuda")
    ls = sorted({l for r in rows for l in r["spec"].get("set_suffix", {})})
    for l in ls:
        mask = torch.tensor([l in r["spec"].get("set_suffix", {}) for r in rows], device="cuda")
        T = np.zeros((B, 5, d), np.float32)
        for i, r in enumerate(rows):
            if l in r["spec"].get("set_suffix", {}):
                T[i] = r["spec"]["set_suffix"][l]
        H.set_suffix[l] = (mask, torch.tensor(T, device="cuda"))
    return H


def cell_path(c: dict) -> Path:
    return OUT / c["task"] / c["ban"] / f"{c['cell']}.jsonl"


def run_cells(tok, model, cells: list[dict], seeds: list[int], batch: int) -> None:
    tick = backtick_ids(tok)
    d = model.config.hidden_size
    todo = []
    for c in cells:
        p = cell_path(c)
        done = set()
        if p.exists():
            done = {json.loads(x)["seed"] for x in p.read_text().splitlines() if x.strip()}
        for s in seeds:
            if s not in done:
                todo.append((c, s))
    logger.info(f"{len(todo)} generations to run ({len(cells)} cells)")
    # group by task so rows in a batch share a prompt family (similar lengths)
    todo.sort(key=lambda x: (x[0]["task"], x[1]))
    k = 0
    bs = batch
    while k < len(todo):
        chunk = todo[k:k + bs]
        rows = [c for c, _ in chunk]
        texts = [render(tok, c["text"]) for c in rows]
        H = make_hooks(model, rows, d)
        knock = None
        if any(c["spec"].get("knock") for c in rows):
            knock = []
            for c, txt in zip(rows, texts):
                if not c["spec"].get("knock"):
                    knock.append(None)
                    continue
                base = render(tok, user_message(c["task"], "baseline"))
                n_full = len(tok(txt, add_special_tokens=False)["input_ids"])
                n_base = len(tok(base, add_special_tokens=False)["input_ids"])
                knock.append((5 + (n_full - n_base), 5))  # the sentence sits right before the 5-token suffix
        try:
            res = generate(tok, model, texts, [s for _, s in chunk], H, tick, knock=knock)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            bs = max(8, bs // 2)
            logger.warning(f"OOM -> batch {bs}")
            continue
        by: dict[Path, list[str]] = {}
        for (c, s), txt, ids, hm in zip(chunk, res["texts"], res["ids"], res["hit_max"]):
            rec = dict(id=f"{c['task']}|{c['ban']}|{c['cell']}|{s}", task=c["task"], condition=f"{c['ban']}:{c['cell']}",
                       ban=c["ban"], cell=c["cell"], banned=[], seed=s, user_message=c["text"], output_text=txt,
                       output_token_ids=ids, hit_max=hm, engine="hf_transplant")
            by.setdefault(cell_path(c), []).append(json.dumps(rec))
        for p, lines in by.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as fh:
                fh.write("\n".join(lines) + "\n")
        ntok = sum(len(x) for x in res["ids"])
        logger.info(f"batch {k // bs}: {len(chunk)} rows, {ntok} tokens, {res['seconds']:.1f}s "
                    f"({ntok / res['seconds']:.0f} tok/s); progress {k + len(chunk)}/{len(todo)}")
        k += len(chunk)
        gc.collect()
        torch.cuda.empty_cache()


@torch.inference_mode()
def hook_tests(tok, model, frozen: dict) -> dict:
    """T6: zero-vector identity, exact positioned edit, Delta reproduces the ban suffix state, left padding."""
    out = {}
    l_a = frozen["band"][0]
    ps = load_ps("T1")
    tick = backtick_ids(tok)
    d = model.config.hidden_size
    pl = render(tok, user_message("T1", "placebo"))
    ban = render(tok, plan_ban_text("T1", "ban_r1"))
    # (i) zero vector == no hook, 8 seeds (common random numbers)
    seeds = list(range(1000, 1008))
    r0 = generate(tok, model, [pl] * 8, seeds, Hooks(model), tick, max_new=64)
    Hz = Hooks(model)
    Hz.add_suffix[l_a] = torch.zeros((8, 5, d), device="cuda")
    r1 = generate(tok, model, [pl] * 8, seeds, Hz, tick, max_new=64)
    out["zero_vector_identical"] = r0["ids"] == r1["ids"]
    # (ii) exact positioned edit at l_a on a mixed-length batch; (v) suffix rows identical
    texts = [pl, ban]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
    suf_ids = enc["input_ids"][:, -5:].tolist()
    out["left_pad_suffix_identical"] = suf_ids[0] == suf_ids[1] and \
        tok.decode(suf_ids[0]) == "<|im_end|>\n<|im_start|>assistant\n"
    pos = (enc["attention_mask"].cumsum(-1) - 1).clamp(min=0)
    Hc = Hooks(model)
    Hc.capture_layers = [l_a]
    with Hc:
        model(**enc, position_ids=pos)
    base = Hc.capture[l_a]
    V = torch.randn((2, 5, d), device="cuda") * 3
    Hv = Hooks(model)
    Hv.capture_layers = [l_a]
    Hv.add_suffix[l_a] = V
    with Hv:
        model(**enc, position_ids=pos)
    edited = Hv.capture[l_a]
    diff = (edited - base)
    out["edit_other_positions_maxabs"] = float(diff[:, :-5].abs().max())
    exp = (base[:, -5:] + V).to(torch.bfloat16).float()
    out["edit_suffix_maxabs_vs_expected"] = float((edited[:, -5:] - exp).abs().max())
    # (iii) placebo + Delta at l_a reproduces suf[ban] at l_a (batch 1)
    D = torch.tensor(suffix_delta(ps, "ban_r1", l_a, []), device="cuda")
    enc1 = tok([pl], return_tensors="pt", add_special_tokens=False).to("cuda")
    Hd = Hooks(model)
    Hd.capture_layers = [l_a]
    Hd.add_suffix[l_a] = D[None]
    with Hd:
        model(**enc1)
    got = Hd.capture[l_a][0, -5:].cpu().numpy()
    want = ps["ban_r1"]["suf"][l_a - 1]
    out["delta_reproduces_ban_suffix_rel_err"] = float(np.linalg.norm(got - want) / np.linalg.norm(want))
    # padded vs unpadded suffix state (batch drift, relative L2)
    enc2 = tok([pl, ban], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
    pos2 = (enc2["attention_mask"].cumsum(-1) - 1).clamp(min=0)
    Hp = Hooks(model)
    Hp.capture_layers = [l_a]
    with Hp:
        model(**enc2, position_ids=pos2)
    padded_row = Hp.capture[l_a][0, -5:].cpu().numpy()  # placebo is the shorter prompt -> padded
    want_pl = ps["placebo"]["suf"][l_a - 1]
    out["left_pad_suffix_state_rel_l2"] = float(np.linalg.norm(padded_row - want_pl) / np.linalg.norm(want_pl))
    out["hook_leak_assert"] = "passed (Hooks.__exit__ asserts no residual hooks)"
    logger.info(f"hook tests: {out}")
    assert out["zero_vector_identical"] and out["edit_other_positions_maxabs"] == 0.0 and out["left_pad_suffix_identical"]
    return out


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["test", "run", "mini"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--only", default="primary,random,secondary,sweep")
    ap.add_argument("--batch", type=int, default=96)
    args = ap.parse_args()
    assert_frozen(ROOT / "results" / "frozen_predictors.json")
    frozen = json.loads((ROOT / "results" / "frozen_predictors.json").read_text())
    free, total = torch.cuda.mem_get_info(0)
    torch.cuda.set_per_process_memory_fraction(min(0.92, (free - 0.5e9) / total))
    tok, model = load_model()
    if args.mode == "test":
        res = hook_tests(tok, model, frozen)
        (ROOT / "results" / "transplant_hook_tests.json").write_text(json.dumps(res, indent=1))
        return
    if args.mode == "mini":
        global OUT
        OUT = ROOT / "data" / "transplant_mini"
        cells = [c for c in build_cells(frozen, {"primary"}) if c["task"] == "T1" and c["ban"] in ("ban_r1", "placebo")]
        run_cells(tok, model, cells, list(range(1000, 1000 + args.n)), args.batch)
        return
    order = [w for w in ("primary", "random", "secondary", "sweep", "knockout") if w in args.only.split(",")]
    for w in order:
        cells = build_cells(frozen, {w})
        logger.info(f"=== {w}: {len(cells)} cells x n={args.n}")
        run_cells(tok, model, cells, list(range(1000, 1000 + args.n)), args.batch)


if __name__ == "__main__":
    main()
