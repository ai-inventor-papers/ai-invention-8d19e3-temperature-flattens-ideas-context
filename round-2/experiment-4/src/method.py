#!/usr/bin/env python3
"""Entry point: (optionally) run every stage in order, then aggregate all results into method_out.json
(exp_gen_sol_out schema: datasets[].examples[] with input/output/predict_*/metadata_* fields; verdicts in metadata).

  uv run method.py              # aggregate existing results/ into method_out.json
  uv run method.py --run-all    # run stages s1..s8 (GPU stages included) then aggregate

Datasets in method_out.json:
  c1_redraw_cells      one example per (task, T, top-k) re-draw cell; output = observed idea shares; predictions =
                       frozen Arrhenius law (anchored), fixed-utility logit baseline, no-temperature-effect baseline
  c3_fresh_seed_strings one example per (task, fresh seed string); output = observed greedy idea; predictions =
                       internal readout argmax, unseeded-greedy baseline (seed strings do nothing)
  ban_screen_conditions one example per (task, ban condition); output = observed counts; prediction = placebo counts
  program_ledger       one example per program (all sources); output = canonical v1 label; predictions = AST
                       classifier label (graph tasks) and the oracle status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from common import LABELS_PATH, ORACLE_PATH, RESULTS, read_jsonl, save_json, setup_logging  # noqa: E402

STAGES = [["src/s1_label.py"], ["src/s2_oracle.py"], ["src/s3_screen.py"], ["src/s4_templaw.py", "--source", "grid"],
          ["src/freeze.py", "c1"], ["src/gpu_gen.py", "--modes", "trunc,redraw"], ["src/s1_label.py"],
          ["src/s2_oracle.py"], ["src/s4b_truncation.py"], ["src/s4_templaw.py", "--source", "redraw"],
          ["src/s6_seed_readout.py", "--phase", "readout"], ["src/s6_seed_readout.py", "--phase", "freeze"],
          ["src/gpu_gen.py", "--modes", "seeds"], ["src/s1_label.py"], ["src/s2_oracle.py"],
          ["src/s6c_seed_score.py"], ["src/s7_c4ref.py"], ["src/judge_audit.py"], ["src/s8_figs.py"]]

USER = {"T1": "Implement a path search algorithm in Python", "T2": "Implement a sorting algorithm",
        "T3": "Implement a function that finds a shortest path in a weighted graph"}


def jl(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def short(d) -> str:
    return json.dumps(d, sort_keys=True)


def ds_c1(red: dict | None) -> list[dict]:
    ex = []
    if not red or "oos" not in red:
        return ex
    for key, res in red["oos"]["per_line"].items():
        task, topk = key.split("|")
        for T, v in res["by_T"].items():
            ex.append(dict(
                input=f"{USER[task]} | temperature={T} | top_k={'none' if topk == '-1' else topk} | n={v['n']} "
                      f"| classes={res['classes']}",
                output=short({k: round(x, 4) for k, x in v["observed"].items()}),
                predict_frozen_arrhenius_anchored=short({k: round(x, 4) for k, x in
                                                         v["pred_frozen_anchored"].items()}),
                predict_frozen_arrhenius_unanchored=short({k: round(x, 4) for k, x in
                                                           v["pred_frozen_unanchored"].items()}),
                predict_baseline_fixed_utility=short({k: round(x, 4) for k, x in
                                                      v["pred_baseline_fixed_utility"].items()}),
                predict_baseline_no_temperature_effect=short({k: round(x, 4) for k, x in
                                                              v["pred_baseline_no_temperature_effect"].items()}),
                metadata_task=task, metadata_T=float(T), metadata_topk=int(topk),
                metadata_jsd_frozen_anchored=v.get("jsd_frozen_anchored"),
                metadata_jsd_fixed_utility=v.get("jsd_baseline_fixed_utility"),
                metadata_jsd_no_temperature=v.get("jsd_baseline_no_temperature_effect")))
    return ex


def ds_c3(score: dict | None, frozen: dict | None) -> list[dict]:
    ex = []
    if not score or not frozen:
        return ex
    for task, t in score.get("tasks", {}).items():
        for row in t.get("per_string", []):
            ex.append(dict(input=f"{row['seed_string']}\n\n{USER[task]}", output=str(row["observed_greedy"]),
                           predict_readout_argmax=str(row["pred_greedy_idea"]),
                           predict_baseline_unseeded_greedy=str(t["unseeded_greedy_label"]),
                           metadata_task=task, metadata_seed_kind=row["seed_kind"],
                           metadata_p_flip_readout=row["p_flip"], metadata_observed_flip=row["observed_flip"],
                           metadata_t07_labels=row["t07_labels"]))
    return ex


def ds_ban(screen: dict | None) -> list[dict]:
    ex = []
    if not screen:
        return ex
    for task, conds in screen["tables"].items():
        plc = conds.get("placebo", {}).get("counts", {})
        for cond, t in conds.items():
            ex.append(dict(input=f"{USER[task]} | condition={cond} | banned={t.get('banned')}",
                           output=short(t["counts"]), predict_placebo_counts=short(plc),
                           metadata_task=task, metadata_n=t["n"], metadata_entropy_bits=t["entropy_bits"],
                           metadata_still_banned_pct=t["still_banned_pct"], metadata_pass_rate=t["pass_rate"],
                           metadata_off_menu_correct_share=t["off_menu_correct_share"]))
    return ex


def ds_ledger() -> list[dict]:
    orc = {r["id"]: r for r in read_jsonl(ORACLE_PATH)}
    ex = []
    for r in read_jsonl(LABELS_PATH):
        o = orc.get(r["id"], {})
        ex.append(dict(input=r["id"], output=r["label"],
                       predict_ast_classifier=str(r.get("ast_label") or "n/a (sort task)"),
                       predict_oracle_status=str(o.get("status")),
                       metadata_source=r["source"], metadata_task=r["task"], metadata_cond=r["cond"],
                       metadata_T=r["T"], metadata_topk=r["topk"], metadata_wording=r["wording"],
                       metadata_finish_reason=r["finish_reason"], metadata_n_tokens=r["n_tokens"],
                       metadata_pass=o.get("passed"), metadata_still_banned=r["still_banned"]))
    return ex


def verdicts(scr, red, c3s) -> dict:
    v = {}
    if scr:
        v["C1_screen"] = scr["c1_criteria"]
    if red:
        v["C1_redraw"] = red["c1_criteria"]
        v["C1_redraw_oos_models"] = {k: x["models"] for k, x in red.get("oos", {}).get("per_line", {}).items()}
    if scr and red:
        keys = [k for k, x in scr["c1_criteria"].items() if x.get("eligible")]
        v["C1_PASS"] = all(scr["c1_criteria"][k].get("pass_all") and red["c1_criteria"].get(k, {}).get("pass_all")
                           for k in keys)
    if c3s:
        v["C3"] = c3s.get("verdict")
    return v


@logger.catch(reraise=True)
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-all", action="store_true")
    args = ap.parse_args()
    setup_logging("method")
    if args.run_all:
        for st in STAGES:
            logger.info(f"running {' '.join(st)}")
            subprocess.run([sys.executable, *st], cwd=ROOT, check=True)
    scr = jl(RESULTS / "temperature_law_screen.json")
    red = jl(RESULTS / "temperature_law_redraw.json")
    screen = jl(RESULTS / "screen_tables.json")
    c3s = jl(RESULTS / "c3_scoring.json")
    fz3 = jl(RESULTS / "frozen_c3_seeds.json")
    meta = dict(
        method_name="Unified idea ledger + temperature law (C1) + seed shocks (C3), Qwen2.5-3B-Instruct",
        model="Qwen/Qwen2.5-3B-Instruct (bf16, vLLM 0.31.0)",
        verdicts=verdicts(scr, red, c3s),
        label_repro=jl(RESULTS / "label_repro_check.json"),
        classifier_audit_ast={k: {kk: vv for kk, vv in x.items() if kk != "confusion_v1_rows_ast_cols"}
                              for k, x in (jl(RESULTS / "classifier_audit_ast.json") or {}).get("per_task_source",
                                                                                                {}).items()},
        judge_audit=(jl(RESULTS / "judge_audit.json") or {}).get("summary"),
        truncation_audit={k: v for k, v in (jl(RESULTS / "truncation_audit.json") or {}).items() if k != "logit"}
        if jl(RESULTS / "truncation_audit.json") else None,
        wording_check=(screen or {}).get("grid_vs_P1"),
        screen_regularity_candidates=(screen or {}).get("candidates"),
        abc_table_screen=(scr or {}).get("abc"), abc_table_redraw=(red or {}).get("abc"),
        hill_screen=(scr or {}).get("hill"), hill_redraw=(red or {}).get("hill"),
        repro_rows=(scr or {}).get("repro_rows", {}).get("identical_labels") if scr else None,
        c3_scoring=(c3s or {}).get("summary"),
        c4_reference=(jl(RESULTS / "frozen_c4_reference.json") or jl(RESULTS / "frozen_c4_reference_v0.json") or {})
        .get("body"),
        frozen={n: (jl(RESULTS / f"frozen_{n}.json") or {}).get("sha256") for n in
                ("c1_temperature", "c3_seeds", "c4_reference_v0", "c4_reference")},
        spend_usd=(jl(RESULTS / "judge_audit.json") or {}).get("spend_usd", 0.0),
        tables=dict(labels="results/labels_unified.jsonl", oracle="results/oracle_results.jsonl",
                    screen="results/screen_tables.json", temperature_screen="results/temperature_law_screen.json",
                    temperature_redraw="results/temperature_law_redraw.json",
                    truncation="results/truncation_audit.json", c3="results/c3_scoring.json",
                    c4="results/frozen_c4_reference.json", judge="results/judge_audit.json"))
    datasets = []
    for name, ex in (("c1_redraw_cells", ds_c1(red)), ("c3_fresh_seed_strings", ds_c3(c3s, fz3)),
                     ("ban_screen_conditions", ds_ban(screen)), ("program_ledger", ds_ledger())):
        if ex:
            datasets.append(dict(dataset=name, examples=ex))
            logger.info(f"dataset {name}: {len(ex)} examples")
    save_json(ROOT / "method_out.json", dict(metadata=meta, datasets=datasets))
    logger.info(f"wrote method_out.json; verdict keys {list(meta['verdicts'])}")
    logger.info(f"source counts {dict(Counter(r['source'] for r in read_jsonl(LABELS_PATH)))}")


if __name__ == "__main__":
    main()
