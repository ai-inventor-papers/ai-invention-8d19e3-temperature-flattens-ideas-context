#!/usr/bin/env python3
"""Step C: second model family, gemma-2-2b-it (HF engine, eager attention for softcapping), bare prompts T1/T2.

Stages: smoke | screen_a | screen_b | audit | geometry | confirm | temp | transplant | analyze
  screen_a  : baseline (seeds 0..NB-1) + placebo triplicate (seeds 1000+, 2000+, 3000+)
  screen_b  : ranks r1..r8 from the gemma baseline -> forced_X (top-8) + bans r1..r4, top3, top5
  geometry  : prompt-suffix states, generated-window centroids (probe band), s_j, predictor fits -> FREEZE
  confirm   : bans r5..r8 + 3 random pairs per task at seeds 1000+ (refuses to run without the frozen file)
  temp      : C5 temperature law (T 0.3/1.0/1.3 + T1.0 top-k 10; T0.7 = baseline seeds)
  transplant: C4 Delta_h transplant / subtraction at L* vs matched-norm random displacements
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import activations as ba_acts  # noqa: E402,F401  (import before logger setup: it reconfigures loguru)
from common import (ACTS, BA, GEMMA, LOGS, RESULTS, dist, freeze, jsd2, read_jsonl, require_frozen,  # noqa: E402
                    sha256_file, write_json)
from protocol import DISPLAY, ban_sentence, bannable, taxonomy, user_message  # noqa: E402
from runner import Runner, gens_path, load_scored  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(LOGS / "gemma.log", rotation="30 MB", level="DEBUG")

TASKS = ("T1", "T2")
SUFFIX_N = 5  # '<end_of_turn>', '\n', '<start_of_turn>', 'model', '\n'
N_LAYERS = 26
FROZEN = RESULTS / "frozen_gemma_bans.json"
DELTA_PATH = RESULTS / "gemma_delta_h.pt"
CENT_PATH = RESULTS / "gemma_centroids.pt"
CODE_STOP = False  # tests/check_codestop.py: agreement < 0.97 -> CodeStop disabled for every new generation
CFG = dict(batch=64, max_new=1024, nb=200, npl=80, nf=30, nban=80, nconf=80, ntemp=60, ntr=50)
SCREEN_BANS = ["ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3", "ban_top5"]
DESCR = {  # fixed one-sentence descriptions for the external text-embedding baseline (frozen before fitting)
    "BFS": "explores a graph level by level with a FIFO queue, giving shortest paths in unweighted graphs",
    "DFS": "explores a graph by going as deep as possible along each branch using recursion or a stack",
    "IDDFS": "runs depth-limited depth-first searches with increasing depth limits",
    "Dijkstra": "finds shortest paths in a weighted graph with non-negative weights using a priority queue",
    "A_star": "best-first search ordered by path cost plus a heuristic estimate of the remaining distance",
    "Greedy_best_first": "expands the node that a heuristic estimates is closest to the goal",
    "Bidirectional": "searches simultaneously forward from the start and backward from the goal until they meet",
    "Bellman_Ford": "relaxes every edge repeatedly to find shortest paths, allowing negative edge weights",
    "SPFA": "a queue-based improvement of Bellman-Ford that only relaxes edges of updated vertices",
    "Floyd_Warshall": "dynamic programming over intermediate vertices giving all-pairs shortest paths",
    "Quick": "picks a pivot, partitions the array around it and recursively sorts the partitions",
    "Merge": "recursively splits the array in halves and merges the sorted halves",
    "Heap": "builds a binary heap and repeatedly extracts the maximum element",
    "Insertion": "builds the sorted array one element at a time by inserting each into place",
    "Selection": "repeatedly selects the minimum of the unsorted part and swaps it to the front",
    "Bubble": "repeatedly swaps adjacent elements that are out of order until no swaps are needed",
    "Shell": "insertion sort over elements a shrinking gap apart",
    "Counting": "counts occurrences of each key value and reconstructs the sorted output from the counts",
    "Radix": "sorts integers digit by digit using a stable sort per digit",
    "Bucket": "distributes elements into buckets, sorts each bucket and concatenates them",
    "Tim_hybrid": "a hybrid of merge sort and insertion sort over natural runs",
    "Builtin": "calls the language's built-in sorted function or list.sort method",
    "Other": "some other algorithm not in this list",
}


def runner() -> Runner:
    return Runner(GEMMA, batch=CFG["batch"], max_new=CFG["max_new"], window=64)


def job(task, setting, family, msg, seeds, T=0.7, topk=0, iv=None):
    return dict(task=task, setting=setting, family=family, user_message=msg, seeds=list(seeds), T=T, topk=topk,
                iv=iv, code_stop=CODE_STOP)


def labels_of(task, setting) -> list[str]:
    return [r["label"] for r in load_scored(GEMMA, task, setting)]


def placebo_rows(task) -> list[dict]:
    return [r for b in range(3) for r in load_scored(GEMMA, task, f"placebo_b{b}")]


# ----------------------------------------------------------------------------------------------- smoke
def stage_smoke(args) -> None:
    from engine import render
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(GEMMA)
    sufs = set()
    for t in TASKS:
        for cond, banned in (("baseline", None), ("placebo", None), ("ban_r1", ["BFS" if t == "T1" else "Bubble"])):
            s = render(tok, user_message(t, cond, banned))
            ids = tok(s, add_special_tokens=False)["input_ids"]
            assert ids.count(tok.bos_token_id) == 1, "double BOS"
            sufs.add(tuple(ids[-SUFFIX_N:]))
    assert len(sufs) == 1, sufs
    logger.info(f"gemma template ok: single BOS, suffix {tok.convert_ids_to_tokens(list(sufs.pop()))} identical")
    r = runner()
    r.run([job("T1", "smoke", "smoke", user_message("T1", "baseline"), range(9000, 9000 + args.n)),
           job("T2", "smoke", "smoke", user_message("T2", "baseline"), range(9000, 9000 + args.n))], None, "smoke")
    r.wait()
    for t in TASKS:
        g = read_jsonl(gens_path(GEMMA, t, "smoke"))
        sc = load_scored(GEMMA, t, "smoke")
        logger.info(f"{t} smoke: labels {Counter(x['label'] for x in sc)} status "
                    f"{Counter(x['oracle_status'] for x in sc)} ntoks median {np.median([x['ntoks'] for x in g])} "
                    f"max {max(x['ntoks'] for x in g)} hit_max {sum(x['hit_max'] for x in g)}")


# ----------------------------------------------------------------------------------------------- screen
def stage_screen_a(args) -> None:
    J = []
    for t in TASKS:
        J.append(job(t, "baseline", "baseline", user_message(t, "baseline"), range(CFG["nb"])))
        for b in range(3):
            s0 = 1000 * (b + 1)
            J.append(job(t, f"placebo_b{b}", "placebo", user_message(t, "placebo"), range(s0, s0 + CFG["npl"])))
    r = runner()
    r.run(J, None, "screen_a")
    r.wait()


def ranks(task) -> list[str]:
    cnt = Counter(labels_of(task, "baseline"))
    meta = json.loads((BA / "data/ban_plan_meta.json").read_text())[task]
    qrank = {c: i for i, c in enumerate(meta["ranked"])}
    bann = bannable(task)
    return sorted(bann, key=lambda c: (-cnt.get(c, 0), qrank.get(c, 99), bann.index(c)))


def plan_bans(task) -> dict:
    r = ranks(task)
    return {"ban_r1": [r[0]], "ban_r2": [r[1]], "ban_r3": [r[2]], "ban_r4": [r[3]], "ban_top3": r[:3],
            "ban_top5": r[:5]}


def stage_screen_b(args) -> None:
    J, plan = [], {}
    for t in TASKS:
        r = ranks(t)
        plan[t] = dict(ranks=r, bans=plan_bans(t), baseline_counts=dict(Counter(labels_of(t, "baseline"))))
        for x in r[:8]:
            J.append(job(t, f"forced_{x}", "forced", user_message(t, f"forced_{x}"), range(CFG["nf"])))
        for b, cl in plan[t]["bans"].items():
            J.append(job(t, b, "ban", user_message(t, b, cl), range(CFG["nban"])))
    write_json(RESULTS / "gemma_screen_plan.json", plan)
    logger.info(f"screen plan {json.dumps({t: plan[t]['ranks'][:8] for t in TASKS})}")
    r = runner()
    r.run(J, None, "screen_b")
    r.wait()


# ----------------------------------------------------------------------------------------------- prompt states
def prompt_states(model, tok, msgs: dict[str, str]) -> dict:
    """One forward pass per distinct prompt string -> {key: float32 [N_LAYERS-1, SUFFIX_N, d]} (layers 1..25)."""
    import torch
    from engine import render
    out = {}
    with torch.no_grad():
        for k, m in msgs.items():
            ids = tok(render(tok, m), add_special_tokens=False, return_tensors="pt")["input_ids"].cuda()
            hs = model.model(input_ids=ids, output_hidden_states=True).hidden_states
            out[k] = torch.stack([hs[l][0, -SUFFIX_N:].float() for l in range(1, N_LAYERS)]).cpu().numpy()
    return out


def msgs_for(task, bans: dict) -> dict:
    m = {"baseline": user_message(task, "baseline"), "placebo": user_message(task, "placebo")}
    for b, cl in bans.items():
        m[b] = user_message(task, b, cl)
    return m


# ----------------------------------------------------------------------------------------------- predictors
def p_placebo(task) -> tuple[list[str], np.ndarray]:
    tax = taxonomy(task)
    labs = [r["label"] for r in placebo_rows(task) if r["label"] in tax]
    return tax, dist(labs, tax, pseudo=0.5)


def obs_counts(task, setting, tax) -> np.ndarray:
    c = Counter(l for l in labels_of(task, setting) if l in tax)
    return np.array([c.get(j, 0) for j in tax], float)


def pred_iia(P0, banned_mask):
    p = np.where(banned_mask, 0.0, P0)
    return p / p.sum()


def pred_iia_comp(P0, banned_mask, rho):
    pb = np.where(banned_mask, P0, 0.0)
    pu = np.where(banned_mask, 0.0, P0)
    if pb.sum() == 0:
        return pu / pu.sum()
    return rho * pb / pb.sum() + (1 - rho) * pu / pu.sum()


def pred_geom(P0, s, beta, banned_mask=None, gamma=0.0):
    z = np.log(P0) + beta * s - (gamma * banned_mask if banned_mask is not None else 0.0)
    z = z - z.max()
    p = np.exp(z)
    return p / p.sum()


def pred_ext(P0, sim, banned_mask, beta_e, gamma):
    return pred_geom(P0, sim, beta_e, banned_mask, gamma)


def loglik(p, n):
    return float((n * np.log(np.maximum(p, 1e-300))).sum())


def fit_params(cases, kind):
    """cases: list of dicts {P0, s, sim, mask, n}. ML fit with scipy."""
    from scipy.optimize import minimize
    if kind == "geom":
        f = lambda th: -sum(loglik(pred_geom(c["P0"], c["s"], th[0]), c["n"]) for c in cases)  # noqa: E731
        x0 = [0.0]
    elif kind == "geom_gamma":
        f = lambda th: -sum(loglik(pred_geom(c["P0"], c["s"], th[0], c["mask"], th[1]), c["n"])  # noqa: E731
                            for c in cases)
        x0 = [0.0, 1.0]
    elif kind == "ext":
        f = lambda th: -sum(loglik(pred_ext(c["P0"], c["sim"], c["mask"], th[0], th[1]), c["n"])  # noqa: E731
                            for c in cases)
        x0 = [0.0, 1.0]
    else:
        raise ValueError(kind)
    best = None
    for start in ([x0] + [[v] + x0[1:] for v in (-5.0, 5.0)]):
        r = minimize(f, start, method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-6, maxiter=4000))
        if best is None or r.fun < best.fun:
            best = r
    return [float(v) for v in best.x], float(-best.fun)


def embed_sims(tasks_tax: dict) -> dict:
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    out = {}
    for t, tax in tasks_tax.items():
        txt = [f"{DISPLAY.get(j, j)}: {DESCR[j]}" for j in tax]
        E = m.encode(txt, normalize_embeddings=True)
        out[t] = E @ E.T
    return out


def s_scores(delta: dict, cvec: dict, band: list[int], tax: list[str]) -> np.ndarray:
    """s_j = mean over band layers of <Delta_h[l], c_j[l]/|c_j[l]|>; 0 when class j has no centroid."""
    s = np.zeros(len(tax))
    for i, j in enumerate(tax):
        if j in cvec:
            s[i] = np.mean([np.dot(delta[l], cvec[j][l] / (np.linalg.norm(cvec[j][l]) + 1e-9)) for l in band])
    return s


# ----------------------------------------------------------------------------------------------- geometry + freeze
def stage_geometry(args) -> None:
    import torch
    from acts_window import choose_band, probe_curve, window_acts
    from engine import load_model, render
    plan = json.loads((RESULTS / "gemma_screen_plan.json").read_text())
    tok, model = load_model(GEMMA)
    # 1. generated-window activations (baseline + forced-compliant) -> probe band + window centroids
    W = {}
    for t in TASKS:
        recs = []
        for st in ["baseline"] + [f"forced_{x}" for x in plan[t]["ranks"][:8]]:
            pid = tok(render(tok, user_message(t, st)), add_special_tokens=False)["input_ids"]
            lab = {r["seed"]: r["label"] for r in load_scored(GEMMA, t, st)}
            for g in read_jsonl(gens_path(GEMMA, t, st)):
                L = lab.get(g["seed"], "Unparseable")
                if st != "baseline" and L != st[len("forced_"):]:
                    continue
                recs.append(dict(task=t, prompt_ids=pid, out_ids=g["output_token_ids"], text=g["text"], label=L,
                                 id=g["id"], src=st))
        a = window_acts(model, tok, recs, N_LAYERS, bs=16)
        W[t] = dict(window=a["window"], fallback=a["fallback"], labels=np.array([r["label"] for r in recs]),
                    src=np.array([r["src"] for r in recs]), norm=a["norm"])
        np.savez(ACTS / f"gemma_{t}_windows.npz", window=a["window"], fallback=a["fallback"],
                 labels=W[t]["labels"], src=W[t]["src"], ids=np.array([r["id"] for r in recs]))
        logger.info(f"gemma {t} window acts n={len(recs)} fallback {a['fallback'].mean():.2f}")
    Xb = {t: W[t]["window"][(W[t]["src"] == "baseline") & (W[t]["labels"] != "Unparseable")] for t in TASKS}
    Yb = {t: W[t]["labels"][(W[t]["src"] == "baseline") & (W[t]["labels"] != "Unparseable")] for t in TASKS}
    curve = probe_curve(Xb, Yb, N_LAYERS, workers=3)
    band, binfo = choose_band(curve, N_LAYERS)
    if binfo["band_gain"] < 0.05:
        mid = N_LAYERS // 2
        band, binfo["fallback_band"] = [mid - 1, mid, mid + 1], True
    logger.info(f"gemma band {band} (gain {binfo['band_gain']:.3f})")
    # 2. prompt states for every screen condition + forced_X prompts
    PS = {}
    for t in TASKS:
        msgs = msgs_for(t, plan[t]["bans"])
        for x in plan[t]["ranks"][:8]:
            msgs[f"forced_{x}"] = user_message(t, f"forced_{x}")
        PS[t] = prompt_states(model, tok, msgs)
    # 3. centroid variants
    cents = {}
    for t in TASKS:
        tax = taxonomy(t)
        X, Y, S = W[t]["window"].astype(np.float32), W[t]["labels"], W[t]["src"]
        base = S == "baseline"
        mu = {l: X[base, l - 1].mean(0) for l in band}
        G, P = {}, {}
        for j in tax:
            m = base & (Y == j)
            if m.sum() >= 8:
                G[j] = {l: X[m, l - 1].mean(0) - mu[l] for l in band}
            elif (S == f"forced_{j}").sum() >= 3:
                G[j] = {l: X[S == f"forced_{j}", l - 1].mean(0) - mu[l] for l in band}
            if f"forced_{j}" in PS[t]:
                P[j] = {l: PS[t][f"forced_{j}"][l - 1].mean(0) - PS[t]["baseline"][l - 1].mean(0) for l in band}
        cents[t] = dict(G=G, P=P)
    # 4. Delta_h (band layers, mean over 5 suffix positions) and per-position versions (all layers) for C4
    delta = {t: {b: {l: (PS[t][b][l - 1] - PS[t]["placebo"][l - 1]).mean(0) for l in band}
                 for b in plan[t]["bans"]} for t in TASKS}
    torch.save({t: {b: torch.tensor(PS[t][b] - PS[t]["placebo"]) for b in plan[t]["bans"]} for t in TASKS},
               DELTA_PATH)
    torch.save({t: {v: {j: {l: torch.tensor(c[l]) for l in band} for j, c in cents[t][v].items()}
                    for v in ("G", "P")} for t in TASKS}, CENT_PATH)
    # 5. fits on the screen
    tt = {t: taxonomy(t) for t in TASKS}
    sims = embed_sims(tt)
    rho_num = rho_den = 0
    cases = {"G": [], "P": []}
    for t in TASKS:
        tax, P0 = p_placebo(t)
        for b, cl in plan[t]["bans"].items():
            n = obs_counts(t, b, tax)
            mask = np.array([j in cl for j in tax], float)
            rho_num += float((n * mask).sum())
            rho_den += float(n.sum())
            sim = sims[t][:, [tax.index(c) for c in cl]].sum(1)
            for v in ("G", "P"):
                cases[v].append(dict(task=t, ban=b, P0=P0, s=s_scores(delta[t][b], cents[t][v], band, tax),
                                     sim=sim, mask=mask, n=n))
    rho = rho_num / max(rho_den, 1)
    fits = {}
    for v in ("G", "P"):
        (beta,), ll = fit_params(cases[v], "geom")
        (bg, gg), llg = fit_params(cases[v], "geom_gamma")
        cv = 0.0
        for i in range(len(cases[v])):
            (bb,), _ = fit_params(cases[v][:i] + cases[v][i + 1:], "geom")
            c = cases[v][i]
            cv += loglik(pred_geom(c["P0"], c["s"], bb), c["n"])
        fits[v] = dict(beta=beta, screen_ll=ll, beta_gamma=[bg, gg], screen_ll_gamma=llg, loo_cv_ll=cv)
    (be, ge), lle = fit_params(cases["G"], "ext")
    ll_iiac = sum(loglik(pred_iia_comp(c["P0"], c["mask"].astype(bool), rho), c["n"]) for c in cases["G"])
    variant = max(("G", "P"), key=lambda v: fits[v]["loo_cv_ll"])
    screen_jsd = {}
    for c_g in cases[variant]:
        obs = (c_g["n"] + 1e-12) / c_g["n"].sum()
        screen_jsd[f"{c_g['task']}/{c_g['ban']}"] = dict(
            IIA=jsd2(pred_iia(c_g["P0"], c_g["mask"].astype(bool)), obs),
            IIA_comp=jsd2(pred_iia_comp(c_g["P0"], c_g["mask"].astype(bool), rho), obs),
            GEOM=jsd2(pred_geom(c_g["P0"], c_g["s"], fits[variant]["beta"]), obs),
            EXT=jsd2(pred_ext(c_g["P0"], c_g["sim"], c_g["mask"], be, ge), obs))
    rng = np.random.default_rng(1000)
    pairs = {}
    for t in TASKS:
        r = plan[t]["ranks"]
        pool = [c for c in r if c not in r[:5]]
        allp = list(itertools.combinations(pool, 2))
        idx = rng.choice(len(allp), size=min(3, len(allp)), replace=False)
        pairs[t] = [list(allp[i]) for i in idx]
    frozen = dict(
        created=time.strftime("%Y-%m-%d %H:%M:%S"), model=GEMMA, engine="HF transformers, eager attention "
        "(softcapping), seeded inverse-CDF sampler, no CodeStop", band=band, band_info=binfo,
        variant=variant, fits=fits, beta=fits[variant]["beta"], beta_gamma=fits[variant]["beta_gamma"],
        beta_e=be, gamma=ge, ext_screen_ll=lle, iia_comp_rho=rho, iia_comp_screen_ll=ll_iiac,
        descriptions=DESCR, pseudo_count=0.5, embedder="sentence-transformers/all-MiniLM-L6-v2",
        menus={t: [c for c, v in Counter(labels_of(t, "baseline")).items() if v / max(1, len(labels_of(t, "baseline")))
                   >= 0.03 and c != "Unparseable"] for t in TASKS},
        ranks={t: plan[t]["ranks"][:8] for t in TASKS}, screen_bans={t: plan[t]["bans"] for t in TASKS},
        confirmation_bans={t: {**{f"ban_r{k}": [plan[t]["ranks"][k - 1]] for k in (5, 6, 7, 8)},
                               **{f"ban_pair{i}": p for i, p in enumerate(pairs[t])}} for t in TASKS},
        thresholds=dict(sign_cell_min_change_pp=10, holm_alpha=0.01, jsd_gain_min=0.20, top_substitute_min=0.70),
        delta_h_sha256=sha256_file(DELTA_PATH), centroids_sha256=sha256_file(CENT_PATH),
        s_j_rule="s_j = mean_band <Delta_h, c_j/|c_j|>, Delta_h = mean over 5 suffix positions of h_ban - h_placebo; "
                 "classes without a centroid get s_j = 0",
        screen_jsd=screen_jsd, seeds_confirmation=f"1000..{1000 + CFG['nconf'] - 1}", n_confirmation=CFG["nconf"])
    h = freeze(FROZEN, frozen)
    write_json(RESULTS / "gemma_probe_band.json", dict(curve={t: {str(l): v for l, v in c.items()}
                                                              for t, c in curve.items()}, band=band, info=binfo))
    logger.info(f"FROZEN {FROZEN.name} {h}: variant {variant} fits {fits} ext {(be, ge)} rho {rho:.3f}")


# ----------------------------------------------------------------------------------------------- confirmation
def stage_confirm(args) -> None:
    h = require_frozen(FROZEN)
    logger.info(f"frozen {FROZEN.name} sha256 {h}")
    fz = json.loads(FROZEN.read_text())
    J = []
    for t in TASKS:
        for b, cl in fz["confirmation_bans"][t].items():
            J.append(job(t, f"conf_{b}", "confirm_ban", user_message(t, "ban", cl),
                         range(1000, 1000 + CFG["nconf"])))
    r = runner()
    r.run(J, None, "confirm")
    r.wait()


def stage_confirm_states(args) -> None:
    """Prompt-suffix states for the confirmation bans (frozen parameters are NOT touched)."""
    import torch
    from engine import load_model
    require_frozen(FROZEN)
    fz = json.loads(FROZEN.read_text())
    tok, model = load_model(GEMMA)
    out = {}
    for t in TASKS:
        msgs = {"placebo": user_message(t, "placebo")}
        for b, cl in fz["confirmation_bans"][t].items():
            msgs[b] = user_message(t, "ban", cl)
        ps = prompt_states(model, tok, msgs)
        out[t] = {b: torch.tensor(ps[b] - ps["placebo"]) for b in fz["confirmation_bans"][t]}
    torch.save(out, RESULTS / "gemma_delta_h_confirm.pt")
    logger.info("confirmation Delta_h saved")


# ----------------------------------------------------------------------------------------------- temperature
def stage_temp(args) -> None:
    J = []
    for t in TASKS:
        for T in (0.3, 1.0, 1.3):
            J.append(job(t, f"temp{T}", "temperature", user_message(t, "baseline"), range(CFG["ntemp"]), T=T))
        J.append(job(t, "temp1.0_top10", "temperature", user_message(t, "baseline"), range(CFG["ntemp"]), T=1.0,
                     topk=10))
    r = runner()
    r.run(J, None, "temp")
    r.wait()


# ----------------------------------------------------------------------------------------------- transplant (C4)
_TR = {}


def tr_resolver(task: str, iv: dict):
    import torch
    from engine import Intervention
    D = _TR["D"][task]  # [P, d] at L*
    if iv["vec"] == "D":
        v = D
    else:
        k = int(iv["vec"][1:])
        g = torch.Generator().manual_seed(4242 + k + (0 if task == "T1" else 100))
        R = torch.randn(D.shape, generator=g)
        v = R / R.norm(dim=-1, keepdim=True) * D.norm(dim=-1, keepdim=True)
    return Intervention(kind="patch", pos_vecs={_TR["L"]: (iv["sign"] * iv.get("scale", 1.0) * v).to("cuda")})


def stage_transplant(args) -> None:
    import torch
    fz = json.loads(FROZEN.read_text())
    L = fz["band"][0]
    dh = torch.load(DELTA_PATH, weights_only=False)
    bans = {"T1": "ban_r1", "T2": "ban_top5"}
    _TR.update(L=L, D={t: dh[t][bans[t]][L - 1].float() for t in TASKS})  # [P, d] = h_ban - h_placebo at hs[L*]
    J = []
    n = range(CFG["ntr"])
    for t in TASKS:
        cl = fz["screen_bans"][t][bans[t]]
        pl, bn = user_message(t, "placebo"), user_message(t, bans[t], cl)
        J += [job(t, "tr_placebo", "transplant", pl, n), job(t, "tr_ban", "transplant", bn, n),
              job(t, "tr_placebo_plusD", "transplant", pl, n, iv=dict(vec="D", sign=1.0)),
              job(t, "tr_ban_minusD", "transplant", bn, n, iv=dict(vec="D", sign=-1.0)),
              job(t, "tr_ban_minusR0", "transplant", bn, n, iv=dict(vec="R0", sign=-1.0))]
        for k in range(3):
            J.append(job(t, f"tr_placebo_plusR{k}", "transplant", pl, n, iv=dict(vec=f"R{k}", sign=1.0)))
    write_json(RESULTS / "transplant_setup.json", dict(L_star=L, bans=bans, n=CFG["ntr"],
                                                       D_norm_per_pos={t: _TR["D"][t].norm(dim=-1).tolist()
                                                                       for t in TASKS}))
    r = runner()
    r.run(J, tr_resolver, "transplant")
    r.wait()


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--n", type=int, default=16)
    for k, v in CFG.items():
        ap.add_argument(f"--{k}", type=int, default=v)
    args = ap.parse_args()
    for k in CFG:
        CFG[k] = getattr(args, k)
    fn = globals().get(f"stage_{args.stage}")
    if fn is None:
        raise SystemExit(f"unknown stage {args.stage}")
    t0 = time.time()
    fn(args)
    logger.info(f"gemma stage {args.stage} done in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    logger.catch(reraise=True)(main_cli)()
