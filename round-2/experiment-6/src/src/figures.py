#!/usr/bin/env python3
"""Figures from the results JSONs (numbers only from results/*.json; every panel skips missing inputs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FIGS, RESULTS  # noqa: E402

plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False})
C_T, C_R, C_O = "#1f5fa8", "#9a9a9a", "#d2691e"


def load(n):
    p = RESULTS / n
    return json.loads(p.read_text()) if p.exists() else None


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGS / f"{name}.png", dpi=180)
    fig.savefig(FIGS / f"{name}.pdf")
    plt.close(fig)


def fig_selector(S):
    fig, axes = plt.subplots(2, 2, figsize=(8, 6))
    for col, t in enumerate(("T1", "T2")):
        d = S["tasks"].get(t)
        if not d:
            continue
        M, al = d["cells"], d["alphas"]
        for row, key, lab in ((0, "entropy_mm", "idea entropy (bits, Miller-Madow)"),
                              (1, "max_nonmode_share", "max non-mode share")):
            ax = axes[row, col]
            dose = d["dose_response_calibration"]
            xs = sorted(float(a) for a in dose)
            ax.plot([0] + xs, [M["baseline"][key]] + [dose[f"{a:.3g}"][key] for a in xs], "-", color=C_T, alpha=.35,
                    label="d_away calibration (n=30)")
            for tag in ("s1", "s2"):
                a = al[tag]
                for k in range(5):
                    m = M.get(f"rand{k}_{tag}", {})
                    if m.get("n"):
                        ax.plot(a, m[key], "_", color=C_R, ms=14, mew=1.2, label="random draw (5/strength)"
                                if (tag == "s1" and k == 0) else None)
                rv = [M[f"rand{k}_{tag}"][key] for k in range(5) if M.get(f"rand{k}_{tag}", {}).get("n")]
                if rv:
                    ax.plot(a, np.mean(rv), "s", color=C_R, ms=6, label="random draw mean" if tag == "s1" else None)
                for nm, mk in ((f"away_{tag}", "o"), (f"away_{tag}_redraw", "^")):
                    if M.get(nm, {}).get("n"):
                        ax.plot(a, M[nm][key], mk, color=C_T, ms=7, label=("targeted d_away" if mk == "o" else
                                                                           "targeted re-draw") if tag == "s1" else None)
                if tag == "s2" and M.get("off_s2", {}).get("n"):
                    ax.plot(a, M["off_s2"][key], "D", color=C_O, ms=6, label="off-target real vector")
            ax.axhline(M["baseline"][key], color="k", lw=.6, ls=":")
            ax.set_xlabel("steering strength alpha (x median residual norm)")
            ax.set_ylabel(lab)
            ax.set_title(f"Qwen {t}: {d['decision']['verdict']}")
            if row == 0 and col == 0:
                ax.legend(fontsize=6.5, frameon=False)
    save(fig, "fig_selector_vs_random_band")


def fig_offmenu(S):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    for ax, t in zip(axes, ("T1", "T2")):
        d = S["tasks"].get(t)
        if not d:
            continue
        c4 = d["c4"]["excl_builtin"]
        names, vals = [], []
        for T, v in c4["temperature"].items():
            names.append(f"T={T}")
            vals.append(v["k"] / max(v["n"], 1))
        for nm, v in c4["settings"].items():
            names.append(nm.replace("screen_", "vLLM ").replace("_s2", ""))
            vals.append(v["k"] / max(v["n"], 1))
        for x, cl in d["prompting_ceiling"].items():
            names.append(f"forced {x}")
            vals.append(cl["forced_prompt"]["correct_target_share"] or 0)
        ax.bar(range(len(vals)), vals, color=[C_R if n.startswith("T=") else C_O if n.startswith(("forced", "vLLM"))
                                              else C_T for n in names])
        ax.set_xticks(range(len(vals)), names, rotation=70, fontsize=6.5)
        ax.set_ylabel("off-menu AND correct share\n(Builtin excluded)")
        ax.set_title(f"Qwen {t}")
    save(fig, "fig_offmenu_correct")


def fig_reanalysis(A):
    per = A["claim3"]["per_setting"]
    fig, ax = plt.subplots(figsize=(6, 5))
    key = A["claim3"]["primary_spec"]
    for i, r in enumerate(per):
        v = r["results"][key]
        c = C_T if v["verdict"] == "beats" else C_O if v["verdict"] == "below" else C_R
        ax.plot(v["ci"], [i, i], color=c)
        ax.plot(v["diff"], i, "o", color=c, ms=4)
        old = r["results"].get("ia|H|iter1_pooled_draws")
        if old:
            ax.plot(old["diff"], i, "x", color="k", ms=4)
    ax.axvline(0, color="k", lw=.6)
    ax.set_yticks(range(len(per)), [f"{r['task']} {r['setting']}" for r in per], fontsize=6.5)
    ax.set_xlabel("targeted - draw-averaged random entropy (bits, MM, n-matched)\nx = iteration-1 pooled comparison")
    ax.set_title(f"Step A: {A['claim3']['verdict'][:60]}", fontsize=8)
    save(fig, "fig_stepA_claim3_forest")


def fig_gemma_bans(G):
    conf = G.get("confirmation", {})
    per = conf.get("per_ban") or []
    if not per:
        return
    fig, ax = plt.subplots(figsize=(7, 3.4))
    models = ("IIA", "IIA_comp", "EXT", "GEOM", "GEOM_gamma")
    w = 0.16
    for k, m in enumerate(models):
        ax.bar(np.arange(len(per)) + (k - 2) * w, [r["jsd"][m] for r in per], w, label=m)
    ax.set_xticks(range(len(per)), [f"{r['task']} {'+'.join(r['banned'])}" for r in per], rotation=60, fontsize=6.5)
    ax.set_ylabel("JSD(pred, observed) bits")
    ax.set_title("gemma held-out bans: frozen predictors")
    ax.legend(fontsize=6.5, frameon=False, ncol=3)
    save(fig, "fig_gemma_predictor_jsd")


def fig_temp(Tm):
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    for ax, t in zip(axes, ("T1", "T2")):
        d = Tm.get(t, {})
        if "arrhenius" not in d:
            continue
        xs = [1 / T for T in (0.3, 0.7, 1.0, 1.3)]
        for j, a in d["arrhenius"].items():
            ax.plot(xs, a["y"], "o-", label=f"{j} (slope {a['slope']:.2f}, R2 {a['r2']:.2f})")
        ax.set_xlabel("1/T")
        ax.set_ylabel(f"ln(share_j / share_{d['mode']})")
        ax.set_title(f"gemma {t}")
        ax.legend(fontsize=6.5, frameon=False)
    save(fig, "fig_gemma_arrhenius")


def fig_transplant(Tr):
    fig, ax = plt.subplots(figsize=(5, 3))
    labels, vals = [], []
    for t, r in Tr["tasks"].items():
        if "recovery_D" not in r:
            continue
        for k in ("recovery_D", "recovery_R0", "recovery_R1", "recovery_R2", "restoration_minusD",
                  "restoration_minusR0"):
            labels.append(f"{t} {k.replace('recovery_', 'rec ').replace('restoration_', 'rest ')}")
            vals.append(r[k])
    if not vals:
        return
    ax.bar(range(len(vals)), vals, color=[C_T if ("D" in l and "R" not in l.split()[-1]) else C_R for l in labels])
    ax.axhline(0.5, color="k", ls=":", lw=.6)
    ax.axhline(0.15, color=C_R, ls=":", lw=.6)
    ax.set_xticks(range(len(vals)), labels, rotation=70, fontsize=6.5)
    ax.set_ylabel("fraction of ban effect recovered")
    ax.set_title("gemma C4: Delta_h transplant vs random")
    save(fig, "fig_transplant")


def fig_audit(Au):
    items = Au.get("items") or []
    if not items:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, t in zip(axes, ("T1", "T2")):
        it = [x for x in items if x["task"] == t]
        labs = sorted({x["label"] for x in it} | {x["judge"] for x in it})
        M = np.zeros((len(labs), len(labs)))
        for x in it:
            M[labs.index(x["label"]), labs.index(x["judge"])] += 1
        ax.imshow(M, cmap="Blues")
        for i in range(len(labs)):
            for j in range(len(labs)):
                if M[i, j]:
                    ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=6)
        ax.set_xticks(range(len(labs)), labs, rotation=70, fontsize=6)
        ax.set_yticks(range(len(labs)), labs, fontsize=6)
        ax.set_xlabel("judge (gpt-4.1-mini)")
        ax.set_ylabel("rule classifier v1")
        k = Au["tasks"].get(t, {}).get("kappa")
        ax.set_title(f"gemma {t}: kappa={k:.2f}" if k is not None else t)
    save(fig, "fig_gemma_audit_confusion")


def main():
    S, A = load("selector_tables.json"), load("reanalysis_contract.json")
    G, Tm, Tr, Au = load("gemma_bans.json"), load("gemma_temperature.json"), load("transplant.json"), load("audit.json")
    for fn, arg in ((fig_selector, S), (fig_offmenu, S), (fig_reanalysis, A), (fig_gemma_bans, G), (fig_temp, Tm),
                    (fig_transplant, Tr), (fig_audit, Au)):
        if arg:
            try:
                fn(arg)
                print("ok", fn.__name__)
            except (KeyError, TypeError, ValueError, IndexError) as e:
                print("skip", fn.__name__, repr(e)[:200])
    try:
        fig_centroid_map()
        print("ok fig_centroid_map")
    except (KeyError, OSError, ValueError, NameError) as e:
        print("skip fig_centroid_map", repr(e)[:200])




def fig_centroid_map():
    """PCA of Qwen commitment-window activations (band middle layer): samples, idea centroids sized by count,
    forced off-menu centroids, and the d_away direction projected into the plane."""
    import torch
    from sklearn.decomposition import PCA
    from common import ACTS
    V = torch.load(RESULTS / "qwen_vectors.pt", weights_only=False)
    l = V["band"][1]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, t in zip(axes, ("T1", "T2")):
        Xs, Ys = [], []
        for name in ("ba_baseline", "hf_baseline"):
            p = ACTS / f"qwen_{t}_{name}.npz"
            if p.exists():
                z = np.load(p)
                Xs.append(z["window"][:, l - 1].astype(np.float32))
                Ys.append(z["labels"])
        F = {}
        for p in sorted(ACTS.glob(f"qwen_{t}_forced_*.npz")):
            z = np.load(p)
            if len(z["ids"]):
                F[p.stem.split("forced_")[1]] = z["window"][:, l - 1].astype(np.float32)
        if not Xs:
            continue
        X, Y = np.concatenate(Xs), np.concatenate(Ys)
        pca = PCA(2, random_state=0).fit(np.concatenate([X] + list(F.values())))
        P = pca.transform(X)
        ideas = [k for k, _ in sorted(((k, (Y == k).sum()) for k in set(Y)), key=lambda kv: -kv[1])]
        cmap = plt.get_cmap("tab10")
        for i, k in enumerate(ideas):
            m = Y == k
            ax.scatter(P[m, 0], P[m, 1], s=4, alpha=.25, color=cmap(i % 10))
            c = P[m].mean(0)
            ax.scatter(*c, s=30 + 400 * m.mean(), color=cmap(i % 10), edgecolor="k", label=f"{k} ({m.sum()})")
        for j, (k, A) in enumerate(F.items()):
            c = pca.transform(A).mean(0)
            ax.scatter(*c, s=90, marker="*", color="k")
            ax.annotate(f"forced {k}", c, fontsize=6.5)
        d = V["d_away"][t][l].numpy()
        o = P[Y == ideas[0]].mean(0)
        v2 = pca.components_ @ d
        sc = 0.5 * np.abs(P).max() / (np.linalg.norm(v2) + 1e-9)
        ax.annotate("", o + v2 * sc, o, arrowprops=dict(arrowstyle="->", color="k", lw=1.5))
        ax.set_title(f"Qwen {t}: window activations, layer {l} (PCA)\narrow = d_away; size = baseline count")
        ax.legend(fontsize=6, frameon=False, loc="best")
    save(fig, "fig_centroid_map")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "map":
        fig_centroid_map()
    else:
        main()
