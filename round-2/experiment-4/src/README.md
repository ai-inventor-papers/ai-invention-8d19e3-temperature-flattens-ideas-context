# Labelling every run, then testing temperature and seeds (Qwen2.5-3B-Instruct)

**Question.** When a small instruction-tuned LLM is asked to "implement a path search algorithm" (T1), "implement a
sorting algorithm" (T2) or "implement a function that finds a shortest path in a weighted graph" (T3), which
*algorithm* (idea) does it pick? Is sampling temperature a "creativity knob" that moves it to new ideas, or does it
only re-phrase the same few ideas? Can prepending a random seed string ("seed=d32qxk4nt43",
"seed=(horse chair roof love)") push it to different ideas?

**What this artifact does.**
1. **One label ledger** for all 13,968 programs: the 8,193 from iteration 1 plus 5,775 new ones. It uses the canonical
   v1 rule classifier (hash `d0d321215bc2`); all 4,210/4,210 stored ban-arm labels reproduce exactly. Every program
   runs through a sandboxed execution oracle. The classifier is audited against the influence-arm AST classifier and
   against two blind LLM judges.
2. **Ban-arm screen tables.** For each prompt variant that forbids one or more algorithms: compliance, pass rate,
   off-menu correct share, forced purity, co-mention similarity, and Fisher/Holm tests against the placebo prompt.
3. **C1, the temperature law.** On the 3,600-row iteration-1 grid it fits Arrhenius / multinomial-logit lines
   (ln-odds vs 1/T), runs a curvature LR test and an intercept test against the fixed-utility logit null, counts rank
   reversals, partitions diversity into within-idea phrasing (Hill alpha, edit-distance Leinster–Cobbold, rarefied) and
   idea-level diversity, and builds the user's (a)/(b)/(c) "10 trajectories" table. The fits are **frozen** (sha256)
   and then tested **out of sample** on a fresh 3,000-generation re-draw at 1536 tokens. The comparison runs against
   two baselines: the fixed-utility logit (shares at 0.7 raised to 0.7/T) and no temperature effect.
4. **Truncation audit.** 150 truncated rows are *continued* from their own tokens.
5. **C3, seed shocks.** An internal name-token utility readout and a behavioural Gaussian-shock model are frozen
   before 120 fresh seed strings × 3 tasks × (1 greedy + 5 samples at T=0.7) are generated and scored.
6. **C4 reference.** The best temperature for correct off-menu ideas, frozen for sibling artifacts.

## Headline results (all independently re-derived by `verify_headline.py`)

| Claim | Result |
|---|---|
| Label reproduction | 4,210/4,210 ban-arm labels identical; T1 baseline BFS 179 / DFS 44 / A* 39 / Dijkstra 22 / Other 14 / SPFA 2 |
| Classifier validity | v1 vs judge (gpt-4.1-mini) κ = 0.84 [0.78, 0.89], judge–judge κ = 0.92 (ceiling), shuffled-label κ = −0.02; n=200, spend $0.042 |
| **C1 temperature law** | **FAILS** on screen and re-draw. Not all lines reach R² ≥ 0.85 (a simulation shows R² < 0.85 in 25–87% of draws *under a true linear law*, so R² is a weak criterion). There are top-3 reversals at T ≤ 1.3. The alpha/beta slope ratio is 0.6–2.6, never ≥ 3. |
| C1 out of sample | The frozen law beats the fixed-utility baseline on T1 (MAE 0.040 vs 0.073 at top-k 10; 0.109 vs 0.129 with no top-k) and loses on T2 (0.100 vs 0.028) |
| Intercepts | T1 intercepts are significantly < 0 (e.g. A* −2.4 [−3.2, −1.6]): **not** a pure scale (fixed-utility) model |
| Temperature = creativity? | Ideas grow slowly with T: E[ideas among 10] goes from 2.4 to 3.9 on T1 and from 2.1 to 4.9 on T2. Phrasings saturate: about 8–10 distinct among 10 already at T=0.3 on T1. At T=1.6 with no top-k, output collapses (93–95% truncated, mostly Unparseable or Other) |
| Truncation | 16/150 = 10.7% labels flip when truncated rows are continued; 0/20 768-token prefixes reproduce on regeneration (vLLM non-determinism) |
| **C3 seed shocks** | **FAILS**. Greedy flip rate observed vs frozen prediction: T1 0.25 vs 0.28 (pass), T2 0.017 vs 0.39 (fail), T3 0.00 (pass, < 5%). |
| Does seeding diversify? | **No, it narrows.** Idea entropy for seeded vs unseeded T=0.7 samples: T1 1.28 vs 1.62 bits (Δ −0.34 [−0.53, −0.13]); T2 0.86 vs 1.53 bits (Δ −0.68 [−0.92, −0.47]); seeded samples converge on BFS / Bubble sort |
| Seed vs ban in the residual stream | Seed strings displace the last-5-template-token residual 1.5–3× more than a "Do not use BFS" sentence, yet flip the greedy idea far less often |
| C4 reference | Correct off-menu ideas stay rare at every T: T1 0.02 (SPFA), T2 0.08 at T=1.3 (Insertion), T3 0.00 |

