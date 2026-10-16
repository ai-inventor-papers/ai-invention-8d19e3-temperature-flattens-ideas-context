#!/usr/bin/env python3
"""Step D (descriptive only): Gemma Scope 16k residual SAE latents for priming and neighbour activation under bans.

Gemma Scope layer L reads HF hidden_states[L+1] (output of block L). L = the gemma probe-band layer nearest the
middle, converted to the block index. 'canonical' = the 16k-width SAE with average L0 closest to 100 (JumpReLU,
params.npz from google/gemma-scope-2b-pt-res; loaded directly, no sae-lens). The SAEs were trained on gemma-2-2b PT;
we check reconstruction FVU on our -it prompt states and mark D unreliable if FVU > 0.5.
Runs on CPU (a handful of short prompts). Output: results/sae_latents.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEMMA, RESULTS, write_json  # noqa: E402
from protocol import user_message  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
SUFFIX_N = 5


def load_sae(layer: int):
    from huggingface_hub import hf_hub_download, list_repo_files
    fs = list_repo_files("google/gemma-scope-2b-pt-res")
    l0s = [int(m.group(1)) for f in fs if (m := re.match(rf"layer_{layer}/width_16k/average_l0_(\d+)/params.npz", f))]
    l0 = min(l0s, key=lambda v: abs(v - 100))
    p = hf_hub_download("google/gemma-scope-2b-pt-res", f"layer_{layer}/width_16k/average_l0_{l0}/params.npz")
    z = np.load(p)
    return {k: torch.tensor(z[k]).float() for k in z.files}, l0


def encode(P, x):
    pre = x @ P["W_enc"] + P["b_enc"]
    return torch.relu(pre) * (pre > P["threshold"]).float()


def decode(P, z):
    return z @ P["W_dec"] + P["b_dec"]


def main() -> None:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    t0 = time.time()
    fz = json.loads((RESULTS / "frozen_gemma_bans.json").read_text())
    band = fz["band"]
    mid = band[len(band) // 2]
    L = mid - 1  # Gemma Scope block index; HF hidden_states[L+1] == hidden_states[mid]
    P, l0 = load_sae(L)
    logger.info(f"SAE layer {L} (hidden_states[{mid}]) width 16k L0 {l0}")
    tok = AutoTokenizer.from_pretrained(GEMMA)
    model = AutoModelForCausalLM.from_pretrained(GEMMA, torch_dtype=torch.float32, attn_implementation="eager")
    model.eval()
    gb = json.loads((RESULTS / "gemma_bans.json").read_text()) if (RESULTS / "gemma_bans.json").exists() else {}
    prompts, meta = {}, {}
    for t in ("T1", "T2"):
        prompts[(t, "placebo")] = user_message(t, "placebo")
        prompts[(t, "baseline")] = user_message(t, "baseline")
        for x in fz["ranks"][t]:
            prompts[(t, f"forced_{x}")] = user_message(t, f"forced_{x}")
        for b, cl in {**fz["screen_bans"][t], **fz["confirmation_bans"][t]}.items():
            prompts[(t, b)] = user_message(t, "ban", cl)
            meta[(t, b)] = cl
    X, Xpos = {}, {}
    with torch.no_grad():
        for k, m in prompts.items():
            s = tok.apply_chat_template([{"role": "user", "content": m}], tokenize=False, add_generation_prompt=True)
            ids = tok(s, add_special_tokens=False, return_tensors="pt")["input_ids"]
            hs = model.model(input_ids=ids, output_hidden_states=True).hidden_states[mid][0, -SUFFIX_N:].float()
            Xpos[k] = hs
            X[k] = hs.mean(0)
    allpos = torch.cat(list(Xpos.values()))
    rec = decode(P, encode(P, allpos))
    fvu = float(((allpos - rec) ** 2).sum() / ((allpos - allpos.mean(0)) ** 2).sum())
    Z = {k: encode(P, v[None])[0] for k, v in X.items()}
    freq = (torch.stack([encode(P, v) for v in Xpos.values()]).reshape(-1, P["W_enc"].shape[1]) > 0).float().mean(0)
    rng = np.random.default_rng(0)
    out = dict(layer_gemma_scope=L, hidden_state_index=mid, l0=l0, fvu=fvu, reliable=fvu <= 0.5,
               note="descriptive only; no verdict counted; SAEs trained on gemma-2-2b PT", tasks={})
    bins = np.digitize(freq.numpy(), [0, 1e-9, 0.05, 0.2, 0.5, 1.01])
    for t in ("T1", "T2"):
        ideas = fz["ranks"][t]
        zf = {x: Z[(t, f"forced_{x}")] for x in ideas}
        S = {}
        for x in ideas:
            spec = zf[x] - torch.stack([zf[y] for y in ideas if y != x]).mean(0)
            S[x] = torch.topk(spec, 10).indices.tolist()
        bans = []
        conf = {(r["task"], r["ban"]): r for r in gb.get("confirmation", {}).get("per_ban", [])}
        for b, cl in {**fz["screen_bans"][t], **fz["confirmation_bans"][t]}.items():
            if len(cl) != 1 or cl[0] not in S:
                continue
            x = cl[0]
            dz = Z[(t, b)] - Z[(t, "placebo")]
            prim = float(dz[S[x]].mean())
            sub = conf.get((t, b), {}).get("top_substitute_pred", {}).get("GEOM")
            neigh = float(dz[S[sub]].mean()) if sub in S else None
            # null (a): random 10-latent sets matched on activation-frequency bin
            nulls = []
            for _ in range(1000):
                idx = [int(rng.choice(np.where(bins == bins[i])[0])) for i in S[x]]
                nulls.append(float(dz[idx].mean()))
            # null (b): the same S_X under bans of OTHER ideas
            other = [float((Z[(t, b2)] - Z[(t, "placebo")])[S[x]].mean())
                     for b2, c2 in {**fz["screen_bans"][t], **fz["confirmation_bans"][t]}.items() if x not in c2]
            top = torch.topk(dz.abs(), 10).indices.tolist()
            bans.append(dict(ban=b, banned=x, priming=prim, priming_pct_random=float(np.mean(np.array(nulls) < prim)),
                             priming_pct_other_bans=float(np.mean(np.array(other) < prim)) if other else None,
                             neighbour_sub=sub, neighbour=neigh, top_abs_dz_latents=top,
                             top_abs_dz_values=[float(dz[i]) for i in top]))
        out["tasks"][t] = dict(S_X=S, bans=bans)
    # Neuronpedia labels (free API; skipped on failure)
    import requests
    labels = {}
    want = sorted({i for t in out["tasks"] for b in out["tasks"][t]["bans"] for i in b["top_abs_dz_latents"][:5]})
    for i in want[:60]:
        try:
            r = requests.get(f"https://www.neuronpedia.org/api/feature/gemma-2-2b/{L}-gemmascope-res-16k/{i}", timeout=10)
            if r.ok:
                js = r.json()
                ex = js.get("explanations") or []
                labels[i] = ex[0].get("description") if ex else None
        except (requests.RequestException, ValueError):
            labels[i] = None
    out["neuronpedia_labels"] = labels
    out["runtime_min"] = (time.time() - t0) / 60
    write_json(RESULTS / "sae_latents.json", out)
    logger.info(f"SAE D done: FVU {fvu:.3f}; " + json.dumps({t: [(b['ban'], round(b['priming'], 3),
                                                                     b['priming_pct_random']) for b in d['bans']]
                                                            for t, d in out["tasks"].items()}))


if __name__ == "__main__":
    logger.catch(reraise=True)(main)()
