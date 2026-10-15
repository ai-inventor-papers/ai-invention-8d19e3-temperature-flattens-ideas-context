"""Build all intervention vectors from the baseline only (+ A4 direction from non-path tasks)."""

from __future__ import annotations

import itertools
import json

import numpy as np
import torch
from loguru import logger
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from protocol.prompts import MODEL_ID, NOVEL_HINT_A4
from src.acts_io import load_acts
from src.common import ACTS, RES, SCORED, VEC, read_jsonl
from src.probes import erasure_check

D = 2048

# ---- A4 prompt variants: 8 phrasing templates x 5 wordings per task, deterministic, no LLM ----
A4_TEMPLATES = [
    "Implement {w} in Python.", "Write a Python program for {w}.", "Can you code {w} in Python?",
    "Please write Python code that performs {w}.", "Create a Python function for {w}.",
    "I need {w} implemented in Python.", "Show me how to implement {w} in Python.",
    "Develop a Python solution for {w}.",
]
A4_TASKS = {
    "sorting": ["a sorting algorithm", "sorting a list of numbers", "an algorithm that sorts an array",
                "ordering a list of integers", "a function that sorts values in ascending order"],
    "substring": ["substring search", "finding a pattern inside a text", "a string matching algorithm",
                  "locating a substring in a string", "searching for a word inside a document"],
    "primality": ["primality testing", "checking whether a number is prime", "a prime number test",
                  "an algorithm that decides if an integer is prime", "detecting prime numbers"],
    "compression": ["string compression", "run-length style compression of a string", "reversing and compressing strings",
                    "an algorithm that compresses text", "shortening a string by encoding repeats"],
    "matmul": ["matrix multiplication", "multiplying two matrices", "a matrix product algorithm",
               "computing the product of two 2D arrays", "an algorithm that multiplies square matrices"],
}
A4_HELDOUT = {
    "T1_path": ["a path search algorithm", "finding a path between two nodes in a graph", "graph path finding",
                "an algorithm that finds a route in a graph", "searching for a path from start to goal"],
    "T3_wsp": ["a shortest path algorithm for a weighted graph", "finding the cheapest route in a weighted graph",
               "weighted shortest path search", "an algorithm for minimum-cost paths",
               "computing shortest distances with edge weights"],
}


def a4_prompts(words: list[str]) -> tuple[list[str], list[str]]:
    plain, novel = [], []
    for tpl, w in itertools.product(A4_TEMPLATES, words):
        p = tpl.format(w=w)
        plain.append(p)
        novel.append(p + " " + NOVEL_HINT_A4)
    return plain, novel


