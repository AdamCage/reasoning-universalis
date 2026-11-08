# Generator and reference-grading audit, 8 November 2026

The resumed project has a completed, reproducible **offline generator audit**, not a completed LLM study. It finds both genuine improvements from v2/v3 to v4 and remaining problems that must be resolved before interpreting model trajectories. No paid calls were made; E0 remains not passed; H0–H7 were not tested by this audit.

## Reproduce

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m resumption.generator_audit --seeds-per-cell 48
python -m unittest tests.test_resumption_generator_audit -v
```

The default output is `artifacts/resumption-2026-11-08/generator_audit/`. `summary.json` includes source SHA-256 values, library versions, fold sizes, class counts, complete baseline metrics and exact duplicate examples. `instances.jsonl.gz` has 6,560 provenance/answer rows: the four published 200-task rosters plus 5,760 extended tasks. Extended v1 uses four domains × three difficulty levels × 48 seeds; v2–v4 each use four domains × three families × three levels × 48 seeds. There is no API dependency. The original generators, manifests and specification remain unchanged.

## Unique identifiers did not guarantee distinct problems

Canonicalization removes family metadata and ignores clause/literal order, edge order and obstacle order. It preserves meaningful numerical data and instruction-relevant fields. It detects exact normalized instances, **not** arbitrary graph isomorphisms or algebraic equivalence.

| Version | Published tasks | Published unique raw prompts | Published canonical instances | Extended tasks | Extended unique raw prompts | Extended canonical instances |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 200 | 181 | 181 | 576 | 465 | 465 |
| v2 | 200 | 200 | 199 | 1,728 | 1,449 | 1,408 |
| v3 | 200 | 200 | 199 | 1,728 | 1,529 | 1,513 |
| v4 | 200 | 200 | 199 | 1,728 | 1,543 | 1,500 |

The published v4 tasks `stage3-generators-v4:planning:grid_a:easy:12` and `stage3-generators-v4:planning:grid_c:easy:2` describe the same grid, start, goal, move budget and obstacle set. Only the family name and obstacle order differ. Their common normalized instance SHA-256 is `0a45cecaebac86286d4a5b608a28f348ecf6d3f5cb5ac9453499f6ee8c89d3ef`.

On the extended v4 set, 284 rows belong to duplicate instance groups spanning at least two folds under a naive task-ID-hash five-fold partition. This is a reproducible example of potential leakage from splitting by seed-derived root ID alone. It is **not** evidence that a prior model experiment actually used such a split; the scientific pilot has not run.

V4 `fixed_fold` has 144 extended tasks but only 21 distinct prompts: seven periodic seed configurations at each of three levels. All 144 extended `fixed_residues` answers equal `(seed + 1) % span`. The latter is a source/metadata-access shortcut: seeds are not displayed to the model, so it must not be described as a demonstrated prompt-visible answer leak. The historical surface gate omits these 432 math tasks entirely.

## Heldout shortcuts: what v4 fixed and what remains

The target below is **instance feasibility**: SAT versus UNSAT, existence of a topological order, or existence of a bounded plan. It is not correctness of a model's submitted answer. In particular, knowing that a valid order or plan exists does not supply that order or plan.

Every baseline fits exclusively on training folds. GroupKFold combines declared roots and normalized duplicate instances; for v3/v4 it also joins complementary family × level × seed-pair target designs. Keeping those pairs together avoids artificial train/test class anticorrelation. The folds are descriptive development checks, not a preregistered scientific hypothesis test. Metadata lookup receives family/level or parity; the character baseline receives only prompt text. The fixed character model uses training-only TF-IDF character 3–5-grams, at most 6,000 features, and logistic regression with C=1. No target-fold hyperparameter selection is performed.

Extended-set heldout accuracy (432 tasks per domain for v2–v4):

| Baseline | v2 logic | v2 graph | v2 planning | v3 logic | v3 graph | v3 planning | v4 logic | v4 graph | v4 planning |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Training majority | .667 | .667 | .667 | .500 | .500 | .498 | .500 | .500 | .500 |
| Family + level lookup | 1.000 | 1.000 | 1.000 | .500 | .500 | .498 | .500 | .500 | .500 |
| Seed parity lookup | .667 | .667 | .667 | 1.000 | 1.000 | .998 | .403 | .481 | .477 |
| Prompt-length stump | .894 | .667 | 1.000 | .944 | .616 | .498 | .500 | .500 | .500 |
| Prompt character n-grams | 1.000 | .648 | 1.000 | .965 | .731 | .810 | .509 | .500 | .632 |

V4 removes the tested v2 family and v3 parity/count shortcuts in this corpus. Its planning prompts retain a measurable signal for the fixed text classifier: 273/432 correct, accuracy .63194 and AUROC .66741. This does not identify its causal source, demonstrate model exploitation, or prove other shortcuts absent. Geometry of obstacle coordinates can legitimately predict feasibility; further matched controls would be needed to separate superficial cues from partial task solving.

The historical `stage3.baseline_audit.surface_audit` is a resubstitution diagnostic: majority mappings and thresholds are selected and scored on the same tasks. Its parity/length/count values are the **maximum over domains**, and its feasibility scores omit math. Those values are useful for finding glaring flaws but are not estimates of heldout prediction or a validated leakage-free admission test.

The names `cnf_a/b/c`, `graph_a/b/c` and `grid_a/b/c` in v4 select different random streams of the same respective generator mechanism. Holding out one such name tests new samples of that mechanism; it must not be advertised as transfer to a substantively different task family.

## Independent scoring and compatibility

All 800 published task answers agree with an independent reference implementation (planning compared by bounded feasibility). Every independently produced witness is accepted by the new verifier; garbage answers are rejected. The implementation independently enumerates Boolean assignments and topological permutations, recomputes arithmetic and searches bounded plans. Correct submitted plans are graded by full simulation, including obstacles, boundaries and step budget.

V4 has no `verify` function. Hypothetically reusing either `generators_v2.verify` or `generators_v3.verify` on independently correct v4 witnesses rejects **all 50 published math answers as unparseable**, because those scorers dispatch on old family names. On the 150 published non-math items both old verifiers accept the reference witnesses. This is a compatibility experiment, not an assertion that a paid run used either scorer. Reusing the v2 grid verifier also omits the bound in its solvability reference; the current published v4 corpus does not expose a witness disagreement from that omission, so no observed failure rate is claimed for it.

The reusable API is in `resumption/generator_audit.py`:

```python
solve_reference(task)                 # exact integer/label/order or bounded planning witness
verify_answer(task, final_text)        # correct / incorrect / unparseable + grading uncertainty
witness_text(task)                    # independently correct final ANSWER line
canonical_instance_key(task)         # exact normalized instance identity, not full isomorphism
```

The explicit generator allowlist includes `resumption-generators-v1`. Unknown versions or malformed task data raise before answer parsing, preventing infrastructure errors from silently becoming model failures. Final answers require the final `ANSWER:` line; graph node arrays reject Boolean and floating-point values; planning arrays require legal strings and are fully simulated. Nine focused tests cover all 120 published schema combinations, a real periodic collision, complementary target grouping, v4/v2 scorer incompatibility, strict answer parsing, lexicographic order, Boolean rejection and bounded planning.

## Consequences for the next run

1. Use a versioned reference verifier and record its source hash alongside every model outcome. A successful parser is not evidence that the final answer is correct.
2. Reject duplicate canonical instances before sampling; preserve both roots and template/family groups. Keep deliberately dependent target pairs together. Use stronger isomorphism handling if making claims requiring it.
3. Generate arithmetic coefficients and congruence witnesses independently of exposed seed formulas and include math in the audit. Difficulty labels need empirical validation rather than size labels alone.
4. Define transfer by substantive heldout task mechanism and heldout model, with source training/validation roots disjoint from target evaluation roots. A new family name or random stream is insufficient.
5. Train the eventual trajectory monitor against verified model-answer correctness, compare against prompt/text/length baselines, and preserve content under order controls. The present feasibility audit does not replace that experiment or human E0 validation.

These results justify concrete repairs and a reproducible methods artifact. They do not establish universal reasoning states, a causal mechanism, a transferable monitor or a deployable stopping policy.
