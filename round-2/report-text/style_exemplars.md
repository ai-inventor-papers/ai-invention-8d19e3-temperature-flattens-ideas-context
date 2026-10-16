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
