"""Hash-bound integrity stage over real study artifacts, never scientific approval."""
from episteme.domains import api
from . import inventory, programs
from .capture import capture

PACK_ID = "resumption_evidence_v1"
PACK_VERSION = "1"
METRIC = "captured_bytes"
OUTPUTS = {"raw_data": "raw.json", "metrics": "metrics.json"}
CAUTIONS = ["Artifact integrity only; no validation of scientific claims or completeness of original collection.",
            "Protocol/tasks/results were previously observed; this is an exploratory offline audit, not a new preregistered scientific experiment.",
            "E0 remains not passed; no independent human scientific review has occurred.",
            "Same-author reanalysis of the same bytes is not independent replication.",
            "Same-user local subprocess and uv closure are not a security sandbox."]
MANIFEST = {"contract_version": 1, "pack_id": PACK_ID, "pack_version": PACK_VERSION,
    "description": "Explicit research artifact roster, byte hashes, JSON readability, and exact offline replay.",
    "roster_semantics": ["frozen_unit_index"],
    "metrics": [{"name": METRIC, "unit": "bytes per artifact", "description": "Verified captured bytes; not a scientific effect."}],
    "outputs": {"raw_data": {"path": "raw.json", "schema_id": PACK_ID + "/raw-v1"},
                "metrics": {"path": "metrics.json", "schema_id": PACK_ID + "/metrics-v1"}},
    "numeric_tolerance": 0, "hidden_inputs": [], "execution_profiles": ["uv_locked_python_v2"],
    "statistical_capabilities": list(api.STATISTICAL_FIELDS), "interpretation_cautions": CAUTIONS, "capture": True}


