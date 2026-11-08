# Human E0 development handoff — prepared, not validated

This operational handoff reuses RESEARCH_SPECIFICATION §6.4/§10, ANNOTATION_PROTOCOL.md, HUMAN_REFERENCE_PROTOCOL.md and E0_PRELIMINARY.json without changing them. It prepares work for real people; it neither resumes paid collection nor identifies or recruits annotators. Codex helpers are software assistants and are not human reviewers.

The selected source is the closed R1 mixed-provenance development corpus. All original roots have already been exposed and the outcomes were already available before this handoff. One physical visible trace per each of 24 roots is chosen by a fixed, outcome-independent hash; 200 S2 segments are chosen in a balanced round-robin hash order. Correctness and status do not rank the candidates. Completed and truncated visible fragments are eligible for this descriptive text-annotation preparation; neither is selected because of its answer label. The original raw reasoning, CRLF and embedded ANSWER text are preserved. Final API content, verified answers, certificates, correctness, model/provider and split/cluster metadata are not part of annotator items. Metadata masking does not remove possible self-identification within the text.

This is not an independent measurement-validation sample. It has 24 exposed development roots, 0 unopened validation roots, and at least a 16-root numerical shortfall against the proposed 40-root minimum even before independence is considered. The 200 balanced real-text segments are not a natural-prevalence sample. No role coverage is known until actual annotation/adjudication; 20 gold examples across 10 roots for each role cannot be promised. No v1 test material is mixed in.

## Existing scientific requirements remain open

E0_PRELIMINARY proposes at least 200 segments/40 roots, complete double human annotation and minimum per-role coverage. It proposes boundary F1 .85, human kappa .67, eight-role macro-F1 .70, recall .50, family/domain macro-F1 .60, natural-sample ambiguous fraction at most .20, macro-F1 CI width at most .20 and style/paraphrase F1 drop at most .10. Those are provisional development targets, not accepted G2 thresholds or an automatic pass rule. Missing coverage, degenerate agreement, wide uncertainty or unfinished checks remain unresolved.

The specification requires all six E0 components: constructed known phases, segmentation accuracy, state recovery, paraphrase robustness, style/length robustness, and random-sequence false-universality controls. Human agreement alone does not complete them. The old 12 constructed sequences/48 segments contain only four unique phrases and do not cover all eight roles; their constructed-control key is not human gold. Practice is separate and contributes no independent validation roots or human labels.

## Distribution and phases

The coordinator assigns two real people who are not authors of the automatic segmenter at annotation time, verifies eligibility/identity and arranges separate training. All participant and adjudicator fields remain empty now. Do not insert invented names, model votes or agent identities.

Distribute only public-boundary/A or B and the constructed practice items to the corresponding person. Keep coordinator files and the other participant's answers separate. Both participants independently annotate internal Unicode operation boundaries on the full selected traces before seeing role items, automatic clusters or others' submissions. They save completed copies outside the immutable package; the first can be recorded separately without opening its peer. Self-attestations record the claimed workflow and do not establish that it actually occurred.

The release tool requires two complete boundary submissions with distinct self-reported pseudonyms, training/independence/no-LLM/no-role-before-boundary declarations and timezone-bearing completion times. It copies prepared S2 role packets only after validating both submissions and records its release time. A role response cannot claim completion before either person's boundary completion or that release time. Distribute only each released A/B directory. Private release receipts preserve the original boundary submissions and must not be sent to the other person.

Role annotation uses the original eight-role vocabulary plus ambiguous_other, the exact current S2 segment and at most two preceding segments/1000 code points. Primary/secondary roles, confidence, reason, explanation, literal current-text evidence and context-extension flags are required. Missing is null, never an automatic incorrect or ambiguous label. Full visible context can be requested from the coordinator; the self-reported extension and explanation are retained and reported separately.

S2 roles do not automatically label human S1 segments or validate S1 recovery. S1 role packets require a separate fixed boundary revision after the independent first round. S3 remains unavailable without genuine tokenizer maps. Boundary problems in a role form do not change that form's segmentation.

## Import, agreement and future adjudication

The importer checks immutable item hashes, exact Unicode offsets and past-only context, exact slot/round/roster, response schemas, quotations and all required self-reports. It preserves the original files and calculates agreement only before adjudication. One submission produces no pairwise agreement. Cohen kappa retains the undefined value for degenerate marginals; counts and task-root bootstrap uncertainty remain explicit. No A-as-gold macro-F1 is claimed.

After both independent role files are sealed, a real third adjudicator resolves disagreement. If only a two-person discussion occurs, describe it as such and never invent a third person. This tool deliberately does not create adjudicated gold, verify human identity, grant scientific review or set E0 to passed. Both original submissions remain available for pre-adjudication agreement.

After exposure to an independent validation set, changing ontology, boundaries, prompts, mapping or thresholds requires a new revision and fresh unopened validation roots. This exposed development packet may help refine procedure but does not replace that future validation. It does not release a confirmatory test, choose N or authorize another R1/recovery/model call.

The coordinator/source key will be public in the repository for reproducibility. Consequently the owner and anyone reading it cannot be claimed blinded. Blind distribution to external participants is a procedural requirement, not an access-control guarantee. Human identity/independence verification and adjudication remain coordinator tasks.

The binary method-source ZIP preserves captured source bytes and their hashes, including inherited CRLF. It is a method snapshot, not the measured A/R1 execution closure or an execution attestation. The importer checks that its creator/importer and three measurement modules match those captured sources after only CRLF-to-LF normalization, accommodating a Git LF checkout without rewriting archived bytes or accepting other source changes.
