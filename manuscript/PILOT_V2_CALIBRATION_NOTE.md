# Completed-Error Support After a Ceiling-Limited Reasoning Pilot

Technical development follow-up, 8 November 2026. Phase A and the separately frozen provider-recovery condition R1 are closed. Neither selects a common output cap; no final study size or test corpus is released.

## Question and relation to the first pilot

The [first pilot](LOCAL_RESEARCH_PAPER.md) could compare assigned correctness probabilities but did not identify a transferable error discriminator at its primary 256-word prefix. Completed errors were scarce, and prefix eligibility further reduced their support. Pilot v2 therefore asks an earlier design question: can a fixed development allocation supply completed, gradeable errors and successes across independent task roots? It does not fit a new predictor, choose features against target labels, test H0–H7, or validate a stopping policy.

Completion and incorrectness are different outcomes. A longer output allowance might produce more completed answers while still supplying no completed errors. Conversely, an infrastructure failure supplies neither a wrong answer nor evidence that an error detector works. The design preserves these distinctions before any future probability-score comparison.

## Development corpus and crossed budgets

The [frozen phase-A protocol](../design/PILOT_V2_PROTOCOL_2026_11_08.json) specifies 24 development roots: four domains, three construction tiers and two roots per domain/tier. Two dependent presentation variants produce 48 tasks. Both model identities receive each variant at output caps of 2048 and 8192 tokens, one sample per condition: 192 planned cells, with 48 attempts in every model/cap denominator. Model routes were DeepSeek-V4.1-Flash through BytePlus and GPT-OSS-20B through DeepInfra. Sampling settings, allocation, route stops and deadlines were fixed before dispatch.

The [corpus](../artifacts/pilot-v2-2026-11-08/development-tasks.json) separates problem construction from generation budget. Arithmetic uses three exact-integer tracks with 12, 18 or 24 operations per track and larger starting values. CNF instances use 9, 11 or 13 variables. Directed ordering problems use 10, 14 or 18 nodes and include acyclic and cyclic constructions. Grid planning uses 8-, 10- or 12-cell side lengths, increasing obstacles and explicit move bounds. These settings measure task size and reference work; they do not establish monotonic model difficulty or a desired error rate.

Reference certificates are checked through separate implementations: integer evaluation against Fraction arithmetic, bitset CNF truth tables against exhaustive Boolean enumeration, heap-based topological ordering against available-node replay, and queue BFS against layer expansion. Planning answers undergo full move simulation; graph answers must be the lexicographically smallest order or a valid impossibility outcome. Certificates and answers remain outside provider prompts. Permutations, relabelings and grid symmetries preserve the underlying root. Two variants, two caps and two models never create additional independent roots.

Historical overlap auditing covers 7466 published source rows, representing 4893 normalized instances. Previously unindexed audit instances were regenerated against published input hashes. Exact normalization and conservative structural fingerprints reject detected overlap; colored-graph summaries do not prove arbitrary graph isomorphism or semantic inequivalence. Six historical rows lack problem data, and 333 historical planning rows lack a supported structural comparison. These limits preclude an exhaustive novelty claim. V1 per-task test labels were not used to select concrete v2 instances or tune outcomes; aggregate v1 class support motivated the development design.

## Eligibility and engineering decision

The [statistical plan](../design/PILOT_V2_STATISTICAL_PLAN.md) retains 256 observed whitespace words as primary and publishes 128/512 as secondary. Prefix text ends before the first literal `ANSWER:` marker. A primary label requires an operationally accepted, non-summary, non-encrypted visible reasoning channel, exact model/provider, HTTP success without API error, `finish_reason=stop`, and a gradeable final answer. Output-limit truncations remain incomplete even when a diagnostic parser extracts an answer. Missing labels remain null.

Each model/cap requires at least three prefix-eligible error roots and three correct roots, plus at least 36 completed, gradeable answers among all 48 planned attempts. A mixed root can contribute to both class counts but remains one resampling unit. Only after all 192 cells resolve without transport unknowns may the smallest common passing cap be selected. These are engineering floors, not validated power or detector readiness. The allocation cannot expand until a desired error count appears.

## Closed phase-A observations

The [phase-A report](../reports/PILOT_V2_RESULT.md), [results](../artifacts/pilot-v2-2026-11-08/results.json) and [class-support table](../artifacts/pilot-v2-2026-11-08/class-support.json) retain all 192 cells. There were 98 actual requests and 94 unsent cells. DeepSeek supplied all 96 attempts: 51 completed, gradeable answers, all correct, and 45 output-limit truncations. GPT-OSS/DeepInfra stopped after two known HTTP-200 responses containing JSON API error 503; its remaining 94 cells were unsent. There were no transport-unknown calls.

| Model / output cap | Completed / planned | Length-censored | Eligible at 256 words | Error / correct roots |
|---|---:|---:|---:|---:|
| DeepSeek / 2048 | 14 / 48 | 34 | 9 | 0 / 7 |
| DeepSeek / 8192 | 37 / 48 | 11 | 21 | 0 / 15 |
| GPT-OSS / 2048 | 0 / 48 | 0 | 0 | 0 / 0 |
| GPT-OSS / 8192 | 0 / 48 | 0 | 0 | 0 / 0 |

