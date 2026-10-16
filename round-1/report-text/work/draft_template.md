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
|---|---|
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

{{baseline300}}

Correctness differs sharply by idea on the weighted task: BFS-style programs pass on 3 of 71 samples because hop-order expansion is wrong under weights, and even Dijkstra passes only about half the time, failing on edge cases (failing Dijkstra programs are correct on a mean of 33% of the 50 graphs). Any knob that moves mass from Dijkstra toward BFS on this task will raise idea entropy and lower the pass rate at the same time. The planned screening assumption that at least 3 idea classes reach 3% on at least 2 tasks fails here: both tasks have exactly two classes above 3%. The plan's narrow-menu fallback (keep the task, report the narrow menu) applied.

## 1.5 Classifier audit

A stratified sample of 200 programs was labelled blind by the judge. Agreement is 0.715 and Cohen's kappa [10] is 0.684, above the pre-registered 0.6 threshold, so the rule labels stand. The main confusions are a rule label of SPFA against a judge label of BFS (12 programs: queue relaxation without in-queue tracking) and a rule label of greedy best-first search against a judge label of Dijkstra (6). The menu classes themselves are labelled consistently: BFS 20/23, DFS 22/22 and Dijkstra 25/26 rule labels match the judge.

Table 2. Classifier audit: rule label (rows) against blind judge label (columns), {{audit_stats}}.

{{audit}}

## 1.6 Locating the choice: probes at the first tokens see nothing, so the late-window fallback was used

The plan chose the intervention band by cross-validated multinomial probes for the final idea at the prompt-final token and the first 8 generated tokens. Two facts defeated that plan [ARTIFACT:art_aSN7z8WuA7Ir]. First, prefill is deterministic, so the prompt-final residual is identical for all samples of a task; a within-task probe there sits at the majority baseline by construction. Second, the first 8 generated tokens are boilerplate (an opening of the form `Certainly! Below is ...`). Probes on generated tokens 1 to 6 return a pooled balanced accuracy of 0.429 to 0.433 at every layer from 1 to 36, and tokens 7 and 8 (alone or averaged with the earlier ones) reach only 0.45 to 0.47. The value 0.433 is exactly the balanced accuracy of predicting each task's majority idea (BFS recall 205/276 = 0.743, Dijkstra recall 225/227 = 0.991, DFS and the rare class 0, mean 0.433): the early tokens carry task identity and nothing about which idea the sample will implement.

The algorithm name, where it appears at all, comes much later. Only 136 of 300 open-task and 152 of 300 weighted-task generations contain an explicit algorithm name anywhere in the text; among those, the first mention never falls within 8 tokens and has a median position of 23.5 tokens on the open task and 46.5 on the weighted task.

Table 3. Position of the first explicit algorithm name in baseline generations (token index after the assistant turn starts).

{{mention}}

The plan's pre-registered fallback for chance-level early probes, which we call the late-window fallback, therefore applied: probes were trained on the mean residual over gen1..32, and the hook window was widened to the prompt-final token plus gen1..64. On that feature the probe reaches a pooled balanced accuracy of 0.638 to 0.713 across layers, against 0.392 to 0.429 for within-task shuffled labels (a control-task baseline in the sense of [9]). The curve is flat across depth: layer 0 already gives 0.648. A flat curve that is high from the embedding layer onward is what a readout of name and data-structure tokens inside the window would produce; it is not evidence of an early plan. The band rule picked layers 29 to 31 (mean gap over shuffled 0.282).

[FIGURE:fig_probe]

Table 4. Per-layer idea probes (5-fold CV, logistic regression with C chosen per layer). The gen1-only, gen8-only and mean(gen1..8) columns are the original plan's features; the mean(gen1..32) columns are the late-window feature actually used.

{{probe}}

