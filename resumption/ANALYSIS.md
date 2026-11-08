# Observable-prefix transfer analysis

`analysis.py` is an offline analysis component. Its tests use constructed data;
passing them is evidence about the implementation, not model reasoning. There
are no new scientific results in this document. E0 remains unpassed. H1–H7 retain
their original meanings in `RESEARCH_SPECIFICATION.md`.

## Estimand and split

For each held-out **model identity**, fit representations and classifiers on the
other models' `train` roots. Choose logistic regularization from `0.01, 0.1, 1.0`
using the other models' `val` roots. Do not refit on validation. Evaluate on the
held-out model's `test` roots. A root must have the same split in every model and
repeat. Canonically duplicated problems and paired outcome variants must share
the root/group ID supplied by the corpus builder. This component checks those
IDs; it cannot discover arbitrary semantic duplicates or prove independent model
ancestry.

The main contrast is static-minus-dynamic held-out log loss; positive values
favor dynamics. Brier improvement is secondary. The bootstrap first averages
paired loss differences within each original task root, including all models
and repeats, then samples roots with replacement. Repeated bootstrap draws keep
their multiplicity. Intervals describe uncertainty conditional on the fitted
classifiers and observed task distribution; they do not incorporate training
uncertainty or establish generalization to all model families.

## Input

Input may be runner JSON (`{"records":[...]}`), a JSON list, or JSONL. Each
record is one completed or failed attempt, with globally unique
`trace_id`, grouped `root_id`, `model`, `split` (`train`, `val`, `test`), `domain`,
`difficulty`, `text`, Boolean `correct`, and `status`. Noncompleted attempts may
have `correct: null` and empty `text`; they remain in coverage counts. Completed
traces explicitly marked `gradable: false` with null correctness are counted as
`grading_unavailable` and excluded from prediction, preserving the denominator.
`text` is the visible
reasoning channel only; final-answer markers are rejected. Correctness comes
from a separate versioned task verifier. Failed/incomplete attempts remain in
the registry and coverage counts, but do not enter prediction fits.

```json
{"trace_id":"model-a:root-001:sample-0","root_id":"root-001","model":"model-a","split":"train","domain":"logic","difficulty":"hard","text":"VISIBLE REASONING ONLY","correct":true,"status":"completed"}
```

The fixed budgets are **128, 256, 512 whitespace-delimited words**, not native
model tokens and not percentages of completed trace length. A trace must reach
the requested budget. Shorter traces are excluded for that budget and counted by
model, domain, split and outcome. This creates a conditional population that may
be selected by correctness; inspect coverage before interpreting performance.
Prefix features never use eventual length or completion-time information.

Each prefix consists of exact consecutive 16-word chunks. For semantic runs add
`embeddings` keyed by the verified model ID, either `baai/bge-m3` or
`qwen/qwen3-embedding-8b`. Each value is a list of chunk records:

```json
{"start":0,"end":93,"text":"EXACT CHUNK TEXT","vector":[0.1,0.2],"model_id":"baai/bge-m3","identity_verified":true,"input_sha256":"SHA256_OF_EXACT_UTF8_CHUNK"}
```

Offsets are Python Unicode character `[start,end)` offsets in the original
reasoning string. The sample vector is illustrative; BGE-M3 requires dimension
1024, and Qwen3-Embedding-8B permits at most 4096 dimensions. The dimension must
remain constant across eligible observations. Input hashes, text and boundaries
are checked. Embeddings must be computed
from each chunk alone, with no later context. The reader cannot independently
verify a provider's identity assertion: raw API provenance and route admission
must be audited upstream. Missing/mismatched representations are excluded and
reported, never synthesized or zero-filled. The alternate fields
`embedding_model` plus `embedding_segments` select one active embedder.

## Predictors and controls

All models include task domain/difficulty and observed text surface features
(character length, digit/punctuation/line rates, type-token ratio and a fixed
uncertainty/correction lexicon). The static model adds source-trained unigram
TF-IDF and order-invariant pooled chunk content. The dynamic model adds eleven
path summaries: adjacent and lag-two cosine distances, jump variability/trend,
endpoint displacement, path efficiency, directional consistency, nonadjacent
revisits, nearest past distance, early/late drift and displacement trend.