## Layout

| Path | What |
|---|---|
| `method.py` | entry point: `--run-all` runs every stage in order; default aggregates `results/` into `method_out.json` |
| `method_out.json`, `full_/mini_/preview_method_out.json` | exp_gen_sol_out output: 4 datasets (C1 re-draw cells with model and baseline predictions; C3 fresh seed strings; ban conditions; full program ledger) plus all verdicts in `metadata` |
| `verify_headline.py` → `results/verify_headline.json` | independent re-derivation of headline numbers + placebo controls |
| `src/protocol.py, classify.py, label.py, oracle.py, oracle_harness.py, activations.py` | copied unchanged from the iteration-1 ban arm (classifier hash `d0d321215bc2`) |
| `src/common.py` | paths, IO, statistics (Wilson, entropy, Hill, rarefaction, Chao1, JSD, Holm), code normalisation |
| `src/s1_label.py` | unified ledger `results/labels_unified.jsonl`, `gens/programs.jsonl`, AST audit |
| `src/s2_oracle.py` | resumable sandboxed oracle → `results/oracle_results.jsonl` |
| `src/s3_screen.py` | ban-arm screen tables → `results/screen_tables.json/.csv`, `results/comention_sim.json` |
| `src/s4_templaw.py` | C1 analysis (`--source grid` screen / `--source redraw` + out-of-sample scoring) |
| `src/s4b_truncation.py` | truncation audit → `results/truncation_audit.json` |
| `src/freeze.py` | sha256 freezing + verification (generation refuses on missing or tampered files) |
| `src/gpu_gen.py` | all vLLM generation (`--modes trunc,redraw` / `seeds`) → `gens/*.jsonl` |
| `src/s6_seed_readout.py` | C3 readout (`--phase readout`, GPU) and freeze (`--phase freeze`) |
| `src/s6c_seed_score.py` | C3 scoring → `results/c3_scoring.json` |
| `src/s7_c4ref.py` | C4 reference → `results/frozen_c4_reference(_v0).json` |
| `src/judge_audit.py` | blind LLM-judge audit → `results/judge_audit.json`, `results/judge_raw.jsonl` |
| `src/s8_figs.py` | figures → `figures/*.pdf/.png` |
| `inputs/` | read-only copies of the iteration-1 inputs (+ `MANIFEST.sha256`) |
| `gens/` | new generations of this artifact (re-draw 3,615; fresh seeds 2,160; truncation continuations 150 + 20) |
| `results/frozen_*.json` | frozen predictions: C1 `d1dabe95…`, C3 `1cffcec3…`, C4 `783778b0…`, C4 v0 `bd5d33a9…` |
| `logs/` | stage logs, `freeze_log.jsonl` |

Large files (`gens/redraw.jsonl` 31 MB, `inputs/grid/data/raw_grid.jsonl` 25 MB) stay on the run's volume and in
the repository, since all are below 100 MB.

## Deviations from the plan (honest list)
* The ban arm's `__topup` replicate files (seeds 100–199) do not exist, so the screen noise floor uses the baseline
  thirds (seeds 0–99 / 100–199 / 200–299).
* The C3 readout failed its pre-registered gate on T1 and T2. Prefix coverage was 0.10–0.37 (< 0.25), and T7 forced
  argmax was 0.70 on T1, where the readout ranks DFS above BFS. The **behavioural** Gaussian-shock model (fallback F4)
  was therefore the frozen primary predictor for T1 and T2. The readout is reported descriptively.
* Alpha uses edit-distance similarity only. The unixcoder-embedding Z2 was skipped (F8).
* Figures are drawn with plain matplotlib (`src/s8_figs.py`), not the JSON-spec renderer.
* The workspace is not a git repository: freezes are logged to `logs/freeze_log.jsonl` with sha256 + UTC time
  instead of a git commit.
* Test T6 (mini re-draw truncation < 5%) failed at T=1.6: 9 of the 20 mini rows truncated, all at T=1.6. This is the
  degeneration finding itself; the full re-draw went ahead.
* Single model family (Qwen2.5-3B). The bootstrap CIs on alpha slopes are biased low because resampling duplicates
  programs.

## How to run
See `reproducibility.md`. Short form: `uv venv .venv --python=3.12 && uv pip install --python .venv/bin/python -r requirements.txt && .venv/bin/python method.py --run-all`.

## Restoring removed files
* `.venv/` (deleted after the round; regenerable): `uv venv .venv --python=3.12 && uv pip install --python .venv/bin/python -r requirements.txt`
* `src/__pycache__/` (regenerable): created automatically by running any script, e.g. `.venv/bin/python method.py`.
* `tests/.pytest_cache/` (regenerable): `.venv/bin/python -m pytest -q -c tests/pytest.ini --rootdir tests tests/test_classifier.py tests/test_oracle.py`
* Model weights are not stored in this folder. They are downloaded on first use from the Hugging Face Hub:
  `huggingface-cli download Qwen/Qwen2.5-3B-Instruct`.