What this settles for the hypothesis is limited but real. In this model and protocol, no linear readout at the prompt-final token or the first 8 generated tokens predicts the idea. The idea becomes decodable only once the 32-token window includes the explanatory preamble, which places the commitment token, if there is a single one, somewhere after token 8. Whether it precedes the first mention of the algorithm's name cannot be read from these data. Forking-path resampling, which would locate it per sample, belonged to the temperature arm and did not run.

## 1.7 Building the intervention vectors, with offline checks

All vectors were built from the baseline only, at layers 29 to 31. Three checks were run before any steered generation.

*The two flattening directions are nearly orthogonal.* The probe-weight direction and the difference-in-means direction have cosine 0.16 to 0.23, so the two flattening variants are different interventions, not two estimates of one.

Table 5. Cosine between the probe-weight and difference-in-means flattening directions.

{{hcos}}

*LEACE [8] erases idea information offline; rank-1 projection nearly does.* On cached activations, a fresh probe for the menu label reaches a balanced accuracy of 0.58 to 0.61 on the open task and 0.88 to 0.89 on the weighted task before erasure. After LEACE it reaches 0.20 and 0.33 to 0.35 (chance is 0.33); after rank-1 projection, 0.32 to 0.34. The menu-centroid subspace is effectively one-dimensional: the second singular value of the centred centroid matrix is about 6 times smaller than the first on the open task and 56 to 61 times smaller on the weighted task.

Table 6. Offline erasure check: balanced accuracy of a fresh 5-fold probe for the menu label (menu classes plus a pooled class for everything else) before and after erasure.

{{leace}}

Table 7. Singular values of the centred menu-centroid matrix (k = 2 menu classes, so the rank is at most 1).

{{svd}}

*The cross-task novelty direction transfers as a readout.* Extracted from sorting, substring search, primality testing, string compression and matrix multiplication prompts only, the direction separates novel-request from plain prompts on held-out path-search and weighted-path prompts with AUROC 1.0 at all three layers. Leave-one-task-out directions have cosine 0.92 to 0.98 with each held-out task's own difference vector. The direction is close to orthogonal to both flattening directions and to the erasure subspace (absolute cosines at most 0.095).

Table 8. Cross-task novelty direction: transfer and overlap checks.

{{a4vec}}

## 1.8 Strength calibration

Strengths for the three additive knobs were calibrated on the open task with n = 20 per point over a grid of 10 values. The lower bound is the largest grid value with pass at least 0.95x baseline, the upper bound the smallest larger value with pass at most 0.40x baseline, and five strengths are spaced geometrically between them. The calibration was frozen before the full run and reused for the weighted task and the random controls. The calibration rows already show what the full sweep confirms: both flattening directions convert the open task to DFS well before they break code (difference-in-means at α = 0.2 gives DFS 19 of 20), and the probe-weight direction keeps pass near baseline up to α = 0.75 only because its samples are almost all DFS.

Table 9. Strength calibration on the open task (n = 20 per row).

{{calib}}

## 1.9 Main sweep: practitioner knobs

The sweep used seeds 0..149 for every method setting and seeds 0..74 for random controls (n = 150 and 75 per task). Table 10 holds the knobs a practitioner would reach for [ARTIFACT:art_aSN7z8WuA7Ir]. Three results stand out.

First, temperature buys almost no idea diversity before it breaks the code. Between T = 0.7 and T = 1.0 idea entropy rises from 1.175 to 1.278 bits on the open task and from 0.916 to 1.165 on the weighted task, while the weighted-task pass rate falls from 0.380 to 0.233. T = 1.0 misses pooled eligibility by 0.006 (0.423 against 0.429), so the best eligible temperature is T = 0.7 itself. At T = 1.3 a quarter to a third of outputs are syntax errors, at T = 1.6 almost all are, and at T = 2.0 one output in 300 contains a parseable program. Top-k = 10 at T = 1.6 keeps most outputs parseable but the pass rate is still 0.227 and 0.040. Across all temperatures the same two menu ideas dominate the outputs that parse; no temperature introduced a third idea class above 5% of samples.

