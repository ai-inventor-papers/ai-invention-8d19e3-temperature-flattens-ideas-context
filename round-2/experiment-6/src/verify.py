#!/usr/bin/env python3
"""Independent re-derivation of headline numbers from the RAW scored jsonl files (pandas + scipy; no import of the
pipeline's statistics code). Also runs each test on placebo / shuffled input and checks that it FAILS there.

Writes results/verify.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import entropy

ROOT = Path(__file__).resolve().parent
SC = ROOT / "data" / "scored"
RES = ROOT / "results"
MODE = {"T1": "BFS", "T2": "Bubble"}
MENU = {"T1": {"BFS", "DFS", "A_star", "Dijkstra"}, "T2": {"Bubble", "Quick", "Merge", "Selection"}}


def df(model, task, setting) -> pd.DataFrame:
    p = SC / model / task / f"{setting}.jsonl"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_json(p, lines=True)
    return d.drop_duplicates("seed")


def H(labels: pd.Series) -> float:
    v = labels[labels != "Unparseable"].value_counts().to_numpy(float)
    return float(entropy(v, base=2)) if v.sum() else float("nan")


def kl_u(labels: pd.Series, U: list[str]) -> float:
    lab = labels[labels != "Unparseable"].map(lambda x: x if x in U else "Other")
    p = lab.value_counts().reindex(U, fill_value=0).to_numpy(float)
    p = p / p.sum()
    return float(entropy(p, np.full(len(U), 1 / len(U)), base=2))


def jsd(p, q) -> float:
    return float(jensenshannon(p, q, base=2) ** 2)


def boot_beats(t_lab, draws, rng, B=2000):
    """Hierarchical bootstrap re-implemented: diff = H(t*) - mean_k H(draw_{k*}*)."""
    t = t_lab[t_lab != "Unparseable"].to_numpy()
    D = [d[d != "Unparseable"].to_numpy() for d in draws]
    vals = []
    for _ in range(B):
        ht = entropy(pd.Series(rng.choice(t, len(t))).value_counts().to_numpy(float), base=2)
        ks = rng.integers(0, len(D), len(D))
        hr = np.mean([entropy(pd.Series(rng.choice(D[k], len(D[k]))).value_counts().to_numpy(float), base=2)
                      for k in ks])
        vals.append(ht - hr)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def main():
    out = {}
    rng = np.random.default_rng(99)
    sel = json.loads((RES / "selector_tables.json").read_text()) if (RES / "selector_tables.json").exists() else None
    if sel:
        for t in ("T1", "T2"):
            st = sel["tasks"][t]
            U = st["support_U"]
            base = df("qwen", t, "baseline")
            base = base[base.seed < 150]
            r = {}
            for arm, (n1, n2) in {"main": ("away_s1", "away_s2"), "redraw": ("away_s1_redraw", "away_s2_redraw")}.items():
                a1, a2 = df("qwen", t, n1), df("qwen", t, n2)
                k0, k1, k2 = kl_u(base.label, U), kl_u(a1.label, U), kl_u(a2.label, U)
                vc = a2.label.value_counts() / len(a2)
                nm = vc.drop(MODE[t], errors="ignore")
                top, share = (nm.idxmax(), float(nm.max())) if len(nm) else (None, 0.0)
                preds = set(st["predicted_gainers"])
                dec = ("SELECT" if (share >= 0.5 and top in preds and k2 > k1) else
                       "FLATTEN" if (k0 > k1 > k2 and share < 0.5) else "MIXED")
                r[arm] = dict(kl=[k0, k1, k2], top_nonmode=top, share=share, decision=dec,
                              pipeline_decision=st["decision"][arm], match=dec == st["decision"][arm])
            # entropy vs draw-mean random at s2 (point + independent bootstrap) and placebo version
            tgt = df("qwen", t, "away_s2").label
            draws = [df("qwen", t, f"rand{k}_s2").label for k in range(5)]
            draws = [d for d in draws if len(d)]
            if draws:
                diff = H(tgt) - np.mean([H(d) for d in draws])
                lo, hi = boot_beats(tgt, draws, rng)
                pipe = st["vs_random"].get("main@s2", {}).get("H", {})
                # placebo: random draw 0 treated as 'targeted' vs the other 4 draws -> should NOT beat
                plo, phi = boot_beats(draws[0], draws[1:], rng) if len(draws) > 2 else (None, None)
                # shuffled: pool targeted+random labels, re-split at random -> should NOT beat
                pool = pd.concat([tgt] + draws).sample(frac=1, random_state=1).reset_index(drop=True)
                sizes = [len(tgt)] + [len(d) for d in draws]
                cuts = np.cumsum([0] + sizes)
                parts = [pool.iloc[cuts[i]:cuts[i + 1]] for i in range(len(sizes))]
                slo, shi = boot_beats(parts[0], parts[1:], rng)
                r["entropy_vs_random_s2"] = dict(diff=diff, ci=[lo, hi], pipeline_diff=pipe.get("diff"),
                                                 pipeline_ci=pipe.get("ci"),
                                                 diff_matches=abs(diff - pipe.get("diff", np.nan)) < 1e-6,
                                                 placebo_draw0_vs_rest_ci=[plo, phi],
                                                 placebo_fails=bool(plo is not None and not (plo > 0)),
                                                 shuffled_ci=[slo, shi], shuffled_fails=bool(not (slo > 0)))
            out[f"qwen_{t}"] = r
    gb = RES / "gemma_bans.json"
    if gb.exists():
        G = json.loads(gb.read_text())
        per = G.get("confirmation", {}).get("per_ban") or []
        rows = []
        for rec in per:
            t, b = rec["task"], rec["ban"]
            d = df("gemma", t, f"conf_{b}")
            tax = sorted(set(rec["predicted"]["IIA"]) | set(rec["predicted"]["GEOM"]) | set(rec["observed"]) |
                         set(d.label.unique()) - {"Unparseable"})
            obs = d.label[d.label != "Unparseable"].value_counts().reindex(tax, fill_value=0).to_numpy(float)
            obs = obs / obs.sum()
            pi = np.array([rec["predicted"]["IIA"].get(j, 0.0) for j in tax])
            pg = np.array([rec["predicted"]["GEOM"].get(j, 0.0) for j in tax])
            ji, jg = jsd(pi / pi.sum(), obs), jsd(pg / pg.sum(), obs)
            # placebo: predict with the observed distribution of ANOTHER (unrelated) confirmation ban
            rows.append(dict(task=t, ban=b, jsd_iia=ji, jsd_geom=jg, gain=1 - jg / max(ji, 1e-12),
                             pipeline_gain=rec["gain_geom_vs_iia"]))
        if rows:
            R = pd.DataFrame(rows)
            # placebo test: shuffle which ban's GEOM prediction is scored against which observation
            perm = []
            for _ in range(200):
                idx = rng.permutation(len(per))
                g = []
                for i, rec in enumerate(per):
                    other = per[idx[i]]
                    if other["task"] != rec["task"]:
                        continue
                    tax = sorted(set(rec["observed"]) | set(other["predicted"]["GEOM"]) | set(rec["predicted"]["IIA"]))
                    obs = np.array([rec["observed"].get(j, 0.0) for j in tax])
                    pg = np.array([other["predicted"]["GEOM"].get(j, 0.0) for j in tax])
                    pi = np.array([rec["predicted"]["IIA"].get(j, 0.0) for j in tax])
                    g.append(1 - jsd(pg / pg.sum(), obs / obs.sum()) / max(jsd(pi / pi.sum(), obs / obs.sum()), 1e-12))
                if g:
                    perm.append(np.mean(g))
            out["gemma_confirmation"] = dict(per_ban=rows, mean_gain=float(R.gain.mean()),
                                             pipeline_mean_gain=G["confirmation"]["summary"]["mean_gain_geom_vs_iia"],
                                             mean_jsd_iia=float(R.jsd_iia.mean()), mean_jsd_geom=float(R.jsd_geom.mean()),
                                             placebo_mismatched_ban_gain_mean=float(np.mean(perm)) if perm else None,
                                             placebo_gain_quantile_of_observed=float(np.mean(np.array(perm) >= R.gain.mean()))
                                             if perm else None)

    # regularity test re-implemented + placebo: each placebo block treated as a 'ban' vs the other two blocks
    from scipy.stats import fisher_exact
    if gb.exists():
        G = json.loads(gb.read_text())
        reg = {}
        for t in ("T1", "T2"):
            blocks = [df("gemma", t, f"placebo_b{k}").label for k in range(3)]
            if not all(len(b) for b in blocks):
                continue
            pv = []
            for k in range(3):
                ref = pd.concat([blocks[j] for j in range(3) if j != k])
                for idea, sh in (ref.value_counts() / len(ref)).items():
                    if sh < 0.05 or idea == "Unparseable":
                        continue
                    a, n1 = int((ref == idea).sum()), len(ref)
                    b, n2 = int((blocks[k] == idea).sum()), len(blocks[k])
                    pv.append(fisher_exact([[a, n1 - a], [b, n2 - b]], alternative="greater")[1])
            m = len(pv)
            holm_min = min(min(1.0, (m - r) * x) for r, x in enumerate(sorted(pv))) if pv else 1.0
            reg[t] = dict(n_placebo_cells=m, min_holm_p=holm_min, placebo_violations=int(holm_min < 0.01))
        reg["pipeline_n_violations"] = G["regularity"]["n_violations"]
        reg["pipeline_n_cells"] = G["regularity"]["n_cells"]
        out["regularity_placebo"] = reg
    tr = RES / "transplant.json"
    if tr.exists():
        T = json.loads(tr.read_text())
        r = {}
        for t in ("T1", "T2"):
            cells = {n: df("gemma", t, n).label for n in ("tr_placebo", "tr_ban", "tr_placebo_plusD", "tr_placebo_plusR0")}
            if not all(len(v) for v in cells.values()):
                continue
            tax = sorted(set().union(*[set(v) for v in cells.values()]))
            P = {k: (v.value_counts().reindex(tax, fill_value=0).to_numpy(float) + 0.5) for k, v in cells.items()}
            P = {k: v / v.sum() for k, v in P.items()}
            rec_d = 1 - jsd(P["tr_placebo_plusD"], P["tr_ban"]) / jsd(P["tr_placebo"], P["tr_ban"])
            rec_r = 1 - jsd(P["tr_placebo_plusR0"], P["tr_ban"]) / jsd(P["tr_placebo"], P["tr_ban"])
            r[t] = dict(recovery_D=rec_d, recovery_R0=rec_r,
                        pipeline_recovery_D=T["tasks"].get(t, {}).get("recovery_D"),
                        note="taxonomy = observed labels only (pipeline uses the full taxonomy with 0.5 pseudo-counts); "
                             "small differences are expected")
        out["transplant"] = r
    ra = RES / "reanalysis_contract.json"
    if ra.exists():
        A = json.loads(ra.read_text())
        rec = A["claim3"]["per_setting"][0]
        import os
        IA = Path(os.environ.get("AII_INFLUENCE_ARM_DIR", ROOT.parents[2] / "round-1" / "." / "experiment-3/src"))
        if IA.exists():
            t = pd.read_json(IA / "scored" / rec["task"] / f"{rec['setting']}.jsonl", lines=True).drop_duplicates("idx")
            t = t[(t.idx < 75) & ~t.label.isin(["no_code", "syntax_error"])]
            hs = []
            for d in rec["draws"]:
                r_ = pd.read_json(IA / "scored" / rec["task"] / f"{d}.jsonl", lines=True).drop_duplicates("idx")
                r_ = r_[~r_.label.isin(["no_code", "syntax_error"])]
                k = r_.label.nunique()
                hs.append(entropy(r_.label.value_counts().to_numpy(float), base=2) + (k - 1) / (2 * len(r_) * np.log(2)))
            k = t.label.nunique()
            ht = entropy(t.label.value_counts().to_numpy(float), base=2) + (k - 1) / (2 * len(t) * np.log(2))
            out["stepA_first_setting"] = dict(setting=f"{rec['task']}/{rec['setting']}", diff=float(ht - np.mean(hs)),
                                              pipeline=rec["results"]["ia|H_mm|nmatched_seeds0_74"]["diff"])
    (RES / "verify.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float)[:4000])


if __name__ == "__main__":
    main()
