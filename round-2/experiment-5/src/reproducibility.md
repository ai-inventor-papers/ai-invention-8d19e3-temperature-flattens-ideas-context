# Reproducibility

This document describes what was actually run, in order, on 2026-10-16.

## 1. Get the artifact

This workspace is published as one folder of a public GitHub repository:

```bash
git clone <repository-url>
cd <repository>/gen_art_experiment_5     # this folder
```

The iteration-1 inputs this artifact builds on are already **copied** into this folder: `data/gen`, `data/labels`,
`data/ban_plan*.json`, and `src/{protocol,classify,label,oracle,oracle_harness,activations,geometry,generate,engine,acts_io}.py`.
They came from the ban arm (`iter_1/gen_art/gen_art_experiment_2`) and the influence arm (`art_aSN7z8WuA7Ir`,
`round-1/experiment-3/src`), and their sha256 hashes are in `manifest_inputs.json`. Nothing outside this
folder is read. No user-uploaded data is used.

## 2. System and Python environment

- Ubuntu (Linux 6.8). One NVIDIA L4 (24 GB VRAM), 48 CPU cores. There was no system C compiler. `tools/cc` is a
  ziglang shim that `src/gen_vllm.py` exports as `CC` for Triton.
- Python 3.12.14 and `uv`.
- Pinned versions are in `pyproject.toml` (exact `uv pip freeze` of the venv used). Key versions: vllm 0.31.0,
  torch 2.13.0 (+cu130), transformers 5.17.0, sentence-transformers 6.1.0, numpy 2.3.5, scikit-learn, scipy,
  umap-learn, ziglang 0.17.0.

```bash
uv venv .venv --python=3.12
uv pip install --python .venv/bin/python -r pyproject.toml
```

## 3. Downloads and keys

- Models (Hugging Face Hub, downloaded on first use): `Qwen/Qwen2.5-3B-Instruct` and `BAAI/bge-base-en-v1.5`.
- Environment variables, by name only:
  - `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL`: used only by `src/judge_t4.py`, the T4 classifier audit with
    `openai/gpt-4.1-mini` (cost $0.015).
  - `HF_HOME` (optional): the Hugging Face cache location.

## 4. Commands, in the order they were run

`python` below means `.venv/bin/python`. All seeds are fixed in the code:
- vLLM per-request seeds: 1000–1029 for the forced extension; 1000–1099, 2000–2099 and 3000–3099 for the placebo
  blocks; 1000–1099 for confirmation conditions; 1000–1299 for the T4 baseline.
- Transplant seeds 1000–1059, with common random numbers.
- Random-direction seeds 778–782.
- Random-pair RNG seeds 20261016 (T1/T2) and 20261017 (T4).

