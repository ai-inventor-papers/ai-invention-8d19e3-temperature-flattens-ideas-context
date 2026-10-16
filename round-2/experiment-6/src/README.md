# Does steering pick ideas or spread them?

This study asks how an LLM's choice of *which algorithm to write* is represented, and whether that choice can be
moved. The test case is "Implement a path search algorithm in Python" (T1), where Qwen writes BFS 61% of the time,
and "Implement a sorting algorithm" (T2), where it writes bubble sort 62% of the time. There are three parts:

* **A.** A re-analysis of iteration 1's steering claims, compared against the *average* of several random directions
  rather than one cell.
* **B.** A pre-registered test on Qwen2.5-3B-Instruct. The question is whether a difference-in-means "away from the
  default idea" direction **selects** one neighbouring idea or **flattens** the idea distribution. Each strength is
  compared with 5 matched-norm random draws, an off-target real vector, temperature, and simply asking for the idea.
* **C.** A second model family, gemma-2-2b-it, used to test whether **bans** ("Do not use X") move probability to
  the ideas whose representation the ban pushes toward (a displacement logit). The comparators are
  proportional renormalisation (IIA) and a text-embedding baseline. Part C also covers the temperature law and a
  prompt-state transplant.

Every verdict below follows rules that were frozen, with SHA256 hashes, before the data they judge existed:
`results/frozen_selector_qwen.json`, `results/frozen_selector_qwen_alphas.json` and `results/frozen_gemma_bans.json`.

## Headline results

**B. Qwen: the "away from the default" direction is a selector, not a flattener.** The frozen rule gives
**SELECT on both tasks, replicated on both seed draws** (seeds 0..149 and 1000..1149).

* **T1 path search, s2 = 0.224.** BFS falls from 61% to 13–14%. A* rises to 57% and 63% on the two draws, and A*
  was the frozen projection prediction.
  * None of the 5 matched-norm random draws makes A* the top gainer. Random draws leave BFS at 61–72%.
  * The non-mode share is +0.54 above the random-draw mean (CI [0.47, 0.61]).
  * The cost is correctness: pass rate is 0.17, against 0.33 for the random-draw mean and 0.31 at baseline. That is
    below the 0.8× bar the n=30 calibration had predicted.
  * Entropy minus the draw-averaged random entropy is +0.32 bits (CI [0.04, 0.56]) on the main draw and +0.10
    (CI [−0.19, 0.36]) on the re-draw.
* **T2 sorting, s2 = 0.473.** Bubble falls from 62% to 0–1%, and Quick rises to 65% and 68%, the frozen projection
  prediction.
  * Entropy is **below** the random-draw mean: −0.71 bits (CI [−0.94, −0.44]) and −0.73 (CI [−0.95, −0.45]).
  * Pass rate is 0.92, against 0.98 at baseline.
  * Some random draws also move T2 a lot, with mode share ranging 0.19–0.69. Draw-level variance is large, which is
    exactly why a single random cell misleads.
* **Prompting beats steering toward an off-menu idea** (AxBench-style).
  * d_j toward IDDFS, Bellman-Ford or Counting produces 0–1% of the target. Asking for it ("… using X.") produces
    92–100%.
  * The exception is d_Heap at α=0.473: 91% heap sort at pass 0.95, against 100% from the forced prompt.
* **C4 (off-menu AND correct ≥ 3× the best temperature)** passes only on T2, through d_Heap and the Qwen screen bans.
  The result is the same with Builtin excluded.
  * On T1, no setting produces correct off-menu code beyond the 0–1 per 150 that temperature gives.
* **Engine consistency.** The HF and vLLM baselines agree: JSD 0.009 (T1) and 0.001 (T2), with chi-square p 0.18
  and 0.91.

**A. Iteration-1 claim 3 ("random directions raise entropy as much as targeted knobs") does not hold as stated.**
Each of the 18 targeted settings was compared with the **draw-averaged** entropy of the 3 random draws (Miller-Madow,
n-matched seeds 0..74, hierarchical bootstrap):

* 3 beat the draw mean;
* 5 are significantly **below** it (H-dim on T1 selects DFS);
* 10 are undetermined.

So the parity claim reduces to "undetermined for most, and targeted is lower where it selects". The two A4 Spearman
correlations are not significant by exact permutation:

* T1: ρ = 0.49, p = 0.36 two-sided (720 permutations);
* T3: ρ = −0.26, p = 0.66.

The original T1 bootstrap CI [−0.03, 0.54] had the point estimate at its edge; the corrected CI is [−0.43, 0.60]. The
file counts are 111/110 (T1) and 81/80 (T3), and the only gens-only file is `gts_list`.

**C. gemma-2-2b-it: bans are NOT predicted by the representation-displacement logit.**

