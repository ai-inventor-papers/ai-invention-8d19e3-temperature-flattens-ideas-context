#!/usr/bin/env python3
"""Step A (CPU): re-analysis of the iteration-1 influence arm (CONTRACT prompt, art_aSN7z8WuA7Ir). READ-ONLY inputs.

1. File counts (gens vs scored), classified as calibration / held-out / explore / gts / main.
2. Claim 3 ('random matched-norm directions raise entropy as much as the targeted knobs'): every targeted
   H-probe / H-dim / A4 setting at the top-3 alphas vs the DRAW-AVERAGED R-add entropy at the same alpha, with a
   hierarchical (draw -> sample) bootstrap, plug-in and Miller-Madow entropy, full-n (150) and n-matched
   (seeds 0..74 = the control seeds, common random numbers). Two label sets: stored influence-arm labels and the
   canonical v1 relabel. Also shows the comparison iteration 1 actually used (pooled draws; single d0 cell).
3. A4 Spearman: exact permutation p (720 permutations) and a CI that resamples samples within every alpha cell
   AND the baseline that defines p0 (the original resampled samples within cells with p0 fixed).
Output: results/reanalysis_contract.json
"""
from __future__ import annotations

import itertools
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import CLASSIFIER_VERSION, classifier_hash, classify_text  # noqa: E402
from common import IA, LOGS, RESULTS, encode, hier_boot, read_jsonl, set_ram_limit, stat_point, write_json  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(LOGS / "reanalysis.log", rotation="30 MB", level="DEBUG")

NONIDEA_IA = {"no_code", "syntax_error"}
NONIDEA_V1 = {"Unparseable"}
FAMILIES = {"H-probe": "Hprobe", "H-dim": "Hdim", "A4": "A4"}
A4_X = [0.0, 0.2, 0.356, 0.632, 1.12, 2.0]
B_MAIN = 10000


def fmt(x: float) -> str:
    return f"{x:.3g}"


def classify_name(n: str) -> str:
    if n.startswith("calib_"):
        return "calibration_only"
    if n.endswith("__ho"):
        return "heldout"
    if n.startswith(("Hprobe_x_", "Hdim_x_")):
        return "explore_posthoc"
    if n.startswith("gts"):
        return "generate_then_select"
    return "main"


def file_counts() -> dict:
    out = {}
    for t in ("T1", "T3"):
        g = {p.stem for p in (IA / "gens" / t).glob("*.jsonl")}
        s = {p.stem for p in (IA / "scored" / t).glob("*.jsonl")}
        cls = Counter(classify_name(n) for n in g)
        out[t] = dict(n_gens_files=len(g), n_scored_files=len(s), gens_without_scored=sorted(g - s),
                      scored_without_gens=sorted(s - g), by_class=dict(cls),
                      calibration_only_files=sorted(n for n in g if classify_name(n) == "calibration_only"))
        logger.info(f"{t}: gens {len(g)} scored {len(s)}; gens-only {sorted(g - s)}; classes {dict(cls)}")
    return out


_V1_CACHE: dict = {}


def v1_labels(task: str, name: str) -> dict[int, str]:
    key = (task, name)
    if key not in _V1_CACHE:
        rows = read_jsonl(IA / "gens" / task / f"{name}.jsonl")
        _V1_CACHE[key] = {r["idx"]: classify_text(r["text"], "graph")["label"] for r in rows}
    return _V1_CACHE[key]


def load_setting(task: str, name: str) -> list[dict]:
    rows = read_jsonl(IA / "scored" / task / f"{name}.jsonl")
    seen, out = set(), []
    for r in rows:  # dedupe by idx (resumed runs can append twice)
        if r["idx"] not in seen:
            seen.add(r["idx"])
            out.append(r)
    return sorted(out, key=lambda r: r["idx"])


def labs(rows: list[dict], task: str, name: str, label_set: str) -> list[str]:
    if label_set == "ia":
        return [r["label"] for r in rows]
    m = v1_labels(task, name)
    return [m.get(r["idx"], "Unparseable") for r in rows]


