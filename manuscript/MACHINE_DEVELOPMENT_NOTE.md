# Machine-Only Functional Annotation: A Bounded Development Measurement

Closed machine-only development collection, 8 November 2026. The portable evidence archive passed keyless offline replay, and the separate mechanical integrity stage and backup restore completed. The user deferred human annotation and instructed use of the existing DeepSeek/RouterAI measurement exception. Human E0 remains deferred and not passed.

## Purpose and scope

This experiment measures the technical coverage, vote distributions, consensus and repeatability of one machine annotator on already exposed reasoning text. It does not establish the true functional roles of natural reasoning, validate an error detector or complete E0. Five stochastic responses from one model are five votes of one measurement instrument, not five independent experts.

The [historical machine protocol](../design/MACHINE_ANNOTATION_PROTOCOL.md) and [configuration](../design/ANNOTATION_CONFIG.json) provide the role vocabulary, strict response schema and finite panel procedure. The [new annotation protocol](../design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json) was frozen before the first annotation response: SHA-256 `0d53274f64e17249611815abe5bb380f5779818bde5545b5732315127bb1fb5e`. The [26-file raw source inventory](../artifacts/machine-annotation-development-2026-11-08/source-inventory.json), [source snapshot](../artifacts/machine-annotation-development-2026-11-08/source-snapshot.zip) and [pre-dispatch manifest](../artifacts/machine-annotation-development-2026-11-08/pre-dispatch-manifest.json) preserve its execution binding, including inherited CRLF bytes. Historical A/R1 conditions and failed engineering gates remain unchanged. The [v3 generation candidate](../design/PILOT_V3_CANDIDATE_PROTOCOL_2026_11_08.json) remains disabled; annotation generates no new task solutions or test corpus.

## Inputs and selection before annotation outcomes

The [frozen input](../artifacts/machine-annotation-development-2026-11-08/input-items.json) is the full 200 natural S2 segments in the prepared source packet, covering 24 exposed development roots: 16 roots contribute eight segments and eight contribute nine. Segments within a root, presentation variants and repeated measurements remain dependent. Input selection precedes new annotation outcomes; the original task outcomes were already available, so this is not unopened validation. Selection is based on the fixed source and deterministic ranking rather than desired roles, task correctness or expected consensus.

An earlier budget-limited option selected 72 items under a proposed 900 RUB additional ceiling. Before any annotation response, the user accepted a total 3300 RUB ceiling and funded the full 200-item allocation. The 72-item option was superseded before data; it was not expanded after seeing agreement or unresolved labels. The new additional commitment ceiling is 2400 RUB. Having 200 machine-annotated items would still supply neither independent human truth nor the historical minimum of 40 evaluation roots.

Each vote receives the unchanged problem statement without its separate verified answer, the full current segment, and a suffix of at most two preceding segments totaling at most 1000 Unicode code points. Source offsets, CRLF, context cut coordinates and input hashes are retained. The separate API answer, correctness, source model/provider, split, cluster labels, future segments and other votes are excluded from the request. An answer already embedded in reasoning remains part of that text; this annotation input differs from the answer-censored predictor prefix. Anonymous IDs mask metadata, while wording and publicly available provenance prevent a guarantee of blinding.

The eight functional roles plus `ambiguous_other` retain their existing definitions. Labels refer to the operation expressed by the observed text, not internal computation or factual correctness. A mistaken calculation can still express a deduction or verification operation. No new ontology is inferred from majority votes.

## Finite voting and technical validity

The instrument is `deepseek/deepseek-v4.1-flash` through RouterAI/BytePlus. Each item has five first-round votes with the fixed first-round seed schedule. Temperature is 0.7, top-p 1.0, output cap 1024, timeout 120 seconds and maximum transport concurrency three within one active controller, with no automatic retries. Parallel collect/resume processes are outside this execution condition. Requests disable reasoning and its return; effective internal mode is unconfirmed. Unexpected returned reasoning is flagged, never read for a label, and does not alone invalidate otherwise valid completed content JSON. These are explicit prospective settings, preserving the historical configuration. The inherited generation-route receipt does not prevalidate this annotation mode's schema behavior.

A vote is technically acceptable only after HTTP/API, exact model/provider and completed-output checks, strict JSON/schema validation, item identity and literal evidence-quote validation against the current segment. Schema compliance and an exact quote do not establish that the assigned role is correct. Oversized inputs remain unresolved rather than silently truncating the current segment; malformed outputs are not repaired by another model.

A complete valid panel resolves at a majority of at least three votes. Majority `ambiguous_other` is recorded as `resolved_ambiguous`, not as successful identification of a functional role. If a main panel has a missing, invalid or unknown planned vote, the item is `technical_unresolved`, even when three available votes agree. A semantic second round is permitted only when all five first-round votes are valid and no role has a majority. It consists of five new votes using the fixed second-round seeds and receives no previous votes or consensus. A second complete panel without a majority remains `ambiguous_unresolved`.