@torch.inference_mode()
def prompt_final_states(tok, model, prompts: list[str], layers: list[int]) -> dict:
    from src.engine import render
    out = {l: [] for l in layers}
    for b in range(0, len(prompts), 64):
        enc = tok([render(tok, p) for p in prompts[b:b + 64]], return_tensors="pt", padding=True).to("cuda")
        hs = model(**enc, output_hidden_states=True).hidden_states
        for l in layers:
            out[l].append(hs[l][:, -1].float().cpu())
    return {l: torch.cat(v).numpy() for l, v in out.items()}


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def build_vectors(ctx: dict, save_ctx) -> None:
    from concept_erasure import LeaceEraser
    band = ctx["band"]
    classes = ctx["probe_classes"]
    menus = {t: ctx["menus"][t]["classes"] for t in ("T1", "T3")}
    acts = {t: load_acts(ACTS, t) for t in ("T1", "T3")}
    labels = {}
    for t in ("T1", "T3"):
        lab = {r["idx"]: r["label"] for r in read_jsonl(SCORED / t / "baseline.jsonl")}
        idx = np.load(ACTS / f"baseline_{t}_idx.npy")
        labels[t] = np.array([lab[int(i)] for i in idx])
    V = {"Hprobe": {"T1": {}, "T3": {}}, "Hdim": {"T1": {}, "T3": {}}, "A3_U": {"T1": {}, "T3": {}},
         "mu": {"T1": {}, "T3": {}}, "leace": {"T1": {}, "T3": {}}, "A4": {}, "rand_add": {}, "rand_proj": {}}
    checks = {"median_norm": {}, "H_target_classes": {}, "leace_offline": {}, "cos": {}, "A3_rank": {}}
    # median residual norm over baseline gen1..8 positions (pooled tasks)
    med = {}
    for l in band:
        norms = np.concatenate([np.linalg.norm(acts[t][:, 1:9, l, :].astype(np.float32), axis=-1).ravel()
                                for t in ("T1", "T3")])
        med[str(l)] = float(np.median(norms))
    checks["median_norm"] = med
    rng = np.random.default_rng(777)
    probes_np = {}
    for l in band:
        X8 = {t: acts[t][:, 1:9, l, :].astype(np.float32).mean(1) for t in ("T1", "T3")}
        X32 = {t: acts[t][:, 9, l, :].astype(np.float32) for t in ("T1", "T3")}
        # final probe on all data at band layer (pooled, union menu + rare)
        Xp = np.concatenate([X32["T1"], X32["T3"]])  # F4: probe on mean(gen1..32)
        yp = np.array([c if c in classes else "rare" for c in np.concatenate([labels["T1"], labels["T3"]])])
        sc = StandardScaler().fit(Xp)
        C = float(ctx["probe_C"][str(l)])
        clf = LogisticRegression(C=C, max_iter=500).fit(sc.transform(Xp), yp)
        W = clf.coef_ / sc.scale_[None, :]  # fold scaler back: logits = W x + b'
        b = clf.intercept_ - (clf.coef_ * (sc.mean_ / sc.scale_)[None, :]).sum(1)
        cls_list = list(clf.classes_)
        if W.shape[0] == 1:  # binary probe -> two rows
            W = np.concatenate([-W / 2, W / 2])
            b = np.concatenate([-b / 2, b / 2])
        probes_np[l] = {"W": W.astype(np.float32), "b": b.astype(np.float32), "classes": cls_list}
        for t in ("T1", "T3"):
            menu = menus[t]
            target = menu if len(menu) >= 2 else [c for c in cls_list if c != "rare"]
            checks["H_target_classes"][t] = target
            mode = max(set(labels[t]), key=list(labels[t]).count)
            if mode not in cls_list:
                mode = target[0]
            Wt = np.stack([W[cls_list.index(c)] for c in target if c in cls_list])
            d = Wt.mean(0) - W[cls_list.index(mode)]
            V["Hprobe"][t][l] = unit(d)
            is_mode = labels[t] == mode
            if is_mode.all() or (~is_mode).all():
                d2 = d
            else:
                d2 = -(X32[t][is_mode].mean(0) - X32[t][~is_mode].mean(0))
            V["Hdim"][t][l] = unit(d2)
            checks["cos"][f"Hprobe_vs_Hdim_{t}_L{l}"] = float(unit(d) @ unit(d2))
            # A3: centroid subspace of menu classes (mean gen1..32)
            mu = X32[t].mean(0)
            V["mu"][t][l] = mu
            if len(menu) >= 2:
                Cm = np.stack([X32[t][labels[t] == c].mean(0) - mu for c in menu], 1)  # [d, k]
                U, S, _ = np.linalg.svd(Cm, full_matrices=False)
                V["A3_U"][t][l] = U[:, :len(menu)]
                checks["A3_rank"][f"{t}_L{l}"] = {"singular_values": S.tolist(), "k": len(menu),
                                                   "note": "centred centroids have rank <= k-1"}
                # LEACE on (X32, one-hot menu + other)
                zc = menu + ["other_class"]
                z = np.array([zc.index(c) if c in menu else len(menu) for c in labels[t]])
                Z = torch.nn.functional.one_hot(torch.tensor(z), num_classes=len(zc)).float()
                er = LeaceEraser.fit(torch.tensor(X32[t]), Z)
                P = (er.proj_left @ er.proj_right).float()
                bias = er.bias.float()
                V["leace"][t][l] = (P, bias)
                Xe = er(torch.tensor(X32[t])).numpy()
                ymenu = np.array([c if c in menu else "other_class" for c in labels[t]])
                maj = float(max(np.mean(ymenu == c) for c in set(ymenu)))
                checks["leace_offline"][f"{t}_L{l}"] = {
                    "bal_acc_before": erasure_check(X32[t], ymenu), "bal_acc_after": erasure_check(Xe, ymenu),
                    "chance_bal_acc": 1.0 / len(set(ymenu)), "majority_share": maj}
                # projection offline check
                Uk = U[:, :max(1, len(menu) - 1)]
                Xp_ = X32[t] - ((X32[t] - mu) @ Uk) @ Uk.T
                checks["leace_offline"][f"{t}_L{l}"]["bal_acc_after_proj_rk-1"] = erasure_check(Xp_, ymenu)
        # random controls (seed 777)
        V["rand_add"][l] = [unit(rng.standard_normal(D)) for _ in range(3)]
        kmax = max(2, max(len(m) for m in menus.values()))
        V["rand_proj"][l] = [np.linalg.qr(rng.standard_normal((D, kmax)))[0] for _ in range(3)]
        logger.info(f"layer {l}: median norm {med[str(l)]:.1f}; leace checks "
                    f"{ {k: v for k, v in checks['leace_offline'].items() if k.endswith(f'L{l}')} }")
    # ---- A4 direction ----
    from src.engine import load_model
    tok, model = load_model(MODEL_ID)
    task_states = {}
    for name, words in {**A4_TASKS, **A4_HELDOUT}.items():
        plain, novel = a4_prompts(words)
        sp = prompt_final_states(tok, model, plain, band)
        sn = prompt_final_states(tok, model, novel, band)
        task_states[name] = (sp, sn)
    a4 = {"loto_cos": {}, "heldout_auroc": {}, "cos_with_H": {}, "cos_with_A3_subspace": {}}
    for l in band:
        diffs = {n: task_states[n][1][l].mean(0) - task_states[n][0][l].mean(0) for n in A4_TASKS}
        v = unit(np.mean([diffs[n] for n in A4_TASKS], 0))
        V["A4"][l] = v
        for n in A4_TASKS:
            v_loo = unit(np.mean([diffs[m] for m in A4_TASKS if m != n], 0))
            a4["loto_cos"][f"L{l}_{n}"] = float(v_loo @ unit(diffs[n]))
        for n in A4_HELDOUT:
            sp, sn = task_states[n]
            proj = np.concatenate([sp[l] @ v, sn[l] @ v])
            yy = np.concatenate([np.zeros(len(sp[l])), np.ones(len(sn[l]))])
            a4["heldout_auroc"][f"L{l}_{n}"] = float(roc_auc_score(yy, proj))
        for t in ("T1", "T3"):
            a4["cos_with_H"][f"L{l}_{t}_Hprobe"] = float(v @ V["Hprobe"][t][l])
            a4["cos_with_H"][f"L{l}_{t}_Hdim"] = float(v @ V["Hdim"][t][l])
            if l in V["A3_U"][t]:
                U = V["A3_U"][t][l]
                a4["cos_with_A3_subspace"][f"L{l}_{t}"] = float(np.linalg.norm(U.T @ v))
    checks["A4"] = a4
    logger.info(f"A4 checks: heldout AUROC {a4['heldout_auroc']}")
    # save tensors
    Tt = {}
    for k in ("Hprobe", "Hdim", "A3_U", "mu"):
        Tt[k] = {t: {l: torch.tensor(np.asarray(v), dtype=torch.float32) for l, v in V[k][t].items()} for t in V[k]}
    Tt["leace"] = {t: {l: (P.float(), b.float()) for l, (P, b) in V["leace"][t].items()} for t in V["leace"]}
    Tt["A4"] = {l: torch.tensor(v, dtype=torch.float32) for l, v in V["A4"].items()}
    Tt["rand_add"] = {l: [torch.tensor(x, dtype=torch.float32) for x in v] for l, v in V["rand_add"].items()}
    Tt["rand_proj"] = {l: [torch.tensor(x, dtype=torch.float32) for x in v] for l, v in V["rand_proj"].items()}
    Tt["probes"] = {l: {"W": torch.tensor(p["W"]), "b": torch.tensor(p["b"]), "classes": p["classes"]}
                    for l, p in probes_np.items()}
    # LEACE erasers (6 x 2048 x 2048 fp32) are stored separately so each file stays < 100 MB
    for t, er in Tt.pop("leace").items():
        torch.save(er, VEC / f"leace_{t}.pt")
    torch.save(Tt, VEC / "vectors.pt")
    ctx["median_norm"] = med
    save_ctx(ctx)
    (RES / "vector_checks.json").write_text(json.dumps(checks, indent=2))
    logger.info("vectors saved")
