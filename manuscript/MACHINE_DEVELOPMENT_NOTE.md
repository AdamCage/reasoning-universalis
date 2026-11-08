# Machine-Only Functional Annotation: A Bounded Development Measurement

Prospective methods draft. The user has deferred human annotation and instructed that the current development work use the existing DeepSeek/RouterAI measurement exception. No annotation outcomes are reported here; the collection tables remain pending. Human E0 remains deferred and not passed.

## Purpose and scope

This experiment measures the technical coverage, vote distributions, consensus and repeatability of one machine annotator on already exposed reasoning text. It does not establish the true functional roles of natural reasoning, validate an error detector or complete E0. Five stochastic responses from one model are five votes of one measurement instrument, not five independent experts.

The [historical machine protocol](../design/MACHINE_ANNOTATION_PROTOCOL.md) and [configuration](../design/ANNOTATION_CONFIG.json) provide the role vocabulary, strict response schema and finite panel procedure. The [new annotation protocol](../design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json) supplies the current execution plan, with source/input pins completed before paid responses. The captured [route metadata](../artifacts/machine-annotation-development-2026-11-08/route-metadata.json) records its prospective provider and price information. Historical A/R1 generation conditions and their failed engineering gates remain unchanged. The [v3 generation candidate](../design/PILOT_V3_CANDIDATE_PROTOCOL_2026_11_08.json) remains disabled; this annotation study generates no new task solutions or test corpus.

## Inputs and selection before annotation outcomes

The planned input is the full 200 natural S2 segments in the prepared source packet, covering 24 exposed development roots: 16 roots contribute eight segments and eight contribute nine. Segments within a root, presentation variants and repeated measurements remain dependent. Input selection precedes new annotation outcomes; the original task outcomes were already available, so this is not unopened validation. Selection is based on the fixed source and deterministic ranking rather than desired roles, task correctness or expected consensus. The execution input is `artifacts/machine-annotation-development-2026-11-08/input-items.json`, pending its final immutable binding in this draft.

An earlier budget-limited option selected 72 items under a proposed 900 RUB additional ceiling. Before any annotation response, the user accepted a total 3300 RUB ceiling and funded the full 200-item allocation. The 72-item option was superseded before data; it was not expanded after seeing agreement or unresolved labels. The new additional commitment ceiling is 2400 RUB. Having 200 machine-annotated items would still supply neither independent human truth nor the historical minimum of 40 evaluation roots.

Each vote receives the unchanged problem statement without its separate verified answer, the full current segment, and a suffix of at most two preceding segments totaling at most 1000 Unicode code points. Source offsets, CRLF, context cut coordinates and input hashes are retained. The separate API answer, correctness, source model/provider, split, cluster labels, future segments and other votes are excluded from the request. An answer already embedded in reasoning remains part of that text; this annotation input differs from the answer-censored predictor prefix. Anonymous IDs mask metadata, while wording and publicly available provenance prevent a guarantee of blinding.

The eight functional roles plus `ambiguous_other` retain their existing definitions. Labels refer to the operation expressed by the observed text, not internal computation or factual correctness. A mistaken calculation can still express a deduction or verification operation. No new ontology is inferred from majority votes.

## Finite voting and technical validity

The instrument is `deepseek/deepseek-v4.1-flash` through RouterAI/BytePlus. Each item has five first-round votes with the fixed first-round seed schedule. Temperature is 0.7, top-p 1.0, output cap 1024, timeout 120 seconds and maximum transport concurrency three, with reasoning disabled and no automatic retries. Concurrency three and disabled reasoning are explicit prospective settings of the new condition; they do not rewrite the historical configuration. The inherited generation-route receipt does not prevalidate this annotation mode's schema behavior.

A vote is technically acceptable only after HTTP/API, exact model/provider and completed-output checks, strict JSON/schema validation, item identity and literal evidence-quote validation against the current segment. Schema compliance and an exact quote do not establish that the assigned role is correct. Oversized inputs remain unresolved rather than silently truncating the current segment; malformed outputs are not repaired by another model.