Rounds are never pooled for the primary consensus. Confidence and secondary roles do not contribute extra votes. All distributions, technical failures, unsent attempts, ambiguous outcomes and unresolved items remain in their denominators. No item is repeated until a convenient label appears, and unresolved positions cannot be removed to join adjacent transitions.

## Preselected repeatability audit

Twenty items are selected before annotation outcomes for exactly one additional five-vote first-round panel, with the same inputs, seeds and route. This is an explicit prospective override of the historical configuration's selection from completed items. The 20-item/100-call audit denominator remains fixed; technical incompleteness does not trigger replacement by easier items. Unknown attempts retain their reserves and are not automatically resent.

Audit calls are additional repeat measurements, not reuse of a cached response. Compare exact returned hashes, valid parsed votes, vote distributions and audit-versus-original decisions where available. Incomplete comparisons remain visible. The audit never repairs, replaces or pools with the main consensus and cannot open a semantic second round. Same-seed repeatability is distinct from variation across requested seeds; neither demonstrates independent replication or provider-enforced determinism.

## Allocation and accounting

| Quantity | Prospective allocation | Closed-run observation |
|---|---:|---|
| Natural S2 items / original roots | 200 / 24 | All 200 represented |
| First-round votes | 1000 | 994 valid; six invalid |
| Conditional second-round votes | At most 1000 | 25 valid votes on five items; 975 slots not scheduled by rule |
| Fixed audit items / additional votes | 20 / 100 | 100 valid votes on all 20 items |
| Total annotation attempts | At most 2100 | 1125 physical calls; no transport unknowns |
| Functional / ambiguous consensus | Not an outcome quota | 180 functional; 15 `ambiguous_other` majorities |
| Unresolved items | Retained in 200-item denominator | Two semantic; three technical |
| Natural-text role accuracy against independent truth | No reference available | Not estimated |

The maximum is `5×200 + 5×200 + 5×20 = 2100` attempts. Conditional second-round capacity is reserved without assuming that it will be needed. The additional commitment ceiling is 2400 RUB, giving an absolute stage ceiling of 3223.5589067445220 RUB above the preserved launch commitments of 823.5589067445220 RUB. The approved global ceiling increased from 3000 to 3300 RUB before annotation data, while the 984 existing ledger rows and all old obligations remain part of the same accounting history. The actual metadata-only [complete-roster preflight](../artifacts/machine-annotation-development-2026-11-08/preflight-cost-plan.json) quoted 2267.5125412857060 RUB, or 3091.0714480302280 RUB including retained launch commitments, within both limits. These are conservative commitments and limits, not observed spending; final reported costs, reservation margins and unreported billing remain separate.

The new dispatch cutoff is 23:00 UTC on 8 November 2026, corresponding to 02:00 Moscow on 9 November. It belongs to the new annotation condition and does not rewrite the closed generation deadlines. Budget, deadline or technical stops can leave planned votes unsent. Every intent, reservation, raw request/response, parsing status, prompt/schema/ontology digest and requested-versus-observed identity remains linked to its finite plan. Secrets are excluded from public artifacts.

## Closed-run observations

Collection closed at 21:45:41 UTC on 8 November. The [result report](../reports/MACHINE_DEVELOPMENT_RESULT.md) and [machine summary](../artifacts/machine-annotation-development-2026-11-08/summary.json) retain all 200 items and all 2100 maximum-roster slots. All first-round and fixed-audit slots were attempted. Five complete first panels without a majority opened the 25 second-round calls; the other 975 conditional slots were not scheduled. They are unused conditional capacity, not missing required observations. Six invalid first-round votes left three technically unresolved items; two items remained semantically unresolved after the allowed second round. No consensus was repaired by an audit.

The [scripted technical-failure audit](../reports/MACHINE_VOTE_FAILURE_AUDIT.md) rechecked all 1125 physical calls against the frozen admission gate and parser, with zero differences from saved outcomes. Two invalid outputs added the forbidden field `reason_code_note`. Four supplied exact source substrings of 445–446 Unicode code points, exceeding the 400-character quote limit. The inherited parser's combined quote-error message therefore denotes excessive length in those four cases, rather than a fabricated citation. No JSON, evidence quote or primary label was repaired; accepted schema compliance remains distinct from role accuracy.

| Machine consensus label | Items / all 200 |
|---|---:|
| Problem formulation | 17 |
| Planning | 26 |
| Deduction/computation | 93 |
| Exploration | 6 |
| Verification | 18 |
| Uncertainty | 7 |
| Backtracking/correction | 1 |
| Conclusion | 12 |
| `ambiguous_other` | 15 |
| No consensus label | 5 |

