# Review of the iteration-1 research report (REVIEW_REPORT step)

This directory holds an adversarial audit of the run's internal research report for iteration 1, together with the scripts
used to recompute its numbers from the artifacts on disk.

## What was done
- Recomputed the influence arm's headline numbers (art_aSN7z8WuA7Ir, `gen_art_experiment_3`) from its `scored/` files. All matched.
- Walked the other two experiment workspaces of iteration 1. The ban arm (`gen_art_experiment_2`) has 4,360 generations,
  4,210 of them labelled, that the report omits. The temperature arm (`gen_art_experiment_1`) has 3,623 grid generations and
  360 seed generations, unlabelled.
- Wrote the structured review.

## Layout
| file | content |
|---|---|
| `.terminal_claude_agent_struct_out.json` | the review (schema: ReviewerFeedback) |
| `write_review.py` | builds the review JSON |
| `recompute.py` | recomputes influence-arm counts, pass rates, entropies, ban compliance and held-out ratios → `recompute_out.json` |
| `recompute_ban_arm.py` | tabulates the ban arm's label files (counts, entropy, still-banned) → `recompute_ban_arm_out.json` |
| `.aii/manifest.yaml` | storage decisions (nothing heavy here) |

## How to run
```
python3 recompute.py <run>/round-1/experiment-3/src
python3 recompute_ban_arm.py <run>/3_invention_loop/iter_1/gen_art/gen_art_experiment_2
python3 write_review.py
```
Only the Python standard library is needed.

## Restoring removed files
Nothing is marked for deletion. All files here are small text files.
