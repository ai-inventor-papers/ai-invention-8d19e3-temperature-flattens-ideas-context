# How an LLM picks a solution idea, and whether internal edits can make it pick new ones: research report

## Framing

This run studies one question from the user's request: when an instruction-tuned open-weight model is asked an open design task such as writing a path search algorithm, how is the choice of solution idea (BFS, DFS, Dijkstra, A*, ...) made inside the model, and can that choice be pushed toward ideas the model does not usually produce? Practitioners treat sampling temperature as the creativity knob and add requests for originality, or prohibitions of named algorithms, to the prompt. Behavioural work finds that temperature is only weakly correlated with novelty in narrative generation, and moderately with incoherence [2], and that incidental prompt cues move algorithm-family choice in code generation without an identified mechanism [3]. The public repository that inspired this run (github.com/DrejcPesjak/llm-creativity) reported, for a weighted shortest-path task on a closed model, that random context seeds changed nothing, that a ban list pushed most programs to a new attractor (SPFA), and that a two-stage pipeline that first lists approaches and then picks one at random (generate-then-select) gave the widest spread.

The run's working hypothesis treats idea choice as a discrete choice made at a few early tokens and governed by a readable vector of internal idea utilities. Under that view each knob acts on a different parameter of a random-utility model: temperature rescales the utilities (it flattens the idea distribution but cannot reorder it), random seeds are utility shocks, bans restrict the choice set with substitution toward internally similar ideas, and novelty instructions shift utilities along a typicality axis. The hypothesis further claims that editing the utilities directly, at the layer and position where the choice forms, is the knob that produces new ideas. Four alternatives were written down with it, and we refer to them by these names throughout: the *gradual-commitment alternative* (commitment spread over many tokens, so heat can reorder ideas); the *far-side ban alternative* (bans push probability to the far side of the idea manifold); the *menu-erasure alternative* (erasing the subspace of the usual ideas is the route to novelty); and the *unusualness-dial alternative* (a single task-general direction controls atypicality).

The model throughout is Qwen2.5-3B-Instruct [1]. The report is chronological, one section per iteration. Each section records what was planned, what ran, every table the artifacts produced, and what the evidence did to the hypothesis.

# Iteration 1: a pre-registered three-arm screen, of which one arm delivered

## 1.1 Strategy and why it was chosen

The hypothesis bundles three separable claims, one per knob family, and each has a rival that predicts the opposite observable on the same data. The iteration therefore planned a wide screen rather than a deep test of one claim: three experiments run in parallel on one model and one shared protocol, each a head-to-head between candidate accounts with a selection rule fixed before any data existed.

- **Temperature arm.** A temperature by top-k grid (T in {0.3, 0.5, 0.7, 1.0, 1.3, 1.6}, top-k in {10, none}, n = 100 per cell, three tasks) with forking-path resampling [4] to locate the commitment token (defined in the hypothesis as the first generated position after which resampling no longer changes the idea class), Arrhenius fits of idea log-odds against 1/T, an ideas-versus-phrasings diversity partition with Hill numbers [11] to answer the user's questions (a), (b) and (c), and a seed-string side condition.
- **Ban arm.** Bans of the top-1, top-3 and top-5 ideas plus a rare-idea priming control, with a geometry-weighted nested logit, a far-side repulsion model and IIA renormalisation as competing predictors of where banned probability goes, scored by held-out Jensen-Shannon divergence. This arm was to draw the low-dimensional map of path-search ideas in activation space, with before/after-ban arrows, that the user asked for.
- **Influence arm.** Three internal knobs (flattening the idea utilities, erasing the menu subspace, a cross-task novelty direction) against tuned temperature, novelty prompts, a top-3 ban and generate-then-select, at matched correctness and against matched-norm random controls.

