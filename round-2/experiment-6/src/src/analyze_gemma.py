#!/usr/bin/env python3
"""Step C analysis (CPU): gemma screen summary, frozen-predictor confirmation (C2a/C2b), regularity,
temperature law (C5 / C1-temp) and the Delta_h transplant (C4 / C2c).

Writes results/gemma_bans.json, results/gemma_temperature.json, results/transplant.json.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger
from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEMMA, RESULTS, dist, jsd2, read_jsonl, require_frozen, wilson, write_json  # noqa: E402
from gemma import (CENT_PATH, FROZEN, TASKS, embed_sims, labels_of, loglik, obs_counts, p_placebo,  # noqa: E402
                   placebo_rows, pred_ext, pred_geom, pred_iia, pred_iia_comp, s_scores)
from protocol import taxonomy  # noqa: E402
from runner import gens_path, load_scored  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
NONIDEA = {"Unparseable"}


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(m)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, (m - r) * pvals[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def screen_summary(fz) -> dict:
    out = {}
    for t in TASKS:
        tax = taxonomy(t)
        b = labels_of(t, "baseline")
        blocks = [labels_of(t, f"placebo_b{k}") for k in range(3)]
        floor = {}
        for j in tax:
            sh = [np.mean([x == j for x in bl]) if bl else 0.0 for bl in blocks]
            floor[j] = float(max(sh) - min(sh))
        forced = {}
        for x in fz["ranks"][t]:
            rows = load_scored(GEMMA, t, f"forced_{x}")
            forced[x] = dict(n=len(rows), compliance=float(np.mean([r["label"] == x for r in rows])) if rows else None,
                             correct=float(np.mean([r["label"] == x and r["oracle_pass"] for r in rows])) if rows
                             else None)
        bans = {}
        for bn, cl in fz["screen_bans"][t].items():
            rows = load_scored(GEMMA, t, bn)
            L = [r["label"] for r in rows]
            bans[bn] = dict(banned=cl, n=len(rows), counts=dict(Counter(L).most_common()),
                            violation_rate=float(np.mean([x in cl for x in L])) if L else None,
                            pass_rate=float(np.mean([r["oracle_pass"] for r in rows])) if rows else None)
        brow = load_scored(GEMMA, t, "baseline")
        out[t] = dict(baseline_counts=dict(Counter(b).most_common()), n_baseline=len(b),
                      baseline_pass=float(np.mean([r["oracle_pass"] for r in brow])) if brow else None,
                      baseline_status=dict(Counter(r["oracle_status"] for r in brow)),
                      truncated_rate=float(np.mean([r["hit_max"] for r in brow])) if brow else None,
                      menu_3pct=fz["menus"][t], ranks=fz["ranks"][t],
                      placebo_blocks=[dict(Counter(bl).most_common()) for bl in blocks],
                      placebo_noise_floor=floor, max_noise_floor_pp=100 * max(floor.values()),
                      forced=forced, screen_bans=bans)
    return out


def predict_all(fz, t, ban, cl, delta, cents, sims):
    tax, P0 = p_placebo(t)
    mask = np.array([j in cl for j in tax], float)
    s = s_scores(delta, cents[fz["variant"]], fz["band"], tax)
    sim = sims[:, [tax.index(c) for c in cl]].sum(1)
    bg, gg = fz["beta_gamma"]
    return tax, P0, mask, dict(
        IIA=pred_iia(P0, mask.astype(bool)), IIA_comp=pred_iia_comp(P0, mask.astype(bool), fz["iia_comp_rho"]),
        GEOM=pred_geom(P0, s, fz["beta"]), GEOM_gamma=pred_geom(P0, s, bg, mask, gg),
        EXT=pred_ext(P0, sim, mask, fz["beta_e"], fz["gamma"])), s


def confirmation(fz) -> dict:
    import torch
    dconf = torch.load(RESULTS / "gemma_delta_h_confirm.pt", weights_only=False)
    C = torch.load(CENT_PATH, weights_only=False)
    band = fz["band"]
    cents = {t: {v: {j: {l: c[l].numpy() for l in band} for j, c in C[t][v].items()} for v in ("G", "P")}
             for t in TASKS}
    sims = embed_sims({t: taxonomy(t) for t in TASKS})
    per, models = [], ("IIA", "IIA_comp", "GEOM", "GEOM_gamma", "EXT")
    rng = np.random.default_rng(11)
    for t in TASKS:
        for b, cl in fz["confirmation_bans"][t].items():
            delta = {l: dconf[t][b][l - 1].float().mean(0).numpy() for l in band}
            tax, P0, mask, preds, s = predict_all(fz, t, b, cl, delta, cents[t], sims[t])
            n = obs_counts(t, f"conf_{b}", tax)
            if n.sum() == 0:
                continue
            obs = n / n.sum()
            rec = dict(task=t, ban=b, banned=cl, n=int(n.sum()), observed={j: float(o) for j, o in zip(tax, obs) if o > 0},
                       s_j={j: float(v) for j, v in zip(tax, s)},
                       jsd={m: jsd2(preds[m], obs + 1e-12) for m in models},
                       loglik_per_sample={m: loglik(preds[m], n) / n.sum() for m in models if m != "IIA"},
                       predicted={m: {j: float(v) for j, v in zip(tax, preds[m]) if v > 0.005} for m in models})
            unb = [i for i, j in enumerate(tax) if j not in cl]
            gain_obs = obs - P0
            top_obs = tax[max(unb, key=lambda i: gain_obs[i])]
            rec["top_substitute_observed"] = top_obs
            rec["top_substitute_pred"] = {m: tax[max(unb, key=lambda i: preds[m][i] - P0[i])] for m in models}
            rec["top_substitute_hit"] = {m: rec["top_substitute_pred"][m] == top_obs for m in models}
            cells = [i for i in unb if abs(gain_obs[i]) >= 0.10]
            rec["sign_cells"] = [tax[i] for i in cells]
            rec["sign_correct"] = {m: int(sum(np.sign(preds[m][i] - P0[i]) == np.sign(gain_obs[i]) for i in cells))
                                   for m in models}
            # bootstrap over samples for JSD gain
            labs = np.repeat(np.arange(len(tax)), n.astype(int))
            bs = []
            for _ in range(1000):
                bb = np.bincount(rng.choice(labs, len(labs)), minlength=len(tax)) / len(labs)
                bs.append(1 - jsd2(preds["GEOM"], bb + 1e-12) / max(jsd2(preds["IIA"], bb + 1e-12), 1e-12))
            rec["gain_geom_vs_iia"] = 1 - rec["jsd"]["GEOM"] / max(rec["jsd"]["IIA"], 1e-12)
            rec["gain_geom_vs_iia_ci_samples"] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
            per.append(rec)
    if not per:
        return dict(status="no confirmation data")
    g = np.array([r["gain_geom_vs_iia"] for r in per])
    gb = [float(np.mean(g[rng.integers(0, len(g), len(g))])) for _ in range(5000)]
    th = fz["thresholds"]
    tot_cells = sum(len(r["sign_cells"]) for r in per)
    summ = dict(
        n_bans=len(per), mean_jsd={m: float(np.mean([r["jsd"][m] for r in per])) for m in
                                   ("IIA", "IIA_comp", "GEOM", "GEOM_gamma", "EXT")},
        mean_loglik_per_sample={m: float(np.mean([r["loglik_per_sample"][m] for r in per])) for m in
                                ("IIA_comp", "GEOM", "GEOM_gamma", "EXT")},
        mean_gain_geom_vs_iia=float(g.mean()), gain_ci_over_bans=[float(np.percentile(gb, 2.5)),
                                                                  float(np.percentile(gb, 97.5))],
        gain_geom_vs_ext=float(np.mean([1 - r["jsd"]["GEOM"] / max(r["jsd"]["EXT"], 1e-12) for r in per])),
        top_substitute_hit_rate={m: float(np.mean([r["top_substitute_hit"][m] for r in per])) for m in
                                 ("IIA", "IIA_comp", "GEOM", "GEOM_gamma", "EXT")},
        sign_accuracy={m: (sum(r["sign_correct"][m] for r in per) / tot_cells if tot_cells else None) for m in
                       ("IIA", "IIA_comp", "GEOM", "GEOM_gamma", "EXT")}, n_sign_cells=tot_cells)
    summ["C2a_jsd_gain_passes"] = bool(summ["mean_jsd"]["GEOM"] < summ["mean_jsd"]["IIA"] and
                                       summ["mean_gain_geom_vs_iia"] >= th["jsd_gain_min"] and
                                       summ["gain_ci_over_bans"][0] > 0)
    summ["C2a_beats_ext"] = bool(summ["mean_jsd"]["GEOM"] < summ["mean_jsd"]["EXT"])
    summ["C2b_top_substitute_passes"] = bool(summ["top_substitute_hit_rate"]["GEOM"] >= th["top_substitute_min"])
    return dict(per_ban=per, summary=summ)


def regularity(fz) -> dict:
    out = {}
    cells = []
    for t in TASKS:
        tax = taxonomy(t)
        pl = [r["label"] for r in placebo_rows(t)]
        blocks = [labels_of(t, f"placebo_b{k}") for k in range(3)]
        bans = {**{b: cl for b, cl in fz["screen_bans"][t].items()},
                **{f"conf_{b}": cl for b, cl in fz["confirmation_bans"][t].items()}}
        for bn, cl in bans.items():
            L = labels_of(t, bn)
            if not L:
                continue
            for j in tax:
                if j in cl or j in NONIDEA:
                    continue
                kp, npl = sum(x == j for x in pl), len(pl)
                if kp / max(npl, 1) < 0.05:
                    continue
                kb, nb = sum(x == j for x in L), len(L)
                p = float(fisher_exact([[kp, npl - kp], [kb, nb - kb]], alternative="greater")[1])
                sh = [np.mean([x == j for x in bl]) if bl else 0.0 for bl in blocks]
                cells.append(dict(task=t, ban=bn, idea=j, placebo_share=kp / npl, ban_share=kb / nb,
                                  change=kb / nb - kp / npl, p_drop=p, noise_floor=float(max(sh) - min(sh))))
    adj = holm([c["p_drop"] for c in cells]) if cells else []
    for c, a in zip(cells, adj):
        c["p_holm"] = a
        c["violation"] = bool(a < 0.01 and -c["change"] > c["noise_floor"])
    for t in TASKS:
        bans = sorted({c["ban"] for c in cells if c["task"] == t})
        out[t] = dict(n_bans=len(bans), bans_with_violation=sorted({c["ban"] for c in cells if c["task"] == t and
                                                                    c["violation"]}))
    out["cells"] = cells
    out["n_cells"] = len(cells)
    out["n_violations"] = sum(c["violation"] for c in cells)
    return out


def hill(labels, q):
    c = np.array(list(Counter(labels).values()), float)
    if c.sum() == 0:
        return float("nan")
    p = c / c.sum()
    if q == 0:
        return float(len(p))
    if q == 1:
        return float(math.exp(-(p * np.log(p)).sum()))
    return float(1 / (p ** q).sum()) ** (1 / (q - 1)) if q != 1 else None


def phrasings(task, setting, labels_by_seed) -> dict:
    """User question (a)/(b): ideas vs phrasings. Distinct opening 32-token prefixes per idea."""
    out = {}
    for g in read_jsonl(gens_path(GEMMA, task, setting)):
        lab = labels_by_seed.get(g["seed"])
        if lab is None:
            continue
        out.setdefault(lab, set()).add(tuple(g["output_token_ids"][:32]))
    return {k: len(v) for k, v in out.items()}


def temperature(fz) -> dict:
    out = {}
    for t in TASKS:
        cellsT = {}
        n = None
        for T in (0.3, 0.7, 1.0, 1.3):
            st = "baseline" if T == 0.7 else f"temp{T}"
            rows = load_scored(GEMMA, t, st)
            if T != 0.7:
                n = len(rows)
            cellsT[T] = rows
        n = n or 60
        cellsT[0.7] = [r for r in cellsT[0.7] if r["seed"] < n]
        top10 = load_scored(GEMMA, t, "temp1.0_top10")
        L = {T: [r["label"] for r in rows if r["label"] not in NONIDEA] for T, rows in cellsT.items()}
        if not all(L.values()):
            out[t] = dict(status="missing cells")
            continue
        c07 = Counter(L[0.7])
        mode = c07.most_common(1)[0][0]
        rank07 = [k for k, _ in c07.most_common()]
        c10 = Counter(L[1.0])
        ideas = [j for j in set().union(*[set(v) for v in L.values()]) if j != mode and c10.get(j, 0) / len(L[1.0]) >= 0.03]
        arr = {}
        xs = np.array([1 / T for T in (0.3, 0.7, 1.0, 1.3)])
        rng = np.random.default_rng(7)
        for j in ideas:
            ys = []
            for T in (0.3, 0.7, 1.0, 1.3):
                c = Counter(L[T])
                ys.append(math.log((c.get(j, 0) + 0.5) / (c.get(mode, 0) + 0.5)))
            ys = np.array(ys)
            sl, ic = np.polyfit(xs, ys, 1)
            r2 = 1 - ((ys - (sl * xs + ic)) ** 2).sum() / max(((ys - ys.mean()) ** 2).sum(), 1e-12)
            bs = []
            for _ in range(2000):
                yb = []
                for T in (0.3, 0.7, 1.0, 1.3):
                    labs = L[T]
                    p = Counter(labs)
                    keys = list(p)
                    draw = Counter(rng.choice(keys, len(labs), p=np.array([p[k] for k in keys]) / len(labs)))
                    yb.append(math.log((draw.get(j, 0) + 0.5) / (draw.get(mode, 0) + 0.5)))
                bs.append(np.polyfit(xs, yb, 1)[0])
            arr[j] = dict(y=ys.tolist(), slope=float(sl), slope_ci=[float(np.percentile(bs, 2.5)),
                                                                     float(np.percentile(bs, 97.5))], r2=float(r2))
        top3 = rank07[:3]
        rev = {}
        for T in (0.3, 1.0, 1.3):
            c = Counter(L[T])
            order = sorted(top3, key=lambda k: -c.get(k, 0))
            rev[str(T)] = dict(order=order, reversal=order != top3)
        lab_by_seed = {T: {r["seed"]: r["label"] for r in rows} for T, rows in cellsT.items()}
        out[t] = dict(
            n_per_T=n, mode=mode, counts={str(T): dict(Counter(L[T]).most_common()) for T in L},
            hill={str(T): {f"q{q}": hill(L[T], q) for q in (0, 1, 2)} for T in L},
            pass_rate={str(T): float(np.mean([r["oracle_pass"] for r in rows])) for T, rows in cellsT.items()},
            truncation={str(T): float(np.mean([r["hit_max"] for r in rows])) for T, rows in cellsT.items()},
            arrhenius=arr, arrhenius_note="4 temperature points: R^2 >= 0.85 is a weak test; read the slope CIs",
            top3_rank_reversals=rev, any_reversal=any(v["reversal"] for v in rev.values()),
            topk10_vs_none_T1=dict(distinct_ideas_top10=len(set(r["label"] for r in top10 if r["label"] not in NONIDEA)),
                                   distinct_ideas_none=len(set(L[1.0])), counts_top10=dict(Counter(
                                       r["label"] for r in top10).most_common()), n_top10=len(top10)),
            phrasings_per_idea={str(T): phrasings(t, "baseline" if T == 0.7 else f"temp{T}", lab_by_seed[T])
                                for T in cellsT},
            phrasings_per_idea_top10=phrasings(t, "temp1.0_top10", {r["seed"]: r["label"] for r in top10}))
    return out


def transplant(fz) -> dict:
    setup = json.loads((RESULTS / "transplant_setup.json").read_text())
    out = dict(setup=setup, tasks={})
    rng = np.random.default_rng(13)
    for t in TASKS:
        tax = taxonomy(t)
        C = {n: [r["label"] for r in load_scored(GEMMA, t, n)] for n in
             ("tr_placebo", "tr_ban", "tr_placebo_plusD", "tr_ban_minusD", "tr_ban_minusR0", "tr_placebo_plusR0",
              "tr_placebo_plusR1", "tr_placebo_plusR2")}
        if not all(C.values()):
            out["tasks"][t] = dict(status="missing cells", n={k: len(v) for k, v in C.items()})
            continue
        D = {k: dist(v, tax, pseudo=0.5) for k, v in C.items()}

        def rec(patched, src="tr_placebo", tgt="tr_ban", Dd=D):
            return 1 - jsd2(Dd[patched], Dd[tgt]) / max(jsd2(Dd[src], Dd[tgt]), 1e-12)

        def boot(fn):
            vals = []
            arrs = {k: np.array(v, dtype=object) for k, v in C.items()}
            for _ in range(2000):
                Db = {k: dist(list(a[rng.integers(0, len(a), len(a))]), tax, pseudo=0.5) for k, a in arrs.items()}
                vals.append(fn(Db))
            return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]
        r = dict(n={k: len(v) for k, v in C.items()}, counts={k: dict(Counter(v).most_common()) for k, v in C.items()},
                 jsd_placebo_ban=jsd2(D["tr_placebo"], D["tr_ban"]))
        r["recovery_D"] = rec("tr_placebo_plusD")
        r["recovery_D_ci"] = boot(lambda Db: 1 - jsd2(Db["tr_placebo_plusD"], Db["tr_ban"]) /
                                  max(jsd2(Db["tr_placebo"], Db["tr_ban"]), 1e-12))
        for k in range(3):
            r[f"recovery_R{k}"] = rec(f"tr_placebo_plusR{k}")
        r["restoration_minusD"] = 1 - jsd2(D["tr_ban_minusD"], D["tr_placebo"]) / max(jsd2(D["tr_ban"], D["tr_placebo"]), 1e-12)
        r["restoration_minusR0"] = 1 - jsd2(D["tr_ban_minusR0"], D["tr_placebo"]) / max(jsd2(D["tr_ban"], D["tr_placebo"]), 1e-12)
        r["restoration_minusD_ci"] = boot(lambda Db: 1 - jsd2(Db["tr_ban_minusD"], Db["tr_placebo"]) /
                                          max(jsd2(Db["tr_ban"], Db["tr_placebo"]), 1e-12))
        r["pass_rates"] = {n: float(np.mean([x["oracle_pass"] for x in load_scored(GEMMA, t, n)])) for n in C}
        r["C2c_passes"] = bool(r["recovery_D"] >= 0.5 and all(r[f"recovery_R{k}"] <= 0.15 for k in range(3)))
        out["tasks"][t] = r
    return out


def main() -> None:
    h = require_frozen(FROZEN)
    fz = json.loads(FROZEN.read_text())
    res = dict(frozen_sha256=h, frozen=dict(variant=fz["variant"], beta=fz["beta"], beta_gamma=fz["beta_gamma"],
                                            beta_e=fz["beta_e"], gamma=fz["gamma"], band=fz["band"],
                                            screen_jsd=fz["screen_jsd"], fits=fz["fits"]),
               screen=screen_summary(fz))
    if (RESULTS / "gemma_delta_h_confirm.pt").exists():
        res["confirmation"] = confirmation(fz)
    res["regularity"] = regularity(fz)
    write_json(RESULTS / "gemma_bans.json", res)
    logger.info(f"gemma bans: {json.dumps(res.get('confirmation', {}).get('summary', {}))[:1500]}")
    write_json(RESULTS / "gemma_temperature.json", temperature(fz))
    if (RESULTS / "transplant_setup.json").exists():
        tr = transplant(fz)
        write_json(RESULTS / "transplant.json", tr)
        logger.info(f"transplant: {json.dumps({t: {k: v for k, v in r.items() if k.startswith(('recovery', 'restoration', 'C2c'))} for t, r in tr['tasks'].items()})}")


if __name__ == "__main__":
    logger.catch(reraise=True)(main)()
