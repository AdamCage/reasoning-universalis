# Manuscript and portfolio preparation

Prepared on 8 November 2026 for the local exploratory study. These notes supply an evidence-dependent manuscript structure and portfolio outline. They contain no new cohort result, human review, or application response. The governing plan is [the resumption protocol](../design/RESUMPTION_PROTOCOL_2026_11_08.json); the estimand and implemented analysis are described in [ANALYSIS.md](../resumption/ANALYSIS.md).

## Recommended title and research question

**Observable Reasoning Prefixes Under Model Holdout: A Controlled Pilot of Text Trajectory Features**

Does the ordered geometry of a fixed, externally observable reasoning prefix improve prediction of independently verified answer correctness over task, surface-text, lexical-path, and pooled-content controls when the target model and test roots are excluded from fitting?

Use “model holdout” or “checkpoint holdout” unless independent training-family ancestry is established for the actual admitted cohort. New roots from the same programmed distributions do not establish transfer to a new benchmark or task family. The pilot tests a restricted predictive component related to H7. It does not complete H7's stopping intervention or establish H1's functional states. H0–H7 retain their original specification meanings, and E0 remains unpassed.

If model collection fails or fewer than two models are admitted, use **Auditing a Reproducible Pilot of Observable Reasoning Prefixes** and identify the deliverable as a methodological and infrastructure report. Empty contrasts are “not estimated,” never zero.

## Manuscript outline

### Abstract

Use a short six-part abstract: the predictive question; observed-text object; actual admitted models and independent test roots; source-only fit and matched order controls; the predeclared BGE-M3/256-word result by target with intervals; the most consequential limitation. Substitute actual coverage and measured effects only after reading saved analysis outputs. Do not insert the planned 576 requests as an achieved sample size. Infrastructure-only results require an infrastructure abstract.

Suggested opening: “We study whether trajectory features of externally visible reasoning text carry information about final-answer correctness beyond static content and surface signals under model holdout.” The result sentence must state the point estimate, uncertainty and eligible population, including an uninformative or opposite result.

### Introduction

Externally visible reasoning is an accessible monitoring channel, but predictive structure may reflect task mix, length, lexical repetition, or the measurement operator. Our narrow test asks whether a specified text-geometry feature set contributes information after these alternatives are represented in the baseline. The contribution is the controlled estimate and its failure boundaries, supported by executable artifacts; a new geometric feature or state diagram alone is insufficient.

Explain safety relevance as monitor reliability under a change of model identity. Correctness prediction on these tasks does not evaluate deception, harmful intent, alignment, adversarial adaptation, or internal computation. Temporal monitors and controlled state dynamics already have close predecessors; use the source distinctions below.

### Related work

Organize around three comparisons: state abstraction and dynamics; temporal prediction and generalization; prediction versus intervention. Keep external text, hidden activations, and behavioral outcomes separate. The reviewed Semantic Afterlife project motivates repetition diagnostics, explicit missingness and measurement sensitivity. It is a same-owner predecessor and an audit source, not independent replication of Reasoning Universalis.

### Study design and task audit

The prospective corpus has **96 main tasks paired into 48 roots**, with 48 train, 16 validation and 32 test tasks. There are also **four separate admission tasks**, excluded from prediction. The four main domains each contain 24 tasks. Cite the final corpus file and its hash, and record any reduced prospective corpus separately. The manifest's main-task count does not include admission tasks.

The programmed domains cover exact arithmetic, CNF satisfiability, topological ordering and grid planning, with a separate versioned verifier. Report the implemented response parser and handling of malformed answers. “Feasibility-balanced” applies to the search-domain task construction; it does not mean balanced model correctness. Input-size schedules are not calibrated human difficulty. Canonical deduplication excludes exact normalized repeats without proving absence of algebraic or isomorphic equivalents. Explain root pairing as a dependence group throughout fitting and uncertainty.

Describe historical audit failures with their own denominators and source artifacts. They motivate the new versioned verifier; they are not performance measurements of the new model cohort.

### Collection and observable prefixes

