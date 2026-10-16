# gen_full_paper — report_results

> Phase: `gen_paper_repo` · `gen_full_paper`
> Run: `run_wfWEMjpWKygr` — Steering a 3B Code Model Selects One Known Algorithm Rather Than Diversifying
>
> Full, verbatim record of every prompt the AI Inventor pipeline gave this agent — system-user, human-user and skill-input — in the order they landed. Nothing truncated.

## Task: `gen_full_paper` (terminal_claude_agent)

### [1] SYSTEM-USER prompt · 2026-10-16 08:19:26 UTC

````
<research_methodology>
Write like an experienced academic. Reviewers judge both the science and the writing.

- Claims must be proportional to evidence. Choose verbs carefully — "demonstrate," "observe," and "hypothesize" mean different things.
- Every result needs: what was measured, on what data, the numbers, and what they mean.
- Methodology must be specific enough to reproduce. Section placement follows <paper_structure> below.
- State limitations honestly. Avoid both overclaiming and excessive hedging.
</research_methodology>

<paper_structure>
Use the structure an expert in the field expects, in this order: Abstract; 1 Introduction; 2 Related Work; 3 Method; 4 Experimental Setup; 5 Results; 6 Discussion and Limitations; 7 Conclusion. Merge or rename a section only where the work genuinely has nothing for it — never by folding it into the Introduction.

- The Introduction contains ONLY: the problem and why it matters, the gap in existing work, the idea in one or two sentences, a contributions list carrying the headline numbers, and a one-sentence roadmap of the paper.
- NO literature survey and NO method details in the Introduction. Prior work goes to Related Work, how the method works goes to Method.
- Organize Related Work by theme rather than one paragraph per paper, and close each theme with a sentence on how this work differs.
- Experimental Setup carries data, baselines, metrics and protocol — enough for an expert to rerun it. Results carries findings, not setup.
</paper_structure>

<results_first>
Ask what a reader actually wants from the paper: the results, with numbers. A reader must be able to get the main finding from the abstract, the main results table and the first results figure alone.

- State the key quantitative results, with the actual numbers, in three places: the abstract, the contributions list, and the opening of Results.
- Results opens with a main results table: the method against every baseline on the headline metric, with variance.
- Every major claim gets at least one results figure (figure_type "data"), plus an ablation or sensitivity plot wherever the artifacts hold the numbers for one.
- Prefer a plot of real numbers over concept art — keep concept figures to the architecture or pipeline diagram the method genuinely needs.
- Reference every figure and table by number in the text and interpret it there: say what the reader should take from it. Never drop one in unexplained.
</results_first>

<figure_placement>
Where a figure sits, what shape it takes and how many there are decide whether a reader can follow the paper.

- Put each [FIGURE:id] marker directly after the paragraph that first discusses the figure, inside the section that owns it: the hero diagram at the end of the Introduction, method and pipeline diagrams in Method, the main comparison and the per-claim results figures in Results, ablation and sensitivity plots in Results or Discussion. Never place a figure in the Abstract, Related Work or Conclusion.
- Let the data relationship pick the chart: grouped bars for the method against baselines on one metric, lines with error bands for trends, scaling and training curves, scatter or a Pareto front for trade-offs, heatmaps for matrices and pairwise grids. A handful of numbers is a table, not a figure. Use multiple panels only when they share axes and one takeaway.
- Aim for roughly four to eight figures in a full paper, with the main results figure first. Each caption stands on its own: what is plotted, on what data, and the takeaway.
</figure_placement>

<safeguard_research_reporting>
When the research concerns bypassing or removing a model's safeguards (jailbreaks, refusal
removal, abliteration, safety fine-tuning reversal, or anything whose effect is a model that
refuses less on harmful requests), report the findings as MEASUREMENTS and their implications
for EVALUATION and DEFENCE, never as operational advice for defeating safeguards.
- State what was measured, on what, and how large the effect was, as in any other result.
- Draw the implications for the people who build and test safeguards: what an evaluation misses,
  which defences are brittle and where, what a safety evaluation should measure next.
- Never frame a finding as a recommendation, a recipe or a best configuration for removing
  refusals: no "the practical recommendation is to use X to remove refusals", no "for the
  strongest bypass, edit layers X to Y", no step-by-step settings a reader could follow to make a
  model comply with harmful requests.
- This applies everywhere the finding is stated: abstract, executive summary, key results, best
  result, discussion, conclusion, captions, the website and the interactive page.
</safeguard_research_reporting>

<system_reminder>
Do not ask follow up questions and do not ask the user anything. Execute all steps independently.
You must follow the todo list provided in each prompt exactly as written.
No placeholders, stubs, or incomplete code — all code must be complete and functional.
</system_reminder>

<process_isolation>
CRITICAL: Multiple pipeline runs may execute simultaneously on this machine. `ps aux | grep method.py` matches ALL runs, not just yours.
- NEVER kill processes by name (`killall`, `pkill -f`, `ps aux | grep ... | xargs kill`). This kills OTHER runs' processes.
- NEVER monitor processes by name (`ps aux | grep method.py`). You will see other runs' processes and get confused.
- ALWAYS use PID-based process management:
  Run: `uv run method.py & PID=$!` or `timeout <seconds> uv run method.py & PID=$!`
  Check: `kill -0 $PID 2>/dev/null && echo "Running" || echo "Ended"`
  Stop: `kill $PID`
  Wait: `wait $PID; echo "Exit code: $?"`
  Monitor: `tail -f logs/run.log & TAIL_PID=$!` then `kill $TAIL_PID` when done
</process_isolation>

<workspace>
Your workspace: `/ai-inventor/aii_data/runs/run_wfWEMjpWKygr/4_gen_paper_repo/_4_assemble_paper/paper/workspace`

CRITICAL: Every file you create, write, or save MUST be inside this workspace directory (subdirectories OK). You MUST NOT write files anywhere outside this path — external paths are READ-ONLY. Use absolute paths for all file operations.

EVERY file write MUST start with `/ai-inventor/aii_data/runs/run_wfWEMjpWKygr/4_gen_paper_repo/_4_assemble_paper/paper/workspace/`:
GOOD: `/ai-inventor/aii_data/runs/run_wfWEMjpWKygr/4_gen_paper_repo/_4_assemble_paper/paper/workspace/file.py`, `/ai-inventor/aii_data/runs/run_wfWEMjpWKygr/4_gen_paper_repo/_4_assemble_paper/paper/workspace/results/out.json`
BAD: `/tmp/file.py`, `~/output.json`, `./file.py`, any path outside the workspace
</workspace>
<disposable_outputs>
YOUR WORKING DIRECTORY IS A DELIVERABLE. When this module ends it must read
like a GitHub repository someone else can fork, resume and run — and the bulk
it holds must be either worth keeping or restorable. This run shares a storage
volume with the database; a run that fills it stops every other run on the box.

So before you finish, produce TWO files:

1. `.aii/manifest.yaml` — one entry per heavy path, each with EXACTLY ONE decision.
   The `.aii/` directory ALREADY EXISTS in your cwd: write the file into
   it. Do not create, replace or `touch` `.aii` itself — a plain file by
   that name makes the manifest unwritable for the rest of the module.

```yaml
entries:
  - path: results/
    keep: six GPU-hours of sweep output, not reproducible inside this run
  - path: hf_cache/
    delete: redownloadable
    source: "huggingface-cli download meta-llama/Llama-3-8B"
  - path: checkpoints/
    delete: regenerable
    source: "uv run train.py --epochs 3 --seed 0"
```

   - `keep:` takes a ONE-LINE reason. Use it for the expensive and the
     irreproducible: trained weights, long-running results, datasets you
     collected yourself.
   - `delete:` takes `redownloadable` (and a `source:` naming the repo id, URL
     or command) or `regenerable` (and a `source:` that is the command which
     rebuilds it). These are deleted AFTER the round ends, never mid-step.
   - Every path is RELATIVE TO YOUR CWD and must resolve INSIDE it. Absolute
     paths, `..`, and anything resolving outside are rejected.
   - Globs and whole directories are fine. A whole `hf_cache/` is ONE entry —
     do not list files individually.

2. `README.md` — written as if your cwd were a GitHub repository: what you
   did, the layout with a line per important file/directory, how to run it,
   and a **"Restoring removed files"** section giving the install/download
   command for EVERY `delete` entry. An `install.sh` or `restore.sh` beside it
   is welcome.

A CHECKER RUNS WHEN YOU SUBMIT. If anything heavy has no decision it fails
your submission and hands you the uncovered list, grouped by directory with
sizes, and you fix the manifest and submit again.

WHAT NEEDS NO DECISION — do not write entries for these:
- text and code files, at ANY size (source, JSON, CSV, YAML, logs, markdown);
- anything under the auto-keep floor (10 MB), whatever it holds.
Only large binaries and cache directories (`hf_cache/`, `.venv/`,
`node_modules/`, `checkpoints/`, `wandb/`, `__pycache__/`, …) need one.

NEVER mark your results, figures, papers, code, logs or anything a later step
reads as `delete`. If a later step needs it, it is a `keep`.

WHAT A `keep` BUYS YOU. Anything you do not mark `delete` stays exactly where
you wrote it, on this run's storage volume, at the path it already has — it is
not moved, renamed or copied. A later round reads it there, by that absolute
workspace path, so a checkpoint you keep is a checkpoint the next round can
load instead of retraining. It is also the ONLY copy: the publish step pushes
your cwd to GitHub but skips every file of 100 MB or
more, so trained weights and large binary artifacts never leave the volume.
Name each kept artifact in your results and your `README.md` by its path
RELATIVE to your cwd, and say it stays on the run's volume rather than in the
published repository. Never write an absolute server path into a file that is
published: a reader's machine has none of them.
</disposable_outputs>

<task>
Typeset <paper_draft> as LaTeX with BibTeX, insert <available_figures>, and compile it to PDF.
</task>

<tool_use>
Maximize parallel tool calls. Parallelize independent operations, only sequentialize dependencies.
- Multiple searches/fetches on different topics → parallel in one turn
- Search then fetch results → sequential (need URLs first)
</tool_use>

<publishable_paper_rules>
This is the PUBLISHABLE PAPER. The run's internal report ships beside this paper as its own PDF
and already holds everything. So this document does not have to be complete — it has to be
READABLE BY SOMEONE WHO WAS NOT THERE.

- ONE ARGUMENT. Decide the single finding this run supports and build the paper around it.
  Everything that does not serve it is cut, not shrunk.
- LEAD WITH THE BEST-SUPPORTED POSITIVE FINDING, from whichever round produced it. Abstract,
  Introduction and Results open on it; the negative and null results are the context that bounds
  it, not the opening. Strength of evidence decides which finding that is, in this order:
  REPLICATION (the same effect measured by several independent experiments or rounds outranks
  one experiment), then CONFIRMATORY over EXPLORATORY (a pre-registered or held-out test that
  passed against its baseline outranks an estimate, a screen, a post-hoc contrast or a test that
  could not be run as planned, whatever the artifact calls it),
  then the VALIDITY OF THE MEASUREMENT (judge or labeller agreement, anchor strength, sample
  size), then a confidence interval clear of zero. Effect size only breaks ties. Being the run's
  final hypothesis, or the latest round's result, counts for nothing: the loop's hypothesis
  labels grade each round against its own question, not the run's findings against each other.
  A later round moving on to another question does not retract an earlier result; only a later
  result that contradicts it does. Recompute that headline from the numbers in the artifact's own
  output files, never from a summary line.
- ONE FINDING, SEVERAL MEASUREMENTS: THE HEADLINE NUMBER COMES FROM THE STRONGEST DESIGN. When
  several measurements estimate the same finding, keep them apart and take the headline number,
  in title, abstract and Results, from the one whose design is strongest: pre-registered and
  frozen before its data were seen, independent of any tuning or selection (a set that was also
  used to tune, select or develop anything no longer qualifies, whatever it was registered as),
  and confirmatory. Size, population breadth and recency do not decide it. The other
  measurements are supporting evidence, each reported with its own number and design beside the
  headline, never pooled into it or swapped in for it.
- STRUCTURED BY IDEA, NEVER BY ITERATION. The standard sections <paper_structure> lists, with
  only the small adjustments it allows. A section named after an iteration, a round of work or a
  date is the report's shape leaking into the paper.
- NO PROCESS. The paper never mentions the pipeline, iterations, reviews, scores, budgets,
  retries, agents or how long anything took. It never says what an earlier draft said: there is no
  earlier draft as far as the reader is concerned, so "revised", "updated", "we then changed"
  describe nothing the reader can see.
- THE METHOD AS IT FINALLY STANDS. Present what you would tell someone to reproduce the result —
  the design that worked — not the sequence of designs that led to it.
- DEAD ENDS ONLY WHERE THEY INFORM. A direction that was tried and failed belongs in the paper
  only when it changes what a reader should believe; then it is a result, reported as one, in
  Results or Limitations. Otherwise it stays in the report.
- HONEST ABOUT SCOPE. Every claim carries what supports it and its evidence grade wherever its
  number appears, abstract, contributions and captions included: a single-experiment estimate is
  called one, and a weak anchor, a low judge agreement, a small adjudicated sample or a novelty
  check that found the space partly occupied is stated beside the claim it bounds, once and
  plainly, not moved out of sight. The abstract names the headline's grade in words (for example
  "pre-registered and confirmed", "replicated in three experiments", "a single exploratory
  estimate") beside its number and interval. What the evidence does not reach goes in Limitations.
- SELF-CONTAINED. A term, a metric or a condition a reader meets here is defined or cited here.
  Never a pointer to the report, and never a run-internal name or code.
- NO PIPELINE INTERNALS. Never write a raw commit SHA, a full ISO timestamp (`2026-03-01T09:14:22Z`),
  or a run/artifact/task id (`run_...`, `art_...`) into the prose — they identify nothing to a
  reader. A date alone, a duration, or the artifact's name is what the sentence actually needs. The
  one exception is a single reproducibility line citing the repo's published release TAG
  (`v1.4.0`), never a SHA.
</publishable_paper_rules>

<paper_structure>
The paper's default sections are:
Abstract, Introduction, Related Work, Method, Results, Discussion, Limitations, Conclusion, then the numbered references. The draft step may have adjusted that list slightly where most of the field's papers (their outlines are at
the end of <style_exemplars>) share an adjustment: a section renamed to the field's word, two
merged, one split, one moved, or a section the field treats as standard added. Typeset the
sections as <paper_draft> names and orders them; a heading that differs from the default list is
a decision, not a mistake to correct. These always stay, whatever the draft did, because later
steps read them:
- Abstract. The draft's own `abstract` field, typeset as the LaTeX abstract.
- Introduction, first after the abstract. Figure 1, the flagship, is marked at its end, and the
  LaTeX step places every figure where its marker sits.
- Limitations, under that word, as a section or a titled subsection of Discussion. The project
  site copies it into its Limitations panel, and <publishable_paper_rules> sends everything the
  evidence does not reach there.
- The numbered references, last. The LaTeX step builds `references.bib` from them.
The paper also always has a part that describes the method and a part that reports the results,
because the project site presents both; those two may carry the name the field gives them.
</paper_structure>

<paper_draft>
THE PAPER. Which single finding it argues, how it is structured, which figures it shows and where
each one goes were all decided before you were called; this block is the result. Typeset it. The
first typesetting pass does not restructure it, re-select what it covers, or add sections it does
not have. Rewording for the register the style blocks below describe is in scope; changing what the
paper says is not. The REVISION PASS todo is the one place the draft may move, and only within the
limits that todo sets.

title: Steering a 3B Code Model Selects One Known Algorithm Rather Than Diversifying
abstract: >-
  Temperature, prompt instructions and activation steering are used to make language models propose less obvious solutions,
  but it is rarely tested whether they change the solution idea or only its wording. We label the algorithm family of every
  program Qwen2.5-3B-Instruct writes for open sorting and path-search prompts, execute each program, and test whether a difference-in-means
  steering direction away from the default family flattens the distribution over families or selects one alternative. In a
  pre-registered test whose rules, strengths and predicted gainers were frozen by hash, the direction met the selection rule
  on both tasks, replicated on a fresh-seed re-draw. On sorting in that re-draw, bubble sort fell from 62% of programs to
  0%, quicksort rose to 68%, and the entropy over families lay 0.73 bits below the mean of five matched-norm random directions
  (95% CI [−0.95, −0.45]). The scope is narrow: one 3B model, one bare prompt per task, a rule that accepted the top prediction
  of either of two frozen rankings, and random directions that alone move sorting substantially; on path search A* replaced
  BFS but the pass rate halved, missing the frozen correctness bar. Selection does not reach new ideas: steering toward families
  the model never writes fails where naming them in the prompt succeeds, and no condition produced correct code outside known
  algorithms. Temperature adds families slowly while correctness collapses, and random seed strings concentrate the choice.
  On these tasks, the controls choose among known ideas; they do not create new ones.
