"""Single HF generation engine for EVERY condition.

- SeededSampler: per-sample inverse-CDF sampling with pre-drawn uniforms U[seed][step] (common random
  numbers). generate() runs greedy, so the emitted token is exactly the sampled one. Per-row temperature
  and top-k let rows of different settings share a batch.
- CodeStop: per-row stop once a ```python block has been closed (applied to ALL code conditions;
  everything after the first code block is unused prose).
- Steerer: forward hooks on model.model.layers[L] applying per-row interventions (add / project / leace)
  at the prompt-final token (prefill) and the first `window` generated tokens; capture hooks record mean
  residuals over gen1..8 and gen1..32 at chosen layers (post-intervention).
Layer convention: hs index l (1..36) == output of model.model.layers[l-1] == hidden_states[l].
"""

from __future__ import annotations

import gc
import re
import time
from dataclasses import dataclass, field

import numpy as np
import torch
from loguru import logger
try:  # torch>=2.14 routes some aten ops to triton kernels that need a C compiler (absent here): disable
    from torch._native import registry as _native_registry
    _native_registry.deregister_op_overrides(disable_dsl_names=["triton"])
except (ImportError, AttributeError, TypeError) as _e:  # older torch: nothing to disable
    pass
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig, LogitsProcessor, StoppingCriteria

PY_CLOSED_RE = re.compile(r"```[ \t]*(?:python|py|Python|python3)[ \t]*\n.*?```", re.S)


def load_model(model_id: str):
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
                                                 device_map="cuda")
    model.eval()
    return tok, model


def render(tok, user_prompt: str) -> str:
    return tok.apply_chat_template([{"role": "user", "content": user_prompt}], tokenize=False,
                                   add_generation_prompt=True)


def uniforms_for(seed: int, n: int) -> torch.Tensor:
    g = torch.Generator(device="cpu").manual_seed(int(seed))
    return torch.rand(n, generator=g, dtype=torch.float64)


class SeededSampler(LogitsProcessor):
    def __init__(self, U: torch.Tensor, temps: torch.Tensor, topk: torch.Tensor, prompt_len: int):
        self.U = U  # [B, max_new] float64 on device
        self.temps = temps  # [B] float32
        self.topk = topk  # [B] int (0 = off)
        self.prompt_len = prompt_len

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        step = input_ids.shape[1] - self.prompt_len
        s = scores.float() / self.temps[:, None]
        if bool((self.topk > 0).any()):
            kmax = int(self.topk.max())
            vals = torch.topk(s, kmax, dim=-1).values  # [B, kmax] sorted desc
            kk = torch.where(self.topk > 0, self.topk, torch.full_like(self.topk, kmax)) - 1
            thr = vals.gather(1, kk[:, None])
            thr = torch.where((self.topk > 0)[:, None], thr, torch.full_like(thr, -float("inf")))
            s = torch.where(s < thr, torch.full_like(s, -float("inf")), s)
        p = torch.softmax(s, dim=-1).double()
        cdf = torch.cumsum(p, dim=-1)
        u = self.U[:, step:step + 1] * cdf[:, -1:]
        tok = torch.searchsorted(cdf, u).clamp(max=scores.shape[-1] - 1)
        # guard: never land on a zero-probability token (ties at cdf plateaus)
        bad = p.gather(1, tok) <= 0
        if bool(bad.any()):
            tok = torch.where(bad, torch.argmax(p, dim=-1, keepdim=True), tok)
        out = torch.full_like(scores, -float("inf"))
        out.scatter_(1, tok, 0.0)
        return out


