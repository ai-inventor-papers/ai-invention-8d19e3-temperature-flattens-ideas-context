# Reproducing "Does steering pick ideas or spread them?"

This file lists the steps that were actually run, in order. Every path is relative to this folder.

## 1. Get the artifact

This folder is published as one directory of a public GitHub repository:

```bash
git clone <repository-url>
cd <repository>/<this-artifact-folder>        # the folder that contains method.py
```

Some files are **not** in the published repository. They stay on the run's storage volume only:

* `data/acts/`: teacher-forced activations, regenerable with stages `B_acts` and `C_geometry`.
* any single file of 100 MB or more.

## 2. System, Python and libraries

* Ubuntu/Debian with an NVIDIA driver ≥ 580 (CUDA 13 runtime). No C compiler is needed: `src/engine.py`
  disables torch's triton op overrides.
* Hardware actually used: **one NVIDIA RTX 2000 Ada (16 GB VRAM, 70 W power cap)**, 6 CPU cores (cgroup quota
  5.1), 28 GB RAM.
* Python 3.12, managed by `uv`:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

`pyproject.toml` and `requirements.lock.txt` pin every installed package. The key versions are torch 2.14.1,
transformers 4.56.2, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1, sentence-transformers 5.7.0 and openai 3.31.0.
vLLM was **not** used: every generation runs on the HF engine in `src/engine.py`.

## 3. Models, data and secrets

* Models from the HuggingFace Hub, downloaded on first use:
  * `Qwen/Qwen2.5-3B-Instruct`
  * `google/gemma-2-2b-it` (gated: accept the licence and set `HF_TOKEN`)
  * `sentence-transformers/all-MiniLM-L6-v2`, the external-embedding baseline
  * `google/gemma-scope-2b-pt-res`: `params.npz` of one 16k-width layer, Step D only
* Environment variables, by name only: `HF_TOKEN`, plus `OPENROUTER_BASE_URL` and `OPENROUTER_API_KEY` for the
  label audit (`src/audit.py`, model `openai/gpt-4.1-mini`, T=0, hard cap $0.45).
* Inputs from two iteration-1 artifacts of the same run, read-only:
  * the **influence arm** (`gen_art_experiment_3` of iteration 1, art_aSN7z8WuA7Ir), used by Step A;
  * the **ban arm** (`gen_art_experiment_2` of iteration 1), whose vLLM screen generations are reused.
  They are read through the constants `IA` and `BA` in `src/common.py`. By default these resolve relative to this
  folder (`../../../iter_1/gen_art/gen_art_experiment_{3,2}`, the layout of the run). Override them with the
  environment variables `AII_INFLUENCE_ARM_DIR` and `AII_BAN_ARM_DIR`, pointing at the sibling folders of your
  clone. Without them, Step A writes `status: inputs unavailable`.
* No user-uploaded inputs are used.

## 4. Commands, in the order they were run

Set this for every GPU stage:

```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Each stage is resumable: finished seeds are skipped. `python method.py run <stage>` wraps the same commands.

| # | command | what it does | runtime |
|---|---|---|---|
| 0 | `.venv/bin/python tests/test_classifier.py`; `.venv/bin/python tests/test_oracle.py` | classifier fixtures 45/45, oracle 0 failures | 2 min |
| 0a | `.venv/bin/python tests/test_hooks_cpu.py` (CPU) and `.venv/bin/python tests/test_freeze.py` | the prompt patch touches only the last 5 prefill positions; zero-add is a no-op; no hook leaks; a missing or tampered frozen file aborts | 4 min |
| 0b | `.venv/bin/python tests/check_codestop.py` | code-stop check. v1 agreement 0.87 (T1) and 0.967 (T2) is below 0.97, so CodeStop is disabled everywhere | 1 min |
| A | `.venv/bin/python src/reanalysis.py` | Step A → `results/reanalysis_contract.json` | 1 min |
| B1 | `.venv/bin/python src/steer_qwen.py base --batch 200` | HF baseline T=0.7 seeds 0..299 (T1, T2) plus forced IDDFS/Bellman-Ford/Counting/Heap, seeds 0..59 | 8 min |
| B2 | `.venv/bin/python src/steer_qwen.py acts`, then `... vectors` | commitment-window activations, CV probe band, directions → `results/qwen_vectors.pt`, `results/qwen_probe_band.json` | 2 + 6 min |
| B3 | `.venv/bin/python src/steer_qwen.py freeze` | pre-registration → `results/frozen_selector_qwen.json` (+ `.sha256`) | <1 min |
| B4 | `.venv/bin/python src/steer_qwen.py calib --batch 200`, then `... freeze2` | n=30 calibration → `results/frozen_selector_qwen_alphas.json` (+ `.sha256`) | 6 min |
| B5 | `.venv/bin/python src/steer_qwen.py main --batch 200` | main sweep: targeted ×2 draws, 5 random draws per strength, off-target, d_j, temperatures | ~40 min |
| B* | `.venv/bin/python src/score_ba.py 2` | v1 + oracle on the iteration-1 vLLM screen (CPU) | 10 min |
| C1 | `.venv/bin/python src/gemma.py screen_a --nb 150 --npl 50 --batch 75 --max_new 768` | gemma baseline + placebo triplicate | 17 min |
| C1b | `.venv/bin/python src/gemma.py screen_b --nf 20 --nban 50 --batch 75 --max_new 768` | ranks r1..r8, forced top-8, screen bans | ~26 min |
| C2 | `.venv/bin/python src/gemma.py geometry` | window acts, probe band, prompt states, fits → frozen `results/frozen_gemma_bans.json` | ~6 min |
| C3 | `.venv/bin/python src/gemma.py confirm --nconf 50 --batch 75 --max_new 768`, then `... confirm_states` | held-out bans r5..r8 plus 3 random pairs per task, seeds 1000..1049 | ~20 min |
| C5 | `.venv/bin/python src/gemma.py temp --ntemp 40 --batch 75 --max_new 768` | T 0.3/1.0/1.3 and T1.0 top-k 10 (T0.7 = baseline seeds 0..39) | ~9 min |
| C4 | `.venv/bin/python src/gemma.py transplant --ntr 30 --batch 75 --max_new 768` | Δh transplant/subtraction vs 3 random displacements | ~13 min |
| C* | `.venv/bin/python src/audit.py` | 100-program blind judge audit (OpenRouter) | 2 min |
| D | `CUDA_VISIBLE_DEVICES="" .venv/bin/python src/sae_describe.py` | Gemma Scope SAE description on CPU. Run during C3 and re-run after the gemma analysis so the neighbour sets exist | 3 min |
| final | `./run_final.sh` | `analyze_qwen` → `analyze_gemma` → `verdicts` → `figures` → `method.py output` → `verify.py` → aii-json validation and full/mini/preview (needs `AII_JSON_SKILL_DIR`) | 4 min |

`run_chain1.sh` (B2 acts, then the gemma smoke test) and `run_chain2.sh` (B3 → C4) are the shell chains that actually
ran. Between them, `src/steer_qwen.py vectors` ran on the CPU with 3 single-threaded, niced workers, and gemma
`screen_a` ran on the GPU. Total wall clock was about 4.5 h:

* Qwen: about 7,300 generations at 130–140 per minute (batch 200, 768 tokens).
* gemma: about 3,200 generations at 32–36 per minute (batch ≤ 75, 768 tokens, eager attention).

**Seeds.** Sample *s* uses `torch.Generator().manual_seed(s)` uniforms through the inverse-CDF sampler (common random
numbers across conditions). The other seeds:

* random steering directions: `numpy.random.default_rng(777+k)`, k = 0..4
* gemma random ban pairs: rng 1000
* transplant random displacements: `torch.Generator().manual_seed(4242+k)` for T1 and `4342+k` for T2
* Step A bootstrap: rng 20261016
* Batches never mix prompt-token lengths. Results are reproducible up to bf16 batch-composition effects (iteration 1
  measured 11–17% label flips).

## 5. Expected outputs

* `results/reanalysis_contract.json`: Step A claim-3 counts and verdict, plus the A4 exact permutation p.
* `results/selector_tables.json`: the per-task SELECT/FLATTEN/MIXED verdict on both draws, entropy versus the
  draw-averaged random entropy (hierarchical CI), the prompting ceiling, C4 and engine consistency.
* `results/gemma_bans.json`: the screen, held-out JSD for IIA / IIA+compliance / GEOM / EXT, top-substitute and sign
  accuracy, and regularity.
* `results/gemma_temperature.json`, `results/transplant.json`, `results/audit.json` and `results/sae_latents.json`.
* `results/verdicts.json` gathers every verdict, and `results/verify.json` holds the independent re-derivation.
* `figs/*.png|pdf`.

The headline numbers are listed in `README.md`.

### Key numbers a reader should get

These are reproducible up to bf16 batch effects:

* **Step A:** 3/18 targeted settings beat the draw-averaged random entropy, 5/18 fall below it and 10/18 are
  undetermined. A4 exact permutation p is 0.36 (T1) and 0.66 (T3).
* **Qwen T1:** SELECT on both draws. A\* reaches 0.57 and 0.63 at α = 0.224, with pass 0.17. Entropy minus the
  random-draw mean is +0.32 bits (main draw).
* **Qwen T2:** SELECT on both draws. Quick reaches 0.65 and 0.68 at α = 0.473, with pass 0.92. Entropy minus the
  random-draw mean is −0.71 and −0.73 bits.
* **Prompting ceiling:** d_j produces 0–1% of IDDFS, Bellman-Ford or Counting, against 92–100% from the forced
  prompt. d_Heap gives 91% heap sort.
* **gemma held-out bans:** mean JSD is 0.088 for IIA, 0.093 for EXT and 0.121 for GEOM (gain −0.71), so C2a and C2b
  fail. Regularity is violated in 1 of 72 cells.
* **Transplant:** recovery is 0.42 on T1 (CI spans 0) and 0.06 on T2, so C2c fails. SAE FVU is 0.61 (unreliable).
* **Audit:** κ = 0.39 on T1 (label-limited) and 0.94 on T2. Cost $0.02.
* `method_out.json` is 31 MB (9,720 examples, schema `exp_gen_sol_out`). It is under the 100 MB limit, so no split
  was needed.
