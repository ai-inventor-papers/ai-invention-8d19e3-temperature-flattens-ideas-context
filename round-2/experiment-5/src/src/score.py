#!/usr/bin/env python3
"""STEP 5: confirmation scoring (CPU). Reads the FROZEN predictions and the confirmation labels only.

C2a regularity (Fisher one-sided, Holm, vs the triplicated placebo noise floor) + the same test on
placebo-vs-placebo and alt-placebo-vs-placebo (false-positive rate); sign accuracy (plain / balanced / IIA);
C2b predictor JSD / log-lik / top-substitute with ban-level paired bootstrap; confound controls (mention,
cross-domain); priming decomposition; screen-vs-confirmation table.
Outputs: results/predictor_scores_conf.json, results/regularity.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit as F  # noqa: E402
from loguru import logger  # noqa: E402
from freeze import assert_frozen  # noqa: E402
from protocol import ROOT  # noqa: E402
import predictors as PR  # noqa: E402

RES = ROOT / "results"
CONF = ROOT / "data" / "conf"
PLACEBOS = ["placebo_b1", "placebo_b2", "placebo_b3"]
NB = 2000
MENTION_SCREEN = {("T1", "BFS"): "ban_r1", ("T1", "A_star"): "ban_r3", ("T2", "Bubble"): "ban_r1",
                  ("T2", "Merge"): "ban_r3"}


def labels(task: str, cond: str) -> list[str] | None:
    p = CONF / "labels" / task / f"{cond}.jsonl"
    return [r["label"] for r in F.load_jsonl(p)] if p.exists() else None


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    adj = np.empty(m)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, (m - r) * ps[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def fisher_less(k_ban: int, n_ban: int, k_ref: int, n_ref: int) -> float:
    return float(fisher_exact([[k_ban, n_ban - k_ban], [k_ref, n_ref - k_ref]], alternative="less")[1])


def regularity_family(tests: list[dict], nf: dict) -> dict:
    ps = [t["p"] for t in tests]
    adj = holm(ps) if ps else []
    viol = []
    for t, a in zip(tests, adj):
        t["p_holm"] = a
        t["violation"] = bool(a < 0.01 and t["drop"] > nf[t["task"]][t["idea"]])
        if t["violation"]:
            viol.append(t)
    return dict(n_cells=len(tests), n_violations=len(viol), violating_bans=sorted({f"{v['task']}/{v['cond']}" for v in viol}),
                cells=tests)


def boot_rel_reduction(a: np.ndarray, b: np.ndarray, seed: int = 0) -> dict:
    """relative reduction 1 - mean(b)/mean(a), ban-level paired bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(a)
    est = 1 - b.mean() / a.mean()
    bs = []
    for _ in range(NB):
        i = rng.integers(0, n, n)
        bs.append(1 - b[i].mean() / a[i].mean())
    return dict(estimate=float(est), ci95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], n=int(n))