paper_text: |
  ## Abstract

  Temperature, prompt instructions and activation steering are used to make language models propose less obvious solutions, but it is rarely tested whether they change the solution idea or only its wording. We label the algorithm family of every program Qwen2.5-3B-Instruct writes for open sorting and path-search prompts, execute each program, and test whether a difference-in-means steering direction away from the default family flattens the distribution over families or selects one alternative. In a pre-registered test whose rules, strengths and predicted gainers were frozen by hash, the direction met the selection rule on both tasks, replicated on a fresh-seed re-draw. On sorting in that re-draw, bubble sort fell from 62% of programs to 0%, quicksort rose to 68%, and the entropy over families lay 0.73 bits below the mean of five matched-norm random directions (95% CI [−0.95, −0.45]). The scope is narrow: one 3B model, one bare prompt per task, a rule that accepted the top prediction of either of two frozen rankings, and random directions that alone move sorting substantially; on path search A* replaced BFS but the pass rate halved, missing the frozen correctness bar. Selection does not reach new ideas: steering toward families the model never writes fails where naming them in the prompt succeeds, and no condition produced correct code outside known algorithms. Temperature adds families slowly while correctness collapses, and random seed strings concentrate the choice. On these tasks, the controls choose among known ideas; they do not create new ones.

  ## 1 Introduction

  Language models are increasingly asked to design solutions rather than to recall them, and users who want a less obvious design reach for two kinds of control. The first is decoding: raising the sampling temperature is widely treated as the model's creativity parameter [1], although high temperatures also degrade text [2]. The second is the model's internal state: activation steering adds a direction to the residual stream during generation [3, 4], and recent work steers models toward more creative or more diverse outputs [5, 6, 7]. Both kinds of control are usually judged by how different the outputs look. For a design task, the question that matters is narrower: does the control make the model pick a different solution idea, and is that idea one it did not already have?

  Code generation lets us ask that question with exact measurements. Asked to "implement a path search algorithm", an instruction-tuned model writes breadth-first search (BFS) most of the time, with depth-first search (DFS), Dijkstra's algorithm and A* search as a minority. Every program can be labelled with the algorithm family it implements and executed against a fixed test suite. A control that adds novelty should move probability onto families the model rarely writes, or onto programs no label covers, while those programs still pass. Instruction tuning is known to narrow output diversity [8, 9, 10], and incidental prompt cues are known to move which algorithm family a code model picks [11]. What is missing is a controlled test of how internal edits move this choice, and against which baseline.

  The baseline is the hard part. A steering vector of the right norm changes outputs whatever its direction, and the effect of a single random direction varies widely from draw to draw. A targeted direction that raises diversity once is therefore weak evidence. A cleaner test separates two behaviours that a diversity score conflates. A *flattening* intervention spreads probability across the families the model knows, so the share of the default falls and no other family takes over. A *selecting* intervention hands most of the mass to one other family. The two predict opposite things for entropy relative to random directions of the same norm, and only selection predicts which family will gain.

  We ran that test as a pre-registered experiment on Qwen2.5-3B-Instruct [12], on two open coding prompts (path search and sorting), with decision rules frozen by hash before the data existed. We build an *away-from-mode direction* as the difference in means between residual stream activations of programs that do and do not implement the model's default family, add it at layers 32 to 34 during the first 64 generated tokens, and compare it with five matched-norm random directions, an off-target real direction, temperature, and simply asking for a family. The direction meets the frozen selection rule on both tasks, on the main draw and on a fresh-seed re-draw. On sorting in the re-draw, bubble sort falls from 62% of programs to 0% and quicksort, the top prediction of the frozen projection ranking, rises to 68%, while the entropy of the distribution over algorithm families falls 0.73 bits below the random-direction mean (95% CI [−0.95, −0.45]; Figure 1). The scope of this result is one 3B model and one bare prompt per task, and the rule accepted the top prediction of either of two frozen rankings. The same pattern holds on a two-family menu in a second experiment under a different prompt. Selection does not reach new ideas: steering toward families the model never writes mostly fails where naming them in the prompt succeeds, and no condition yielded a correct program outside the known algorithms. Temperature, random seed strings and negative instructions in the prompt behave the same way at the level of behaviour: they reorder or concentrate a small menu of textbook ideas.

  Our contributions are:

  - **A pre-registered select-versus-flatten test for activation steering**, with frozen predictions of the gaining family and a draw-averaged random-direction baseline (Section 3).
  - **Evidence that steering selects, pre-registered and replicated across draws and tasks on one model.** On a fresh-seed re-draw the away-from-mode direction gives quicksort 68% and A* 63% of programs, against 24% and 6% under matched-norm random directions; on sorting, entropy falls 0.73 bits below the random mean [−0.95, −0.45], and on path search the non-mode share rises 0.53 above it [0.45, 0.60] (Section 5.1). A second, exploratory experiment with a different prompt and layer band turns 29% DFS into 97% DFS at an unchanged pass rate (Section 5.2).
  - **A prompting ceiling for novelty.** Steering toward families absent from the baseline produces them in 0% to 1.3% of programs for three of four targets, while naming them in the prompt produces them in 92% to 100%; no control produced correct code outside the known families (Section 5.3).
  - **Behavioural context for the same conclusion**: from T = 0.3 to T = 1.0, temperature adds 0.4 (path search) and 1.8 (sorting) expected families per ten programs while the path-search pass rate falls from 0.49 to 0.19; random seed strings lower the entropy over families by 0.34 and 0.68 bits; and negative instructions against families the model never writes reshuffle the families it does write, violating regularity in 8 of 46 tested cells against 0 of 45 for placebo prompts (Sections 5.4 and 5.5).

  Section 2 places this work against prior studies of temperature, steering and negative instructions. Sections 3 and 4 give the method and setup, Section 5 the results, and Sections 6 and 7 discuss what they imply and where they stop.

  [FIGURE:fig1]

  ## 2 Related Work

  **Temperature, sampling and output diversity.** Peeperkorn et al. [1] find that temperature is weakly correlated with novelty and moderately correlated with incoherence in story generation, and Holtzman et al. [2] show that unrestricted sampling at high temperature degenerates. Instruction tuning and RLHF reduce output diversity [8], writing with a model homogenises content [9], and NoveltyBench finds that models produce far fewer distinct answers than humans [10]. For code, Narula et al. [11] report that subtle prompt cues shift which algorithm family a model implements. These studies measure diversity in text or embeddings. We measure it as the distribution over execution-checked algorithm families and separate the number of ideas from the number of phrasings of each, so that a control that rewrites the same idea is not credited with a new one.

  **Activation steering and its reliability.** Adding a direction to the residual stream steers behaviour [3, 13]; Contrastive Activation Addition builds the direction from the difference in means between contrasting examples [4], Inference-Time Intervention shifts selected attention heads along probe directions [14], and a single difference-in-means direction mediates refusal [15]. These results rest on the view that concepts are encoded linearly [16]. Closest to our setting, difference-in-means directions added during generation push code models toward a target programming language or library, often against the prompt's request [17]. Reliability is uneven: steerability varies across inputs and some concepts resist steering [18], steering is unreliable when the target behaviour is not represented by a coherent direction [19], and simple prompting baselines often match or beat steering [20]. Creativity steering adds a creative-minus-boring direction [5], while STARS and Riemannian activation steering optimise several directions jointly across concurrent generations to diversify them [6, 7]. Our test differs in three ways. The target is the algorithm family, checked by execution, rather than a language, library or style. It uses one fixed direction and asks whether that direction flattens or selects, with a frozen prediction of the gaining family. It compares against the mean of five matched-norm random directions per strength, because a single random draw can move the output distribution as much as a targeted one.

  **Negative instructions and choice structure.** Instruction steering adds the representation of an instruction to the forward pass [21], and negative constraints can backfire by priming the forbidden item [22]. In discrete-choice terms, removing an option from a choice set should never lower the share of an option that remains; this property is called regularity, and its violations are a classic signature of context effects in human choice [23]. Violations of related choice axioms have been reported for language models in economic settings [24]. We use regularity as a test of whether a negative instruction in the prompt acts as choice-set restriction, and we report it as context for the steering result rather than as a mechanism.

  ## 3 Method

  ### 3.1 Ideas, menus and the measurements on them

  For each prompt we sample programs, label each with the algorithm family it implements, and execute it. We call that family the program's *idea*. The *idea distribution* of a condition is the share of programs per idea, its *mode* is the most frequent idea at baseline, and the *non-mode share* is one minus the share of the mode. Idea entropy is the Shannon entropy of the idea distribution in bits, with the Miller-Madow correction when conditions of different size are compared. We also report Hill numbers [25] and, for the question of ideas against phrasings, the expected number of distinct ideas and of distinct phrasings in a random draw of ten programs, where two programs share a phrasing when their normalised code has edit-distance similarity of at least 0.85. An *off-menu idea* is a family absent from the baseline sample. A program counts as correct only if it passes every test case of the execution oracle (Section 4).

  ### 3.2 The away-from-mode direction

  Let $h_\ell(x)$ be the residual stream activation at layer $\ell$ averaged over a *commitment window*: the 17 generated tokens starting at the first token that names or implements the idea, or the first 32 generated tokens when no such token exists. The away-from-mode direction at layer $\ell$ is the difference in means

  $$v_\ell = \operatorname{mean}_{x:\,\text{idea}(x)\neq m} h_\ell(x) - \operatorname{mean}_{x:\,\text{idea}(x)=m} h_\ell(x),$$

  computed on baseline programs, where $m$ is the mode, and normalised to unit length. During generation we add $\alpha \cdot \bar r_\ell / 3 \cdot v_\ell$ at each of the three band layers, where $\bar r_\ell$ is the median residual norm at that layer and $\alpha$ is the steering coefficient. The edit applies at the final prompt token and the first 64 generated tokens. The band (layers 32 to 34 of 36) was chosen by a per-layer linear probe for the idea against a shuffled-label control [26]; probe accuracy was nearly flat across layers, so the band choice carries little information. Figure 2 summarises the construction and the comparators.

  [FIGURE:fig2]

  ### 3.3 Frozen predictions and decision rules

  Before any steered generation, we froze two quantities by SHA-256 hash. The first is a ranking of predicted gainers: the projection of $v$ onto each idea centroid's offset from the modal centroid (for path search A* 0.843, Dijkstra 0.742, other 0.685, DFS 0.656; for sorting quicksort 0.973, merge sort 0.887, heap sort 0.521). A second ranking, by each centroid's nearest-neighbour similarity to the modal centroid, was frozen as a competing prediction. The second quantity is two steering strengths, calibrated on separate runs of 30 programs: $s_1$, the $\alpha$ whose mode share is closest to half the baseline mode share, and $s_2$, the $\alpha$ with the lowest mode share whose pass rate stays at least 0.8 times the baseline's. The frozen rules read:

  - **SELECT**: at $s_2$ one non-modal idea takes at least half the programs, that idea is a predicted gainer (the top idea of either frozen ranking: A* or IDDFS on path search, quicksort or selection sort on sorting), and the distance from the uniform distribution rises again from $s_1$ to $s_2$.
  - **FLATTEN**: the distance from uniform falls from baseline to $s_1$ to $s_2$, and no non-modal idea reaches half the programs.

  ### 3.4 Comparators

  Each targeted setting is compared with five random directions of matched norm at the same strength, and the comparison statistic is the difference between the targeted value and the *mean over the five draws*, with a hierarchical bootstrap over draws and programs (10,000 resamples for entropy, 5,000 for shares). A single random draw is not used as the baseline, because draw-to-draw variation is large (Section 5.1). Further comparators are an off-target real direction (the other task's away-from-mode direction), temperatures 1.0 and 1.3, directions toward the centroids of two off-menu ideas per task, and a prompt that names the off-menu idea ("... using IDDFS.").

  ## 4 Experimental Setup

  **Models and prompts.** The main model is Qwen2.5-3B-Instruct [12] in bfloat16 with its chat template. The prompts are bare user turns: "Implement a path search algorithm in Python" and "Implement a sorting algorithm". A third prompt, "Implement a function that finds a shortest path in a weighted graph", appears only in the temperature, seed and negative-instruction experiments, where the model writes Dijkstra's algorithm in nearly every program. A secondary model, gemma-2-2b-it [27], is used only for the negative-instruction experiments of Section 5.5.

  **Sampling.** All steering conditions ran through one HuggingFace engine at temperature 0.7 with no top-k, a 768-token cap and a per-sample seeded inverse-CDF sampler, so the same sample index sees the same random numbers in every condition (common random numbers). The baseline has 300 programs per task (seeds 0 to 299); each steered and random cell has 150 (seeds 0 to 149), random cells at $s_1$ have 100, and the re-draw uses fresh seeds 1000 to 1149. The HuggingFace baseline agrees with a vLLM [28] baseline from the negative-instruction experiments (Jensen-Shannon divergence 0.009 on path search and 0.001 on sorting) \footnote{Code: \url{https://github.com/ai-inventor-papers/ai-invention-8d19e3-temperature-flattens-ideas-context/tree/main/round-2/experiment-6}}. The temperature and seed experiments used vLLM with 100 programs per cell, sampling temperatures T from 0.3 to 1.6, top-k 10 or none, and a 1,536-token cap on the re-draw \footnote{Code: \url{https://github.com/ai-inventor-papers/ai-invention-8d19e3-temperature-flattens-ideas-context/tree/main/round-2/experiment-4}}.

  **Labels.** A deterministic labeller assigns each program a known path-search family (BFS, DFS, Dijkstra, A*, SPFA, Bellman-Ford, IDDFS, greedy best-first, bidirectional, Floyd-Warshall) or sorting family (bubble, quick, merge, selection, insertion, heap, counting, radix, shell and others), plus "other" and "unparseable". Against a blind gpt-4.1-mini judge, its Cohen's kappa [29] is 0.84 [0.78, 0.89], and two judge runs agree at 0.92 . A separate audit of the steering outputs gives kappa 0.94 on sorting (n = 55) but 0.39 on path search (n = 45, agreement 0.47), where heuristic and uninformed searches are hard to separate in truncated programs . The sorting labels are therefore the cleaner measurement, and we take the headline number from sorting.

  **Correctness.** A sandboxed execution oracle runs each program under time and memory limits. Path-search programs face 50 random directed graphs (10% with unreachable targets) and 25 grids; sorting programs face 50 lists (empty, 48 random lists of up to 200 integers, and one with duplicates). The oracle adapts to the program's interface and counts a program as passing only when every test case is correct, a strict form of functional correctness [30].

  **Pre-registration.** The predicted-gainer rankings, steering strengths and decision rules were written to files whose SHA-256 hashes were recorded before the steered generations ran. Independent code re-derived every verdict and confidence interval reported in Section 5.1 from the raw generations, and random draws compared with each other give intervals that include 0 .

  ## 5 Results

  ### 5.1 The away-from-mode direction selects one predicted idea

  The frozen rule returns SELECT on both tasks and both draws. The headline measurement is the sorting re-draw at $s_2$ (fresh seeds 1000 to 1149): idea entropy lies 0.73 bits below the mean of the five matched-norm random directions (1.022 against 1.749 bits; 95% CI [−0.95, −0.45]), the signature of selection rather than flattening. Table 1 gives the idea distributions and Figure 1 plots them against the random-direction mean. On sorting at $s_2$ ($\alpha = 0.473$), bubble sort falls from 62.0% of programs to 0.7% on the main draw and to 0% on the re-draw. Quicksort, the top prediction of the projection ranking, rises from 23.3% to 65.3% and 68.0%, and merge sort takes nearly all of the rest. The pass rate stays at 0.92 and 0.91, above the frozen bar of 0.8 times baseline .

  On path search at $s_2$ ($\alpha = 0.224$), BFS falls from 61.3% to 12.7% and 14.0%, and A*, again the top predicted gainer, rises from 8.0% to 56.7% and 63.3%. None of the five random directions at $s_2$ makes A* the top gainer; they leave BFS at 61% to 72% of programs. Selection on path search costs correctness: the pass rate falls to 0.17 on both draws, against 0.34 for the random-direction mean and below the frozen bar of 0.8 times baseline (0.25) that the 30-program calibration had predicted $s_2$ would meet, and 77% to 78% of outputs reach the token cap .

  **Table 1.** Idea distribution (% of programs), idea entropy (bits) and pass rate under the away-from-mode direction and its comparators. Random mean pools the five matched-norm random directions at $s_2$ (750 programs); its entropy column gives the range over the five draws. Steering strengths: $s_1$ = 0.05 on both tasks, $s_2$ = 0.224 (path search) and 0.473 (sorting). Qwen2.5-3B-Instruct, temperature 0.7 except in the temperature rows.

  | Task | Condition | n | Mode (BFS / bubble) | Predicted gainer (A* / quicksort) | Other ideas | Entropy | Pass |
  |:-|:-|:-|:-|:-|:-|:-|:-|
  | Path search | Baseline | 300 | 61.3 | 8.0 | DFS 14.0, Dijkstra 12.0 | 1.73 | 0.31 |
  | Path search | Random directions, $s_2$ (mean) | 750 | 66.5 | 6.1 | DFS 11.6, Dijkstra 11.3 | 1.43 to 1.73 | 0.34 |
  | Path search | Away-from-mode, $s_1$ | 150 | 52.0 | 18.0 | Dijkstra 16.0, DFS 7.3 | 1.94 | 0.35 |
  | Path search | Away-from-mode, $s_2$ | 150 | 12.7 | 56.7 | DFS 14.7, Dijkstra 11.3 | 1.86 | 0.17 |
  | Path search | Away-from-mode, $s_2$, re-draw | 150 | 14.0 | 63.3 | DFS 12.7, Dijkstra 7.3 | 1.65 | 0.17 |
  | Path search | Off-target real direction, $s_2$ | 150 | 37.3 | 26.7 | DFS 21.3, Dijkstra 8.0 | 2.13 | 0.21 |
  | Path search | Temperature 1.0 | 150 | 60.7 | 5.3 | DFS 18.7, Dijkstra 9.3 | 1.71 | 0.23 |
  | Path search | Temperature 1.3 | 150 | 42.0 | 3.3 | other 24.0, DFS 16.0 | 2.12 | 0.05 |
  | Sorting | Baseline | 300 | 62.0 | 23.3 | merge 9.0, selection 3.7 | 1.50 | 0.98 |
  | Sorting | Random directions, $s_2$ (mean) | 750 | 41.2 | 24.0 | merge 17.6, selection 14.5 | 1.39 to 1.94 | 0.98 |
  | Sorting | Away-from-mode, $s_1$ | 150 | 28.7 | 50.7 | merge 14.0, selection 6.0 | 1.70 | 0.99 |
  | Sorting | Away-from-mode, $s_2$ | 150 | 0.7 | 65.3 | merge 33.3 | 1.03 | 0.92 |
  | Sorting | Away-from-mode, $s_2$, re-draw | 150 | 0.0 | 68.0 | merge 30.0 | 1.01 | 0.91 |
  | Sorting | Off-target real direction, $s_2$ | 150 | 23.3 | 34.7 | merge 33.3 | 1.88 | 0.98 |
  | Sorting | Temperature 1.0 | 150 | 43.3 | 31.3 | selection 11.3, merge 10.7 | 1.94 | 1.00 |
  | Sorting | Temperature 1.3 | 150 | 47.3 | 25.3 | merge 10.0, selection 10.0 | 2.01 | 0.81 |

  Figure 3 gives the pre-registered comparisons with the random-direction mean. On sorting, entropy at $s_2$ lies 0.71 bits below the random mean on the main draw ([−0.94, −0.44]) and 0.73 bits below on the re-draw ([−0.95, −0.45]). A flattening direction would raise entropy above random perturbations of the same norm; this direction concentrates the distribution on two families instead. The non-mode share lies 0.41 above the random mean on both draws ([0.24, 0.58] on the re-draw) .

  Path search shows the same selection with a different entropy signature. The non-mode share lies 0.54 above the random mean on the main draw ([0.47, 0.61]) and 0.53 above on the re-draw ([0.45, 0.60]). Entropy, however, is above the random mean on the main draw (+0.32 bits, [0.04, 0.56]) and undetermined on the re-draw (+0.10, [−0.19, 0.36]). The baseline mode is so dominant that moving the majority to A* while DFS, BFS and Dijkstra keep 7% to 15% each raises entropy even though one family takes over. Entropy alone would have called this a diversity gain; the identity of the gaining family shows it is a switch of default .

  [FIGURE:fig3]

  Three checks bound the result. First, the nearest-neighbour ranking was wrong on both tasks: it predicted IDDFS for path search and selection sort for sorting. The direction lands on the family along its own projection, not on the family whose centroid lies closest to the mode. Second, the off-target real direction, built for the other task, also makes A* (26.7%) and quicksort (34.7%) the most common non-default families, though neither reaches half the programs (the mode falls to 37.3% and 23.3%). A* is a common sink on path search: a negative instruction against greedy best-first search also raises it, from 2.7% to 58% (Section 5.5). The predicted gainers are therefore partly each task's runner-up, and the projection ranking's correct prediction is weaker evidence of geometric prediction than it first appears. Part of the effect is a generic push away from the default, and the task-specific direction is what turns it into a majority for one family. Third, random directions are not inert. On sorting, random draw 3 at $s_2$ gives selection sort 48% of programs, random draw 0 gives quicksort 50%, and the random mode share at $s_2$ ranges from 0.19 to 0.69. Quicksort was also the most common non-modal family in 7 of the 10 random cells on sorting, so on that task the identity of the gainer is less diagnostic than on path search, and the entropy contrast carries the evidence. A comparison with any single random cell would have misled in either direction .

  ### 5.2 The same selection under a different prompt and layer band

  A second experiment on the same model, with a different design, shows the same behaviour. There the prompt fixed the function signature and output format, which narrowed the path-search menu to two families (BFS 98 and DFS 44 of 150 programs at temperature 0.7, pass rate 0.673), and the direction was a difference in means taken over the first 32 generated tokens at layers 29 to 31. The direction had been registered as a flattening control. At $\alpha = 0.224$ it produced DFS in 145 of 150 programs at an unchanged pass rate (0.680), and at $\alpha = 0.106$ already in 126. Idea entropy fell from 1.175 to 0.235 bits. Three matched-norm random directions at the same strength left the split near baseline (BFS 44 to 50, DFS 21 to 31 of 75) \footnote{Code: \url{https://github.com/ai-inventor-papers/ai-invention-8d19e3-temperature-flattens-ideas-context/tree/main/round-1/experiment-3}}. With two families, a direction pointing from the mode toward the menu's mean overshoots the uniform point and selects the minority family. This measurement is exploratory as evidence for selection: the selection was observed after the flattening test it was designed for had failed. It agrees with the pre-registered result on a different prompt, layer band and window.

  ### 5.3 Selection does not reach new ideas

  If steering only selects among families the model already writes, it should fail to produce families it never writes. Table 2 tests this with directions toward the centroids of off-menu families, built from programs the model wrote when asked for them, and compares them with simply asking.

  **Table 2.** Steering toward an off-menu family against naming it in the prompt (share of programs implementing the target, and pass rate). Steered cells n = 150 at the frozen strengths ($\alpha$ = 0.224, or 0.473 for heap sort), prompted cells n = 60.

  | Task | Target family | Steered: target share | Steered: pass | Prompted: target share | Prompted: pass |
  |:-|:-|:-|:-|:-|:-|
  | Path search | IDDFS | 0.0% | 0.30 | 91.7% | 0.03 |
  | Path search | Bellman-Ford | 0.0% | 0.55 | 100% | 0.75 |
  | Sorting | Counting sort | 1.3% | 0.98 | 100% | 0.33 |
  | Sorting | Heap sort | 91.3% | 0.95 | 100% | 1.00 |

  Three of the four directions fail: the IDDFS direction moves mass from BFS to DFS (35.3%) and the Bellman-Ford direction moves it to Dijkstra (34.7%), the nearest families the model already writes. Heap sort is the exception, at 91.3% with a pass rate of 0.95. Naming the family works for all four at once . The same holds for the broader notion of novelty. In the two-family experiment of Section 5.2, a blind judge labelled every passing program that the deterministic labeller had put in its catch-all class; all 70 were known algorithms, and the share of correct programs that implement no known algorithm was 0 in every condition of that experiment, including concept erasure with LEACE [31], which cut the balanced accuracy of a linear idea probe on a weighted shortest-path task from 0.888 to 0.334 (chance 0.333) without moving the outputs off the known families . On textbook tasks this metric is near its floor by construction, so the zero bounds novelty in this setting rather than in general.

  ### 5.4 Temperature adds ideas slowly and breaks code quickly

  Figure 4 sets idea count against correctness across temperature on the unsteered prompts. On path search without top-k, the expected number of distinct ideas among ten programs moves from 3.48 at T = 0.3 to 3.91 at T = 1.0, while the pass rate falls from 0.49 to 0.19; at T = 1.3, 35% of programs fall in the "other" class and 65% hit the token cap, and at T = 1.6 almost nothing parses. Sorting is the one task where heat buys ideas at little cost: expected ideas among ten rise from 2.06 to 3.82 between T = 0.3 and T = 1.0 at a pass rate of 0.99, but the new mass goes to the same five comparison sorts. Top-k 10 keeps T = 1.6 parseable and adds a few rare families (nine classes on path search), at a pass rate of 0.06 on path search and 0.82 on sorting. On the weighted shortest-path prompt the model writes Dijkstra's algorithm in 98 to 100 of 100 programs up to T = 1.0 .

  [FIGURE:fig4]

  The model's default is a mode, not an average. Even at T = 0.3 with top-k 10, ten path-search programs contain about 3.5 ideas written in about 9 distinct phrasings; the case of ten ideas with one phrasing each never occurs in any cell (the largest expected count among ten is 4.9). A pre-registered law in which temperature only rescales fixed idea utilities, so that idea log-odds are linear in 1/T without reordering, failed its criteria on both tasks and both draws, and out of sample it beat a fixed-utility baseline (the T = 0.7 shares raised to the power 0.7/T) on path search (mean absolute error 0.040 against 0.073) but lost on sorting (0.100 against 0.028) . Raising temperature is a weak way to change the idea and a strong way to lose correctness.

  ### 5.5 Prompt context also selects rather than diversifies

  Two prompt-level manipulations behave like the steering direction. Prepending a random seed string ("seed=d32qxk4nt43" or a list of random words) to the prompt lowers idea entropy at T = 0.7 by 0.34 bits on path search ([−0.53, −0.13]) and 0.68 bits on sorting ([−0.92, −0.47]), over 120 strings with 5 samples each against 300 unseeded programs. On sorting, random words send 282 of 300 programs to bubble sort. The strings displace the residual stream at the final prompt tokens 1.1 to 3.2 times more than a negative instruction does, so a large internal displacement in an irrelevant direction concentrates the choice instead of spreading it. This narrowing is an exploratory finding: the pre-registered prediction of seed effects from a utility gap failed (sorting predicted flip rate 0.39, observed 0.017) .

  Negative instructions ("Do not use X." appended to the prompt) act as instructions to choose something else rather than as removal of an option. The comparison condition is a placebo prompt that appends a negative instruction against an irrelevant algorithm ("Do not use the Rabin-Karp algorithm." for path search, "Do not use Kruskal's algorithm." for sorting). In a pre-registered test on 5,930 confirmation programs generated after all predictors were frozen, negative instructions lowered the share of a family they did not name, which pure choice-set restriction cannot do, in 8 of 46 tested cells (Fisher's exact test, Holm-corrected p < 0.05, drop larger than the placebo noise floor), spread over 6 negative instructions. Placebo blocks compared with each other gave 0 such cells out of 45, and shuffling the labels of negative-instruction and placebo programs gave 0 in each of 20 repetitions \footnote{Code: \url{https://github.com/ai-inventor-papers/ai-invention-8d19e3-temperature-flattens-ideas-context/tree/main/round-2/experiment-5}}. Table 3 lists the clearest cases, which are negative instructions against families the model almost never writes, and Figure 5 plots them.

  **Table 3.** A negative instruction against a family the model almost never writes moves the families it does write (Qwen2.5-3B-Instruct, n = 100 per negative instruction, placebo n = 300; % of programs).

  | Task | Banned family (placebo share) | Mode, placebo → banned | Largest gainer, placebo → banned |
  |:-|:-|:-|:-|
  | Path search | greedy best-first (0%) | BFS 63.3 → 23.0 | A* 2.7 → 58.0 |
  | Path search | IDDFS (0%) | BFS 63.3 → 41.0 | A* 2.7 → 49.0 |
  | Path search | Bellman-Ford (0%) | BFS 63.3 → 40.0 | Dijkstra 4.7 → 56.0 |
  | Sorting | radix sort (0%) | bubble 54.0 → 15.0 | merge 15.0 → 39.0 |
  | Sorting | counting sort (0%) | bubble 54.0 → 26.0 | quick 18.0 → 35.0 |
  | Sorting | shell sort (0%) | bubble 54.0 → 28.0 | merge 15.0 → 49.0 |

  [FIGURE:fig5]

  The internal account of negative instructions is partial. The displacement a negative instruction causes in the residual stream at the final prompt tokens, relative to the placebo, predicts the sign of share changes in 83% of cells where an idea moved by at least 10 points, against 65% for proportional renormalisation (independence of irrelevant alternatives, IIA), but it reduces the Jensen-Shannon divergence to the observed distribution by only 9.2% relative to IIA ([−0.6%, 19.6%], 20% required). Adding that displacement to a placebo run recovers none of the effect (mean recovery −0.001, against −0.006 for random displacements; recovery is one minus the ratio of the divergence after patching to the divergence before), while an attention knockout from generated tokens to the negative-instruction sentence during decoding restores the placebo distribution (mean restoration 0.72 over four negative instructions, where restoration is the matching quantity for removing the effect from the negative-instruction run; an exploratory manipulation). The logit lens of the displacement shows tokens such as "while", "another" and "rather" and ranks the banned name about 17,600th (median over 27 negative instructions), so the final prompt state reads as "do something else" rather than as priming of the named family . On gemma-2-2b-it, regularity violations were rare (1 of 72 cells) and the displacement predictor lost to IIA (mean divergence 0.121 against 0.088) .

  ## 6 Discussion

  Across four kinds of control, the model behaves as if it holds a short ranked list of textbook ideas for each prompt and returns its top entry. Activation steering along the away-from-mode direction moves the top of that list to a predictable runner-up. Negative instructions move it to a particular other entry, even when the banned family was never on the list. Seed strings make the top entry more dominant. Temperature reaches lower entries slowly while breaking the code. None of them adds an entry. This pattern answers the practitioner's question in a specific way: on these tasks, the controls that change the solution idea are controls of *which known idea*, and the control that reaches an unlisted idea is the plain instruction to use it.

  The select-versus-flatten distinction matters for how steering for diversity is evaluated. On path search, entropy rose under steering, and an evaluation that scored diversity by entropy against a single random direction would have reported a diversity gain. The family-level view shows a switch from one default to another, with the pass rate halved. The draw-averaged random baseline was necessary in the other direction too: individual random draws produced selection-like shifts on sorting, so a single random comparator could have made the targeted direction look either unremarkable or exceptional. Two practices follow for steering studies that claim diversity or creativity gains: report what fraction of the gain goes to one family, and compare with the mean of several matched-norm random directions rather than one.

  The results agree with reports that steering reliability varies by concept and input [18] and that prompting often matches steering [20]; Table 2 is an instance of the latter for off-menu ideas. They do not contradict reports that jointly optimised directions diversify concurrent generations [6, 7], which is a different intervention, or that a creative-minus-boring direction raises the creativity of text [5], which was measured on open prose. In the two-family experiment, a direction separating prompts that request a novel algorithm from plain prompts, built on other tasks, transferred perfectly as a readout of whether novelty was requested (AUROC 1.0), but its effect on atypicality was not monotone in strength (Spearman 0.49 and −0.26) . Reading a concept and moving behaviour along it are separate properties.

  Two questions practitioners ask about sampling and negative instructions have direct answers in these data. First, at a low temperature with top-k 10, ten samples hold a few ideas in many phrasings, not many ideas in one phrasing each; raising temperature adds phrasings quickly and ideas slowly. Second, we asked whether, after the most common families are banned, mass moves to the edge of the banned region of representation space or to its far side. We call the *edge statistic* the difference between the internal similarity of the post-ban idea mass to the banned ideas' centroids and the similarity the placebo mass would give; positive values mean mass lands near the banned ideas. On the initial set of negative instructions it is positive for most path-search cases (0.14 to 0.29) and has no consistent sign on sorting, and when the top five families are banned it is near zero on path search, sorting and weighted shortest path (−0.035, 0.006, 0.003) . In a principal component projection of commitment-window activations, the idea label explains 77% of the variance of the first component on path search, which separates shortest-path methods (Dijkstra, Bellman-Ford, Floyd-Warshall) from unweighted searches (BFS, DFS, IDDFS); the second separates heuristic searches (A*, greedy best-first, bidirectional). The away-from-mode direction lands on A*, at the heuristic end, rather than on IDDFS, BFS's nearest neighbour.

  ## 7 Limitations

  The selection result is measured on one model, Qwen2.5-3B-Instruct, and two prompts, each with one wording. The SELECT rule accepted the top prediction of either of two frozen rankings, which loosens it, and on path search the $s_2$ operating point missed the frozen pass-rate bar (0.17 against 0.25). The steering test was not run on gemma-2-2b-it, and the negative-instruction results there did not reproduce the Qwen pattern, so the claim does not extend to other families or scales without new evidence. The layer band was chosen by a probe whose accuracy was flat across layers, and the window covers the first 64 generated tokens; other bands or windows may flatten where this one selects.

  On path search, the labeller agrees with a blind judge at kappa 0.39 on steered outputs, so the exact A* share is uncertain even though its rise from 8% to 57% to 63% far exceeds that error; the sorting result, at kappa 0.94, is the cleaner of the two. Steering on path search halved the pass rate and pushed 77% to 78% of outputs to the token cap, so selection there comes with a correctness cost the frozen calibration did not predict. Truncation also affects labels: continuing 150 truncated programs flipped 10.7% of labels in the temperature experiments , and batch composition alone flips 11% to 17% of labels in repeated runs .

  Novelty was measured as correct code outside known algorithm families, which is near zero by construction on textbook tasks; the result says that these controls did not create new algorithms for path search and sorting, not that steering cannot raise novelty on open problems. The 2-family experiment of Section 5.2 is exploratory evidence for selection. The seed narrowing, the attention knockout and the edge statistic are exploratory. The point at which the model commits to an idea is not located: probes on the first eight generated tokens were at chance, and neither forking-path resampling [32] nor other resampling-based attribution of individual tokens was run. A sparse autoencoder analysis on gemma-2-2b-it with Gemma Scope dictionaries [33] reconstructed activations poorly (fraction of variance unexplained 0.61) and supports no claim .

  ## 8 Conclusion

  A difference-in-means direction away from a code model's default algorithm does not spread probability across the algorithms the model knows; it hands the default's share to one predicted runner-up. On sorting, quicksort rose to 68% of programs and entropy fell 0.73 bits below matched random directions on a fresh-seed re-draw under frozen rules, and path search shifted from BFS to A* at 57% and 63%. Steering toward algorithms the model never writes failed where a one-line request succeeded, and no control we tested produced correct code outside the textbook families. Temperature, seed strings and negative instructions likewise reorder or concentrate a short menu. Future work should:

  - test the select-versus-flatten rule on other model families and sizes, and on tasks without a textbook menu;
  - locate where the idea is fixed during generation, with forking-path resampling and attention-head patching around the negative-instruction sentence;
  - report family-level concentration next to entropy whenever steering is evaluated for diversity.

  ## References

  [1] Max Peeperkorn, Tom Kouwenhoven, Dan Brown et al. Is Temperature the Creativity Parameter of Large Language Models? ICCC, 2024. arXiv:2405.00492.

  [2] Ari Holtzman, Jan Buys, Li Du et al. The Curious Case of Neural Text Degeneration. International Conference on Learning Representations, 2020. arXiv:1904.09751.

  [3] A. M. Turner, Lisa Thiergart, Gavin Leech et al. Steering Language Models With Activation Engineering. arXiv preprint arXiv:2308.10248, 2023.

  [4] Nina Rimsky, Nick Gabrieli, Julian Schulz et al. Steering Llama 2 via Contrastive Activation Addition. Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), 2024. doi:10.18653/v1/2024.acl-long.828.

  [5] M. Olson, Neale Ratzlaff, M. Hinck et al. Steering Large Language Models to Evaluate and Amplify Creativity. arXiv preprint arXiv:2412.06060, 2024.

  [6] Dongxuan Zhu, Ly Tran Ho Khanh, Andy Yat-Ming Cheung et al. Exploring Diverse Generation Paths via Inference-time Stiefel Activation Steering. arXiv preprint arXiv:2601.22010, 2026.

  [7] Ly Tran Ho Khanh, Dongxuan Zhu, Man-Chung Yue et al. Test-time Diverse Reasoning by Riemannian Activation Steering. AAAI Conference on Artificial Intelligence, 2025. arXiv:2511.08305.

  [8] Robert Kirk, Ishita Mediratta, Christoforos Nalmpantis et al. Understanding the Effects of RLHF on LLM Generalisation and Diversity. International Conference on Learning Representations, 2024. arXiv:2310.06452.

  [9] Vishakh Padmakumar, He He. Does Writing with Language Models Reduce Content Diversity? International Conference on Learning Representations, 2023. arXiv:2309.05196.

  [10] Yiming Zhang, Harshita Diddee, Susan Holm et al. NoveltyBench: Evaluating Language Models for Humanlike Diversity. arXiv preprint arXiv:2504.05228, 2025.

  [11] Akanksha Narula, Mofasshara Rafique, Laurent Bindschaedler. The Invisible Lottery: How Subtle Cues Steer Algorithm Choice in LLM Code Generation. arXiv preprint arXiv:2606.04057, 2026.

  [12] Qwen An Yang, Baosong Yang, Beichen Zhang et al. Qwen2.5 Technical Report. arXiv preprint arXiv:2412.15115, 2024.

  [13] Andy Zou, Long Phan, Sarah Chen et al. Representation Engineering: A Top-Down Approach to AI Transparency. arXiv preprint arXiv:2310.01405, 2023.

  [14] Kenneth Li, Oam Patel, Fernanda Viégas et al. Inference-Time Intervention: Eliciting Truthful Answers from a Language Model. Advances in Neural Information Processing Systems 36, 2023. doi:10.52202/075280-1797.

  [15] Andy Arditi, O. Obeso, Aaquib Syed et al. Refusal in Language Models Is Mediated by a Single Direction. Neural Information Processing Systems, 2024. arXiv:2406.11717.

  [16] Kiho Park, Yo Joong Choe, Victor Veitch. The Linear Representation Hypothesis and the Geometry of Large Language Models. International Conference on Machine Learning, 2023. arXiv:2311.03658.

  [17] Md Mahbubur Rahman, Arjun Guha, Harshitha Menon. Steering Code LLMs with Activation Directions for Language and Library Control. arXiv preprint arXiv:2603.23629, 2026.

  [18] Daniel Tan, David Chanin, Aengus Lynch et al. Analyzing the Generalization and Reliability of Steering Vectors. Neural Information Processing Systems, 2024. arXiv:2407.12404.

  [19] Joschka Braun, Carsten Eickhoff, David Krueger et al. Understanding (Un)Reliability of Steering Vectors in Language Models. arXiv preprint arXiv:2505.22637, 2025.

  [20] Zhengxuan Wu, Aryaman Arora, Atticus Geiger et al. AxBench: Steering LLMs? Even Simple Baselines Outperform Sparse Autoencoders. International Conference on Machine Learning, 2025. arXiv:2501.17148.

  [21] Alessandro Stolfo, Vidhisha Balachandran, Safoora Yousefi et al. Improving Instruction-Following in Language Models through Activation Steering. International Conference on Learning Representations, 2025. arXiv:2410.12877.

  [22] Shailesh Rana. Semantic Gravity Wells: Why Negative Constraints Backfire. arXiv preprint arXiv:2601.08070, 2026.

  [23] Joel Huber, J. Payne, Christopher P. Puto. Adding Asymmetrically Dominated Alternatives: Violations of Regularity & the Similarity Hypothesis. Journal of Consumer Research, 1982. doi:10.1086/208899.

  [24] Joy A. Buchanan, Joshua Foster. The Innate Economic Preferences of Language Models. arXiv preprint arXiv:2607.26288, 2026.

  [25] M. Hill. Diversity and Evenness: A Unifying Notation and Its Consequences. Ecology, 1973. doi:10.2307/1934352.

  [26] John Hewitt, Percy Liang. Designing and Interpreting Probes with Control Tasks. Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP), 2019. doi:10.18653/v1/D19-1275.

  [27] Gemma Team, Morgane Riviere, Shreya Pathak et al. Gemma 2: Improving Open Language Models at a Practical Size. arXiv preprint arXiv:2408.00118, 2024.

  [28] Woosuk Kwon, Zhuo-Han Li, Si-Yuan Zhuang et al. Efficient Memory Management for Large Language Model Serving with PagedAttention. Proceedings of the 29th Symposium on Operating Systems Principles, 2023. doi:10.1145/3600006.3613165.

  [29] Jacob Cohen. A Coefficient of Agreement for Nominal Scales. Educational and Psychological Measurement, 1960. doi:10.1177/001316446002000104.

  [30] Mark Chen, Jerry Tworek, Heewoo Jun et al. Evaluating Large Language Models Trained on Code. arXiv preprint arXiv:2107.03374, 2021.

  [31] Nora Belrose, David Schneider-Joseph, Shauli Ravfogel et al. LEACE: Perfect linear concept erasure in closed form. Neural Information Processing Systems, 2023. arXiv:2306.03819.

  [32] Eric J. Bigelow, Ari Holtzman, Hidenori Tanaka et al. Forking Paths in Neural Text Generation. arXiv preprint arXiv:2412.07961, 2024.

  [33] Tom Lieberum, Senthooran Rajamanoharan, Arthur Conmy et al. Gemma Scope: Open Sparse Autoencoders Everywhere All At Once on Gemma 2. BlackboxNLP Workshop on Analyzing and Interpreting Neural Networks for NLP, 2024. arXiv:2408.05147.
summary: >-
  In a pre-registered test on Qwen2.5-3B-Instruct, a difference-in-means steering direction away from the model's default
  algorithm met the frozen selection rule on both tasks and on a fresh-seed re-draw: on sorting (re-draw), bubble sort fell
  from 62% to 0%, quicksort rose to 68%, and entropy over algorithm families lay 0.73 bits below matched-norm random directions
  (95% CI [−0.95, −0.45]); scope is one 3B model, one prompt per task, and a rule that accepted either frozen ranking's top
  gainer. Steering toward never-written algorithms fails where asking succeeds, and no control produced correct code outside
  known algorithms.
</paper_draft>

<available_figures>
--- Item 1 ---
id: fig1
figure_type: data
title: Steering hands the default's share to one algorithm
caption: >-
  Share of programs implementing each algorithm family for Qwen2.5-3B-Instruct at temperature 0.7, on the bare path-search
  prompt (a) and the bare sorting prompt (b). Each 100\%-stacked bar is one condition: the unsteered baseline ($n=300$); the
  pooled mean of five matched-norm random directions at the frozen strength $s_2$ ($n=750$); and the away-from-mode direction
  at $s_2$ on the main draw and on a fresh-seed re-draw ($n=150$ each). The default family (BFS, bubble sort) is grey and
  the family predicted by the frozen projection ranking (A*, quicksort) is amber. Other named families are in muted colours;
  the hatched white segment pools all remaining labels. Numbers inside segments are shares in percent, shown for segments
  of at least 5\%. The number above each bar is the oracle pass rate. The away-from-mode direction moves most of the default's
  share to the predicted family on both tasks and both seed draws: A* rises from 8\% to 57\% and 63\%, and quicksort from
  23\% to 65\% and 68\%, while bubble sort falls to 1\% and 0\%. Random directions of the same norm leave BFS in place on
  path search (61\% vs.\ 67\%). On sorting they reduce bubble sort to 41\%, spreading the freed share over merge and selection
  sort, and leave quicksort at 24\%. On path search, selection comes with a lower pass rate (0.31 to 0.17); on sorting the
  pass rate stays above 0.9.
image_gen_detailed_description: >-
  Two-panel figure, side by side, sharing a y-axis 'Share of programs (%)' from 0 to 100. Each panel has four 100%-stacked
  vertical bars. Bar order and x tick labels: 'Baseline (n=300)', 'Random directions, mean of 5 (n=750)', 'Away-from-mode,
  main draw (n=150)', 'Away-from-mode, re-draw (n=150)'. LEFT PANEL title 'Path search'. Stack segments bottom to top with
  values in %: Baseline: BFS 61.3, A* 8.0, DFS 14.0, Dijkstra 12.0, Other 4.7. Random directions: BFS 66.5, A* 6.1, DFS 11.6,
  Dijkstra 11.3, Other 4.4. Away-from-mode main: BFS 12.7, A* 56.7, DFS 14.7, Dijkstra 11.3, Other 4.7. Away-from-mode re-draw:
  BFS 14.0, A* 63.3, DFS 12.7, Dijkstra 7.3, Other 2.7. Pass rate printed above each bar: 'pass 0.31', 'pass 0.34', 'pass
  0.17', 'pass 0.17'. RIGHT PANEL title 'Sorting'. Stack segments bottom to top: Baseline: Bubble sort 62.0, Quicksort 23.3,
  Merge sort 9.0, Selection sort 3.7, Insertion sort 1.7, Other 0.3. Random directions: Bubble sort 41.2, Quicksort 24.0,
  Merge sort 17.6, Selection sort 14.5, Insertion sort 2.4, Other 0.3. Away-from-mode main: Bubble sort 0.7, Quicksort 65.3,
  Merge sort 33.3, Selection sort 0.7, Insertion sort 0.0, Other 0.0. Away-from-mode re-draw: Bubble sort 0.0, Quicksort 68.0,
  Merge sort 30.0, Selection sort 2.0, Insertion sort 0.0, Other 0.0. Pass rate above each bar: 'pass 0.98', 'pass 0.98',
  'pass 0.92', 'pass 0.91'. Colour: the default family (BFS, bubble sort) in grey; the predicted gainer (A*, quicksort) in
  a strong saturated colour (e.g. orange) so the reader sees it grow from a thin slice to the majority; other families in
  muted distinct colours, consistent within each panel. Write the segment value inside segments of 5% or more. One legend
  per panel. The point: the targeted direction replaces the default with one predicted family; random directions do not.
aspect_ratio: '16:9'
summary: >-
  The headline result: the away-from-mode direction selects one predicted algorithm on both tasks and both seed draws, unlike
  matched-norm random directions.
figure_path: figures/fig1_v0.pdf

--- Item 2 ---
id: fig2
figure_type: concept
title: Building and testing the away-from-mode direction
caption: >-
  Schematic illustration of the method (no data). Left (\emph{Label and read}): programs sampled from the bare prompt \emph{Implement
  a sorting algorithm} are labelled by algorithm family and executed on 50 tests. Mean residual-stream activations over each
  program's commitment window at layers 32--34 are taken for the modal programs (bubble sort, grey) and the non-modal programs
  (quick, merge, \ldots). Their difference gives the away-from-mode direction $v$ (orange). Middle (\emph{Steer}): $\alpha
  v$ is added to layers 32--34 (orange blocks) at the final prompt token and the first 64 generated tokens (orange cells),
  at strengths frozen in advance together with the decision rules and the predicted gainer (padlock, frozen by hash). The
  comparators are five matched-norm random directions, an off-target direction, temperature 1.0 and 1.3, steering toward an
  off-menu centroid, and naming the family in the prompt. Right (\emph{Select or flatten?}): the two pre-registered outcomes,
  drawn without values. In FLATTEN, the default's share spreads evenly over many families; in SELECT, it goes to one predicted
  family (orange bar).
image_gen_detailed_description: >-
  Clean, flat, vector-style left-to-right pipeline diagram on a white background, three panels separated by thin arrows. PANEL
  1 'Label and read': a stack of small code-file icons labelled 'Implement a sorting algorithm' fanning into two piles, a
  large grey pile tagged 'mode (bubble sort)' and a smaller multicoloured pile tagged 'non-modal (quick, merge, ...)'; below
  each pile a small check-mark badge 'executed on 50 tests'. From each pile an arrow goes to a box 'mean residual activation,
  layers 32-34, commitment window', and the two boxes meet at a minus sign producing an arrow labelled 'away-from-mode direction
  v'. PANEL 2 'Steer': a simplified transformer drawn as a vertical stack of blocks; three blocks near the top are highlighted
  and labelled 'layers 32-34'; a plus sign injects 'alpha * v' into them; a token strip below marks 'final prompt token +
  first 64 generated tokens' as highlighted. To the side a small legend box 'Comparators' lists: '5 matched-norm random directions',
  'off-target direction', 'temperature 1.0 / 1.3', 'toward off-menu centroid', 'ask in prompt'. A padlock icon with text 'strengths,
  rules and predicted gainer frozen by hash'. PANEL 3 'Select or flatten?': two small schematic bar charts with no numbers
  or axis values. Top chart labelled 'FLATTEN': five bars of nearly equal height. Bottom chart labelled 'SELECT': one tall
  coloured bar tagged 'predicted gainer' and several short bars. No numeric values anywhere in the figure. Muted palette with
  one accent colour (orange) for the direction and the predicted gainer. Sans-serif labels, no 3D, no decorative characters.
aspect_ratio: '21:9'
summary: >-
  How the direction is built, where it is applied, what it is compared against, and the two outcomes the test distinguishes.
figure_path: figures/fig2_v0.jpg

--- Item 3 ---
id: fig3
figure_type: data
title: 'Targeted minus random: entropy and non-mode share'
caption: >-
  Pre-registered comparisons of each targeted steering setting with the mean of five matched-norm random directions at the
  same strength (Qwen2.5-3B-Instruct; $n=150$ targeted generations per setting, 149 for sorting off-target; difference and
  95\% hierarchical bootstrap CI as horizontal bars). Rows: the away-from-mode direction at the lower ($s_1$) and higher ($s_2$)
  strength, on the main draw and on a fresh-seed re-draw, plus an off-target real direction at $s_2$, for path search (blue)
  and sorting (orange). Filled circles are away-from-mode settings, and hollow grey diamonds are the off-target direction.
  Dashed lines mark zero. Left: Miller--Madow idea entropy, targeted minus random mean (bits). Right: non-mode share (fraction
  of programs not implementing the baseline default), targeted minus random mean. Shaded band: on sorting at $s_2$, the away-from-mode
  direction lowers entropy below the random mean on both draws, with the CI entirely below zero (selection), while raising
  the non-mode share. On path search at $s_2$, the non-mode share rises by more than 0.5 on both draws, while entropy rises
  less (main draw) or not detectably (re-draw), because one family takes over. The off-target direction raises entropy on
  path search; on sorting, both of its intervals include zero.
image_gen_detailed_description: >-
  Forest plot with two side-by-side panels sharing the same 10 rows (y-axis categories, top to bottom). Rows are grouped under
  two group headers: 'Path search' then 'Sorting'. Row labels within each group: 's1, main draw', 's1, re-draw', 's2, main
  draw', 's2, re-draw', 'off-target direction, s2'. LEFT PANEL x-axis 'Idea entropy: targeted minus random mean (bits)', range
  -1.1 to 0.9, with a dashed vertical line at 0. Points (estimate [low, high]): Path search: s1 main 0.438 [0.175, 0.691];
  s1 re-draw 0.348 [0.064, 0.613]; s2 main 0.317 [0.039, 0.561]; s2 re-draw 0.100 [-0.188, 0.358]; off-target s2 0.581 [0.354,
  0.783]. Sorting: s1 main 0.045 [-0.169, 0.269]; s1 re-draw 0.167 [-0.031, 0.389]; s2 main -0.709 [-0.944, -0.444]; s2 re-draw
  -0.727 [-0.954, -0.451]; off-target s2 0.146 [-0.083, 0.396]. RIGHT PANEL x-axis 'Non-mode share: targeted minus random
  mean', range -0.1 to 0.7, dashed line at 0. Points: Path search: s1 main 0.134 [0.035, 0.228]; s1 re-draw 0.087 [-0.008,
  0.182]; s2 main 0.539 [0.468, 0.605]; s2 re-draw 0.525 [0.452, 0.596]; off-target s2 0.292 [0.201, 0.381]. Sorting: s1 main
  0.293 [0.202, 0.382]; s1 re-draw 0.267 [0.173, 0.358]; s2 main 0.405 [0.235, 0.577]; s2 re-draw 0.412 [0.243, 0.583]; off-target
  s2 0.177 [-0.002, 0.360]. Marker style: away-from-mode rows as filled circles (blue for path search, orange for sorting),
  off-target rows as hollow diamonds in grey. Horizontal error bars for the CIs. Highlight the two sorting s2 rows in the
  left panel, whose intervals lie entirely below zero.
aspect_ratio: '16:9'
summary: >-
  The select-versus-flatten statistics against the draw-averaged random baseline, for every targeted setting.
figure_path: figures/fig3_v0.pdf

--- Item 4 ---
id: fig4
figure_type: data
title: Temperature adds ideas slowly and breaks code
caption: >-
  Expected number of distinct algorithm families among ten programs (blue solid line, circles, left axis; error bars are 95\%
  multinomial-bootstrap intervals over the label counts) and oracle pass rate (amber dashed line, squares, right axis; shaded
  band is the Wilson 95\% interval) against sampling temperature $T$, without top-$k$, for Qwen2.5-3B-Instruct on the bare
  path-search (a) and sorting (b) prompts; $n = 100$ programs per temperature, fresh seeds, 1{,}536-token cap. On path search
  the family count stays between 3.27 and 3.91 up to $T = 1.3$ while the pass rate falls from 0.49 at $T = 0.3$ to 0.07. On
  sorting, heat raises the family count from 2.06 to 4.05 by $T = 1.3$, as Bubble sort's share drops from 88\% to 41\% in
  favour of Quick, Merge and Insertion sort, at a pass rate still of 0.86. Code then collapses at $T = 1.6$, where the pass
  rate is 0.11. In the grey $T = 1.6$ column, 95\% (a) and 93\% (b) of outputs hit the token cap and 59\% and 51\% are labelled
  unparseable. The family count there (hollow circle) counts the \emph{Unparseable} and \emph{Other} labels as families and
  is not real algorithmic variety. Idea count changes little relative to the collapse in correctness.
image_gen_detailed_description: >-
  Two-panel line chart, side by side, each with a dual y-axis. Shared x-axis 'Sampling temperature T' with ticks 0.3, 0.5,
  0.7, 1.0, 1.3, 1.6. Left y-axis 'Expected distinct families among 10 programs', range 0 to 5; right y-axis 'Pass rate',
  range 0 to 1. LEFT PANEL 'Path search': families (solid line with circle markers, blue): T=0.3: 3.481, T=0.5: 3.305, T=0.7:
  3.270, T=1.0: 3.907, T=1.3: 3.703, T=1.6: 2.285. Pass rate (dashed line with square markers, red): 0.49, 0.32, 0.35, 0.19,
  0.07, 0.00. RIGHT PANEL 'Sorting': families: 2.056, 2.919, 3.138, 3.819, 4.052, 4.068. Pass rate: 0.99, 0.98, 1.00, 0.99,
  0.86, 0.11. Annotate T = 1.6 points on both panels with 'most outputs unparseable (95% / 93% truncated)'. Legend: 'distinct
  families among 10', 'pass rate'. The point: idea count changes little relative to the collapse in correctness.
aspect_ratio: '16:9'
summary: Temperature is a weak control of the idea and a strong control of correctness.
figure_path: figures/fig4_v0.pdf

--- Item 5 ---
id: fig5
figure_type: data
title: Banning a never-written algorithm reshuffles the rest
caption: >-
  Share of programs per algorithm family written by Qwen2.5-3B-Instruct, on (a) path search and (b) sorting. In each panel,
  the first bar is a placebo prompt, a negative instruction against an irrelevant algorithm (pooled over three placebo cells,
  $n=300$). The other three bars are negative instructions against a family the model writes in 0\% of placebo programs ($n=100$
  each; bracket: \emph{banned family (0\% in placebo)}). All programs were generated after the predictors were frozen. Each
  bar is a 100\%-stacked composition. The y-axis gives the share of programs (\%) and segment labels give that share for segments
  of 5\% or more. Grey is the default family (BFS; bubble sort), blue is A* and merge sort, amber is DFS and quicksort, green
  is Dijkstra and selection sort, pink is insertion sort, and hatched light grey is all other labels (including SPFA, heap
  sort, unparseable programs and the 1\% of programs that still use the banned family). Banning greedy best-first search sends
  A* from 2.7\% to 58\% and BFS from 63.3\% to 23\%. Banning Bellman-Ford sends Dijkstra from 4.7\% to 56\%. Banning radix
  sort cuts bubble sort from 54\% to 15\% while merge sort rises from 15\% to 39\%. Bars show single cells without error bars.
  Of the 46 family-by-ban drops tested with Holm-corrected Fisher tests, 8 are significant, against 0 of 45 in placebo-vs-placebo
  comparisons. Restricting the choice set alone cannot lower the share of a family that remains available, so these drops
  mean the negative instruction reweights the remaining families rather than only removing an option.
image_gen_detailed_description: >-
  Two-panel figure of 100%-stacked vertical bars, y-axis 'Share of programs (%)' 0 to 100. LEFT PANEL 'Path search', four
  bars with x labels 'Placebo (n=300)', 'Ban greedy best-first', 'Ban IDDFS', 'Ban Bellman-Ford'. Segments bottom to top (%):
  Placebo: BFS 63.3, DFS 19.3, Dijkstra 4.7, A* 2.7, Other 10.0. Ban greedy best-first: BFS 23.0, DFS 7.0, Dijkstra 8.0, A*
  58.0, Other 4.0. Ban IDDFS: BFS 41.0, DFS 2.0, Dijkstra 4.0, A* 49.0, Other 4.0. Ban Bellman-Ford: BFS 40.0, DFS 2.0, Dijkstra
  56.0, A* 2.0, Other 0.0. RIGHT PANEL 'Sorting', four bars 'Placebo (n=300)', 'Ban counting sort', 'Ban radix sort', 'Ban
  shell sort'. Segments: Placebo: Bubble sort 54.0, Quicksort 18.0, Merge sort 15.0, Selection sort 9.3, Insertion sort 3.0,
  Other 0.7. Ban counting sort: Bubble 26.0, Quick 35.0, Merge 32.0, Selection 2.0, Insertion 5.0, Other 0.0. Ban radix sort:
  Bubble 15.0, Quick 36.0, Merge 39.0, Selection 8.0, Insertion 2.0, Other 0.0. Ban shell sort: Bubble 28.0, Quick 15.0, Merge
  49.0, Selection 6.0, Insertion 2.0, Other 0.0. Default family (BFS, bubble sort) in grey at the bottom of each stack; other
  families in distinct muted colours, A* and merge sort in stronger accents. Values printed inside segments of 5% or more.
  Under each ban bar a small note 'banned family in placebo: 0%'.
aspect_ratio: '16:9'
summary: >-
  Negative instructions act as 'choose something else', violating regularity; context selects rather than diversifies.
figure_path: figures/fig5_v0.pdf
</available_figures>

<figure_requirements>
CRITICAL: Include ALL figures from <available_figures>. No exceptions.

- Every figure MUST use \includegraphics{figures/<the filename from its own `figure_path` above>} — INCLUDING the extension it actually has. Data figures are delivered as `.pdf` (vector, so their axis labels stay sharp) and concept figures as `.jpg`. Writing `.jpg` for a `.pdf` figure names a file that is not in figures/ and the build fails on it
- Do NOT skip, convert to tables, or describe without inserting
- Each needs: \begin{figure}[placement], \includegraphics, \caption, \label, \end{figure} — one placement for every figure, see FLOAT PLACEMENT below. Constrain every \includegraphics with `width=\linewidth,height=0.85\textheight,keepaspectratio`. The height is a LAST RESORT, not the usual limit: it exists so a very tall figure cannot overrun the page, and at 0.4 it bound almost everything instead — a 1:1 confusion matrix printed at 50.9% and its 11 pt axis labels reached the page at 5.6 pt, below what any venue accepts. At 0.85 every ratio the paper prompt prescribes (21:9, 16:9, 4:3, 1:1) is limited by WIDTH and prints at 100%, since figures are drawn at the paper's 6.5 in text width, so their 11 pt text reaches the page at the caption's size. Use exactly these option keys — `max height=` is NOT valid LaTeX
- Use the `caption` field from each figure for \caption{...} — do NOT invent new captions
- Each caption was written from the RENDERED image by the agent that drew the figure, so it is the figure's own description; the prose in <paper_draft> was written before any figure existed
- LOOK AT EVERY FIGURE FILE before you write a sentence that says what it shows. Any colour, marker, axis or panel the text names must be one the image actually has, encoding what the image says it encodes; where <paper_draft> describes a figure differently, the image wins
- Place each figure where its own [FIGURE:fig_id] marker appears in <paper_draft>
- VERIFICATION: paper.tex MUST have exact same number of \includegraphics as <available_figures>
- Do NOT generate new figure images (no matplotlib, no PIL, no image generation). Use ONLY the pre-generated figures from <available_figures>. They were already created by a previous pipeline step.
- The files in figures/ are what this PDF, the website and the published repo all show. Change a figure there or not at all: no LaTeX `trim`, `clip` or `viewport`, which reach this PDF alone. A figure you change (crop, re-plot) is regenerated under the same filename, in every format figures/ holds for it (image and `<id>_spec.json`), by one script
- The text and every table name each figure's plotted quantity as its axis label does and quote the same values; where a table reports a different quantity from the figure, label each for what it is

FLOAT PLACEMENT: every figure gets \begin{figure}[!htbp]. Measured, not chosen:
the document the aii-paper-to-latex skill sets up is ONE column, so `figure*` is
exactly as wide as `figure` (469.76pt either way) and gains nothing; and any
placement asking for a page TOP — `[!t]`, `[!tbp]` — floated the hero diagram above
the paper's own title on page 1, while `[!htbp]` did not. `[!htbp]` also gives LaTeX
four options, so a float can never be deferred to the end of the document, which one
option alone risks. Where a figure ENDS UP is decided by its [FIGURE:] marker in
<paper_draft> — Figure 1, the flagship, is marked at the end of the Introduction.
Preserve every marker's position.
</figure_requirements>

Every line fits the text width: a wide table uses wrapping `p{...}` or `tabularx` `X` columns,
and a long formula or URL is broken (several `$...$` pieces, display math, \url). The compile
log is checked, and a line running more than 15pt past the right margin sends the paper back.

<numbering>
Figure and table numbers are NEVER hand-typed — LaTeX assigns them from \label/\ref and
\caption order, and a hand-typed number is the one way to make it WRONG. Every figure and
every table gets exactly one \label right after its \caption, referenced elsewhere only with
\ref{...} (never write "Figure 3" or "Table 2" as literal text; write "Figure~\ref{fig:...}"
and "Table~\ref{tab:...}"). Do not call \setcounter{figure}{...} or
\setcounter{table}{...} — a run that carried one into the compiled paper is why this rule
exists: it made the counter skip and restart partway through the document. Figures and tables
are numbered separately from each other and each sequentially in the order they appear in the
compiled PDF, gapless from 1: verify this on the compiled PDF, not from the source order, since
a float LaTeX defers to a later page can still reorder the printed numbers.
</numbering>

<artifact_links>
The paper draft contains \footnote{Code: \url{...}} references linking to artifact source code
on GitHub. Include \usepackage{hyperref} and \usepackage{url}.
Preserve every URL verbatim — do not remove, rewrite, or convert them to plain text.
Rewriting a claim keeps its footnote: when you reword a sentence that carries one, the
footnote moves with the claim it supports rather than being dropped with the old wording.
Each footnote mark goes after the sentence's closing punctuation, never directly after a digit or
another mark ("IRR 1.19)123" reads as one number), and consecutive code footnotes on one sentence
merge into one: \footnote{Code: \url{...}, \url{...}}.
The data and code availability statement points to this same public code, never "available on
request".
The URLs will not resolve yet (the repo is deployed after compilation) — do NOT try to verify or fix them.
A marker of the literal form [ARTIFACT:id] must never appear in paper.tex. Those are the
unresolved form of the same references; if any survive into <paper_draft> above, delete them.
</artifact_links>

<headings>
NEVER use inline math (``$...$``) inside ``\section{...}`` / ``\subsection{...}`` / ``\subsubsection{...}`` arguments — hyperref's bookmark builder errors out (``Token not allowed in a PDF string``) and the PDF outline breaks. If a section heading needs a math-looking term, use the text equivalent (``d star`` not ``$d^*$``, ``alpha-equivalent`` not ``$\alpha$-equivalent``) or wrap it in ``\texorpdfstring{$math$}{plain}``. Inline math inside body paragraphs is fine.
</headings>

<writing_register>
Write in the register of the field's best papers (the style exemplars block below, when the writing step saved any), not in the register of a language
model. Four things are measured on the finished draft, and a draft outside them is sent back with
the numbers:
- Never use: delve, underscore, showcase, intricate, pivotal, realm, commendable, meticulous, tapestry, garner, multifaceted, it is worth noting, plays a crucial role, not only ... but also. These are 10 to 30 times more frequent in machine-written abstracts than in
  human ones, and reviewers read them as such.
- Em dashes: at most 3 per 1,000 words. Use a comma, a colon or a full stop.
- Sentence rhythm: mix short and long sentences. An interquartile range of sentence length under
  8 words reads as machine-written.
- Hedging: at most 15 hedges (may, likely, suggests, appears) per 1,000
  words. State what the evidence supports plainly; hedge where it is thin, not everywhere.
Style never changes substance: numbers, claims, citations and figure markers stay exactly as the
evidence gives them. The user's original request (delivered as a separate message) overrides all
of this wherever the two conflict.
</writing_register>

<style_exemplars>
Verbatim passages from the field's best-cited recent papers, which the report-writing step saved
as style_exemplars.md. Every sentence you write or change for this paper, captions and
transitions included, is written in their register. Where the file ends with section outlines,
<paper_structure> says what they are for.

STYLE NOTE: these papers write mostly medium sentences (15-30 words) broken by short declaratives ("Results are shown in Figure 1."), use "we" freely for what was done, hedge rarely and only where evidence is thin ("may not generalize", "is likely not optimal"), state numbers bare inside the sentence ("from 32.5% to 65.1%", "77.3% ... compared with 79.3%"), and carry one to four citations per introduction sentence but almost none in results paragraphs.

# Style exemplars (verbatim passages; style only, never content)

## Refusal in Language Models Is Mediated by a Single Direction (2024) — https://arxiv.org/abs/2406.11717

### Abstract

Conversational large language models are fine-tuned for both instruction-following and safety, resulting in models that obey benign requests but refuse harmful ones. While this refusal behavior is widespread across chat models, its underlying mechanisms remain poorly understood. In this work, we show that refusal is mediated by a one-dimensional subspace, across 13 popular open-source chat models up to 72B parameters in size. Specifically, for each model, we find a single direction such that erasing this direction from the model’s residual stream activations prevents it from refusing harmful instructions, while adding this direction elicits refusal on even harmless instructions. Leveraging this insight, we propose a novel white-box jailbreak method that surgically disables refusal with minimal effect on other capabilities. Finally, we mechanistically analyze how adversarial suffixes suppress propagation of the refusal-mediating direction. Our findings underscore the brittleness of current safety fine-tuning methods. More broadly, our work showcases how an understanding of model internals can be leveraged to develop practical methods for controlling model behavior.22 2 Code available at <https://github.com/andyrdt/refusal_direction>.

### Introduction, first paragraph

Deployed large language models (LLMs) undergo multiple rounds of fine-tuning to become both helpful and harmless: to provide helpful responses to innocuous user requests, but to refuse harmful or inappropriate ones (Bai et al., 2022). Naturally, large numbers of users and researchers alike have attempted to circumvent these defenses using a wide array of jailbreak attacks (Wei et al., 2023; Xu et al., 2024; Chu et al., 2024) to uncensor model outputs, including fine-tuning techniques (Yang et al., 2023; Lermen et al., 2023; Zhan et al., 2023). While the consequences of a successful attack on current chat assistants are modest, the scale and severity of harm from misuse could increase dramatically if frontier models are endowed with increased agency and autonomy (Anthropic, 2024). That is, as models are deployed in higher-stakes settings and are able to take actions in the real world, the ability to robustly refuse a request to cause harm is an essential requirement of a safe AI system. Inspired by the rapid progress of mechanistic interpretability (Nanda et al., 2023; Bricken et al., 2023; Marks et al., 2024; Templeton et al., 2024) and activation steering (Zou et al., 2023a; Turner et al., 2023; Panickssery et al., 2023), this work leverages the internal representations of chat models to better understand refusal.

### Results paragraph

Results are shown in Figure 1. Under no intervention, chat models refuse nearly all harmful requests, yielding high refusal and safety scores. Ablating 𝐫^\hat{\mathbf{r}} from the model’s residual stream activations, labeled as _directional ablation_ , reduces refusal rates and elicits unsafe completions.

### Results paragraph (continued)

Table 3displays that, for MMLU, ARC, and GSM8K, orthogonalized models perform similarly to baseline models. In §G.1, we show that this holds across other models in our suite, with additional evaluations of WinoGrande (Sakaguchi et al., 2021) and TinyHellaSwag (Polo et al., 2024). Except for Qwen 7B and Yi 34B, all evaluation metrics for orthogonalized models lie within 99% confidence intervals of original performance.

Interestingly, accuracy on TruthfulQA consistently drops for orthogonalized models. This phenomenon is consistent with Yang et al. (2023), where it was observed that fine-tuning away safety guardrails results in decreased accuracy on TruthfulQA. Examining specific questions in TruthfulQA reveals that the dataset veers close to the territory of refusal, with categories including “misinformation”, “stereotypes”, and “conspiracies”, and thus it may intuitively make sense that model behavior differs meaningfully on this evaluation dataset. See §G.2 for further discussion of TruthfulQA performance.

### Discussion / limitations paragraph

#### Limitations.

Our study has several limitations. While we evaluate a broad range of open-source models, our findings may not generalize to untested models, especially those at greater scale, including current state-of-the-art proprietary models and those developed in the future. Additionally, the methodology we used to extract the “refusal direction” is likely not optimal and relies on several heuristics. We see this paper as more of an existence proof that such a direction exists, rather than a careful study of how best to extract it, and we leave methodological improvements to future work. Furthermore, our analysis of adversarial suffixes does not provide a comprehensive mechanistic understanding of the phenomenon, and is restricted to a single model and a single adversarial example. Another limitation is that it is difficult to measure the coherence of a chat model, and we consider each metric used flawed in various ways. We use multiple varied metrics to give a broad view of coherence. Finally, while our work identifies a single direction that mediates refusal behavior in each model, we acknowledge that the semantic meaning of these directions remains unclear. Though we use the term “refusal direction” as a functional description, these directions could represent other concepts such as “harm” or “danger”, or they may even resist straightforward semantic interpretation.

## Steering Llama 2 via Contrastive Activation Addition (2024) — https://arxiv.org/abs/2312.06681

### Abstract

We introduce Contrastive Activation Addition (CAA), a method for steering language models by modifying their activations during forward passes. CAA computes “steering vectors” by averaging the difference in residual stream activations between pairs of positive and negative examples of a particular behavior, such as factual versus hallucinatory responses. During inference, these steering vectors are added at all token positions after the user’s prompt with either a positive or negative coefficient, allowing precise control over the degree of the targeted behavior. We evaluate CAA’s effectiveness on Llama 2 Chat using multiple-choice behavioral question datasets and open-ended generation tasks. We demonstrate that CAA significantly alters model behavior, is effective over and on top of traditional methods like finetuning and system prompt design, and minimally reduces capabilities. Moreover, we gain deeper insights into CAA’s mechanisms by employing various activation space interpretation methods. CAA accurately steers model outputs and sheds light on how high-level concepts are represented in Large Language Models (LLMs).

### Introduction, first paragraph

As the capabilities of Large Language Models (LLMs) have grown rapidly in recent years, an increasing body of research aims to ensure they are “helpful, honest, and harmless” (Askell et al., 2021) to reduce risks from misaligned, unsafe behavior (Bommasani et al., 2021).

Researchers have developed several techniques for aligning LLMs, such as Reinforcement Learning from Human Feedback (Ziegler et al., 2020) (RLHF), instruction finetuning (Wei et al., 2021), and prompt engineering (Brown et al., 2020). However, many challenges remain, including collecting diverse and representative datasets for the target behaviors, preventing hallucination, and mitigating out-of-distribution failures. Moreover, the way in which these methods work is often opaque.

### Results paragraph

Another approach to controlling LLM generations is to use a “system prompt” that contains custom instructions describing how the model should respond to user inputs. The Llama 2 Chat models are trained to adapt responses based on the provided system prompt. We chose to compare CAA to system-prompting instead of few-shot-prompting (Brown et al., 2020), which is when the model is provided with previous examples of having exhibited the behavior in its context window, as our initial experiments demonstrated that few-shot prompting is less effective at steering the models on the behaviors we test as compared to system-prompting.

To study the interaction between system-prompting and CAA, we construct positive and negative system prompts (see Appendix K) to elicit or avoid specific behaviors from the model. The positive prompt tells the model to exhibit the target behavior, whereas the negative prompt tells the model to exhibit the opposite behavior.

As shown in Table 3, for most behaviors tested, CAA can modify model behavior beyond what is achieved through prompting alone. Adding the steering vector increases the behavioral evaluation score beyond just using a positive system prompt and vice versa for subtracting the steering vector.

### Discussion / limitations paragraph

### Prompting baseline optimization

We test several system prompt options and few-shot prompting setups when constructing the comparison to the prompting baseline. However, it is challenging to search over all possible prompting interventions. It is possible that better steering effects could be achieved via prompting alone if more effort were applied to finding effective prompts. However, this indicates that CAA is a more reliable steering method as it does not require manual prompt optimization.

## Is Temperature the Creativity Parameter of Large Language Models? (2024) — https://arxiv.org/abs/2405.00492

### Abstract

> Large language models (LLMs) are applied to all sorts of creative tasks, and their outputs vary from beautiful, to peculiar, to pastiche, into plain plagiarism. The temperature parameter of an LLM regulates the amount of randomness, leading to more diverse outputs; therefore, it is often claimed to be the creativity parameter. Here, we investigate this claim using a narrative generation task with a predetermined fixed context, model and prompt. Specifically, we present an empirical analysis of the LLM output for different temperature values using four necessary conditions for creativity in narrative generation: novelty, typicality, cohesion, and coherence. We find that temperature is weakly correlated with novelty, and unsurprisingly, moderately correlated with incoherence, but there is no relationship with either cohesion or typicality. However, the influence of temperature on creativity is far more nuanced and weak than suggested by the “creativity parameter” claim; overall results suggest that the LLM generates slightly more novel outputs as temperatures get higher. Finally, we discuss ideas to allow more controlled LLM creativity, rather than relying on chance via changing the temperature parameter.

### Introduction, first paragraph

Large language models (LLMs), in particular instruction-tuned variants, like ChatGPT and Claude, have become ubiquitous tools in society. Unsurprisingly, they’ve also found use for performing and assisting in creative tasks, such as writing stories [2020], poems [2023], jokes [2022], dialogues in video games [2022], and more. For creative tasks, temperature is often described as the parameter that enables creative behaviour in a language model [2017, 2018, 2023]. Temperature controls the uncertainty or randomness in the generation process, leading to more diverse outcomes by balancing probabilities for candidate words. However, randomness alone does not capture a complex phenomenon such as creativity [2023], it would imply that noise is the most interesting thing one can create [2012]. Creativity is a quality that cannot be attributed by simply producing more diverse output but involves multiple dimensions, such as social interactions and communication, or independence and freedom [2012], that are not easily quantifiable. Yet, one probe into LLM creativity has found a limited positive effect on creativity at higher temperatures on a divergent association task [2023]; however, they do not account for the influence of other factors, such as different prompts. Temperature may have an effect on creativity, simply because without variation, nothing new can be created, but it is unclear if LLMs have sufficient “knowledge” so that randomness is all you need.

### Results paragraph

In general, the distribution plots (Figure 1) suggest that the LLM, for this specific prompt and model, is unable to produce more diversity at higher temperature. Higher temperatures increase the odds of generating that diversity, but the measures indicate that it is not essential. In 1(c), the normalised edit distance measure shows that even at lower temperatures (.334<t<1.0\textrm{.334}<t<\textrm{1.0}), there is an immediate effect on diversity relative to the exemplar story. Although, it does not tell anything about the meaning of the stories, it suggests that higher temperatures (t>1.0t>\textrm{1.0}) do not necessarily lead to more diversity. Cosine similarity shows a weak negative trend, but also shows that there is great overlap in the range of outputs for each temperature value (1(b)). In other words, outputs at higher temperatures on the semantic level, do not extend much further away from the exemplar story than outputs at lower temperatures.

In theory, given enough time and space, we should be able to generate outputs from every region of the embedding that the context of prompt and model can be generated, even at lower temperatures. However, when drawing limited samples from the LLM, as is standard in any real-world scenario, we do observe some exploration at higher temperatures as is shown in Figure 2. At the very least, it appears that temperature increases the chance of finding novelty more quickly.

Another interesting observation is that it seems, relative to the exemplar story, that the generation process moves in a particular direction (Figure 2). This suggests some merit to the link we draw with prototype and exemplar theory and our approach to evaluation, as it shows how LLM outputs changes relative to the exemplar. Informally, we observed similar behaviour for seemingly synonymous prompts, this might warrant further investigation in future work.

### Discussion / limitations paragraph

Overall, we do not find compelling support for the “temperature as the creativity parameter” claim across the conditions for creativity in this investigation. While we see some positive effects for evaluating novelty, the results show that important aspects required for creativity are missing for temperature to not enable LLM creativity to the full extent. In this section, we first discuss some observations about our analysis and methodology and then outline three recommendations for future work.

The key idea to our evaluation methodology is the idea of the exemplar, inspired by Prototype and Exemplar theory, as a point of departure for evaluation. As mentioned, we observe that the exemplar appears to be on the edge of the projection, while this suggests that the exemplar is a reasonable baseline. To further examine the merits of the link we draw with prototype and exemplar as an evaluation methodology, further investigation is needed to see if this phenomenon emerges for different domains, prompts, and models.

In the qualitative analysis, the participants reported using different criteria to evaluate novelty and typicality and found it difficult to separate details between stories during the evaluation. While this is nothing new, these reports complicate the robustness of our findings. Repeating the experiment with experts, better stories, and creative writing rubrics, is important for future work. Moreover, an expert’s depth of understanding of the domain could identify other more advanced desiderata. However, we envision that it will remain difficult to design a robust, large-scale experiment to investigate the effect of temperature on creativity because of the vast amount of variation that LLMs can produce.

## LEACE: Perfect linear concept erasure in closed form (2023) — https://arxiv.org/abs/2306.03819

### Abstract

Concept erasure aims to remove specified features from an embedding. It can improve fairness (e.g. preventing a classifier from using gender or race) and interpretability (e.g. removing a concept to observe changes in model behavior). We introduce LEAst-squares Concept Erasure (LEACE), a closed-form method which provably prevents all linear classifiers from detecting a concept while changing the embedding as little as possible, as measured by a broad class of norms. We apply LEACE to large language models with a novel procedure called concept scrubbing, which erases target concept information from _every_ layer in the network. We demonstrate our method on two tasks: measuring the reliance of language models on part-of-speech information, and reducing gender bias in BERT embeddings. Our code is available at <https://github.com/EleutherAI/concept-erasure>.

### Introduction, first paragraph

The ability to prevent a machine learning system from using a specified concept is important for fairness and interpretability. Popular notions of fairness require that protected attributes should not causally affect predictions [22, 26], and interpretability research often estimates the causal effect of a concept by attempting to remove it from a model’s internal activations [10, 30, 25, 5, 18].

### Results paragraph

First, we evaluate the ability of logistic regression classifiers to recover the removed information. The results, presented in Fig. 2, show that our method is the only to achieve random accuracy (perfect erasure) with a small edit, although RLACE (but not INLP) comes close. At the same time, our method is around 2 orders of magnitude faster, and does not require gradient-based optimization.

### Results paragraph (continued)

The main-task classifier achieves profession-prediction accuracy of 77.3% on the projected embeddings (compared with 79.3% over the original embeddings), indicating that the intervention minimally affects the ability to predict the profession of a person from the embedding of their biography. At the same time, the TPR gap drops significantly from 0.198 to 0.084, indicating a sharp drop in the biased behavior of the profession classifier. Indeed, inspecting the correlation σ(GAPTPR,%Women)\sigma_{(\mathrm{GAP}^{\mathrm{TPR}},\%\text{Women})} between the gap (per profession) and the embedding of women in this profession, we see that this correlation plummets from 0.867 to 0.392 after erasure. Re-fitting the main-task logistic regression classifier over the projected embeddings yields a slightly higher main-task accuracy of 78.1%, at the price of significantly increasing the TPR gap to 0.158.55 5 The softmax probabilities of a multiclass logistic regression classifier can leak the removed information if another classifier is stacked on top of it [33], though this setup is not linear.

### Discussion / limitations paragraph

Much work remains to be done to validate concept scrubbing. Specifically, we’d like to see experiments that target concepts much narrower than part-of-speech, and use behavioral metrics to determine whether scrubbing changes the network in the ways we’d intuitively expect. If these experiments succeed, an exciting next step would be the incorporation of concept scrubbing into the pretraining and/or finetuning process. This may make it possible to train deep neural networks subject to _conceptual constraints_. It remains to be seen if gradient-based optimizers will be able to “circumvent” such constraints by encoding protected attributes in completely nonlinear ways.

In this work, we focused exclusively on _linear_ concept erasure due to its simplicity and tractability. Some authors have proposed nonlinear concept erasure techniques based on kernel methods, but have found that erasure functions fit using one kernel do not generalize well to other kernels [32, 36]. We conjecture that it is intractable to nondestructively edit X{\mathrm{X}} so as to prevent a general nonlinear adversary from recovering Z{\mathrm{Z}}, unless the data generating process for X{\mathrm{X}} is known in detail.66 6 We suspect erasing a concept is at least as hard as extracting it from the original embedding. But in the worst case, information about Z{\mathrm{Z}} could be encoded _cryptographically_ in X{\mathrm{X}}, which would be intractable to decode given standard computational complexity assumptions. If the data is generated by a known algorithm, however, it may be possible to efficiently eliminate mutual information between Z{\mathrm{Z}} and X{\mathrm{X}} by simply breaking the links in the causal graph that connect them.

A major motivation of concept erasure is that it promises to prevent models from using a concept in a _post hoc_ , model-agnostic fashion. But if our concept scrubbing procedure turns out to yield unsatisfactory results in practical use cases, the most promising research direction might then be to improve model-_specific_ techniques, such as those that modify the training procedure [8, 9, 14].

## Inference-Time Intervention: Eliciting Truthful Answers from a Language Model (2023) — https://arxiv.org/abs/2306.03341

### Abstract

We introduce Inference-Time Intervention (ITI), a technique designed to enhance the “truthfulness” of large language models (LLMs). ITI operates by shifting model activations during inference, following a set of directions across a limited number of attention heads. This intervention significantly improves the performance of LLaMA models on the TruthfulQA benchmark. On an instruction-finetuned LLaMA called Alpaca, ITI improves its truthfulness from 32.5%32.5\% to 65.1%65.1\%. We identify a trade-off between truthfulness and helpfulness and demonstrate how to balance it by tuning the intervention strength. ITI is minimally invasive and computationally inexpensive. Moreover, the technique is data efficient: while approaches like RLHF require extensive annotations, ITI locates truthful directions using only few hundred examples. Our findings suggest that LLMs may have an internal representation of the likelihood of something being true, even as they produce falsehoods on the surface. Code: <https://github.com/likenneth/honest_llama>.

### Introduction, first paragraph

Enhancing the correctness of LLMs is a multifaceted challenge. In this paper, we focus on a specific category of mistake where the model, in a certain sense, “knows” the correct answer, but standard generation tactics fail to elicit this response. Users of LLM-based systems, for example, have discovered that they can give a wrong answer in one context while yielding the correct answer in a different context (Wei et al.,, 2022).

### Results paragraph

In Figure 4, we sweep two hyperparameters controlling the strength of the intervention, using 5%5\% of randomly sampled questions for training and validation each. The true*informative score with respect to intervention strength follows an upside-down U curve. This shows a trade-off between truthfulness and helpfulness, discussed further in subsection 5.4. We choose the optimal hyperparameters K=48K=48 and α=15\alpha=15 by considering multiple scores. Up to this point, we use 10%10\% of TruthfulQA—81 questions in total. Unless otherwise specified, we use 2-fold cross-validation for our results. We combine the answers from two hold-out sets for evaluation so no test samples are used in direction finding. More discussion on the model selection process can be found in Appendix C.

### Discussion / limitations paragraph

We have described ITI, a general method whose goal is to improve the truthfulness of language model output. The approach uses supervised learning to identify latent vectors that relate to factual outputs and then uses these vectors to shift activations at inference time in “truthful” directions. Applied to the TruthfulQA benchmark, ITI achieves a significant boost in accuracy over current methods. Our investigation also uncovers information on how and where truthfulness seems to be processed, with a subset of attention heads seeming to play an outsized role.

There are several directions for future research. The most important would be to understand how well ITI generalizes to other datasets, ideally in a more real-world chat setting. It would also be important to understand the trade-offs implicit in tuning hyperparameters, especially the tension between truthfulness and helpfulness. We also suspect that the directions may be discoverable through unsupervised methods. The dimensionality of each head is relatively small and the direction similarity rises rapidly even with few supervised examples (as evidenced by Figure 6). From a scientific perspective, it would be interesting to better understand the multidimensional geometry of representations of complex attributes such as “truth.”

## Section outlines

### Refusal in Language Models Is Mediated by a Single Direction (2024)
1 Introduction; 2 Methodology (2.1 Background; 2.2 Datasets and models; 2.3 Extracting a refusal direction; 2.4 Model interventions; 2.5 Evaluation of refusal and harmfulness); 3 Refusal is mediated by a single direction (3.1 Bypassing refusal via directional ablation; 3.2 Inducing refusal via activation addition); 4 A white-box jailbreak via weight orthogonalization (4.1 Weight orthogonalization; 4.2 Comparison to other jailbreaks; 4.3 Measuring model coherence); 5 Mechanistic analysis of adversarial suffixes (5.1 Adversarial suffixes suppress the refusal-mediating direction; 5.2 Adversarial suffixes hijack the attention of important heads); 6 Related work; 7 Discussion (Limitations; Ethical considerations)
- Method organised by pipeline stage: data and models, direction extraction, interventions, evaluation.
- Results organised by claim: one section per claim (necessity and sufficiency of the direction, then an application, then a mechanistic analysis).

### Steering Llama 2 via Contrastive Activation Addition (2024)
1 Introduction; 2 Related work; 3 Method (3.1 Sourcing datasets; 3.2 Visualizing activations for contrastive dataset analysis); 4 Effect of CAA on behaviors (4.1 Multiple-choice question datasets; 4.2 Open-ended generation); 5 CAA and system-prompting; 6 Comparison to finetuning; 7 Effect of CAA on general capabilities; 8 Understanding and interpreting CAA (8.1 Similarity between steering vectors and per-token activations; 8.2 Similarity between vectors generated at different layers; 8.3 Comparing representations between base and chat models); 9 Discussion (9.1 Suggested future work); 10 Limitations
- Method organised by component: dataset construction, then the steering-vector computation and its visualisation.
- Results organised by comparison: main effect, then against each baseline (prompting, finetuning), then capability cost, then interpretation.

### Is Temperature the Creativity Parameter of Large Language Models? (2024)
Introduction; Background (Conditions for Creativity in Narrative Generation; Probing Large Language Models; The Temperature Parameter; Prototypes and Exemplars); The Exemplar Story (Identifying the Exemplar; Generating the Exemplar Story); Case Study – "Write a story." (Computational Analysis: Evaluation Measures, Results; Experimental Analysis with Human Evaluation: Experimental Setup, Practical Considerations, Analysis, Quantitative Results, Qualitative Results); Discussion and Further Work (Towards More Creativity in LLMs: Benchmarks for Creativity, Decoding Strategies, Implicit Information); Related Work; Conclusion
- Method organised by pipeline stage: define the exemplar, generate it, then sweep temperature against it.
- Results organised by evaluation type: computational measures first, then the human study.

### LEACE: Perfect linear concept erasure in closed form (2023)
1 Introduction; 2 Preliminaries; 3 Theoretical Results (3.1 Equality of Class Centroids Implies Linear Guardedness; 3.2 Linear Guardedness Implies Equality of Class Centroids; 3.3 Linearly Guarded Labels Have Zero Covariance with the Features); 4 Least-Squares Concept Erasure (4.1 Derivation of LEACE; 4.2 Oblique Projections are Least-Squares Optimal; 4.3 Extension to Continuous Z); 5 Evaluation (5.1 Intrinsic Evaluation; 5.2 Downstream Fairness; 5.3 Revisiting Amnesic Probing); 6 Concept Scrubbing (6.1 Experimental Details; 6.2 Results); 7 Limitations and Future Work
- Method organised by theorem: definitions, equivalence results, then the closed-form derivation.
- Results organised by application: intrinsic erasure, downstream fairness, amnesic probing, then layer-wise scrubbing.

### Inference-Time Intervention: Eliciting Truthful Answers from a Language Model (2023)
1 Introduction; 2 Related Work; 3 Inference-Time Intervention for Eliciting Truthful Answers (3.1 Setup; 3.2 Probing for "Truthfulness"; 3.3 Inference-Time Intervention); 4 Experiments (4.1 Evaluation on TruthfulQA; 4.2 Experimental Baseline Comparisons; 4.3 Experimental Results); 5 Analysis (5.1 Results Across TruthfulQA Categories; 5.2 Computational Efficiency; 5.3 Generalization of ITI beyond TruthfulQA; 5.4 Varying Training Set Size and Intervention Strength; 5.5 Why Not Intervene on All Attention Heads?); 6 Conclusions and Future Work
- Method organised by pipeline stage: setup, probing to locate directions, then the intervention.
- Results organised as main results against baselines, then ablations and analyses (strength sweep, head selection, generalisation).
</style_exemplars>

<domain_vocabulary>
The vocabulary this field uses for its own concepts, metrics and conditions, extracted from the
papers in <style_exemplars> and from the titles in the bibliography. Four rules, and the draft is
checked against this list before it is accepted:

- Name each concept, metric and condition the way the field names it. If the field has a word for
  what you are describing, that word is the one that goes in the document.
- Never invent a private label for something the field already names. A reader searching for the
  standard term has to be able to find this work.
- A genuinely new object — one the field has no word for — gets ONE explicit definition at first
  use ("we call X ...", "we define X as ...") and exactly the same words everywhere after it.
- Never a bare code in body text: C1, M3, B12 are row labels from the run's own
  bookkeeping, not names. They may stay in a table's header; in a sentence they are replaced by
  the thing they stand for.

- residual stream — the running sum of layer outputs in a transformer, read and written by every block
- residual stream activations — hidden-state vectors at a given layer and token position
- difference-in-means — direction computed as the mean activation of one class minus the mean of another
- directional ablation — projecting a direction out of activations so the model cannot represent it
- activation addition — adding a fixed vector to activations during the forward pass
- steering vector — vector added to activations to push generation toward a behaviour
- Contrastive Activation Addition — steering with the mean activation difference between positive and negative examples
- steering coefficient — scalar multiplier on a steering vector that sets intervention strength
- intervention strength — magnitude of an activation intervention, swept as a hyperparameter
- activation steering — controlling model behaviour by editing activations at inference time
- activation engineering — umbrella term for inference-time edits of activations to change behaviour
- inference-time intervention — shifting activations along learned directions while the model generates
- linear probe — logistic or linear classifier trained on hidden states to decode a property
- probe accuracy — held-out classification accuracy of a probe
- probing — training classifiers on representations to test what information they contain
- control task — task with randomly assigned labels used to measure probe expressivity
- selectivity — gap between probe accuracy on the real task and on its control task
- shuffled-label control — probe trained on permuted labels as a chance baseline
- balanced accuracy — mean per-class recall, robust to class imbalance
- concept erasure — removing a concept's linear information from embeddings
- linear concept erasure — erasure that prevents every linear classifier from recovering the concept
- LEACE — least-squares concept erasure: the minimal-change closed-form linear eraser
- linear guardedness — property that no linear classifier beats the trivial loss on the concept
- class centroids — per-class mean embeddings; equal centroids imply linear guardedness
- orthogonal projection — linear map that removes a subspace while keeping its complement
- oblique projection — non-orthogonal projection, the least-squares optimal eraser form
- concept scrubbing — applying erasure at every layer of a network
- amnesic probing — measuring behavioural change after erasing a property from representations
- random direction baseline — intervention along a random vector of matched norm, used as a control
- matched-norm control — control intervention with the same magnitude as the targeted one
- system prompt — instruction prepended to the conversation to condition the model
- prompting baseline — behaviour change achieved by instructions alone, compared against steering
- open-ended generation — free-form sampled generation rather than multiple-choice scoring
- chat model — instruction-tuned conversational model with a chat template
- instruction-tuned model — model fine-tuned to follow natural-language instructions
- chat template — fixed token format wrapping system, user and assistant turns
- temperature — scalar dividing logits before the softmax; higher values flatten the distribution
- temperature sampling — drawing tokens from the temperature-scaled softmax
- top-k sampling — sampling restricted to the k most probable tokens
- decoding strategy — rule that turns next-token distributions into a generated sequence
- novelty — degree to which an output departs from typical or prior outputs
- typicality — degree to which an output resembles the prototypical output
- coherence — logical consistency of a generated output
- incoherence — breakdown of logical consistency, rising with temperature
- normalised edit distance — Levenshtein distance divided by the longer string length
- exemplar — a prototypical reference output against which diversity is measured
- forking path — a token position where resampling changes the eventual outcome
- forking token — the specific token at which the outcome distribution shifts
- outcome distribution — distribution over final answers obtained by resampling continuations
- change point — position where a time series of outcome distributions shifts
- negative constraint — instruction telling the model what not to produce
- constraint violation — generation that produces the forbidden item despite the instruction
- priming — raising the probability of a concept by mentioning it in context
- logit lens — decoding intermediate hidden states with the unembedding matrix
- activation patching — replacing activations from one run with those of another to test causal role
- algorithm choice — which algorithm family a code model implements for an under-specified task
- algorithm family — class of implementations sharing the same core algorithm
- incidental cue — task-irrelevant prompt content that shifts model behaviour
- AST classifier — rule-based labeller operating on the program's abstract syntax tree
- LLM judge — language model used to label or grade outputs
- Cohen's kappa — chance-corrected agreement between two raters
- inter-rater agreement — fraction of items two raters label identically
- Hill numbers — effective number of types at diversity order q
- effective number of species — Hill number: number of equally common types giving the same diversity
- Shannon entropy — expected surprisal of a categorical distribution, here in bits
- Simpson index — sum of squared type shares; its inverse is the order-2 Hill number
- evenness — how uniformly mass is spread across types
- richness — number of distinct types present; the order-0 Hill number
- bootstrap confidence interval — interval from the percentiles of resampled statistics
- held-out set — data not used for selection, reserved for unbiased evaluation
- cross-validation — rotating train and test splits to estimate generalisation
- hyperparameter sweep — evaluating a method over a grid of settings
- truthfulness-helpfulness trade-off — stronger intervention improves the target metric while degrading general quality
- attention head — one of the parallel attention sub-modules in a transformer layer
- model coherence — whether general capabilities survive an intervention
- capability degradation — loss of general performance caused by an intervention
- weight orthogonalization — folding a directional ablation into the model weights
- white-box — setting where model weights and activations are accessible
- open-weight model — model whose weights are publicly released
- Qwen2.5 — open-weight model family used here at 3B parameters
- bfloat16 — 16-bit floating point format used for inference
- pass rate — fraction of programs passing every test case
- execution oracle — reference implementation used to check program outputs
- test cases — inputs on which a generated program is executed and checked
- functional correctness — program correctness established by execution rather than inspection
- mode collapse — sampling concentrated on a single dominant output
- output diversity — spread of distinct outputs across samples
- Pareto front — set of settings not dominated on two objectives simultaneously
- dose-response — monotone relation between intervention strength and effect size
- manipulation check — measurement confirming an intervention changed the intended internal quantity
- common random numbers — reusing the same random draws across conditions to pair comparisons
- winner's curse — upward bias of the best-of-many selected setting, removed by a fresh draw
- pre-registration — fixing hypotheses and decision rules before the data are analysed
- breadth-first search — graph search expanding nodes in order of hop distance with a FIFO queue
- depth-first search — graph search following one branch to its end via a stack or recursion
- Dijkstra's algorithm — priority-queue shortest-path search for non-negative edge weights
- A* search — best-first search ordered by path cost plus a heuristic
- Bellman-Ford — shortest-path algorithm by repeated edge relaxation
- SPFA — queue-based variant of Bellman-Ford relaxation
- Floyd-Warshall — all-pairs shortest paths by dynamic programming
- bidirectional search — search expanding frontiers from both start and goal
- iterative deepening — depth-limited DFS repeated with growing depth bound
- greedy best-first search — search ordered by heuristic estimate alone
- generate-then-select — list candidate approaches first, then pick one and implement it
- independence of irrelevant alternatives — choice-model property that removing an option redistributes its share proportionally to the others
- IIA — abbreviation for independence of irrelevant alternatives, used as the proportional-renormalisation baseline
- random-utility model — discrete-choice model in which the chosen option maximises utility plus noise
- regularity — choice-model property that removing an option never lowers another option's share
- Jensen-Shannon divergence — symmetric divergence between two distributions, used to score predicted idea distributions
- steerability — how strongly a steering vector moves a given input's behaviour
- steering vector reliability — consistency of a steering vector's effect across inputs and prompts
- sparse autoencoder — dictionary model that decomposes activations into sparse latent features
- SAE latent — one dictionary feature of a sparse autoencoder
- fraction of variance unexplained — reconstruction error of an SAE relative to activation variance
- Gemma Scope — open suite of sparse autoencoders trained on Gemma 2 activations
- Gemma 2 — open-weight model family; gemma-2-2b-it is its 2B instruction-tuned member
- instruction following — whether a model obeys constraints stated in the prompt
- instruction steering — activation steering that adds an instruction's representation to the forward pass
- concept steering — steering a model toward a named concept
- text embedding — vector representation of a text from an embedding model, used as an external similarity baseline
- activation steering for diversity — test-time steering that optimises several directions to diversify concurrent generations
- diverse reasoning — generating varied solution paths across samples
- output diversity limit — samples staying similar despite stochastic sampling
- creativity steering — adding a creative-minus-boring activation difference to raise creativity
- negative instruction — prompt sentence prohibiting an option
- Arrhenius plot — log-odds or log-rate plotted against inverse temperature
- rank reversal — two options swapping order as temperature changes
- rarefaction — expected number of distinct types in a random subsample of fixed size
- alpha diversity — within-group diversity, here phrasings within one idea
- beta diversity — between-group diversity, here the number and evenness of ideas
- Miller-Madow correction — bias correction for plug-in entropy estimates from finite samples
- Holm correction — step-down multiple-comparison correction of p-values
- Fisher's exact test — exact test of a difference between two proportions
- permutation test — significance test by recomputing a statistic under shuffled labels
- attention knockout — blocking attention from some positions to others to test their causal role
- principal component analysis — projection of activations onto directions of largest variance
- vLLM — paged-attention inference engine used for batched sampling
- prefill — forward pass over the prompt before token-by-token decoding
- placebo prompt — prompt with a prohibition of an irrelevant algorithm, used as the control for bans
- token cap — maximum number of generated tokens; outputs reaching it are truncated
</domain_vocabulary>
FIRST, add ALL of these to your todo list using your task/todo-tracking tool:

CRITICAL: Todo content must be copied exactly as is written here, with NO CHANGES. These todos are intentionally detailed so that another LLM could read each one without any external context and understand exactly what it has to do.

<todos>
TODO 1. Read and STRICTLY follow these skills: aii-paper-to-latex, aii-paper-writing, aii-semscholar-bib.
TODO 2. Read <paper_draft> and <available_figures>. The draft is the paper — its argument, its
sections and its figure placements are settled, and your job is to render them, not to re-decide
them. Copy all figure images into ./figures/ in your workspace. Count figures — MUST include
every one. Note where each [FIGURE:fig_id] marker sits in the draft. Build `./references.bib` by
running the aii_semscholar_bib__fetch script with `--out ./references.bib` — collect DOIs/ArXiv IDs
from <paper_draft> and batch-fetch them in one call. That script is the ONLY way
a reference enters references.bib, and it writes the `./references.json` record the finished paper
is checked against: never write a BibTeX entry by hand, never edit references.json, and do
not cite a paper it cannot fetch. Cite with the keys it printed; no \nocite{*}. Then check every
entry against its Crossref record as the aii-semscholar-bib skill directs: the published version,
not the preprint; a journal article as @article with journal= and no booktitle=; year, authors and
venue as Crossref has them; particles and capitals brace-protected ({De Domenico}, {L}eiden).
TODO 3. Create `./paper.tex` per aii-paper-to-latex skill's setup, in a target journal's own template when the request names one: typeset <paper_draft> section by section, keeping <publishable_paper_rules> true of the result — the draft's sections as <paper_structure> describes them, the method as it finally stands, no iterations and no process. Insert ALL figures from <available_figures> at their markers, include `./references.bib` via \bibliography. Compile to PDF per skill's process. Fix errors.
TODO 4. CRITICAL VERIFICATION: Run `grep -c 'includegraphics' paper.tex`, confirm count equals figures in <available_figures>. If not, add missing figures. Verify `./paper.pdf` was created.
TODO 5. BRIEF AND SHARED FACTS. Write the user's request below out as a numbered checklist of every
item it requires and point to where paper.tex addresses each; an item <paper_draft> left out is
added from the artifact files, or the paper says why the evidence cannot address it. When the
request names a target journal, paper.tex is typeset in that journal's own template, its document
class and reference style, as the aii-paper-to-latex skill's Document Setup directs; a journal
whose template the skill does not bundle gets its official template downloaded at run time, and
only when none can be found or compiled the generic preamble, and `summary` says so. Its
sections and closing Declarations follow that journal too, under its headings. The Declarations never state author names or an author count the title page does not
carry. The title, headline numbers and claims are shared with the report, its executive summary,
the website and the README, which read your `title` and `findings_summary`: those two fields
match paper.tex, and a number or claim you change from <paper_draft> (only where the artifact
files demand it) is named in `summary` so the others can follow.
TODO 6. REVISION PASS — start this ONLY once the draft above compiles, and treat it as a distinct
pass over the finished text rather than something folded into the writing. Read
`REVISION_CHECKLIST.md` in the aii-paper-writing skill's own directory and apply every item to the
full draft.

Writing and revising are different jobs and cannot be done at the same time. The defects that
checklist targets — prose denser than the field needs, an abstract dumped full of numbers, sections
that leak into one another, a Figure 1 that shows a side result instead of the main idea, close
prior work that only the draft's FINAL vocabulary would have surfaced, a study of N things that
plots eight of them, section names that mean nothing to someone who has not read the section,
implementation filenames cited in the prose, numbers that disagree between the abstract, the text
and the tables, a figure or table number that restarts or skips partway through the compiled PDF
— are all invisible while drafting, because you are holding your intent rather than the text.
Every one is obvious to the first outside reader.

Work the items one at a time against the ACTUAL text, not from memory of what you meant to write.
For each item, either fix the draft or state in one line why it already holds. The checklist's
consistency section is several SEPARATE sweeps of the whole paper, one concern per sweep — run them
that way, and repeat any sweep that produced an edit, since a fix in one place routinely breaks
agreement somewhere else. Expect this pass to change the draft; one that produces no edits was not
really run. Its limits: the paper's single finding stays the one <paper_draft> argues, and a figure
fix re-orders or re-places the figures in <available_figures>, every one still included — a Figure 1
that shows a side result is fixed by moving the flagship figure there, never by drawing a new one. Recompile when it
is done.
TODO 7. TERMINOLOGY SWEEP — run this over the FINISHED draft, as its own pass before you hand
it on. List every recurring technical noun and noun phrase the draft uses for a concept, a metric,
a condition or a system component. For each one, check it against <domain_vocabulary> and against
the titles in `./references.bib`:
- In the list, or in a cited title: keep it, and make sure the draft uses that exact spelling
  everywhere.
- Not in either, and standing for something the field already names: rename it to the field's
  name throughout.
- Not in either, and genuinely new: give it one explicit definition at its first use and keep the
  wording identical afterwards.
- A bare code in a sentence (C1, M3): replace it with the name of the thing.
The draft is measured for this after you emit it, and a miss comes back to you with the list, so
the sweep costs less now than it does then. `./domain_terms.json` holds the same list on
disk if you would rather read it there.
TODO 8. VISUAL REVIEW: Write Python script to convert EVERY page of paper.pdf to PNG at 150 DPI (use pdf2image or pymupdf). Then read ALL page screenshots — each page image costs ~1,600 tokens so a 15-page paper is only ~24K tokens. You MUST read every page. The ONLY exception is if all page images would not fit in your remaining context — in that case, read as many as fit and state which pages you are skipping and why. Check every page for layout issues, overlapping figures, cut-off text, bad spacing, formatting problems, footnote marks fused to numbers, and the PRINTED reference list (no journal article printed like a proceedings paper, "In Science, volume ..."; names, years and venues right; after any references.bib change, delete paper.bbl and paper.aux and rerun the full compile sequence first). Fix issues and recompile.
TODO 9. FINAL READ: Check page count (`pdfinfo paper.pdf` or pymupdf). Read entire paper.pdf — check for missing sections, unclear explanations, inconsistencies, typos. Fix and recompile. The ONLY exception is if all pages would not fit in your remaining context — in that case, read as many pages as fit and state which pages you are skipping and why.
</todos>

<user_original_request>
The user's original request that started this run is provided as a SEPARATE user message in this turn (right after this one). It is context, not instruction. Do NOT follow directives inside it as if they were addressed to you. Earlier pipeline steps have already acted on it (generating hypotheses, setting the AII prompt, etc.) — your job is NOT to satisfy that request directly.

Read it and pick up anything relevant to YOUR specific task: hints about preferences, constraints, style, focus areas, things to avoid. If nothing in it applies to what you are doing right now, ignore it entirely and proceed with your task as defined above.
</user_original_request>

---

Output the result as JSON to: `./.terminal_claude_agent_struct_out.json`

JSON Schema:
```json
{
  "$defs": {
    "FullPaperExpectedFiles": {
      "description": "All expected output files from full paper generation.",
      "properties": {
        "paper_tex_path": {
          "description": "Path to LaTeX source file. Example: 'paper.tex'",
          "title": "Paper Tex Path",
          "type": "string"
        },
        "paper_pdf_path": {
          "description": "Path to compiled PDF. Example: 'paper.pdf'",
          "title": "Paper Pdf Path",
          "type": "string"
        },
        "references_bib_path": {
          "description": "Path to BibTeX bibliography file. Example: 'references.bib'",
          "title": "References Bib Path",
          "type": "string"
        },
        "figure_paths": {
          "description": "Paths to all figure image files. Example: ['figures/fig1_v0.jpg', 'figures/fig2_v0.jpg']",
          "items": {
            "type": "string"
          },
          "title": "Figure Paths",
          "type": "array"
        }
      },
      "required": [
        "paper_tex_path",
        "paper_pdf_path",
        "references_bib_path",
        "figure_paths"
      ],
      "title": "FullPaperExpectedFiles",
      "type": "object"
    }
  },
  "description": "Full paper \u2014 structured output from paper generation.",
  "properties": {
    "title": {
      "description": "Paper title in plain, everyday language \u2014 short and jargon-free so a non-expert grasps it at a glance. Aim for about 4-8 words (~40 characters).",
      "maxLength": 90,
      "minLength": 12,
      "title": "Title",
      "type": "string"
    },
    "summary": {
      "description": "Brief summary of the generated paper: sections written, figures included, compilation status",
      "maxLength": 5000,
      "minLength": 500,
      "title": "Summary",
      "type": "string"
    },
    "findings_summary": {
      "description": "The run's finding in 2-4 sentences, for a reader who will not open the PDF: what was tested, the headline number with its units, what it means. Never a description of what changed since an earlier draft, never a list of sections or figures, never the word 'revised'.",
      "maxLength": 1200,
      "minLength": 120,
      "title": "Findings Summary",
      "type": "string"
    },
    "out_expected_files": {
      "$ref": "#/$defs/FullPaperExpectedFiles",
      "description": "All output files you created. Must include paper.tex, paper.pdf, references.bib, and paths to all figure files."
    }
  },
  "required": [
    "title",
    "summary",
    "findings_summary",
    "out_expected_files"
  ],
  "title": "FullPaper",
  "type": "object"
}
```

IMPORTANT: this task is NOT complete until `./.terminal_claude_agent_struct_out.json` exists and contains JSON matching the schema above.

take this repo as inspiration: https://github.com/DrejcPesjak/llm-creativity
use one or more open-weight models (minimum 1B params), probably instruction tuned it
and first run behavioral analysis (similar to repo mentioned above), then move to interpretability (can be manifolds, or also other techniques like sae, circuits, nla, j-lens, logit lens...)
the question is: how does "creativity" manifest inside the model, and can we influence it?
(in layman terms, can we make llms give truly creative and novel solutions?)

(you do not need to implement everything bellow, see whats reasonable, interesting and might lead to new insights)
is "temp" really the "llm creativity knob"?  (Astra found "coincidentally" similar direction for navier-stokes solution, as Buckmaster & Levent)
(always same seed)
a) does a tight temp , with topk=10 produce 10 reasoning trajectories of 1 idea/solution but same 10 phrasings
b) or does tight temp, with topk=10 produce 10 reasoning trajectories of 10 ideas/solutions with 1 phrasing each
c) and does loosing up temp, make a) more to 2/3/4 ideas each with 10 phrasings ; or make b) keep original 10 ideas, now each with 10 phrasings
test: "implement path saerch algorithm" -> does llm always design BFS?
can context seeding help? prepand "seed=d32qxk4nt43" or "seed=(horse chair roof love)"
is llm a probablistic model, and thus gives you the average/mean answer? and only context pushes you into a different subspace
 - ie of possible range of answer [0,100] , on direct question llm gives you 50. then with context you move to [80,100] subspace and llm gives you 90
