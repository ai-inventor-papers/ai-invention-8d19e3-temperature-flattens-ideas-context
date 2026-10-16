#!/usr/bin/env python3
"""Step B: bare-prompt selector on Qwen2.5-3B-Instruct (HF engine of iteration 1, T1/T2 bare prompts).

Stages (run in order):  smoke | base | acts | vectors | freeze | calib | freeze2 | main | analyze
  base    : B1 HF baseline (T=0.7, seeds 0..299) + B1b forced runs (n=60) for the off-menu targets
  acts    : teacher-forced commitment-window activations (layers 1..35) for BA vLLM baseline, HF baseline, forced
  vectors : probe band (5-fold CV vs shuffled labels), centroids, d_away, d_j, random draws, d_off, median norms
  freeze  : results/frozen_selector_qwen.json (+sha256) BEFORE any steered generation
  calib   : B4 strength calibration (n=30); freeze2 writes s1/s2/s2_j -> frozen_selector_qwen_alphas.json
  main    : B5 main sweep (refuses to run without both frozen files)
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import activations as ba_acts  # noqa: E402  (BA commitment window: commit_pos, LEX_GRAPH/LEX_SORT, WIN=16; import before logger setup)
from common import (ACTS, BA, LOGS, MODE, P4_MENU, QWEN, RESULTS, freeze, read_jsonl, require_frozen,  # noqa: E402
                    set_ram_limit, sha256_file, write_json)
from protocol import DISPLAY, user_message  # noqa: E402
from runner import Runner, load_scored  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(LOGS / "steer_qwen.log", rotation="30 MB", level="DEBUG")

TASKS = ("T1", "T2")
OFF_TARGETS = {"T1": ["IDDFS", "Bellman_Ford"], "T2": ["Counting", "Heap"]}
BACKUP_TARGETS = {"T1": ["Bidirectional", "Greedy_best_first"], "T2": ["Radix", "Shell"]}
CALIB_AWAY = [0.05, 0.106, 0.224, 0.473, 1.0]
CALIB_DJ = [0.224, 0.473, 1.0]
N_RAND = 5
# CODE-STOP CHECK (tests/check_codestop.py): v1 agreement full vs truncated = 0.87 (T1), 0.967 (T2) < 0.97 -> disabled
CODE_STOP = False
FROZEN = RESULTS / "frozen_selector_qwen.json"
FROZEN2 = RESULTS / "frozen_selector_qwen_alphas.json"
VEC_PATH = RESULTS / "qwen_vectors.pt"
CFG = dict(batch=160)


def runner() -> Runner:
    return Runner(QWEN, batch=CFG["batch"], max_new=768, window=64)


def job(task, setting, family, cond, seeds, T=0.7, topk=0, iv=None, banned=None):
    return dict(task=task, setting=setting, family=family, user_message=user_message(task, cond, banned),
                seeds=list(seeds), T=T, topk=topk, iv=iv, code_stop=CODE_STOP)


# ----------------------------------------------------------------------------------------------- smoke
def stage_smoke(args) -> None:
    from engine import render
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(QWEN)
    for t in TASKS:
        ref = read_jsonl(BA / "data/gen" / t / "baseline.jsonl")[0]["prompt_text"]
        mine = render(tok, user_message(t, "baseline"))
        assert mine == ref, f"render mismatch on {t}:\n{mine!r}\n{ref!r}"
    logger.info("render check: rendered Qwen prompt == BA prompt_text (byte-for-byte) on T1 and T2")
    r = runner()
    jobs = [job("T1", "smoke", "smoke", "baseline", range(9000, 9000 + args.n))]
    r.run(jobs, resolver=None, tag="smoke")
    r.wait()
    sc = load_scored(QWEN, "T1", "smoke")
    logger.info(f"smoke labels {Counter(x['label'] for x in sc)} status {Counter(x['oracle_status'] for x in sc)}")


# ----------------------------------------------------------------------------------------------- base
def stage_base(args) -> None:
    jobs = []
    for t in TASKS:
        jobs.append(job(t, "baseline", "baseline", "baseline", range(args.n_base)))
    for t in TASKS:
        for x in OFF_TARGETS[t] + (BACKUP_TARGETS[t] if args.backups else []):
            jobs.append(job(t, f"forced_{x}", "forced", f"forced_{x}", range(args.n_forced)))
    r = runner()
    r.run(jobs, resolver=None, tag="base")
    r.wait()
    for t in TASKS:
        sc = load_scored(QWEN, t, "baseline")
        logger.info(f"{t} HF baseline n={len(sc)} {Counter(x['label'] for x in sc).most_common()} "
                    f"pass={np.mean([x['oracle_pass'] for x in sc]):.2f}")


# ----------------------------------------------------------------------------------------------- acts (B2)
def _src_records(tok, task: str) -> dict[str, list[dict]]:
    """Samples for activations: BA vLLM baseline, HF baseline, forced-compliant HF rows."""
    from engine import render
    out = {}
    ba = read_jsonl(BA / "data/gen" / task / "baseline.jsonl")
    bal = {r["id"]: r["label"] for r in read_jsonl(BA / "data/labels" / task / "baseline.jsonl")}
    out["ba_baseline"] = [dict(task=task, prompt_ids=r["prompt_token_ids"], out_ids=r["output_token_ids"],
                               text=r["output_text"], label=bal[r["id"]], id=r["id"]) for r in ba]
    pids = tok(render(tok, user_message(task, "baseline")), add_special_tokens=False)["input_ids"]
    gens = {r["seed"]: r for r in read_jsonl(Path(gens_path_q(task, "baseline")))}
    lab = {r["seed"]: r["label"] for r in load_scored(QWEN, task, "baseline")}
    out["hf_baseline"] = [dict(task=task, prompt_ids=pids, out_ids=g["output_token_ids"], text=g["text"],
                               label=lab.get(s, "Unparseable"), id=g["id"]) for s, g in sorted(gens.items())]
    for x in OFF_TARGETS[task] + BACKUP_TARGETS[task]:
        st = f"forced_{x}"
        gg = {r["seed"]: r for r in read_jsonl(Path(gens_path_q(task, st)))}
        if not gg:
            continue
        fp = tok(render(tok, user_message(task, st)), add_special_tokens=False)["input_ids"]
        lab = {r["seed"]: r["label"] for r in load_scored(QWEN, task, st)}
        out[st] = [dict(task=task, prompt_ids=fp, out_ids=g["output_token_ids"], text=g["text"], label=lab[s],
                        id=g["id"]) for s, g in sorted(gg.items()) if lab.get(s) == x]
    return out


def gens_path_q(task, setting):
    from runner import gens_path
    return gens_path(QWEN, task, setting)


def stage_acts(args) -> None:
    import torch
    from acts_window import window_acts
    from engine import load_model
    tok, model = load_model(QWEN)
    nL = model.config.num_hidden_layers  # 36 -> hidden_states 1..35 kept
    stats = {}
    for t in TASKS:
        for name, recs in _src_records(tok, t).items():
            outp = ACTS / f"qwen_{t}_{name}.npz"
            if outp.exists() and len(np.load(outp)["ids"]) == len(recs):
                continue
            t0 = time.time()
            a = window_acts(model, tok, recs, nL)
            np.savez(outp, window=a["window"], norm=a["norm"], fallback=a["fallback"], c_pos=a["c_pos"],
                     ids=np.array([r["id"] for r in recs]), labels=np.array([r["label"] for r in recs]))
            stats[f"{t}/{name}"] = dict(n=len(recs), fallback_rate=float(a["fallback"].mean()),
                                        seconds=time.time() - t0)
            logger.info(f"acts {t}/{name}: {stats[f'{t}/{name}']}")
            gc.collect()
            torch.cuda.empty_cache()
    write_json(RESULTS / "qwen_acts_stats.json", stats)


def load_acts(t: str, name: str) -> dict | None:
    p = ACTS / f"qwen_{t}_{name}.npz"
    if not p.exists():
        return None
    z = np.load(p)
    return {k: z[k] for k in z.files}


# ----------------------------------------------------------------------------------------------- vectors (B2)
def unit(v):
    return v / (np.linalg.norm(v) + 1e-12)


def stage_vectors(args) -> None:
    import torch
    from acts_window import choose_band, probe_curve
    base = {t: [load_acts(t, "ba_baseline"), load_acts(t, "hf_baseline")] for t in TASKS}
    X = {t: np.concatenate([b["window"] for b in base[t]]) for t in TASKS}
    Y = {t: np.concatenate([b["labels"] for b in base[t]]) for t in TASKS}
    fbr = {t: float(np.concatenate([b["fallback"] for b in base[t]]).mean()) for t in TASKS}
    logger.info(f"fallback rate {fbr}")
    keep = {t: Y[t] != "Unparseable" for t in TASKS}
    curve = probe_curve({t: X[t][keep[t]] for t in TASKS}, {t: Y[t][keep[t]] for t in TASKS}, 36, workers=3)
    band, binfo = choose_band(curve, 36)
    if binfo["band_gain"] < 0.05:
        logger.warning(f"probe band gain {binfo['band_gain']:.3f} < 0.05 -> iteration-1 band 29-31")
        band, binfo["fallback_band"] = [29, 30, 31], True
    logger.info(f"band {band} gain {binfo['band_gain']:.3f}")
    V = {"band": band, "median_norm": {}, "centroids": {}, "mu": {}, "d_away": {}, "d_j": {}, "d_off": {},
         "rand": {}, "counts": {}}
    nrm = np.concatenate([np.concatenate([b["norm"] for b in base[t]]) for t in TASKS])
    for l in band:
        V["median_norm"][l] = float(np.median(nrm[:, l - 1]))
    for t in TASKS:
        mode = MODE[t]
        xs, ys = X[t][keep[t]].astype(np.float32), Y[t][keep[t]]
        V["counts"][t] = dict(Counter(ys.tolist()))
        cents = {}
        for j in sorted(set(ys)):
            if (ys == j).sum() >= 8:
                cents[j] = {l: xs[ys == j, l - 1].mean(0) for l in band}
        forced_n = {}
        for x in OFF_TARGETS[t] + BACKUP_TARGETS[t]:
            a = load_acts(t, f"forced_{x}")
            forced_n[x] = 0 if a is None else len(a["ids"])
            if a is not None and len(a["ids"]) >= 1:
                cents[f"forced:{x}"] = {l: a["window"][:, l - 1].astype(np.float32).mean(0) for l in band}
        V["counts"][t]["forced_compliant"] = forced_n
        V["centroids"][t] = cents
        V["mu"][t] = {l: xs[:, l - 1].mean(0) for l in band}
        nonmode = ys != mode
        V["d_away"][t] = {l: unit(xs[nonmode, l - 1].mean(0) - xs[~nonmode, l - 1].mean(0)) for l in band}
        V["d_away_rawnorm"] = V.get("d_away_rawnorm", {})
        V["d_away_rawnorm"][t] = {l: float(np.linalg.norm(xs[nonmode, l - 1].mean(0) - xs[~nonmode, l - 1].mean(0)))
                                  for l in band}
        V["d_j"][t] = {}
        for x in OFF_TARGETS[t] + BACKUP_TARGETS[t]:
            if f"forced:{x}" in cents:
                V["d_j"][t][x] = {l: unit(cents[f"forced:{x}"][l] - cents[mode][l]) for l in band}
    for t in TASKS:
        other = "T2" if t == "T1" else "T1"
        V["d_off"][t] = V["d_away"][other]
    d = X["T1"].shape[2]
    for k in range(N_RAND):
        rng = np.random.default_rng(777 + k)
        V["rand"][k] = {l: unit(rng.standard_normal(d)) for l in band}
    # sanity: BFS vs DFS centred-centroid cosine
    checks = {}
    for t in TASKS:
        c = V["centroids"][t]
        ks = [k for k in c if not k.startswith("forced:")]
        if len(ks) >= 2:
            a, b = ks[:2]
            l = band[1]
            checks[t] = dict(pair=[a, b], cos_centred=float(np.dot(unit(c[a][l] - V["mu"][t][l]),
                                                                    unit(c[b][l] - V["mu"][t][l]))),
                             d_away_raw_norm=V["d_away_rawnorm"][t])
    tens = {"band": band, "median_norm": V["median_norm"]}
    for key in ("d_away", "d_off"):
        tens[key] = {t: {l: torch.tensor(V[key][t][l]) for l in band} for t in TASKS}
    tens["d_j"] = {t: {x: {l: torch.tensor(v[l]) for l in band} for x, v in V["d_j"][t].items()} for t in TASKS}
    tens["rand"] = {k: {l: torch.tensor(v[l]) for l in band} for k, v in V["rand"].items()}
    tens["centroids"] = {t: {j: {l: torch.tensor(v[l]) for l in band} for j, v in V["centroids"][t].items()}
                         for t in TASKS}
    tens["mu"] = {t: {l: torch.tensor(V["mu"][t][l]) for l in band} for t in TASKS}
    torch.save(tens, VEC_PATH)
    write_json(RESULTS / "qwen_probe_band.json", dict(curve={t: {str(l): v for l, v in c.items()} for t, c in
                                                             curve.items()}, band=band, info=binfo,
                                                      fallback_rate=fbr, counts=V["counts"], checks=checks,
                                                      iteration1_band=[29, 30, 31],
                                                      same_as_iteration1=band == [29, 30, 31]))
    logger.info(f"vectors saved; checks {checks}")


# ----------------------------------------------------------------------------------------------- freeze (B3)
def _cos(a, b):
    return float(np.dot(unit(a), unit(b)))


def stage_freeze(args) -> None:
    import torch
    V = torch.load(VEC_PATH, weights_only=False)
    band = V["band"]
    targets = {}
    for t in TASKS:
        ok = [x for x in OFF_TARGETS[t] if x in V["d_j"][t]]
        comp = V["counts"][t]["forced_compliant"] if "counts" in V else {}
        targets[t] = ok
    pq = json.loads((RESULTS / "qwen_probe_band.json").read_text())
    for t in TASKS:
        fc = pq["counts"][t]["forced_compliant"]
        sel = []
        for x in OFF_TARGETS[t]:
            if fc.get(x, 0) >= 10:
                sel.append(x)
            else:
                alt = [b for b in BACKUP_TARGETS[t] if fc.get(b, 0) >= 10 and b not in sel]
                if alt:
                    sel.append(max(alt, key=lambda b: fc[b]))
                    logger.warning(f"{t}: forced_{x} compliance {fc.get(x, 0)}/60 < 10 -> substitute {sel[-1]}")
        targets[t] = sel
    pred = {}
    for t in TASKS:
        mode = MODE[t]
        C = {k: {l: V["centroids"][t][k][l].numpy() for l in band} for k in V["centroids"][t]}
        mu = {l: V["mu"][t][l].numpy() for l in band}
        da = {l: V["d_away"][t][l].numpy() for l in band}
        g, nn = {}, {}
        for k in C:
            j = k.split(":", 1)[1] if k.startswith("forced:") else k
            if j == mode or k == mode:
                continue
            g[k] = float(np.mean([_cos(da[l], C[k][l] - C[mode][l]) for l in band]))
            nn[k] = float(np.mean([_cos(C[k][l] - mu[l], C[mode][l] - mu[l]) for l in band]))
        gl = sorted(g.items(), key=lambda kv: -kv[1])
        nl = sorted(nn.items(), key=lambda kv: -kv[1])
        strip = lambda k: k.split(":", 1)[1] if k.startswith("forced:") else k  # noqa: E731
        pred[t] = dict(mode=mode, g_proj=dict(gl), nn_cos=dict(nl),
                       predicted_top_gainer_proj=strip(gl[0][0]), predicted_top_gainer_nn=strip(nl[0][0]),
                       ranked_proj=[strip(k) for k, _ in gl], ranked_nn=[strip(k) for k, _ in nl])
    frozen = dict(
        created=time.strftime("%Y-%m-%d %H:%M:%S"), model=QWEN, band=band,
        median_norm={str(k): v for k, v in V["median_norm"].items()}, vectors_sha256=sha256_file(VEC_PATH),
        scaling="vec_l = alpha * median_norm[l] / len(band) * unit(v); window = prompt-final + gen 1..64",
        off_targets=targets, predictions=pred,
        support_rule="U = P4 menu + {Other} + {any j reaching >= 10% in some B5 cell}; fixed after B5 by this rule",
        decision_rule=dict(
            SELECT="at s2: max non-mode share >= 0.5 AND that idea is a predicted gainer (proj or nn) AND "
                   "KL_u(s2) > KL_u(s1) (entropy non-monotone across 0, s1, s2)",
            FLATTEN="KL_u(0) > KL_u(s1) > KL_u(s2) AND max non-mode share at s2 < 0.5",
            MIXED="otherwise", replication="computed separately on the re-draw (seeds 1000..1149); counts only if "
                                           "both draws agree"),
        entropy_vs_random="targeted entropy minus the DRAW-AVERAGED entropy of 5 matched-norm random draws at the "
                          "same alpha; hierarchical bootstrap (draws then samples) 95% CI; beats random iff CI lo > 0",
        c4_rule="offmenu_correct = #(pass AND v1 label not in P4 menu)/n (Builtin, Other included); C4 passes iff for "
                "some setting S with pass(S) >= 0.8*pass(B1): (k_S+.5)/(n_S+1) >= 3*max_T (k_T+.5)/(n_T+1) over HF "
                "T in {0.7,1.0,1.3} AND one-sided Fisher p < 0.05 vs the best temperature cell; sensitivity "
                "excluding Builtin; eligible: d_away s1/s2, d_j s2, Qwen screen bans (vLLM, engine mismatch flagged)",
        calibration=dict(grid_away=CALIB_AWAY, grid_dj=CALIB_DJ, n=30, seeds="0..29",
                         s1="alpha whose mode share is closest to 0.5 x HF-baseline mode share",
                         s2="alpha with minimal mode share subject to pass >= 0.8 x HF-baseline pass (if none, "
                            "the smallest alpha; shortfall logged)",
                         s2_j="alpha maximising target share subject to the same pass rule"),
        n_random_draws=N_RAND, random_seeds=[777 + k for k in range(N_RAND)])
    h = freeze(FROZEN, frozen)
    logger.info(f"FROZEN {FROZEN.name} sha256 {h}; predictions "
                f"{ {t: (pred[t]['predicted_top_gainer_proj'], pred[t]['predicted_top_gainer_nn']) for t in TASKS} }")


# ----------------------------------------------------------------------------------------------- resolver
_V = {}


def resolver(task: str, iv: dict):
    import torch
    from engine import Intervention
    if not _V:
        _V.update(torch.load(VEC_PATH, weights_only=False))
    band, med = _V["band"], _V["median_norm"]
    name = iv["vec"]
    if name == "d_away":
        src = _V["d_away"][task]
    elif name == "d_off":
        src = _V["d_off"][task]
    elif name.startswith("d_j:"):
        src = _V["d_j"][task][name[4:]]
    elif name.startswith("rand:"):
        src = _V["rand"][int(name[5:])]
    else:
        raise ValueError(name)
    vecs = {l: (iv["alpha"] * med[l] / len(band) * src[l].float()).to("cuda") for l in band}
    return Intervention(kind="add", vecs=vecs)


def fa(a: float) -> str:
    return f"{a:.3g}"


# ----------------------------------------------------------------------------------------------- calib (B4)
def stage_calib(args) -> None:
    require_frozen(FROZEN)
    fz = json.loads(FROZEN.read_text())
    jobs = []
    for t in TASKS:
        for a in CALIB_AWAY + ([1.5, 2.0] if args.backups else []):
            jobs.append(job(t, f"calib_away_a{fa(a)}", "calib", "baseline", range(30),
                            iv=dict(kind="add", vec="d_away", alpha=a)))
        for x in fz["off_targets"][t]:
            for a in CALIB_DJ:
                jobs.append(job(t, f"calib_dj_{x}_a{fa(a)}", "calib", "baseline", range(30),
                                iv=dict(kind="add", vec=f"d_j:{x}", alpha=a)))
    r = runner()
    r.run(jobs, resolver=resolver, tag="calib")
    r.wait()


def _share(rows, lab):
    return float(np.mean([x["label"] == lab for x in rows])) if rows else float("nan")


def _pass(rows):
    return float(np.mean([x["oracle_pass"] for x in rows])) if rows else float("nan")


def stage_freeze2(args) -> None:
    require_frozen(FROZEN)
    fz = json.loads(FROZEN.read_text())
    out, log = {}, {}
    for t in TASKS:
        mode = MODE[t]
        b = [x for x in load_scored(QWEN, t, "baseline")]
        bm, bp = _share(b, mode), _pass(b)
        grid = [a for a in CALIB_AWAY + [1.5, 2.0] if load_scored(QWEN, t, f"calib_away_a{fa(a)}")]
        cells = {a: load_scored(QWEN, t, f"calib_away_a{fa(a)}") for a in grid}
        ms = {a: _share(c, mode) for a, c in cells.items()}
        ps = {a: _pass(c) for a, c in cells.items()}
        s1 = min(grid, key=lambda a: abs(ms[a] - 0.5 * bm))
        elig = [a for a in grid if ps[a] >= 0.8 * bp]
        if elig:
            s2 = min(elig, key=lambda a: (ms[a], -a))
            short = None
        else:
            s2 = min(grid)
            short = "no alpha meets pass >= 0.8x baseline; s2 = smallest alpha"
        if s1 == s2 and len(grid) > 1:
            log[t + "_note"] = "s1 == s2 under the frozen rules"
        sj = {}
        for x in fz["off_targets"][t]:
            cj = {a: load_scored(QWEN, t, f"calib_dj_{x}_a{fa(a)}") for a in CALIB_DJ}
            el = [a for a in CALIB_DJ if _pass(cj[a]) >= 0.8 * bp]
            pool = el or CALIB_DJ
            sj[x] = max(pool, key=lambda a: (_share(cj[a], x), -a))
            log[f"{t}_dj_{x}"] = {fa(a): dict(target_share=_share(cj[a], x), pass_=_pass(cj[a])) for a in CALIB_DJ}
        out[t] = dict(s1=s1, s2=s2, s2_j=sj, baseline_mode_share=bm, baseline_pass=bp, shortfall=short,
                      mode_share_by_alpha={fa(a): ms[a] for a in grid}, pass_by_alpha={fa(a): ps[a] for a in grid},
                      mode_halved=bool(min(ms.values()) <= 0.5 * bm))
    out["frozen_parent_sha256"] = require_frozen(FROZEN)
    out["details"] = log
    h = freeze(FROZEN2, out)
    logger.info(f"FROZEN {FROZEN2.name} sha256 {h}: " + json.dumps({t: (out[t]['s1'], out[t]['s2'], out[t]['s2_j'])
                                                                      for t in TASKS}))


# ----------------------------------------------------------------------------------------------- main (B5)
def main_jobs(args) -> list[dict]:
    fz = json.loads(FROZEN.read_text())
    fz2 = json.loads(FROZEN2.read_text())
    J = []
    for t in TASKS:
        s1, s2 = fz2[t]["s1"], fz2[t]["s2"]
        main = range(args.n_main)
        for tag, a in (("s1", s1), ("s2", s2)):
            iv = dict(kind="add", vec="d_away", alpha=a)
            J.append(job(t, f"away_{tag}", "targeted", "baseline", main, iv=iv))
            J.append(job(t, f"away_{tag}_redraw", "targeted_redraw", "baseline", range(1000, 1000 + args.n_main),
                         iv=iv))
        for k in range(N_RAND):
            J.append(job(t, f"rand{k}_s2", "random", "baseline", main, iv=dict(kind="add", vec=f"rand:{k}", alpha=s2)))
        for k in range(N_RAND):
            J.append(job(t, f"rand{k}_s1", "random", "baseline", range(args.n_rand_s1),
                         iv=dict(kind="add", vec=f"rand:{k}", alpha=s1)))
        J.append(job(t, "off_s2", "off_target", "baseline", main, iv=dict(kind="add", vec="d_off", alpha=s2)))
        for x, a in fz2[t]["s2_j"].items():
            J.append(job(t, f"dj_{x}_s2", "d_j", "baseline", main, iv=dict(kind="add", vec=f"d_j:{x}", alpha=a)))
        for T in (1.0, 1.3):
            J.append(job(t, f"temp{T}", "temperature", "baseline", main, T=T))
    if args.only:
        keep = set(args.only.split(","))
        J = [j for j in J if j["setting"] in keep]
    return J


def stage_main(args) -> None:
    h1, h2 = require_frozen(FROZEN), require_frozen(FROZEN2)
    logger.info(f"frozen hashes: {FROZEN.name} {h1}; {FROZEN2.name} {h2}")
    write_json(RESULTS / "qwen_main_hashes.json", {FROZEN.name: h1, FROZEN2.name: h2})
    J = main_jobs(args)
    r = runner()
    r.run(J, resolver=resolver, tag="main")
    r.wait()


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--n_base", type=int, default=300)
    ap.add_argument("--n_forced", type=int, default=60)
    ap.add_argument("--backups", action="store_true")
    ap.add_argument("--batch", type=int, default=160)
    ap.add_argument("--n_main", type=int, default=150)
    ap.add_argument("--n_rand_s1", type=int, default=100)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    CFG["batch"] = args.batch
    # no RLIMIT_AS here: CUDA reserves a large virtual address space (cuMemAddressReserve fails under the cap)
    fn = globals().get(f"stage_{args.stage}")
    if fn is None:
        raise SystemExit(f"unknown stage {args.stage}")
    t0 = time.time()
    fn(args)
    logger.info(f"stage {args.stage} done in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    logger.catch(reraise=True)(main_cli)()
