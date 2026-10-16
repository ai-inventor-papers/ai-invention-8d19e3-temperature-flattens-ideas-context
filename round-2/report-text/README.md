# Research report, iteration 2 (gen_report_text)

This folder holds the run's internal research report after iteration 2: a chronological lab notebook of a study on
how an instruction-tuned LLM (Qwen2.5-3B-Instruct, with gemma-2-2b-it as a second model) chooses the algorithm it
implements for an open coding task, and whether temperature, seed strings, prompt bans or activation steering can move
that choice. Iteration 2 appended its section (Sections 2.1 to 2.12), added eight marked corrections to the
iteration-1 text, and rewrote the closing "What we have learned so far" section.

## Layout

| path | content |
|---|---|
| `paper_draft.md` | the full report: framing, Iteration 1, Iteration 2, "What we have learned so far", references. Figures are `[FIGURE:id]` markers whose specs live in the structured output |
| `references.bib`, `references.json` | bibliography fetched with the Semantic Scholar fetch script (never hand-written), and its fetch record |
| `style_exemplars.md` | verbatim passages from five papers used as a sentence-level style reference, plus their section outlines |
| `domain_terms.json` | the field's vocabulary (140 terms) that the report and the later paper are checked against |
| `.aii/manifest.yaml` | storage decisions (no heavy files in this folder) |

## How it was produced

Every number in the iteration-2 section was read from the output files of the three iteration-2 artifacts
(`gen_art_experiment_4`, `_5`, `_6` of the same run) by small Python scripts that typeset the tables; no table was
copied from an artifact summary. The bibliography was rebuilt with:

```bash
SKILL_DIR=../../tools/aii-semscholar-bib
$SKILL_DIR/../.ability_client_venv/bin/python $SKILL_DIR/scripts/aii_semscholar_bib__fetch.py --out ./references.bib --refs '<list of arXiv ids / DOIs>'
```

## Restoring removed files

Nothing in this folder is marked `delete`; all files are small text files and are kept.
