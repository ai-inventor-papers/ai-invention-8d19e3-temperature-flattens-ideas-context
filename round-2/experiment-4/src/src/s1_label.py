#!/usr/bin/env python3
"""STEP 1: put every program (temperature grid, seed rows, ban arm, new re-draw / fresh-seed generations) into
ONE label space with the canonical ban-arm v1 classifier, and audit it against the influence-arm AST classifier.

Outputs: results/labels_unified.jsonl, gens/programs.jsonl (id -> extracted code, for the oracle and Hill alpha),
results/ban_relabel_diff.jsonl, results/label_map_ast_to_v1.json, results/classifier_audit_ast.json
"""
from __future__ import annotations

import importlib.util
import multiprocessing as mp
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (GENS, INPUTS, LABELS_PATH, RESULTS, detect_cpus, read_jsonl, save_json,  # noqa: E402
                    setup_logging, write_jsonl)

TASK_KIND = {"T1": "graph", "T2": "sort", "T3": "graph"}
AST_TO_V1 = {"bfs": "BFS", "dfs": "DFS", "dijkstra": "Dijkstra", "astar": "A_star",
             "greedy_best_first": "Greedy_best_first", "bidirectional": "Bidirectional",
             "bellman_ford": "Bellman_Ford", "spfa": "SPFA", "floyd_warshall": "Floyd_Warshall",
             "iddfs": "IDDFS", "dial_bucket": "Other", "random_walk": "Other", "other": "Other",
             "no_code": "Unparseable", "syntax_error": "Unparseable"}


def load_sources() -> list[dict]:
    """Every generation as a common record (text kept only in memory)."""
    rows: list[dict] = []
    for r in read_jsonl(INPUTS / "grid" / "data" / "raw_grid.jsonl"):
        rows.append(dict(id=f"grid|{r['task']}|{r['cond']}|{r['T']}|{r['topk']}|{r['seed']}|{r['sample_idx']}",
                         source="grid", task=r["task"], cond=r["cond"], T=float(r["T"]), topk=int(r["topk"]),
                         seed=r["seed"], idx=r["sample_idx"], seed_string=None, seed_kind=None, wording="grid",
                         text=r["text"], n_tokens=int(r["n_tokens"]), finish_reason=r["finish_reason"], banned=[]))
    for r in read_jsonl(INPUTS / "grid" / "data" / "raw_seeds.jsonl"):
        rows.append(dict(id=f"seeds|{r['task']}|{r['cond']}|{r['T']}|{r['topk']}|{r['seed']}|{r['sample_idx']}",
                         source="seeds", task=r["task"], cond=r["cond"], T=float(r["T"]), topk=int(r["topk"]),
                         seed=r["seed"], idx=r["sample_idx"], seed_string=r["seed_string"],
                         seed_kind=r["seed_kind"], wording="grid", text=r["text"], n_tokens=int(r["n_tokens"]),
                         finish_reason=r["finish_reason"], banned=[]))
    for p in sorted((INPUTS / "ban" / "gen").glob("*/*.jsonl")):
        if p.stem == "comention":
            continue
        for r in read_jsonl(p):
            rows.append(dict(id=f"ban|{r['task']}|{r['condition']}|0.7|-1|{r['seed']}|{r['seed']}", source="ban",
                             task=r["task"], cond=r["condition"], T=0.7, topk=-1, seed=r["seed"], idx=r["seed"],
                             seed_string=None, seed_kind=None, wording="P1", text=r["output_text"],
                             n_tokens=len(r["output_token_ids"]), finish_reason=r["finish_reason"],
                             banned=r.get("banned") or []))
    # new generations of this artifact (re-draw, fresh seeds); identical field layout written by gpu_gen.py
    for p in sorted(GENS.glob("*.jsonl")):
        if p.name in ("programs.jsonl",) or p.stem.startswith("trunc"):
            continue
        for r in read_jsonl(p):
            rows.append(dict(id=r["id"], source=r["source"], task=r["task"], cond=r["cond"], T=float(r["T"]),
                             topk=int(r["topk"]), seed=r["seed"], idx=r["idx"], seed_string=r.get("seed_string"),
                             seed_kind=r.get("seed_kind"), wording=r["wording"], text=r["text"],
                             n_tokens=int(r["n_tokens"]), finish_reason=r["finish_reason"], banned=[]))
    return rows


