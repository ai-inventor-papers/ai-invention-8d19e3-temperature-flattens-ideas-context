# Can internal knobs beat temperature for novel code? (influence arm)

This study asks whether interventions on the internal activations of **Qwen2.5-3B-Instruct** make the model write
*more diverse* and *novel* path-search algorithms that are *still correct*, compared with the practitioner knobs
(temperature, novelty prompts, a ban on the most common ideas, generate-then-select). Correctness is checked by
execution on 50 fixed random graphs. The algorithmic idea is labelled by an AST classifier, which was audited
against a blind LLM judge.

## Headline (pre-registered rules, `results/rules.json`)

**Prompting ceiling: no internal knob survives.**

| condition (pooled T1+T3, seeds 0..149) | oracle pass | idea entropy (bits) |
|---|---|---|
| baseline T=0.7 | 0.53 | 1.05 |
| temperature 1.0 / 1.3 / 1.6 / 2.0 | 0.42 / 0.19 / 0.00 / 0.00 | 1.22 / 1.33 / – / – |
| prompt "Make a new algorithm." | 0.55 | 1.05 |
| prompt "fully novel … 2000 words" | 0.08 | 2.20 |
| **prompt ban top-3 ideas** (best eligible) | 0.43 | **1.59** |
| generate-then-select (list 10, seeded pick) | 0.26 | 2.56 |
| best H-dim (α=0.05) | 0.57 | 1.06 |
| best A4 "unusualness" dial (α=0.356) | 0.47 | 1.37 |
| A3 erasure (rank-1 projection a=0.25 / LEACE a=0.5) | 0.55 / 0.52 | 1.06 / 0.94 |

* **H-flatten fails.** On the held-out draw (seeds 1000..1099), H-dim reaches 0.93× the entropy of the best
  eligible temperature on T1 and 1.20× on T3; the rule required ≥2×. Its CI against the matched random direction
  includes 0. H-probe has no setting at the matched pass rate.
* **The H directions select an idea rather than flatten the choice.** With two dominant ideas the
  "flatten" direction overshoots the uniform point. H-dim α=0.224 turns T1 into DFS 145/150 (baseline: BFS 98,
  DFS 44) at an unchanged pass rate (0.68 vs 0.67). H-probe α=0.75 does the same, and on T3 it pushes
  Dijkstra towards BFS. The internal knob is a reliable, correctness-preserving *selector* of known ideas, not a
  generator of new ones.
* **A3 fails.** Judge-confirmed novel-and-correct programs: **0 in every condition**. All 70 distinct passing programs
  the rule classifier labelled `other` (sweep + held-out) were judged to be known algorithms: Dijkstra 41,
  other_known 12, BFS 7, Bellman-Ford 7, DFS 3. LEACE erases
  idea decodability offline (T3: 0.88 → 0.35 balanced accuracy; chance 0.33) without breaking code, but the model
  still writes BFS, DFS and Dijkstra.
* **A4 fails.** The cross-task unusualness direction transfers perfectly as a *readout*: AUROC 1.0 separating
  novel-request from plain prompts on held-out path tasks, with leave-one-task-out cosine >0.92. As a *dial*,
  atypicality is not monotone in α: Spearman 0.49 on T1 and −0.26 on T3; the rule required ≥0.8 on both.
* **Random matched-norm directions raise entropy as much as the targeted knobs.** Several R-add settings would sit
  on the entropy/pass Pareto front if controls were allowed on it (`results/results.json → pareto`). Most of the
  "diversity" gained by steering is non-specific perturbation.
* **Why the probes needed fallback F4.** The first 8 generated tokens are boilerplate ("Certainly! Below is …").
  Probes at gen1..8 sit at the majority baseline at every layer. The algorithm name first appears at a median of
  token 23.5 (T1) and 46.5 (T3), and never within 8 tokens. Probes on mean(gen1..32) reach about 0.65–0.69
  balanced accuracy, against 0.42 for within-task shuffled labels. Decodability is flat across layers, which
  points to a readout of the name tokens rather than an early plan. The steering window was therefore widened to
  prompt-final + gen1..64, and the band chosen by the pre-registered rule is layers 29–31.
* **Noise floor.** Re-generating the baseline in mixed batches (`crn_rerun`) flips 17% (T1) and 11% (T3) of idea labels,
  because bf16 batch numerics differ by batch composition. Common random numbers therefore pair conditions only
  approximately, and no paired effect is claimed below that floor.
* **Classifier audit.** 200 stratified programs, rule vs blind judge (gpt-4.1-mini): agreement 0.715, Cohen's
  κ = 0.68 (≥ 0.6, so the rule labels stand). The main confusion is rule `spfa` vs judge `bfs` (queue relaxation
  without in-queue tracking).

Survival verdicts and every CI are in `results/results.json` (`survival`, `settings.*.tasks.*.ci`,
`knob_vs_random_controls`, `manipulation_checks`). The figures are in `figs/`.

## Layout