def claim3(ctx: dict) -> dict:
    per, missing = [], []
    for t in ("T1", "T3"):
        for fam, knob in FAMILIES.items():
            for a in sorted(ctx["alphas"][knob])[-3:]:
                tname = f"{knob}_a{fmt(a)}"
                trows = load_setting(t, tname)
                if not trows:
                    missing.append(f"{t}/{tname}")
                    continue
                rdraws = []
                for d in range(3):
                    rn = f"Radd_a{fmt(a)}_d{d}"
                    rr = load_setting(t, rn)
                    if rr:
                        rdraws.append((rn, rr))
                    else:
                        missing.append(f"{t}/{rn}")
                if not rdraws:
                    continue
                rec = dict(task=t, family=fam, setting=tname, alpha=a, draws=[n for n, _ in rdraws],
                           n_target=len(trows), n_draw=[len(r) for _, r in rdraws], results={})
                for ls, excl in (("ia", NONIDEA_IA), ("v1", NONIDEA_V1)):
                    T_all = labs(trows, t, tname, ls)
                    T_75 = [l for r, l in zip(trows, T_all) if r["idx"] < 75]
                    R = [labs(rr, t, rn, ls) for rn, rr in rdraws]
                    enc, vocab = encode([T_all, T_75] + R, exclude=excl)
                    K = len(vocab)
                    for est in ("H", "H_mm"):
                        for nm, tgt in (("full_n150", enc[0]), ("nmatched_seeds0_74", enc[1])):
                            res = hier_boot([tgt], enc[2:], K, est, B=B_MAIN)
                            rec["results"][f"{ls}|{est}|{nm}"] = res
                    # iteration-1 comparisons as actually run (pooled R-add samples; single d0 cell)
                    pooled = np.concatenate(enc[2:])
                    rec["results"][f"{ls}|H|iter1_pooled_draws"] = hier_boot([enc[0]], [pooled], K, "H", B=2000)
                    rec["results"][f"{ls}|H|iter1_single_d0"] = hier_boot([enc[0]], [enc[2]], K, "H", B=2000)
                # pass rate (labels irrelevant)
                pt = np.array([float(r["pass"]) for r in trows])
                pr = [np.array([float(r["pass"]) for r in rr]) for _, rr in rdraws]
                rec["results"]["pass|full_n150"] = hier_boot([pt], pr, 1, "mean", B=B_MAIN)
                rec["results"]["pass|nmatched_seeds0_74"] = hier_boot(
                    [np.array([float(r["pass"]) for r in trows if r["idx"] < 75])], pr, 1, "mean", B=B_MAIN)
                per.append(rec)
                k = rec["results"]["ia|H_mm|nmatched_seeds0_74"]
                logger.info(f"{t} {tname}: dH(MM, n-matched, IA labels) = {k['diff']:+.3f} CI {k['ci'][0]:+.3f}.."
                            f"{k['ci'][1]:+.3f} -> {k['verdict']}")
    # counts per family and pooled, for the primary specification and every sensitivity
    specs = sorted({k for r in per for k in r["results"] if not k.startswith("pass")})
    counts = {}
    for sp in specs:
        c = {}
        for fam in list(FAMILIES) + ["pooled"]:
            rr = [r for r in per if fam == "pooled" or r["family"] == fam]
            v = Counter(r["results"][sp]["verdict"] for r in rr if sp in r["results"])
            c[fam] = dict(beats_draw_mean=v.get("beats", 0), below_draw_mean=v.get("below", 0),
                          ci_includes_0=v.get("undetermined", 0), n=sum(v.values()))
        counts[sp] = c
    primary = "ia|H_mm|nmatched_seeds0_74"
    pc = counts[primary]["pooled"]
    if pc["beats_draw_mean"] == 0 and pc["below_draw_mean"] == 0:
        verdict = "undetermined (every targeted CI includes the draw mean)"
    elif pc["beats_draw_mean"] > pc["n"] / 2:
        verdict = "overturned (most targeted settings beat the draw-averaged random entropy)"
    elif pc["beats_draw_mean"] == 0:
        verdict = "supported (no targeted setting beats the draw-averaged random entropy)"
    else:
        verdict = "partly overturned (a minority of targeted settings beat the draw mean)"
    return dict(per_setting=per, counts=counts, primary_spec=primary, verdict=verdict, missing_files=missing,
                label_sets={"ia": "stored influence-arm AST labels (no_code/syntax_error excluded, as iteration 1)",
                            "v1": f"canonical {CLASSIFIER_VERSION}:{classifier_hash()} relabel of the same texts"},
                entropy_estimator="plug-in (H) and Miller-Madow (H_mm), bits",
                bootstrap="hierarchical: resample the 3 R-add draws with replacement, then samples within each "
                          f"chosen draw; targeted arm resamples samples; B={B_MAIN}, rng 20261016",
                caveat="only 3 random draws at n=75 exist; draw-level variance is poorly estimated")


def atyp(labels: list[str], p0: dict) -> float:
    v = [-math.log(p0[l]) for l in labels if l in p0]
    return float(np.mean(v)) if v else float("nan")