def _load_ast_module():
    spec = importlib.util.spec_from_file_location("ast_classifier", INPUTS / "influence" / "classifier.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _classify_one(args: tuple[str, str, str]) -> dict:
    text, kind, task = args
    from classify import classify_text
    c = classify_text(text, kind)
    out = dict(label=c["label"], multi=c["multi"], multi_labels=c["multi_labels"], raw_labels=c["raw_labels"],
               oracle_eligible=c["oracle_eligible"], code=c["code"] or "")
    if kind == "graph":
        try:
            out["ast_label"] = AST_TO_V1.get(_load_ast_module_cached().classify_text(text)["label"], "Other")
        except (RecursionError, ValueError, SyntaxError, TypeError) as e:
            out["ast_label"] = f"error:{type(e).__name__}"
    return out


_AST = None


def _load_ast_module_cached():
    global _AST
    if _AST is None:
        _AST = _load_ast_module()
    return _AST


def kappa_ci(a: list[str], b: list[str], n_boot: int = 1000, seed: int = 0) -> dict:
    from sklearn.metrics import cohen_kappa_score
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0:
        return dict(n=0)
    k = float(cohen_kappa_score(a, b))
    rng = np.random.default_rng(seed)
    ks = []
    for _ in range(n_boot):
        i = rng.integers(0, len(a), len(a))
        if len(set(a[i]) | set(b[i])) < 2:
            continue
        ks.append(cohen_kappa_score(a[i], b[i]))
    lo, hi = (np.quantile(ks, [0.025, 0.975]).tolist() if ks else [float("nan")] * 2)
    return dict(n=int(len(a)), agreement=float((a == b).mean()), kappa=k, kappa_ci=[lo, hi])


def confusion(a: list[str], b: list[str]) -> dict:
    m: dict[str, Counter] = defaultdict(Counter)
    for x, y in zip(a, b):
        m[x][y] += 1
    return {k: dict(v) for k, v in m.items()}


@logger.catch(reraise=True)
def main() -> None:
    setup_logging("s1_label")
    from classify import CLASSIFIER_VERSION, classifier_hash
    chash = classifier_hash()
    logger.info(f"classifier {CLASSIFIER_VERSION}:{chash}")
    rows = load_sources()
    logger.info(f"loaded {len(rows)} generations: {dict(Counter(r['source'] for r in rows))}")
    args = [(r["text"], TASK_KIND[r["task"]], r["task"]) for r in rows]
    n_workers = max(1, min(12, detect_cpus() - 2))
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp.get_context("spawn")) as ex:
        res = list(ex.map(_classify_one, args, chunksize=64))
    out, programs = [], []
    for r, c in zip(rows, res):
        rec = {k: r[k] for k in ("id", "source", "task", "cond", "T", "topk", "seed", "idx", "seed_string",
                                 "seed_kind", "wording", "banned", "finish_reason", "n_tokens")}
        rec.update(label=c["label"], multi=c["multi"], multi_labels=c["multi_labels"], raw_labels=c["raw_labels"],
                   oracle_eligible=c["oracle_eligible"], still_banned=c["label"] in r["banned"],
                   ast_label=c.get("ast_label"), classifier=f"{CLASSIFIER_VERSION}:{chash}")
        out.append(rec)
        programs.append(dict(id=r["id"], task=r["task"], code=c["code"], oracle_eligible=c["oracle_eligible"]))
    ids = [o["id"] for o in out]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    assert not dup, f"duplicate ids: {dup[:5]}"
    write_jsonl(LABELS_PATH, out)
    write_jsonl(GENS / "programs.jsonl", programs)
    logger.info(f"wrote {len(out)} labels")

    # ---- T1 reproduction gate: relabel must equal the stored ban-arm labels
    stored = {}
    for p in sorted((INPUTS / "ban" / "labels").glob("*/*.jsonl")):
        for s in read_jsonl(p):
            stored[f"ban|{s['task']}|{s['condition']}|0.7|-1|{s['seed']}|{s['seed']}"] = s["label"]
    diffs = [dict(id=o["id"], stored=stored[o["id"]], new=o["label"]) for o in out
             if o["source"] == "ban" and o["id"] in stored and stored[o["id"]] != o["label"]]
    n_cmp = sum(1 for o in out if o["source"] == "ban" and o["id"] in stored)
    write_jsonl(RESULTS / "ban_relabel_diff.jsonl", diffs)
    logger.info(f"ban relabel: {n_cmp} compared, {len(diffs)} diffs")
    checks = {}
    for (task, cond), expect in {("T1", "baseline"): {"BFS": 179, "DFS": 44, "A_star": 39, "Dijkstra": 22,
                                                       "Other": 14, "SPFA": 2},
                                 ("T2", "placebo"): {"Bubble": 43, "Merge": 26, "Quick": 18, "Selection": 8,
                                                     "Insertion": 5}}.items():
        got = dict(Counter(o["label"] for o in out if o["source"] == "ban" and o["task"] == task
                           and o["cond"] == cond))
        checks[f"{task}/{cond}"] = dict(expected=expect, got=got, match=got == expect)
    # ---- AST comparator audit (graph tasks only)
    audit = {"map": AST_TO_V1, "per_task_source": {}}
    for task in ("T1", "T3"):
        for src in sorted({o["source"] for o in out}):
            sel = [o for o in out if o["task"] == task and o["source"] == src and o.get("ast_label")]
            if not sel:
                continue
            a = [o["label"] for o in sel]
            b = [o["ast_label"] for o in sel]
            d = kappa_ci(a, b)
            d["confusion_v1_rows_ast_cols"] = confusion(a, b)
            audit["per_task_source"][f"{task}|{src}"] = d
            logger.info(f"AST audit {task}|{src}: n={d['n']} agree={d.get('agreement', 0):.3f} "
                        f"kappa={d.get('kappa', float('nan')):.3f}")
    save_json(RESULTS / "label_map_ast_to_v1.json", AST_TO_V1)
    save_json(RESULTS / "classifier_audit_ast.json", audit)
    save_json(RESULTS / "label_repro_check.json", dict(classifier=f"{CLASSIFIER_VERSION}:{chash}",
                                                        n_compared=n_cmp, n_diffs=len(diffs), counts=checks))
    if diffs or not all(v["match"] for v in checks.values()):
        logger.error("label reproduction FAILED: see results/ban_relabel_diff.jsonl")


if __name__ == "__main__":
    main()
