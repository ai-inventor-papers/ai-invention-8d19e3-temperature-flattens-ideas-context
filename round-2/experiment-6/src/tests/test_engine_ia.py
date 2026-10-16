"""T0-T2: model config, prompt rendering, sampler determinism (batch independence, CRN), hooks."""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import torch
from src.engine import (load_model, render, generate_batch, Steerer, Intervention, backtick_token_ids)
from protocol.prompts import build_user_prompt, MODEL_ID, T2_TASK

tok, model = load_model(MODEL_ID)
cfg = model.config
print("layers", cfg.num_hidden_layers, "d_model", cfg.hidden_size, "vocab", cfg.vocab_size)
p1, p3 = build_user_prompt("T1"), build_user_prompt("T3")
print(render(tok, p1))
ticks = backtick_token_ids(tok)
print("n backtick tokens", len(ticks))
# left padding check
enc = tok([render(tok, p1), render(tok, p3)], return_tensors="pt", padding=True)
print("last tokens", tok.convert_ids_to_tokens(enc["input_ids"][:, -1].tolist()))
st = Steerer(model, capture_layers=[10])
def gen(prompts, seeds, T=0.7, k=0, ivs=None, mx=768):
    return generate_batch(tok, model, prompts, seeds, [T]*len(prompts), [k]*len(prompts),
                          ivs or [Intervention()]*len(prompts), [True]*len(prompts), st, ticks, max_new=mx)
# (a) batch independence: idx 7 alone vs in a batch of 32 (mixed prompts)
r1 = gen([p1], [7])
prompts = [p1 if i % 2 == 0 else p3 for i in range(32)]; prompts[7] = p1
seeds = list(range(32))
t0 = time.time(); rb = gen(prompts, seeds); print("batch32 sec", time.time()-t0, "ntoks", rb["ntoks"][:8])
print("(a) identical idx7 batch1 vs batch32:", r1["texts"][0] == rb["texts"][7])
# (b) T->0 equals greedy
gr = model.generate(**tok([render(tok, p1)], return_tensors="pt").to("cuda"), do_sample=False, max_new_tokens=60, repetition_penalty=1.0)
gtxt = tok.decode(gr[0, tok([render(tok, p1)], return_tensors="pt")["input_ids"].shape[1]:], skip_special_tokens=True)
r0 = gen([p1], [3], T=0.01, mx=60)
print("(b) T=0.01 == greedy:", r0["texts"][0] == gtxt)
# (c) different idx differ
print("(c) idx0 != idx2:", rb["texts"][0] != rb["texts"][2])
# (d) topk=10 sampler: tokens from top10 only (check with logits on 1 step)
rk = gen([p1]*4, [11, 12, 13, 14], T=2.0, k=10, mx=40)
ids = tok([render(tok, p1)], return_tensors="pt")["input_ids"].cuda()
with torch.no_grad():
    lg = model(ids).logits[0, -1]
top10 = set(torch.topk(lg, 10).indices.tolist())
first = [tok(rk["texts"][i], add_special_tokens=False)["input_ids"][0] for i in range(4)]
print("(d) first tokens in top10:", all(f in top10 for f in first))
# T2 hooks: (a) zero-vector add == no hook
zero = Intervention(kind="add", vecs={10: torch.zeros(cfg.hidden_size, device="cuda")})
rz = gen([p1]*4, [0, 1, 2, 3], ivs=[zero]*4, mx=120)
rn = gen([p1]*4, [0, 1, 2, 3], mx=120)
print("(T2a) zero hook identical:", rz["texts"] == rn["texts"])
print("(T2b) n_mod calls (expect 33 with 1 group, 1 layer):", rz["n_mod_calls"])
# (c) hidden_states[L+1] == layers[L] output
cap = {}
h = model.model.layers[9].register_forward_hook(lambda m, i, o: cap.__setitem__("o", (o[0] if isinstance(o, tuple) else o).detach()))
with torch.no_grad():
    out = model(ids, output_hidden_states=True)
h.remove()
print("(T2c) hs[10]==layers[9] out:", torch.allclose(out.hidden_states[10].float(), cap["o"].float(), atol=1e-3))
# (d) projection a=1 leaves zero component in span(U)
U = torch.linalg.qr(torch.randn(cfg.hidden_size, 3, device="cuda"))[0]
mu = torch.zeros(cfg.hidden_size, device="cuda")
pj = Intervention(kind="project", U={10: U}, mu={10: mu}, a=1.0)
st2 = Steerer(model, capture_layers=[])
st2.set_batch([pj]); st2.step = 1
hh = torch.randn(1, cfg.hidden_size, device="cuda") * 50
res = st2._modify(hh.clone(), 10)
print("(T2d) residual component in span(U):", float((res @ U).norm()))
print("(T2e) hooks empty:", all(not l._forward_hooks and not l._forward_pre_hooks for l in model.model.layers))
print("sample text idx0:\n", rb["texts"][0][:1500])
