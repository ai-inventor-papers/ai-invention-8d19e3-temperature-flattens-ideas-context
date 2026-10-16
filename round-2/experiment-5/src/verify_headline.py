#!/usr/bin/env python3
"""T9 final integrity: recompute the headline numbers from the saved jsonl (labels + frozen predictions) with an
independent implementation and assert equality with results/*.json."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from scipy.stats import fisher_exact

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results"


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def jsd(p: list[float], q: list[float]) -> float:
    s = 0.0
    for a, b in zip(p, q):
        m = (a + b) / 2
        if a > 0:
            s += 0.5 * a * math.log2(a / m)
        if b > 0:
            s += 0.5 * b * math.log2(b / m)
    return s


def dist(labels: list[str], K: list[str]) -> list[float]:
    c = Counter(labels)
    n = sum(c[k] for k in K)
    return [c[k] / n for k in K]


def main() -> None:
    fp = json.loads((RES / "frozen_predictions.json").read_text())
    sc = json.loads((RES / "predictor_scores_conf.json").read_text())
    jA, jB = [], []
    for t, td in fp["tasks"].items():
        K = td["classes"]
        for cond, cd in td["conditions"].items():
            if not cd["banned"] or cond == "cross":
                continue
            p = ROOT / "data" / "conf" / "labels" / t / f"{cond}.jsonl"
            obs = dist([r["label"] for r in jl(p)], K)
            jA.append(jsd(cd["pred"]["A"], obs))
            jB.append(jsd(cd["pred"]["B"], obs))
    g = sc["c2b"]["T1T2T3_bans"]
    assert abs(sum(jA) / len(jA) - g["A"]["mean_jsd"]) < 1e-9, (sum(jA) / len(jA), g["A"]["mean_jsd"])
    assert abs(sum(jB) / len(jB) - g["B"]["mean_jsd"]) < 1e-9
    print(f"mean JSD A={sum(jA) / len(jA):.6f} B={sum(jB) / len(jB):.6f} over {len(jA)} T1-T3 bans: MATCH")
    reg = json.loads((RES / "regularity.json").read_text())
    n_le = 0
    for c in reg["c2a"]["cells"]:
        p = fisher_exact([[c["ban_count"], c["n_ban"] - c["ban_count"]],
                          [c["placebo_count"], c["n_placebo"] - c["placebo_count"]]], alternative="less")[1]
        assert abs(p - c["p"]) < 1e-12
        n_le += c["violation"]
    assert n_le == reg["c2a"]["n_violations"]
    print(f"C2a: {n_le} violating cells over {len(reg['c2a']['cells'])} (Fisher p recomputed): MATCH")
    # shuffled-input check: pool each ban's samples with the 300 placebo samples, reassign at random (labels exchangeable
    # under the null) and rerun the same one-sided Fisher + Holm + noise-floor rule; it must (almost) never fire.
    import random
    rng = random.Random(0)
    nf = json.loads((RES / "predictor_scores_conf.json").read_text())["noise_floor"]
    viol_shuf = []
    for rep in range(20):
        ps, meta = [], []
        for t, cond in sorted({(c["task"], c["cond"]) for c in reg["c2a"]["cells"]}):
            ban = [r["label"] for r in jl(ROOT / "data" / "conf" / "labels" / t / f"{cond}.jsonl")]
            pl = [r["label"] for b in ("placebo_b1", "placebo_b2", "placebo_b3")
                  for r in jl(ROOT / "data" / "conf" / "labels" / t / f"{b}.jsonl")]
            pool = ban + pl
            rng.shuffle(pool)
            sb, sp = Counter(pool[:len(ban)]), Counter(pool[len(ban):])
            for c in reg["c2a"]["cells"]:
                if c["task"] == t and c["cond"] == cond:
                    i = c["idea"]
                    ps.append(fisher_exact([[sb[i], len(ban) - sb[i]], [sp[i], len(pl) - sp[i]]], alternative="less")[1])
                    meta.append((sp[i] / len(pl) - sb[i] / len(ban), nf[t][i]))
        order = sorted(range(len(ps)), key=lambda k: ps[k])
        run, nv = 0.0, 0
        for r_, k in enumerate(order):
            run = max(run, (len(ps) - r_) * ps[k])
            if min(1.0, run) < 0.01 and meta[k][0] > meta[k][1]:
                nv += 1
        viol_shuf.append(nv)
    print(f"C2a on shuffled ban/placebo labels (20 reps): violations per rep = {viol_shuf} (real data: {n_le})")
    assert sum(viol_shuf) <= 2, "regularity test fires on exchangeable (shuffled) labels"
    tp = RES / "transplant.json"
    if tp.exists():
        tr = json.loads(tp.read_text())
        Rs = []
        for key, e in tr["bans"].items():
            t, b = key.split("/")
            K = list(json.loads((RES / "frozen_predictions.json").read_text())["tasks"][t]["classes"])
            lab = lambda c, bb=b: [r["label"] for r in jl(ROOT / "data" / "transplant_labels" / t / bb / f"{c}.jsonl")]  # noqa: E731
            pl = [r["label"] for r in jl(ROOT / "data" / "transplant_labels" / t / "placebo" / "REF_placebo.jsonl")]
            rb, x = lab("REF_ban"), lab("TRANSPLANT")
            R = 1 - jsd(dist(x, K), dist(rb, K)) / jsd(dist(pl, K), dist(rb, K))
            assert abs(R - e["TRANSPLANT"]["R"]) < 1e-9
            Rs.append(R)
        assert abs(sum(Rs) / len(Rs) - tr["summary"]["mean_R_transplant"]) < 1e-9
        print(f"mean transplant recovery {sum(Rs) / len(Rs):.4f} over {len(Rs)} bans: MATCH")
    # sign accuracy of B and IIA over |change|>=10pp cells (all confirmation bans incl. T4, excluding cross-domain)
    fz = json.loads((RES / "frozen_predictors.json").read_text())
    tasks = dict(fp["tasks"])
    f4 = json.loads((RES / "frozen_predictions_T4.json").read_text())
    tasks["T4"] = f4
    q_by = {t: __import__("numpy").load(RES / f"centroids_{t}.npz")["q"].tolist() for t in tasks}
    hits = {"A": [], "B": []}
    for t, td in tasks.items():
        K = td["classes"]
        c0 = td["P0_conf_counts"]
        n0 = sum(c0)
        for cond, cd in td["conditions"].items():
            if not cd["banned"] or cond == "cross":
                continue
            obs = dist([r["label"] for r in jl(ROOT / "data" / "conf" / "labels" / t / f"{cond}.jsonl")], K)
            for j, k in enumerate(K):
                if k in cd["banned"] or abs(obs[j] - c0[j] / n0) < 0.10:
                    continue
                pt0 = (c0[j] + fz["eps"] * q_by[t][j]) / (n0 + fz["eps"])
                for m in hits:
                    hits[m].append((obs[j] - c0[j] / n0 > 0) == (cd["pred"][m][j] - pt0 > 0))
    sc_reg = reg["sign"]
    for m in hits:
        acc = sum(hits[m]) / len(hits[m])
        assert abs(acc - sc_reg[m]["sign_acc"]) < 1e-9, (m, acc, sc_reg[m]["sign_acc"])
        print(f"sign acc {m} = {acc:.4f} over {len(hits[m])} cells: MATCH")
    print("verify_headline: ALL MATCH")


if __name__ == "__main__":
    main()