List requested and returned model IDs, routes, available revisions, inference parameters, timestamps, prices, and operational admission outcomes. A completed exposed reasoning channel is the observed text. Neither a provider flag nor operational admission establishes complete or faithful internal reasoning. Keep failed, truncated, summary-only and route-drift attempts in the registry and coverage table.

Prefixes contain 128, 256 or 512 Unicode non-whitespace spans, called **whitespace words** throughout the manuscript; these are not tokenizer tokens. Each is divided into exact consecutive 16-word chunks. Predictor inputs stop before the first `ANSWER:` marker. Prefix construction uses no future total length. Eligibility still requires an observed completed trace to reach that prefix; consequently reported performance conditions on completion, grading and prefix/embedding availability.

### Predictors and source-only fitting

For each target model, train on other models' training roots and select logistic regularization from the fixed grid using source validation roots. Do not refit on validation. The target model is excluded from vocabulary, scaling, encoding, hyperparameter selection and classifier fitting; the target test roots are absent from fitting across all models.

Describe the nesting of baselines clearly. All predictors use domain/difficulty and observed surface features. The static predictor adds source-trained unigram TF-IDF and order-invariant pooled chunk content. In the semantic experiment it also includes observed lexical-path geometry. The dynamic predictor adds eleven summaries of semantic trajectory geometry. Therefore the semantic contrast estimates incremental value beyond a lexical-dynamics baseline, not “all dynamics versus no dynamics.” The lexical experiment uses TF-IDF chunk geometry and supports lexical claims only.

List the eleven features with their exact implementation definitions or refer to a source-linked appendix. Do not rename them validated semantic roles, cognitive phases or macro-states. BGE-M3 and Qwen3-Embedding-8B remain separate measurement operators; compare conclusions on common eligible trace/prefix IDs before attributing a difference to the embedder.

### Estimand and uncertainty

For target model m and eligible test root r, let d_r be the mean static-minus-dynamic binary log-loss difference over that root's eligible attempts. The reported gain is the equal-root mean of d_r. Positive gain favors the dynamic addition. Bootstrap the original root-level differences with replacement and preserve draw multiplicity. Repeated generations, task variants, prefixes and source-target folds are not independent roots.

The primary reporting matrix is **BGE-M3 at 256 words, separately for every held-out model**. Other budgets, the alternate embedder, lexical geometry, Brier, AUROC and pooled summaries are secondary exploratory outputs. State the actual bootstrap replicate count and interval level from the analysis artifact. The intervals are descriptive, pointwise, and conditional on fitted predictors and the observed cohort. They omit training, hyperparameter-selection and model-population uncertainty. They are not confirmatory p-values or equivalence tests. A one-class target has undefined AUROC; retain `null` and report class counts.

### Order controls

Reverse order and the three fixed within-trace permutations preserve chunk content/count and pooled static content. Refit each affected source pipeline, select its regularization on source validation, and evaluate the corresponding transformed target paths. In the semantic analysis the observed lexical-path baseline remains fixed while the semantic order is changed.

The decisive order comparison is **control dynamic loss minus observed-order dynamic loss on the same trace/root**, then equal-root aggregation and a paired root interval. Positive values favor observed order. Show all three permutation seeds separately. A positive static-to-dynamic interval under observed order and an overlapping/zero interval under a shuffle do not test the difference between orders. Order controls localize dependence on the chosen ordering; they do not establish causal reasoning mechanisms.

### Results

Present coverage before predictive performance. Include the planned count, attempted count, completed visible-channel count, gradeable count, sufficient-prefix count and verified-embedding count by model, split, domain and correctness. Show missingness as an outcome because eligibility may depend on model or correctness.

Then present every model-specific BGE/256 contrast with static and dynamic log loss, paired gain, interval, roots, traces and class counts. Follow it with direct observed-versus-control contrasts and common-sample embedder sensitivity. Report unavailable folds and constant-predictor fallbacks alongside other folds. Use pooled results only as additional evidence; they can hide opposite effects across models.

### Discussion and limitations

Interpret the actual sign, interval width and controls rather than selecting a favored narrative. The core limitations are a small programmed task distribution; model/provider identity uncertainty; completion/prefix selection; sparse or single-class outcomes; conditional uncertainty; no independent human construct validation; and no prospective stopping intervention. Strong predictive transfer would be evidence for this observable feature set in this setting. It would not establish universal internal dynamics or complete H7 support.

