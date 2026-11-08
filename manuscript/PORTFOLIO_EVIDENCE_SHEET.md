# Observable Prefix Transfer Evidence Sheet

**Result, 8 November 2026.** The primary error-discrimination question remains unidentified by class support. This pilot evaluates probability scores on a selected, mostly correct population; it does not establish an error detector, equivalence to no effect, universal reasoning states or useful stopping.

**Question.** Do ordered features of observable reasoning prefixes add correctness information beyond task attributes, surface text, lexical dynamics and pooled content when both the target model and test-task roots are excluded from fitting?

**Actual sample.** DeepSeek-V4.1-Flash and GPT-OSS-20B produced 384 saved main attempts on 96 tasks/48 paired roots in four programmed domains: 335 completed traces, 49 output-limit exclusions and 333 gradeable answers, including 329 correct and four incorrect. Qwen3-32B failed finite admission; its 192 main cells remain unsent. Both semantic embedders cover all 5,778 chunks. See [coverage](../artifacts/resumption-2026-11-08/local/tables/coverage.md) and the [paper](LOCAL_RESEARCH_PAPER.md).

| Primary BGE-M3 / 256 words | Test traces / roots | Static-minus-dynamic log-loss gain [pointwise 95% interval] | Interpretation |
|---|---:|---|---|
| DeepSeek held out | 20 / 9 | -0.00154 [-0.00669, 0.00290] | Target has no errors; error-ranking AUROC undefined |
| GPT-OSS held out | 34 / 11 | 0.00000 [0.00000, 0.00000] | Source has no errors; identical constant predictors force zero |

**Controls and limits.** Source-only transforms and validation tuning precede target evaluation. Direct refitted reverse/three-shuffle comparisons preserve content; all primary BGE DeepSeek log-loss intervals span zero. Intervals condition on fitted predictors and observed roots, without training uncertainty or multiplicity correction. Qwen's secondary 256-word DeepSeek gain is -0.00259 [-0.00700, 0.00138]. All secondary results are [retained](../artifacts/resumption-2026-11-08/local/tables/observed-secondary.md). E0 remains unpassed. New task instances are not new mechanisms, and model holdout is not automatically independent family holdout.

**Research judgment and implementation evidence.** Separate deterministic checks support all four error labels; two formatting failures retain unavailable labels. Operational amendments after API preflight preserve original source/protocol bytes, raw IDs, rejected routing batches and one ledger, while pinning later embedding requests to DeepInfra without fallback. Matched-embedder refits reproduce original predictions. [Source/plan](../design/LOCAL_PILOT_2026_11_08.json), [error certificates](../artifacts/resumption-2026-11-08/local/error-audit.json) and [claims map](../artifacts/resumption-2026-11-08/local/claims-to-evidence.json) make these decisions inspectable. Mechanical tests and replay do not supply human scientific review.

**Cost.** New API-reported charges total 22.26254 RUB. Conservative new charged-or-reserved obligations are 404.71915 RUB, including 4.17591 RUB without reported cost. Including 246.79888 RUB historical obligations gives 651.51803 RUB against the authorized 3000 RUB ceiling. **651.52 RUB is not measured spending.** [Accounting](../artifacts/resumption-2026-11-08/local/tables/summary.json) retains charges, reservation margin and unknown-cost commitments separately.

**Free replay.** With `requirements-resumption.txt` installed, run `scripts/reproduce_local.py --manifest evidence/local-pilot-2026-11-08/manifest.json --output .research/local-replay-check` using Python. It verifies/restores the bundle and reruns frozen analysis without API calls; the output directory must be new.

**Contribution and next evidence.** The owner set the objective, recorded design choices and authorized execution. Codex and programming assistants performed substantial code, tests, source review, analysis preparation and drafting. These are AI-assisted checks, not independent human scientific review or unaided human execution. A stronger study needs fresh tasks yielding sufficient completed errors at prospective prefixes, followed by new held-out evaluation. Personal application drafts and actual involvement belong to the owner, consistent with [Anthropic candidate AI guidance](https://www.anthropic.com/candidate-ai-guidance). No application or article is submitted.