A complete valid panel resolves at a majority of at least three votes. Majority `ambiguous_other` is recorded as `resolved_ambiguous`, not as successful identification of a functional role. If a main panel has a missing, invalid or unknown planned vote, the item is `technical_unresolved`, even when three available votes agree. A semantic second round is permitted only when all five first-round votes are valid and no role has a majority. It consists of five new votes using the fixed second-round seeds and receives no previous votes or consensus. A second complete panel without a majority remains `ambiguous_unresolved`.

Rounds are never pooled for the primary consensus. Confidence and secondary roles do not contribute extra votes. All distributions, technical failures, unsent attempts, ambiguous outcomes and unresolved items remain in their denominators. No item is repeated until a convenient label appears, and unresolved positions cannot be removed to join adjacent transitions.

## Preselected repeatability audit

Twenty items are selected before annotation outcomes for exactly one additional five-vote first-round panel, with the same inputs, seeds and route. This is an explicit prospective override of the historical configuration's selection from completed items. The 20-item/100-call audit denominator remains fixed; technical incompleteness does not trigger replacement by easier items. Unknown attempts retain their reserves and are not automatically resent.

Audit calls are additional repeat measurements, not reuse of a cached response. Compare exact returned hashes, valid parsed votes, vote distributions and audit-versus-original decisions where available. Incomplete comparisons remain visible. The audit never repairs, replaces or pools with the main consensus and cannot open a semantic second round. Same-seed repeatability is distinct from variation across requested seeds; neither demonstrates independent replication or provider-enforced determinism.

## Allocation and accounting

| Quantity | Prospective allocation | Observed result |
|---|---:|---|
| Natural S2 items / original roots | 200 / 24 | Pending collection |
| First-round votes | 1000 | Pending collection |
| Conditional second-round votes | At most 1000 | Pending collection |
| Fixed audit items / additional votes | 20 / 100 | Pending collection |
| Total annotation attempts | At most 2100 | Pending collection |
| Resolved / ambiguous / technical-unresolved items | Not an outcome quota | Pending collection |
| Natural-text role accuracy against independent truth | No reference available | Not estimated |

The maximum is `5×200 + 5×200 + 5×20 = 2100` attempts. Conditional second-round capacity is reserved without assuming that it will be needed. The additional commitment ceiling is 2400 RUB, giving an absolute stage ceiling of 3223.5589067445220 RUB above the preserved launch commitments of 823.5589067445220 RUB. The approved global ceiling increased from 3000 to 3300 RUB before annotation data, while the 984 existing ledger rows and all old obligations remain part of the same accounting history. These are limits and retained commitments, not observed spending. The final conservative quote and actual reported costs, reservation margins and unreported billing are reported separately.

The new dispatch cutoff is 23:00 UTC on 8 November 2026, corresponding to 02:00 Moscow on 9 November. It belongs to the new annotation condition and does not rewrite the closed generation deadlines. Budget, deadline or technical stops can leave planned votes unsent. Every intent, reservation, raw request/response, parsing status, prompt/schema/ontology digest and requested-versus-observed identity remains linked to its finite plan. Secrets are excluded from public artifacts.

## What the resulting evidence can mean

Natural-text outputs support descriptions of technical coverage, selected-sample machine-label frequencies, disagreement and repeatability. They do not provide natural-text accuracy or human macro-F1. Shared model training and architecture can produce correlated, unanimous errors. Source DeepSeek traces must therefore be described separately from GPT-OSS traces, without treating self-annotation as independent corroboration.

The old constructed controls have known constructed role keys and are kept separate. This 200-item natural-text allocation does not itself constitute a new constructed-control experiment. Any later accuracy calculation on such controls must identify their known key, repeated templates, represented roles and prior exposure; it cannot become truth for natural traces. This scope adds no predictive models, cluster discovery, intervention or stopping evaluation.

The project owner's instruction defines the authorized machine-only scope. Codex and programming assistants prepare software, provenance and prose; the frozen DeepSeek instrument supplies the annotation votes. They do not become human annotators or scientific reviewers. The prepared human handoff remains deferred, human gold remains absent, E0 remains not passed, and scientific validity remains unassessed.
