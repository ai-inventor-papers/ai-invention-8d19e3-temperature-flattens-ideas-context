# Reproducing the influence-arm experiment

These are the steps that were actually run, in order. Every path is relative to this folder.

## 1. Get the artifact

This folder is published as one directory of a public GitHub repository:

```bash
git clone <repository-url>
cd <repository>/<this-artifact-folder>      # the folder that contains method.py
```

Two large outputs are **not** in the published repository. They stay on the run's storage volume only:

* `acts/`: cached baseline residuals, 0.9 GB, stored as `baseline_{T1,T3}_part_001..006.npy` (each under 100 MB,
  read by `src/acts_io.py`)
* `caps/`: residuals captured during steered generation, 0.9 GB

Stage 2 (`acts`) regenerates `acts/` from the generations, which are published in `gens/`. The sweep and
held-out stages regenerate `caps/`. The intervention vectors (`vectors/vectors.pt` and `vectors/leace_{T1,T3}.pt`)
are published.

## 2. System, Python and libraries

* Ubuntu or Debian (ran on Debian 12) with NVIDIA driver ≥ 580 (CUDA 13 runtime).
* Hardware used: one NVIDIA RTX PRO 4500 Blackwell (32 GB VRAM), 24 CPU cores, 57 GB RAM (container limit).
* Python 3.12 managed by `uv` (uv 0.6.14). No system packages beyond the NVIDIA driver are needed. No C compiler
  is needed either, because `src/engine.py` disables torch 2.14's triton-backed op overrides.

```bash
uv venv .venv --python=3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

`requirements.lock.txt` and `pyproject.toml` pin every installed package. The key versions are torch 2.14.1,
transformers 4.56.2, concept-erasure, scikit-learn, numpy, scipy and openai.

## 3. Model, data and secrets

* Model: `Qwen/Qwen2.5-3B-Instruct` from the HuggingFace Hub. It downloads on first use; you can prefetch it with
  `.venv/bin/huggingface-cli download Qwen/Qwen2.5-3B-Instruct`.
* Data: none is downloaded. All data are the model's own generations on the fixed prompts in
  `protocol/prompts.py`. The oracle graphs are generated from seed 12345 (`protocol/oracle.py`).
* The LLM judge (stage `judge`) needs the environment variables `OPENROUTER_BASE_URL` and `OPENROUTER_API_KEY`.
  It calls `openai/gpt-4.1-mini` at temperature 0, has a $1.5 cap in code, and cost $0.081 in total.
* No user-uploaded inputs are used.

## 4. Commands, in the order they were run

Set this for every GPU stage. It was in effect from the sweep restart onwards; it changes only the CUDA allocator,
not the numerics.

```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

| # | command | what it does | runtime |
|---|---|---|---|
| 0 | `python3 tests/test_protocol.py` and `.venv/bin/python tests/test_engine.py` | classifier, oracle, sampler and hook tests | ~3 min |
| 1 | `.venv/bin/python method.py baseline --batch 192` | T=0.7, seeds 0..299 on T1 and T3, then score; writes menus and ban-3 text to `results/context.json` | ~5 min |
| 2 | `.venv/bin/python method.py acts` | teacher-forced residual cache → `acts/` | ~2 min |
| 3 | `.venv/bin/python method.py probes --workers 20` | per-layer idea probes → `results/probe_curve.json`, band = layers 29–31 | ~2 min |
| 4 | `.venv/bin/python method.py vectors` | all vectors and controls (random seed 777), A4 direction → `vectors/vectors.pt` + `vectors/leace_{T1,T3}.pt`, `results/vector_checks.json` | ~3 min |
| 5 | `.venv/bin/python method.py calib --batch 200` | n=20 strength calibration → frozen `results/calibration.json`, `results/rules.json` | ~4 min |
| 6 | `.venv/bin/python method.py sweep --batch 200 --n_main 150 --n_ctrl 75` | full sweep with seeds 0..149 (controls 0..74), then generate-then-select | ~65 min |
| 7 | `./run_post.sh` | judge → select → heldout (seeds 1000..1099) → judge → analyze | ~25 min |
| 8 | `.venv/bin/python method.py explore --batch 200 --n_main 150` | post-hoc low-α H settings, excluded from survival | ~5 min |
| 9 | `.venv/bin/python score_backlog.py` | scores 2 held-out files whose scoring thread crashed on a malformed return (oracle since fixed) | ~1 min |
| 10 | `.venv/bin/python method.py judge && .venv/bin/python method.py analyze` | final judge pass, then the analysis → `results/results.json`, `figs/`, `method_out.json` | ~6 min |
| 11 | `.venv/bin/python verify_headline.py` | independent re-derivation and placebo tests → `results/verify_headline.json` | ~4 min |
| 12 | `aii_json_format_mini_preview.py --input method_out.json` | `full_`, `mini_` and `preview_method_out.json` | <1 min |
| 13 | `.venv/bin/python tests/test_acts_split.py` | checks the split activation cache (written as single `.npy` files during the original run, split afterwards with a bitwise check) | ~2 min |

Notes on what actually happened:

* The first launch of step 6 was stopped after about 2,400 generations because of CUDA allocator thrashing.
  It was relaunched with the same command and the env var above, and resumed from the per-setting jsonl files.
* The example field `predict_temp2.0` in `method_out.json` was renamed to `predict_temp2p0` so that it matches the schema.
* Seeds: sample *i* uses `torch.Generator().manual_seed(i)`; generate-then-select stage 2 uses *i* + 100000.
  Generations are reproducible up to bf16 batch-composition effects. Re-generating the baseline in other batches
  changes 11–17% of idea labels (setting `crn_rerun`).

## 5. Expected outputs and numbers

* `results/results.json` → `survival.survivors` is `[]`, and the headline is "prompting ceiling".
* Pooled pass rate and idea entropy (`settings.<name>.pooled`):
  * baseline: 0.53 / 1.05
  * prompt_ban3: 0.43 / 1.59 (best eligible)
  * gts: 0.26 / 2.56
  * Hdim_a0.05: 0.57 / 1.06
  * A4_a0.356: 0.47 / 1.37
* Held-out H-dim/temperature entropy ratio is 0.93 (T1) and 1.20 (T3); the rule required ≥ 2.
* A4 Spearman is 0.49 (T1) and −0.26 (T3).
* Judge-confirmed novel-and-correct share is 0 everywhere. Classifier audit: κ = 0.68, agreement 0.715,
  n = 200.
* `results/verify_headline.json`:
  * the independent oracle agrees with the stored pass/fail on 147/147 sampled programs
  * the coarse classifier agrees 97%
  * the placebo baseline-vs-rerun entropy CIs include 0 on both tasks
* Figures: `figs/fig_pareto_entropy.png` (main result), `fig_probe_curve.png`, `fig_a4_dose.png`,
  `fig_idea_shares.png`, `fig_pca_manifold.png`, `fig_violin_frac_correct.png`, `fig_pareto_offmenu.png` and
  `fig_pareto_outside.png`.
