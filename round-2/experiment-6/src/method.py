#!/usr/bin/env python3
"""Entry point: 'Does steering pick ideas or spread them?' (selector steering on Qwen + ban displacement on gemma).

  python method.py run <stage>     run one pipeline stage (see STAGES; each is resumable)
  python method.py output          build method_out.json (schema exp_gen_sol_out) from data/scored + results/

Order actually run: A reanalysis -> B base, acts, vectors, freeze, calib, freeze2, main -> CPU score_ba ->
C screen_a, screen_b, audit, geometry, confirm, confirm_states, temp, transplant -> analyze (B, C) -> figures -> output.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from common import P4_MENU, RESULTS, SCORED, GENS, read_jsonl, write_json  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "method.log", rotation="30 MB", level="DEBUG")

PY = sys.executable
STAGES = {
    "A": ["src/reanalysis.py"],
    "codestop": ["tests/check_codestop.py"],
    "B_base": ["src/steer_qwen.py", "base", "--batch", "200"],
    "B_acts": ["src/steer_qwen.py", "acts"],
    "B_vectors": ["src/steer_qwen.py", "vectors"],
    "B_freeze": ["src/steer_qwen.py", "freeze"],
    "B_calib": ["src/steer_qwen.py", "calib", "--batch", "200"],
    "B_freeze2": ["src/steer_qwen.py", "freeze2"],
    "B_main": ["src/steer_qwen.py", "main", "--batch", "200"],
    "B_score_ba": ["src/score_ba.py", "2"],
    "B_analyze": ["src/analyze_qwen.py"],
    "C_screen_a": ["src/gemma.py", "screen_a", "--nb", "150", "--npl", "50", "--batch", "75", "--max_new", "768"],
    "C_screen_b": ["src/gemma.py", "screen_b", "--nf", "20", "--nban", "50", "--batch", "75", "--max_new", "768"],
    "C_audit": ["src/audit.py"],
    "C_geometry": ["src/gemma.py", "geometry"],
    "C_confirm": ["src/gemma.py", "confirm", "--nconf", "50", "--batch", "75", "--max_new", "768"],
    "C_confirm_states": ["src/gemma.py", "confirm_states"],
    "C_temp": ["src/gemma.py", "temp", "--ntemp", "40", "--batch", "75", "--max_new", "768"],
    "C_transplant": ["src/gemma.py", "transplant", "--ntr", "30", "--batch", "75", "--max_new", "768"],
    "C_analyze": ["src/analyze_gemma.py"],
    "figures": ["src/figures.py"],
    "verify": ["verify.py"],
}


def run_stage(name: str) -> None:
    cmd = [PY] + STAGES[name]
    logger.info(f"stage {name}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def _load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def build_output() -> None:
    from protocol import user_message  # noqa: F401  (kept for reference of the prompt builder)
    datasets = []
    n_total = 0
    for model in ("qwen", "gemma"):
        for task in ("T1", "T2"):
            gdir = GENS / model / task
            if not gdir.exists():
                continue
            ex = []
            for gp in sorted(gdir.glob("*.jsonl")):
                setting = gp.stem
                if setting == "smoke":
                    continue
                sc = {r["seed"]: r for r in read_jsonl(SCORED / model / task / f"{setting}.jsonl")}
                for g in read_jsonl(gp):
                    s = sc.get(g["seed"])
                    if s is None:
                        continue
                    lab = s["label"]
                    menu = set(P4_MENU[task]) | {"Unparseable"}
                    off = bool(s["oracle_pass"] and lab not in menu)
                    ex.append({
                        "input": g["user_message"], "output": g["text"],
                        "predict_idea_label_v1": lab, "predict_oracle_status": s["oracle_status"],
                        "metadata_task": task, "metadata_model": model, "metadata_condition": setting,
                        "metadata_family": g.get("family", ""), "metadata_seed": g["seed"],
                        "metadata_temperature": g.get("T"), "metadata_topk": g.get("topk"),
                        "metadata_intervention": json.dumps(g.get("iv")) if g.get("iv") else "",
                        "metadata_label_v1": lab, "metadata_oracle_status": s["oracle_status"],
                        "metadata_pass_frac": s["pass_frac"], "metadata_offmenu_correct": off,
                        "metadata_offmenu_correct_excl_builtin": off and lab != "Builtin",
                        "metadata_truncated": g["hit_max"], "metadata_ntoks": g["ntoks"]})
            if ex:
                datasets.append({"dataset": f"{model}_{task}_{'path_search' if task == 'T1' else 'sorting'}",
                                 "examples": ex})
                n_total += len(ex)
    meta = dict(
        method_name="Does steering pick ideas or spread them? Selector steering (Qwen2.5-3B-Instruct) vs matched-norm "
                    "random draws, and a displacement logit for bans (gemma-2-2b-it)",
        models=["Qwen/Qwen2.5-3B-Instruct", "google/gemma-2-2b-it"], n_examples=n_total,
        verdicts=_load(RESULTS / "verdicts.json"),
        A_reanalysis=_summ_A(_load(RESULTS / "reanalysis_contract.json")),
        frozen_hashes={p.name: p.read_text().split()[0] for p in sorted(RESULTS.glob("frozen_*.sha256"))},
        deviations=_load(RESULTS / "deviations.json"),
        audit_cost_usd=_load(RESULTS / "audit.json").get("cost_usd"),
        result_files=sorted(p.name for p in RESULTS.glob("*.json")))
    out = {"metadata": meta, "datasets": datasets}
    (ROOT / "method_out.json").write_text(json.dumps(out))
    logger.info(f"method_out.json: {n_total} examples in {len(datasets)} datasets")


def _summ_A(a: dict) -> dict:
    if not a:
        return {}
    return dict(status=a.get("status"), claim3_verdict=a.get("claim3", {}).get("verdict"),
                claim3_counts_primary=a.get("claim3", {}).get("counts", {}).get(a.get("claim3", {}).get("primary_spec")),
                a4={t: {k: a["a4"][t][k] for k in ("rho", "exact_p_two_sided", "exact_p_one_sided_positive",
                                                   "original_ci", "ci_corrected")} for t in ("T1", "T3")},
                file_counts={t: {k: v for k, v in a["file_counts"][t].items() if k.startswith("n_") or k ==
                                 "gens_without_scored"} for t in ("T1", "T3")})


@logger.catch(reraise=True)
def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "run":
        for st in sys.argv[2:]:
            run_stage(st)
    elif sys.argv[1] == "output":
        build_output()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