| path | content |
|---|---|
| `method.py` | pipeline entry point. Stages: `baseline acts probes vectors calib sweep select heldout judge analyze` (+ `explore`, post-hoc) |
| `protocol/prompts.py`, `protocol/protocol.json` | shared protocol: task prompts, output contracts, condition texts, taxonomy |
| `protocol/classifier.py` | AST classifier; docstrings and comments are stripped before the rules run |
| `protocol/oracle.py` | sandboxed execution oracle: 50 graphs with seed 12345, 5 s CPU, 1 GB RAM, module-level demo code removed |
| `src/engine.py` | the single HF engine: per-sample seeded inverse-CDF sampler, code-block stop, steering and capture hooks |
| `src/settings.py` | registry of every condition |
| `src/acts_io.py` | split activation cache: writer and lazy memory-mapped reader |
| `src/probes.py`, `src/vectors.py` | idea probes; H-probe, H-dim, A3 bases, LEACE, A4 direction and random controls |
| `src/analysis.py` | metrics, bootstrap CIs, survival rules, OpenRouter judge, figures, `method_out.json` |
| `verify_headline.py` | independent re-derivation (own classifier, own oracle runner, pandas) plus placebo tests → `results/verify_headline.json` |
| `score_backlog.py` | recovery: scores generations that were left unscored |
| `run_post.sh` | the post-sweep chain that was actually run |
| `tests/` | classifier/oracle unit tests (`tests/refs/`), engine tests (sampler, hooks), `test_acts_split.py` (split-cache readers) |
| `gens/{T1,T3}/*.jsonl` | every generation: prompt, text, seed, sampler and intervention spec |
| `scored/{T1,T3}/*.jsonl` | label, oracle pass, fraction correct, degeneration flags; `oracle_cache.jsonl` |
| `judge/` | judge verdicts (`verdicts.jsonl`), audit sample, cost (`cost.json`, $0.081 in total) |
| `results/` | `context.json` (menus, band, alphas), `probe_curve.json`, `calibration.json`, `rules.json`, `vector_checks.json`, `heldout_plan.json`, `results.json`, `verify_headline.json` |
| `figs/` | probe curve, Pareto fronts (entropy, off-menu, novel), violin of fraction correct, A4 dose-response, idea shares, PCA "manifold" view |
| `method_out.json` (+ `full_`, `mini_`, `preview_`) | schema `exp_gen_sol_out`: 300 examples (T1/T3 × seeds 0..149) with baseline and per-method generations, plus all metrics in `metadata` |
| `acts/` | cached baseline residuals, 0.9 GB, split into `baseline_{T1,T3}_part_001..006.npy` (50 samples each, 73 MB) and read through `src/acts_io.py`. **Kept on the run's volume only**; not in the published repo |
| `caps/` | residuals captured during steered generation, 0.9 GB. **Kept on the run's volume only** |
| `vectors/vectors.pt`, `vectors/leace_{T1,T3}.pt` | every intervention vector and probe weight (0.6 MB); LEACE erasers stored per task (50 MB each) so each file is under 100 MB |

## How to run

```bash
uv venv .venv --python=3.12 && uv pip install --python .venv/bin/python -r requirements.lock.txt
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
.venv/bin/python method.py baseline   # 600 gens
.venv/bin/python method.py acts && .venv/bin/python method.py probes --workers 20
.venv/bin/python method.py vectors && .venv/bin/python method.py calib --batch 200
.venv/bin/python method.py sweep --batch 200 --n_main 150 --n_ctrl 75
./run_post.sh                          # judge -> select -> heldout -> judge -> analyze
.venv/bin/python method.py explore --batch 200 --n_main 150   # post-hoc, excluded from survival
.venv/bin/python method.py judge && .venv/bin/python method.py analyze
.venv/bin/python verify_headline.py
```

See `reproducibility.md` for the exact sequence, the hardware used and the runtimes.

## Deviations from the plan (all recorded)

* **F4 applied**: probes use mean(gen1..32) and the hook window is prompt-final + gen1..64, because gen1..8 probes
  are at chance.
* **Menus exclude `other`**: T1 = {BFS, DFS} and T3 = {Dijkstra, BFS}, so k = 2 and A3 has rank 1 only.
* **Oracle runs only the requested code**: it executes imports, defs and safe assignments. Module-level demo code
  crashed 22% of T3 programs for reasons unrelated to the algorithm.
* **Code-block early stop (F1 rule)**: applied to every condition.
* **Larger samples**: n = 150 per setting and 75 per control, up from the planned 100/50; the held-out draw is
  100 seeds.
* **Allocator change**: after 2,400 generations the sweep was restarted with
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, an allocator-only change, and resumed from the files.
* **Post-hoc low-α H settings**: `Hprobe_x_*` and `Hdim_x_0.075` (`explore`) are reported, but they are not used
  by the survival rules.
* **Single model**: Qwen2.5-3B-Instruct only, and all results are single-model.

## Restoring removed files

Only `.venv/` is marked `delete` in `.aii/manifest.yaml`. To recreate it with the pinned versions:

```bash
uv venv .venv --python=3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

The model weights are not stored here. They are downloaded on first use with
`huggingface-cli download Qwen/Qwen2.5-3B-Instruct`.
