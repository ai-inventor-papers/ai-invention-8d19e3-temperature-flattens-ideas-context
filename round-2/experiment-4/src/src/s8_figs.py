#!/usr/bin/env python3
"""STEP 8: figures (matplotlib, vector PDF + PNG) drawn directly from the results/ JSON files."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FIGS, RESULTS, TEMPS, load_json  # noqa: E402

plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False,
                     "axes.spines.right": False})
COL = plt.get_cmap("tab10").colors


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGS / f"{name}.pdf")
    fig.savefig(FIGS / f"{name}.png", dpi=160)
    plt.close(fig)


def fig_arrhenius(scr, red, fz):
    for task in ("T1", "T2"):
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
        for ax, topk in zip(axes, (-1, 10)):
            key = f"{task}|{topk}"
            fr = fz["body"]["lines"].get(key)
            if not fr:
                continue
            m = fr["reference"]
            x = 1 / np.array(TEMPS)
            for i, j in enumerate(fr["eligible"]):
                ln = scr["arrhenius"][key]["lines"][j]
                ax.plot(ln["x"], ln["y"], "o", color=COL[i], label=f"{j} (R²={ln['r2']:.2f})")
                xx = np.linspace(x.min(), x.max(), 50)
                ax.plot(xx, fr["lines"][j]["a"] + fr["lines"][j]["b"] * xx, "-", color=COL[i], lw=1)
                ys = []
                for T in TEMPS:
                    c = red["cells"].get(f"{task}|{T}|{topk}", {}).get("counts", {})
                    ys.append(np.log((c.get(j, 0) + .5) / (c.get(m, 0) + .5)))
                ax.plot(x, ys, "^", color=COL[i], mfc="none")
            ax.set_title(f"{task}, top-k={'none' if topk == -1 else topk} (ref = {m})")
            ax.set_xlabel("1 / T")
            ax.legend(fontsize=7, frameon=False)
        axes[0].set_ylabel("ln(share_j / share_ref)")
        fig.suptitle("Arrhenius lines: screen (circles, frozen fit) vs re-draw (triangles)", fontsize=9)
        save(fig, f"fig_arrhenius_{task}")


def fig_hill(scr, red):
    keys = [k for k in scr["hill"]]
    fig, axes = plt.subplots(1, len(keys), figsize=(2.6 * len(keys), 3), sharey=True)
    for ax, k in zip(axes, keys):
        for src, d, mk in (("screen", scr, "o-"), ("re-draw", red, "^--")):
            h = d["hill"].get(k)
            if not h:
                continue
            ax.plot(h["T"], h["ln_alpha1"], mk, color=COL[0], label=f"ln α₁ within-idea ({src})", ms=4)
            ax.plot(h["T"], h["ln_beta1"], mk, color=COL[1], label=f"ln D₁ ideas ({src})", ms=4)
        ax.set_title(k.replace("|-1", " none").replace("|10", " top10"))
        ax.set_xlabel("T")
    axes[0].set_ylabel("log diversity")
    axes[0].legend(fontsize=6, frameon=False)
    save(fig, "fig_hill_partition")


def fig_abc(scr):
    keys = list(scr["abc"])
    E_i = np.array([[scr["abc"][k][str(T)]["E_ideas_10"] for T in TEMPS] for k in keys])
    E_p = np.array([[scr["abc"][k][str(T)]["E_phrasings_10"] for T in TEMPS] for k in keys])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    for ax, M, t in ((axes[0], E_i, "E[distinct ideas among 10]"), (axes[1], E_p, "E[distinct phrasings among 10]")):
        im = ax.imshow(M, cmap="viridis", vmin=1, vmax=10, aspect="auto")
        ax.set_xticks(range(len(TEMPS)), [str(T) for T in TEMPS])
        ax.set_yticks(range(len(keys)), keys)
        ax.set_xlabel("T")
        ax.set_title(t)
        for i in range(len(keys)):
            for j in range(len(TEMPS)):
                lab = scr["abc"][keys[i]][str(TEMPS[j])]["verdict"] if ax is axes[1] else ""
                ax.text(j, i, f"{M[i, j]:.1f}{' ' + lab if lab else ''}", ha="center", va="center", fontsize=6,
                        color="w" if M[i, j] < 6 else "k")
        fig.colorbar(im, ax=ax, fraction=0.04)
    save(fig, "fig_abc_table")


def fig_seed(c3, disp):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    ax = axes[0]
    tasks = list(c3["tasks"])
    for i, t in enumerate(tasks):
        r = c3["tasks"][t]
        ax.errorbar(i, r["observed_flip_rate"], yerr=[[r["observed_flip_rate"] - r["observed_flip_ci"][0]],
                                                      [r["observed_flip_ci"][1] - r["observed_flip_rate"]]],
                    fmt="o", color="k", label="observed (fresh)" if i == 0 else None)
        ax.plot(i - .15, r["predicted_behavioural"], "s", color=COL[1], label="pred behavioural" if i == 0 else None)
        ax.plot(i + .15, r["predicted_readout"], "D", color=COL[2], label="pred readout" if i == 0 else None)
        s = c3["screen_in_sample"][t]
        ax.plot(i + .3, s["flip_rate"], "x", color=COL[3], label="screen (in-sample)" if i == 0 else None)
    ax.set_xticks(range(len(tasks)), tasks)
    ax.set_ylabel("greedy flip rate")
    ax.set_title("Seed strings: greedy idea flips")
    ax.legend(fontsize=7, frameon=False)
    ax = axes[1]
    for i, t in enumerate(disp):
        ax.plot(disp[t]["layers"], disp[t]["ratio_seed_over_ban"], color=COL[i], label=t)
    ax.set_xlabel("layer")
    ax.set_ylabel("||Δh seed|| / ||Δh ban_r1||")
    ax.set_title("Residual displacement at last 5 template tokens")
    ax.legend(frameon=False)
    save(fig, "fig_seed_flip")


def fig_ban(screen):
    for task, conds in screen["tables"].items():
        order = ["placebo", "baseline"] + [c for c in conds if c not in ("placebo", "baseline")]
        classes = sorted({k for c in conds.values() for k in c["counts"]})
        M = np.array([[conds[c]["counts"].get(k, 0) / conds[c]["n"] for k in classes] for c in order])
        fig, ax = plt.subplots(figsize=(0.6 * len(classes) + 2, 0.35 * len(order) + 1.2))
        ax.imshow(M, cmap="Blues", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
        ax.set_yticks(range(len(order)), order)
        sig = {(c["ban"], c["idea"]) for c in screen["regularity"][task] if c["decrease"] and c["p_holm"] < 0.01}
        for i, c in enumerate(order):
            for j, k in enumerate(classes):
                v = conds[c]["counts"].get(k, 0)
                if v:
                    ax.text(j, i, str(v), ha="center", va="center", fontsize=6, color="w" if M[i, j] > .5 else "k")
                if (c, k) in sig:
                    ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, fill=False, ec="red", lw=1.5))
        ax.set_title(f"{task}: idea counts by ban condition (red = Holm p<0.01 decrease vs placebo)")
        save(fig, f"fig_ban_heatmap_{task}")


def fig_qd(scr, red):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for ax, d, name in ((axes[0], scr, "screen grid (768 tok)"), (axes[1], red, "re-draw (1536 tok)")):
        for i, (k, pts) in enumerate(d["quality_diversity"].items()):
            pts = [p for p in pts if p["pass_rate"] is not None]
            ax.plot([p["entropy"] for p in pts], [p["pass_rate"] for p in pts], "o-", color=COL[i % 10], label=k,
                    ms=3)
            for p in pts:
                ax.annotate(str(p["T"]), (p["entropy"], p["pass_rate"]), fontsize=5)
        ax.set_xlabel("idea entropy (bits)")
        ax.set_title(name)
    axes[0].set_ylabel("oracle pass rate")
    axes[0].legend(fontsize=6, frameon=False)
    save(fig, "fig_quality_diversity")


def main() -> None:
    scr = load_json(RESULTS / "temperature_law_screen.json")
    red = load_json(RESULTS / "temperature_law_redraw.json")
    fz = load_json(RESULTS / "frozen_c1_temperature.json")
    fig_arrhenius(scr, red, fz)
    fig_hill(scr, red)
    fig_abc(scr)
    fig_seed(load_json(RESULTS / "c3_scoring.json"), load_json(RESULTS / "seed_displacement.json"))
    fig_ban(load_json(RESULTS / "screen_tables.json"))
    fig_qd(scr, red)
    print("figures:", sorted(p.name for p in FIGS.glob("*.pdf")))


if __name__ == "__main__":
    main()