def a4_stats(results: dict, ctx: dict) -> dict:
    out = {"x": A4_X}
    perms = list(itertools.permutations(range(6)))
    for t in ("T1", "T3"):
        y = results["survival"]["A4"]["tasks"][t]["atypicality"]
        rho = float(spearmanr(A4_X, y).correlation)
        rp = np.array([spearmanr(A4_X, [y[i] for i in p]).correlation for p in perms])
        p2 = float((np.abs(rp) >= abs(rho) - 1e-12).mean())
        p1 = float((rp >= rho - 1e-12).mean())
        # recompute atypicality from scored files to check, then the corrected bootstrap
        base = load_setting(t, "baseline")
        cells = [[r for r in base if r["idx"] < 150]] + [load_setting(t, f"A4_a{fmt(a)}") for a in A4_X[1:]]

        def p0_of(rows):
            c = Counter(r["label"] for r in rows if r["label"] not in NONIDEA_IA)
            n = sum(c.values())
            return {k: v / n for k, v in c.items()}
        p0 = p0_of(base)
        y_re = [atyp([r["label"] for r in c], p0) for c in cells]
        rng = np.random.default_rng(5)
        boots = []
        for _ in range(5000):
            bb = [base[i] for i in rng.integers(0, len(base), len(base))]
            q0 = p0_of(bb)
            yy = [atyp([c[i]["label"] for i in rng.integers(0, len(c), len(c))], q0) for c in cells]
            boots.append(spearmanr(A4_X, yy).correlation)
        ci = [float(np.nanpercentile(boots, 2.5)), float(np.nanpercentile(boots, 97.5))]
        orig_ci = results["survival"]["A4"]["tasks"][t]["spearman_ci"]
        attainable = sorted(set(np.round(rp, 4)))
        out[t] = dict(atypicality=y, atypicality_recomputed=y_re, rho=rho, exact_p_two_sided=p2,
                      exact_p_one_sided_positive=p1, n_permutations=len(perms), original_ci=orig_ci,
                      ci_corrected=ci, attainable_rho_values=len(attainable),
                      rho_step=float(6 / (6 * 35)),
                      point_outside_or_at_edge_of_original_ci=bool(rho < orig_ci[0] or rho >= orig_ci[1] - 0.06))
        logger.info(f"A4 {t}: rho={rho:.3f} exact p2={p2:.3f} p1={p1:.3f} orig CI {orig_ci} corrected CI {ci}")
    out["bootstrap_unit_original"] = ("samples within each alpha cell (1000 resamples), with p0 FIXED from the full "
                                      "baseline; dose 0 = baseline seeds 0..149 (IA src/analysis.py survival())")
    out["bootstrap_unit_corrected"] = ("samples within each alpha cell AND the baseline that defines p0 "
                                       "(5000 resamples, rng 5)")
    out["note"] = ("with n=6 points rho takes only multiples of 1/35 (rho = 1 - 6*sum d^2/210); a two-sided exact p "
                   "below 0.05 needs |rho| >= 0.886")
    return out


def sanity(results: dict) -> dict:
    """Re-derive 2 entropies with the original code path (ent_bits, NONIDEA excluded) and match results.json."""
    out = {}
    for t, n in (("T1", "Hdim_a0.224"), ("T3", "A4_a0.356")):
        rows = load_setting(t, n)
        c = Counter(r["label"] for r in rows if r["label"] not in NONIDEA_IA)
        m = sum(c.values())
        h = -sum(v / m * math.log2(v / m) for v in c.values())
        ref = results["settings"][n]["tasks"][t]["entropy"]
        out[f"{t}/{n}"] = dict(recomputed=h, results_json=ref, match_3dp=round(h, 3) == round(ref, 3))
    return out


@logger.catch(reraise=True)
def main() -> None:
    set_ram_limit(12)
    t0 = time.time()
    if not (IA / "scored").exists():
        write_json(RESULTS / "reanalysis_contract.json", {"status": "inputs unavailable"})
        logger.warning("A: inputs purged")
        return
    results = json.loads((IA / "results/results.json").read_text())
    ctx = json.loads((IA / "results/context.json").read_text())
    out = dict(status="ok", source="iteration-1 influence arm (READ-ONLY)", file_counts=file_counts())
    out["sanity_entropy_rederivation"] = sanity(results)
    logger.info(f"sanity: {out['sanity_entropy_rederivation']}")
    out["a4"] = a4_stats(results, ctx)
    out["claim3"] = claim3(ctx)
    out["iteration1_claim3_text"] = ("Random matched-norm directions raise entropy as much as the targeted knobs "
                                     "(README); knob_vs_random_controls compared each setting with the POOLED R-add "
                                     "samples, and survival() with the single d0 cell")
    out["runtime_min"] = (time.time() - t0) / 60
    write_json(RESULTS / "reanalysis_contract.json", out)
    logger.info(f"claim3 verdict: {out['claim3']['verdict']}; counts(primary) "
                f"{out['claim3']['counts'][out['claim3']['primary_spec']]}")


if __name__ == "__main__":
    main()
