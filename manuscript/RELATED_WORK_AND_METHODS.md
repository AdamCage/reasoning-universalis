# Observable Reasoning Prefixes Under Model Holdout

## Research question

We study whether ordered features of externally visible reasoning text add information about final-answer correctness beyond task attributes, lexical content, and simpler text statistics. The evaluation withholds both a target model and its test-task roots from fitting. This separates transfer to a new model on new task instances from prediction on tasks already represented in training.

The object is the text returned through a reasoning channel, measured by a specified representation operator. It is not a direct observation of internal computation. The study is an exploratory predictive pilot within the broader Reasoning Universalis program. It uses no functional-state labels and does not establish shared cognitive states, faithful reasoning, harmful overthinking, or a causal benefit from stopping. The original H0–H7 hypotheses retain their meanings; the independent human-reference measurement gate E0 remains unpassed.

## Related work

Reasoning-state abstraction already has close precedents. Yu et al. represent steps through spectral features, cluster them, and analyze Markov transitions [1]. Shahariar et al. combine a six-state abstraction with activation steering [2]. These studies preclude treating a state graph alone as a contribution. Our narrower question concerns the incremental predictive information obtained from an external text measurement under explicit controls.

Temporal prediction is also established. Chrabąszcz et al. extract trajectories from hidden-state probes and distinguish in-distribution separability from transfer [3]. Their revised analysis reports that evaluation-distribution fitting and classifier selection changed earlier transfer conclusions. Harrasse et al. study activation-derived regimes with correctness and temporal controls, including permutation before dynamics fitting, and examine interventions [4]. The present pilot instead uses observed text; this difference does not establish superiority or validate text geometry as a functional ontology.

Prediction and intervention require separate evidence. Dong, Qin and Shah compare stopping policies at matched lost-correct risk while accounting for probe and serving overhead [5]. An observational gain here cannot establish deployable savings. Liu et al. evaluate CoT pathologies using interventions and model organisms, while noting family-dependent intervention shifts and limits of the healthy-reference assumption [6]. Repetitive or unusual text alone therefore does not diagnose pathology. The same-owner Semantic Afterlife audit supplies lessons about repetition, missingness and measurement sensitivity, rather than independent support for this cohort [7].

## Tasks and operational collection

The prospective corpus contains 96 main tasks grouped into 48 paired roots. Four domains—exact arithmetic, CNF satisfiability, topological ordering and bounded grid planning—contribute 24 tasks each. The fixed split contains 48 training, 16 validation and 32 test tasks. Four additional admission tasks are excluded from predictive evaluation. Root pairs, repeated generations and observations from different models retain the same split. Canonical instance checks reject exact normalized duplicates, but do not prove absence of algebraic equivalence or graph isomorphism. Named generator variants are not certified independent task families, and input-size difficulty schedules are not calibrated measures of model difficulty.

Correctness is determined by a separate versioned verifier: arithmetic recomputation, exhaustive Boolean assignments, independent topological search, or bounded planning with full simulation. Responses require a final nonempty `ANSWER:` line. Unparseable answers and unavailable grading are recorded explicitly. Task feasibility is distinct from model-answer correctness; balancing feasible and infeasible instances does not balance the model's outcomes. The verifier and its source hash accompany the observations.

The candidate model identities are Qwen3-32B, DeepSeek-V4.1-Flash and GPT-OSS-20B, accessed through RouterAI. Candidates are not automatically admitted or replaced. Operational admission requires the exact returned model and provider, a completed exposed reasoning channel, and no summary-only, encrypted or truncated substitute. The admitted route is pinned without fallback; subsequent drift is retained as an exclusion. Admission is an access check, not proof of complete or faithful internal reasoning. Unknown weight revisions, quantization and execution details remain unknown.

The local v2 plan permits two samples per task, temperature 0.7, top-p 0.95 and at most 4096 output tokens. Its maximum concurrency is three and automatic retries are disabled. A deterministic task queue preserves planned root/model/sample coverage; partial collection is reported without outcome-based selection. Raw requests, responses, failure statuses, identities and accounting survive unsuccessful attempts. Pricing is reserved before dispatch using conservative explicit rates. The total authorized ceiling is 3000 RUB including 246.7988793802352 RUB in historical charged-or-reserved obligations, with 100 RUB separated from the generation ceiling for embeddings. These are accounting limits, not a claim that the full allocation was executed.

