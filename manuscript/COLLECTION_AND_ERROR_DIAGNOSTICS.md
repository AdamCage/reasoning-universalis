# Collection and answer diagnostics

The main collection closed at 09:37:58 UTC on 8 November 2026. All 384 requests in the admitted allocation produced saved attempt records: 96 tasks, two requested samples, and two model identities. The corpus contains 48 paired task roots and four additional admission tasks. The three-candidate design contained another 192 Qwen3-32B cells, which were not dispatched after the finite admission rule rejected two output-length-limited responses. These absent cells are an admission outcome, not measured Qwen accuracy.

| Model and observed route | Main attempts | Completed visible traces | Truncated or excluded | Gradeable answers | Correct | Incorrect |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek-V4.1-Flash, BytePlus | 192 | 173 | 19 | 173 | 172 | 1 |
| GPT-OSS-20B, DeepInfra | 192 | 162 | 30 | 160 | 157 | 3 |
| Admitted allocation total | 384 | 335 | 49 | 333 | 329 | 4 |

The 329/333 proportion describes gradeable completed answers. It is not an unconditional accuracy estimate over the attempted matrix, and neither 333 answers nor their segments are independent task roots. All 49 excluded main attempts reached the output limit. The exclusions were concentrated in logic: 43 of 96 logic attempts were truncated, compared with six of 96 planning attempts and none in arithmetic or topological ordering. Two completed arithmetic answers additionally failed the fixed response parser. The full model/domain/split matrix, including the unadmitted candidate's unsent cells, is retained in the [coverage tables](../artifacts/resumption-2026-11-08/local/tables/coverage.md).

These counts expose an evaluation bottleneck. Balancing satisfiable and unsatisfiable instances, or feasible and infeasible plans, does not balance model correctness. The completed, gradeable population contains only four errors, and completion itself depends strongly on the observed domain. Increasing apparent accuracy by conditioning on completion would obscure this selection. Conversely, treating every missing answer as a measured incorrect label would change the specified prediction target. We preserve the original labels and report availability separately.

## Separate checks of the observed errors

Every recorded incorrect answer was checked with a separate deterministic implementation that does not import the main `verify_answer` function. The [diagnostic code](../scripts/audit_local_errors.py), [certificates](../artifacts/resumption-2026-11-08/local/error-audit.json), and [audit report](../reports/LOCAL_ERROR_AUDIT.md) retain task data, exact submitted answers, input hashes, and the checker hash. This is a postcollection program check of selected error records; it is not an independent human scientific review or a second hypothesis test.

The DeepSeek error answered `SAT` for an eight-variable CNF. Exhaustive evaluation rejected all 256 assignments. A separately checked resolution derivation also reached the empty clause. The three GPT-OSS errors violate explicit grid constraints: one test answer moves north from the origin to `(0,-1)`, one training answer leaves the grid at `(5,-1)`, and another enters an obstacle at `(4,2)` on its eighth move. An independent breadth-first search found valid routes of nine, ten, and eight moves for the corresponding planning problems, and those witnesses were simulated again. The diagnostic therefore supports the four local error labels; it does not validate every aspect of the task distribution.

The two unparseable GPT-OSS arithmetic outputs ended with `**ANSWER: 44**` and `**ANSWER:** 32`. Removing Markdown emphasis yields numbers that satisfy their respective remainder constraints. The fixed parser requires the exact final-line format, so both original labels remain `null` and neither enters the gradeable prediction sample. This distinction matters when correctness errors are rare: formatting failures, unsuccessful reasoning, and incomplete generations are different observations.

## Consequences for the predictive question

At the predeclared 256-word budget, text eligibility yields the following support before embedding exclusions. The [programmatically generated support table](../artifacts/resumption-2026-11-08/local/tables/prefix-support.md) retains all three budgets.

| Model | Split | Eligible traces | Roots | Correct labels | Incorrect labels |
|---|---|---:|---:|---:|---:|
| DeepSeek-V4.1-Flash | Train | 25 | 14 | 25 | 0 |
| DeepSeek-V4.1-Flash | Validation | 11 | 5 | 11 | 0 |
| DeepSeek-V4.1-Flash | Test | 20 | 9 | 20 | 0 |
| GPT-OSS-20B | Train | 60 | 20 | 58 | 2 |
| GPT-OSS-20B | Validation | 17 | 6 | 17 | 0 |
| GPT-OSS-20B | Test | 34 | 11 | 33 | 1 |

Consequently, neither transfer direction supplies both a source training sample with errors and a target sample with errors. Holding out GPT-OSS trains on a single-class DeepSeek sample, invoking the specified constant-predictor fallback. Holding out DeepSeek evaluates a target containing only correct answers, making error-ranking AUROC undefined. Both source-validation samples also contain no errors. This is a limitation of the achieved evaluation population, not evidence that ordered text features contain no information.

The sole DeepSeek error has 226 retained whitespace words. It qualifies at 128 words but is excluded by the predeclared 256-word primary budget. The budget is retained; moving the primary analysis to a shorter prefix after seeing this error would change the design. The 128-word analyses remain reported secondary results, where one error root still provides little support for a robust detector claim.

The usable prediction sample is further conditioned on reaching a specified prefix and having its embeddings available. The model-specific class counts and independent root counts for each 128-, 256-, and 512-word analysis must therefore accompany the loss contrasts. A single-class target has no estimable AUROC. A source training sample without errors invokes the documented smoothed constant predictor, so identical static and dynamic predictions are a property of that fitted procedure rather than evidence that trajectory information is absent.

The small number of failures limits any claim about error discrimination. Conditional log-loss differences compare the probabilities assigned to observed labels under a proper scoring rule; they do not validate calibration in the wider population, a transferable failure detector, or a useful stopping policy. The root bootstrap conditions on the fitted classifiers and omits training uncertainty. A narrow or zero-width interval from identical fitted predictors cannot supply an equivalence margin, establish H0, or compensate for the lack of negative outcomes. The broader hypotheses and human measurement validation remain unresolved.