[FIGURE:fig_temp]

Second, the top-3 ban is largely ignored. On the open task, 142 of 150 programs (0.947) still implement a banned idea, and the ban only evens BFS and DFS out (70/70), which raises entropy from 1.175 to 1.404 bits. On the weighted task 131 of 150 (0.873) still implement Dijkstra, BFS or SPFA; the ban shifts mass from Dijkstra to BFS (from 111/37 to 62/66), which raises entropy to 1.779 bits and drops the pass rate from 0.380 to 0.153, because BFS-style programs fail on weighted graphs. Small amounts of Bellman-Ford (7) and Floyd-Warshall (3) appear. The entropy gain from the ban on the weighted task is mostly a move toward the incorrect menu idea. Non-compliance with negative instructions is a known failure: naming a forbidden item can prime it [5]. The artifact also rendered a PCA view of layer-30 window activations with per-idea centroids for the baseline, the ban and the best projection setting. It is not reproduced here, because its coordinates were not written to the results files, and it is not the planned manifold analysis, which belonged to the ban arm.

Third, the novelty prompts split. The new-algorithm prompt leaves the pooled numbers almost unchanged (pass 0.553, entropy 1.053) but moves the two tasks in opposite directions: more DFS, A* and Dijkstra on the open task (entropy 1.533), and more Dijkstra on the weighted task (137 of 150; entropy 0.573, pass 0.547, the highest weighted-task pass rate in the sweep; the held-out re-draw gives 0.580). The 2000-word novelty prompt raises entropy to 2.205 bits pooled but collapses the pass rate to 0.083, with 39 and 64 syntax errors. Generate-then-select gives the highest entropy of all (2.561 pooled; 9 idea classes on each task) at pass 0.263: listing approaches first does put A*, bidirectional, IDDFS, Bellman-Ford and Floyd-Warshall into the outputs, but these implementations fail the oracle more often.

Table 10. Practitioner knobs and noise-floor rerun (sweep seeds 0..149).

{{s_pract}}

Table 11 lists what the generate-then-select pipeline chose in stage 1. The picked names are far more varied than what the model writes unprompted; on the weighted task they include the Johnson, Kruskal and Prim algorithms (the last two are minimum-spanning-tree methods, not shortest-path methods), A* search and Bellman-Ford.

Table 11. Generate-then-select, stage 1: items picked by the seeded RNG from the 10-item lists the model wrote itself (possessive apostrophes dropped from item names).

{{gts}}

## 1.10 Main sweep: internal knobs

**Flattening directions.** Neither flattening direction flattens [ARTIFACT:art_aSN7z8WuA7Ir]. The difference-in-means direction at α = 0.224 turns the open task into DFS on 145 of 150 samples (baseline BFS 98, DFS 44) at an unchanged pass rate (0.680 against 0.673); at α = 0.106 it already gives DFS 126. Idea entropy therefore falls, to 0.235 bits. The probe-weight direction does the same at α = 0.75 (DFS 148 of 150) at a lower pass rate (0.580). On the weighted task the same directions push Dijkstra toward BFS: at α = 0.224 the split is 77/60 against 111/37 at baseline, entropy rises to 1.444 bits, and the pass rate falls to 0.287 because more programs are BFS. With only two menu ideas, a direction that points from the mode toward the mean of the menu overshoots the uniform point and selects the minority idea. At the top strengths both directions destroy the output: the difference-in-means direction at α = 1.0 leaves 148 of 150 open-task samples with no code or a syntax error, the probe-weight direction at α = 1.5 leaves 125.

Table 12. Flattening directions (rows marked post hoc are excluded from survival).

{{s_H}}

[FIGURE:fig_select]

