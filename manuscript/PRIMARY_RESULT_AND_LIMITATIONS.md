# Primary result and interpretation

## The specified BGE comparison

The primary reporting contrast is the equal-root mean of static-minus-dynamic log loss at 256 observed whitespace words with BGE-M3, separately for each held-out model. Positive values favor the dynamic addition. All 5,778 requested BGE chunks from the 335 completed visible traces were covered by accepted DeepInfra responses. Prefix and grading eligibility therefore determine the final primary sample: 20 DeepSeek test traces from nine roots and 34 GPT-OSS test traces from 11 roots. The [saved analysis](../artifacts/resumption-2026-11-08/local/analysis-bge.json) contains every prediction, source-fit fingerprint, regularization choice and control.

| Held-out model | Test traces / roots | Static log loss | Dynamic log loss | Gain | Pointwise 95% root interval |
|---|---:|---:|---:|---:|---|
| DeepSeek-V4.1-Flash | 20 / 9 | 0.53152 | 0.53306 | -0.00154 | [-0.00669, 0.00290] |
| GPT-OSS-20B | 34 / 11 | 0.11179 | 0.11179 | 0.00000 | [0.00000, 0.00000] |

The DeepSeek point estimate favors the static predictor slightly. Its interval includes gains of either sign and conditions on the fitted source models. Since the target contains only correct answers, this comparison scores probabilities assigned to positive observations; it cannot measure error-ranking AUROC or validate calibration across a population containing failures.

The predefined metadata/surface baseline has DeepSeek target log loss 0.10952, compared with 0.28643 for lexical static content, 0.53152 for BGE static content and 0.79139 for Qwen static content. The richer feature sets therefore score worse than this simpler baseline on the observed all-correct target. These are descriptive probability-score comparisons, not evidence that the metadata model is a validated failure detector. All three method families are retained in the numerical tables.

In the GPT-OSS direction, all 25 eligible DeepSeek training observations are correct. The predefined procedure consequently returns the same smoothed constant predictor for metadata, static and dynamic inputs. The zero contrast and zero-width interval follow from identical fitted predictions. They are not evidence of practical equivalence, absent dynamic information, or acceptance of H0. GPT-OSS has one error among its 34 eligible target traces; a constant score has AUROC 0.5, but no transferable error discriminator was learned in this fold.

The achieved experiment therefore provides no convincing primary evidence for incremental error prediction by these features. More specifically, the primary discrimination question lacks the required class support in opposite sides of the two transfer directions. This is a restriction on inference from this pilot, not an estimate of a universal absence of useful reasoning dynamics.

## Direct order controls

Each control refits the affected source pipeline and compares its dynamic predictor directly with the observed-order dynamic predictor on the same target traces and roots. The contrast below is control dynamic loss minus observed dynamic loss; positive values favor the observed order. These are separate exploratory comparisons with conditional pointwise intervals.

| Control | DeepSeek loss gain | DeepSeek 95% root interval | GPT-OSS loss gain |
|---|---:|---|---:|
| Reverse | 0.00103 | [-0.00733, 0.01206] | 0.00000 |
| Shuffle 104729 | 0.00208 | [-0.00186, 0.00507] | 0.00000 |
| Shuffle 130363 | -0.00149 | [-0.01319, 0.00676] | 0.00000 |
| Shuffle 155921 | 0.01936 | [-0.02083, 0.06595] | 0.00000 |

Every displayed DeepSeek log-loss interval spans zero. GPT-OSS remains at the constant-predictor fallback, so its direct contrasts are algebraically zero. These comparisons do not establish ordering-dependent error prediction. Other scoring rules are retained rather than used to replace the primary metric: the last shuffle comparison has an exploratory Brier gain of 0.01081 with interval [0.00149, 0.02697], while its log-loss interval spans zero. That result concerns probabilities on the all-correct DeepSeek target and does not supply evidence of a robust failure detector.

## What remains unresolved

The main limitations arise before any geometric interpretation. Only two model identities passed operational admission, trace completion varies by domain, and reaching a fixed prefix further selects the population. At the primary budget, source validation contains no errors in either direction. A model-held-out score cannot establish transfer to all architectural families, and new roots from the same programmed distributions do not establish a new task mechanism. Only four gradeable errors occurred in the full main collection; the primary populations retain even fewer.

The intervals describe resampling of observed target roots conditional on the learned representations, selected regularization and fitted classifiers. They omit uncertainty in source training, task-generator choice, model ancestry and external backend revisions. No minimum useful effect or equivalence margin was frozen for this development pilot. Non-rejection and an identical-predictor contrast therefore cannot establish H0. A single source checkpoint in each fold also leaves model-population uncertainty unresolved.

E0 remains unpassed. The study uses geometric features of an observed text channel and programmatically verified final answers; it does not validate functional role labels, faithful internal computation, shared cognitive states or causal overthinking. H7 includes a controlled stopping intervention and complete serving-cost evaluation, neither of which was performed. No human G3 or manuscript G4 approval is supplied by tests, AI-assisted audits, archive verification or an EpistemeOS mechanical stage.

A stronger subsequent study needs fresh development tasks that yield enough **completed** correct and incorrect answers, with coverage checked at each prospective prefix budget. Feasibility balance alone is insufficient, and simply increasing input difficulty can increase truncation instead of producing informative errors. Task difficulty and inference budget should be examined separately before a new held-out analysis is frozen. The present target sample must not become a tuning set for that next study.
