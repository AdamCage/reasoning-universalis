# Novelty update for the resumed investigation

Primary sources checked on 8 November 2026. This is an additive update to the October review. It does not replace the original hypotheses, imply experimental reproduction of cited papers, or treat absence from this search as proof of novelty. Results below are the cited authors' claims; implications for Reasoning Universalis are our analysis.

## Closest prior work and limits on claims

| Primary source and access level | What is already established in that source | Implication for this project |
|---|---|---|
| [Yu et al., 2509.00190v2](https://arxiv.org/abs/2509.00190v2), abstract and metadata rechecked; full text in October review | Spectral representations of reasoning steps, clustering into semantic states, and Markov-chain analysis of CoT trajectories | A semantic graph or a transition matrix alone is not a new contribution |
| [Shahariar et al., 2510.22437v2](https://arxiv.org/abs/2510.22437v2), abstract and metadata rechecked; full text in October review | Six-state finite-state abstraction of reasoning and Q-value-guided activation steering; experiments on three reasoning models and four benchmarks | Functional-state dynamics and successful control already have a close predecessor; external text measurement must be justified on its own terms |
| [Carson and Reisizadeh, 2506.04374v1](https://arxiv.org/html/2506.04374v1), October methods review retained | Low-dimensional switching dynamics and cross-model/task predictive transfer using internal activations | Neither dynamical systems nor transfer is independently novel here |
| [Dong, Qin and Shah, 2606.30852v2](https://arxiv.org/abs/2606.30852v2), abstract/metadata rechecked; October methods review retained | A hidden-state-free learned stopper compared with calibrated scalar alternatives under matched risk and serving-cost accounting | A new stopping feature needs incremental value, calibration and total cost; shorter sampled completions alone do not prove deployable savings |
| [Caldarella et al., 2606.02835v1](https://arxiv.org/abs/2606.02835v1), abstract and metadata rechecked; October full-text review retained | Correct prefixes can become incorrect with more reasoning; verbose and harmful overthinking are different | More length is not equivalent to more harm, and first-correct-prefix stopping uses unavailable ground truth |

## Important additions to the October review

### Chrabąszcz et al.: temporal monitors already exist

[Monitoring the Internal Monologue: Probe Trajectories Reveal Reasoning Dynamics, 2605.18549v2](https://arxiv.org/html/2605.18549v2), revised **2 November 2026**. Read abstract, §2–3.3, conclusions/limitations and evaluation-protocol passages. The paper uses hidden-state probes, cumulative pooling and signal features of probability trajectories to predict harmfulness and mathematical errors. It distinguishes in-distribution cross-validation as a diagnostic separability bound from transferable monitoring. Within-math-category transfer is more favorable than cross-dataset transfer; target-domain retraining is reported separately. Thus temporal predictive features and OOD tests are already direct predecessors. Our possible distinction is a shared measurement operator over external text and explicit nuisance/measurement controls. Access to activations is a material difference, not evidence of superiority. Do not call a classifier trained on test-set trajectories a deployed monitor, or use full-trace percentages as online information.

### Harrasse et al.: functional dynamics with temporal controls and interventions

[Reasoning Fine-Tuning Induces Persistent Latent Policy States, 2607.18532v1](https://arxiv.org/html/2607.18532v1), COLM 2026 according to the arXiv record. Read abstract, selected passages in §3–8 and appendix E.2 on temporal controls. The authors recover switching regimes from activation trajectories with contrastive dimensionality reduction and compare base and reasoning-tuned models. The study reports functional specialization, time-shuffling and correctness controls, state-swap ablations, policy transplantation and prefix pruning. Therefore functional phases, regime persistence, temporal controls, cross-model dynamics and process-level interventions cannot be advertised as first observations. Text-trace invariance and sensitivity to an external measurement operator remain different questions. The regimes are activation-derived; they are not an independently validated annotation standard for our text labels. This update does not reproduce their experiments or certify every reported causal claim.

### Liu et al.: pathology diagnostics require interventions and reference assumptions

[Diagnosing Pathological Chain-of-Thought in Reasoning Models, 2602.13904v2](https://arxiv.org/html/2602.13904v2), revised 23 July 2026. Read methods and limitations. Necessity, paraphrasability and substantivity compare answer likelihood after interventions on CoT, and are tested on trained/prompted model organisms. The limitations explicitly recognize that removal/random-text interventions can create family-specific distribution shifts and that a presumed healthy baseline is an assumption. A strange text pattern is therefore not itself evidence of a pathology, encoded reasoning or deception. Cross-family differences in our measurements may reflect training format rather than reasoning quality. Our observational dynamics cannot replace these interventions or establish faithfulness.

### Recent developments checked at abstract level only

- [Anwar et al., Monitorability Is Trainable, 2610.29734v1](https://arxiv.org/abs/2610.29734v1), 21 October 2026: proposes a mutual-information post-training objective and reports restoration of monitorability in degraded model organisms. This prevents presenting monitorability as an immutable model attribute. Full methods were not reviewed in this update.
- [Lewis-Lim et al., Efficient Reasoning Training Does Not Always Harm CoT Faithfulness and Monitorability, 2610.03509v1](https://arxiv.org/abs/2610.03509v1), 2 October 2026: reports different effects of length-pressure training on faithfulness and monitorability. The two must not be equated. Full methods were not reviewed here.
- [Van Deventer, Troitskii and Ruis, The First Few Tokens Matter, 2610.40939v1](https://arxiv.org/abs/2610.40939v1), 29 October 2026: reports that initial-token interventions affect distinct forms of controllability differently. Prompt and opening-format sensitivity are plausible nuisance variables, not a mechanistic conclusion of our own work. Full methods were not reviewed here.

## Defensible research gap, conditional on actual evidence

The strongest narrow question is whether **a specified external text measurement yields cross-model trajectory information beyond task identity, position, length and lexical surface, and whether that conclusion survives changes of measurement**. This combines a scientific target with a safety-relevant failure boundary: a monitor's apparent transfer can arise from nuisance variables or its measurement operator. The October specification already points in this direction; the new sources make disciplined controls more important.

This is a proposed gap, not an exhaustive novelty claim. A successful test still establishes only observable text dynamics under the tested domains and models. A failure can be informative if it localizes the confound and carries independent-task uncertainty. Neither outcome proves common internal computation, deception detection, causal effectiveness of stopping, or universal cognition. Functional role interpretation still needs independent reference validation; correlated machine labels do not pass human E0.

## Analysis safeguards implied by the literature

1. Keep every checkpoint/sample from a task within its assigned fold; account for shared task identity across models.
2. Report length/position, task-only and lexical baselines, and order-shuffled controls. A feature family must beat the relevant nuisance alternative.
3. Freeze model selection/calibration without the held-out test labels. Report within-distribution diagnostics separately from transfer.
4. Use observable prefix lengths for prospective claims. A percentage of the eventually generated trace is retrospective unless the total budget was fixed in advance.
5. Distinguish complete traces, truncated traces, summaries, refusals, errors and missing responses. Exclusion and trace-availability rates are part of the result.
6. Treat a geometric or graph similarity as a property of a specified operator and null model. Do not infer a semantic state or mechanism from appearance alone.
7. Include actual probe, embedding and repeated-prefill costs before claiming savings. Observational answer prediction does not justify a stopping intervention.

These are design recommendations derived from the sources and the existing specification, not new experimentally verified findings.