* **Held-out bans.** Over 14 confirmation bans (ranks 5–8 plus 3 random pairs per task, seeds 1000+), the frozen
  GEOM predictor has mean JSD 0.121 against **0.088 for IIA** (proportional renormalisation) and 0.093 for the
  MiniLM text-embedding baseline.
  * Relative gain −0.71, with a CI over bans of [−1.29, −0.23]: C2a fails.
  * Top-substitute hit rate is 7% (C2b fails), and sign accuracy is 0.60 against 0.56 for IIA.
  * GEOM predicts the same substitute for every ban, so the prompt-state shift Δh is dominated by a generic "Do not
    use …" component.
  * An independent re-check scores GEOM against a *mismatched* ban's prediction and finds it no worse.
* **On the screen**, GEOM ties IIA (mean JSD 0.249 vs 0.254). It wins only where gemma *ignores* the ban: on T1,
  BFS stays 72% under a ban that names it.
* **Regularity** (no unbanned idea's share drops) holds in 71/72 cells. The exception is the T2 heap-sort ban, where
  merge sort drops 0.55 → 0.16 (Holm p 1e-4). Placebo blocks tested the same way give 0 violations.
* **The placebo sentence is a large perturbation.** gemma T2 goes from Bubble 81% (baseline) to Merge about 55%
  (placebo). Placebo-block noise floors are 18 pp (T1) and 12 pp (T2), so confirmation on T1 is underpowered.
* **Labels.** The gemma audit (100 programs, gpt-4.1-mini, $0.02) gives κ = 0.94 on T2 but **κ = 0.39 on T1**, so
  T1 gemma labels are flagged *label-limited*. 87% of gemma T1 answers hit the 768-token cap.

**C5. Temperature law on gemma (n=40 per T, so this is weak).**

* On T2, the log-odds of Merge and Selection against Bubble are close to linear in 1/T: R² 0.96 and 0.93, slopes
  −1.08 and −1.03.
* On T1, R² is 0.29–0.74 and the top-3 ranks reorder by T=1.0. With 4 points, R² ≥ 0.85 is a weak test.
* **Answer to "does tight temperature give one idea with many phrasings?"**
  * At T=0.3, gemma T2 writes bubble sort 40/40 times with 19 distinct 32-token openings: one idea, many phrasings.
  * Raising T adds ideas only slowly: Hill-1 diversity goes 1.0 → 1.5 → 3.0 → 4.5 for T = 0.3/0.7/1.0/1.3.
  * Top-k 10 at T=1.0 gives the same number of distinct ideas (6) as no top-k.
  * On T1, T=1.3 is mostly degenerate (label "Other" 19/40, pass 0.05).

**C4. Δh transplant at L* = 13 (5 suffix positions, n=30): C2c fails on both tasks.**

* **T2 (ban top-5).** Adding the ban–placebo prompt-state difference to the placebo prompt recovers only 6% of the
  ban effect (CI [−0.13, 0.21]). It moves output away from Bubble (13 → 4 of 30), but toward Insertion rather than
  the ban's Heap/Quick/Radix. Subtracting it from the ban prompt restores nothing (−0.03).
* **T1 (ban A\*).** gemma barely obeys the ban itself (JSD placebo vs ban 0.11), so recovery (0.42, CI [−0.93, 0.78])
  is noise. One random displacement "recovers" 0.66.
* The ban is therefore not carried by the end-of-prompt summary state at this layer. Per the plan, this is not a
  null for displacement through the ban-token positions.

**D. Gemma Scope SAE (layer 13, 16k, L0 84): unreliable and descriptive only.**

* Reconstruction FVU on the -it prompt states is 0.61 (> 0.5), so D is marked unreliable.
* Priming of the banned idea's specific latents is positive in 10/16 single bans, but within the random-latent null
  for most.

**What this says about "creativity" (the run's question).**

* The default answer is a basin in the model's commitment-window representation: the BFS / bubble-sort centroid in
  `figs/fig_centroid_map.png`.
* A difference-in-means push "away from the default" does not spread probability over the space. It **selects the
  nearest large neighbour** (A\* on T1, Quick on T2), the idea the frozen projection predicted. On T1 it also costs
  correctness.
* Truly off-menu ideas (IDDFS, Bellman-Ford, Counting sort) are reached by **asking for them** in the prompt, not by
  steering toward their centroid. Heap sort is the one exception.
* Bans move the model, but the move is not predicted by representation distances, and IIA (proportional
  renormalisation) remains the better predictor.
* Every selector verdict is specific to the prompt wording: one wording per condition.

## Independent re-derivation (`verify.py` → `results/verify.json`)

`verify.py` uses pandas and scipy on the raw scored jsonl files and does not call the pipeline's statistics code.

**Re-derived:**

* the Qwen SELECT verdicts on both tasks and both draws;
* the s2 entropy difference against the random-draw mean (exact match);
* the gemma transplant recoveries;
* the first Step-A setting;
* the gemma held-out JSD comparison. This comes out at −0.88 here against −0.71 in the pipeline, because only the
  classes present are scored. The direction is the same.

**Placebo checks:**

* For each task, one random draw tested against the other four, and shuffled targeted/random labels, both give CIs
  that include 0.
* Placebo blocks tested as "bans" give 0 regularity violations.
* Scoring GEOM against a mismatched ban's prediction does no worse, so GEOM's predictions are not ban-specific.

**Not independently re-derived:** the C4 Fisher tests, the audit κ, the Arrhenius slopes and the SAE statistics.

## Layout

| path | content |
|---|---|
| `method.py` | entry point: `python method.py run <stage>` and `python method.py output` (builds `method_out.json`) |
| `src/common.py` | paths, I/O, freeze/require-frozen, statistics: entropy, Miller-Madow, Wilson, KL-to-uniform, JSD, hierarchical draw→sample bootstrap |
| `src/engine.py` | the single HF engine (from iteration 1): seeded inverse-CDF sampler (common random numbers), steering hooks, prompt-patch hook (C4) |
| `src/runner.py` | batched generation (never mixes prompt lengths) and concurrent v1-label + oracle scoring |
| `src/protocol.py`, `src/classify.py`, `src/label.py`, `src/oracle*.py`, `src/activations.py` | copied verbatim from the iteration-1 ban arm (classifier `v1:d0d321215bc2`); hashes are in `results/provenance.json` |
| `src/reanalysis.py` | Step A |
| `src/steer_qwen.py`, `src/acts_window.py`, `src/analyze_qwen.py` | Step B: stages, commitment-window activations and probe band, analysis |
| `src/score_ba.py` | v1 + oracle on the iteration-1 vLLM screen (Qwen bans, for C4) |
| `src/gemma.py`, `src/analyze_gemma.py`, `src/audit.py` | Step C: screen, geometry, fits and freeze, confirmation, temperature, transplant; analysis; judge audit |
| `src/sae_describe.py` | Step D: Gemma Scope SAE description (descriptive only) |
| `src/verdicts.py`, `src/figures.py`, `verify.py` | verdict collection, figures, independent re-derivation with placebo checks |
| `tests/` | classifier fixtures (45/45), oracle tests, code-stop check |
| `data/gens/<model>/<task>/<setting>.jsonl` | every generation: prompt, text, seed, temperature, intervention, token ids |
| `data/scored/<model>/<task>/<setting>.jsonl` | v1 label, oracle status, fraction of instances passed, truncation |
| `data/scored/ba_vllm/` | the iteration-1 vLLM screen, re-scored |
| `data/acts/` | teacher-forced window activations (≈200 MB). **Kept on the run's volume only**, not in the published repo |
| `data/discarded_codestop/` | 400 early generations made with CodeStop before the code-stop check disabled it. Not used |
| `results/` | all result JSONs, frozen files (+ `.sha256`), `qwen_vectors.pt`, `gemma_centroids.pt`, `gemma_delta_h*.pt`, `verdicts.json`, `verify.json`, `deviations.json` |
| `figs/` | figures (PNG + PDF) |
| `method_out.json` (+ `full_`, `mini_`, `preview_`) | schema `exp_gen_sol_out`: one example per generated sample, with every verdict in `metadata` |
| `run_chain1.sh`, `run_chain2.sh` | the GPU chains that were actually run |

## How to run

See `reproducibility.md` for the exact commands, seeds, hardware and runtimes. In short:

```bash
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.lock.txt
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
.venv/bin/python method.py run A codestop B_base B_acts B_vectors B_freeze B_calib B_freeze2 B_main B_score_ba \
    C_screen_a C_screen_b C_audit C_geometry C_confirm C_confirm_states C_temp C_transplant \
    B_analyze C_analyze figures verify
.venv/bin/python method.py output
```

## Deviations from the plan

All deviations are recorded in `results/deviations.json`. The main ones:

* **Hardware.** A 16 GB RTX 2000 Ada, so vLLM was not used and gemma runs on the HF engine with eager attention.
* **CodeStop disabled.** The code-stop check failed (v1 agreement 0.87 on T1).
* **gemma sample sizes cut.** Baseline 150, placebo 3×50, forced 20, bans 50, confirmation 50, temperature 40 per T,
  transplant 30 per condition. gemma `max_new_tokens` is 768.
* **Qwen random draws at s1** use n=100.
* **Band.** The Qwen probe band is layers 32–34, not iteration 1's 29–31. Probe accuracy is nearly flat across
  layers, which points to a readout of the name tokens.

## Restoring removed files

`.aii/manifest.yaml` marks these paths `delete`:

* `.venv/`: `uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.lock.txt`
* `src/__pycache__/`, `tests/__pycache__/`: recreated automatically by running any script.

The model weights are not stored here. They download on first use: `Qwen/Qwen2.5-3B-Instruct`,
`google/gemma-2-2b-it` (gated, needs `HF_TOKEN`), `sentence-transformers/all-MiniLM-L6-v2` and
`google/gemma-scope-2b-pt-res` (one layer's `params.npz`).

`data/acts/` and `results/*.pt` are marked `keep`. They stay on the run's storage volume at these relative paths.
To regenerate `data/acts/`, run `python src/steer_qwen.py acts` for Qwen and `python src/gemma.py geometry` for
gemma (gemma's window file).
