# Bans as nudges to the idea state (Qwen2.5-3B-Instruct)

When you tell an LLM "Implement a path search algorithm. **Do not use BFS.**", what does it build instead, and why?
This experiment tests one explanation. The ban moves the model's internal "idea state". The direction of that move,
read at the prompt's final chat-template tokens, should predict which alternative ideas gain share. The experiment
also tests whether that move causes the behaviour.

Model: `Qwen/Qwen2.5-3B-Instruct` (bf16). Tasks: T1 "Implement a path search algorithm in Python", T2 "Implement a
sorting algorithm", T3 "shortest path in a weighted graph", and the reserved task T4 "k-th smallest element in a list"
(new classifier and execution oracle). Ideas are labelled by a rule classifier (v1, plus v1+T4 for T4) and checked by an
execution oracle.

## What was done

1. **Screen (iteration 1, copied and verified).** 27 ban conditions on T1–T3 with stored v1 labels: prompts are
   byte-identical and 200/200 relabels agree. A forced extension adds 810 vLLM generations (40 per idea).
2. **Activations.** `Δh = h(ban) − h(placebo)` at the 5 aligned suffix tokens `<|im_end|>\n<|im_start|>assistant\n`
   (and the user-span mean). Generated-window means at the idea commitment token. The layer band (32–34) was chosen by a
   probe against shuffled labels on unbanned data.
3. **Seven predictors, one scalar each**, all sharing the same floor and compliance model, fitted by
   leave-one-ban-out on the screen: A IIA (Luce renormalisation), **B Δh displacement (the method)**, C iteration-1
   nested geometry, D/D2 bge text embeddings (names and descriptions, or prompt difference), D3 Qwen name-embedding
   lexical, and E co-mention.
4. **Freeze.** The predictors were frozen (sha256 + git commit) *before* any confirmation generation. The per-condition
   predicted distributions were frozen *before* any confirmation ban was generated, and every generation script asserts
   the hashes.
5. **Confirmation (never-generated conditions, n=100 each).** T1/T2 rank-5..8 single bans, 6 random pairs per task,
   T3 SPFA/BFS, 3 placebo blocks per task, an alternative placebo, "You may use X" mention controls, cross-domain bans,
   and T4: baseline, forced, comention, rank 1–4/top3/top5/rare bans and 4 pairs, as pure transfer. 5,930 vLLM
   generations in total.
6. **Causal transplant (HF hooks, custom KV-cached loop, common random numbers, n=60 per cell).**
   - The primary cells: `placebo + Δh` and `ban − Δh` at the suffix, at layer 32, during prefill only.
   - Controls: 5 matched-norm random draws and an off-target real Δh.
   - Secondary cells: a suffix ceiling (suffix residual overwritten at all 35 layers), a Stolfo-style add at all
     positions, and a layer sweep (layers 8 and 18).
   - Exploratory: a decode-time attention knockout of the ban sentence.
7. **Analyses.**
   - Regularity (Fisher, Holm and a triplicated-placebo noise floor), plus the same test placebo-vs-placebo.
   - Sign accuracy, plain and balanced, and the edge-vs-far-side statistic with a permutation null.
   - Logit lens of Δh, the priming decomposition, and the PCA/UMAP manifold.

## Headline results (all independently re-derived by `verify_headline.py`, output in `results/verify_headline.txt`)