A gain compatible with zero is inconclusive about a small benefit unless a justified equivalence region and sufficient precision were fixed in advance. Failure to improve a specified baseline does not prove that every apparent dynamic effect is caused by the baseline's nuisance variables. If controls perform comparably or better, report that order-specific incremental value was not established under the tested pipeline.

### Reproducibility and contributions

Release protocol/corpus/source hashes, all attempts, cleaned raw outputs, bound model-route admissions, prices, ledger, dependency versions, fit diagnostics, predictions, controls and exact offline commands. Explain same-code replay separately from new-data replication. The EpistemeOS stage adapter provides mechanical provenance/completion checks with `scientific_validity=not_assessed`; it does not supply human scientific approval.

Use the contribution disclosure below. Close with the bounded empirical or methodological conclusion supported by the data, without announcing journal acceptance or a completed Residency application.

## Required figures and tables

| Artifact | What it must show | Source of values |
|---|---|---|
| Coverage table | Planned/attempted/completed/gradeable/prefix/embedding denominators, failures and class counts | All-attempt registry plus deterministic eligibility audit |
| Primary effect figure | Each held-out model's BGE/256 equal-root log-loss gain and interval; zero reference | Saved analysis `paired_gain_by_target` |
| Order-control figure/table | Direct matched loss contrasts for reverse and each of three permutations | Saved `order_contrasts`, not a subtraction of separate interval endpoints |
| Measurement-sensitivity table | BGE and Qwen results on both original and common eligible IDs; exclusions | Bound embedding inputs, predictions and a common-ID audit |
| Cohort and cost table | Requested/returned model, provider, admission, unknown revisions, confirmed and reserved spending | Raw journal, admissions, price snapshot, historical/new ledger |
| Claims-to-evidence map | Each numerical sentence to an immutable artifact and computation | Final manifest and source-linked output paths |

The main effect figure and coverage table should fit in the short portfolio. Plot from saved tidy tables. Do not manually move points, hide failed folds, or average embedder spaces into one geometry.

## Primary sources and the limits they set

These source passages were rechecked on 8 November 2026. They support literature framing, not replication of their experimental results.