class CodeStop(StoppingCriteria):
    """Stop a row once its generated text contains a closed ```python block."""

    def __init__(self, tok, prompt_len: int, tick_ids: set[int], active: torch.Tensor):
        self.tok = tok
        self.prompt_len = prompt_len
        self.tick_ids = torch.tensor(sorted(tick_ids), device="cuda")
        self.active = active  # [B] bool: rows subject to code-stop
        self.done = None

    def __call__(self, input_ids: torch.LongTensor, scores, **kwargs) -> torch.BoolTensor:
        B = input_ids.shape[0]
        if self.done is None:
            self.done = torch.zeros(B, dtype=torch.bool, device=input_ids.device)
        last = input_ids[:, -1]
        hit = torch.isin(last, self.tick_ids) & self.active & ~self.done
        if bool(hit.any()):
            for i in torch.nonzero(hit).flatten().tolist():
                txt = self.tok.decode(input_ids[i, self.prompt_len:], skip_special_tokens=True)
                if PY_CLOSED_RE.search(txt):
                    self.done[i] = True
        return self.done.clone()


@dataclass
class Intervention:
    """One per-row intervention spec. kind in {none, add, project, leace}. Params keyed by hs layer."""
    kind: str = "none"
    vecs: dict = field(default_factory=dict)  # add: l -> [d] tensor already scaled (coef*v)
    U: dict = field(default_factory=dict)  # project: l -> [d, r]
    mu: dict = field(default_factory=dict)  # project: l -> [d]
    eraser: dict = field(default_factory=dict)  # leace: l -> (P [d,d], mean [d]) affine eraser params
    a: float = 1.0

    def key(self) -> int:
        return id(self)


class Steerer:
    """Per-row interventions + residual capture over generation, via forward hooks."""

    def __init__(self, model, window: int = 32, capture_layers: list[int] | None = None):
        self.model = model
        self.layers = model.model.layers
        self.window = window
        self.capture_layers = capture_layers or []
        self.handles = []
        self.step = -1
        self.groups: list[tuple[torch.Tensor, Intervention]] = []
        self.cap8: dict[int, torch.Tensor] = {}
        self.cap32: dict[int, torch.Tensor] = {}
        self.cap_n8 = 0
        self.cap_n32 = 0
        self.n_mod = 0

    def set_batch(self, interventions: list[Intervention]) -> None:
        groups: dict[int, tuple[list[int], Intervention]] = {}
        for i, iv in enumerate(interventions):
            if iv.kind == "none":
                continue
            groups.setdefault(iv.key(), ([], iv))[0].append(i)
        self.groups = [(torch.tensor(ix, device="cuda"), iv) for ix, iv in groups.values()]
        self.step = -1
        self.cap8, self.cap32 = {}, {}
        self.cap_n8 = self.cap_n32 = 0
        self.n_mod = 0

    def _layer_set(self) -> set[int]:
        ls = set(self.capture_layers)
        for _, iv in self.groups:
            ls |= set(iv.vecs) | set(iv.U) | set(iv.eraser)
        return ls

    def __enter__(self):
        self.handles.append(self.layers[0].register_forward_pre_hook(self._pre, with_kwargs=True))
        for l in sorted(self._layer_set()):
            self.handles.append(self.layers[l - 1].register_forward_hook(self._make_hook(l)))
        return self

    def __exit__(self, *exc):
        for h in self.handles:
            h.remove()
        self.handles = []
        for layer in self.layers:
            assert not layer._forward_hooks and not layer._forward_pre_hooks, "hook leak"

    def _pre(self, module, args, kwargs):
        hs = args[0] if args else kwargs.get("hidden_states")
        S = hs.shape[1] if hs is not None else 1
        self.step = 0 if S > 1 else self.step + 1
        return None

    def _modify(self, h: torch.Tensor, l: int) -> torch.Tensor:
        """h: [B, d] residual at the active position (float32)."""
        for ix, iv in self.groups:
            if iv.kind == "add" and l in iv.vecs:
                h[ix] = h[ix] + iv.vecs[l][None, :]
            elif iv.kind == "project" and l in iv.U:
                U, mu = iv.U[l], iv.mu[l]
                x = h[ix] - mu[None, :]
                h[ix] = h[ix] - iv.a * (x @ U) @ U.T
            elif iv.kind == "leace" and l in iv.eraser:
                P, m = iv.eraser[l]
                x = h[ix]
                erased = x - (x - m[None, :]) @ P.T
                h[ix] = x - iv.a * (x - erased)
            else:
                continue
            self.n_mod += 1
        return h

    def _make_hook(self, l: int):
        def hook(module, inp, out):
            hs = out[0] if isinstance(out, tuple) else out
            S = hs.shape[1]
            pos = -1 if S > 1 else 0
            modify = self.groups and (S > 1 or 1 <= self.step <= self.window)
            if modify:
                h = hs[:, pos, :].float()
                h = self._modify(h, l)
                hs = hs.clone()
                hs[:, pos, :] = h.to(hs.dtype)
            if l in self.capture_layers and S == 1 and 1 <= self.step <= 32:
                v = hs[:, 0, :].float()
                if self.step <= 8:
                    self.cap8[l] = self.cap8.get(l, 0) + v
                self.cap32[l] = self.cap32.get(l, 0) + v
            if modify:
                return (hs,) + tuple(out[1:]) if isinstance(out, tuple) else hs
            return None

        return hook

    def captured(self) -> dict:
        """Mean over gen1..8 and gen1..32 per capture layer: {l: (m8 [B,d] np.float16, m32)}."""
        steps = max(self.step, 0)
        n8, n32 = min(steps, 8), min(steps, 32)
        out = {}
        for l in self.capture_layers:
            if l in self.cap8:
                out[l] = ((self.cap8[l] / max(n8, 1)).cpu().numpy().astype(np.float16),
                          (self.cap32[l] / max(n32, 1)).cpu().numpy().astype(np.float16))
        return out