| Claim | Result | Verdict |
|---|---|---|
| C2a regularity violations (removing an option *lowers* another option's share) | 6 bans (T1 Bellman-Ford, Greedy best-first, IDDFS; T2 Counting, Radix, Shell), 8/46 cells; 0/45 on placebo-vs-placebo; 0 in 20 shuffled-label reps | **PASS** |
| Sign of share changes (≥10pp cells, n=52) | B 0.83 (balanced 0.79) vs IIA 0.65 (balanced 0.50) | PASS (target 0.70) |
| C2b: B vs IIA mean JSD on T1–T3 confirmation bans (22) | 0.188 vs 0.207, a 9.2% reduction, 95% CI [−0.6%, 19.6%]; top-substitute hit 0.20 | **FAIL** (target 20%, 70%) |
| B vs external bge embedding (D) / prompt embedding (D2), T1–T3 | B better by 0.033 / 0.029 JSD; neither CI includes 0 | B beats both |
| T4 pure transfer | B *worse* than IIA (−25%) | FAIL |
| C2c suffix transplant recovery (6 bans) | mean R = −0.001; random 5-draw mean −0.006; suffix ceiling 0.01/0.04; all-position add 0.08/−0.03 | **FAIL** |
| Exploratory: decode-time knockout of the ban sentence | mean restoration 0.72 (4 bans; the banned ideas come back) | the ban is read from the sentence tokens during generation |

Other findings:
- **Rare bans move the whole distribution.** Banning greedy best-first, a near-zero-rate idea, moves A* from about 3%
  to 58% and BFS from 63% to 23%. The IIA null cannot produce this.
- **Logit lens.** The top tokens of Δh are "while / although / another / nouvel" (that is, "do something else"). The
  banned name ranks around 17,600 (median), so there is no Stolfo-style priming in the suffix Δh.
- **Mention controls.** "You may use X" pushes the model strongly toward X: A* rises from 3% to 95%, and merge sort
  from 15% to 100%. B predicts the direction 4/4.
- **Priming decomposition.** The ban and mention Δh agree on the user tokens (cosine 0.70–0.85) but not at the suffix
  (cosine 0.06–0.38).
- **Edge vs far side.** There is no consistent direction: 33/56 bans are positive, and the top-5 bans are near zero.
- **Manifold.** PC1 is label-dominated (eta² of 0.77, 0.82 and 0.57 on T1–T3). It is not explained by surface features
  (R² < 0.17).

Caveats: single model family; one wording per confirmation ban; screen labels are the stored v1 labels, which another
artifact is auditing in parallel; and β_B = 19.75 was chosen near the edge of the pre-registered grid.
The T4 classifier was audited by an LLM judge (gpt-4.1-mini, 60 programs): κ = 0.79, accepted at a cost of $0.015.

## Layout

| Path | What |
|---|---|
| `method.py` | Pipeline driver (`run`) and `method_out.json` assembly (`assemble`) |
| `verify_headline.py` | Independent re-derivation of the headline numbers + shuffled-label falsification check |
| `src/protocol.py, classify.py, label.py, oracle*.py, activations.py, geometry.py, generate.py, engine.py, acts_io.py` | Copied byte-identical from iteration 1 (sha256 in `manifest_inputs.json`) |
| `src/protocol_t4.py, protocol_ext.py` | T4 task + new condition types (placebo blocks, mention, cross, alt placebo, pairs) |
| `src/classify_t4.py, oracle_t4.py` | T4 classifier v1+T4 and execution oracle; `tests/test_classifier_t4.py` (22 fixtures + 6 oracle cases) |
| `src/setup_check.py` | Step 0 integrity (byte-equal prompts, suffix identity, tests, 200 relabels) |
| `src/gen_vllm.py, jobs.py` | vLLM generation (with freeze guard) and job specs |
| `src/states.py` | HF prompt-suffix states and generated-window activations |
| `src/predictors.py, fit.py` | Predictors A–E, LOBO fit, band selection, centroids, freeze |
| `src/predict_conf.py` | Frozen per-condition predictions (T1–T3, then T4 plan + T4 predictions) |
| `src/judge_t4.py` | LLM-judge audit of the T4 classifier |
| `src/transplant.py` | Causal transplant / ceiling / knockout cells (HF hooks) |
| `src/score.py, analysis.py` | Confirmation scoring, regularity, transplant metrics, edge stat, logit lens, manifold, figures |
| `data/gen, data/labels, data/ban_plan*.json` | Iteration-1 screen (copied) |
| `data/conf/gen, data/conf/labels` | All new generations + labels (forced extension, confirmation, T4); `pairs.json`, `T4_plan.json`, job specs |
| `data/transplant, data/transplant_labels` | Transplant cell outputs and labels |
| `results/frozen_*.json + .sha256` | Frozen predictors and predictions |
| `results/predictor_scores_{screen,conf}.json, regularity.json, transplant.json, edge_stat.json, logit_lens.json, manifold_coords.json, geometry_checks.json, band_selection.json, t4_classifier_audit.json, budget.json` | Results |
| `results/centroids_T*.npz, delta_h_T*.pt` | Idea centroids/similarity matrices, suffix Δh for all screen conditions and layers (kept; stay on the run volume if ≥100 MB, here ~13 MB each) |
| `figures/` | Manifolds (PCA/UMAP/LDA), predictor JSD bars, sign cells, regularity forest, transplant recovery, layer sweep, edge stat |
| `method_out.json` (+ `full_/mini_/preview_`) | One example per confirmation generation with frozen predicted probabilities; metadata holds the verdicts |
| `logs/` | All run logs |

## How to run

See `reproducibility.md`. In short: `uv venv .venv --python=3.12 && uv pip install --python .venv/bin/python -r pyproject.toml`,
then `.venv/bin/python method.py run` (about 3 h on one 24 GB L4), then `.venv/bin/python method.py assemble`.

## Restoring removed files

These paths are listed as `delete` in `.aii/manifest.yaml` and can be rebuilt:

- `.venv/`: `uv venv .venv --python=3.12 && uv pip install --python .venv/bin/python -r pyproject.toml`
- `acts/` (activation caches, about 600 MB):
  ```
  .venv/bin/python src/states.py screen
  .venv/bin/python src/states.py band --layers 32,33,34
  .venv/bin/python src/states.py prompts --jobs data/conf/jobs_conf_nonban.json --out acts/prompt_states_conf_nonban
  .venv/bin/python src/states.py prompts --jobs data/conf/jobs_conf_bans.json --out acts/prompt_states_conf_bans
  .venv/bin/python src/states.py prompts --jobs data/conf/jobs_t4_bans.json --out acts/prompt_states_conf_t4bans
  .venv/bin/python src/states.py conf --layers 32,33,34
  ```
- `src/__pycache__/`, `tests/__pycache__/`: recreated automatically by Python on import (`.venv/bin/python method.py run`
  or `.venv/bin/python -m pytest tests/`).
- Model weights (not in the workspace): `huggingface-cli download Qwen/Qwen2.5-3B-Instruct` and `huggingface-cli download BAAI/bge-base-en-v1.5`.
