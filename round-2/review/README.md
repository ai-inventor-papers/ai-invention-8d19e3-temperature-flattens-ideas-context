# Review of the iteration-2 research report (REVIEW_REPORT step)

This directory holds an adversarial audit of the run's internal research report after iteration 2.

## Layout
- `.terminal_claude_agent_struct_out.json`: the structured review (scores, critiques, coverage, blocking flag).
- `.aii/manifest.yaml`: the disposal manifest. It is empty because this step wrote no heavy files.
- `README.md`: this file.

## What was done
- Recomputed the headline numbers from the artifacts' own outputs:
  - gen_art_experiment_4: `results/labels_unified.jsonl` and `oracle_results.jsonl`. Covers the ban-arm tables, the temperature re-draw and the seed-string entropy.
  - gen_art_experiment_5: `results/predictor_scores_conf.json`, `regularity.json` and `transplant.json`.
  - gen_art_experiment_6: `results/verdicts.json`, `gemma_bans.json`, `codestop_check.json` and `engine_consistency.json`.
- Checked the nearest published neighbours for the new positive claims: String Seed of Thought (arXiv 2510.21150) and PASTA (arXiv 2311.02262).

## How to run
There is nothing to run. The recomputations were short inline Python reads over the artifact files named above.

## Restoring removed files
Nothing is marked for deletion.