def backtick_token_ids(tok) -> set[int]:
    ids = set()
    for t, i in tok.get_vocab().items():
        s = tok.convert_tokens_to_string([t])
        if "`" in s:
            ids.add(i)
    return ids


@torch.inference_mode()
def generate_batch(tok, model, prompts: list[str], seeds: list[int], temps: list[float], topks: list[int],
                   interventions: list[Intervention], code_stop: list[bool], steerer: Steerer,
                   tick_ids: set[int], max_new: int = 768) -> dict:
    enc = tok([render(tok, p) for p in prompts], return_tensors="pt", padding=True).to("cuda")
    plen = enc["input_ids"].shape[1]
    U = torch.stack([uniforms_for(s, max_new) for s in seeds]).to("cuda")
    sampler = SeededSampler(U, torch.tensor(temps, device="cuda", dtype=torch.float32),
                            torch.tensor(topks, device="cuda", dtype=torch.long), plen)
    stopper = CodeStop(tok, plen, tick_ids, torch.tensor(code_stop, device="cuda"))
    gc_ = GenerationConfig(do_sample=False, max_new_tokens=max_new, pad_token_id=tok.pad_token_id,
                           eos_token_id=[151645, 151643], repetition_penalty=1.0, temperature=None, top_p=None,
                           top_k=None)
    steerer.set_batch(interventions)
    t0 = time.time()
    with steerer:
        out = model.generate(**enc, generation_config=gc_, logits_processor=[sampler], stopping_criteria=[stopper])
    dt = time.time() - t0
    gen = out[:, plen:]
    texts, ntoks, hit_max, ids32 = [], [], [], []
    for i in range(gen.shape[0]):
        ids = gen[i].tolist()
        n = len(ids)
        while n > 0 and ids[n - 1] in (tok.pad_token_id,):
            n -= 1
        eos = any(t in (151645, 151643) for t in ids[:n])
        texts.append(tok.decode(ids[:n], skip_special_tokens=True))
        ids32.append(ids[:min(n, 32)])
        ntoks.append(n)
        hit_max.append(n >= max_new and not eos and not bool(stopper.done is not None and stopper.done[i]))
    cap = steerer.captured()
    res = {"texts": texts, "ids32": ids32, "ntoks": ntoks, "hit_max": hit_max, "seconds": dt, "captured": cap,
           "n_mod_calls": steerer.n_mod, "steps": steerer.step}
    del out, enc, U
    return res


def free():
    gc.collect()
    torch.cuda.empty_cache()
