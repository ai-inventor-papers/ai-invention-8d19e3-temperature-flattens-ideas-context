# Reproducing this artifact

Everything below is what was actually run, in order, on 2026-10-16. All paths are relative to this artifact folder.

## 1. Get the artifact
```bash
git clone <URL of the published run repository>
cd <repository>/<this artifact folder>      # the folder that contains method.py and this file
```
`inputs/` already holds read-only copies of every iteration-1 input: the temperature grid `raw_grid.jsonl`, the seed
rows, the ban-arm generations and labels, and the influence-arm AST classifier. `inputs/MANIFEST.sha256` lists their
hashes. Nothing outside this folder is read. The user-uploaded reference folder of the run was empty and is not needed.

## 2. System, Python and libraries
* Ubuntu/Debian x86-64. NVIDIA GPU with ≥ 22 GB VRAM: we used **1× NVIDIA L4 (23 GB)**, driver 595.91 (CUDA 13.2),
  15 CPU cores (cgroup quota) and 66 GB RAM.
* No system C compiler is needed. vLLM/Triton JIT uses `tools/cc`, a `python -m ziglang cc` shim (package `ziglang`),
  which `src/gpu_gen.py` sets as `CC` automatically.
* Python 3.12 and [uv](https://github.com/astral-sh/uv) 0.6.14:
```bash
uv venv .venv --python=3.12
uv pip install --python .venv/bin/python -r requirements.txt   # 223 exact pins = pyproject.toml dependencies
```
Key pins: `vllm==0.31.0`, `torch==2.13.0`, `transformers==5.17.0`, `numpy==2.3.5`, `scipy==1.18.1`,
`statsmodels==0.15.0`, `rapidfuzz==3.14.6`, `scikit-learn`, `openai` (see `pyproject.toml` for all).

## 3. Downloads, environment variables, keys
* Model: `Qwen/Qwen2.5-3B-Instruct` from the Hugging Face Hub. It is fetched automatically on first use, or ahead of
  time with `huggingface-cli download Qwen/Qwen2.5-3B-Instruct`. Optional: `HF_HOME` sets the cache location.
* Judge audit only: `OPENROUTER_BASE_URL` and `OPENROUTER_API_KEY` (OpenRouter; models `openai/gpt-4.1-mini` and
  `google/gemini-2.5-flash-lite`). Cost: **$0.042** for 400 calls. Every other stage needs no key.

## 4. Commands, in the order run (≈ 2.5 h wall-clock in total on the L4)
```bash
P=.venv/bin/python
$P -m pytest -q -c tests/pytest.ini --rootdir tests tests/test_classifier.py tests/test_oracle.py  # 3 tests pass (all fixtures)
$P src/s1_label.py                 # ledger of the 8,193 iteration-1 programs (~1 min, 12 CPU workers)
$P src/s2_oracle.py                # sandboxed oracle, ~7 min at ~20 programs/s (10 workers)
$P src/s4_templaw.py --source grid # C1 screen analysis (~1 min)
$P src/freeze.py c1                # -> results/frozen_c1_temperature.json  sha256 d1dabe95...
$P src/gpu_gen.py --modes trunc,redraw   # 150 continuations + 20 regenerations + mini + 3,615 re-draw gens (~20 min)
$P src/s3_screen.py                # ban-arm screen tables
$P src/s4b_truncation.py           # truncation audit
$P src/s6_seed_readout.py --phase readout  # HF readout + residual displacement (~9 min GPU)
$P src/s1_label.py && $P src/s2_oracle.py  # add re-draw rows to the ledger + oracle
$P src/s4_templaw.py --source redraw       # C1 re-draw + out-of-sample scoring
$P src/s6_seed_readout.py --phase freeze   # -> results/frozen_c3_seeds.json sha256 1cffcec3...
$P src/s7_c4ref.py --screen-only           # -> results/frozen_c4_reference_v0.json
$P src/gpu_gen.py --modes seeds            # 2,160 fresh seeded generations (~8 min)
$P src/judge_audit.py --pilot && $P src/judge_audit.py   # 10-program pilot, then 200 programs x 2 judges
$P src/s1_label.py && $P src/s2_oracle.py  # add fresh-seed rows (13,968 programs in total)
$P src/s6c_seed_score.py                   # C3 scoring
$P src/s7_c4ref.py                         # -> results/frozen_c4_reference.json sha256 783778b0...
$P src/s8_figs.py                          # figures/
$P method.py                               # -> method_out.json
$P verify_headline.py                      # independent re-derivation -> results/verify_headline.json
```
`.venv/bin/python method.py --run-all` runs the same stages in order. `freeze.py` writes a new UTC timestamp, so a
rerun produces new hashes for any freeze whose inputs changed.

Seeds and configuration:
* vLLM: `LLM(dtype=bfloat16, gpu_memory_utilization=0.85, max_model_len=4096, enforce_eager=True,
  enable_prefix_caching=True, seed=0)`, `top_p=1.0`.
* Re-draw: per-request `seed=1000+i` (i = 0..99) at T ∈ {0.3, 0.5, 0.7, 1.0, 1.3, 1.6} × top-k ∈ {10, none}
  (T3: none only), `max_tokens=1536`. The extra unseeded T=0.7 block uses seeds 1100..1299. There are 5 unseeded
  greedy repeats per task.
* Fresh seed strings: `random.Random(20261016)` (char) and `random.Random(20261017)` (word); T=0.7 sample seed
  `1000+5*idx+r`.
* Truncation sample: seed 11. Judge sample: seed 7. Bootstrap seeds are fixed in code.

**Determinism caveat.** vLLM batch generation is not bit-reproducible: 0/20 768-token prefixes reproduced, and 17/20
repeat rows kept their label. Regenerated text will therefore differ row by row, but the distributions and verdicts
should reproduce within the reported CIs. Using the shipped `gens/*.jsonl` makes every downstream number exact.

## 5. What you should get (`method_out.json` → `metadata`, `results/verify_headline.json`)
* `label_repro`: 4,210/4,210 identical; T1 baseline counts BFS 179 / DFS 44 / A* 39 / Dijkstra 22 / Other 14 / SPFA 2.
* `judge_audit`: κ(v1, gpt-4.1-mini) = 0.842, κ(judge, judge) = 0.919.
* `verdicts.C1_PASS = false`. Re-draw out-of-sample MAE (frozen anchored law vs fixed-utility baseline): T1 top-k10
  0.040 vs 0.073; T1 none 0.109 vs 0.129; T2 none 0.103 vs 0.056; T2 top-k10 0.100 vs 0.028.
* `verdicts.C3 = {C3a_T1: true, C3a_T2: false, C3b_T3: true, C3_PASS: false}`. Greedy flip rates are 0.25 / 0.017 / 0.00.
* `truncation_audit.continuation.flip_rate = 0.107` (16/150).
* C4 (frozen): best off-menu correct share T1 0.02, T2 0.08 (T=1.3, 1536 tokens), T3 0.00.
* Figures: `figures/fig_arrhenius_T1/T2`, `fig_hill_partition`, `fig_abc_table`, `fig_seed_flip`,
  `fig_ban_heatmap_T1..T3`, `fig_quality_diversity` (PDF + PNG). These back the paper's temperature-law,
  diversity-partition, seed and ban-arm sections.