| Source | Relevant prior result and implication |
|---|---|
| [Yu et al., v2](https://arxiv.org/abs/2509.00190v2) | The abstract describes spectral step representations, semantic clustering and Markov-chain trajectories. State graphs and transition matrices are precedented. Abstract/metadata rechecked; detailed methods remain attributed to the October review. |
| [Shahariar et al., v2](https://arxiv.org/abs/2510.22437v2) | The abstract describes six-state abstraction and Q-value-guided activation steering. Functional dynamics and control are precedented. Do not equate their activation access with our external text. Abstract/metadata rechecked. |
| [Chrabąszcz et al., v2](https://arxiv.org/html/2605.18549v2) | Sections 2–3.3 and Appendix O distinguish hidden-state probe trajectories, in-distribution diagnostic evaluation and transfer. Their revised analysis explicitly notes that evaluation-set fitting/model selection can reverse an apparent transfer conclusion. Our incremental question uses external text and source-only fitting; it is not the first temporal monitor. |
| [Harrasse et al., v1](https://arxiv.org/html/2607.18532v1) | Sections 5.2/8 and Appendix E.2 examine activation-derived regimes, correctness controls, sentence-order permutation before dynamics fitting, policy transplantation and prefix pruning. Temporal controls and interventions have direct predecessors. Their regimes do not validate our text features or supply a human label standard. |
| [Liu et al., v2](https://arxiv.org/html/2602.13904v2) | Sections 3 and 6 use interventions and deliberately trained model organisms to diagnose CoT pathologies. Removing/substituting reasoning can induce family-dependent distribution shifts, and the healthy-reference assumption is limited. An odd or repetitive observed trace alone does not establish pathology or faithfulness. |
| [Dong, Qin and Shah, v2](https://arxiv.org/abs/2606.30852v2) | The abstract compares learned stopping with calibrated scalar alternatives at matched lost-correct risk and includes serving/probe overhead. A predictive pilot cannot claim practical stopping savings without the separate intervention and complete cost account. Abstract rechecked; detailed methods remain attributed to the October review. |

The [Semantic Afterlife transfer audit](SEMANTIC_AFTERLIFE_TRANSFER.md) is a separate local source for repetition, missingness and bootstrap lessons. Do not import its numerical estimates as evidence for this cohort, or reuse its thresholds without calibration. The audit identifies a bootstrap issue in that predecessor; it does not recompute or invalidate every published estimate there.

## Portfolio evidence sheet

Prepare a factual one-page artifact, rather than a first-person application answer. A suitable heading is **Observable Prefix Transfer: Evidence and Limits**.

| Field | Required final content |
|---|---|
| Question | One sentence stating incremental correctness prediction under model/root holdout |
| Actual population | Admitted checkpoints/providers, domains, independent roots, attempts, eligible traces and prefixes |
| Main result | Each predeclared target's BGE/256 gain/interval; “not estimated” where unavailable |
| Decisive control | Direct refitted-order contrast with its matched denominator and uncertainty |
| Main limitation | The limitation that most changes the result's interpretation, including coverage selection if material |
| Research decision | A documented design or audit decision and its rationale, linked to protocol/history |
| Implementation evidence | Free offline reproduction command, exact commit/bundle hash, tests and what they verify |
| Human/AI contribution | The factual role separation below, linked to recorded decisions and generated code/history |
| Next evidence needed | A concrete larger/independent evaluation or intervention warranted by the result |

The [Residency announcement](https://alignment.anthropic.com/2026/anthropic-residency/) emphasizes technical leadership, research judgment, implementation, communication and collaboration. The sheet can demonstrate the research work; it cannot establish the owner's career history or eligibility. Do not assert leadership, degrees, employment, reference relationships or personal experience from repository ownership.

The [candidate AI guidance](https://www.anthropic.com/candidate-ai-guidance) allows preparation/refinement, asks the candidate to write initial application drafts and expects transparency. This evidence sheet is supporting research material. The owner must supply any personal application draft and actual involvement; no third-party message or submission is part of this task.

## Contribution disclosure

Suggested manuscript disclosure, adjusted only to facts established by the final record:

> This project used Codex and autonomous programming assistants for implementation, testing, source review, analysis preparation, and drafting. The repository owner set the research objective, supplied the recorded design choices and authorized the bounded study. Automated code and method audits are identified as AI-assisted checks. They are not independent human scientific review. The contribution record distinguishes the owner's documented decisions from work executed by the AI system; repository ownership does not imply unaided authorship of every artifact.

Do not list a human as an annotator or scientific reviewer without a recorded real contribution. Do not claim that E0, G3, G4, journal submission or application submission occurred. Any later human interpretation, validation or writing should be recorded with its specific scope.

## Evidence-dependent conclusion language

| Observed situation | Defensible English formulation |
|---|---|
| Positive gain and supportive direct order controls | “For [targets] and eligible [budget]-word prefixes, the specified trajectory features improved held-out correctness prediction over the stated baseline. The direct refitted-order controls support an ordering-dependent contribution in this setting.” |
| Gain compatible with zero | “The pilot did not resolve an incremental predictive benefit at this precision. The interval includes [range]; this result does not establish practical equivalence or accept H0.” |
| Order controls match or outperform observed order | “An advantage specific to the observed semantic ordering was not established relative to the refitted controls.” |
| Opposite model effects | “The predictive contribution differed across held-out models, limiting a shared-effect interpretation.” |
| Embedder disagreement on common IDs | “The conclusion depended on the measurement operator on the matched eligible sample.” |
| Inadequate coverage or class balance | “The contrast was not identifiable for [target/budget], with [counts/reasons]; no zero effect was imputed.” |
| Access/admission failure | “The report establishes an audited implementation and an access/admission boundary; it contains no empirical test of the proposed predictive contrast.” |

The [TMLR acceptance criteria](https://jmlr.org/tmlr/acceptance-criteria.html) prioritize evidence-supported claims and findings useful to readers. A systematic robustness result can be valuable, but a polished AI-produced manuscript or infrastructure alone does not establish scientific adequacy. Select a journal route after the empirical scope and actual human review are clear.
