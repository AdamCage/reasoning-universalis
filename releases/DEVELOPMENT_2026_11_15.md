# Cross-model measurement pilot — 15 November 2026

This exploratory release measures portability of visible-reasoning role labels across annotation instruments. It preserves the previous experiments and release unchanged. Machine consensus is not ground truth, there is no human gold, and E0 remains unpassed.

## Observed results

The fixed sample contains 72 segments from 24 development task roots: a label-blind 48-item core and a separate 24-item challenge sample enriched for rare prior roles. Two annotators each received all 72 full-context items and 24 paired context ablations.

| Annotator | Core matches / valid / planned | Raw agreement (95% root CI) | Cohen kappa (95% root CI) |
|---|---|---|---|
| Qwen3-32B | 19 / 43 / 48 | 0.442 [0.286, 0.605] | 0.240 [0.075, 0.425] |
| GPT-OSS-20B | 24 / 43 / 48 | 0.558 [0.409, 0.711] | 0.383 [0.193, 0.573] |

The 192 study calls produced 166 valid and 26 invalid outputs. Two earlier technical probes failed before study dispatch. A frozen premeasurement transport addendum corrected unsupported schema grammar and mandatory GPT-OSS reasoning; no failed study case was retried and the total remained 194 calls. Context removal changed 7/19 paired-valid Qwen labels and 6/19 GPT-OSS labels, with 24 planned pairs per instrument.

All 26 rejected objects satisfy the supplied JSON schemas but violate unchanged local rules: 13 repeat primary in secondary roles, 12 provide a nonliteral evidence quote, and one gives the wrong source ID. No invalid annotation was repaired or rescued. The result indicates limited transfer of this measurement configuration, not adjudicated role accuracy or a causal model-family effect. Provider, decoding and reasoning-mode differences remain confounds.

## Assets and offline reproduction

- `cross-model-replay-2026-11-15.zip`: complete public payload, including frozen sources, inputs, raw responses, protocols, analysis, report and validation receipts. Extract into an empty directory.
- `cross-model-measurement-pilot.pdf`: the three-page English report.
- `release-manifest.json` and `SHA256SUMS.txt`: source commit and asset sizes/hashes.

Reference runtime: CPython 3.13.1. Primary numerical replay requires only the Python standard library; no key, live state or network is needed:

```text
python -X utf8 scripts/reproduce_cross_model_compat.py --output replay-output
python -X utf8 scripts/tabulate_cross_model.py
```

The optional contract audit uses `jsonschema` (the producer used the version recorded in run metadata):

```text
python -X utf8 scripts/audit_cross_model_outputs.py
```

The public snapshot records 428 passing tests and a fresh-directory replay with networking blocked: 15 numerical/audit files matched exactly. Release integration CI additionally verifies the archived payload and primary replay on Linux and Windows. These are software/provenance checks, not independent scientific review.

## Accounting and boundaries

New charged-or-reserved commitments are 90.6341236966256 RUB within the separately approved 400 RUB cap. API-reported study cost is 2.747385854153200015 RUB; two initial probe reservations with unreported cost remain retained. The shared ledger has 2303 rows and 2128.9515870670476 RUB committed, with its original 2109-row prefix preserved exactly. No paid collector is run for this release.

Next: make every local output rule explicit, then separate contract compliance, sampling variation, context sensitivity and disputed role boundaries before a confirmatory study. No new generation stage or E0 acceptance is released. Model weights, credentials, private settings, caches and temporary directories are excluded; no repository-wide license is introduced.