The input contains 99 segments from DeepSeek-generated traces and 101 from GPT-OSS traces. These source strata are preserved because the annotator shares the identity of one source generator. The counts describe selected, already exposed text under a supplied vocabulary; they are neither natural role prevalence nor discovery of independently validated functional states. Sparse selected segments do not support transition or dwell-time estimates.

First-round agreement uses the 197 technically complete five-vote panels, comprising 1970 unordered vote pairs. Raw pairwise agreement is 0.8188. Fleiss kappa is 0.7565, with a descriptive root-bootstrap 95% interval [0.7060, 0.8048]; the corresponding raw-agreement interval is [0.7811, 0.8571]. Resampling uses the 24 original roots and 1000 fixed-seed replicates. These are conditional descriptions of observed machine panels, not intervals for natural-text accuracy or an E0 acceptance test. The five second-round panels are selected for first-round disagreement and do not form an independent comparison cohort.

The preselected audit reproduced the first-round consensus role on 20/20 comparable items. Across its 100 same-seed vote pairs, 92 retained the primary role and 58 retained the entire parsed response. None had an identical raw-response envelope hash; envelopes also contain varying API fields, so this alone does not identify semantic instability. Audit agreement neither changed primary labels nor demonstrated provider-enforced determinism. No returned-reasoning flag was observed in the 1125 vote records, while effective internal reasoning mode remains unconfirmed.

The [budget snapshot](../artifacts/machine-annotation-development-2026-11-08/budget-final.json) retains all 984 launch rows within 2109 final rows, all finalized. Commitments increased by 1214.7585566259000 RUB to 2038.3174633704220 RUB, within the stage and global limits. This phase reported 14.390418143355540296 RUB of API costs and retained 1200.368138482544459704 RUB above that reported amount. Across the full ledger, reported costs total 61.0338606323081489197 RUB, while 204.9083777214812 RUB remains committed without reported billing. These are journaled reported costs and conservative obligations, not a reconciled account statement or a claim that the entire committed amount was spent.

The [portable evidence manifest](../evidence/machine-annotation-development-2026-11-08/manifest.json) binds the 23,675,674-byte archive. Its [keyless replay receipt](../artifacts/machine-annotation-development-2026-11-08/reproduction-check.json), completed at 22:05:33 UTC, confirms byte-exact results and summary, all 26 measured source files, the preserved 984-row launch prefix and successful nested R1 replay, with zero network attempts. The strengthened postcollection consumer also verified original raw costs, source bindings and audit ordering without changing the saved results, summary or budget. This is same-code replay of captured responses, schema checks, panels and accounting; it is neither a new annotation sample nor independent validation of natural functional roles. No measurement labels or estimands were revised.

The producer and original successful replay used CPython 3.12.11. A subsequent Python 3.11 replay differed only in the lower Fleiss-kappa bootstrap endpoint: `0.7060296279441571` rather than the saved `0.706029627944157`, one floating-point unit in the last place. Python documents a [change to float summation in 3.12](https://docs.python.org/3.12/library/functions.html#sum); process-only emulation of the older sum reproduced this difference. Strict archive replay is therefore pinned to Python 3.12.11, without a numerical tolerance. Source bytes, raw responses, counts and billing were unchanged.

The separate postcollection EpistemeOS [integrity stage](../artifacts/machine-annotation-development-2026-11-08/episteme-stage-result.json) captured 48 indexed inputs plus their index, totaling 49 artifacts. All 98 hash jobs completed, with zero failed or unknown jobs. The [fresh restore check](../artifacts/machine-annotation-development-2026-11-08/episteme-backup-check.json) confirmed exact database/CAS bytes, 604 events, 303 receipts and the same provenance-graph hash across 562 restored files. The [privacy-checked proof archive](../evidence/episteme-machine-annotation-2026-11-08.zip) preserves this mechanical evidence. These are checks of artifact and graph integrity; they do not independently recompute annotation statistics, establish scientific validity or substitute for preregistration or human review.

## What the resulting evidence can mean

Natural-text outputs support descriptions of technical coverage, selected-sample machine-label frequencies, disagreement and repeatability. They do not provide natural-text accuracy or human macro-F1. Shared model training and architecture can produce correlated, unanimous errors. Source DeepSeek traces must therefore be described separately from GPT-OSS traces, without treating self-annotation as independent corroboration.

The old constructed controls have known constructed role keys and are kept separate. This 200-item natural-text allocation does not itself constitute a new constructed-control experiment. Any later accuracy calculation on such controls must identify their known key, repeated templates, represented roles and prior exposure; it cannot become truth for natural traces. This scope adds no predictive models, cluster discovery, intervention or stopping evaluation.

The project owner's instruction defines the authorized machine-only scope. Codex and programming assistants prepare software, provenance and prose; the frozen DeepSeek instrument supplies the annotation votes. They do not become human annotators or scientific reviewers. The prepared human handoff remains deferred, human gold remains absent, E0 remains not passed, and scientific validity remains unassessed.
