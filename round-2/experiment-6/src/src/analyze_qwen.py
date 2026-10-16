#!/usr/bin/env python3
"""Step B analysis: selector verdicts, entropy vs the DRAW-AVERAGED random entropy, prompting ceiling, C4.

Reads data/scored/qwen/*, data/scored/ba_vllm/*, the frozen files, and writes results/selector_tables.json and
results/engine_consistency.json. Every verdict uses the rules frozen in results/frozen_selector_qwen*.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger
from scipy.stats import chi2_contingency, fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BA, MODE, P4_MENU, QWEN, RESULTS, SCORED, encode, entropy_bits, entropy_mm, hier_boot,  # noqa: E402
                    jsd2, kl_uniform, read_jsonl, require_frozen, wilson, write_json)
from protocol import taxonomy  # noqa: E402
from runner import load_scored  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")

TASKS = ("T1", "T2")
FROZEN = RESULTS / "frozen_selector_qwen.json"
FROZEN2 = RESULTS / "frozen_selector_qwen_alphas.json"
NONIDEA = {"Unparseable"}


def cell(task, setting, seeds=None):
    rows = load_scored(QWEN, task, setting)
    seen, out = set(), []
    for r in rows:
        if r["seed"] not in seen and (seeds is None or r["seed"] in seeds):
            seen.add(r["seed"])
            out.append(r)
    return sorted(out, key=lambda r: r["seed"])


def ba_cell(task, cond):
    return read_jsonl(SCORED / "ba_vllm" / task / f"{cond}.jsonl")


def labs(rows):
    return [r["label"] for r in rows if r["label"] not in NONIDEA]


def offmenu_correct(r, task, excl_builtin=False):
    bad = set(P4_MENU[task]) | NONIDEA | ({"Builtin"} if excl_builtin else set())
    return bool(r["oracle_pass"] and r["label"] not in bad)


def metrics(rows, task, support, pred_gainers=()):
    n = len(rows)
    if n == 0:
        return dict(n=0)
    L = labs(rows)
    c = Counter(L)
    mode = MODE[task]
    nonmode = {k: v for k, v in c.items() if k != mode}
    top_nm = max(nonmode, key=nonmode.get) if nonmode else None
    st = Counter(r["oracle_status"] for r in rows)
    pf = np.array([r["pass_frac"] for r in rows])
    oc = [r for r in rows if offmenu_correct(r, task)]
    return dict(
        n=n, counts=dict(c.most_common()),
        shares={k: dict(share=v / n, ci=wilson(v, n)) for k, v in c.most_common()},
        entropy=entropy_bits(L), entropy_mm=entropy_mm(L), kl_u=kl_uniform(L, support),
        mode_share=c.get(mode, 0) / n, max_nonmode_idea=top_nm,
        max_nonmode_share=(nonmode[top_nm] / n if top_nm else 0.0),
        pass_rate=st.get("pass", 0) / n, fail_rate=st.get("fail", 0) / n,
        not_callable_rate=st.get("not_callable", 0) / n, timeout_rate=st.get("timeout", 0) / n,
        truncated_rate=float(np.mean([r["hit_max"] for r in rows])),
        pass_ci=wilson(st.get("pass", 0), n),
        offmenu_correct=len(oc), offmenu_correct_share=len(oc) / n,
        offmenu_correct_excl_builtin=sum(offmenu_correct(r, task, True) for r in rows),
        offmenu_correct_by_idea=dict(Counter(r["label"] for r in oc)),
        pass_frac_quantiles=[float(np.quantile(pf, q)) for q in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)],
        pass_frac_hist=np.histogram(pf, bins=10, range=(0, 1))[0].tolist(),
        top_gainer_hit=(top_nm in pred_gainers) if top_nm else False)


def decision(m0, m1, m2, preds):
    """Frozen SELECT / FLATTEN / MIXED rule on KL_u at (0, s1, s2) and max non-mode share at s2."""
    if not all(m.get("n") for m in (m0, m1, m2)):
        return "INCOMPLETE"
    sel = (m2["max_nonmode_share"] >= 0.5 and m2["max_nonmode_idea"] in preds and m2["kl_u"] > m1["kl_u"])
    flat = (m0["kl_u"] > m1["kl_u"] > m2["kl_u"]) and m2["max_nonmode_share"] < 0.5
    return "SELECT" if sel else "FLATTEN" if flat else "MIXED"


def fisher_c4(kS, nS, kT, nT):
    return float(fisher_exact([[kS, nS - kS], [kT, nT - kT]], alternative="greater")[1])


def engine_consistency(task, support) -> dict:
    hf = labs(cell(task, "baseline"))
    vl = labs(ba_cell(task, "baseline")) or [r["label"] for r in read_jsonl(BA / "data/labels" / task /
                                                                             "baseline.jsonl")]
    sup = sorted(set(hf) | set(vl))
    p, q = (np.array([Counter(x)[s] for s in sup], float) for x in (hf, vl))
    j = jsd2(p, q)
    rng = np.random.default_rng(3)
    boots = []
    hf_a, vl_a = np.array(hf), np.array(vl)
    for _ in range(2000):
        a = Counter(hf_a[rng.integers(0, len(hf_a), len(hf_a))])
        b = Counter(vl_a[rng.integers(0, len(vl_a), len(vl_a))])
        boots.append(jsd2(np.array([a[s] for s in sup], float) + 1e-12, np.array([b[s] for s in sup], float) + 1e-12))
    # placebo-scale reference: JSD between two vLLM halves (seeds even/odd) gives the sampling floor
    half = jsd2(np.array([Counter(vl[0::2])[s] for s in sup], float) + 1e-12,
                np.array([Counter(vl[1::2])[s] for s in sup], float) + 1e-12)
    tab = np.array([p, q])
    tab = tab[:, tab.sum(0) > 0]
    chi = chi2_contingency(tab)
    return dict(n_hf=len(hf), n_vllm=len(vl), hf_counts=dict(Counter(hf).most_common()),
                vllm_counts=dict(Counter(vl).most_common()), jsd=j, jsd_ci=[float(np.percentile(boots, 2.5)),
                                                                            float(np.percentile(boots, 97.5))],
                jsd_vllm_split_half=half, chi2_p=float(chi[1]), chi2_dof=int(chi[2]))


def main() -> dict:
    h1, h2 = require_frozen(FROZEN), require_frozen(FROZEN2)
    fz, fz2 = json.loads(FROZEN.read_text()), json.loads(FROZEN2.read_text())
    out = dict(frozen_hashes={FROZEN.name: h1, FROZEN2.name: h2}, tasks={})
    main_seeds, re_seeds = set(range(150)), set(range(1000, 1150))
    for t in TASKS:
        s1, s2, sj = fz2[t]["s1"], fz2[t]["s2"], fz2[t]["s2_j"]
        pr = fz["predictions"][t]
        preds = {pr["predicted_top_gainer_proj"], pr["predicted_top_gainer_nn"]}
        names = (["baseline", "away_s1", "away_s2", "away_s1_redraw", "away_s2_redraw", "off_s2", "temp1.0",
                  "temp1.3"] + [f"rand{k}_s{s}" for k in range(5) for s in (1, 2)] +
                 [f"dj_{x}_s2" for x in sj] + [f"forced_{x}" for x in sj])
        C = {n: cell(t, n) for n in names}
        C["baseline_0_149"] = [r for r in C["baseline"] if r["seed"] in main_seeds]
        # support U: P4 menu + Other + any idea reaching >= 10% in some B5 cell (frozen rule)
        U = set(P4_MENU[t]) | {"Other"}
        for n, rows in C.items():
            if n.startswith("forced_") or not rows:
                continue
            for k, v in Counter(labs(rows)).items():
                if v / len(rows) >= 0.10:
                    U.add(k)
        U = sorted(U)
        M = {n: metrics(rows, t, U, preds) for n, rows in C.items()}
        # calibration dose-response (n=30)
        dose = {}
        for a in fz["calibration"]["grid_away"] + [1.5, 2.0]:
            rows = cell(t, f"calib_away_a{a:.3g}")
            if rows:
                dose[f"{a:.3g}"] = metrics(rows, t, U, preds)
        # decision rule on both draws
        d_main = decision(M["baseline_0_149"], M["away_s1"], M["away_s2"], preds)
        d_re = decision(M["baseline_0_149"], M["away_s1_redraw"], M["away_s2_redraw"], preds)
        verdict = d_main if d_main == d_re else f"UNREPLICATED ({d_main} vs {d_re})"
        # entropy (and other stats) vs the DRAW-AVERAGED random entropy (hierarchical bootstrap)
        vs_rand = {}
        for tag in ("s1", "s2"):
            draws = [labs(C[f"rand{k}_{tag}"]) for k in range(5) if C[f"rand{k}_{tag}"]]
            if not draws:
                continue
            for arm, tgt in (("main", [labs(C[f"away_{tag}"])]), ("redraw", [labs(C[f"away_{tag}_redraw"])]),
                             ("both_draws", [labs(C[f"away_{tag}"]), labs(C[f"away_{tag}_redraw"])]),
                             ("off_target", [labs(C["off_s2"])] if tag == "s2" else None)):
                if not tgt or not all(tgt):
                    continue
                enc, vocab = encode(tgt + draws)
                K = len(vocab)
                r = {}
                for est in ("H", "H_mm"):
                    r[est] = hier_boot(enc[:len(tgt)], enc[len(tgt):], K, est, B=10000)
                # max non-mode share and pass rate vs random draw mean
                mode = MODE[t]
                nm = lambda rows: np.array([1.0 if (x != mode) else 0.0 for x in rows])  # noqa: E731
                r["nonmode_share"] = hier_boot([nm(x) for x in tgt], [nm(x) for x in draws], 1, "mean", B=5000)
                trows = {"main": [C[f"away_{tag}"]], "redraw": [C[f"away_{tag}_redraw"]],
                         "both_draws": [C[f"away_{tag}"], C[f"away_{tag}_redraw"]],
                         "off_target": [C["off_s2"]]}[arm]
                pv = lambda rows: np.array([float(x["oracle_pass"]) for x in rows])  # noqa: E731
                r["pass"] = hier_boot([pv(x) for x in trows], [pv(C[f"rand{k}_{tag}"]) for k in range(5)
                                                               if C[f"rand{k}_{tag}"]], 1, "mean", B=5000)
                vs_rand[f"{arm}@{tag}"] = r
        # prompting ceiling for d_j
        ceiling = {}
        ban_mode = ba_cell(t, "ban_r1")
        for x in sj:
            st = C[f"dj_{x}_s2"]
            fx = C[f"forced_{x}"]
            ceiling[x] = dict(
                alpha=sj[x],
                steered=dict(n=len(st), target_share=float(np.mean([r["label"] == x for r in st])) if st else None,
                             correct_target_share=float(np.mean([r["label"] == x and r["oracle_pass"] for r in st]))
                             if st else None, pass_rate=M[f"dj_{x}_s2"].get("pass_rate")),
                forced_prompt=dict(n=len(fx), target_share=float(np.mean([r["label"] == x for r in fx])) if fx
                                   else None, correct_target_share=float(np.mean([r["label"] == x and r["oracle_pass"]
                                                                                  for r in fx])) if fx else None),
                screen_ban_of_mode=dict(n=len(ban_mode), target_share=float(np.mean([r["label"] == x for r in ban_mode]))
                                        if ban_mode else None,
                                        correct_target_share=float(np.mean([r["label"] == x and r["oracle_pass"]
                                                                            for r in ban_mode])) if ban_mode else None,
                                        engine="vLLM (iteration-1 screen; engine mismatch)"))
        # C4 (Qwen): off-menu correct vs temperature
        temps = {"0.7": C["baseline"], "1.0": C["temp1.0"], "1.3": C["temp1.3"]}
        base_pass = M["baseline"]["pass_rate"]

        def rate(rows, excl=False):
            k = sum(offmenu_correct(r, t, excl) for r in rows)
            return k, len(rows), (k + 0.5) / (len(rows) + 1)
        c4 = {}
        for excl in (False, True):
            tr = {T: rate(r, excl) for T, r in temps.items() if r}
            if not tr:
                continue
            bestT = max(tr, key=lambda T: tr[T][2])
            cands = {"away_s1": C["away_s1"], "away_s2": C["away_s2"],
                     **{f"dj_{x}_s2": C[f"dj_{x}_s2"] for x in sj},
                     **{f"screen_{b}": ba_cell(t, b) for b in ("ban_r1", "ban_r2", "ban_r3", "ban_r4", "ban_top3",
                                                                "ban_top5", "ban_rare")}}
            rows_out = {}
            passed = False
            for nm_, rows in cands.items():
                if not rows:
                    continue
                k, n, r_ = rate(rows, excl)
                ps = float(np.mean([x["oracle_pass"] for x in rows]))
                elig = ps >= 0.8 * base_pass
                ratio_ok = r_ >= 3 * tr[bestT][2]
                p = fisher_c4(k, n, tr[bestT][0], tr[bestT][1])
                ok = bool(elig and ratio_ok and p < 0.05)
                passed |= ok
                rows_out[nm_] = dict(k=k, n=n, rate=r_, pass_rate=ps, pass_eligible=elig, ratio_vs_best_temp=r_ /
                                     tr[bestT][2], fisher_p=p, passes=ok,
                                     engine="vLLM (cross-engine)" if nm_.startswith("screen_") else "HF")
            c4["excl_builtin" if excl else "incl_builtin"] = dict(temperature={T: dict(k=v[0], n=v[1], rate=v[2])
                                                                               for T, v in tr.items()},
                                                                  best_temperature=bestT, settings=rows_out,
                                                                  C4_passes=passed)
        hits = {f"{tag}_{arm}": M[n].get("top_gainer_hit") for tag in ("s1", "s2")
                for arm, n in (("main", f"away_{tag}"), ("redraw", f"away_{tag}_redraw"))}
        rand_hits = {f"rand{k}_{tag}": M[f"rand{k}_{tag}"]["top_gainer_hit"] for k in range(5) for tag in ("s1", "s2")
                     if M[f"rand{k}_{tag}"].get("n")}
        out["tasks"][t] = dict(alphas=dict(s1=s1, s2=s2, s2_j=sj), support_U=U, predictions=pr,
                               predicted_gainers=sorted(preds), cells=M, dose_response_calibration=dose,
                               decision=dict(main=d_main, redraw=d_re, verdict=verdict), vs_random=vs_rand,
                               prompting_ceiling=ceiling, c4=c4, top_gainer_hits=hits, random_top_gainer_hits=rand_hits,
                               engine_consistency=engine_consistency(t, U),
                               hf_menu_3pct=sorted(k for k, v in Counter(labs(C["baseline"])).items()
                                                   if v / max(1, len(C["baseline"])) >= 0.03))
        logger.info(f"{t}: decision {d_main}/{d_re}; s1={s1} s2={s2}; " + "; ".join(
            f"{k}: dH_mm={v['H_mm']['diff']:+.2f} [{v['H_mm']['ci'][0]:+.2f},{v['H_mm']['ci'][1]:+.2f}]"
            for k, v in vs_rand.items()))
    out["C4_qwen_passes"] = any(out["tasks"][t]["c4"].get("incl_builtin", {}).get("C4_passes") for t in TASKS)
    out["C4_qwen_passes_excl_builtin"] = any(out["tasks"][t]["c4"].get("excl_builtin", {}).get("C4_passes")
                                             for t in TASKS)
    write_json(RESULTS / "selector_tables.json", out)
    write_json(RESULTS / "engine_consistency.json", {t: out["tasks"][t]["engine_consistency"] for t in TASKS})
    return out


if __name__ == "__main__":
    logger.catch(reraise=True)(main)()
