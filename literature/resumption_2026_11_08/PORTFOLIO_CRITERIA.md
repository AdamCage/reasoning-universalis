# Portfolio target and publication criteria

Verified on 8 November 2026. This is a preparation memo, not an application or an assessment of the applicant's eligibility. It does not claim that this project's experiments have already succeeded.

## Verified program facts

The [Anthropic Residency announcement](https://alignment.anthropic.com/2026/anthropic-residency/) describes a transition into full-time empirical AI research for established technical leaders. It emphasizes research judgment, implementation speed, communication, collaboration, and motivation to make AI safe. A PhD, prior ML experience, and published papers are not prerequisites. Relevant advertised areas include scalable oversight, model internals and interpretability, and safeguards. Placements last six weeks, three months, or six months; dedicated mentorship and compute are provided. These are program facts, not a promise that a particular project will receive a placement.

The [US application](https://job-boards.greenhouse.io/anthropic/jobs/5438311008) closes on **22 November 2026 at 11:59 PM Pacific Time**, equivalent to **23 November 2026 at 10:59 Moscow time**. Offers are expected in January 2027. It asks for links to notable work with a description of the candidate's involvement, desired research, and 2–3 references. Its process includes a technical assessment and research discussion. The [UK application](https://job-boards.greenhouse.io/anthropic/jobs/5439169008) is a separate posting for a remote UK position with a London-office option. Availability in a country where Anthropic can hire and visa arrangements are individual questions; this memo has not established the applicant's eligibility.

The [candidate AI guidance](https://www.anthropic.com/candidate-ai-guidance), last updated 10 July 2025, permits AI-assisted preparation and refinement, asks applicants to write their initial application drafts themselves, and expects transparency. AI assistance in assessments or live interviews requires explicit permission. Consequently, this repository can supply research evidence and accurate attribution, while a personal application must reflect the candidate's actual contribution and experience.

## Inference: what this project should demonstrate

The following is our interpretation of the criteria, not an Anthropic scoring rubric.

| Capability to demonstrate | Concrete portfolio evidence | Failure to avoid |
|---|---|---|
| Research judgment | A narrow question with an outcome that can falsify the hypothesis; documented reasons for choosing it | Equating a large scope with an important result |
| Empirical skill | Frozen analysis decisions, executable scripts, raw outputs, uncertainty and negative controls | Reporting only successful or complete traces |
| Safety relevance | Clear account of what a monitor observes, what it predicts, and where it fails under distribution shift | Calling ordinary answer correctness a validated alignment detector |
| Implementation | One-command offline reproduction, reliable provenance, bounded execution and accounting | Presenting infrastructure alone as a scientific finding |
| Communication | Short result summary connected to one decisive figure/table and a claims-to-evidence map | Advertising universal internal cognition from text alone |
| Ownership | Factual human/AI contribution statement, version history and decisions the applicant can explain | Attributing autonomous AI work to an unaided human |

The [Anthropic technical safety directions](https://alignment.anthropic.com/2025/recommended-directions/) discuss monitor generalization under distribution shift and process-based weak-to-strong/easy-to-hard oversight. A realistic connection is therefore to **the reliability and limits of a transferable text-based measurement or monitor**. A successful mathematical-answer predictor would be a preliminary testbed result; it would not establish deception detection, robustness to adversarial adaptation, or faithful access to internal computation.

## Result-dependent framing

These are candidate framings. Select one only after the corresponding analysis exists.

| Possible result | Defensible claim | Additional evidence required for a stronger claim |
|---|---|---|
| Dynamics fail to beat length, position, task or lexical controls | Apparent cross-model similarity is explained by identified nuisance variables in the tested setting | More families/tasks and independent measurement before generalizing the failure |
| Dynamic features add predictive information | The specified observable trajectory features improve held-out prediction over specified controls | Calibrated prospective evaluation and intervention before claiming a deployable control policy |
| Results change with segmenter or embedder | Conclusions about text-trace dynamics are sensitive to the measurement operator | Independent functional validation before identifying semantic roles |
| API traces are unavailable or access is blocked | A reproducibility/admission audit documents an infrastructure boundary | Actual traces and experiments before asserting any scientific hypothesis result |

The short portfolio should identify which of these happened, show the denominator and exclusions, state one limitation that changes the conclusion, and link directly to the executable evidence. An honest, well-controlled negative result can demonstrate judgment. This is not a guarantee of admissions or publication.

## Journal route

[TMLR acceptance criteria](https://jmlr.org/tmlr/acceptance-criteria.html) prioritize convincing evidence for stated claims and findings that are useful and clearly communicated to some of its research audience. A systematic robustness or generalizability study can meet the interest criterion; merely rerunning a paper without generalizable lessons may not. A negative result therefore needs an informative design, not just a failed run. Our recommendation is to evaluate TMLR as a potential target once there is a complete evidence-supported manuscript; acceptance and graduate-school recognition are not established here.

The [TMLR author guide](https://jmlr.org/tmlr/author-guide.html) requires an anonymous, complete submission and active author OpenReview profiles, with the manuscript produced using the journal's LaTeX template. Supporting data/code are encouraged. A public portfolio and an anonymous submission require separate packages. No paper, application, or other external submission is authorized or performed by this memo.

The minimum paper bar for this project is a verified outcome: a defined population, task-level independent evaluation, a justified measurement, nuisance controls, sensitivity analysis, and a limitation-aware conclusion. Completing a polished manuscript within the research session does not itself establish that bar, pass human-reference gate E0, or prove any of H0–H7.