def describe():
    return api.ParameterCatalog(schema_version=1, pack_id=PACK_ID, pack_version=PACK_VERSION,
        description="Artifact integrity only, with an explicit immutable manifest.",
        parameters_schema={"type": "object", "additionalProperties": False, "required": ["manifest_sha256"],
            "properties": {"manifest_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}},
        metric=METRIC, outputs=OUTPUTS, limitations=CAUTIONS)


def validate_parameters(parameters):
    describe().validate_parameters(api.thaw(parameters))


def compiled(request):
    validate_parameters(request.parameters)
    inventory.require(request.capture is not None and not api.thaw(request.host_inputs), "Explicit captured roster required")
    files = dict(request.capture.files); manifest = inventory.verify(files)
    inventory.require(inventory.sha(files["manifest.json"]) == request.parameters["manifest_sha256"], "Manifest pin differs")
    return inventory.compiled(manifest, files)


def compile_protocol(request):
    data = compiled(request); n = len(data["artifacts"]); key = inventory.sha(inventory.canonical(data))
    rule = "One offline byte check and one same-data reanalysis per declared artifact, no exclusions or interim selection."
    design = {"schema_version": 1, "mode": "exploratory", "experimental_unit": "artifact",
        "estimand": "Mean captured byte count over the explicit artifact roster; no scientific estimand.",
        "primary_metric": {"name": METRIC, "unit": "bytes per artifact"}, "secondary_metrics": [],
        "sample_size": n, "sample_size_rationale": "All explicitly listed artifacts; not a scientific power calculation.",
        "uncertainty": {"method": "not_applicable", "resampling_unit": None, "rationale": "Exact finite-roster byte arithmetic."},
        "exclusions": [], "stopping_rule": {"kind": "fixed_sample", "rule": rule},
        "multiple_testing": {"family": [], "correction": "not_applicable", "rationale": "No scientific tests."},
        "data_splits": [{"id": "already_observed_resumption", "digest": key, "role": "discovery", "exposure_policy": "open"}]}
    return api.ProtocolDraft(schema_version=1, design="Previously observed research artifacts; integrity audit only.",
        analysis_plan="Check every declared source hash and size, JSON readability, then exact same-data reanalysis.",
        metric=METRIC, stopping_rule=rule, statistical_design=design, roster=list(range(n)),
        roster_semantics="frozen_unit_index", sample_size_scope="total", run_limit=2*n,
        replication_tolerance=0, seen_data=[key])


def compile_execution(request):
    data = compiled(request)
    return api.ExecutionPlanV2(
        primary_program=api.SourceTree(entry_point="main.py", files={"main.py": (programs.PRIMARY + programs.TAIL).encode()}),
        reanalysis_program=api.SourceTree(entry_point="reanalyse.py", files={"reanalyse.py": (programs.REANALYSIS + programs.TAIL).encode()}),
        input=inventory.canonical(data), outputs=OUTPUTS, wall_seconds=60, max_output_bytes=64*1024*1024,
        required_capabilities=["locked_environment", "workspace_outside_store"],
        project={"pyproject.toml": programs.PYPROJECT, "uv.lock": programs.UV_LOCK}, variables={"PYTHONHASHSEED": "0"})


def validate_protocol(context):
    p = context.protocol
    inventory.require(p["metric"] == METRIC and p["protocol_mode"] == "exploratory" and
        p["data"] == context.execution_plan["input"]["sha256"] and p["data"] in p["seen_data"] and
        context.capture is not None and context.execution_plan["execution_profile"] == "uv_locked_python_v2",
        "Protocol escapes exploratory artifact-integrity scope")


def source(context, cas):
    files = {r["path"]: cas.read(r["sha256"]) for r in context.capture["inventory"]}
    manifest = inventory.verify(files); data = inventory.compiled(manifest, files)
    inventory.require(data == cas.json(context.protocol["data"], "frozen artifact input"), "Bound captured source differs")
    return data


def validate_outputs(context, cas):
    data = source(context, cas); checks = []
    for slot in context.slots:
        findings = []
        try:
            expected = inventory.expected_raw(data, slot["roster_unit"])
            inventory.require(cas.json(slot["outputs"]["raw_data"], "raw") == expected, "Raw artifact differs")
            metrics = cas.json(slot["outputs"]["metrics"], "metrics")
            inventory.require(metrics == {METRIC: inventory.metric(expected)}, "Recorded byte count differs")
        except (ValueError, KeyError, IndexError) as exc:
            findings.append(str(exc))
        checks.append(api.OutputCheck(schema_version=1, slot=slot["slot"], roster_unit=slot["roster_unit"], mode=slot["mode"],
            result=slot["result"], raw_data=slot["outputs"]["raw_data"], metrics=slot["outputs"]["metrics"],
            status="failed" if findings else "passed", findings=findings))
    return checks


def recompute_metrics(context, cas):
    data = source(context, cas); rows = []
    for unit in context.draft.roster:
        primary = context.slot("primary:" + str(unit)); reanalysis = context.slot("reanalysis:" + str(unit))
        expected = inventory.expected_raw(data, unit)
        inventory.require(cas.json(primary["outputs"]["raw_data"], "raw") == expected and
            primary["outputs"]["raw_data"] == reanalysis["outputs"]["raw_data"], "Reanalysis changed source bytes")
        value = inventory.metric(expected)
        a = cas.json(primary["outputs"]["metrics"], "primary metric")[METRIC]
        b = cas.json(reanalysis["outputs"]["metrics"], "reanalysis metric")[METRIC]
        rows.append(api.Recomputation(schema_version=1, roster_unit=unit, metric=METRIC, recomputed=value,
            primary_recorded=a, reanalysis_recorded=b, primary_absolute_difference=abs(a-value),
            reanalysis_absolute_difference=abs(b-value), tolerance=0))
    return rows


def analyse(context, cas, checks, recomputations):
    inventory.require(all(c.status == "passed" for c in checks), "Artifact check failed")
    data = source(context, cas); design = context.draft.typed_design()
    values = {r.roster_unit: r.recomputed for r in recomputations}
    inventory.require(sorted(values) == list(context.draft.roster), "Missing artifact recomputation")
    mean = sum(values.values()) / len(values)
    report = api.StatisticalReport.from_dict({"schema_version": 1, "protocol_hash": context.protocol_hash,
        "estimand": api.supplied({"protocol_hash": context.protocol_hash, "text": design.estimand}),
        "estimator": api.supplied({"name": "finite_roster_byte_mean", "hook": "recompute_metrics", "description": "Exact byte counts."}),
        "point_estimate": api.supplied({"metric": METRIC, "unit": "bytes per artifact", "value": mean,
            "by_roster_unit": [{"roster_unit": i, "value": values[i]} for i in sorted(values)]}),
        "uncertainty": api.not_applicable("Exact arithmetic, no population inference."),
        "confidence_interval": api.not_applicable("No scientific interval."),
        "effect_size": api.not_supplied("Artifact bytes are not a scientific effect."),
        "assumptions": api.supplied([{"assumption": "The explicit index covers the intended research artifacts.",
            "status": "unchecked", "reference": "This stage verifies indexed bytes only; original collection completeness is not assessed."}]),
        "sample_size": api.supplied({"experimental_unit": "artifact", "unit_scope": "total", "planned": design.sample_size,
            "planned_total": design.sample_size, "analysed": len(values), "exclusions": [], "missing_slots": []}),
        "multiple_testing": api.not_applicable("No tests."),
        "stopping_rule": api.supplied({"rule_sha256": inventory.sha(design.stopping_rule.rule.encode()), "roster_complete": True, "interim_looks": 0}),
        "sensitivity_analysis": api.supplied([]), "deviations": api.supplied([])})
    return api.AnalysisReport(pack_id=PACK_ID, pack_version=PACK_VERSION, protocol_hash=context.protocol_hash,
        statement="Explicit artifact roster was hash-checked and replayed; scientific conclusions remain unassessed.",
        limitations=CAUTIONS, outcome="inconclusive", inference_mode="exploratory",
        details={"artifact_count": len(values), "total_captured_bytes": sum(values.values()),
                 "manifest_sha256": data["manifest_sha256"], "scientific_validity": "not_assessed"}, statistical_report=report)
