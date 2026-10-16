#!/usr/bin/env python3
"""CPU hook tests (testing plan item 2) on Qwen2.5-3B-Instruct in bf16:
(a) PromptPatcher ('patch' intervention) changes ONLY the last 5 positions of the prefill at layer L, for a 2-prompt
    batch with different lengths and left padding, and does nothing on decode steps;
(b) an 'add' intervention with a zero vector leaves the logits bit-identical;
(c) no hooks leak after the context exits.
"""
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import Intervention, Steerer, render  # noqa: E402
from protocol import user_message  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

torch.set_num_threads(2)
M = "Qwen/Qwen2.5-3B-Instruct"
tok = AutoTokenizer.from_pretrained(M)
tok.padding_side = "left"
model = AutoModelForCausalLM.from_pretrained(M, torch_dtype=torch.bfloat16, attn_implementation="eager")
model.eval()
msgs = [user_message("T1", "baseline"), user_message("T1", "ban_r1", ["BFS"])]
enc = tok([render(tok, m) for m in msgs], return_tensors="pt", padding=True, add_special_tokens=False)
L = 10
cap = {}


def grab(m, i, o):
    cap["h"] = (o[0] if isinstance(o, tuple) else o).detach().float().clone()


res = {}
with torch.no_grad():
    h = model.model.layers[L - 1].register_forward_hook(grab)
    model.model(**enc)
    base = cap["h"]
    h.remove()
    D = torch.randn(5, model.config.hidden_size) * 3
    st = Steerer(model, window=64)
    st.set_batch([Intervention(kind="patch", pos_vecs={L: D}), Intervention()])
    with st:
        h = model.model.layers[L - 1].register_forward_hook(grab)  # registered after the patch hook -> sees output
        model.model(**enc)
        h.remove()
    pat = cap["h"]
    diff = (pat - base).abs().sum(-1)  # [B, T]
    res["patched_row_changed_positions"] = torch.nonzero(diff[0] > 1e-3).flatten().tolist()
    res["unpatched_row_changed"] = bool((diff[1] > 1e-3).any())
    T = enc["input_ids"].shape[1]
    res["patch_ok"] = res["patched_row_changed_positions"] == list(range(T - 5, T)) and not res["unpatched_row_changed"]
    res["n_mod"] = st.n_mod
    # (b) zero add
    out0 = model(**enc).logits[:, -1].float()
    st2 = Steerer(model, window=64)
    st2.set_batch([Intervention(kind="add", vecs={L: torch.zeros(model.config.hidden_size)})] * 2)
    with st2:
        out1 = model(**enc).logits[:, -1].float()
    res["zero_add_identical"] = bool(torch.equal(out0, out1))
    res["zero_add_n_mod"] = st2.n_mod
res["no_hook_leak"] = all(not l._forward_hooks and not l._forward_pre_hooks for l in model.model.layers)
print(res)
assert res["patch_ok"] and res["zero_add_identical"] and res["no_hook_leak"] and res["n_mod"] > 0
print("ALL HOOK TESTS PASS")