def boot_diff(a: np.ndarray, b: np.ndarray, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    n = len(a)
    bs = [float((b[i] - a[i]).mean()) for i in (rng.integers(0, n, n) for _ in range(NB))]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(mean_diff=float((b - a).mean()), ci95=[float(lo), float(hi)], tie=bool(lo <= 0 <= hi), n=int(n))


@logger.catch(reraise=True)
def main() -> None:
    assert_frozen(RES / "frozen_predictors.json")
    assert_frozen(RES / "frozen_predictions.json")
    frozen = json.loads((RES / "frozen_predictors.json").read_text())
    fp = json.loads((RES / "frozen_predictions.json").read_text())
    t4p = RES / "frozen_predictions_T4.json"
    if t4p.exists():
        assert_frozen(t4p)
        fp4 = json.loads(t4p.read_text())
        fp["tasks"]["T4"] = dict(classes=fp4["classes"], P0_conf_counts=fp4["P0_conf_counts"], conditions=fp4["conditions"])
    eps = frozen["eps"]
    out: dict = {"noise_floor": {}, "jsd_floor": {}, "conditions": {}}
    nf: dict = {}
    ban_items: list[tuple[str, str, dict, dict]] = []
    for t, td in fp["tasks"].items():
        K = td["classes"]
        blocks = [labels(t, b) for b in PLACEBOS]
        if any(b is None for b in blocks):
            continue
        P = [F.counts_of(b, K) / len(b) for b in blocks]
        nf[t] = {K[j]: float(max(abs(P[a][j] - P[b][j]) for a in range(3) for b in range(a + 1, 3))) for j in range(len(K))}
        out["noise_floor"][t] = nf[t]
        out["jsd_floor"][t] = float(max(PR.jsd(P[a], P[b]) for a in range(3) for b in range(a + 1, 3)))
        c0 = np.array(td["P0_conf_counts"], float)
        q = np.load(RES / f"centroids_{t}.npz")["q"]
        for cond, cd in td["conditions"].items():
            lab = labels(t, cond)
            if lab is None:
                continue
            cnt = F.counts_of(lab, K)
            B = [K.index(c) for c in cd["banned"]]
            item = dict(counts=cnt, counts0=c0, q=q, B=B)
            res = {}
            for k, ph in cd["pred"].items():
                m = PR.metrics_one(np.array(ph), item, eps)
                res[k] = m
            P_obs = cnt / cnt.sum()
            out["conditions"][f"{t}/{cond}"] = dict(task=t, cond=cond, banned=cd["banned"], n=int(cnt.sum()),
                                                   obs=dict(zip(K, P_obs.round(4).tolist())),
                                                   P0=dict(zip(K, (c0 / c0.sum()).round(4).tolist())),
                                                   jsd={k: v["jsd"] for k, v in res.items()},
                                                   loglik={k: v["loglik"] for k, v in res.items()},
                                                   top_hit={k: v["top_hit"] for k, v in res.items()},
                                                   violation_rate=float(P_obs[B].sum()) if B else None)
            if B:
                ban_items.append((t, cond, cd, res))
    # ---------------------------------------------------------------- C2b predictor comparison
    groups = {
        "all_bans": lambda t, c: True,
        "T1T2_singles": lambda t, c: t in ("T1", "T2") and c.startswith("ban_"),
        "pairs": lambda t, c: c.startswith("pair_"),
        "T3": lambda t, c: t == "T3",
        "T4_transfer": lambda t, c: t == "T4",
        "T1T2T3_bans": lambda t, c: t != "T4",
        "singles_all": lambda t, c: c.startswith("ban_") and len(c) > 0,
    }
    preds = ["A", "B", "C", "D", "D2", "D3", "E", "B_screenP0"]
    c2b = {}
    for g, f in groups.items():
        sel = [(t, c, cd, r) for t, c, cd, r in ban_items if f(t, c) and c != "cross"]
        if not sel:
            continue
        gs = {"n_bans": len(sel), "bans": [f"{t}/{c}" for t, c, _, _ in sel]}
        pg = [k for k in preds if all(k in r for _, _, _, r in sel)]
        for k in pg:
            gs[k] = PR.summarize([r[k] for _, _, _, r in sel])
        J = {k: np.array([r[k]["jsd"] for _, _, _, r in sel]) for k in pg}
        gs["B_vs_A_rel_jsd_reduction"] = boot_rel_reduction(J["A"], J["B"])
        for k in ("D", "D2", "D3", "E", "C"):
            gs[f"B_minus_{k}_jsd"] = boot_diff(J[k], J["B"])
        c2b[g] = gs
    out["c2b"] = c2b
    # ---------------------------------------------------------------- C2a regularity
    reg_tests, fp_tests = [], []
    for t, cond, cd, _ in ban_items:
        if not (cond.startswith("ban_") and len(cd["banned"]) == 1):
            continue
        K = fp["tasks"][t]["classes"]
        c0 = np.array(fp["tasks"][t]["P0_conf_counts"], float)
        cnt = F.counts_of(labels(t, cond), K)
        for j, idea in enumerate(K):
            if idea in cd["banned"] or c0[j] < 10:
                continue
            p = fisher_less(int(cnt[j]), int(cnt.sum()), int(c0[j]), int(c0.sum()))
            reg_tests.append(dict(task=t, cond=cond, idea=idea, ban_count=int(cnt[j]), n_ban=int(cnt.sum()),
                                  placebo_count=int(c0[j]), n_placebo=int(c0.sum()),
                                  drop=float(c0[j] / c0.sum() - cnt[j] / cnt.sum()), p=p,
                                  noise_floor=nf[t][idea]))
    reg = regularity_family(reg_tests, nf)
    # false-positive families: each placebo block vs the other two pooled; alt placebo vs pooled placebo
    for t in nf:
        K = fp["tasks"][t]["classes"]
        blocks = {b: F.counts_of(labels(t, b), K) for b in PLACEBOS}
        for b in PLACEBOS:
            rest = sum(v for k, v in blocks.items() if k != b)
            for j, idea in enumerate(K):
                if rest[j] * 1.5 < 10:
                    continue
                fp_tests.append(dict(task=t, cond=f"{b}_vs_rest", idea=idea, drop=float(rest[j] / rest.sum() - blocks[b][j] / 100),
                                     p=fisher_less(int(blocks[b][j]), 100, int(rest[j]), int(rest.sum()))))
        alt = labels(t, "alt_placebo")
        if alt is not None:
            ca = F.counts_of(alt, K)
            c0 = sum(blocks.values())
            for j, idea in enumerate(K):
                if c0[j] < 10:
                    continue
                fp_tests.append(dict(task=t, cond="alt_placebo_vs_placebo", idea=idea,
                                     drop=float(c0[j] / c0.sum() - ca[j] / ca.sum()),
                                     p=fisher_less(int(ca[j]), int(ca.sum()), int(c0[j]), int(c0.sum()))))
    fpr = regularity_family(fp_tests, nf)
    # sign accuracy over all confirmation bans incl. pairs (|change| >= 10pp)
    sign = {}
    for k in ("B", "A", "C", "D", "D2", "D3", "E"):
        sign[k] = PR.summarize([r[k] for t, c, _, r in ban_items if c != "cross"])
    regularity = dict(c2a=reg, false_positive_check=fpr, sign=sign,
                      c2a_pass=bool(len([b for b in reg["violating_bans"] if not b.startswith("T3/")]) >= 3
                                    and (sign["B"]["sign_acc"] or 0) >= 0.70))
    (RES / "regularity.json").write_text(json.dumps(regularity, indent=1))
    # ---------------------------------------------------------------- confound controls
    ctrl = {}
    for t in ("T1", "T2"):
        td = fp["tasks"].get(t)
        if not td:
            continue
        K = td["classes"]
        c0 = np.array(td["P0_conf_counts"], float)
        P0 = c0 / c0.sum()
        for cond, cd in td["conditions"].items():
            if not (cond.startswith("mention_") or cond in ("cross", "alt_placebo")):
                continue
            lab = labels(t, cond)
            if lab is None:
                continue
            P_obs = F.counts_of(lab, K) / len(lab)
            PB = np.array(cd["pred"]["B"])
            e = dict(jsd_obs_vs_placebo=PR.jsd(P_obs, P0), jsd_floor=out["jsd_floor"][t],
                     within_floor=bool(PR.jsd(P_obs, P0) <= out["jsd_floor"][t]),
                     max_abs_s_B=float(np.max(np.abs(cd["s_B"]))), pred_jsd_B_vs_P0=PR.jsd(PB, P0))
            if cond.startswith("mention_"):
                x = cond[len("mention_"):]
                j = K.index(x)
                e.update(idea=x, obs_shift=float(P_obs[j] - P0[j]), pred_shift_B=float(PB[j] - P0[j]),
                         s_B_idea=float(cd["s_B"][j]),
                         direction_match=bool(np.sign(P_obs[j] - P0[j]) == np.sign(PB[j] - P0[j])))
            ctrl[f"{t}/{cond}"] = e
    out["confound_controls"] = ctrl
    # priming decomposition: cos(Delta_ban_X, Delta_mention_X)
    prim = {}
    band = frozen["band"]
    for (t, x), sc in MENTION_SCREEN.items():
        ps_s = F.prompt_states(t)
        from predict_conf import conf_ps
        ps_c = conf_ps(t)
        if f"mention_{x}" not in ps_c:
            continue
        d_ban = F.delta(ps_s, sc, "placebo", band, "G_suffix")
        d_men = F.delta(ps_c, f"mention_{x}", "placebo_b1", band, "G_suffix")
        d_ban_u = F.delta(ps_s, sc, "placebo", band, "G_umean")
        d_men_u = F.delta(ps_c, f"mention_{x}", "placebo_b1", band, "G_umean")
        for v in (d_ban, d_men, d_ban_u, d_men_u):
            v[frozen["massive_dims"]] = 0
        cs = float(d_ban @ d_men / (np.linalg.norm(d_ban) * np.linalg.norm(d_men)))
        cu = float(d_ban_u @ d_men_u / (np.linalg.norm(d_ban_u) * np.linalg.norm(d_men_u)))
        prim[f"{t}/{x}"] = dict(screen_ban=sc, cos_suffix=cs, cos_umean=cu,
                                norm_ban_suffix=float(np.linalg.norm(d_ban)), norm_mention_suffix=float(np.linalg.norm(d_men)))
    out["priming_decomposition"] = prim
    scr = json.loads((RES / "predictor_scores_screen.json").read_text())
    out["screen_vs_confirmation"] = {k: dict(screen_lobo_mean_jsd=scr["lobo"][k]["mean_jsd"],
                                             screen_lobo_sign_acc=scr["lobo"][k]["sign_acc"],
                                             conf_mean_jsd=c2b.get("T1T2T3_bans", {}).get(k, {}).get("mean_jsd"),
                                             conf_T4_mean_jsd=c2b.get("T4_transfer", {}).get(k, {}).get("mean_jsd"))
                                     for k in PR.PREDICTORS}
    out["c2b_pass"] = bool(c2b.get("T1T2T3_bans") and c2b["T1T2T3_bans"]["B_vs_A_rel_jsd_reduction"]["estimate"] >= 0.20
                           and (c2b["T1T2T3_bans"]["B"]["top_hit_rate"] or 0) >= 0.70)
    (RES / "predictor_scores_conf.json").write_text(json.dumps(out, indent=1))
    g = c2b.get("T1T2T3_bans", {})
    logger.info(f"C2a: {reg['n_violations']} violating cells, bans={reg['violating_bans']}; FP family: {fpr['n_violations']}")
    if g:
        logger.info(f"C2b T1-T3: JSD A={g['A']['mean_jsd']:.4f} B={g['B']['mean_jsd']:.4f} D={g['D']['mean_jsd']:.4f} "
                    f"rel={g['B_vs_A_rel_jsd_reduction']} sign B={sign['B']['sign_acc']} bal={sign['B']['balanced_sign_acc']}")


if __name__ == "__main__":
    main()