The lexical run uses source-trained TF-IDF chunk vectors. Its findings concern
lexical trajectories. The semantic run also includes pooled semantic vectors
and **observed lexical geometry in the baseline**, then tests whether semantic
geometry adds predictive value beyond them. It does not assign functional
states or use an LLM annotator.

Order ablations refit on reversed or permuted representations for training,
validation and evaluation. Three deterministic permutation seeds are reported
separately. Static pooled content is unchanged. In semantic runs these ablations
permute semantic geometry while keeping the observed lexical-geometry baseline
fixed; they isolate semantic ordering conditional on lexical information.
For each control a direct root-paired contrast compares its refitted dynamic
predictor against the observed-order dynamic predictor on exactly the same
traces. Positive loss gain favors observed order. The three shuffle contrasts
are reported separately as exploratory, without multiplicity correction;
separate confidence intervals against the static baseline are not a test of
the difference between orders. Test-only perturbation is not used. Label-permutation inference, live stopping
and causal prefix interventions are not implemented by this component.

## Local commands

Run from the repository root after installing the analysis dependencies
(`numpy`, `scipy`, `scikit-learn`; tested here with 2.3.5, 1.17.0, 1.8.0).

```bash
python -m unittest tests.test_resumption_analysis tests.test_resumption_statistical_validity -v
python -m resumption.analysis artifacts/observations.jsonl --output artifacts/analysis-lexical.json
python -m resumption.analysis artifacts/observations.jsonl --embedding-model baai/bge-m3 --output artifacts/analysis-bge.json
python -m resumption.analysis artifacts/observations.jsonl --embedding-model qwen/qwen3-embedding-8b --output artifacts/analysis-qwen.json
```

The default evaluates all three fixed budgets and observed, reverse, and three
shuffle conditions. For a smoke check use `--budgets 128 --no-order-controls
--bootstrap-samples 100`. JSON output includes fit roots/models, vocabulary and
scaler hashes, source validation losses, selected regularization, predictions,
coverage and paired root-bootstrap intervals. Single-class training gets an
explicitly flagged Laplace-smoothed constant predictor; single-class target
AUROC is `null`. Missing train, validation or target-test data yields an
`unavailable` fold, never a successful result.

Each run and direct order contrast includes `paired_gain_by_target`, with
separate root-paired intervals for every held-out model. Use those for the
predeclared model-specific contrasts; the pooled estimate is additional
descriptive evidence and may hide opposite model effects. Admission-phase
documents or records are rejected by default. `--allow-admission-smoke` permits
an explicit implementation check and stamps its scientific status as smoke only.

Inspect a real result for outcome coverage and errors per held-out model before
writing a conclusion. Better prediction alone does not establish universal
functional states, faithful cognition, harmful overthinking, or benefits of
early stopping. A portfolio or manuscript must state which narrower observable
text claim was actually tested.

## Local software revision before collection

Version `observable-prefix-transfer-v1.1` was frozen before the local collection.
A paired gain based on one independent root retains its point estimate but has
`null` confidence limits and an explicit insufficient-root interval status.
Source, validation and target diagnostics also report zero TF-IDF chunk vectors;
the original feature convention remains unchanged. These diagnostics do not turn
lexical geometry into a validated semantic measure.

For a supplementary comparison on common support, add
`--matched-embedding-input OTHER_EMBEDDER.json` to each semantic run. The two
inputs are intersected on exact trace/prefix identities before every source fit,
validation choice and target evaluation. Run both directions on the same two
inputs. This option does not replace the original-population BGE-M3/256-word
primary reporting contrast.

The local protocol, cap increase and actual state are recorded in
`design/LOCAL_PILOT_2026_11_08.json` and `reports/LOCAL_SESSION.md`. Raw journal
export and offline restoration use `scripts/export_local_evidence.py`; free
analysis from the exported frozen source uses `scripts/reproduce_local.py`.
