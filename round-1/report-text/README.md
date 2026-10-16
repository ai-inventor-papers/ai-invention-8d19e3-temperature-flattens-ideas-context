# Research report, iteration 1 (gen_report_text)

This directory holds the run's internal research report after iteration 1: a chronological lab notebook of the
study "How an LLM picks a solution idea, and whether internal edits can make it pick new ones" (Qwen2.5-3B-Instruct,
path-search code generation). Iteration 1 planned a three-arm pre-registered screen; only the influence arm
(artifact `art_aSN7z8WuA7Ir`) delivered, and its full results are recorded here.

## Layout

| path | content |
|---|---|
| `paper_draft.md` | the report itself: framing, the Iteration 1 section with all 26 result tables, "What we have learned so far", references, `[FIGURE:...]` and `[ARTIFACT:...]` markers |
| `references.bib`, `references.json` | BibTeX fetched by the aii-semscholar-bib script, and its fetch record (one entry, Shai2024, was fetched by mistake and is not cited) |
| `style_exemplars.md` | verbatim style passages and section outlines from five reference papers (style only) |
| `domain_terms.json` | 104 field terms with glosses, used for the terminology sweep |
| `work/make_tables.py` | builds every markdown table directly from the artifact's output files |
| `work/make_figs.py` | builds the figure specs (exact values) from the artifact's `results/results.json` |
| `work/draft_template.md` | report text with `{{table}}` placeholders |
| `work/assemble.py` | fills the placeholders and writes `paper_draft.md` |
| `work/tables.json`, `work/figs.json`, `work/settings_dump.txt` | generated tables, figure specs, compact per-setting dump |
| `work/ex/` | fetched exemplar papers (markdown) used to write `style_exemplars.md` |

## How to rebuild the report

```bash
A=<path to the influence-arm artifact directory>   # gen_art_experiment_3 of iteration 1
python3 work/make_tables.py "$A" work/tables.json
python3 work/make_figs.py "$A"
python3 work/assemble.py          # writes paper_draft.md
```

Only the Python standard library is needed.

## Restoring removed files

Nothing is marked `delete` in `.aii/manifest.yaml`; every file here is small text and is kept.
