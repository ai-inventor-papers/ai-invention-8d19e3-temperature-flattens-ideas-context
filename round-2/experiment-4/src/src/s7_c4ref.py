#!/usr/bin/env python3
"""STEP 7: C4 reference = best temperature for correct OFF-MENU ideas (P4 menus), per task.

Per (task, T, topk) cell of the screen grid (768 tokens, grid wording) and of the re-draw (1536 tokens, P1):
pass rate (Wilson), off-menu correct share, counts of correct rare ideas. 768-equivalent for the re-draw: cut
token_ids at 768, decode, re-extract + re-classify + re-run the oracle. Best T = argmax off-menu correct share s.t.
pass >= 0.8 x pass(T=0.7, same topk, same source); ties -> lower T.
Writes results/c4_reference.json then freezes it (freeze.py c4 / c4v0).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (GENS, LABELS_PATH, MENUS, MODEL, NON_IDEAS, ORACLE_PATH, RARE_CORRECT, RESULTS,  # noqa: E402
                    TEMPS, read_jsonl, save_json, setup_logging, wilson)

KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}


def cell_stats(rs: list[dict], task: str) -> dict:
    n = len(rs)
    p = wilson(sum(bool(r["pass"]) for r in rs), n)
    off = [r for r in rs if r["pass"] and r["label"] not in MENUS[task] and r["label"] not in NON_IDEAS]
    o = wilson(len(off), n)
    return dict(n=n, pass_rate=p[0], pass_ci=[p[1], p[2]], off_menu_correct=len(off), off_menu_correct_share=o[0],
                off_menu_ci=[o[1], o[2]], off_menu_by_idea=dict(Counter(r["label"] for r in off)),
                rare_correct=dict(Counter(r["label"] for r in rs if r["pass"] and r["label"] in RARE_CORRECT[task])))


def best(cells: dict, task: str) -> dict:
    res = {}
    for topk in sorted({k[1] for k in cells}):
        ref = cells.get((0.7, topk))
        if not ref:
            continue
        ok = [(T, c) for (T, k), c in cells.items() if k == topk and c["pass_rate"] >= 0.8 * ref["pass_rate"]]
        if not ok:
            continue
        T, c = sorted(ok, key=lambda x: (-x[1]["off_menu_correct_share"], x[0]))[0]
        res[str(topk)] = dict(best_T=T, **{k: c[k] for k in ("pass_rate", "off_menu_correct_share",
                                                             "off_menu_by_idea", "n")},
                              pass_T07=ref["pass_rate"], off_menu_T07=ref["off_menu_correct_share"])
    return res


def redraw_768(rows: list[dict]) -> list[dict]:
    from classify import classify_text
    from oracle import run_many
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    gen = {r["id"]: r for r in read_jsonl(GENS / "redraw.jsonl")}
    out, items = [], []
    for r in rows:
        g = gen[r["id"]]
        if len(g["token_ids"]) > 768:
            text = tok.decode(g["token_ids"][:768], skip_special_tokens=True)
            c = classify_text(text, KIND[r["task"]])
            out.append(dict(r, label=c["label"], cut=True))
            items.append((c["code"] if c["oracle_eligible"] else "", r["task"]))
        else:
            out.append(dict(r, cut=False))
            items.append(None)
    todo = [i for i, it in enumerate(items) if it is not None]
    res = run_many([items[i] for i in todo], workers=10)
    for i, o in zip(todo, res):
        out[i]["pass"] = bool(o.get("passed"))
    return out


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen-only", action="store_true")
    args = ap.parse_args()
    setup_logging("s7_c4ref")
    orc = {r["id"]: r for r in read_jsonl(ORACLE_PATH)}
    lab = read_jsonl(LABELS_PATH)
    for r in lab:
        r["pass"] = bool(orc.get(r["id"], {}).get("passed"))
    body = dict(menus=MENUS, rule="argmax off-menu correct share s.t. pass >= 0.8 x pass(T=0.7, same topk & source);"
                " ties -> lower T", tasks={}, cells={})
    sources = {"screen_grid_768": [r for r in lab if r["source"] == "grid" and r["cond"] == "grid"]}
    if not args.screen_only:
        red = [r for r in lab if r["source"] == "redraw" and r["cond"] == "grid"]
        sources["redraw_1536"] = red
        sources["redraw_768equiv"] = redraw_768(red)
        n_cut = sum(r["cut"] for r in sources["redraw_768equiv"])
        body["redraw_768equiv_note"] = f"{n_cut}/{len(red)} re-draw rows longer than 768 tokens were cut and re-scored"
    for name, rows in sources.items():
        by = defaultdict(list)
        for r in rows:
            by[(r["task"], r["T"], r["topk"])].append(r)
        for task in ("T1", "T2", "T3"):
            cells = {(T, k): cell_stats(rs, task) for (t, T, k), rs in by.items() if t == task}
            body["cells"].setdefault(name, {})[task] = {f"{T}|{k}": v for (T, k), v in sorted(cells.items())}
            body["tasks"].setdefault(task, {})[name] = best(cells, task)
    body["designated_comparator_for_768_token_siblings"] = "redraw_768equiv" if not args.screen_only \
        else "screen_grid_768"
    save_json(RESULTS / "c4_reference.json", body)
    for t, v in body["tasks"].items():
        logger.info(f"C4 {t}: { {s: {k: (x['best_T'], round(x['off_menu_correct_share'], 3)) for k, x in b.items()} for s, b in v.items()} }")
    from freeze import write_frozen
    write_frozen(RESULTS / ("frozen_c4_reference_v0.json" if args.screen_only else "frozen_c4_reference.json"), body)


if __name__ == "__main__":
    main()
