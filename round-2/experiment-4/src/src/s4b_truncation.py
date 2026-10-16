#!/usr/bin/env python3
"""STEP 4b: truncation audit.

(1) logistic: finish=='length' ~ C(label) + T + topk + task over the screen grid rows (odds ratios with CI);
(2) PRIMARY: 150 truncated grid rows CONTINUED from their own 768 tokens (gens/trunc_cont.jsonl, gpu_gen.py trunc):
    label flip = label(prefix + continuation) != label(prefix alone); oracle pass change;
(3) SECONDARY: 20 rows regenerated from scratch at the same seed (max_tokens 2048): is the 768-token prefix reproduced?
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENS, LABELS_PATH, ORACLE_PATH, RESULTS, read_jsonl, save_json, setup_logging, wilson  # noqa

KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}


def trunc_logit(rows: list[dict]) -> dict:
    import pandas as pd
    import statsmodels.formula.api as smf
    d = pd.DataFrame([dict(y=int(r["finish_reason"] == "length"), label=r["label"], T=r["T"], topk=str(r["topk"]),
                           task=r["task"]) for r in rows])
    vc = d["label"].value_counts()
    d["label"] = d["label"].where(d["label"].map(vc) >= 20, "rare_pooled")
    try:
        f = smf.logit("y ~ C(label, Treatment('BFS')) + T + C(topk) + C(task)", data=d).fit(disp=0, maxiter=200)
        ci = f.conf_int()
        return dict(n=len(d), trunc_rate=float(d["y"].mean()),
                    odds_ratios={k: dict(OR=float(np.exp(v)), lo=float(np.exp(ci.loc[k, 0])),
                                         hi=float(np.exp(ci.loc[k, 1])), p=float(f.pvalues[k]))
                                 for k, v in f.params.items()},
                    trunc_rate_by_label={k: float(v) for k, v in d.groupby("label")["y"].mean().items()},
                    trunc_rate_by_T={str(k): float(v) for k, v in d.groupby("T")["y"].mean().items()})
    except (np.linalg.LinAlgError, ValueError) as e:
        return dict(n=len(d), error=repr(e)[:200])


@logger.catch(reraise=True)
def main() -> None:
    setup_logging("s4b_truncation")
    from classify import classify_text
    from oracle import run_many
    lab = {r["id"]: r for r in read_jsonl(LABELS_PATH)}
    orc = {r["id"]: r for r in read_jsonl(ORACLE_PATH)}
    grid = [r for r in lab.values() if r["source"] == "grid" and r["cond"] == "grid"]
    out = dict(logit=trunc_logit(grid))
    cont = read_jsonl(GENS / "trunc_cont.jsonl")
    if cont:
        items, recs = [], []
        for r in cont:
            gid = r["id"].replace("trunc|", "grid|", 1)
            full_text = r["prefix_text"] + r["text"]
            c = classify_text(full_text, KIND[r["task"]])
            before = lab[gid]
            recs.append(dict(id=gid, task=r["task"], T=r["T"], topk=r["topk"], label_trunc=before["label"],
                             label_full=c["label"], flip=c["label"] != before["label"],
                             pass_trunc=bool(orc.get(gid, {}).get("passed")),
                             cont_finish=r["finish_reason"], cont_tokens=r["n_tokens"]))
            items.append((c["code"] if c["oracle_eligible"] else "", r["task"]))
        res = run_many(items, workers=8)
        for rec, o in zip(recs, res):
            rec["pass_full"] = bool(o.get("passed"))
        n = len(recs)
        k = sum(r["flip"] for r in recs)
        fw = wilson(k, n)
        by_T = defaultdict(list)
        by_idea = defaultdict(list)
        for r in recs:
            by_T[r["T"]].append(r["flip"])
            by_idea[r["label_trunc"]].append(r["flip"])
        out["continuation"] = dict(
            n=n, flips=k, flip_rate=fw[0], flip_ci=[fw[1], fw[2]],
            flip_by_T={str(T): dict(n=len(v), rate=sum(v) / len(v)) for T, v in sorted(by_T.items())},
            flip_by_trunc_label={j: dict(n=len(v), rate=sum(v) / len(v)) for j, v in by_idea.items()},
            transitions=dict(Counter(f"{r['label_trunc']}->{r['label_full']}" for r in recs if r["flip"])),
            pass_trunc=sum(r["pass_trunc"] for r in recs) / n, pass_full=sum(r["pass_full"] for r in recs) / n,
            still_truncated_after_continuation=sum(r["cont_finish"] == "length" for r in recs),
            rows=recs)
        logger.info(f"continuation: flips {k}/{n} = {fw[0]:.3f} [{fw[1]:.3f},{fw[2]:.3f}]; pass "
                    f"{out['continuation']['pass_trunc']:.2f} -> {out['continuation']['pass_full']:.2f}")
    reg = read_jsonl(GENS / "trunc_regen.jsonl")
    if reg:
        out["regeneration"] = dict(n=len(reg), prefix768_reproduced=sum(r["prefix_reproduced"] for r in reg),
                                   median_common_prefix_tokens=float(np.median([r["n_common_prefix"] for r in reg])),
                                   common_prefix_tokens=[r["n_common_prefix"] for r in reg])
        logger.info(f"regeneration: {out['regeneration']['prefix768_reproduced']}/{len(reg)} prefixes reproduced")
    save_json(RESULTS / "truncation_audit.json", out)


if __name__ == "__main__":
    main()