## Observable prefixes and representation

Predictor inputs contain the reasoning channel only, censored before the first `ANSWER:` marker. Budgets are 128, 256 and 512 Unicode non-whitespace spans, termed *whitespace words*. They are not model-native tokens or percentages of eventual completion length. Each prefix consists of exact consecutive 16-word chunks with original character offsets and input hashes. Construction uses no future total length or final-answer text.

Eligibility requires a completed, gradeable observation that reaches the requested budget. Short traces are not padded. Semantic analysis additionally requires valid embeddings for every exact chunk. Consequently the estimand conditions on completion, grading, prefix availability and, where applicable, embedding availability. These conditions may depend on correctness or model identity. Coverage and class counts must therefore accompany performance by model, domain, split and outcome; the eligible sample does not represent all attempted queries automatically.

The lexical representation uses unigram TF-IDF. Semantic representations are BGE-M3, requiring 1024 dimensions, and Qwen3-Embedding-8B, permitting up to 4096 dimensions with a constant admitted dimension. Each chunk is embedded alone, without later context. Returned identity, nonzero finite vectors, exact text, character boundaries and hashes are checked. Raw provenance binds these checks to the external responses, although a returned identifier cannot independently establish backend weights.

TF-IDF vocabulary and inverse-document frequencies are fitted only on source training prefixes. Chunks containing no source-vocabulary terms remain zero vectors; they are neither filled from target data nor silently excluded. Each fold reports their frequency and the number of affected or entirely zero traces. The implementation's zero-vector cosine convention can influence lexical geometry, so out-of-vocabulary coverage is a measurement limitation, not a semantic similarity claim. Valid semantic zero vectors are rejected separately.

## Predictors and model holdout

For each target identity, source training roots from the other models fit the representation and classifier. Source validation roots select regularization; the target is evaluated on its test roots. Test roots are absent from training and validation across all models. Vocabulary, numeric scaling, category encoding and classifier fitting exclude the target model. This is checkpoint or model holdout. A family-generalization interpretation additionally requires evidence that no related training lineage remains among the sources; model names alone cannot establish that independence. The test roots are new instances of the programmed distributions, not an unseen benchmark.

Three nested predictors use root-balanced training weights. The metadata predictor includes domain/difficulty encoding and seven surface statistics: character length, digit and punctuation rates, newline rate, type-token ratio, and fixed uncertainty/correction lexicon rates. The static predictor adds source-trained prefix TF-IDF and mean chunk content. In the semantic analysis it also adds the mean normalized semantic vector **and observed lexical-path geometry**. The dynamic predictor then adds semantic-path features. Thus the semantic contrast tests semantic geometry beyond lexical dynamics and pooled content; “static” does not mean that all temporal features are absent. In the lexical experiment, the dynamic addition concerns TF-IDF geometry alone.

The eleven geometric summaries are adjacent cosine-distance mean, standard deviation and slope; mean lag-two distance; endpoint cosine distance; Euclidean endpoint displacement divided by path length; mean cosine between consecutive increments; the fraction of nonadjacent pairs within cosine distance 0.1; mean nearest nonadjacent past distance; early-versus-late centroid distance; and the slope of distance from the initial chunk. They are descriptive path statistics rather than validated reasoning phases. Vectors are row-normalized, and slopes use equally spaced normalized chunk positions.

Each predictor uses logistic regression with regularization selected from C = 0.01, 0.1 and 1.0 by equal-root source-validation log loss. Fitting is repeated on the source training data at the chosen C, without adding validation observations. A one-class training sample uses an explicitly flagged, smoothed constant predictor. A one-class target has undefined AUROC, retained as missing. Empty training, validation or test subsets yield an unavailable fold rather than a successful evaluation. Per-fold manifests record fit roots/models, vocabulary, scaling, selected regularization and predictions.

## Estimands and uncertainty

The principal reported comparison is static-minus-dynamic binary log loss at 256 words with BGE-M3, separately for every held-out model. For each original test root, paired loss differences are averaged over its eligible attempts; these root means then receive equal weight. Positive gain favors the dynamic addition. Brier improvement, AUROC, other prefix budgets, Qwen embeddings, lexical geometry and pooled summaries are secondary exploratory outputs. All target-specific contrasts are retained, because pooling can hide opposite model effects.

