#!/usr/bin/env python3
"""STEP 6c: score claim C3 on the fresh seed strings against the FROZEN predictions (results/frozen_c3_seeds.json).

C3a (T1, T2): |predicted - observed greedy flip rate| <= 0.10 (primary predictor as frozen by the gate);
C3b (T3): observed greedy flip rate < 5%. C3 PASS iff C3a on T1 and T2 and C3b on T3.
Also: per-string AUROC of the readout score, T=0.7 non-mode rate seeded vs unseeded (fresh n=300), between-string
heterogeneity vs within-string multinomial noise (chi-square + permutation over string labels, ICC), and
'does seeding diversify?' (entropy, E[S_10]; char vs word strings). The same scoring on the screen data is in-sample.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from loguru import logger
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (LABELS_PATH, RESULTS, entropy_bits, rarefied_richness, read_jsonl, save_json,  # noqa: E402
                    setup_logging, wilson)


def auroc(scores, y) -> float | None:
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y, int)
    if len(set(y)) < 2:
        return None
    return float(roc_auc_score(y, scores))


def heterogeneity(per_string: dict[str, list[str]], n_perm: int = 5000, seed: int = 0) -> dict:
    strings = sorted(per_string)
    labs = sorted({x for v in per_string.values() for x in v})
    tab = np.array([[per_string[s].count(lab) for lab in labs] for s in strings], float)

    def chi(t):
        exp = t.sum(1, keepdims=True) * t.sum(0, keepdims=True) / t.sum()
        m = exp > 0
        return float((((t - exp) ** 2)[m] / exp[m]).sum())
    obs = chi(tab)
    flat = np.array([x for s in strings for x in per_string[s]])
    sizes = [len(per_string[s]) for s in strings]
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n_perm):
        rng.shuffle(flat)
        pos, t = 0, np.zeros_like(tab)
        for i, k in enumerate(sizes):
            for x in flat[pos:pos + k]:
                t[i, labs.index(x)] += 1
            pos += k
        ge += chi(t) >= obs - 1e-9
    # ICC of the modal-idea indicator (one-way ANOVA)
    mode = Counter(flat.tolist()).most_common(1)[0][0]
    groups = [np.array([x == mode for x in per_string[s]], float) for s in strings]
    k = np.mean(sizes)
    grand = np.mean(np.concatenate(groups))
    msb = sum(len(g) * (g.mean() - grand) ** 2 for g in groups) / (len(groups) - 1)
    msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (sum(sizes) - len(groups))
    icc = (msb - msw) / (msb + (k - 1) * msw) if (msb + (k - 1) * msw) > 0 else None
    return dict(chi2=obs, dof=(len(strings) - 1) * (len(labs) - 1), perm_p=(ge + 1) / (n_perm + 1), icc_mode=icc,
                mode=mode, n_strings=len(strings), n_per_string=k)


def diversify(seeded_by_string: dict[str, list[str]], unseeded: list[str], seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    pooled = [x for v in seeded_by_string.values() for x in v]
    hs, hu = entropy_bits(Counter(pooled).values()), entropy_bits(Counter(unseeded).values())
    keys = list(seeded_by_string)
    U = np.array(unseeded)
    diffs = []
    for _ in range(2000):
        ks = rng.choice(keys, len(keys))
        ps = [x for k in ks for x in seeded_by_string[k]]
        diffs.append(entropy_bits(Counter(ps).values()) - entropy_bits(Counter(U[rng.integers(0, len(U), len(U))]
                                                                              .tolist()).values()))
    return dict(n_seeded=len(pooled), n_unseeded=len(unseeded), H_seeded=hs, H_unseeded=hu, diff=hs - hu,
                diff_ci=np.quantile(diffs, [.025, .975]).tolist(), ES10_seeded=rarefied_richness(
                    Counter(pooled).values(), 10), ES10_unseeded=rarefied_richness(Counter(unseeded).values(), 10),
                counts_seeded=dict(Counter(pooled).most_common()), counts_unseeded=dict(Counter(unseeded).most_common()))


@logger.catch(reraise=True)
def main() -> None:
    setup_logging("s6c_seed_score")
    from freeze import verify
    fz = verify(RESULTS / "frozen_c3_seeds.json")["body"]
    lab = read_jsonl(LABELS_PATH)
    out = dict(frozen_sha256=None, tasks={}, screen_in_sample={})
    out["frozen_sha256"] = __import__("json").loads((RESULTS / "frozen_c3_seeds.json").read_text())["sha256"]
    kinds = {s["string"]: s["kind"] for s in fz["fresh_strings"]}
    verdict = {}
    for t in ("T1", "T2", "T3"):
        ft = fz["tasks"][t]
        ug = ft["engine"]["unseeded_greedy_label"]
        g = {r["seed_string"]: r["label"] for r in lab if r["source"] == "seedsfresh" and r["task"] == t
             and r["cond"] == "seed_greedy"}
        s7 = defaultdict(list)
        for r in lab:
            if r["source"] == "seedsfresh" and r["task"] == t and r["cond"] == "seed_t07":
                s7[r["seed_string"]].append(r["label"])
        if not g:
            logger.warning(f"{t}: no fresh seeded rows yet")
            continue
        unseeded07 = [r["label"] for r in lab if r["source"] == "redraw" and r["task"] == t and r["T"] == 0.7
                      and r["topk"] == -1 and r["cond"] in ("grid", "extra07")]
        mode07 = Counter(unseeded07).most_common(1)[0][0]
        per = []
        pr = ft["predictions"]["readout"]["per_string"]
        for s, obs in g.items():
            p = pr[s]
            per.append(dict(seed_string=s, seed_kind=kinds[s], observed_greedy=obs, observed_flip=obs != ug,
                            pred_greedy_idea=p["pred_greedy_idea"], p_flip=p["p_flip"], shift_ref=p["shift_ref"],
                            t07_labels=s7.get(s, []),
                            t07_nonmode_obs=float(np.mean([x != mode07 for x in s7.get(s, [])])) if s7.get(s) else None,
                            pred_t07_nonmode=p["pred_t07_nonmode"]))
        n = len(per)
        k = sum(x["observed_flip"] for x in per)
        fw = wilson(k, n)
        prim = ft["predictions"]["primary"]
        pred = ft["predictions"]["primary_task_pred_greedy_flip"]
        pred_ro = ft["predictions"]["readout"]["task_pred_greedy_flip"]
        pred_bh = ft["predictions"]["behavioural"]["task_pred_greedy_flip"]
        res = dict(unseeded_greedy_label=ug, unseeded_greedy_repeats=ft["engine"]["unseeded_greedy_repeats"],
                   n_strings=n, observed_flips=k, observed_flip_rate=fw[0], observed_flip_ci=[fw[1], fw[2]],
                   primary_predictor=prim, predicted_flip_rate=pred, abs_error=abs(pred - fw[0]),
                   predicted_readout=pred_ro, predicted_behavioural=pred_bh,
                   abs_error_readout=abs(pred_ro - fw[0]), abs_error_behavioural=abs(pred_bh - fw[0]),
                   baseline_seeds_inert_pred=0.0, abs_error_baseline_inert=fw[0],
                   readout_idea_accuracy=float(np.mean([x["pred_greedy_idea"] == x["observed_greedy"] for x in per])),
                   auroc_readout_shift=auroc([-x["shift_ref"] for x in per], [x["observed_flip"] for x in per]),
                   greedy_counts=dict(Counter(g.values()).most_common()),
                   by_kind={kd: dict(n=sum(1 for x in per if x["seed_kind"] == kd),
                                     flip_rate=float(np.mean([x["observed_flip"] for x in per
                                                              if x["seed_kind"] == kd])))
                            for kd in ("char", "word")})
        seeded_nonmode = float(np.mean([x != mode07 for v in s7.values() for x in v]))
        res["t07"] = dict(mode_unseeded=mode07, nonmode_unseeded=float(np.mean([x != mode07 for x in unseeded07])),
                          n_unseeded=len(unseeded07), nonmode_seeded=seeded_nonmode,
                          predicted_nonmode_readout=ft["predictions"]["readout"]["task_pred_t07_nonmode"],
                          predicted_nonmode_behavioural=ft["predictions"]["behavioural"]["task_pred_t07_nonmode"],
                          chi2_seeded_vs_unseeded=None)
        cs, cu = Counter(x for v in s7.values() for x in v), Counter(unseeded07)
        keys = sorted(set(cs) | set(cu))
        tab = np.array([[cs.get(kk, 0) for kk in keys], [cu.get(kk, 0) for kk in keys]])
        tab = tab[:, tab.sum(0) > 0]
        if tab.shape[1] > 1:
            c2, pp, dof, _ = stats.chi2_contingency(tab)
            res["t07"]["chi2_seeded_vs_unseeded"] = dict(chi2=float(c2), dof=int(dof), p=float(pp))
        res["heterogeneity"] = heterogeneity(dict(s7))
        res["diversify"] = dict(all=diversify(dict(s7), unseeded07),
                                char=diversify({s: v for s, v in s7.items() if kinds[s] == "char"}, unseeded07),
                                word=diversify({s: v for s, v in s7.items() if kinds[s] == "word"}, unseeded07))
        res["per_string"] = per
        if t in ("T1", "T2"):
            verdict[f"C3a_{t}"] = abs(pred - fw[0]) <= 0.10
        else:
            verdict["C3b_T3"] = fw[0] < 0.05
        out["tasks"][t] = res
        logger.info(f"{t}: greedy flip obs {k}/{n}={fw[0]:.3f} pred({prim})={pred:.3f} ro={pred_ro:.3f} "
                    f"beh={pred_bh:.3f}; t07 nonmode seeded={seeded_nonmode:.3f} vs unseeded "
                    f"{res['t07']['nonmode_unseeded']:.3f}; heterogeneity p={res['heterogeneity']['perm_p']:.4f}")
        # screen in-sample
        sg = {r["seed_string"]: r["label"] for r in lab if r["source"] == "seeds" and r["task"] == t
              and r["cond"] == "seed_greedy"}
        ugs = [r["label"] for r in lab if r["source"] == "grid" and r["task"] == t and r["cond"] == "greedy"][0]
        sfl = [x != ugs for x in sg.values()]
        w = wilson(sum(sfl), len(sfl))
        out["screen_in_sample"][t] = dict(unseeded_greedy=ugs, flip_rate=w[0], ci=[w[1], w[2]],
                                          greedy_counts=dict(Counter(sg.values())),
                                          pred_behavioural_fit=ft["behavioural_screen"],
                                          pred_readout_pop=ft["readout_screen"]["pop_pred_greedy_flip"])
    if len(verdict) == 3:
        verdict["C3_PASS"] = bool(verdict["C3a_T1"] and verdict["C3a_T2"] and verdict["C3b_T3"])
    out["verdict"] = verdict
    out["summary"] = {t: {k: v for k, v in r.items() if k not in ("per_string", "diversify", "heterogeneity")}
                      | dict(heterogeneity_p=r["heterogeneity"]["perm_p"], icc=r["heterogeneity"]["icc_mode"],
                             entropy_diff=r["diversify"]["all"]["diff"], entropy_diff_ci=r["diversify"]["all"]["diff_ci"])
                      for t, r in out["tasks"].items()}
    save_json(RESULTS / "c3_scoring.json", out)
    logger.info(f"C3 verdict: {verdict}")


if __name__ == "__main__":
    main()