**Menu erasure.** Rank-1 projection and LEACE leave the open-task distribution close to baseline and the weighted task more Dijkstra-heavy, at pass rates near baseline. LEACE at a = 1.0 gives open-task BFS 117 and weighted-task Dijkstra 127; rank-1 projection at a = 0.25 evens the open task (DFS 75, BFS 73) and raises weighted-task BFS to 47. No erasure setting produced a single passing program outside the known classes that the judge accepted as novel. Rank-1 projection at a = 0.5 and above produced 17 to 23 syntax errors on the open task.

Table 13. Menu erasure.

{{s_A3}}

**Cross-task novelty direction.** This is the internal knob with the clearest effect on diversity. At α = 0.356 the open task shows 7 idea classes (DFS 76, BFS 51, A* 9, Dijkstra 6, other 5, greedy best-first 2, bidirectional 1) and entropy 1.750 bits, at pass 0.560, just at the per-task eligibility line. The weighted task barely moves (entropy 0.984). At α = 2.0 about 15% of outputs contain no code.

Table 14. Cross-task novelty direction.

{{s_A4}}

**Random controls.** Matched-norm random directions and random projections produce entropy changes of the same size as the targeted knobs. Several random settings reach higher pooled entropy than any targeted internal setting at comparable pass rate (draw 2 at α = 1.12: 1.407 bits at pass 0.467; draw 2 at α = 1.0: 1.370 at 0.487), and the random draws disagree with each other in direction: draw 1 tends toward DFS on the open task and draw 0 toward BFS on the weighted task.

Table 15. Random controls (n = 75 per task).

{{s_ctrl}}

Table 16 carries the secondary metrics for every method setting: off-menu correct share, atypicality, degeneration, flip rate against the same-seed baseline sample, the order-1 Hill number, idea entropy among passing programs only, and phrasing diversity (mean normalised edit distance among up to 25 programs of the modal idea). Two regularities are worth stating. Phrasing diversity within the modal idea stays between 0.39 and 0.67 in every setting and rises with temperature (0.503 at T = 0.7 to 0.599 at T = 1.3 on the open task), while idea entropy rises little (1.175 to 1.288 bits). Read against the user's cases, this is closer to (a), more phrasings of the same two ideas, than to (b). It rests on two temperature points that still produce code and one phrasing measure; the dedicated ideas-versus-phrasings partition belonged to the temperature arm. And on the weighted task the entropy among passing programs is 0 in many settings: whatever the knob does to the idea mix, the programs that pass are nearly all Dijkstra.

Table 16. Secondary metrics for every method setting (sweep).

{{x_main}}

Table 17. Secondary metrics for random controls and the held-out draw.

{{x_ctrl}}

## 1.11 Pareto fronts across all settings

The figure below places every setting on the pooled pass-rate and idea-entropy plane. Above the eligibility line the front, in order of rising entropy, runs through the difference-in-means direction at α = 0.05, the cross-task novelty direction at α = 0.2 and 0.356, and the top-3 ban; generate-then-select extends it below the line. The ban is the eligible setting with the highest entropy (1.591 bits at pass 0.430), and the best internal setting (the novelty direction at α = 0.356: 1.367 at 0.467) sits below it. Seven random-control settings would join the entropy front if controls were allowed on it.

[FIGURE:fig_pareto]

Table 18. Pareto fronts (pass, metric) for each objective, with the random controls that would join them.

{{pareto}}

Table 19. Ten highest-entropy eligible settings (pooled). Five of the ten are random controls.

{{entrank}}

## 1.12 Selection, held-out draw and survival verdicts

The selection step picked, among eligible settings on indices 0..99, the difference-in-means direction at α = 0.05 (highest entropy), rank-1 projection at a = 0.25 and LEACE at a = 0.5 (on the novel-and-correct share, all tied at 0, broken by off-menu share and entropy). The probe-weight direction had no eligible setting. The best eligible temperature was T = 0.7. These were re-drawn on fresh seeds 1000..1099 with their matched controls.

