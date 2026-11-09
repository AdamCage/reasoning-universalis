# Statistical audit of the resumption analysis

8 November 2026. This is an additional AI code and method audit. It is not an independent human review, E0 validation, G3 approval, or a scientific result from the model cohort.

## Assessed implementation

`resumption/analysis.py` uses fixed prefixes of 128, 256 and 512 non-whitespace spans, divided into exact 16-span chunks. These are a documented whitespace unit, not model-native tokens. Prefix features do not use final trace length. A trace must complete and reach the requested budget to enter that budget's analysis; consequently the estimand conditions on eligibility. Coverage by model/domain/split/correctness must accompany every result.

For each target checkpoint, learned representations and scalers use other models' training roots only. Regularization is selected using source validation roots. Target test roots are disjoint from both training and validation roots across models. The target checkpoint does not enter feature fitting, hyperparameter selection or fitting of the predictor. Other models' examples from target test roots are also excluded from training and validation. These checks prevent the easier estimand in which target-model success is predicted on already seen tasks.

The code implements checkpoint holdout. Calling this *family holdout* additionally requires a cohort with no related training family remaining among sources; model names alone are insufficient. Unseen roots are sampled from the same programmed benchmark distribution. This is not transfer to an unseen benchmark, domain or arbitrary real-world reasoning task.

## Independent invariants tested

Command:

```bash
python -m unittest discover -s tests -p 'test_resumption_statistical_validity.py' -v
```

Twelve tests passed on 8 November 2026:

- Unequal numbers of repeated generations and models do not change an equal-root paired estimand.
- A root drawn twice by the bootstrap contributes twice, preserving original within-root aggregation. This avoids the source-seed relabeling concern found in the predecessor project.
- Identical predictor probabilities produce exactly zero paired gain and zero-width zero interval.
- Duplicate prediction identities and cross-model accidental pairing are rejected. These checks were added to the implementation after this audit.
- Flipping target labels changes neither training features, regularization nor target predicted probabilities.
- The target model's vocabulary and category levels are absent from fitting.
- A root present in both source training and target testing is rejected.
- Changes to an unobserved future suffix leave the fixed prefix and chunk boundaries unchanged.
- Static features remain unchanged under the order conditions for both lexical and semantic representations.
- Order controls refit the source feature pipeline and do not introduce the target model.

The tests use known labels, probabilities and synthetic paths. They verify implementation properties rather than mirror an observed significance result. They do not establish external validity, bootstrap coverage for this empirical sampling distribution, or human construct validity.

## Estimand and uncertainty

The primary reported difference is a paired static-minus-dynamic loss for each eligible trace, averaged within original root across available models and repeats, then averaged equally over roots. The bootstrap resamples these original root-level differences with replacement. It therefore preserves dependence among models/repeats within a task and does not count segments as independent observations.

The interval conditions on the fitted predictors and observed experimental cohort. It does not propagate uncertainty in training data, selected regularization, model-family sampling or provider identity. Sparse roots, a narrow cohort, selection induced by reaching the prefix budget, and highly unequal success rates can still limit practical interpretation. Report point estimates, intervals, sample counts and source/target performance even when the intervals are wide. AUROC is undefined when the test subset contains only one class; this is retained as missing rather than manufactured.

## Interpretation of order ablations

A fair order ablation keeps static content fixed and refits the dynamic classifier on the permuted training/validation paths before evaluating permuted target paths. Test-only shuffling would add a distribution shift and is not used. For semantic analysis, observed lexical path geometry intentionally remains in the static confound baseline; only the added semantic path geometry is shuffled/reversed. Thus the question is whether semantic order adds value above observable lexical dynamics and pooled content.

Separate intervals for static-to-dynamic gain in the observed and shuffled conditions do not by themselves establish a difference between conditions. In particular, “significant with order, nonsignificant after shuffle” is not evidence of a significant order effect. A direct root-paired observed-dynamic versus refitted-shuffled-dynamic loss contrast is required. After this audit requested it, `run_analysis` added `order_contrasts`: control refitted dynamic loss minus observed dynamic loss, matched by original trace and root. Its sign and matching were inspected. The three shuffle seeds remain separate exploratory contrasts, not three independent replications; their intervals are pointwise and not multiplicity-adjusted.

## Scientific boundaries

This is a predictive audit of externally observable text geometry. It does not recover validated functional roles, establish universal internal reasoning mechanisms, identify deception, prove harmful overthinking, or demonstrate a causal benefit from stopping generation. A useful prefix predictor and a useful stopping intervention are different results. The original hypotheses and human-validation requirements remain unchanged.

The predecessor project's numerical results are not imported as prior support for the new cohort. Only its control-design lessons are transferred; see `SEMANTIC_AFTERLIFE_TRANSFER.md`.