The larger DeepSeek cap yielded more completions in this fixed allocation, yet neither cap supplied a completed error. Its 8192-token completion fraction, 77.1%, alone cannot pass the gate. Phase A selects no common cap. The 503 responses are retained infrastructure outcomes, not incorrect answers. Neither all-correct completions nor discarded truncations justify a population accuracy claim: the estimand conditions on completion, grading and prefix availability. This selection can suppress exactly the difficult cases needed for error discrimination. More observed text therefore does not resolve the main identification problem by itself.

## Separate provider-recovery condition R1

The [recovery decision](../design/PILOT_V2_PROVIDER_RECOVERY_DECISION.json) and [R1 protocol](../design/PILOT_V2_PROVIDER_RECOVERY_PROTOCOL.json) define one separate operational supplement. The final protocol, collector and source inventory were fixed before its first paid response. R1 retains all 96 physical DeepSeek phase-A records unchanged, including exclusions, and allows at most 96 new GPT-OSS/AkashML calls on the same tasks and caps. It neither adds roots nor repairs phase A retrospectively. No further recovery condition is authorized by this plan.

R1 is mixed-provenance development evidence, not independent replication. A provider change does not establish a new model checkpoint; actual weight revision, quantization and execution differences remain unknown. The original two GPT-OSS/DeepInfra 503 outcomes remain in phase A; they are not relabeled or silently replaced there.

The [closed R1 report](../reports/PILOT_V2_RECOVERY_RESULT.md) and [support](../artifacts/pilot-v2-recovery-2026-11-08/class-support.json) contain 192 combined rows: 96 unchanged DeepSeek records and 96 fresh GPT-OSS/AkashML observations, with no R1 API errors or transport unknowns. There are 97 completed, gradeable answers (93 correct, four wrong) and 95 length-censored outputs. GPT-OSS contributes 46 completions, comprising 42 correct and four incorrect answers, plus 50 truncations. Its 2048 cap has 11/48 completions and no errors; its 8192 cap has 35/48 completions (72.9%), 33 primary-eligible traces, and two error versus 18 correct roots. One eligible root is mixed.

The [independent programming audit](../reports/PILOT_V2_ERROR_AUDIT.md) checked all 48 reference certificates and 192 answer diagnostics without changing labels. All four completed errors agree: three wrong integers and one path leaving the grid, spanning three original roots. The grid error has only 40 observed words and is excluded even at 128 words. At primary 256, three error traces therefore supply only two arithmetic error roots. This concentration cannot establish broad domain transfer. DeepSeek still has no completed errors, and GPT-OSS's higher cap misses both the three-error-root floor and 75% completion threshold. All common-cap gates fail; complete collection has improved observability without establishing detector readiness.

The original absolute v2 commitment ceiling remains 1851.5180250837596 RUB within the shared 3000 RUB cap. Phase A closed at 811.7621058153828 RUB charged-or-reserved; [R1 accounting](../artifacts/pilot-v2-recovery-2026-11-08/budget-final.json) closes at 823.5589067445220 RUB, an increment of 11.7968009291392 RUB. These are commitments, not reported spending: final reported costs are 46.6434424889526086237 RUB, with reserves and obligations without reported billing retained separately. The budget and historical ledger were not reset.

## Future study and evidential limits

The [R1 future-design decision](../artifacts/pilot-v2-recovery-2026-11-08/future-design-decision.json) reports conditional class-support and root-level precision scenarios. Their hypothetical probabilities and standard deviations are assumptions, not empirical power estimates derived from v1 or v2. Before a final study, a scientifically useful effect or precision target, measurement error, training/selection uncertainty, heterogeneous strata, eligibility and full costs require justification. Floors of 10/10 source-training, 5/5 validation and 20/20 target roots per class remain lower policy bounds. No final N is selected. A private fresh-seed commitment exists, but no final test corpus is released; all development roots remain excluded. Observed model identities can later be held out from fitting without becoming unseen model families.

The [R1 offline replay](../artifacts/pilot-v2-recovery-2026-11-08/reproduction-check.json) first replays phase A, then verifies 14 frozen source files, all 96 unchanged DeepSeek records, 96 new GPT records, exact results/support and the retained 888-row A ledger prefix within 984 rows. Network attempts were zero. This is same-code reproducibility, not independent statistical replication. Separate [phase-A](../reports/PILOT_V2_KERNEL_CHECK.md) and [R1 EpistemeOS checks](../reports/PILOT_V2_RECOVERY_KERNEL_CHECK.md) completed 54 and 68 byte-integrity jobs and verified backup restoration; they establish neither statistical validity nor complete reasoning. Human authorization defines scope and budget; Codex and programming assistants implemented, checked, analyzed and drafted the artifacts. No independent human annotation or scientific approval is supplied. E0 remains unpassed, scientific validity unassessed, and G2–G4 and external preregistration unclaimed.
