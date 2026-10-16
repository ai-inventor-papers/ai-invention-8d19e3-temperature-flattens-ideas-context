# Prompts

Complete, auto-generated record of **every prompt the AI Inventor system gave each agent** across this run — generated at repository-upload time so it captures all steps. For the full conversation (assistant turns, thinking, tool calls and results) see the sibling `../messages/` folder.

- Run: `run_wfWEMjpWKygr` — Steering a 3B Code Model Selects One Known Algorithm Rather Than Diversifying

Each prompt is labelled by type and timestamped, with its full untruncated body:

- **SYSTEM-USER** — the pipeline-generated role/instruction prompt placed in the user slot.
- **HUMAN-USER** — the task / human-typed message into the agent stream.
- **SKILL-INPUT** — a skill the agent loaded; its `SKILL.md` instructions, verbatim.

Layout mirrors the run's module tree: one folder per high-level phase, a `round_N/` per iteration where the phase iterates, then each module — a single-task module is one `.md` file, a parallel module (gen_plan / gen_art / gen_viz / gen_demo_art) is a folder with one `.md` per task.

## Index

- **1. create_idea** — `hypo_loop`
  - round_1
    - `chat/prompts/1_create_idea/round_1/1_gen_hypo.md` — 4 prompts
    - `chat/prompts/1_create_idea/round_1/2_review_hypo.md` — 2 prompts
- **2. test_idea** — `invention_loop`
  - round_1
    - `chat/prompts/2_test_idea/round_1/1_gen_strat.md` — 2 prompts
    - `2_gen_plan/` — 3 task(s)
      - `chat/prompts/2_test_idea/round_1/2_gen_plan/gen_plan_experiment_1.md` — 2 prompts
      - `chat/prompts/2_test_idea/round_1/2_gen_plan/gen_plan_experiment_2.md` — 2 prompts
      - `chat/prompts/2_test_idea/round_1/2_gen_plan/gen_plan_experiment_3.md` — 2 prompts
    - `3_gen_art/` — 3 task(s)
      - `chat/prompts/2_test_idea/round_1/3_gen_art/gen_art_experiment_1.md` — 26 prompts
      - `chat/prompts/2_test_idea/round_1/3_gen_art/gen_art_experiment_2.md` — 26 prompts
      - `chat/prompts/2_test_idea/round_1/3_gen_art/gen_art_experiment_3.md` — 14 prompts
    - `chat/prompts/2_test_idea/round_1/4_gen_report_text.md` — 6 prompts
    - `chat/prompts/2_test_idea/round_1/5_review_report.md` — 1 prompt
    - `chat/prompts/2_test_idea/round_1/6_upd_hypo.md` — 1 prompt
  - round_2
    - `chat/prompts/2_test_idea/round_2/1_gen_strat.md` — 2 prompts
    - `2_gen_plan/` — 3 task(s)
      - `chat/prompts/2_test_idea/round_2/2_gen_plan/gen_plan_experiment_1.md` — 2 prompts
      - `chat/prompts/2_test_idea/round_2/2_gen_plan/gen_plan_experiment_2.md` — 2 prompts
      - `chat/prompts/2_test_idea/round_2/2_gen_plan/gen_plan_experiment_3.md` — 2 prompts
    - `3_gen_art/` — 3 task(s)
      - `chat/prompts/2_test_idea/round_2/3_gen_art/gen_art_experiment_4.md` — 12 prompts
      - `chat/prompts/2_test_idea/round_2/3_gen_art/gen_art_experiment_5.md` — 11 prompts
      - `chat/prompts/2_test_idea/round_2/3_gen_art/gen_art_experiment_6.md` — 10 prompts
    - `chat/prompts/2_test_idea/round_2/4_gen_report_text.md` — 3 prompts
    - `chat/prompts/2_test_idea/round_2/5_review_report.md` — 1 prompt
    - `chat/prompts/2_test_idea/round_2/6_upd_hypo.md` — 1 prompt
- **3. report_results** — `gen_paper_repo`
  - `chat/prompts/3_report_results/1_gen_paper_draft.md` — 4 prompts
  - `2_gen_viz/` — 13 task(s)
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_1.md` — 2 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_2.md` — 7 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_3.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_4.md` — 2 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_5.md` — 4 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_1.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_2.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_3.md` — 2 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_4.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_5.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_6.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_7.md` — 3 prompts
    - `chat/prompts/3_report_results/2_gen_viz/gen_viz_report_8.md` — 2 prompts
  - `3_gen_demo_art/` — 4 task(s)
    - `chat/prompts/3_report_results/3_gen_demo_art/gen_demo_art_experiment_1.md` — 5 prompts
    - `chat/prompts/3_report_results/3_gen_demo_art/gen_demo_art_experiment_2.md` — 12 prompts
    - `chat/prompts/3_report_results/3_gen_demo_art/gen_demo_art_experiment_3.md` — 5 prompts
    - `chat/prompts/3_report_results/3_gen_demo_art/gen_demo_art_experiment_4.md` — 4 prompts
  - `4_gen_full_paper/` — 3 task(s)
    - `chat/prompts/3_report_results/4_gen_full_paper/gen_full_paper.md` — 7 prompts
    - `chat/prompts/3_report_results/4_gen_full_paper/gen_paper_site.md` — 9 prompts
    - `chat/prompts/3_report_results/4_gen_full_paper/gen_report_doc.md` — 3 prompts
  - `chat/prompts/3_report_results/5_gen_html_demo.md` — 4 prompts
  - `chat/prompts/3_report_results/6_final_review.md` — 7 prompts