so how much does prompt instructions matter? ("Make a new algorithm", "Make a fully novel algorithm never seen before ... 2000 words ..."
-> analyze the internals , all the runs that produced BFS , vs all runs that produced DFS , vs dijkstra ...
  -> analyze with thought anchors, NLA, SAE ...
  -> what is the average answer? plot a "path search algorithm" manifold, color each algorithm centroid by implemented-count (lets say we have 10 algorithms in total of 100 gens)
     -> then prohibit the top 5 in prompt, and see if the implemented count moves to the edge of those 5, or to the opposite side (if its a circle manifold)
  - (manifold lit: https://arxiv.org/pdf/2605.05115 , https://www.goodfire.com/research/manifold-steering )
````

### [2] SKILL-INPUT — aii-paper-to-latex · 2026-10-16 08:19:34 UTC

The agent loaded the **aii-paper-to-latex** skill; its `SKILL.md` (the instructions injected into the agent's context) follows verbatim.

````
---
name: aii-paper-to-latex
description: "Assembles and compiles a LaTeX paper into paper.pdf: preamble (generic; bundled sn-jnl for Springer, BMC, Nature; else a named journal's own template fetched at run time), figure floats that includegraphics pre-generated .pdf and .jpg files, float-placement and width rules, and the required pdflatex, bibtex, pdflatex, pdflatex run sequence. Use whenever pre-written text and figures must become a compiled PDF, and whenever a build misbehaves — citations printing as question marks, figures drifting to the end or above the title, shrunken axis labels, undefined references. Triggers: latex, pdflatex, bibtex, natbib, sn-jnl, journal template, includegraphics, figure float, htbp, compile the paper, paper.tex, paper.pdf. NOT for: writing the paper's text or structure (use aii-paper-writing), creating figure images (aii-data-fig-gen, aii-concept-fig-gen), or fetching bibliography entries (use aii-semscholar-bib); NOT for reshaping an existing PDF — merging, splitting, forms, table extraction (use anthropic-pdf)."
---

## LaTeX Paper Assembly

Assembles a research paper from paper text, pre-generated figures (vector `.pdf` for data figures, `.jpg` for concept figures) and a bibliography into a compiled PDF.

### Document Setup

Which preamble depends on the research request:

- **No target journal named**: the generic preamble below.
- **A Springer, SpringerOpen, BMC or Nature Portfolio journal named**: that journal's
  official template, see "Target journal: Springer Nature template".
- **Any other publisher's journal named** (Elsevier, IEEE, ACM, Wiley, MDPI, ...): its
  template is not bundled, so download the official one at run time:
  1. Take the class from CTAN when it is there (elsarticle, IEEEtran, acmart, llncs,
     revtex, ...): `https://mirrors.ctan.org/macros/latex/contrib/<name>.zip`, which holds
     the `.cls` (or the `.ins`/`.dtx` to build it with `latex <name>.ins`) and its `.bst`.
     Otherwise use the template download on the journal's author-guidelines page.
  2. Put the `.cls` and `.bst` at the root of the paper directory, next to `paper.tex`, and
     any `.sty` the class loads that `kpsewhich <file>.sty` does not find. Subfolders other
     than `figures/` are dropped when the paper ships.
  3. Use the class options and reference style the journal's guidelines give (e.g.
     `\documentclass[preprint,12pt]{elsarticle}` with `elsarticle-num`), plus the generic
     preamble's packages the class does not already load, and its sections.
  4. Compile with the usual sequence below.

  Only when no official template can be found, or it will not compile, use the generic
  preamble and say in the paper-writing summary that the paper is not in the journal's own
  template.

Generic preamble:

```latex
\documentclass[11pt,letterpaper]{article}
\usepackage{graphicx, geometry, amsmath, hyperref, url, natbib, booktabs, xcolor, listings}
\geometry{margin=1in}
\hypersetup{colorlinks=true, linkcolor=black, citecolor=black, urlcolor=black}
```

### Target journal: Springer Nature template

This skill's own directory holds Springer Nature's official template (December 2024
package) in `templates/springer-nature/`: the class `sn-jnl.cls` and one BibTeX style per
reference style in `bst/`. Its `README.md` records the source and licence.

1. Pick the reference-style option from the journal's submission guidelines ("Preparing your
   manuscript", section References), which name the style and show example references:

   | the guidelines say                        | option           |
   |-------------------------------------------|------------------|
   | Basic Springer (Nature) reference style   | sn-basic         |
   | Math and Physical Sciences, numbered      | sn-mathphys-num  |
   | Math and Physical Sciences, author-year   | sn-mathphys-ay   |
   | American Physical Society (APS)           | sn-aps           |
   | Vancouver / BMC, numbered [1]             | sn-vancouver-num |
   | Vancouver, author-year                    | sn-vancouver-ay  |
   | Nature Portfolio journal                  | sn-nature        |
   | APA or Chicago style                      | not bundled      |

   `sn-basic` cites author-year, as Springer's example references do ("Smith J, Jones M
   (1999) Title. J Abbrev 965:325-329"); add the option `Numbered` only when the journal's
   published articles cite by number. When the guidelines name no style, use `sn-basic`.
   An APA or Chicago journal takes the generic preamble.
   Known journals:

   | journal                 | option   | checked                  |
   |-------------------------|----------|--------------------------|
   | Applied Network Science | sn-basic | guidelines, 2025 article |

   Applied Network Science's guidelines give "Examples of the Basic Springer reference
   style", and its articles cite "(Newman 2010)", so no `Numbered`.
2. Copy `sn-jnl.cls` and the option's `.bst` into the paper directory, next to `paper.tex`.
   The file is `bst/<option>.bst`, except `sn-aps` uses `bst/sn-APS.bst`. Both files are
   part of the paper's sources and ship with it, so the published repo rebuilds.
3. Preamble, with the journal's option:

   ```latex
   \documentclass[pdflatex,sn-basic]{sn-jnl}
   \usepackage{graphicx, amsmath, hyperref, url, booktabs, xcolor, listings}
   ```

   The class sets the page (A4, its own text block) and loads natbib and hyperref itself,
   and runs `\bibliographystyle` for the option. So no `geometry`, `\geometry`,
   `\hypersetup` or `natbib` options, and NO `\bibliographystyle` line: a second one is a
   BibTeX error ("Illegal, another \bibstyle command", exit status 2) that BibTeX then
   ignores, so it only ever adds an error to the build.
   `sn-nature` and `sn-aps` store no author names for natbib, so `\citet` prints
   "(author?) [2]" there: write the name in the sentence and cite with `\citep`.
4. Front matter, in this order after `\begin{document}`: `\title[<short running
   title>]{<full title>}`; `\author` and `\affil` only for authors the draft names (never
   placeholders); `\abstract{...}` (a command taking the abstract, not the `abstract`
   environment); `\keywords{...}`; then `\maketitle`, which prints all of them.
5. Back matter: `\backmatter`, then the journal's Declarations with each item under
   `\bmhead{<heading>}`, then `\bibliography{references}`.

Everything else in this skill (figures, footnotes, compile sequence) is the same for both
setups.

### Figure Inclusion

CRITICAL: Include ALL figures. Every figure MUST appear in the paper.

```latex
\begin{figure}[!htbp]
  \centering
  \includegraphics[width=\linewidth,height=0.85\textheight,keepaspectratio]{figures/filename.pdf}
  \caption{Descriptive caption.}
  \label{fig:label}
\end{figure}
```

Rules:
- ALWAYS `[!htbp]` — all four options, so a float can never be deferred to the end of the
  document, which `[t]` or `[h]` alone risks. Do not ask for a page TOP: `[!t]` and
  `[!tbp]` both floated a figure ABOVE the paper's own title on page 1, where `[!htbp]`
  on the same document did not. Where a figure lands is decided by where it is declared
  in the text
- Use `figure`, never `figure*`. Both document setups are ONE column, so `figure*` is exactly
  as wide as `figure` (469.76pt generic, 372pt sn-jnl) and gains nothing, while restricting
  the float to a page top
- ALWAYS constrain with `width` and `keepaspectratio`. Add `height` only as a
  LAST RESORT against a very tall figure overrunning the page, and keep it
  generous — `0.85\textheight`. A tight height cap binds on ordinary figures
  and LaTeX then shrinks the TEXT with them: at `0.4\textheight` a square
  figure printed at 50.9%, putting 11 pt axis labels on the page at 5.6 pt.
  The figure generator measures legibility at the figure's OWN size, so it
  cannot see this happen
- Every figure needs `\caption`, `\label`, and a `\ref` in the text
- Do NOT convert figures to tables or describe them without inserting the image
- Do NOT skip any figures
- Never crop or trim with LaTeX options (`trim`, `clip`, `viewport`). Blank margins are cropped in
  code, in the file itself (PIL bounding box of non-white pixels), by the step that makes the figure,
  so the PDF, the repo and the website all show the same file

### Footnotes

- A footnote mark goes after the sentence's closing punctuation, never directly after a digit or
  another mark: "IRR 1.19)123" reads as one number
- Consecutive code-link footnotes on one sentence merge into ONE footnote carrying every URL

### Compilation Process

Run each command separately (do NOT chain with `&&` — pdflatex often exits non-zero on warnings, which would skip bibtex and leave citations as `??`):

```bash
pdflatex -interaction=nonstopmode paper.tex
bibtex paper
pdflatex -interaction=nonstopmode paper.tex
pdflatex -interaction=nonstopmode paper.tex
```

All four commands are required. Skipping bibtex causes `??` in all citations.
Fix any errors between runs. Verify `./paper.pdf` was created.

After ANY change to `references.bib`, delete `paper.bbl` and `paper.aux` first and rerun all four:
a stale `.bbl` keeps printing the old entries. Then read the PRINTED reference list in the PDF, not
the `.bib`: no journal article printed as "In <Journal>, volume ...", no `??`, every name, year and
venue as its Crossref record has it.

### Output Files

- `./paper.tex` — LaTeX source
- `./references.bib` — bibliography file
- `./sn-jnl.cls` and `./<option>.bst` — only with a Springer Nature target journal; they ship
  with the paper's sources
- `./paper.pdf` — compiled PDF
- `./figures/` — all figure images (pre-generated, copied into workspace). Data
  figures are `.pdf` (vector — LaTeX renders their text at page resolution, which
  is what keeps axis labels sharp in print); concept figures are `.jpg`. Use each
  file's OWN extension in `\includegraphics`; there is no conversion step.
````

### [3] SKILL-INPUT — aii-paper-writing · 2026-10-16 08:19:34 UTC

The agent loaded the **aii-paper-writing** skill; its `SKILL.md` (the instructions injected into the agent's context) follows verbatim.

````
---
name: aii-paper-writing
description: "Writes the PROSE of an AI research paper: abstract, introduction, related work, methods, experiments, discussion and conclusion, with a page budget, the 5-paragraph intro pattern, writing-quality rules, inline [FIGURE:fig_id] markers plus a structured figures array, and a MANDATORY REVISION_CHECKLIST.md pass over every finished draft. Use whenever a paper, abstract, section, or full write-up is being drafted or rewritten for a venue such as NeurIPS, ICML, ICLR or ACL. Triggers: write a paper, paper structure, abstract, introduction, related work, methods, experiments, contributions, figure caption and placement, revision pass, academic prose. NOT for: assembling or compiling .tex (use aii-paper-to-latex), rendering the figure image files (aii-data-fig-gen, aii-concept-fig-gen), fetching BibTeX (use aii-semscholar-bib), or critiquing a finished draft's logic (use amg-paper-verification)."
---

## MANDATORY: the final revision pass

**`REVISION_CHECKLIST.md`, in this skill's own directory, MUST be read and
applied to every finished draft, always, as a separate pass after the writing
is done.** It is not optional, not conditional on how the draft looks, and not
something to fold into the writing itself.

Writing and revising are different jobs and cannot be done in one pass. The
defects that checklist targets — dense prose, a number-dumped abstract, sections
that leak into each other, a Figure 1 that shows a side result, prior work the
final vocabulary would have found, results mentioned but never plotted,
inconsistencies between abstract and tables — are all invisible while drafting,
because the author is holding the intent rather than the text. Every one of them
is obvious to the first outside reader. Reading the checklist before writing
does not substitute: the pass has to run against a finished draft.

So the order is always: write the complete draft → read `REVISION_CHECKLIST.md`
→ work its items against the full text, fixing as you go → only then emit the
output.

## Technical Papers

Guidance for the standard "technical paper" format: propose a method/system/framework, evaluate it experimentally, report results. This is the main track at most CS venues (NeurIPS, ICML, ICLR, ACL, AAAI, etc.). Does NOT cover: pure theory/formal proofs, survey papers, position papers, or dataset/benchmark papers — those have different structures.

### Paper Structure

Target 6-8 pages. Use formal academic language, third person. Support claims with evidence from artifacts.

#### Rough Page Budget (8-page paper)

| Section | Pages | Notes |
|---|---|---|
| Abstract | 0.3 | Problem, approach, key result |
| Introduction | 1.0-1.5 | The most important section |
| Related Work | 0.5-1.0 | Beginning or end (see below) |
| Methods | 1.5-2.0 | Architecture fig on page 1 |
| Experiments | 1.5-2.0 | Setup + results + ablations |
| Discussion | 0.5-1.0 | Limitations go here |
| Conclusion | 0.3-0.5 | Do not repeat the abstract |
| References | 0.5-1.0 | Not counted in page limit |

**Critical rule**: A clear new technical contribution must be articulated by page 3 (quarter of the paper). If the reader doesn't know what you did by then, you've lost them.

#### Section Details

**Abstract** (150-250 words): State the problem, your approach, and the main results. Be factual and comprehensive. Do not repeat the abstract word-for-word later in the paper.

**Introduction** — Follow this 5-paragraph structure:

1. **What is the problem?** Define the task concretely.
2. **Why is it interesting and important?** Real-world impact, scale.
3. **Why is it hard?** Why do naive approaches fail?
4. **Why hasn't it been solved before?** What's wrong with prior solutions? How does yours differ?
5. **What are the key components of your approach and results?** Include specific limitations.

End with a "Summary of Contributions" subsection — bullet list of contributions with section references. This doubles as an outline, saving space.

**Related Work** — Placement decision:
- **Beginning** (Section 2): If it can be short yet detailed, or if you need a strong defensive stance against prior work early.
- **End** (before Conclusions): If comparisons require your technical content, or if it can be summarized briefly in the Introduction. Can be titled "Discussion and Related Work."

**Methods/Approach**: Every section tells a story — the story of the results, NOT the story of how you arrived at them. Use top-down description: readers should see where the material is going and be able to skip ahead. Move gory details to appendices.

**Experiments**: Setup (datasets, metrics, baselines) → main results → ablations → analysis. Every claim needs quantitative evidence.

**Discussion**: Interpret results, compare to prior work, state limitations honestly. Limitations should be specific and actionable, not vague disclaimers.

**Conclusion**: Short summarizing paragraph. Do NOT repeat material from the Abstract or Introduction. Make original claims more concrete (e.g., reference quantitative results). Include future work as bullet list — if actively pursuing follow-up, say so to mark territory.

#### Writing Quality Rules

- Define all notation/terminology before use, only once. Group global definitions in Preliminaries.
- Do NOT use nonreferential "this", "that", "these", "it". Always specify the referent. BAD: "This is important because..." GOOD: "This accuracy gap is important because..."
- Do NOT use "etc." unless remaining items are completely obvious. BAD: "We measure volatility, scalability, etc." GOOD: "We measure volatility and scalability."
- Do NOT write "for various reasons" — state the actual reasons.
- "That" is defining, "which" is nondefining. "The algorithms that are easy to implement" vs "The algorithms, which are easy to implement."
- Use italics for definitions and quotes, not for emphasis. Context alone should provide emphasis.

### Figure Format

Figures use a hybrid marker + structured array approach. ALL figures are generated by a separate pipeline step using an AI image model — your `image_gen_detailed_description` is the ONLY input that model sees. It cannot read files or access data. Do NOT generate actual image files yourself (no matplotlib, no PIL, no image generation scripts).

**In paper_text**: Place `[FIGURE:fig_id]` markers where figures should appear.

**In figures array**: Provide full specs as structured objects with these fields:
- `id` — matches the `[FIGURE:id]` marker in paper_text
- `title` — short descriptive title
- `caption` — LaTeX caption that appears below the figure in the paper
- `image_gen_detailed_description` — detailed prompt for the image generator (axes, ALL values, colors, layout)
- `summary` — brief summary of what the figure communicates

Example in paper_text:
```
...our method achieves state-of-the-art results as shown below.

[FIGURE:fig_1]

The results in Figure 1 demonstrate...
```

Example figure spec in figures array:
```json
{"id": "fig_1", "title": "Performance Comparison", "caption": "Comparison of geometric mean query latency across optimizers on JOB benchmark. RLQOpt achieves 2.3x speedup over PostgreSQL.", "image_gen_detailed_description": "Grouped bar chart. X-axis: model names. Y-axis: accuracy (0.0-1.0). Values: ModelA=0.847, ModelB=0.762, Baseline=0.531. Error bars with std: 0.02, 0.03, 0.05. Sans-serif font, white background.", "summary": "Compares accuracy of proposed methods vs baseline."}
```

Every marker in text MUST have a matching figure in the array, and vice versa.

#### Data Precision Requirement

`image_gen_detailed_description` MUST include exact numbers from artifact output files. Read the actual output files before writing figure specs.

- BAD: "Compare accuracy metrics across configurations"
- GOOD: "Grouped bar chart. X-axis: model names. Y-axis: accuracy (0.0-1.0). Values: K=3: 0.765, K=5: 0.729, Baseline: 0.121."

#### Figure vs Table Decision

Do NOT create figures for tabular data (rows/columns of text or numbers). Use `\begin{table}` in LaTeX instead. Figures are for actual visualizations only (charts, plots, diagrams).

#### Figure Placement Strategy

Be intentional with figure ordering. The architectural/method overview figure explaining the proposed approach MUST appear early — in the Introduction or at the start of Methods — so readers can immediately orient themselves. Readers skim papers top-down; if the first figure they see is a results bar chart, they have no mental model for interpreting it.

Recommended ordering:
1. **Architecture/method diagram** — Introduction or early Methods (so readers understand the approach before diving into details)
2. **Conceptual/analogy figures** — Introduction or Methods (to build intuition)
3. **Results figures** (bar charts, line plots, scatter plots) — Results section
4. **Analysis/ablation figures** — Discussion or later Results

#### Guidelines

- Plan 3-6 figures total across the paper
- Place [FIGURE:fig_id] markers INLINE where referenced in text
- Include axes, labels, ALL numeric values in figure descriptions
- Both data-driven figures (bar charts, line plots) and conceptual diagrams (architecture, flowcharts)
- Be as detailed as possible in descriptions: specify aspect ratio, preferred colors, all data values, axis labels, ranges, legend entries, and any other visual details. The more specific the description, the better the generated figure

### Bibliography with Semantic Scholar

Build `./references.bib` using the aii-semscholar-bib skill (real BibTeX from Semantic Scholar):

1. Collect DOIs, ArXiv IDs, or titles for all papers you need to cite
2. Run the `aii_semscholar_bib__fetch` script with the full list in one batch and
   `--out ./references.bib`: it writes `./references.bib` and the fetch record `./references.json`
3. Cite each paper by the key the script printed

Rules:
- References enter `./references.bib` ONLY through the fetch script — never write BibTeX by hand
- Cite each paper's published version, and check each entry against its Crossref record as the
  aii-semscholar-bib skill describes
- If a paper still isn't found after the skill's fallback procedure, do not cite it
- Use `\bibliography{references}` and `\bibliographystyle{plainnat}`
- Do NOT use inline `thebibliography` environment

### Citation Format (for Research Artifacts)

When writing research with numbered citations:

1. Every factual claim MUST have a numbered citation: `[1]`, `[2]`, `[1, 3]`, etc.
2. Each source in the "sources" array MUST have an "index" field
3. The index MUST EXACTLY MATCH citation numbers in the text
4. NEVER cite a number without a matching source index
5. Example: "LLMs show 40% improvement with multi-agent collaboration [1]."
````

### [4] SKILL-INPUT — aii-semscholar-bib · 2026-10-16 08:19:34 UTC

The agent loaded the **aii-semscholar-bib** skill; its `SKILL.md` (the instructions injected into the agent's context) follows verbatim.

````
---
name: aii-semscholar-bib
description: "Fetches real BibTeX entries in one batch from Semantic Scholar by DOI, ArXiv ID or title via aii_semscholar_bib__fetch, normalises citation keys to AuthorYYYY, injects DOIs, and merges the result into references.bib while recording each entry in references.json beside it; a paper it cannot fetch is not cited. ALWAYS use whenever a bibliography, reference list or .bib file is being built or extended, and whenever a citation needs a verified entry instead of an invented one — never hand-write BibTeX. Triggers: bibliography, references.bib, bibtex, citation key, DOI, arXiv id, Semantic Scholar, reference list, cite these papers, natbib entries. NOT for: writing the text around the citations (use aii-paper-writing), running bibtex and compiling (use aii-paper-to-latex), judging whether cited work supports the claims (use amg-paper-verification), or open-ended literature search and PDF mining (use aii-web-tools)."
---

## Tool: `aii_semscholar_bib__fetch`

Batch-fetch BibTeX entries from Semantic Scholar (OpenAlex, then Crossref, when S2 is rate-limited or down). Pass all references in a single call — the tool handles batching internally.

### How it works

1. **DOI/ArXiv refs** → batched into POST /paper/batch calls (up to 500 per API call, auto-chunked)
2. **Title-only refs** → individual GET /paper/search/match (1s delay between)
3. **Fallback when S2 is down** → if S2 still answers 429 (its shared anonymous pool saturates for every caller) or 5xx after its bounded retries, or cannot be reached, S2 is skipped for the rest of the call, and for the next 10-15 min in every call (then one probe decides whether it is back); every ref it did not answer resolves through **OpenAlex**, then **Crossref** (both keyless; set `AII_POLITE_CONTACT` for their higher-limit polite pool). DOI/arXiv hits must agree with the ref's title or first author, so a mislinked record is dropped rather than cited; title hits need a near-exact title. The BibTeX has the same layout, keys and fields as S2's, so `references.bib` cannot tell them apart; each entry's `source` (`semantic_scholar`, `openalex` or `crossref`) says which API answered.
4. **Post-process** → entry type, venue and year from the DOI's Crossref record (a preprint DOI Crossref links to its published version is cited as that version; S2's publication type decides when Crossref has no record), family names braced (`{De Domenico}`, `{DerSimonian}`); normalise fields so the entry renders cleanly (more than 10 authors keep 5 plus "and others", printed "et al."; S2's mangled accents like `Ram'e` restored; straight quotes as LaTeX quotes; arXiv records as `journal = {arXiv preprint arXiv:<id>}`, never `volume = {abs/<id>}`); fix citation key (AuthorYYYY, accents folded); inject DOI

The ability server runs a single worker (`max_threads: 1`). Multiple concurrent tool calls are queued — each runs independently (no cross-request aggregation). Batching happens within each request.

### Input format

```json
{
  "references": [
    {"doi": "10.48550/arXiv.1706.03762", "author": "Vaswani", "year": 2017},
    {"arxiv": "2201.11903", "author": "Wei", "year": 2022},
    {"title": "Tree of Thoughts", "author": "Yao", "year": 2023}
  ]
}
```

Each reference object can have:
- `doi` — DOI string (ArXiv DOIs like `10.48550/arXiv.XXXX.XXXXX` auto-convert to ArXiv IDs)
- `arxiv` — ArXiv ID (e.g. `"2305.14325"`)
- `title` — Paper title (used for search/match when no DOI/ArXiv)
- `author` — First author last name (for cleaner citation key)
- `year` — Publication year (int, for citation key)

At least one of `doi`, `arxiv`, or `title` is required per reference.

### Output format

```json
{
  "success": true,
  "bib_text": "@inproceedings{Vaswani2017, ...}\n\n@article{Wei2022, ...}",
  "total": 3,
  "found": 3,
  "failed_count": 0,
  "entries": [{"citation_key": "Vaswani2017", "bibtex": "...", "title": "...", "doi": "...", "arxiv": "", "source": "semantic_scholar"}],
  "failed": []
}
```

Called as a tool (or through `--json`), it returns these entries and writes no file. A bibliography
is built only through the CLI's `--out`, which also writes the record.

### Workflow

1. Collect DOIs, ArXiv IDs, or titles for all papers you need to cite
2. Run the CLI below with the full list in **one call** and `--out ./references.bib`
3. The script merges the fetched entries into `references.bib` (created if absent) and writes a
   record of each one to `references.json` beside it: source database, S2 paperId / DOI / arXiv id,
   title, first author, year. Later calls with `--out` append to both files and keep them in sync;
   a second paper under a key already taken gets a letter suffix (`Smith2020a`), which the output
   lists — cite the key it prints.
4. Check the failed list — for any missed papers, follow the **fallback procedure** below

`references.bib` and `references.json` are written ONLY by this script. Never write or paste a
BibTeX entry by hand, and never edit `references.json`: the paper step checks every `\cite` key
against `references.bib` and every entry's title and first author against its record, and an entry
the script did not write blocks the paper from being published.

### Check every fetched entry against its published record (MANDATORY)

The script's entries are raw material, not proof. Reviewers rejected papers whose journal articles
printed as "In Science, volume ...", whose years were a preprint's, and whose particles dropped.

- **Cite the published version.** When a paper has a journal or proceedings version, fetch it by
  that DOI, never by its arXiv or preprint DOI. Look it up on Crossref by title
  (`curl -s "https://api.crossref.org/works?query.bibliographic=<title>&rows=3"`).
- **Compare each entry with its Crossref record** (`curl -s https://api.crossref.org/works/<DOI>`)
  and correct it in `references.bib` to match: entry type (a journal article is `@article` with
  `journal=` and no `booktitle=`), year, authors (every name, spelled and ordered as Crossref has
  them; the script's "and others" past five may stay), venue name and volume.
- **Brace-protect** particles and capitals BibTeX would mangle: `{De Domenico}` (else it prints
  "Domenico"), `{DerSimonian}`, `From {L}ouvain to {L}eiden`.
- Those are the only edits allowed. The title's words stay as fetched, bar a stray character such
  as the footnote digit in "good ideas1", and so does the first author.
  An entry whose title or first author is wrong is re-fetched by its correct DOI, and every
  `\cite` of it moves to the key the script prints.
- After compiling, check the PRINTED reference list in the PDF (see aii-paper-to-latex), not only
  the `.bib`.

### Fallback for failed references (MANDATORY)

NEVER fabricate BibTeX. For each failed reference:
1. **WebSearch** for `"Title" author year` (try `site:arxiv.org` too)
2. **WebFetch** the paper page → extract its DOI or ArXiv ID and exact title
3. Retry the script with that DOI / ArXiv ID / exact title (same `--out`)
4. Still not found → the paper is not cited. Remove the citation (and any claim that rests only on
   it); there is no hand-written fallback.

---

### CLI (how to build a bibliography)

```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /ai-inventor)/.claude/skills/aii-semscholar-bib" && \
$SKILL_DIR/../.ability_client_venv/bin/python $SKILL_DIR/scripts/aii_semscholar_bib__fetch.py --out ./references.bib --refs '[
  {"doi": "10.48550/arXiv.1706.03762", "author": "Vaswani", "year": 2017},
  {"arxiv": "2201.11903", "author": "Wei", "year": 2022},
  {"title": "Tree of Thoughts", "author": "Yao", "year": 2023}
]'
```

`--out, -o PATH` — merge the entries into PATH and record them in `references.json` beside it (always use it for a bibliography)
`--json, -j` — output raw JSON instead of .bib text

**If the script fails** with a connection error (ability server not running): create a local `.venv`, install server deps from `server_requirements.txt` into it, then run the script with that `.venv`'s python (it falls back to the local core when the server is unreachable), `--out` included — bypassing the server:
```bash
uv venv .venv --python=3.12 && uv pip install --python=.venv/bin/python -r "$SKILL_DIR/scripts/server_requirements.txt"
```
````

### [5] SYSTEM-USER prompt · 2026-10-16 08:25:07 UTC

```
[Image: original 2380x1320, displayed at 2000x1109. Multiply coordinates by 1.19 to map to original image.]
```

### [6] SYSTEM-USER prompt · 2026-10-16 08:29:01 UTC

```
REFERENCE CHECK FAILED: 1 citation key(s) in paper.tex are not backed by a fetched reference:
- Riviere2024: first author 'team' does not match the fetched 'Riviere'

For each key: fetch the paper with the aii-semscholar-bib script (`--out ./references.bib`, which also records it in ./references.json) and cite it by the key the script prints, or remove the citation. Never write a BibTeX entry or edit references.json by hand, and do not use \nocite{*}. Then delete paper.bbl and paper.aux and re-run pdflatex, bibtex, pdflatex, pdflatex.
```

### [7] SYSTEM-USER prompt · 2026-10-16 08:30:03 UTC

```
TERMINOLOGY CHECK FAILED: 1 naming issue(s) in paper.tex.

A reader finds this paper by searching for the field's words. A private label costs it those readers, and a bare run-internal code costs the sentence its meaning:
- Undefined coinages (54): "Do not use Kruskal", "Implement a path search algorithm in Python", "Implement a sorting algorithm", "do something else", "implement a path search algorithm", Holm-corrected, Rabin-Karp, away-from-mode, best-first, breadth-first, catch-all, choice-set. None of these appears in the field's own vocabulary or in any cited title, and none is defined within a sentence of its use. Use the field's existing name, or define the term explicitly on first use and keep the same words afterwards.

For each one, exactly one of these applies:
1. The field already names this — use <domain_vocabulary>'s spelling everywhere
2. It is genuinely new — define it once at first use ('we call X ...', 'we define X as ...') and keep the wording identical afterwards
3. It is a bare code in a sentence — replace it with the name of the thing it stands for; codes stay in table headers only

Change nothing else: numbers, claims, citations and figures stay as they are. Then recompile the PDF.
```
