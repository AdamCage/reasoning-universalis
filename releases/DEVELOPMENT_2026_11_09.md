# Development snapshot — 9 November 2026

This release preserves the closed local pilot, v2 calibration with its single R1 recovery, and machine-only development annotation. It includes their reports and manuscript notes, saved responses, exact source snapshots and offline reproduction tools. It is an exploratory research snapshot; H0–H7 are not confirmed, E0 has not passed, and no main-study N or new test has been selected. The proposed v3 collector remains disabled.

## Closed results

- The local reasoning-prefix pilot retained 384 main attempts and 333 gradable answers, with four errors. Error-class support was insufficient for the main predictive question.
- The combined v2/R1 record has 97 completed gradable answers: 93 correct and four errors; another 95 traces are truncated. The class-support gate did not pass.
- Machine development used 200 existing S2 segments from 24 exposed task-root groups. Of 2100 maximum slots, 1125 physical calls were needed: 1000 first-round, 25 conditional second-round and 100 preselected audit calls. The 975 unused conditional slots remain in the denominator.
- Consensus produced 180 functional labels and 15 `ambiguous_other` labels; two items remained semantically unresolved and three technically unresolved. Six votes failed the fixed gate: two extra fields and four literal quotes longer than 400 code points. No vote repair or retry of technically incomplete panels was performed.
- On 197 complete first-round panels, pairwise agreement was 0.8187817258883249 and Fleiss kappa was 0.7565378799627793. Same-seed audit consensus matched for 20/20 items; individual roles matched for 92/100 vote pairs and full parsed objects for 58/100. These measure agreement of one DeepSeek/BytePlus multiseed instrument, not role accuracy, human gold or independent replication.

## Downloadable assets

- `machine-development-replay-2026-11-09.zip`: self-contained replay kit with the unchanged machine manifest and evidence archive, all seven bootstrap scripts, a payload checksum list and `REPRODUCE.md`. The evidence archive includes the sealed A/R1 parent chain. No separate parent download is required.
- `machine-development-results-2026-11-09.zip`: machine results, budget/provenance receipts, Russian reports and English manuscript notes, including earlier pilot limitations and the offline next-stage design.
- `episteme-machine-annotation-2026-11-08.zip`: unchanged optional integrity/backup proof. Its 98 hash jobs and successful restoration establish artifact integrity, not independent statistical inference or scientific approval. The later Linux replay receipt is outside its closed evidence index.
- `release-manifest.json` and `SHA256SUMS.txt`: source commit, asset sizes and SHA-256 hashes. The release builder is preserved in `releases/build_development_2026_11_09.py`.

GitHub's source archives contain the complete tracked repository, including the earlier historical evidence packages. The replay kit is the smaller standalone entry point for the machine-development result.

## Reproduce without a model key

Extract the replay kit and use CPython **3.12.11**, the original producer runtime:

```text
python -I -X utf8 scripts/reproduce_machine_development.py --manifest evidence/machine-annotation-development-2026-11-08/manifest.json --output replay-output
```

Choose an output directory that does not already exist. This replay uses the Python standard library, reads saved responses and blocks network access; it neither loads `.env` nor sends model requests. Successful output reports `results_exact=true`, `summary_exact=true`, `source_files_exact=26`, `parent_R1_replay_status=passed` and `network_attempts=0`.

Python 3.11 reproduces one lower bootstrap endpoint as 0.7060296279441571 instead of 0.706029627944157, a one-ULP difference caused by the float-summation change in Python 3.12. Strict comparison is retained and no numerical tolerance is added. See [Python's summation documentation](https://docs.python.org/3.12/library/functions.html#sum).

## Validation and accounting

The measured source closure contains 26 unchanged raw-byte files; the original protocol, inputs, raw calls, closed A/R1, bundled EpistemeOS and scientific specification are preserved. Before release preparation, [CI run 42532517137](https://github.com/AdamCage/reasoning-universalis/actions/runs/42532517137) passed Linux 3.11/3.13 root suites (376 tests each), Windows checks and full archive replay in all three jobs using managed CPython 3.12.11. Separate fresh Windows and Ubuntu replays also passed. The release page records the final integration checks and commit.

The shared ledger has 2109 rows, including all 984 launch rows. Cumulative charged-or-reserved commitments are **2038.3174633704220 RUB** against the approved **3300 RUB** total. The new machine calls reported **14.390418143355540296 RUB** through the API; this is distinct from retained margins and historical obligations, and is not a reconciliation of final billing. No paid commands are repeated for this release.

Model weights are not redistributed. The publisher license receipt applies to the named model, not to the whole repository; this release does not introduce a repository-wide license. Secrets, `.env` and the reserved private holdout seed are excluded. No human annotations, approval or scientific review are fabricated, and no journal submission is made.