The default uncertainty calculation draws 2000 bootstrap samples of the original root means with replacement and reports percentile 95% intervals. A root drawn multiple times contributes with its multiplicity; it is not relabeled as a new independent task. Repeats and model observations within a root remain dependent. One root permits a descriptive point estimate but no estimated between-root interval.

Intervals are pointwise and conditional on the fitted predictors and observed cohort. They omit uncertainty from training, regularization selection, model-population sampling and backend identity. The matrix is exploratory, without confirmatory multiplicity-adjusted inference. An interval containing zero neither accepts H0 nor establishes practical equivalence; an equivalence claim would require a justified prospective region and sufficient precision.

## Order and measurement controls

Controls reverse the chunk order or apply three deterministic within-trace permutations with seeds 104729, 130363 and 155921. Each preserves chunk content/count and pooled static information. The affected source pipeline is refitted, regularization is selected on source validation, and the corresponding transformed target paths are evaluated. Shuffling only test inputs would introduce a different distribution shift and is not the control used here. For semantic analysis, observed lexical geometry stays in the baseline while the added semantic geometry changes order.

Direct contrasts pair each refitted control's dynamic loss with observed-order dynamic loss on the same trace/root, then use equal-root aggregation and root uncertainty. Positive values favor observed order. Separate static-to-dynamic intervals under two orders do not test their difference. The three shuffle results are reported separately, not treated as independent replications.

The primary BGE population remains unchanged by alternate-embedder availability. Supplementary matched analyses intersect exact eligible trace/prefix identities **before** all training, validation and test fitting, refit each pipeline on that common population, and report exclusions. This isolates a comparison on observed common support; it does not recover missing embeddings or remove selection bias. Agreement between operators is a robustness check, not human construct validation.

## Reproducibility and interpretation

The record links the prospective local plan, tasks, source snapshots, route admissions, all attempts, raw outputs, ledger, dependencies, predictions and controls through hashes. Analysis version `observable-prefix-transfer-v1.1` implements the procedures above. A separate pinned EpistemeOS adapter checks the declared evidence inventory and offline recomputation. Mechanical stage completion leaves scientific validity unassessed and review unrequested; it does not certify collection completeness, statistical correctness or human approval.

The strongest conclusion available is about incremental prediction in the tested eligible population. It remains limited by a small programmed task distribution, identity uncertainty, selection into sufficiently long completed traces, out-of-vocabulary behavior and conditional intervals. A causal stopping benefit requires a further controlled intervention with complete cost accounting. All numerical conclusions must be tied to saved results and their actual denominators.

## References

1. Yu et al. *Explainable Chain-of-Thought Reasoning: An Empirical Analysis on State-Aware Reasoning Dynamics*. [arXiv:2509.00190v2](https://arxiv.org/abs/2509.00190v2).
2. Shahariar et al. *Modeling Hierarchical Thinking in Large Reasoning Models*. [arXiv:2510.22437v2](https://arxiv.org/abs/2510.22437v2).
3. Chrabąszcz et al. *Monitoring the Internal Monologue: Probe Trajectories Reveal Reasoning Dynamics*. [arXiv:2605.18549v2](https://arxiv.org/html/2605.18549v2), especially sections 2–3.3 and Appendix O.
4. Harrasse et al. *Reasoning Fine-Tuning Induces Persistent Latent Policy States*. [arXiv:2607.18532v1](https://arxiv.org/html/2607.18532v1), especially sections 5.2/8 and Appendix E.2.
5. Dong, Qin and Shah. *When Does Learning to Stop Help? A Cost-Aware Study of Early Exits in Reasoning Models*. [arXiv:2606.30852v2](https://arxiv.org/abs/2606.30852v2).
6. Liu et al. *Diagnosing Pathological Chain-of-Thought in Reasoning Models*. [arXiv:2602.13904v2](https://arxiv.org/html/2602.13904v2), especially sections 3 and 6.
7. Reasoning Universalis. [Semantic Afterlife transfer audit](../reports/SEMANTIC_AFTERLIFE_TRANSFER.md), 8 November 2026; same-owner source audit, not independent replication.

Implementation and plan: [local pilot v2](../design/LOCAL_PILOT_2026_11_08.json), [analysis source](../resumption/analysis.py), [analysis contract](../resumption/ANALYSIS.md), [generator audit](../reports/GENERATOR_AUDIT_2026_11_08.md), [local preflight](../reports/LOCAL_PREFLIGHT.md).