| # | Command | What | Approx. time (L4) |
|---|---|---|---|
| 0 | `python src/setup_check.py` | prompt byte-equality 67/67, suffix identity, tests (v1 fixtures, oracle, 22 T4 fixtures + 6 oracle cases), relabel 200/200 | 5 min |
| 1 | `python src/jobs.py forced && python src/gen_vllm.py --jobs data/conf/jobs_forced.json` | forced extension, 810 gens | 4 min |
| 2 | `python src/label_conf.py` | v1 labels + oracle | 2 min |
| 3 | `python src/states.py screen` | prompt-suffix states + generated windows (HF) | 7 min |
| 4 | `python src/fit.py` | probe band sweep (630 probe fits, ~26 min on CPU), centroids, predictors, LOBO, **FREEZE** (git commit) | 30 min |
| 5 | `python src/jobs.py conf_nonban && python src/gen_vllm.py --jobs data/conf/jobs_conf_nonban.json --frozen results/frozen_predictors.json` | placebo blocks, alt placebo, mentions, T4 baseline/forced/comention (2,430 gens) | 9 min |
| 6 | `python src/label_conf.py` | labels + oracle | 2 min |
| 7 | `python src/jobs.py conf_bans`; `python src/states.py prompts --jobs data/conf/jobs_conf_nonban.json --out acts/prompt_states_conf_nonban`; same for `jobs_conf_bans.json` → `acts/prompt_states_conf_bans`; `python src/states.py conf --layers 32,33,34` | confirmation prompt states, T4 windows | 5 min |
| 8 | `python src/transplant.py test`; `python src/transplant.py mini --n 16 --batch 48` | hook tests (`results/transplant_hook_tests.json`), mini run | 4 min |
| 9 | `python src/predict_conf.py t1t3` | **FREEZE** per-condition predictions | 2 min |
| 10 | `python src/judge_t4.py`; `python src/predict_conf.py t4plan`; `python src/jobs.py t4_bans`; `python src/states.py prompts --jobs data/conf/jobs_t4_bans.json --out acts/prompt_states_conf_t4bans`; `python src/predict_conf.py t4` | T4 audit, plan, **FREEZE** T4 predictions | 6 min |
| 11 | concatenate `jobs_conf_bans.json` + `jobs_t4_bans.json` → `data/conf/jobs_all_bans.json`; `python src/gen_vllm.py --jobs data/conf/jobs_all_bans.json --frozen results/frozen_predictors.json results/frozen_predictions.json results/frozen_predictions_T4.json` | all confirmation bans (3,500 gens) | 12 min |
| 12 | `python src/label_conf.py`; `python src/states.py band --layers 32,33,34`; `python src/states.py conf --layers 32,33,34` | labels, windows | 6 min |
| 13 | `python src/transplant.py run --n 60 --batch 120` | primary, random, secondary and sweep transplant cells (3,780 gens) | 32 min |
| 14 | `python src/transplant.py run --n 60 --batch 120 --only knockout` | exploratory decode-time attention knockout (480 gens) | 6 min |
| 15 | `python src/score.py`; `python src/analysis.py edge`; `python src/analysis.py lens`; `python src/analysis.py manifold`; `python src/analysis.py transplant`; `python src/analysis.py figures` | scoring, analyses, figures | 15 min |
| 16 | `python verify_headline.py > results/verify_headline.txt`; `python method.py assemble` | independent re-derivation; `method_out.json` | 3 min |

`python method.py run` runs the same stages in order. Every stage is resumable and skips finished files.

vLLM sampling is not bit-reproducible across runs (2/20 in iteration 1). Regenerated text will therefore differ sample
by sample, and the distributions should agree within the placebo noise floor. The HF transplant uses deterministic
per-seed uniforms, so with the same GPU, kernels and batch composition it reproduces token for token.

## 5. Expected outputs

| Number | Value | File |
|---|---|---|
| Frozen band / variant / β | layers 32–34, G-centroid × suffix, β = 19.75 | `results/frozen_predictors.json` (sha256 a669710b…) |
| Screen LOBO mean JSD, IIA vs B | 0.1915 vs 0.1830 | `results/predictor_scores_screen.json` |
| C2a regularity violations | 6 bans, 8/46 cells; 0/45 placebo-vs-placebo; 0 in 20 shuffled reps | `results/regularity.json`, `results/verify_headline.txt` |
| Sign accuracy, B vs IIA | 0.827 vs 0.654 (balanced 0.789 vs 0.500), 52 cells | `results/regularity.json` |
| C2b, T1–T3 mean JSD A / B / D / D2 | 0.207 / 0.188 / 0.221 / 0.217; B vs A reduction 9.2% [−0.6%, 19.6%] | `results/predictor_scores_conf.json` |
| T4 transfer B vs A | −25% (B worse) | `results/predictor_scores_conf.json` |
| C2c mean recovery, transplant / random | −0.001 / −0.006 (FAIL) | `results/transplant.json` |
| Knockout restoration (exploratory) | 0.72 mean over 4 bans | `results/transplant.json` |
| T4 classifier audit | κ = 0.79, agreement 0.82, n = 60 | `results/t4_classifier_audit.json` |

The figures are in `figures/`. The paper's figures map one-to-one:
- manifold → `manifold_T1_pca`, `manifold_T2_pca`
- predictors → `predictor_jsd_bars`
- regularity → `regularity_forest`
- causal → `transplant_recovery`
