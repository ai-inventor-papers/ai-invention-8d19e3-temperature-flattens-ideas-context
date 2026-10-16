#!/usr/bin/env python3
"""Bans as nudges to the idea state: pipeline driver + method_out.json assembly.

Method (B, 'displacement'): Delta_h = h(ban prompt) - h(placebo prompt) at the 5 aligned chat-template suffix
tokens (band layers chosen by a probe on unbanned data), projected on idea centroids, enters a one-scalar logit
that reweights the unbanned share. Baselines: A IIA renormalisation of the placebo (econometric null),
C iteration-1 nested geometry, D/D2 external bge text embeddings, D3 Qwen name-embedding lexical, E co-mention.
All share the same smoothing floor and compliance model and one scalar fitted by leave-one-ban-out on the screen,
then are FROZEN (sha256 + git commit) before any confirmation generation. Causal test: suffix transplant of
Delta_h with HF hooks vs 5 matched-norm random draws and an off-target real displacement.

Pipeline (each step is resumable; see README.md):
  python method.py run            # all stages in order (GPU + CPU), skipping finished ones
  python method.py assemble       # build method_out.json from the saved results
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
(ROOT / "logs").mkdir(exist_ok=True)
logger.add(ROOT / "logs" / "method.log", rotation="30 MB", level="DEBUG")
PY = sys.executable

STAGES = [
    ("setup_check", [PY, "src/setup_check.py"]),
    ("jobs_forced", [PY, "src/jobs.py", "forced"]),
    ("gen_forced", [PY, "src/gen_vllm.py", "--jobs", "data/conf/jobs_forced.json"]),
    ("label_forced", [PY, "src/label_conf.py"]),
    ("states_screen", [PY, "src/states.py", "screen"]),
    ("fit_and_freeze", [PY, "src/fit.py"]),
    ("jobs_conf", [PY, "src/jobs.py", "conf_nonban"]),
    ("gen_conf_nonban", [PY, "src/gen_vllm.py", "--jobs", "data/conf/jobs_conf_nonban.json", "--frozen",
                         "results/frozen_predictors.json"]),
    ("label_conf_nonban", [PY, "src/label_conf.py"]),
    ("jobs_bans", [PY, "src/jobs.py", "conf_bans"]),
    ("states_conf_prompts", [PY, "src/states.py", "prompts", "--jobs", "data/conf/jobs_conf_nonban.json", "--out",
                             "acts/prompt_states_conf_nonban"]),
    ("states_conf_prompts_b", [PY, "src/states.py", "prompts", "--jobs", "data/conf/jobs_conf_bans.json", "--out",
                               "acts/prompt_states_conf_bans"]),
    ("states_conf_windows", [PY, "src/states.py", "conf", "--layers", "32,33,34"]),
    ("freeze_predictions", [PY, "src/predict_conf.py", "t1t3"]),
    ("t4_plan", [PY, "src/predict_conf.py", "t4plan"]),
    ("judge_t4", [PY, "src/judge_t4.py"]),
    ("jobs_t4", [PY, "src/jobs.py", "t4_bans"]),
    ("states_t4_prompts", [PY, "src/states.py", "prompts", "--jobs", "data/conf/jobs_t4_bans.json", "--out",
                           "acts/prompt_states_conf_t4bans"]),
    ("freeze_t4", [PY, "src/predict_conf.py", "t4"]),
    ("jobs_all_bans", [PY, "-c", "import json; json.dump(json.load(open('data/conf/jobs_conf_bans.json')) + "
                       "json.load(open('data/conf/jobs_t4_bans.json')), open('data/conf/jobs_all_bans.json', 'w'), indent=1)"]),
    ("gen_bans", [PY, "src/gen_vllm.py", "--jobs", "data/conf/jobs_all_bans.json", "--frozen",
                  "results/frozen_predictors.json", "results/frozen_predictions.json", "results/frozen_predictions_T4.json"]),
    ("label_bans", [PY, "src/label_conf.py"]),
    ("states_band", [PY, "src/states.py", "band", "--layers", "32,33,34"]),
    ("states_conf_windows_b", [PY, "src/states.py", "conf", "--layers", "32,33,34"]),
    ("transplant_test", [PY, "src/transplant.py", "test"]),
    ("transplant", [PY, "src/transplant.py", "run", "--n", "60"]),
    ("transplant_knockout", [PY, "src/transplant.py", "run", "--n", "60", "--batch", "120", "--only", "knockout"]),
    ("score", [PY, "src/score.py"]),
    ("analysis", [PY, "src/analysis.py", "all"]),
    ("verify", [PY, "verify_headline.py"]),
]


def run_all() -> None:
    for name, cmd in STAGES:
        logger.info(f"=== stage {name}: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=ROOT, check=True)


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def assemble() -> None:
    res = ROOT / "results"
    fz = json.loads((res / "frozen_predictors.json").read_text())
    fp = json.loads((res / "frozen_predictions.json").read_text())
    f4 = json.loads((res / "frozen_predictions_T4.json").read_text())
    tasks = dict(fp["tasks"])
    tasks["T4"] = dict(classes=f4["classes"], conditions=f4["conditions"])
    datasets = []
    for t in ("T1", "T2", "T3", "T4"):
        K = tasks[t]["classes"]
        ex = []
        for p in sorted((ROOT / "data" / "conf" / "gen" / t).glob("*.jsonl")):
            cond = p.stem
            lp = ROOT / "data" / "conf" / "labels" / t / p.name
            if not lp.exists() or "__mini" in cond:
                continue
            labs = {r["id"]: r for r in load_jsonl(lp)}
            pred = tasks[t]["conditions"].get(cond, {}).get("pred")
            for r in load_jsonl(p):
                lab = labs[r["id"]]
                e = {"input": r["user_message"], "output": lab["label"]}
                if pred:
                    j = K.index(lab["label"])
                    e["predict_iia"] = f"{pred['A'][j]:.6f}"
                    e["predict_disp"] = f"{pred['B'][j]:.6f}"
                    e["predict_embed"] = f"{pred['D'][j]:.6f}"
                    e["predict_lexical"] = f"{pred['D3'][j]:.6f}"
                    e["predict_nested"] = f"{pred['C'][j]:.6f}"
                    e["predict_comention"] = f"{pred['E'][j]:.6f}"
                e.update(metadata_task=t, metadata_condition=cond, metadata_seed=r["seed"],
                         metadata_banned=r.get("banned") or [], metadata_engine=r.get("engine", "vllm"),
                         metadata_finish_reason=r.get("finish_reason"),
                         metadata_oracle=dict(passed=lab.get("oracle_pass"), status=lab.get("oracle_status"),
                                              pass_0idx=lab.get("oracle_pass_0idx")),
                         metadata_role=("placebo_block" if cond.startswith("placebo_b") else
                                        "screen_extension" if cond.startswith("forced_") and t != "T4" else
                                        "t4_screen" if t == "T4" and (cond in ("baseline", "comention") or cond.startswith("forced_"))
                                        else "confirmation"))
                ex.append(e)
        datasets.append(dict(dataset=f"qwen2.5-3b-instruct_{t}_confirmation_generations", examples=ex))
        logger.info(f"{t}: {len(ex)} examples")
    sc = json.loads((res / "predictor_scores_conf.json").read_text())
    reg = json.loads((res / "regularity.json").read_text())
    tr = json.loads((res / "transplant.json").read_text()) if (res / "transplant.json").exists() else {}
    scr = json.loads((res / "predictor_scores_screen.json").read_text())
    audit = json.loads((res / "t4_classifier_audit.json").read_text())
    edge = json.loads((res / "edge_stat.json").read_text()) if (res / "edge_stat.json").exists() else {}
    g = sc["c2b"].get("T1T2T3_bans", {})
    meta = dict(
        method_name="Prompt-suffix displacement predictor of idea bans (Qwen2.5-3B-Instruct)",
        model="Qwen/Qwen2.5-3B-Instruct", engine_note="All screen + confirmation generations: vLLM 0.31.0 (bf16, "
        "T=0.7, top-p 1, top-k off, max_tokens 768, per-request seed). Transplant cells: HF transformers custom "
        "KV-cached loop with common-random-number sampling, CodeStop on, max_new 640; compared only with same-engine "
        "HF references.",
        frozen_hashes=dict(frozen_predictors=(res / "frozen_predictors.sha256").read_text().strip(),
                           frozen_predictions=(res / "frozen_predictions.sha256").read_text().strip(),
                           frozen_predictions_T4=(res / "frozen_predictions_T4.sha256").read_text().strip()),
        frozen=dict(band=fz["band"], variant=fz["variant"], beta=fz["beta"], eps=fz["eps"], kappa=fz["kappa"],
                    massive_dims=fz["massive_dims"]),
        verdicts=dict(
            C2a=dict(verdict="PASS" if reg["c2a_pass"] else "FAIL", violating_bans=reg["c2a"]["violating_bans"],
                     n_violating_cells=reg["c2a"]["n_violations"], n_cells=reg["c2a"]["n_cells"],
                     false_positive_cells_placebo_checks=reg["false_positive_check"]["n_violations"],
                     sign_acc_B=reg["sign"]["B"]["sign_acc"], balanced_sign_acc_B=reg["sign"]["B"]["balanced_sign_acc"],
                     sign_acc_IIA=reg["sign"]["A"]["sign_acc"], balanced_sign_acc_IIA=reg["sign"]["A"]["balanced_sign_acc"]),
            C2b=dict(verdict="PASS" if sc["c2b_pass"] else "FAIL",
                     mean_jsd=dict((k, g.get(k, {}).get("mean_jsd")) for k in ("A", "B", "C", "D", "D2", "D3", "E")),
                     B_vs_A_rel_reduction=g.get("B_vs_A_rel_jsd_reduction"), top_hit_B=g.get("B", {}).get("top_hit_rate"),
                     B_minus_D=g.get("B_minus_D_jsd"), B_minus_D2=g.get("B_minus_D2_jsd")),
            C2c=dict(verdict="PASS" if tr.get("c2c_pass") else ("FAIL" if tr else "NOT RUN"), summary=tr.get("summary"),
                     secondary=dict((b, dict((c, e.get(c)) for c in ("SUFFIX_CEILING", "ALLPOS", "TRANSPLANT_L8",
                                                                      "TRANSPLANT_L18", "KNOCKOUT_BAN", "KNOCKOUT_PLACEBO_SENT")
                                             if c in e)) for b, e in tr.get("bans", {}).items()),
                     interpretation="Suffix-state transplant, restore, suffix ceiling (all 35 layers) and Stolfo-style "
                                    "all-position add all recover ~0; a decode-time attention knockout of the ban sentence "
                                    "(added after pre-registration, exploratory) restores placebo behaviour: the ban is read "
                                    "from the sentence tokens during generation, not from the prompt-final state (fallback F5).")),
        screen_vs_confirmation=sc["screen_vs_confirmation"], screen_chosen_variant=scr["chosen_variant"],
        t4_classifier_audit=dict(kappa=audit["cohen_kappa"], agreement=audit["agreement"], n=audit["n_judged"],
                                 accept=audit["accept"], cost_usd=audit["cost_usd"]),
        edge_stat_overall=edge.get("overall"), edge_stat_top5=edge.get("top5_summary"),
        notes=["Screen fits use the stored iteration-1 v1 labels (relabel check 200/200), which are under a parallel audit.",
               "Predictors were frozen with sha256 + git commit before any confirmation generation; per-condition "
               "predictions were frozen before any confirmation BAN was generated (gen scripts assert all hashes).",
               "beta for B was selected at 19.75 on a pre-registered grid [-20, 20]: near the grid edge; reported as is.",
               "Single model family (Qwen2.5-3B-Instruct); one prompt wording per confirmation ban.",
               "Probe band selection used generated-window probes on baseline+forced samples; the probe score is high at "
               "every layer (forced prompts make classes separable), so the band choice (32-34) is weakly determined.",
               "Exploratory additions beyond the plan: KNOCKOUT_BAN / KNOCKOUT_PLACEBO_SENT transplant cells (4 bans, n=60).",
               "No plan cuts were needed (all pairs, T4, controls, transplant n=60 with 5 random draws were run)."],
        predict_fields="predict_* = frozen predicted probability of the OBSERVED label under each predictor "
                       "(iia=A, disp=B, embed=D, lexical=D3, nested=C, comention=E); absent for placebo blocks, T4 "
                       "baseline/forced/comention.")
    out = dict(metadata=meta, datasets=datasets)
    (ROOT / "method_out.json").write_text(json.dumps(out, indent=1))
    logger.info(f"method_out.json written ({sum(len(d['examples']) for d in datasets)} examples)")


if __name__ == "__main__":
    {"run": run_all, "assemble": assemble}[sys.argv[1]]()