The shared protocol fixed the model checkpoint, chat template (Qwen's default system message, nothing else), task prompts, per-sample seed equal to the sample index (the user asked for a fixed seed throughout), max 768 new tokens, the idea taxonomy, a comment-stripping AST classifier, and an execution oracle. Two things were reserved and touched by no artifact this iteration: a second model family (gemma-2-2b-it, which also has public SAEs for naming features) and a fourth task (k-th smallest element), both for confirming any survivor in iteration 2. The strategy states plainly that nothing is claimed from the screen alone.

The choice of one model was deliberate: a screen has to compare candidates on identical evidence, and a second model would have halved the depth of each arm. SAE features and circuit discovery were left out on purpose; the field's own evidence rates raw SAE latents as a weak default for steering and single-draw circuits as unstable, so causal weight was to come from steering and erasure with random controls.

## 1.2 What ran and what did not

Only the influence arm produced an artifact [ARTIFACT:art_aSN7z8WuA7Ir]. The other two arms are recorded here as not delivered.

- **Temperature arm: not delivered.** Its executor froze and committed a pre-registration before any data existed and built an idea classifier that passed its 41 fixtures. Setup then consumed most of the time budget: the container had no C compiler, so vLLM's compiled path failed and the executor moved to eager mode and a compiler workaround. The arm ended with an interim status file that explicitly reports no results. Its raw generations were not analysed and are not part of the evidence base; no number from that arm appears in this report.
- **Ban arm: not delivered.** Its executor failed with a model-API streaming error before producing results.

As a consequence, the questions that depended on those arms remain unanswered after iteration 1: the Arrhenius test and the ideas-versus-phrasings partition (the user's questions a, b, c), the forking-path localisation of the commitment token, the seed-shock test, and the nested-logit ban prediction with the manifold figure. The influence arm does contain a temperature sweep, a top-k cell, a top-3 ban and two novelty prompts as baselines, so partial behavioural evidence on those knobs exists and is reported below; it was not designed to test the temperature law or the ban substitution model.

## 1.3 Influence arm: design

**Question.** Does any internal intervention make Qwen2.5-3B-Instruct write more diverse, and genuinely novel, correct path-search programs than the knobs practitioners use?

**Tasks.** Two of the three planned tasks were used; the sorting task served only to extract the cross-task direction. Each prompt is the task sentence followed by an output contract that fixes the function signature, so that every program can be executed:

- *Open path-search task*, or the open task for short: the sentence `Implement a path search algorithm in Python.` plus a contract for `find_path(graph, start, goal)` on an unweighted directed adjacency dict, returning any valid path or None.
- *Weighted shortest-path task*, or the weighted task for short: the sentence `Implement a function that finds a shortest path in a weighted graph.` plus a contract for `shortest_path(graph, source, target)` with non-negative weights, returning `(distance, path)` or `(inf, None)`.

**Engine.** All conditions ran through one HuggingFace engine (bf16) with a custom sampler: sample *i* draws its token uniforms from a random generator seeded with *i* and samples by inverse CDF, so the same index sees the same random numbers in every condition (common random numbers). Generation stops at the closing fence of the first code block; this rule applied to every condition. Hardware was one 32 GB RTX PRO 4500 GPU.

**Correctness.** A sandboxed oracle runs only the requested code (imports, definitions and safe assignments; module-level demo code is removed because it crashed 22% of weighted-task programs for reasons unrelated to the algorithm) on 50 fixed random directed graphs (seed 12345; 10 to 60 nodes; edge density 0.05 to 0.3; start equal to goal, isolated goals, self-loops, unreachable targets and float weights included), with 5 s CPU and 1 GB RAM per program. A program passes only if all 50 graphs are correct: a valid path for the open task, the exact optimal distance with a consistent path for the weighted task.

**Idea labels.** An AST classifier assigns one of 13 classes (Floyd-Warshall, Bellman-Ford, SPFA, bidirectional search, A* search, greedy best-first search, Dijkstra, Dial, iterative deepening, BFS, DFS, random walk, and a catch-all class for anything else) after stripping comments and docstrings; syntax errors and missing code get non-idea labels. A blind LLM judge (gpt-4.1-mini, temperature 0) audited the classifier and also decided whether passing programs in the catch-all class were genuinely distinct algorithms.

**Definitions used throughout this section.** *Idea entropy* is the Shannon entropy, in bits, of the idea-class distribution over the samples of a setting, with syntax-error and no-code outputs excluded. We call the set of idea classes with at least 3% baseline share a task's *menu*. The *off-menu correct share* is the fraction of samples that pass and carry an idea label outside the menu. The *judge-confirmed novel-and-correct share* is the fraction that pass, fall in the catch-all class of the classifier, and are judged a distinct novel algorithm. *Atypicality* is the mean of −log p0(label), with p0 the baseline idea frequency (add-0.5 smoothing). A setting is *eligible* when its pass rate is at least 0.8 times the baseline pass rate (0.56 on the open task, 0.299 on the weighted task, 0.429 pooled); eligibility at the pooled level decided selection.

**Interventions.** All internal knobs act on the residual stream at a band of three layers (29, 30, 31 of 36), at the prompt-final token and the first 64 generated tokens. An additive knob adds α times the median residual norm of the layer (122.0, 135.3 and 170.6 at layers 29 to 31), divided by three, along a unit direction at each band layer. We call the two utility-flattening steering vectors the *probe-weight direction* and the *difference-in-means direction*, the two erasure variants *menu erasure* by rank-1 projection and by LEACE, and the transferred vector the *cross-task novelty direction*; the table below gives the construction of each and the setting names used in later tables.

| setting name in tables | what it is |
|:-|:-|
| baseline T=0.7 | temperature 0.7, plain prompt, seeds 0..149 (the 300-sample draw is used only for menus, probes and vectors) |
| temperature 1.0 to 2.0; temperature 1.6, top-k 10 | temperature 1.0, 1.3, 1.6, 2.0; temperature 1.6 with top-k = 10 |
| new-algorithm prompt | the sentence `Make a new algorithm.` appended to the task sentence |
| 2000-word novelty prompt | the sentence `Make a fully novel algorithm never seen before. Explain the idea in detail (about 2000 words) and implement it.` appended |
| top-3 ban | a prohibition sentence of the form `Do not use any of the following algorithms: ...` naming the three most frequent baseline ideas (open task: BFS, DFS, Dijkstra; weighted task: Dijkstra, BFS, SPFA) |
| generate-then-select | list 10 approaches, pick one with an external seeded RNG, implement it |
| probe-weight direction α=... | mean of the probe weight vectors of the menu classes minus the vector of the modal class |
| difference-in-means direction α=... | minus (mean activation of modal-idea samples minus mean of the rest), in the style of contrastive activation addition [6, 7, 12] |
| ... (post hoc) | lower-strength settings of the same two directions, added after the sweep and excluded from the survival rules |
| rank-1 projection a=... | menu erasure by partial orthogonal projection off the centred menu-centroid subspace (rank 1), strength a in [0, 1] |
| LEACE erasure a=... | menu erasure with LEACE [8] fitted on one-hot menu labels, applied at strength a |
| novelty direction α=... | cross-task novelty direction: difference in means of prompt-final states between plain prompts and the same prompts followed by `Make a fully novel algorithm never seen before.`, over 5 non-path tasks x 40 phrasings |
| random direction α=..., draw k | matched-norm random direction (3 draws, seed 777) at the same strength |
| random projection a=..., draw k | random rank-1 projection (3 draws) at the same strength |
| baseline rerun (noise floor) | the baseline regenerated in differently composed batches |
| ..., held-out | re-draw on fresh seeds 1000..1099 |

**Pre-registered rules** (frozen at 15:39:37 on 2026-10-15, before the sweep). The flattening knobs survive if, on the held-out draw, their idea entropy is at least 2x that of the best eligible temperature and the bootstrap 95% CI of their entropy difference from the matched random direction excludes 0. Menu erasure survives if its judge-confirmed novel-and-correct share is at least 3x the best of temperature, the novelty prompts and the ban, at least 0.05 absolute, and above random projection. The cross-task novelty direction survives if atypicality rises monotonically with strength (Spearman at least 0.8 over α in {0, five strengths}) on both tasks and the top strength beats random. The best setting per family was picked on indices 0..99 and judged on the fresh held-out seeds, to remove winner's-curse bias. We define the *prompting ceiling* as the outcome in which no internal knob survives these rules; the plan fixed it as the headline in that case, naming the prompt-level method on top of each diversity front.

## 1.4 Baseline: two ideas per task, and a weighted task that the model often gets wrong

The 300-sample baseline at T = 0.7 establishes each task's menu and how often each idea is correct. On the open task the model writes BFS about two times in three and DFS about one time in four; on the weighted task it writes Dijkstra three times in four and a BFS-style queue relaxation almost one time in four. The baseline menus are therefore two ideas each, {BFS, DFS} and {Dijkstra, BFS}, which made the planned rank-k menu erasure a rank-1 operation.

Table 1. Baseline idea distribution and per-class pass rate, T = 0.7, seeds 0..299 [ARTIFACT:art_aSN7z8WuA7Ir].

| task | idea class | count | share | passing | pass rate within class |
|:-|:-|:-|:-|:-|:-|
| open path search | BFS | 205 | 0.683 | 150 | 0.732 |
| open path search | DFS | 80 | 0.267 | 54 | 0.675 |
| open path search | other | 12 | 0.040 | 5 | 0.417 |
| open path search | Dijkstra | 2 | 0.007 | 0 | 0.000 |
| open path search | A* | 1 | 0.003 | 1 | 1.000 |
| open path search | **all** | 300 | 1.000 | 210 | 0.700 |
| weighted shortest path | Dijkstra | 225 | 0.750 | 108 | 0.480 |
| weighted shortest path | BFS | 71 | 0.237 | 3 | 0.042 |
| weighted shortest path | SPFA | 2 | 0.007 | 0 | 0.000 |
| weighted shortest path | other | 1 | 0.003 | 1 | 1.000 |
| weighted shortest path | bidirectional | 1 | 0.003 | 0 | 0.000 |
| weighted shortest path | **all** | 300 | 1.000 | 112 | 0.373 |

Correctness differs sharply by idea on the weighted task: BFS-style programs pass on 3 of 71 samples because hop-order expansion is wrong under weights, and even Dijkstra passes only about half the time, failing on edge cases (failing Dijkstra programs are correct on a mean of 33% of the 50 graphs). Any knob that moves mass from Dijkstra toward BFS on this task will raise idea entropy and lower the pass rate at the same time. The planned screening assumption that at least 3 idea classes reach 3% on at least 2 tasks fails here: both tasks have exactly two classes above 3%. The plan's narrow-menu fallback (keep the task, report the narrow menu) applied.

## 1.5 Classifier audit

A stratified sample of 200 programs was labelled blind by the judge. Agreement is 0.715 and Cohen's kappa [10] is 0.684, above the pre-registered 0.6 threshold, so the rule labels stand. The main confusions are a rule label of SPFA against a judge label of BFS (12 programs: queue relaxation without in-queue tracking) and a rule label of greedy best-first search against a judge label of Dijkstra (6). The menu classes themselves are labelled consistently: BFS 20/23, DFS 22/22 and Dijkstra 25/26 rule labels match the judge.

Table 2. Classifier audit: rule label (rows) against blind judge label (columns), n = 200, agreement = 0.715, Cohen's kappa = 0.684.

| rule \ judge | A* | Bellman-Ford | BFS | bidirectional | DFS | Dijkstra | Floyd-Warshall | greedy best-first search | iterative deepening | other | random walk | SPFA | row total |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| **A*** | 15 | · | · | · | · | · | · | · | · | 1 | · | · | 16 |
| **Bellman-Ford** | · | 15 | 1 | · | · | · | · | · | · | · | · | · | 16 |
| **BFS** | · | · | 20 | · | · | · | · | · | · | 3 | · | · | 23 |
| **bidirectional** | · | · | 3 | 7 | · | 3 | · | · | · | 3 | · | · | 16 |
| **DFS** | · | · | · | · | 22 | · | · | · | · | · | · | · | 22 |
| **Dijkstra** | · | · | · | · | · | 25 | · | · | · | 1 | · | · | 26 |
| **Floyd-Warshall** | · | · | · | · | · | · | 17 | · | · | · | · | · | 17 |
| **greedy best-first search** | 3 | · | 1 | · | · | 6 | · | 1 | · | 5 | · | · | 16 |
| **iterative deepening** | · | · | 1 | · | · | · | · | · | 8 | · | · | · | 9 |
| **other** | · | 2 | · | · | · | 8 | · | · | · | 6 | · | · | 16 |
| **random walk** | · | · | · | · | · | · | · | · | · | · | 7 | · | 7 |
| **SPFA** | · | · | 12 | · | · | · | · | · | · | 4 | · | · | 16 |

## 1.6 Locating the choice: probes at the first tokens see nothing, so the late-window fallback was used

The plan chose the intervention band by cross-validated multinomial probes for the final idea at the prompt-final token and the first 8 generated tokens. Two facts defeated that plan [ARTIFACT:art_aSN7z8WuA7Ir]. First, prefill is deterministic, so the prompt-final residual is identical for all samples of a task; a within-task probe there sits at the majority baseline by construction. Second, the first 8 generated tokens are boilerplate (an opening of the form `Certainly! Below is ...`). Probes on generated tokens 1 to 6 return a pooled balanced accuracy of 0.429 to 0.433 at every layer from 1 to 36, and tokens 7 and 8 (alone or averaged with the earlier ones) reach only 0.45 to 0.47. The value 0.433 is exactly the balanced accuracy of predicting each task's majority idea (BFS recall 205/276 = 0.743, Dijkstra recall 225/227 = 0.991, DFS and the rare class 0, mean 0.433): the early tokens carry task identity and nothing about which idea the sample will implement.

The algorithm name, where it appears at all, comes much later. Only 136 of 300 open-task and 152 of 300 weighted-task generations contain an explicit algorithm name anywhere in the text; among those, the first mention never falls within 8 tokens and has a median position of 23.5 tokens on the open task and 46.5 on the weighted task.

Table 3. Position of the first explicit algorithm name in baseline generations (token index after the assistant turn starts).

| task | generations | with an algorithm name | median token of first mention | quartiles (25/50/75) | share within 8 tokens | within 32 | within 64 |
|:-|:-|:-|:-|:-|:-|:-|:-|
| open path search | 300 | 136 | 23.5 | 20.0 / 23.5 / 40.0 | 0.000 | 0.654 | 0.904 |
| weighted shortest path | 300 | 152 | 46.5 | 24.75 / 46.5 / 72.25 | 0.000 | 0.447 | 0.645 |

The plan's pre-registered fallback for chance-level early probes, which we call the late-window fallback, therefore applied: probes were trained on the mean residual over gen1..32, and the hook window was widened to the prompt-final token plus gen1..64. On that feature the probe reaches a pooled balanced accuracy of 0.638 to 0.713 across layers, against 0.392 to 0.429 for within-task shuffled labels (a control-task baseline in the sense of [9]). The curve is flat across depth: layer 0 already gives 0.648. A flat curve that is high from the embedding layer onward is what a readout of name and data-structure tokens inside the window would produce; it is not evidence of an early plan. The band rule picked layers 29 to 31 (mean gap over shuffled 0.282).

[FIGURE:fig_probe]

Table 4. Per-layer idea probes (5-fold CV, logistic regression with C chosen per layer). The gen1-only, gen8-only and mean(gen1..8) columns are the original plan's features; the mean(gen1..32) columns are the late-window feature actually used.

| layer | C | bal. acc. mean(gen1..32), pooled | open path search | weighted shortest path | shuffled-label pooled (mean ± sd, 5 perms) | gen1 only | gen8 only | mean(gen1..8) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| 0 | 0.1 | 0.648 | 0.424 | 0.589 | 0.410 ± 0.026 | 0.247 | 0.359 | 0.450 |
| 1 | 1.0 | 0.664 | 0.440 | 0.602 | 0.402 ± 0.022 | 0.433 | 0.468 | 0.466 |
| 2 | 1.0 | 0.672 | 0.455 | 0.599 | 0.403 ± 0.015 | 0.433 | 0.466 | 0.466 |
| 3 | 1.0 | 0.647 | 0.420 | 0.597 | 0.409 ± 0.022 | 0.433 | 0.463 | 0.467 |
| 4 | 1.0 | 0.663 | 0.444 | 0.597 | 0.424 ± 0.018 | 0.433 | 0.463 | 0.466 |
| 5 | 1.0 | 0.661 | 0.438 | 0.591 | 0.420 ± 0.020 | 0.433 | 0.463 | 0.467 |
| 6 | 1.0 | 0.663 | 0.437 | 0.605 | 0.421 ± 0.018 | 0.433 | 0.467 | 0.466 |
| 7 | 0.1 | 0.661 | 0.440 | 0.594 | 0.413 ± 0.009 | 0.433 | 0.468 | 0.467 |
| 8 | 1.0 | 0.644 | 0.418 | 0.592 | 0.416 ± 0.014 | 0.433 | 0.467 | 0.466 |
| 9 | 0.01 | 0.681 | 0.464 | 0.589 | 0.421 ± 0.011 | 0.433 | 0.466 | 0.465 |
| 10 | 0.01 | 0.684 | 0.467 | 0.589 | 0.420 ± 0.019 | 0.433 | 0.465 | 0.467 |
| 11 | 1.0 | 0.713 | 0.500 | 0.606 | 0.422 ± 0.035 | 0.433 | 0.463 | 0.467 |
| 12 | 0.1 | 0.668 | 0.443 | 0.598 | 0.427 ± 0.025 | 0.433 | 0.467 | 0.463 |
| 13 | 1.0 | 0.666 | 0.443 | 0.600 | 0.407 ± 0.017 | 0.433 | 0.468 | 0.467 |
| 14 | 1.0 | 0.699 | 0.485 | 0.598 | 0.423 ± 0.023 | 0.433 | 0.468 | 0.467 |
| 15 | 0.01 | 0.692 | 0.475 | 0.594 | 0.424 ± 0.018 | 0.433 | 0.468 | 0.467 |
| 16 | 0.1 | 0.690 | 0.470 | 0.606 | 0.416 ± 0.015 | 0.433 | 0.465 | 0.463 |
| 17 | 0.01 | 0.663 | 0.439 | 0.600 | 0.423 ± 0.005 | 0.433 | 0.467 | 0.467 |
| 18 | 1.0 | 0.664 | 0.438 | 0.605 | 0.419 ± 0.023 | 0.433 | 0.466 | 0.467 |
| 19 | 1.0 | 0.675 | 0.458 | 0.602 | 0.411 ± 0.019 | 0.433 | 0.467 | 0.467 |
| 20 | 1.0 | 0.658 | 0.434 | 0.600 | 0.405 ± 0.009 | 0.433 | 0.467 | 0.467 |
| 21 | 0.01 | 0.667 | 0.446 | 0.589 | 0.421 ± 0.007 | 0.433 | 0.465 | 0.467 |
| 22 | 1.0 | 0.665 | 0.440 | 0.600 | 0.410 ± 0.015 | 0.433 | 0.467 | 0.467 |
| 23 | 0.01 | 0.659 | 0.439 | 0.595 | 0.429 ± 0.014 | 0.433 | 0.468 | 0.465 |
| 24 | 0.1 | 0.668 | 0.445 | 0.603 | 0.415 ± 0.030 | 0.433 | 0.467 | 0.466 |
| 25 | 1.0 | 0.661 | 0.437 | 0.605 | 0.421 ± 0.012 | 0.433 | 0.468 | 0.463 |
| 26 | 1.0 | 0.676 | 0.455 | 0.605 | 0.417 ± 0.009 | 0.433 | 0.464 | 0.466 |
| 27 | 0.1 | 0.669 | 0.447 | 0.600 | 0.416 ± 0.010 | 0.433 | 0.463 | 0.466 |
| 28 | 1.0 | 0.656 | 0.434 | 0.594 | 0.408 ± 0.020 | 0.433 | 0.465 | 0.467 |
| 29 | 1.0 | 0.691 | 0.477 | 0.598 | 0.416 ± 0.013 | 0.433 | 0.464 | 0.464 |
| 30 | 1.0 | 0.694 | 0.481 | 0.595 | 0.399 ± 0.021 | 0.433 | 0.468 | 0.467 |
| 31 | 1.0 | 0.680 | 0.460 | 0.601 | 0.401 ± 0.011 | 0.433 | 0.466 | 0.465 |
| 32 | 1.0 | 0.660 | 0.437 | 0.600 | 0.422 ± 0.021 | 0.433 | 0.467 | 0.468 |
| 33 | 0.1 | 0.665 | 0.442 | 0.603 | 0.424 ± 0.007 | 0.433 | 0.468 | 0.467 |
| 34 | 1.0 | 0.638 | 0.409 | 0.598 | 0.416 ± 0.015 | 0.433 | 0.467 | 0.467 |
| 35 | 0.1 | 0.665 | 0.442 | 0.603 | 0.411 ± 0.015 | 0.433 | 0.468 | 0.465 |
| 36 | 1.0 | 0.670 | 0.450 | 0.597 | 0.392 ± 0.015 | 0.433 | 0.468 | 0.463 |

What this settles for the hypothesis is limited but real. In this model and protocol, no linear readout at the prompt-final token or the first 8 generated tokens predicts the idea. The idea becomes decodable only once the 32-token window includes the explanatory preamble, which places the commitment token, if there is a single one, somewhere after token 8. Whether it precedes the first mention of the algorithm's name cannot be read from these data. Forking-path resampling, which would locate it per sample, belonged to the temperature arm and did not run.

## 1.7 Building the intervention vectors, with offline checks

All vectors were built from the baseline only, at layers 29 to 31. Three checks were run before any steered generation.

*The two flattening directions are nearly orthogonal.* The probe-weight direction and the difference-in-means direction have cosine 0.16 to 0.23, so the two flattening variants are different interventions, not two estimates of one.

Table 5. Cosine between the probe-weight and difference-in-means flattening directions.

| layer | cos(probe-weight dir., diff-in-means dir.) open path search | weighted shortest path |
|:-|:-|:-|
| layer 29 | 0.207 | 0.159 |
| layer 30 | 0.225 | 0.163 |
| layer 31 | 0.213 | 0.170 |

*LEACE [8] erases idea information offline; rank-1 projection nearly does.* On cached activations, a fresh probe for the menu label reaches a balanced accuracy of 0.58 to 0.61 on the open task and 0.88 to 0.89 on the weighted task before erasure. After LEACE it reaches 0.20 and 0.33 to 0.35 (chance is 0.33); after rank-1 projection, 0.32 to 0.34. The menu-centroid subspace is effectively one-dimensional: the second singular value of the centred centroid matrix is about 6 times smaller than the first on the open task and 56 to 61 times smaller on the weighted task.

Table 6. Offline erasure check: balanced accuracy of a fresh 5-fold probe for the menu label (menu classes plus a pooled class for everything else) before and after erasure.

| task, layer | probe bal. acc. before | after LEACE | after rank-1 projection | chance | majority share |
|:-|:-|:-|:-|:-|:-|
| open path search, layer 29 | 0.607 | 0.198 | 0.334 | 0.333 | 0.683 |
| weighted shortest path, layer 29 | 0.888 | 0.334 | 0.325 | 0.333 | 0.750 |
| open path search, layer 30 | 0.582 | 0.199 | 0.337 | 0.333 | 0.683 |
| weighted shortest path, layer 30 | 0.884 | 0.352 | 0.323 | 0.333 | 0.750 |
| open path search, layer 31 | 0.577 | 0.198 | 0.339 | 0.333 | 0.683 |
| weighted shortest path, layer 31 | 0.893 | 0.332 | 0.323 | 0.333 | 0.750 |

Table 7. Singular values of the centred menu-centroid matrix (k = 2 menu classes, so the rank is at most 1).

| task, layer | singular value 1 | singular value 2 |
|:-|:-|:-|
| open path search, layer 29 | 3.632 | 0.576 |
| weighted shortest path, layer 29 | 7.930 | 0.134 |
| open path search, layer 30 | 4.023 | 0.626 |
| weighted shortest path, layer 30 | 8.834 | 0.145 |
| open path search, layer 31 | 4.848 | 0.811 |
| weighted shortest path, layer 31 | 10.148 | 0.180 |

*The cross-task novelty direction transfers as a readout.* Extracted from sorting, substring search, primality testing, string compression and matrix multiplication prompts only, the direction separates novel-request from plain prompts on held-out path-search and weighted-path prompts with AUROC 1.0 at all three layers. Leave-one-task-out directions have cosine 0.92 to 0.98 with each held-out task's own difference vector. The direction is close to orthogonal to both flattening directions and to the erasure subspace (absolute cosines at most 0.095).

Table 8. Cross-task novelty direction: transfer and overlap checks.

| layer | leave-one-task-out cosine: sorting | substring | primality | compression | matmul | held-out AUROC open path search | weighted shortest path | cos with probe-weight dir. (path / weighted) | cos with diff-in-means dir. (path / weighted) | cos with erasure subspace (path / weighted) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| layer 29 | 0.941 | 0.978 | 0.956 | 0.934 | 0.966 | 1.0 | 1.0 | 0.037 / -0.027 | 0.008 / 0.093 | 0.009 / 0.095 |
| layer 30 | 0.943 | 0.977 | 0.956 | 0.925 | 0.966 | 1.0 | 1.0 | 0.027 / -0.013 | -0.021 / 0.082 | 0.024 / 0.088 |
| layer 31 | 0.946 | 0.978 | 0.952 | 0.919 | 0.964 | 1.0 | 1.0 | 0.021 / -0.028 | 0.011 / 0.038 | 0.039 / 0.039 |

## 1.8 Strength calibration

Strengths for the three additive knobs were calibrated on the open task with n = 20 per point over a grid of 10 values. The lower bound is the largest grid value with pass at least 0.95x baseline, the upper bound the smallest larger value with pass at most 0.40x baseline, and five strengths are spaced geometrically between them. The calibration was frozen before the full run and reused for the weighted task and the random controls. The calibration rows already show what the full sweep confirms: both flattening directions convert the open task to DFS well before they break code (difference-in-means at α = 0.2 gives DFS 19 of 20), and the probe-weight direction keeps pass near baseline up to α = 0.75 only because its samples are almost all DFS.

Table 9. Strength calibration on the open task (n = 20 per row).

| knob | strength α | pass (n=20) | degenerate share | idea labels |
|:-|:-|:-|:-|:-|
| probe-weight direction | 0.02 | 0.75 | 0.00 | DFS 4, BFS 15, Dijkstra 1 |
| probe-weight direction | 0.05 | 0.55 | 0.00 | DFS 8, BFS 11, A* 1 |
| probe-weight direction | 0.1 | 0.60 | 0.00 | DFS 12, A* 1, BFS 6, other 1 |
| probe-weight direction | 0.2 | 0.90 | 0.00 | DFS 14, BFS 5, other 1 |
| probe-weight direction | 0.35 | 0.85 | 0.00 | DFS 19, other 1 |
| probe-weight direction | 0.5 | 0.65 | 0.00 | DFS 20 |
| probe-weight direction | 0.75 | 0.70 | 0.00 | DFS 19, BFS 1 |
| probe-weight direction | 1.0 | 0.45 | 0.25 | DFS 14, syntax error 5, BFS 1 |
| probe-weight direction | 1.5 | 0.05 | 0.70 | other 3, syntax error 14, DFS 3 |
| probe-weight direction | 2.0 | 0.20 | 0.85 | no code 14, DFS 4, syntax error 1, BFS 1 |
| probe-weight direction | **chosen** | α_lo = 0.75, α_hi = 1.5 | | 0.75, 0.892, 1.06, 1.26, 1.5 |
| difference-in-means direction | 0.02 | 0.65 | 0.00 | DFS 9, BFS 10, A* 1 |
| difference-in-means direction | 0.05 | 0.75 | 0.00 | DFS 13, BFS 6, other 1 |
| difference-in-means direction | 0.1 | 0.65 | 0.00 | DFS 15, BFS 5 |
| difference-in-means direction | 0.2 | 0.60 | 0.00 | DFS 19, BFS 1 |
| difference-in-means direction | 0.35 | 0.40 | 0.00 | DFS 17, BFS 2, other 1 |
| difference-in-means direction | 0.5 | 0.65 | 0.00 | DFS 19, BFS 1 |
| difference-in-means direction | 0.75 | 0.30 | 0.15 | syntax error 1, other 1, DFS 16, BFS 2 |
| difference-in-means direction | 1.0 | 0.00 | 0.95 | no code 10, syntax error 9, DFS 1 |
| difference-in-means direction | 1.5 | 0.10 | 0.80 | DFS 1, no code 16, BFS 2, other 1 |
| difference-in-means direction | 2.0 | 0.00 | 0.95 | no code 19, other 1 |
| difference-in-means direction | **chosen** | α_lo = 0.05, α_hi = 1.0 | | 0.05, 0.106, 0.224, 0.473, 1.0 |
| novelty direction | 0.02 | 0.55 | 0.00 | DFS 3, BFS 16, A* 1 |
| novelty direction | 0.05 | 0.65 | 0.00 | DFS 5, BFS 14, A* 1 |
| novelty direction | 0.1 | 0.80 | 0.00 | DFS 7, BFS 12, A* 1 |
| novelty direction | 0.2 | 0.85 | 0.00 | DFS 10, BFS 10 |
| novelty direction | 0.35 | 0.60 | 0.00 | A* 2, BFS 9, DFS 7, other 1, Dijkstra 1 |
| novelty direction | 0.5 | 0.45 | 0.00 | Dijkstra 2, DFS 11, BFS 4, A* 3 |
| novelty direction | 0.75 | 0.60 | 0.00 | BFS 11, Dijkstra 1, DFS 7, greedy best-first search 1 |
| novelty direction | 1.0 | 0.40 | 0.00 | DFS 9, BFS 8, A* 1, Dijkstra 2 |
| novelty direction | 1.5 | 0.60 | 0.05 | BFS 12, DFS 4, Dijkstra 2, no code 1, A* 1 |
| novelty direction | 2.0 | 0.65 | 0.05 | DFS 6, BFS 12, no code 1, Dijkstra 1 |
| novelty direction | **chosen** | α_lo = 0.2, α_hi = 2.0 | | 0.2, 0.356, 0.632, 1.12, 2.0 |

## 1.9 Main sweep: practitioner knobs

The sweep used seeds 0..149 for every method setting and seeds 0..74 for random controls (n = 150 and 75 per task). Table 10 holds the knobs a practitioner would reach for [ARTIFACT:art_aSN7z8WuA7Ir]. Three results stand out.

First, temperature buys almost no idea diversity before it breaks the code. Between T = 0.7 and T = 1.0 idea entropy rises from 1.175 to 1.278 bits on the open task and from 0.916 to 1.165 on the weighted task, while the weighted-task pass rate falls from 0.380 to 0.233. T = 1.0 misses pooled eligibility by 0.006 (0.423 against 0.429), so the best eligible temperature is T = 0.7 itself. At T = 1.3 a quarter to a third of outputs are syntax errors, at T = 1.6 almost all are, and at T = 2.0 one output in 300 contains a parseable program. Top-k = 10 at T = 1.6 keeps most outputs parseable but the pass rate is still 0.227 and 0.040. Across all temperatures the same two menu ideas dominate the outputs that parse; no temperature introduced a third idea class above 5% of samples.

[FIGURE:fig_temp]

Second, the top-3 ban is largely ignored. On the open task, 142 of 150 programs (0.947) still implement a banned idea, and the ban only evens BFS and DFS out (70/70), which raises entropy from 1.175 to 1.404 bits. On the weighted task 131 of 150 (0.873) still implement Dijkstra, BFS or SPFA; the ban shifts mass from Dijkstra to BFS (from 111/37 to 62/66), which raises entropy to 1.779 bits and drops the pass rate from 0.380 to 0.153, because BFS-style programs fail on weighted graphs. Small amounts of Bellman-Ford (7) and Floyd-Warshall (3) appear. The entropy gain from the ban on the weighted task is mostly a move toward the incorrect menu idea. Non-compliance with negative instructions is a known failure: naming a forbidden item can prime it [5]. The artifact also rendered a PCA view of layer-30 window activations with per-idea centroids for the baseline, the ban and the best projection setting. It is not reproduced here, because its coordinates were not written to the results files, and it is not the planned manifold analysis, which belonged to the ban arm.

Third, the novelty prompts split. The new-algorithm prompt leaves the pooled numbers almost unchanged (pass 0.553, entropy 1.053) but moves the two tasks in opposite directions: more DFS, A* and Dijkstra on the open task (entropy 1.533), and more Dijkstra on the weighted task (137 of 150; entropy 0.573, pass 0.547, the highest weighted-task pass rate in the sweep; the held-out re-draw gives 0.580). The 2000-word novelty prompt raises entropy to 2.205 bits pooled but collapses the pass rate to 0.083, with 39 and 64 syntax errors. Generate-then-select gives the highest entropy of all (2.561 pooled; 9 idea classes on each task) at pass 0.263: listing approaches first does put A*, bidirectional, IDDFS, Bellman-Ford and Floyd-Warshall into the outputs, but these implementations fail the oracle more often.

Table 10. Practitioner knobs and noise-floor rerun (sweep seeds 0..149).

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| baseline T=0.7 | 150 | 0.673 | 1.175 | BFS 98, DFS 44, other 7, Dijkstra 1 | 0.380 | 0.916 | Dijkstra 111, BFS 37, other 1, SPFA 1 | 0.527 | 1.045 | y / y / y |
| baseline rerun (noise floor) | 150 | 0.673 | 1.133 | BFS 95, DFS 50, other 4, Dijkstra 1 | 0.413 | 0.891 | Dijkstra 109, BFS 40, SPFA 1 | 0.543 | 1.012 | y / y / y |
| temperature 1.0 | 150 | 0.613 | 1.278 | BFS 82, DFS 61, other 3, Dijkstra 3, A* 1 | 0.233 | 1.165 | Dijkstra 105, BFS 35, other 6, DFS 2, greedy best-first search 1, syntax error 1 | 0.423 | 1.222 | y / n / n |
| temperature 1.3 | 150 | 0.320 | 1.288 | BFS 52, DFS 51, syntax error 41, other 5, Dijkstra 1 | 0.067 | 1.377 | Dijkstra 73, syntax error 48, BFS 15, other 7, DFS 4, greedy best-first search 2, A* 1 | 0.193 | 1.333 | n / n / n |
| temperature 1.6 | 150 | 0.007 | 0.811 | syntax error 139, no code 7, BFS 3, other 1 | 0.000 | 1.000 | syntax error 134, no code 14, Dijkstra 1, other 1 | 0.003 | 0.906 | n / n / n |
| temperature 1.6, top-k 10 | 150 | 0.227 | 1.366 | BFS 71, DFS 56, syntax error 13, other 6, Dijkstra 4 | 0.040 | 1.301 | Dijkstra 84, syntax error 27, BFS 26, other 7, DFS 4, greedy best-first search 1, no code 1 | 0.133 | 1.333 | n / n / n |
| temperature 2.0 | 150 | 0.000 | 0.000 | syntax error 78, no code 72 | 0.000 | 0.000 | no code 78, syntax error 71, other 1 | 0.000 | 0.000 | n / n / n |
| new-algorithm prompt | 150 | 0.560 | 1.533 | BFS 75, DFS 61, A* 6, Dijkstra 4, other 2, bidirectional 1, iterative deepening 1 | 0.547 | 0.573 | Dijkstra 137, BFS 8, Bellman-Ford 2, Floyd-Warshall 1, SPFA 1, other 1 | 0.553 | 1.053 | y / y / y |
| 2000-word novelty prompt | 150 | 0.113 | 1.881 | DFS 65, syntax error 39, BFS 24, other 6, bidirectional 4, Dijkstra 4, greedy best-first search 2, random walk 2, iterative deepening 2, no code 1, A* 1 | 0.053 | 2.528 | syntax error 64, Dijkstra 37, BFS 17, other 7, greedy best-first search 5, DFS 5, bidirectional 4, random walk 3, Bellman-Ford 3, no code 2, Floyd-Warshall 2, A* 1 | 0.083 | 2.205 | n / n / n |
| top-3 ban | 150 | 0.707 | 1.404 | DFS 70, BFS 70, other 5, Dijkstra 2, A* 2, greedy best-first search 1 | 0.153 | 1.779 | BFS 66, Dijkstra 62, Bellman-Ford 7, other 6, DFS 3, Floyd-Warshall 3, SPFA 3 | 0.430 | 1.591 | y / n / y |
| generate-then-select | 150 | 0.353 | 2.549 | Dijkstra 45, DFS 40, BFS 26, bidirectional 10, A* 10, iterative deepening 6, other 6, syntax error 3, random walk 2, greedy best-first search 2 | 0.173 | 2.574 | Dijkstra 58, A* 21, BFS 19, Floyd-Warshall 13, Bellman-Ford 13, bidirectional 9, syntax error 7, greedy best-first search 5, DFS 3, other 2 | 0.263 | 2.561 | n / n / n |

Table 11 lists what the generate-then-select pipeline chose in stage 1. The picked names are far more varied than what the model writes unprompted; on the weighted task they include the Johnson, Kruskal and Prim algorithms (the last two are minimum-spanning-tree methods, not shortest-path methods), A* search and Bellman-Ford.

Table 11. Generate-then-select, stage 1: items picked by the seeded RNG from the 10-item lists the model wrote itself (possessive apostrophes dropped from item names).

| task | stage-1 lists parsed | mean items listed | 15 most frequent picked items (count) |
|:-|:-|:-|:-|
| open path search | 150/150 | 9.99 | Bidirectional Search (15); Depth-First Search (14); Dijkstra Algorithm (11); Uniform Cost Search (11); Breadth-First Search (10); Depth-First Search (DFS) (9); A* Search Algorithm (8); Greedy Best-First Search (8); Hill Climbing Search (6); Best-First Search (3); A* Search (3); Depth-First Search with Iterative Deepening (3); Wavefront Search (2); Bi-directional Search (2); Iterative Deepening Search (2) |
| weighted shortest path | 150/150 | 9.97 | A* Search Algorithm (19); Bellman-Ford Algorithm (14); Dijkstra Algorithm (11); Floyd-Warshall Algorithm (11); Bidirectional Search (9); Johnson Algorithm (9); Breadth-First Search (BFS) with Relaxation (4); Kruskal Algorithm (3); Breadth-First Search (BFS) with relaxation (3); A* Search (2); Breadth-First Search (with relaxation) (2); Bi-directional Search (2); Johnson algorithm (2); Prim Minimum Spanning Tree (MST) Algorithm (2); Kruskal MST Approach for Shortest Path (via MST) (1) |

## 1.10 Main sweep: internal knobs

**Flattening directions.** Neither flattening direction flattens [ARTIFACT:art_aSN7z8WuA7Ir]. The difference-in-means direction at α = 0.224 turns the open task into DFS on 145 of 150 samples (baseline BFS 98, DFS 44) at an unchanged pass rate (0.680 against 0.673); at α = 0.106 it already gives DFS 126. Idea entropy therefore falls, to 0.235 bits. The probe-weight direction does the same at α = 0.75 (DFS 148 of 150) at a lower pass rate (0.580). On the weighted task the same directions push Dijkstra toward BFS: at α = 0.224 the split is 77/60 against 111/37 at baseline, entropy rises to 1.444 bits, and the pass rate falls to 0.287 because more programs are BFS. With only two menu ideas, a direction that points from the mode toward the mean of the menu overshoots the uniform point and selects the minority idea. At the top strengths both directions destroy the output: the difference-in-means direction at α = 1.0 leaves 148 of 150 open-task samples with no code or a syntax error, the probe-weight direction at α = 1.5 leaves 125.

Table 12. Flattening directions (rows marked post hoc are excluded from survival).

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| probe-weight direction α=0.75 | 150 | 0.580 | 0.102 | DFS 148, BFS 2 | 0.173 | 1.543 | BFS 88, Dijkstra 42, DFS 11, SPFA 4, other 3, syntax error 1, bidirectional 1 | 0.377 | 0.823 | y / n / n |
| probe-weight direction α=0.892 | 150 | 0.387 | 0.323 | DFS 129, syntax error 14, BFS 6, other 1 | 0.087 | 1.522 | BFS 76, Dijkstra 44, DFS 18, syntax error 8, other 2, no code 1, SPFA 1 | 0.237 | 0.922 | n / n / n |
| probe-weight direction α=1.06 | 150 | 0.247 | 0.806 | DFS 81, syntax error 54, BFS 10, other 4, Dijkstra 1 | 0.127 | 1.603 | BFS 60, Dijkstra 45, syntax error 19, DFS 16, no code 6, other 3, Floyd-Warshall 1 | 0.187 | 1.205 | n / n / n |
| probe-weight direction α=1.26 | 150 | 0.020 | 0.994 | syntax error 117, DFS 18, other 15 | 0.200 | 1.410 | Dijkstra 71, BFS 28, no code 23, syntax error 17, DFS 5, other 4, bidirectional 1, Bellman-Ford 1 | 0.110 | 1.202 | n / n / n |
| probe-weight direction α=1.5 | 150 | 0.007 | 0.943 | syntax error 121, other 16, DFS 9, no code 4 | 0.140 | 0.808 | no code 64, Dijkstra 62, syntax error 12, BFS 9, other 2, DFS 1 | 0.073 | 0.875 | n / n / n |
| difference-in-means direction α=0.05 | 150 | 0.727 | 1.149 | DFS 87, BFS 58, other 5 | 0.420 | 0.972 | Dijkstra 106, BFS 40, other 3, syntax error 1 | 0.573 | 1.061 | y / y / y |
| difference-in-means direction α=0.106 | 150 | 0.727 | 0.714 | DFS 126, BFS 22, other 1, A* 1 | 0.360 | 1.192 | Dijkstra 94, BFS 49, other 3, Bellman-Ford 2, syntax error 1, SPFA 1 | 0.543 | 0.953 | y / y / y |
| difference-in-means direction α=0.224 | 150 | 0.680 | 0.235 | DFS 145, BFS 4, other 1 | 0.287 | 1.444 | Dijkstra 77, BFS 60, SPFA 6, other 4, bidirectional 1, syntax error 1, DFS 1 | 0.483 | 0.840 | y / n / y |
| difference-in-means direction α=0.473 | 150 | 0.580 | 0.450 | DFS 138, BFS 7, other 4, syntax error 1 | 0.313 | 1.459 | Dijkstra 80, BFS 52, other 6, syntax error 4, DFS 3, no code 2, Floyd-Warshall 1, Bellman-Ford 1, SPFA 1 | 0.447 | 0.954 | y / y / y |
| difference-in-means direction α=1 | 150 | 0.000 | 1.000 | no code 79, syntax error 69, DFS 1, other 1 | 0.033 | 1.141 | no code 110, syntax error 20, Dijkstra 13, BFS 6, other 1 | 0.017 | 1.071 | n / n / n |
| probe-weight direction α=0.1 (post hoc) | 150 | 0.633 | 1.158 | DFS 83, BFS 62, other 3, A* 1, syntax error 1 | 0.247 | 1.152 | Dijkstra 86, BFS 58, other 5, syntax error 1 | 0.440 | 1.155 | y / n / y |
| probe-weight direction α=0.2 (post hoc) | 150 | 0.733 | 1.046 | DFS 100, BFS 47, other 2, Dijkstra 1 | 0.287 | 1.223 | Dijkstra 78, BFS 66, other 5, SPFA 1 | 0.510 | 1.135 | y / n / y |
| probe-weight direction α=0.35 (post hoc) | 150 | 0.807 | 0.415 | DFS 140, BFS 8, other 1, Dijkstra 1 | 0.313 | 1.340 | BFS 73, Dijkstra 69, SPFA 4, other 2, bidirectional 1, Bellman-Ford 1 | 0.560 | 0.877 | y / y / y |
| probe-weight direction α=0.5 (post hoc) | 150 | 0.753 | 0.160 | DFS 147, BFS 2, Dijkstra 1 | 0.220 | 1.352 | BFS 74, Dijkstra 67, SPFA 5, DFS 2, other 2 | 0.487 | 0.756 | y / n / y |
| difference-in-means direction α=0.075 (post hoc) | 150 | 0.740 | 0.978 | DFS 106, BFS 41, other 3 | 0.380 | 1.100 | Dijkstra 102, BFS 42, other 3, syntax error 1, DFS 1, bidirectional 1 | 0.560 | 1.039 | y / y / y |

[FIGURE:fig_select]

**Menu erasure.** Rank-1 projection and LEACE leave the open-task distribution close to baseline and the weighted task more Dijkstra-heavy, at pass rates near baseline. LEACE at a = 1.0 gives open-task BFS 117 and weighted-task Dijkstra 127; rank-1 projection at a = 0.25 evens the open task (DFS 75, BFS 73) and raises weighted-task BFS to 47. No erasure setting produced a single passing program outside the known classes that the judge accepted as novel. Rank-1 projection at a = 0.5 and above produced 17 to 23 syntax errors on the open task.

Table 13. Menu erasure.

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| rank-1 projection a=0.25 | 150 | 0.720 | 1.089 | DFS 75, BFS 73, other 2 | 0.380 | 1.027 | Dijkstra 100, BFS 47, other 3 | 0.550 | 1.058 | y / y / y |
| rank-1 projection a=0.5 | 150 | 0.640 | 0.983 | DFS 76, BFS 56, syntax error 18 | 0.347 | 0.958 | Dijkstra 101, BFS 48, DFS 1 | 0.493 | 0.971 | y / y / y |
| rank-1 projection a=0.75 | 150 | 0.627 | 1.086 | DFS 74, BFS 57, syntax error 17, other 2 | 0.233 | 1.117 | Dijkstra 96, BFS 49, other 2, SPFA 1, Bellman-Ford 1, syntax error 1 | 0.430 | 1.101 | y / n / y |
| rank-1 projection a=1 | 150 | 0.607 | 0.976 | DFS 75, BFS 52, syntax error 23 | 0.340 | 1.113 | Dijkstra 101, BFS 43, other 2, Bellman-Ford 2, syntax error 1, DFS 1 | 0.473 | 1.045 | y / y / y |
| LEACE erasure a=0.5 | 150 | 0.740 | 1.079 | BFS 100, DFS 46, other 2, Dijkstra 2 | 0.293 | 0.792 | Dijkstra 122, BFS 24, bidirectional 2, DFS 1, syntax error 1 | 0.517 | 0.936 | y / n / y |
| LEACE erasure a=1 | 150 | 0.673 | 1.072 | BFS 117, DFS 23, A* 5, other 2, Dijkstra 2, greedy best-first search 1 | 0.387 | 0.635 | Dijkstra 127, BFS 17, syntax error 4, Floyd-Warshall 1, DFS 1 | 0.530 | 0.853 | y / y / y |

**Cross-task novelty direction.** This is the internal knob with the clearest effect on diversity. At α = 0.356 the open task shows 7 idea classes (DFS 76, BFS 51, A* 9, Dijkstra 6, other 5, greedy best-first 2, bidirectional 1) and entropy 1.750 bits, at pass 0.560, just at the per-task eligibility line. The weighted task barely moves (entropy 0.984). At α = 2.0 about 15% of outputs contain no code.

Table 14. Cross-task novelty direction.

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| novelty direction α=0.2 | 150 | 0.647 | 1.354 | BFS 77, DFS 63, Dijkstra 4, other 3, A* 2, syntax error 1 | 0.440 | 1.100 | Dijkstra 114, BFS 27, other 4, DFS 2, SPFA 2, Bellman-Ford 1 | 0.543 | 1.227 | y / y / y |
| novelty direction α=0.356 | 150 | 0.560 | 1.750 | DFS 76, BFS 51, A* 9, Dijkstra 6, other 5, greedy best-first search 2, bidirectional 1 | 0.373 | 0.984 | Dijkstra 115, BFS 26, other 7, Bellman-Ford 1, syntax error 1 | 0.467 | 1.367 | y / y / y |
| novelty direction α=0.632 | 150 | 0.493 | 1.769 | DFS 75, BFS 48, A* 13, Dijkstra 8, other 3, greedy best-first search 1, syntax error 1, Floyd-Warshall 1 | 0.340 | 1.270 | Dijkstra 108, BFS 26, DFS 9, other 5, Bellman-Ford 2 | 0.417 | 1.519 | n / y / n |
| novelty direction α=1.12 | 150 | 0.493 | 1.520 | BFS 75, DFS 59, Dijkstra 11, A* 2, greedy best-first search 2, other 1 | 0.360 | 0.950 | Dijkstra 119, BFS 22, other 6, greedy best-first search 1, DFS 1, no code 1 | 0.427 | 1.235 | n / y / n |
| novelty direction α=2 | 150 | 0.567 | 1.330 | BFS 76, DFS 42, no code 22, Dijkstra 7, A* 3 | 0.327 | 0.585 | Dijkstra 112, no code 24, BFS 12, SPFA 1, DFS 1 | 0.447 | 0.958 | y / y / y |

**Random controls.** Matched-norm random directions and random projections produce entropy changes of the same size as the targeted knobs. Several random settings reach higher pooled entropy than any targeted internal setting at comparable pass rate (draw 2 at α = 1.12: 1.407 bits at pass 0.467; draw 2 at α = 1.0: 1.370 at 0.487), and the random draws disagree with each other in direction: draw 1 tends toward DFS on the open task and draw 0 toward BFS on the weighted task.

Table 15. Random controls (n = 75 per task).

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| random direction α=0.224, draw 0 | 75 | 0.707 | 0.978 | BFS 44, DFS 31 | 0.307 | 1.088 | Dijkstra 38, BFS 36, other 1 | 0.507 | 1.033 | y / y / y |
| random direction α=0.224, draw 1 | 75 | 0.693 | 1.183 | BFS 50, DFS 21, Dijkstra 2, other 2 | 0.373 | 0.837 | Dijkstra 55, BFS 20 | 0.533 | 1.010 | y / y / y |
| random direction α=0.224, draw 2 | 75 | 0.680 | 1.121 | BFS 44, DFS 29, other 2 | 0.440 | 1.117 | Dijkstra 53, BFS 18, other 3, Bellman-Ford 1 | 0.560 | 1.119 | y / y / y |
| random direction α=0.473, draw 0 | 75 | 0.680 | 1.009 | BFS 54, DFS 19, Dijkstra 1, other 1 | 0.253 | 0.990 | BFS 42, Dijkstra 33 | 0.467 | 0.999 | y / n / y |
| random direction α=0.473, draw 1 | 75 | 0.533 | 1.320 | BFS 39, DFS 32, Dijkstra 2, other 1, A* 1 | 0.253 | 1.025 | Dijkstra 48, BFS 26, other 1 | 0.393 | 1.173 | n / n / n |
| random direction α=0.473, draw 2 | 75 | 0.733 | 1.000 | BFS 38, DFS 37 | 0.360 | 1.250 | Dijkstra 50, BFS 20, other 3, DFS 1, SPFA 1 | 0.547 | 1.125 | y / y / y |
| random direction α=0.632, draw 0 | 75 | 0.640 | 1.093 | BFS 49, DFS 24, other 1, Dijkstra 1 | 0.280 | 0.953 | BFS 47, Dijkstra 28 | 0.460 | 1.023 | y / n / y |
| random direction α=0.632, draw 1 | 75 | 0.560 | 1.492 | DFS 37, BFS 29, Dijkstra 7, other 2 | 0.373 | 0.917 | Dijkstra 58, BFS 15, SPFA 1, bidirectional 1 | 0.467 | 1.204 | y / y / y |
| random direction α=0.632, draw 2 | 75 | 0.787 | 0.994 | DFS 41, BFS 34 | 0.387 | 1.067 | Dijkstra 59, BFS 11, other 2, A* 1, SPFA 1, bidirectional 1 | 0.587 | 1.030 | y / y / y |
| random direction α=1, draw 0 | 75 | 0.613 | 1.092 | BFS 48, DFS 23, syntax error 2, other 1, Dijkstra 1 | 0.093 | 0.986 | BFS 49, Dijkstra 22, syntax error 3, other 1 | 0.353 | 1.039 | y / n / n |
| random direction α=1, draw 1 | 75 | 0.453 | 1.191 | DFS 50, BFS 19, syntax error 2, Dijkstra 2, A* 1, other 1 | 0.347 | 0.743 | Dijkstra 64, BFS 5, syntax error 2, DFS 2, bidirectional 1, other 1 | 0.400 | 0.967 | n / y / n |
| random direction α=1, draw 2 | 75 | 0.707 | 1.284 | BFS 41, DFS 30, A* 2, Dijkstra 2 | 0.267 | 1.456 | Dijkstra 50, BFS 15, other 3, syntax error 2, SPFA 1, Bellman-Ford 1, A* 1, Floyd-Warshall 1, greedy best-first search 1 | 0.487 | 1.370 | y / n / y |
| random direction α=1.06, draw 0 | 75 | 0.547 | 1.095 | BFS 50, DFS 22, other 3 | 0.187 | 1.218 | BFS 47, Dijkstra 19, syntax error 5, other 2, bidirectional 1, Floyd-Warshall 1 | 0.367 | 1.156 | n / n / n |
| random direction α=1.06, draw 1 | 75 | 0.400 | 1.075 | DFS 54, BFS 15, syntax error 2, A* 2, Dijkstra 2 | 0.373 | 0.871 | Dijkstra 61, BFS 11, DFS 2, other 1 | 0.387 | 0.973 | n / y / n |
| random direction α=1.06, draw 2 | 75 | 0.640 | 1.284 | BFS 39, DFS 32, other 3, A* 1 | 0.293 | 1.241 | Dijkstra 54, BFS 14, other 4, Floyd-Warshall 2, DFS 1 | 0.467 | 1.262 | y / n / y |
| random direction α=1.12, draw 0 | 75 | 0.440 | 1.167 | BFS 45, DFS 21, syntax error 5, other 4 | 0.120 | 1.526 | BFS 38, Dijkstra 24, syntax error 6, other 3, bidirectional 2, DFS 1, SPFA 1 | 0.280 | 1.346 | n / n / n |
| random direction α=1.12, draw 1 | 75 | 0.573 | 1.144 | DFS 51, BFS 18, A* 2, Dijkstra 2, syntax error 2 | 0.347 | 0.697 | Dijkstra 63, BFS 7, DFS 3, syntax error 2 | 0.460 | 0.920 | y / y / y |
| random direction α=1.12, draw 2 | 75 | 0.520 | 1.497 | BFS 40, DFS 27, A* 5, other 2, greedy best-first search 1 | 0.413 | 1.316 | Dijkstra 53, BFS 12, other 6, bidirectional 1, greedy best-first search 1, Bellman-Ford 1, syntax error 1 | 0.467 | 1.407 | n / y / y |
| random direction α=1.26, draw 0 | 75 | 0.373 | 0.776 | BFS 54, DFS 16, syntax error 5 | 0.080 | 1.623 | BFS 44, Dijkstra 20, bidirectional 3, greedy best-first search 2, syntax error 2, SPFA 1, other 1, A* 1, Bellman-Ford 1 | 0.227 | 1.199 | n / n / n |
| random direction α=1.26, draw 1 | 75 | 0.400 | 1.219 | DFS 52, BFS 14, other 3, syntax error 3, Dijkstra 2, A* 1 | 0.307 | 1.110 | Dijkstra 55, BFS 13, DFS 3, syntax error 2, A* 1, SPFA 1 | 0.353 | 1.164 | n / y / n |
| random direction α=1.26, draw 2 | 75 | 0.453 | 1.613 | BFS 36, DFS 24, A* 10, other 3, syntax error 2 | 0.280 | 1.409 | Dijkstra 51, BFS 13, other 5, syntax error 2, greedy best-first search 1, DFS 1, Bellman-Ford 1, A* 1 | 0.367 | 1.511 | n / n / n |
| random direction α=1.5, draw 0 | 75 | 0.560 | 0.703 | BFS 63, DFS 8, syntax error 2, Dijkstra 1, other 1 | 0.120 | 1.264 | BFS 42, Dijkstra 27, other 3, syntax error 2, bidirectional 1 | 0.340 | 0.983 | y / n / n |
| random direction α=1.5, draw 1 | 75 | 0.387 | 1.224 | DFS 45, BFS 12, Dijkstra 6, syntax error 6, no code 5, other 1 | 0.213 | 1.341 | Dijkstra 47, BFS 15, other 6, syntax error 4, DFS 1, A* 1, no code 1 | 0.300 | 1.283 | n / n / n |
| random direction α=1.5, draw 2 | 75 | 0.360 | 1.849 | BFS 29, DFS 26, A* 9, Dijkstra 4, syntax error 3, no code 2, greedy best-first search 1, other 1 | 0.280 | 1.550 | Dijkstra 50, other 9, BFS 8, syntax error 2, DFS 2, Bellman-Ford 2, SPFA 1, Floyd-Warshall 1 | 0.320 | 1.699 | n / n / n |
| random direction α=2, draw 0 | 75 | 0.187 | 1.481 | no code 48, BFS 16, DFS 7, Dijkstra 3, bidirectional 1 | 0.093 | 0.889 | no code 48, Dijkstra 19, BFS 4, syntax error 3, other 1 | 0.140 | 1.185 | n / n / n |
| random direction α=2, draw 1 | 75 | 0.267 | 1.420 | no code 25, BFS 24, DFS 11, syntax error 10, Dijkstra 4, other 1 | 0.173 | 0.965 | Dijkstra 33, no code 22, syntax error 12, BFS 5, DFS 2, other 1 | 0.220 | 1.193 | n / n / n |
| random direction α=2, draw 2 | 75 | 0.147 | 1.564 | syntax error 37, BFS 13, no code 11, DFS 11, other 1, A* 1, Dijkstra 1 | 0.120 | 1.095 | syntax error 35, Dijkstra 25, BFS 7, no code 6, SPFA 1, other 1 | 0.133 | 1.329 | n / n / n |
| random projection a=0.5, draw 0 | 75 | 0.560 | 1.115 | BFS 51, DFS 21, Dijkstra 2, other 1 | 0.293 | 1.063 | Dijkstra 51, BFS 22, other 1, Bellman-Ford 1 | 0.427 | 1.089 | y / n / n |
| random projection a=0.5, draw 1 | 75 | 0.613 | 1.226 | BFS 49, DFS 22, other 2, A* 1, Dijkstra 1 | 0.387 | 1.131 | Dijkstra 50, BFS 22, other 2, Bellman-Ford 1 | 0.500 | 1.179 | y / y / y |
| random projection a=0.5, draw 2 | 75 | 0.680 | 1.092 | BFS 47, DFS 26, other 2 | 0.480 | 0.864 | Dijkstra 59, BFS 14, other 2 | 0.580 | 0.978 | y / y / y |
| random projection a=1, draw 0 | 75 | 0.600 | 1.021 | BFS 54, DFS 18, other 3 | 0.347 | 1.020 | Dijkstra 52, BFS 21, Bellman-Ford 2 | 0.473 | 1.021 | y / y / y |
| random projection a=1, draw 1 | 75 | 0.720 | 0.892 | BFS 56, DFS 18, Dijkstra 1 | 0.480 | 1.037 | Dijkstra 51, BFS 22, other 2 | 0.600 | 0.964 | y / y / y |
| random projection a=1, draw 2 | 75 | 0.667 | 0.999 | BFS 50, DFS 24, Dijkstra 1 | 0.427 | 0.748 | Dijkstra 59, BFS 16 | 0.547 | 0.873 | y / y / y |

Table 16 carries the secondary metrics for every method setting: off-menu correct share, atypicality, degeneration, flip rate against the same-seed baseline sample, the order-1 Hill number, idea entropy among passing programs only, and phrasing diversity (mean normalised edit distance among up to 25 programs of the modal idea). Two regularities are worth stating. Phrasing diversity within the modal idea stays between 0.39 and 0.67 in every setting and rises with temperature (0.503 at T = 0.7 to 0.599 at T = 1.3 on the open task), while idea entropy rises little (1.175 to 1.288 bits). Read against the user's cases, this is closer to (a), more phrasings of the same two ideas, than to (b). It rests on two temperature points that still produce code and one phrasing measure; the dedicated ideas-versus-phrasings partition belonged to the temperature arm. And on the weighted task the entropy among passing programs is 0 in many settings: whatever the knob does to the idea mix, the programs that pass are nearly all Dijkstra.

Table 16. Secondary metrics for every method setting (sweep).

| setting | path: off-menu correct | path: atypicality | path: degeneration | path: flip rate vs baseline | path: Hill-1 | path: entropy among passing | path: phrasing diversity (modal idea) | weighted: off-menu correct | weighted: atypicality | weighted: degeneration | weighted: flip rate | weighted: Hill-1 | weighted: entropy among passing | weighted: phrasing diversity |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| baseline T=0.7 | 0.027 | 0.835 | 0.000 | n/a | 2.258 | 1.097 | 0.503 | 0.007 | 0.654 | 0.000 | n/a | 1.887 | 0.254 | 0.467 |
| baseline rerun (noise floor) | 0.007 | 0.816 | 0.000 | 0.167 | 2.194 | 1.013 | 0.513 | 0.007 | 0.643 | 0.000 | 0.107 | 1.855 | 0.324 | 0.495 |
| temperature 1.0 | 0.013 | 0.958 | 0.000 | 0.387 | 2.425 | 1.087 | 0.557 | 0.007 | 0.902 | 0.007 | 0.300 | 2.243 | 0.373 | 0.557 |
| temperature 1.3 | 0.013 | 1.007 | 0.280 | 0.633 | 2.442 | 1.217 | 0.599 | 0.000 | 1.239 | 0.360 | 0.580 | 2.598 | 0.469 | 0.635 |
| temperature 1.6 | 0.000 | 1.100 | 0.980 | 1.000 | 1.755 | 0.000 | 0.570 | 0.000 | 2.813 | 1.000 | 1.000 | 2.000 | 0.000 | n/a |
| temperature 1.6, top-k 10 | 0.000 | 1.034 | 0.107 | 0.560 | 2.577 | 0.834 | 0.610 | 0.000 | 1.090 | 0.213 | 0.500 | 2.464 | 0.000 | 0.663 |
| temperature 2.0 | 0.000 | n/a | 1.000 | 1.000 | 1.000 | 0.000 | n/a | 0.000 | 5.320 | 1.000 | 1.000 | 1.000 | 0.000 | n/a |
| new-algorithm prompt | 0.027 | 1.213 | 0.020 | 0.520 | 2.893 | 1.213 | 0.485 | 0.007 | 0.554 | 0.007 | 0.293 | 1.487 | 0.190 | 0.396 |
| 2000-word novelty prompt | 0.013 | 1.858 | 0.447 | 0.747 | 3.684 | 1.277 | 0.603 | 0.000 | 2.578 | 0.693 | 0.787 | 5.767 | 0.000 | 0.624 |
| top-3 ban | 0.013 | 1.095 | 0.000 | 0.467 | 2.647 | 1.126 | 0.500 | 0.033 | 1.633 | 0.000 | 0.580 | 3.431 | 1.328 | 0.465 |
| generate-then-select | 0.113 | 3.272 | 0.040 | 0.787 | 5.851 | 1.751 | 0.530 | 0.047 | 3.196 | 0.113 | 0.673 | 5.953 | 1.000 | 0.605 |
| probe-weight direction α=0.75 | 0.000 | 1.324 | 0.000 | 0.707 | 1.073 | 0.091 | 0.516 | 0.013 | 1.692 | 0.007 | 0.627 | 2.914 | 1.217 | 0.477 |
| probe-weight direction α=0.892 | 0.007 | 1.309 | 0.093 | 0.720 | 1.251 | 0.418 | 0.537 | 0.013 | 1.809 | 0.060 | 0.673 | 2.871 | 1.352 | 0.526 |
| probe-weight direction α=1.06 | 0.000 | 1.353 | 0.380 | 0.773 | 1.749 | 0.800 | 0.598 | 0.000 | 1.810 | 0.180 | 0.673 | 3.039 | 0.629 | 0.559 |
| probe-weight direction α=1.26 | 0.000 | 2.184 | 0.867 | 0.980 | 1.992 | 0.000 | 0.620 | 0.007 | 1.160 | 0.287 | 0.647 | 2.657 | 0.561 | 0.514 |
| probe-weight direction α=1.5 | 0.000 | 2.529 | 0.947 | 0.980 | 1.922 | 0.000 | n/a | 0.000 | 0.665 | 0.533 | 0.693 | 1.751 | 0.276 | 0.513 |
| difference-in-means direction α=0.05 | 0.007 | 1.037 | 0.000 | 0.420 | 2.218 | 1.050 | 0.505 | 0.013 | 0.716 | 0.007 | 0.313 | 1.962 | 0.320 | 0.491 |
| difference-in-means direction α=0.106 | 0.000 | 1.238 | 0.000 | 0.647 | 1.640 | 0.688 | 0.475 | 0.033 | 0.898 | 0.007 | 0.407 | 2.285 | 0.795 | 0.484 |
| difference-in-means direction α=0.224 | 0.000 | 1.324 | 0.000 | 0.700 | 1.177 | 0.191 | 0.477 | 0.020 | 1.160 | 0.007 | 0.480 | 2.721 | 0.935 | 0.506 |
| difference-in-means direction α=0.473 | 0.000 | 1.343 | 0.007 | 0.720 | 1.366 | 0.269 | 0.521 | 0.013 | 1.174 | 0.040 | 0.480 | 2.748 | 0.893 | 0.501 |
| difference-in-means direction α=1 | 0.000 | 2.268 | 0.993 | 0.993 | 2.000 | 0.000 | n/a | 0.000 | 0.902 | 0.880 | 0.940 | 2.206 | 0.000 | 0.508 |
| probe-weight direction α=0.1 (post hoc) | 0.000 | 1.011 | 0.007 | 0.467 | 2.232 | 0.982 | 0.501 | 0.007 | 0.922 | 0.007 | 0.313 | 2.222 | 0.357 | 0.473 |
| probe-weight direction α=0.2 (post hoc) | 0.007 | 1.091 | 0.000 | 0.560 | 2.065 | 0.982 | 0.479 | 0.007 | 1.009 | 0.000 | 0.427 | 2.335 | 0.603 | 0.420 |
| probe-weight direction α=0.35 (post hoc) | 0.007 | 1.323 | 0.000 | 0.700 | 1.333 | 0.419 | 0.466 | 0.033 | 1.127 | 0.000 | 0.513 | 2.531 | 1.232 | 0.511 |
| probe-weight direction α=0.5 (post hoc) | 0.000 | 1.348 | 0.000 | 0.700 | 1.117 | 0.000 | 0.445 | 0.013 | 1.172 | 0.007 | 0.533 | 2.552 | 0.851 | 0.499 |
| difference-in-means direction α=0.075 (post hoc) | 0.007 | 1.118 | 0.000 | 0.533 | 1.970 | 0.958 | 0.470 | 0.013 | 0.806 | 0.007 | 0.333 | 2.143 | 0.381 | 0.475 |
| rank-1 projection a=0.25 | 0.000 | 0.906 | 0.000 | 0.340 | 2.127 | 0.996 | 0.541 | 0.013 | 0.767 | 0.000 | 0.180 | 2.038 | 0.219 | 0.453 |
| rank-1 projection a=0.5 | 0.000 | 0.939 | 0.120 | 0.547 | 1.977 | 0.992 | 0.489 | 0.000 | 0.715 | 0.000 | 0.207 | 1.943 | 0.000 | 0.434 |
| rank-1 projection a=0.75 | 0.000 | 0.963 | 0.113 | 0.547 | 2.122 | 0.997 | 0.464 | 0.007 | 0.823 | 0.007 | 0.227 | 2.168 | 0.501 | 0.459 |
| rank-1 projection a=1 | 0.000 | 0.953 | 0.153 | 0.567 | 1.967 | 0.975 | 0.470 | 0.007 | 0.829 | 0.007 | 0.240 | 2.163 | 0.460 | 0.395 |
| LEACE erasure a=0.5 | 0.013 | 0.783 | 0.000 | 0.480 | 2.113 | 1.009 | 0.484 | 0.000 | 0.600 | 0.007 | 0.373 | 1.732 | 0.156 | 0.486 |
| LEACE erasure a=1 | 0.013 | 0.844 | 0.000 | 0.473 | 2.103 | 0.682 | 0.428 | 0.000 | 0.524 | 0.027 | 0.360 | 1.553 | 0.126 | 0.485 |
| novelty direction α=0.2 | 0.013 | 1.037 | 0.007 | 0.427 | 2.557 | 1.082 | 0.539 | 0.020 | 0.830 | 0.000 | 0.327 | 2.143 | 0.502 | 0.445 |
| novelty direction α=0.356 | 0.033 | 1.560 | 0.007 | 0.633 | 3.364 | 1.345 | 0.508 | 0.013 | 0.784 | 0.007 | 0.367 | 1.977 | 0.386 | 0.420 |
| novelty direction α=0.632 | 0.033 | 1.675 | 0.047 | 0.647 | 3.408 | 1.337 | 0.537 | 0.007 | 1.121 | 0.000 | 0.467 | 2.411 | 0.139 | 0.452 |
| novelty direction α=1.12 | 0.007 | 1.256 | 0.007 | 0.627 | 2.868 | 1.030 | 0.495 | 0.013 | 0.760 | 0.020 | 0.360 | 1.932 | 0.398 | 0.469 |
| novelty direction α=2 | 0.013 | 1.064 | 0.167 | 0.540 | 2.514 | 1.016 | 0.474 | 0.007 | 0.501 | 0.173 | 0.487 | 1.500 | 0.144 | 0.414 |

Table 17. Secondary metrics for random controls and the held-out draw.

| setting | path: off-menu correct | path: atypicality | path: degeneration | path: flip rate vs baseline | path: Hill-1 | path: entropy among passing | path: phrasing diversity (modal idea) | weighted: off-menu correct | weighted: atypicality | weighted: degeneration | weighted: flip rate | weighted: Hill-1 | weighted: entropy among passing | weighted: phrasing diversity |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| random direction α=0.224, draw 0 | 0.000 | 0.787 | 0.000 | 0.293 | 1.970 | 0.924 | 0.524 | 0.000 | 0.925 | 0.000 | 0.400 | 2.126 | 0.258 | 0.459 |
| random direction α=0.224, draw 1 | 0.027 | 0.854 | 0.000 | 0.320 | 2.271 | 0.966 | 0.520 | 0.000 | 0.613 | 0.000 | 0.213 | 1.786 | 0.000 | 0.456 |
| random direction α=0.224, draw 2 | 0.000 | 0.837 | 0.000 | 0.400 | 2.175 | 0.897 | 0.514 | 0.013 | 0.865 | 0.000 | 0.333 | 2.169 | 0.196 | 0.445 |
| random direction α=0.473, draw 0 | 0.000 | 0.733 | 0.000 | 0.347 | 2.013 | 0.787 | 0.521 | 0.000 | 0.950 | 0.000 | 0.493 | 1.986 | 0.297 | 0.408 |
| random direction α=0.473, draw 1 | 0.000 | 1.020 | 0.000 | 0.440 | 2.497 | 0.934 | 0.516 | 0.000 | 0.772 | 0.000 | 0.307 | 2.035 | 0.000 | 0.478 |
| random direction α=0.473, draw 2 | 0.000 | 0.862 | 0.000 | 0.533 | 2.000 | 1.000 | 0.493 | 0.027 | 0.955 | 0.000 | 0.373 | 2.379 | 0.605 | 0.482 |
| random direction α=0.632, draw 0 | 0.000 | 0.796 | 0.000 | 0.493 | 2.134 | 0.871 | 0.512 | 0.000 | 1.027 | 0.000 | 0.507 | 1.936 | 0.702 | 0.422 |
| random direction α=0.632, draw 1 | 0.067 | 1.348 | 0.000 | 0.533 | 2.812 | 1.456 | 0.544 | 0.000 | 0.663 | 0.000 | 0.267 | 1.889 | 0.000 | 0.514 |
| random direction α=0.632, draw 2 | 0.000 | 0.912 | 0.000 | 0.533 | 1.991 | 1.000 | 0.501 | 0.000 | 0.817 | 0.000 | 0.267 | 2.095 | 0.362 | 0.476 |
| random direction α=1, draw 0 | 0.000 | 0.794 | 0.027 | 0.467 | 2.132 | 0.828 | 0.522 | 0.000 | 1.158 | 0.040 | 0.667 | 1.981 | 0.592 | 0.512 |
| random direction α=1, draw 1 | 0.000 | 1.268 | 0.027 | 0.627 | 2.283 | 0.960 | 0.528 | 0.000 | 0.690 | 0.027 | 0.320 | 1.674 | 0.000 | 0.502 |
| random direction α=1, draw 2 | 0.013 | 1.023 | 0.000 | 0.480 | 2.435 | 1.090 | 0.473 | 0.040 | 1.145 | 0.027 | 0.547 | 2.744 | 0.848 | 0.490 |
| random direction α=1.06, draw 0 | 0.000 | 0.787 | 0.013 | 0.493 | 2.136 | 0.712 | 0.504 | 0.013 | 1.380 | 0.067 | 0.693 | 2.327 | 0.946 | 0.506 |
| random direction α=1.06, draw 1 | 0.027 | 1.349 | 0.027 | 0.627 | 2.107 | 1.111 | 0.506 | 0.013 | 0.705 | 0.000 | 0.387 | 1.829 | 0.222 | 0.515 |
| random direction α=1.06, draw 2 | 0.013 | 0.977 | 0.000 | 0.533 | 2.435 | 1.031 | 0.520 | 0.013 | 1.033 | 0.000 | 0.493 | 2.364 | 0.530 | 0.556 |
| random direction α=1.12, draw 0 | 0.000 | 0.841 | 0.067 | 0.560 | 2.245 | 0.533 | 0.524 | 0.013 | 1.457 | 0.080 | 0.640 | 2.879 | 0.503 | 0.489 |
| random direction α=1.12, draw 1 | 0.027 | 1.310 | 0.027 | 0.653 | 2.210 | 1.118 | 0.513 | 0.000 | 0.668 | 0.027 | 0.333 | 1.621 | 0.391 | 0.504 |
| random direction α=1.12, draw 2 | 0.013 | 1.220 | 0.000 | 0.547 | 2.823 | 1.129 | 0.483 | 0.027 | 1.133 | 0.013 | 0.400 | 2.490 | 0.612 | 0.449 |
| random direction α=1.26, draw 0 | 0.000 | 0.614 | 0.067 | 0.440 | 1.712 | 0.371 | 0.551 | 0.013 | 1.670 | 0.027 | 0.680 | 3.079 | 1.252 | 0.505 |
| random direction α=1.26, draw 1 | 0.040 | 1.384 | 0.053 | 0.600 | 2.328 | 1.249 | 0.505 | 0.000 | 0.908 | 0.027 | 0.453 | 2.158 | 0.258 | 0.536 |
| random direction α=1.26, draw 2 | 0.000 | 1.497 | 0.027 | 0.640 | 3.058 | 0.960 | 0.511 | 0.040 | 1.190 | 0.027 | 0.453 | 2.655 | 0.857 | 0.505 |
| random direction α=1.5, draw 0 | 0.000 | 0.601 | 0.027 | 0.453 | 1.627 | 0.371 | 0.518 | 0.000 | 1.242 | 0.040 | 0.613 | 2.401 | 0.000 | 0.522 |
| random direction α=1.5, draw 1 | 0.013 | 1.516 | 0.147 | 0.747 | 2.336 | 1.091 | 0.540 | 0.013 | 1.157 | 0.080 | 0.493 | 2.533 | 0.669 | 0.502 |
| random direction α=1.5, draw 2 | 0.000 | 1.758 | 0.080 | 0.680 | 3.602 | 0.918 | 0.538 | 0.027 | 1.531 | 0.027 | 0.467 | 2.928 | 0.454 | 0.508 |
| random direction α=2, draw 0 | 0.013 | 1.356 | 0.653 | 0.827 | 2.791 | 0.946 | 0.475 | 0.013 | 0.707 | 0.680 | 0.787 | 1.851 | 0.592 | 0.520 |
| random direction α=2, draw 1 | 0.000 | 1.168 | 0.520 | 0.747 | 2.675 | 0.722 | 0.541 | 0.000 | 0.867 | 0.467 | 0.707 | 1.953 | 0.000 | 0.461 |
| random direction α=2, draw 2 | 0.000 | 1.231 | 0.693 | 0.893 | 2.956 | 0.845 | 0.521 | 0.013 | 0.823 | 0.560 | 0.747 | 2.136 | 0.986 | 0.462 |
| random projection a=0.5, draw 0 | 0.013 | 0.817 | 0.000 | 0.200 | 2.166 | 0.945 | 0.515 | 0.000 | 0.792 | 0.000 | 0.147 | 2.090 | 0.000 | 0.435 |
| random projection a=0.5, draw 1 | 0.013 | 0.874 | 0.000 | 0.173 | 2.339 | 1.049 | 0.524 | 0.013 | 0.859 | 0.000 | 0.187 | 2.191 | 0.216 | 0.422 |
| random projection a=0.5, draw 2 | 0.013 | 0.799 | 0.000 | 0.200 | 2.131 | 1.046 | 0.519 | 0.027 | 0.655 | 0.000 | 0.160 | 1.820 | 0.310 | 0.435 |
| random projection a=1, draw 0 | 0.000 | 0.737 | 0.000 | 0.160 | 2.029 | 0.867 | 0.506 | 0.000 | 0.791 | 0.000 | 0.160 | 2.028 | 0.235 | 0.434 |
| random projection a=1, draw 1 | 0.013 | 0.683 | 0.000 | 0.227 | 1.856 | 0.890 | 0.514 | 0.013 | 0.778 | 0.000 | 0.240 | 2.052 | 0.593 | 0.465 |
| random projection a=1, draw 2 | 0.013 | 0.758 | 0.000 | 0.213 | 1.999 | 1.012 | 0.492 | 0.000 | 0.552 | 0.000 | 0.147 | 1.679 | 0.000 | 0.439 |
| LEACE erasure a=0.5, held-out | 0.000 | 0.796 | 0.000 | n/a | 2.035 | 0.966 | 0.466 | 0.000 | 0.552 | 0.010 | n/a | 1.639 | 0.191 | 0.465 |
| rank-1 projection a=0.25, held-out | 0.000 | 0.887 | 0.000 | n/a | 1.998 | 0.998 | 0.515 | 0.000 | 0.640 | 0.000 | n/a | 1.826 | 0.191 | 0.469 |
| difference-in-means direction α=0.05, held-out | 0.010 | 0.962 | 0.000 | n/a | 2.077 | 1.070 | 0.443 | 0.000 | 0.852 | 0.000 | n/a | 2.147 | 0.316 | 0.449 |
| random direction α=0.05, draw 0, held-out | 0.000 | 0.765 | 0.000 | n/a | 1.952 | 0.928 | 0.529 | 0.000 | 0.690 | 0.000 | n/a | 1.925 | 0.000 | 0.452 |
| random projection a=0.25, draw 0, held-out | 0.010 | 0.756 | 0.000 | n/a | 2.012 | 0.986 | 0.507 | 0.010 | 0.656 | 0.000 | n/a | 1.870 | 0.575 | 0.450 |
| random projection a=0.5, draw 0, held-out | 0.000 | 0.728 | 0.000 | n/a | 1.911 | 0.887 | 0.513 | 0.010 | 0.728 | 0.000 | n/a | 2.007 | 0.201 | 0.467 |
| top-3 ban, held-out | 0.010 | 1.072 | 0.000 | n/a | 2.598 | 1.087 | 0.499 | 0.020 | 1.480 | 0.000 | n/a | 3.203 | 1.472 | 0.479 |
| new-algorithm prompt, held-out | 0.070 | 1.603 | 0.020 | n/a | 3.175 | 1.332 | 0.495 | 0.000 | 0.460 | 0.000 | n/a | 1.430 | 0.000 | 0.411 |
| 2000-word novelty prompt, held-out | 0.000 | 1.771 | 0.520 | n/a | 4.004 | 0.971 | 0.639 | 0.000 | 1.882 | 0.730 | n/a | 4.136 | 0.000 | 0.639 |
| temperature 0.7, held-out | 0.000 | 0.840 | 0.000 | n/a | 2.191 | 0.928 | 0.509 | 0.010 | 0.675 | 0.010 | n/a | 1.888 | 0.420 | 0.488 |

## 1.11 Pareto fronts across all settings

The figure below places every setting on the pooled pass-rate and idea-entropy plane. Above the eligibility line the front, in order of rising entropy, runs through the difference-in-means direction at α = 0.05, the cross-task novelty direction at α = 0.2 and 0.356, and the top-3 ban; generate-then-select extends it below the line. The ban is the eligible setting with the highest entropy (1.591 bits at pass 0.430), and the best internal setting (the novelty direction at α = 0.356: 1.367 at 0.467) sits below it. Seven random-control settings would join the entropy front if controls were allowed on it.

[FIGURE:fig_pareto]

Table 18. Pareto fronts (pass, metric) for each objective, with the random controls that would join them.

| objective (pooled, vs pass rate) | Pareto front (methods only) | random controls that would join the front | best prompt or temperature | best internal knob |
|:-|:-|:-|:-|:-|
| idea entropy | novelty direction α=0.2 (0.543, 1.227); novelty direction α=0.356 (0.467, 1.367); difference-in-means direction α=0.05 (0.573, 1.061); generate-then-select (0.263, 2.561); top-3 ban (0.430, 1.591) | random direction α=0.224, draw 2, random direction α=0.473, draw 2, random direction α=0.632, draw 2, random direction α=1.12, draw 2, random direction α=1.5, draw 2, random direction α=1, draw 2, random projection a=1, draw 1 | top-3 ban (1.591) | novelty direction α=0.356 (1.367) |
| off-menu correct share | novelty direction α=0.356 (0.467, 0.023); difference-in-means direction α=0.05 (0.573, 0.010); probe-weight direction α=0.35 (post hoc) (0.560, 0.020); generate-then-select (0.263, 0.080) | random direction α=0.632, draw 1, random direction α=1, draw 2, random projection a=0.5, draw 2, random projection a=1, draw 1 | top-3 ban (0.023) | novelty direction α=0.356 (0.023) |
| judge-confirmed novel-and-correct share | difference-in-means direction α=0.05 (0.573, 0.000) | random projection a=1, draw 1 | baseline T=0.7 (0.000) | LEACE erasure a=0.5 (0.000) |
| idea entropy among passing programs | novelty direction α=0.356 (0.467, 0.866); difference-in-means direction α=0.05 (0.573, 0.685); probe-weight direction α=0.35 (post hoc) (0.560, 0.826); generate-then-select (0.263, 1.375); top-3 ban (0.430, 1.227) | random direction α=1, draw 2, random projection a=1, draw 1 | top-3 ban (1.227) | novelty direction α=0.356 (0.866) |

Table 19. Ten highest-entropy eligible settings (pooled). Five of the ten are random controls.

| rank | setting | pooled idea entropy |
|:-|:-|:-|
| 1 | top-3 ban | 1.591 |
| 2 | random direction α=1.12, draw 2 | 1.407 |
| 3 | random direction α=1, draw 2 | 1.370 |
| 4 | novelty direction α=0.356 | 1.367 |
| 5 | random direction α=1.06, draw 2 | 1.262 |
| 6 | novelty direction α=0.2 | 1.227 |
| 7 | random direction α=0.632, draw 1 | 1.204 |
| 8 | random projection a=0.5, draw 1 | 1.179 |
| 9 | probe-weight direction α=0.1 (post hoc) | 1.155 |
| 10 | probe-weight direction α=0.2 (post hoc) | 1.135 |

## 1.12 Selection, held-out draw and survival verdicts

The selection step picked, among eligible settings on indices 0..99, the difference-in-means direction at α = 0.05 (highest entropy), rank-1 projection at a = 0.25 and LEACE at a = 0.5 (on the novel-and-correct share, all tied at 0, broken by off-menu share and entropy). The probe-weight direction had no eligible setting. The best eligible temperature was T = 0.7. These were re-drawn on fresh seeds 1000..1099 with their matched controls.

Table 20. Held-out draw, seeds 1000..1099 (n = 100 per task).

| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| temperature 0.7, held-out | 100 | 0.700 | 1.131 | BFS 59, DFS 38, other 3 | 0.300 | 0.917 | Dijkstra 74, BFS 23, other 2, syntax error 1 | 0.500 | 1.024 | y / y / y |
| new-algorithm prompt, held-out | 100 | 0.670 | 1.667 | BFS 44, DFS 38, Dijkstra 14, bidirectional 3, A* 1 | 0.580 | 0.516 | Dijkstra 90, BFS 9, bidirectional 1 | 0.625 | 1.091 | y / y / y |
| 2000-word novelty prompt, held-out | 100 | 0.100 | 2.002 | DFS 34, syntax error 27, BFS 23, other 4, random walk 3, Dijkstra 3, no code 2, greedy best-first search 1, iterative deepening 1, bidirectional 1, A* 1 | 0.060 | 2.048 | syntax error 55, Dijkstra 25, BFS 8, other 4, DFS 2, A* 1, SPFA 1, greedy best-first search 1, no code 1, bidirectional 1, Bellman-Ford 1 | 0.080 | 2.025 | n / n / n |
| top-3 ban, held-out | 100 | 0.670 | 1.378 | BFS 51, DFS 43, other 2, greedy best-first search 2, A* 1, Dijkstra 1 | 0.150 | 1.679 | Dijkstra 45, BFS 43, Bellman-Ford 4, SPFA 2, DFS 2, Floyd-Warshall 2, other 2 | 0.410 | 1.528 | y / n / n |
| difference-in-means direction α=0.05, held-out | 100 | 0.750 | 1.054 | DFS 57, BFS 42, other 1 | 0.350 | 1.102 | Dijkstra 66, BFS 30, other 4 | 0.550 | 1.078 | y / y / y |
| random direction α=0.05, draw 0, held-out | 100 | 0.700 | 0.965 | BFS 61, DFS 39 | 0.270 | 0.945 | Dijkstra 70, BFS 29, other 1 | 0.485 | 0.955 | y / n / y |
| rank-1 projection a=0.25, held-out | 100 | 0.700 | 0.999 | DFS 52, BFS 48 | 0.340 | 0.869 | Dijkstra 71, BFS 29 | 0.520 | 0.934 | y / y / y |
| random projection a=0.25, draw 0, held-out | 100 | 0.720 | 1.009 | BFS 64, DFS 35, other 1 | 0.290 | 0.903 | Dijkstra 73, BFS 26, other 1 | 0.505 | 0.956 | y / n / y |
| LEACE erasure a=0.5, held-out | 100 | 0.790 | 1.025 | BFS 62, DFS 37, A* 1 | 0.340 | 0.713 | Dijkstra 83, BFS 16, DFS 1 | 0.565 | 0.869 | y / y / y |
| random projection a=0.5, draw 0, held-out | 100 | 0.690 | 0.934 | BFS 65, DFS 35 | 0.320 | 1.005 | Dijkstra 73, BFS 24, other 2, SPFA 1 | 0.505 | 0.969 | y / y / y |

On the held-out draw the difference-in-means direction gives 0.93x the entropy of the held-out T = 0.7 draw on the open task and 1.20x on the weighted task, against a required 2x, and its CI against the random direction includes 0 on both tasks. Nothing survives [ARTIFACT:art_aSN7z8WuA7Ir].

Table 21. Pre-registered survival verdicts.

| knob family | selected setting (indices 0..99) | rule | held-out numbers | verdict |
|:-|:-|:-|:-|:-|
| probe-weight flattening | none | entropy ≥ 2× best eligible temperature and CI vs random direction excludes 0 | no eligible setting at matched pass rate | fails |
| difference-in-means flattening | difference-in-means direction α=0.05 | same | path: entropy 1.054 vs 1.131 (ratio 0.932), diff vs random 0.090 [-0.054, 0.234], pass 0.75; weighted: 1.102 vs 0.917 (ratio 1.203), diff 0.158 [-0.069, 0.367], pass 0.35; pooled 1.078 vs 1.024, diff 0.124 [-0.019, 0.251] | fails |
| menu erasure, rank-1 projection | rank-1 projection a=0.25 | judge-confirmed novel-and-correct share ≥ 3× best of temperature/prompts/ban, ≥ 0.05 absolute, CI vs random projection excludes 0 | share 0.000 (comparators all 0.000); rule-only upper bound 0.000; pass 0.520 | fails |
| menu erasure, LEACE | LEACE erasure a=0.5 | judge-confirmed novel-and-correct share ≥ 3× best of temperature/prompts/ban, ≥ 0.05 absolute, CI vs random projection excludes 0 | share 0.000 (comparators all 0.000); rule-only upper bound 0.000; pass 0.565 | fails |
| cross-task novelty direction | all 5 strengths (no selection) | Spearman(α, atypicality) ≥ 0.8 on both tasks and top strength beats random | Spearman path 0.486 [-0.029, 0.543], weighted -0.257 [-0.486, 0.143]; top vs random path -0.176 [-0.529, 0.187], weighted -0.313 [-0.612, -0.041] | fails |

Table 22. Targeted additive settings against the pooled random directions at the same strength (unpaired bootstrap; * = CI excludes 0).

| setting | path: Δ entropy vs random [95% CI] | path: Δ pass vs random [95% CI] | weighted: Δ entropy [95% CI] | weighted: Δ pass [95% CI] |
|:-|:-|:-|:-|:-|
| novelty direction α=0.632 | +0.496 [+0.252, +0.719] * | -0.169 [-0.267, -0.064] * | +0.118 [-0.154, +0.383] | -0.007 [-0.104, +0.096] |
| novelty direction α=1.12 | +0.092 [-0.166, +0.319] | -0.018 [-0.120, +0.096] | -0.454 [-0.748, -0.156] * | +0.067 [-0.033, +0.160] |
| novelty direction α=2 | -0.219 [-0.514, +0.101] | +0.367 [+0.278, +0.462] * | -0.456 [-0.788, -0.075] * | +0.198 [+0.113, +0.282] * |
| difference-in-means direction α=0.224 | -0.892 [-1.092, -0.678] * | -0.013 [-0.113, +0.078] | +0.374 [+0.130, +0.584] * | -0.087 [-0.182, +0.007] |
| difference-in-means direction α=0.473 | -0.713 [-0.946, -0.475] * | -0.069 [-0.171, +0.029] | +0.302 [+0.058, +0.533] * | +0.024 [-0.071, +0.124] |
| difference-in-means direction α=1 | -0.287 [-1.391, -0.196] * | -0.591 [-0.653, -0.524] * | -0.210 [-0.762, +0.149] | -0.202 [-0.262, -0.142] * |
| probe-weight direction α=1.06 | -0.498 [-0.805, -0.173] * | -0.282 [-0.380, -0.187] * | +0.278 [+0.028, +0.497] * | -0.158 [-0.233, -0.076] * |
| probe-weight direction α=1.26 | -0.463 [-0.637, -0.313] * | -0.389 [-0.453, -0.324] * | -0.201 [-0.546, +0.102] | -0.022 [-0.107, +0.058] |
| probe-weight direction α=1.5 | -0.634 [-0.923, -0.434] * | -0.429 [-0.493, -0.367] * | -0.763 [-1.124, -0.427] * | -0.064 [-0.140, +0.004] |

The cross-task novelty direction fails its own test in an instructive way. Atypicality rises from α = 0 to 0.632 on the open task (0.835 to 1.675) and then falls back (1.064 at α = 2.0); on the weighted task it never rises consistently. The rule required Spearman at least 0.8 on both tasks; the values are 0.486 and −0.257. At the top strength the direction is less atypical than random directions on the weighted task (CI excludes 0 in the wrong direction).

[FIGURE:fig_a4]

Table 23. Cross-task novelty direction: dose-response used by the survival rule (α = 0 is the baseline).

| strength α | path: atypicality | path: pass | weighted: atypicality | weighted: pass |
|:-|:-|:-|:-|:-|
| 0.0 | 0.835 | 0.673 | 0.654 | 0.380 |
| 0.2 | 1.037 | 0.647 | 0.830 | 0.440 |
| 0.356 | 1.560 | 0.560 | 0.784 | 0.373 |
| 0.632 | 1.675 | 0.493 | 1.121 | 0.340 |
| 1.12 | 1.256 | 0.493 | 0.760 | 0.360 |
| 2.0 | 1.064 | 0.567 | 0.501 | 0.327 |
| slope of Δlog p vs −log p0 at top strength | 0.242 | | 0.230 | |

## 1.13 Manipulation checks: the steering does what it was built to do internally, and the output follows only partly

Baseline probes (trained on unsteered mean(gen1..32) residuals) were applied to the residuals captured during steered generation, at layer 30 (band middle) and layer 33 (downstream). Two quantities are reported: the probe menu entropy, defined as the entropy of the probe softmax restricted to the menu, and the probe decodability, defined as the balanced accuracy with which the probe predicts the realised idea of each steered sample. For the flattening directions the probe menu entropy goes to 0.000 bits at every strength from α = 0.224 (difference-in-means; from α = 0.106 on the open task) and at every probe-weight strength: the steered state reads as one idea with full confidence, the opposite of flattening, and consistent with the DFS takeover in the outputs. For erasure, probe decodability drops to 0.27 to 0.44 at full strength (unsteered rerun: 0.48 and 0.57), yet the outputs remain BFS, DFS and Dijkstra. The internal readout can be erased without the behaviour changing.

Table 24. Manipulation checks with baseline probes on steered residuals (unsteered reference rows first).

| setting | path, layer 30: probe menu entropy (bits) | path, layer 30: probe decodability | path, layer 33: menu entropy | path, layer 33: decodability | weighted, layer 30: menu entropy | weighted, layer 30: decodability | weighted, layer 33: menu entropy | weighted, layer 33: decodability |
|:-|:-|:-|:-|:-|:-|:-|:-|:-|
| baseline rerun (noise floor) | 0.181 | 0.481 | 0.274 | 0.489 | 0.128 | 0.574 | 0.186 | 0.577 |
| temperature 0.7, held-out | 0.233 | 0.484 | 0.322 | 0.475 | 0.152 | 0.594 | 0.201 | 0.565 |
| temperature 1.0 | 0.165 | 0.570 | 0.237 | 0.655 | 0.168 | 0.417 | 0.222 | 0.424 |
| top-3 ban | 0.273 | 0.403 | 0.410 | 0.410 | 0.300 | 0.361 | 0.330 | 0.329 |
| new-algorithm prompt | 0.138 | 0.463 | 0.190 | 0.583 | 0.059 | 0.414 | 0.069 | 0.456 |
| 2000-word novelty prompt | 0.173 | 0.327 | 0.350 | 0.323 | 0.334 | 0.323 | 0.340 | 0.287 |
| probe-weight direction α=0.75 | 0.000 | 0.500 | 0.000 | 0.500 | 0.000 | 0.250 | 0.000 | 0.250 |
| probe-weight direction α=0.892 | 0.000 | 0.333 | 0.000 | 0.333 | 0.000 | 0.250 | 0.000 | 0.250 |
| probe-weight direction α=1.06 | 0.000 | 0.250 | 0.000 | 0.250 | 0.000 | 0.250 | 0.000 | 0.250 |
| probe-weight direction α=1.26 | 0.000 | 0.500 | 0.000 | 0.500 | 0.000 | 0.250 | 0.000 | 0.250 |
| probe-weight direction α=1.5 | 0.000 | 0.500 | 0.000 | 0.500 | 0.000 | 0.250 | 0.000 | 0.250 |
| difference-in-means direction α=0.05 | 0.109 | 0.526 | 0.153 | 0.564 | 0.162 | 0.553 | 0.226 | 0.553 |
| difference-in-means direction α=0.106 | 0.000 | 0.333 | 0.009 | 0.333 | 0.209 | 0.401 | 0.183 | 0.394 |
| difference-in-means direction α=0.224 | 0.000 | 0.333 | 0.000 | 0.333 | 0.000 | 0.250 | 0.000 | 0.250 |
| difference-in-means direction α=0.473 | 0.000 | 0.333 | 0.000 | 0.333 | 0.000 | 0.250 | 0.000 | 0.250 |
| difference-in-means direction α=1 | 0.000 | 0.500 | 0.000 | 0.500 | 0.000 | 0.333 | 0.000 | 0.333 |
| rank-1 projection a=0.25 | 0.169 | 0.645 | 0.292 | 0.668 | 0.127 | 0.509 | 0.177 | 0.522 |
| rank-1 projection a=0.5 | 0.108 | 0.462 | 0.224 | 0.516 | 0.147 | 0.360 | 0.221 | 0.398 |
| rank-1 projection a=0.75 | 0.162 | 0.431 | 0.242 | 0.476 | 0.116 | 0.336 | 0.169 | 0.384 |
| rank-1 projection a=1 | 0.175 | 0.436 | 0.227 | 0.466 | 0.093 | 0.273 | 0.144 | 0.281 |
| LEACE erasure a=0.5 | 0.290 | 0.282 | 0.408 | 0.427 | 0.117 | 0.294 | 0.116 | 0.288 |
| LEACE erasure a=1 | 0.085 | 0.392 | 0.192 | 0.526 | 0.114 | 0.286 | 0.081 | 0.292 |
| novelty direction α=0.2 | 0.150 | 0.600 | 0.294 | 0.571 | 0.099 | 0.382 | 0.381 | 0.377 |
| novelty direction α=0.356 | 0.146 | 0.394 | 0.290 | 0.544 | 0.034 | 0.337 | 0.311 | 0.422 |
| novelty direction α=0.632 | 0.015 | 0.250 | 0.355 | 0.371 | 0.064 | 0.319 | 0.431 | 0.277 |
| novelty direction α=1.12 | 0.003 | 0.250 | 0.172 | 0.245 | 0.202 | 0.250 | 0.001 | 0.250 |
| novelty direction α=2 | 0.000 | 0.250 | 0.000 | 0.250 | 0.129 | 0.250 | 0.000 | 0.250 |

## 1.14 Novelty: the judge found no novel correct program in any condition

Every distinct passing program in the catch-all class of the classifier, across the sweep and the held-out draw, was sent to the judge: 70 programs [ARTIFACT:art_aSN7z8WuA7Ir]. All 70 were judged to be known algorithms, most often Dijkstra written in an unusual way (41). The judge-confirmed novel-and-correct share is therefore 0 in every condition, including generate-then-select and the 2000-word novelty prompt. Over all 267 judge calls (audit plus novelty checks) the verdicts were: Dijkstra 81, BFS 45, other (known) 31, DFS 25, Bellman-Ford 23, A* 18, Floyd-Warshall 17, iterative deepening 8, bidirectional 7, random walk 7, unparsed 4, greedy best-first search 1. Judge spend was $0.081 against a $1.5 cap.

Table 25. Judge verdicts on the 70 distinct passing programs in the catch-all class of the classifier.

| judge verdict | open path search | weighted shortest path | total |
|:-|:-|:-|:-|
| Dijkstra | 4 | 37 | 41 |
| other (known) | 11 | 1 | 12 |
| Bellman-Ford | 0 | 7 | 7 |
| BFS | 7 | 0 | 7 |
| DFS | 3 | 0 | 3 |
| distinct novel algorithm | 0 | 0 | 0 |
| **all** | 25 | 45 | 70 |

## 1.15 Noise floor and independent verification

Regenerating the baseline in differently composed batches flips 16.7% of open-task and 10.7% of weighted-task idea labels at the same seeds (the noise-floor rerun row in Table 10), because bf16 numerics depend on batch composition. Common random numbers therefore pair conditions only approximately, and the per-sample flip rates in Tables 16 and 17 have a floor of roughly 0.11 to 0.17. An independent re-derivation script, with its own oracle runner, a coarse independent classifier and a separate recomputation of every metric, reproduces the stored numbers. The placebo test also shows that the bootstrap CIs are somewhat anticonservative: random splits of the baseline produce a CI excluding 0 at a rate of 0.10 and 0.15 instead of 0.05, which matters for any claim resting on a CI that barely excludes 0. None of the iteration's verdicts rests on such a claim, because nothing came close to the survival margins.

Table 26. Independent verification and placebo checks.

| check | result |
|:-|:-|
| independent oracle runner vs stored pass/fail | 1.000 agreement on 147 programs |
| coarse independent classifier vs AST classifier | 0.973 agreement |
| entropy difference, open path search, baseline vs noise-floor rerun (placebo) | 95% CI [-0.182, 0.281], excludes 0: False |
| entropy difference, weighted shortest path, baseline vs noise-floor rerun (placebo) | 95% CI [-0.189, 0.228], excludes 0: False |
| entropy difference, open path search, top-3 ban vs baseline (real effect) | 95% CI [-0.035, 0.445], excludes 0: False |
| entropy difference, weighted shortest path, top-3 ban vs baseline (real effect) | 95% CI [0.560, 1.103], excludes 0: True |
| rate at which a random split of the baseline yields a CI excluding 0 | path 0.10, weighted 0.15 (nominal 0.05) |

## 1.16 Bookkeeping

- Artifact: `art_aSN7z8WuA7Ir` (gen_art_experiment_3). 19,250 generations in total, in 111 setting files per task (baseline, calibration, sweep, held-out, post-hoc, generate-then-select). Pipeline stages and wall-clock times as recorded: baseline about 5 min, activation cache 2 min, probes 2 min, vectors 3 min, calibration 4 min, sweep about 65 min, post-sweep chain (judge, select, held-out, judge, analyse) about 25 min, post-hoc settings 5 min, verification 4 min; roughly two GPU-hours on one RTX PRO 4500 (32 GB).
- The first sweep launch was stopped after about 2,400 generations because of CUDA allocator thrashing and resumed from the per-setting files with `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (allocator only, no change to numerics). Two held-out files whose scoring thread crashed on a malformed return were scored afterwards by `score_backlog.py`.
- Deviations from the plan, all recorded in the artifact: the late-window probe feature and hook window; menus exclude the catch-all class, so k = 2 and erasure is rank 1; oracle runs only the requested code; code-block early stop for all conditions; n = 150 and 75 instead of the planned 100 and 50, with a 100-seed held-out draw; post-hoc low-strength flattening settings reported but excluded from survival; a single model.
- Kept on the run volume only (not in the published repository): `acts/` (0.9 GB baseline residuals, split into parts under 100 MB) and `caps/` (0.9 GB residuals captured during steering). Published: generations, scored rows, judge verdicts, vectors (`vectors/vectors.pt` and one LEACE eraser file per task, `vectors/leace_*.pt`), figures and results files.
- The external judge model was the only paid call: $0.081.
- Files: pre-registered rules `results/rules.json` (frozen 2026-10-15 15:39:37); all metrics and CIs `results/results.json`; independent re-derivation `verify_headline.py` → `results/verify_headline.json`; PCA view `figs/fig_pca_manifold.png`; artifact figures `figs/` (probe curve, three Pareto fronts, fraction-correct violins, novelty-direction dose-response, idea shares, PCA view); schema output `method_out.json` with `full_`, `mini_` and `preview_` variants.

## 1.17 What iteration 1 established, and what it did not

**Established, on one model and two tasks.**

1. The internal knobs tested here are selectors, not diversifiers. A single residual direction at layers 29 to 31, built from baseline activations, moves the open task from two-thirds BFS to 97% DFS without costing correctness. This is controllable choice among ideas the model already writes. No knob produced an idea outside the model's usual repertoire.
2. Under the pre-registered rules no internal knob beats the practitioner knobs: the difference-in-means direction reached 0.93x and 1.20x the entropy of the best eligible temperature on held-out seeds (2x required), menu erasure produced no novel correct program, and the cross-task novelty direction was not monotone in strength. The headline the rules prescribe is the prompting ceiling, with the top-3 ban atop the eligible entropy front and generate-then-select atop the full front.
3. Matched-norm random directions raise idea entropy about as much as targeted ones, and five of the ten highest-entropy eligible settings are random controls. Most of the diversity that steering buys here is non-specific perturbation.
4. Temperature is not a creativity knob for this model on these tasks. Its eligible range ends at T = 0.7; above that, correctness collapses while idea entropy gains a few tenths of a bit and no new idea class appears above 5% of samples.
5. Bans are mostly ignored by this 3B model (87% to 95% of programs still use a banned idea), and on the weighted task the ban moves mass from the correct menu idea to the incorrect one.
6. Novelty, defined strictly as a correct program the judge does not recognise as a known algorithm, was zero in every condition.
7. The idea is not linearly decodable from the prompt-final token or the first 8 generated tokens; it becomes decodable from the mean over the first 32 generated tokens, which cover the explanatory preamble, at about the same level at every layer.

**Dead ends recorded as such.**

- *Flattening the idea utilities as a novelty knob (the main hypothesis's claim about direct utility edits).* Killed by Table 12, the idea-composition figure in Section 1.10 and Table 24: the flattening directions select the minority idea, the internal readout collapses to one idea, and the held-out entropy ratio is 0.93 and 1.20 against a required 2.
- *Menu erasure as a route to novelty (the menu-erasure alternative).* Killed by Tables 13 and 25: erasure removes idea decodability offline (weighted task 0.888 to 0.334) and online (0.27 to 0.44), but the outputs remain BFS, DFS and Dijkstra and the novel-and-correct share is 0.
- *A single portable unusualness dial (the unusualness-dial alternative).* Killed as a dial by Table 23 (Spearman 0.486 and −0.257, required 0.8), although the direction transfers perfectly as a readout (AUROC 1.0, Table 8). Reading whether novelty was requested is easy; turning that reading into atypical outputs did not work.
- *Probing the first 8 tokens for the choice.* The planned probe feature carried only task identity (Table 4).
- *Temperature arm and ban arm.* Not delivered; no evidence either way from them.

**Open after iteration 1.**

- Whether the temperature law holds (straight Arrhenius lines, no reordering) or the gradual-commitment alternative holds; the influence arm's temperature rows show no reordering among the two menu ideas but cover only T = 0.7 to 1.3 with usable output.
- Where the commitment point is per sample (forking-path resampling), and whether a utility vector read there predicts temperature, seed and ban effects.
- Seeds: untested.
- Where banned probability goes (nearest neighbour, far side, or proportional): the influence arm's single ban shows mostly non-compliance, which by itself argues that a 3B model may be the wrong place to test substitution structure, since there is little banned mass to redistribute.
- Whether the selector finding generalises to the reserved model and task.

# What we have learned so far

The run set out to test whether an LLM's choice of solution idea is a discrete choice governed by a readable internal utility vector, and whether editing that vector is a better creativity knob than temperature, prompts or bans. After one iteration, only the internal-influence part has evidence [ARTIFACT:art_aSN7z8WuA7Ir], from one model (Qwen2.5-3B-Instruct) and two path-search tasks whose baseline menus contain two ideas each.

That evidence answers the user's question of whether LLMs can be made to give truly novel solutions in the negative for this setting: no condition, internal or external, produced a single correct program that a judge accepted as a new algorithm, and no internal knob met the pre-registered bar against tuned temperature, prompts and bans. What internal steering does provide is reliable selection: one residual direction switches the dominant idea (BFS to DFS on the open task, 145 of 150 samples) at unchanged correctness. Diversity gains from steering are about as large for random directions as for targeted ones. Temperature buys a few tenths of a bit of idea entropy before code breaks, and the most diverse outputs come from external two-stage prompting (generate-then-select, 2.56 bits) at a large correctness cost. The prompt-level ban raised entropy mainly because it was ignored on the open task and moved mass to an incorrect idea on the weighted task.

On the mechanism, the idea is not decodable at the prompt-final token or in the first eight generated tokens, and becomes decodable only from a 32-token window that covers the explanatory preamble, at about the same level at every layer. The temperature law, the commitment token, the seed-shock test and the ban substitution structure remain untested, because the arms built for them did not deliver.

Status of the user's questions after iteration 1:

1. *Is temperature the creativity knob, and do cases (a), (b) or (c) hold under tight temperature with top-k = 10?* Partly answered. Temperature adds at most a few tenths of a bit of idea entropy before code breaks, and phrasing diversity rises faster than idea entropy between T = 0.7 and 1.3, which leans toward case (a). Only one top-k cell (T = 1.6, top-k = 10) was run, and the dedicated grid did not deliver.
2. *Does the model always design BFS for the path-search prompt?* Answered for this model: BFS in 68% of baseline samples and DFS in 27%, with A* and Dijkstra under 1%.
3. *Does context seeding (prepending `seed=d32qxk4nt43` or `seed=(horse chair roof love)`) help?* Not tested; the seed condition belonged to the temperature arm.
4. *Is the model giving the average answer?* Not tested directly. The baseline distributions are bimodal over two discrete ideas, so there is no meaningful average idea to give; whether the default is the mode of a readable utility landscape needs the utility readout, which did not run.
5. *How much do prompt instructions matter?* Answered for three instructions: the new-algorithm prompt changes little pooled but moves the two tasks in opposite directions, the 2000-word novelty prompt raises entropy and destroys correctness, and a top-3 ban is mostly ignored.
6. *What do the internals of BFS, DFS and Dijkstra runs look like, and can a manifold be drawn?* Partly answered. Ideas are linearly decodable from a 32-token window at 0.64 to 0.71 balanced accuracy and the centroid subspace is one-dimensional per task. The planned manifold figure with before/after-ban arrows was not produced; SAE, attribution-graph and thought-anchor analyses were not run.
7. *After banning the top ideas, does mass move to the edge or the opposite side?* Not answerable from this iteration: the 3B model mostly ignored the ban, and the ban arm did not deliver.
8. *Can we make LLMs give truly creative and novel solutions?* Answered negatively for this model and these tasks: zero judge-confirmed novel and correct programs under any of the 80 non-calibration settings.

# References

[1] Yang et al. Qwen2.5 Technical Report. arXiv:2412.15115, 2024. (Yang2024)

[2] Peeperkorn et al. Is Temperature the Creativity Parameter of Large Language Models? ICCC, 2024. (Peeperkorn2024)

[3] Narula et al. The Invisible Lottery: How Subtle Cues Steer Algorithm Choice in LLM Code Generation. arXiv:2606.04057, 2026. (Narula2026)

[4] Bigelow et al. Forking Paths in Neural Text Generation. arXiv:2412.07961, 2024. (Bigelow2024)

[5] Rana. Semantic Gravity Wells: Why Negative Constraints Backfire. arXiv:2601.08070, 2026. (Rana2026)

[6] Rimsky et al. Steering Llama 2 via Contrastive Activation Addition. ACL, 2024. (Rimsky2023)

[7] Turner et al. Steering Language Models With Activation Engineering. 2023. (Turner2023)

[8] Belrose et al. LEACE: Perfect linear concept erasure in closed form. NeurIPS, 2023. (Belrose2023)

[9] Hewitt and Liang. Designing and Interpreting Probes with Control Tasks. EMNLP-IJCNLP, 2019. (Hewitt2019)

[10] Cohen. A Coefficient of Agreement for Nominal Scales. Educational and Psychological Measurement, 1960. (Cohen1960)

[11] Hill. Diversity and Evenness: A Unifying Notation and Its Consequences. Ecology, 1973. (Hill1973)

[12] Arditi et al. Refusal in Language Models Is Mediated by a Single Direction. NeurIPS, 2024. (Arditi2024)