Table 20. Held-out draw, seeds 1000..1099 (n = 100 per task).

{{s_ho}}

On the held-out draw the difference-in-means direction gives 0.93x the entropy of the held-out T = 0.7 draw on the open task and 1.20x on the weighted task, against a required 2x, and its CI against the random direction includes 0 on both tasks. Nothing survives [ARTIFACT:art_aSN7z8WuA7Ir].

Table 21. Pre-registered survival verdicts.

{{survival}}

Table 22. Targeted additive settings against the pooled random directions at the same strength (unpaired bootstrap; * = CI excludes 0).

{{knobrand}}

The cross-task novelty direction fails its own test in an instructive way. Atypicality rises from α = 0 to 0.632 on the open task (0.835 to 1.675) and then falls back (1.064 at α = 2.0); on the weighted task it never rises consistently. The rule required Spearman at least 0.8 on both tasks; the values are 0.486 and −0.257. At the top strength the direction is less atypical than random directions on the weighted task (CI excludes 0 in the wrong direction).

[FIGURE:fig_a4]

Table 23. Cross-task novelty direction: dose-response used by the survival rule (α = 0 is the baseline).

{{a4dose}}

## 1.13 Manipulation checks: the steering does what it was built to do internally, and the output follows only partly

Baseline probes (trained on unsteered mean(gen1..32) residuals) were applied to the residuals captured during steered generation, at layer 30 (band middle) and layer 33 (downstream). Two quantities are reported: the probe menu entropy, defined as the entropy of the probe softmax restricted to the menu, and the probe decodability, defined as the balanced accuracy with which the probe predicts the realised idea of each steered sample. For the flattening directions the probe menu entropy goes to 0.000 bits at every strength from α = 0.224 (difference-in-means; from α = 0.106 on the open task) and at every probe-weight strength: the steered state reads as one idea with full confidence, the opposite of flattening, and consistent with the DFS takeover in the outputs. For erasure, probe decodability drops to 0.27 to 0.44 at full strength (unsteered rerun: 0.48 and 0.57), yet the outputs remain BFS, DFS and Dijkstra. The internal readout can be erased without the behaviour changing.

Table 24. Manipulation checks with baseline probes on steered residuals (unsteered reference rows first).

{{manip}}

## 1.14 Novelty: the judge found no novel correct program in any condition

Every distinct passing program in the catch-all class of the classifier, across the sweep and the held-out draw, was sent to the judge: 70 programs [ARTIFACT:art_aSN7z8WuA7Ir]. All 70 were judged to be known algorithms, most often Dijkstra written in an unusual way (41). The judge-confirmed novel-and-correct share is therefore 0 in every condition, including generate-then-select and the 2000-word novelty prompt. Over all {{judge_n}} judge calls (audit plus novelty checks) the verdicts were: {{judge_all}}. Judge spend was $0.081 against a $1.5 cap.

Table 25. Judge verdicts on the 70 distinct passing programs in the catch-all class of the classifier.

{{judge}}

## 1.15 Noise floor and independent verification

Regenerating the baseline in differently composed batches flips 16.7% of open-task and 10.7% of weighted-task idea labels at the same seeds (the noise-floor rerun row in Table 10), because bf16 numerics depend on batch composition. Common random numbers therefore pair conditions only approximately, and the per-sample flip rates in Tables 16 and 17 have a floor of roughly 0.11 to 0.17. An independent re-derivation script, with its own oracle runner, a coarse independent classifier and a separate recomputation of every metric, reproduces the stored numbers. The placebo test also shows that the bootstrap CIs are somewhat anticonservative: random splits of the baseline produce a CI excluding 0 at a rate of 0.10 and 0.15 instead of 0.05, which matters for any claim resting on a CI that barely excludes 0. None of the iteration's verdicts rests on such a claim, because nothing came close to the survival margins.

Table 26. Independent verification and placebo checks.

{{verify}}

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
