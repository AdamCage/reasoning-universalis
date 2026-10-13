"""Development-only DomainPack v1 over real, immutable external reasoning bytes."""
import json
import hashlib
import math
from episteme.domains import api
from . import inventory, programs
from .capture import capture

PACK_ID = 'reasoning_universalis_v1'
PACK_VERSION = '1'
METRIC = 'segment_count_delta'
OUTPUTS = {'raw_data': 'raw.json', 'metrics': 'metrics.json'}
CONTRASTS = ['S2-S1', 'S1-S2', 'S2-S2']
CAUTIONS = ['Development-only imported observations; E0 not passed, no H0-H7 result.',
            'External RouterAI inference is not locally managed execution.',
            'Research BPE token intervals are not model tokenizer intervals.',
            'Same-author second implementation is not independent scientific replication.',
            'uv_locked_python_v2 and same-user hook subprocess are not a sandbox.']
MANIFEST = {'contract_version': 1, 'pack_id': PACK_ID, 'pack_version': PACK_VERSION,
            'description': 'Offline segment-count contrast bound to real external raw observations.',
            'roster_semantics': ['frozen_unit_index'],
            'metrics': [{'name': METRIC, 'unit': 'segments per trace', 'description': 'Mean paired count delta within root.'}],
            'outputs': {'raw_data': {'path': 'raw.json', 'schema_id': PACK_ID+'/raw-v1'},
                        'metrics': {'path': 'metrics.json', 'schema_id': PACK_ID+'/metrics-v1'}},
            'numeric_tolerance': 0.0, 'hidden_inputs': [], 'execution_profiles': ['uv_locked_python_v2'],
            'statistical_capabilities': list(api.STATISTICAL_FIELDS), 'interpretation_cautions': CAUTIONS,
            'capture': True}


def describe():
    return api.ParameterCatalog(schema_version=1, pack_id=PACK_ID, pack_version=PACK_VERSION,
                                description='Development contrasts; no confirmatory/human approval parameter.',
                                parameters_schema={'type': 'object', 'additionalProperties': False,
                                                   'required': ['contrast', 'bundle_digest', 'method_digest'],
                                                   'properties': {'contrast': {'enum': CONTRASTS},
                                                                  'bundle_digest': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                                                                  'method_digest': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}},
                                metric=METRIC, outputs=OUTPUTS, limitations=CAUTIONS)


def validate_parameters(parameters):
    describe().validate_parameters(api.thaw(parameters))


def compiled(request):
    parameters = api.thaw(request.parameters); validate_parameters(parameters)
    inventory.require(request.capture is not None and not api.thaw(request.host_inputs), 'Needs captured external bundle, no implicit host inputs')
    bundle = inventory.verify(dict(request.capture.files))
    key = inventory.sha(request.capture.files['bundle.json'])
    inventory.require(key == parameters['bundle_digest'] and bundle['method_digest'] == parameters['method_digest'], 'Wrong source or measurement binding')
    return bundle, inventory.canonical({'source_bundle': bundle, 'source_bundle_digest': key, 'contrast': parameters['contrast']})


def compile_protocol(request):
    bundle, data = compiled(request); n = len(bundle['roots']); key = inventory.sha(data)
    rule = 'One offline primary and one same-data reanalysis per frozen development root; no exclusions or interim selection.'
    design = {'schema_version': 1, 'mode': 'exploratory', 'experimental_unit': 'task_root',
              'estimand': 'Mean paired segmentation-count delta in this observed development root roster; no population claim.',
              'primary_metric': {'name': METRIC, 'unit': 'segments per trace'}, 'secondary_metrics': [],
              'sample_size': n, 'sample_size_rationale': 'All observed roots; not a scientific power calculation.',
              'uncertainty': {'method': 'not_applicable', 'resampling_unit': None,
                              'rationale': 'Descriptive development arithmetic; no population inference.'},
              'exclusions': [], 'stopping_rule': {'kind': 'fixed_sample', 'rule': rule},
              'multiple_testing': {'family': [], 'correction': 'not_applicable', 'rationale': 'No significance tests.'},
              'data_splits': [{'id': 'stage2_open_development', 'digest': key, 'role': 'discovery', 'exposure_policy': 'open'}]}
    return api.ProtocolDraft(schema_version=1, design='External observed bytes, all development; E0 not passed.',
                             analysis_plan='Recompute paired segment counts from exact raw-linked segment inventories.',
                             metric=METRIC, stopping_rule=rule, statistical_design=design, roster=list(range(n)),
                             roster_semantics='frozen_unit_index', sample_size_scope='total', run_limit=2*n,
                             replication_tolerance=0, seen_data=sorted({key}))


def compile_execution(request):
    _, data = compiled(request)
    return api.ExecutionPlanV2(primary_program=api.SourceTree(entry_point='main.py', files={'main.py': (programs.PRIMARY+programs.TAIL).encode()}),
                               reanalysis_program=api.SourceTree(entry_point='reanalyse.py', files={'reanalyse.py': (programs.REANALYSIS+programs.TAIL).encode()}),
                               input=data, outputs=OUTPUTS, wall_seconds=60, max_output_bytes=4*1024*1024,
                               required_capabilities=['locked_environment', 'workspace_outside_store'],
                               project={'pyproject.toml': programs.PYPROJECT, 'uv.lock': programs.UV_LOCK},
                               variables={'PYTHONHASHSEED': '0'})


def validate_protocol(context):
    protocol = context.protocol
    inventory.require(protocol['metric'] == METRIC and protocol['protocol_mode'] == 'exploratory' and
                      protocol['data'] == context.execution_plan['input']['sha256'] and
                      protocol['data'] in protocol['seen_data'] and context.capture is not None and
                      context.execution_plan['execution_profile'] == 'uv_locked_python_v2', 'Protocol escapes development/external evidence boundary')


def source(context, cas):
    envelope = cas.json(context.protocol['data'], 'bound input')
    files = {row['path']: cas.read(row['sha256']) for row in context.capture['inventory']}
    bundle = inventory.verify(files)
    inventory.require(envelope['source_bundle'] == bundle and envelope['source_bundle_digest'] == inventory.sha(files['bundle.json']) and
                      envelope['contrast'] == context.parameters['contrast'], 'Execution source bundle differs from captured raw')
    return bundle, envelope['source_bundle_digest']


def validate_outputs(context, cas):
    bundle, key = source(context, cas); checks = []
    for slot in context.slots:
        findings = []
        try:
            expected = inventory.root_raw(bundle, slot['roster_unit'], context.parameters['contrast'], key)
            raw = cas.json(slot['outputs']['raw_data'], 'measured raw')
            inventory.require(raw == expected, 'Measured raw differs from frozen observations')
            metrics = cas.json(slot['outputs']['metrics'], 'metrics')
            inventory.require(set(metrics) == {METRIC} and type(metrics[METRIC]) in (int, float) and math.isfinite(metrics[METRIC]) and
                              metrics[METRIC] == inventory.metric(expected), 'Metric differs from raw features')
        except (ValueError, KeyError, IndexError) as exc:
            findings.append(str(exc))
        checks.append(api.OutputCheck(schema_version=1, slot=slot['slot'], roster_unit=slot['roster_unit'], mode=slot['mode'],
                                      result=slot['result'], raw_data=slot['outputs']['raw_data'], metrics=slot['outputs']['metrics'],
                                      status='failed' if findings else 'passed', findings=findings))
    return checks


def recompute_metrics(context, cas):
    bundle, key = source(context, cas); rows = []
    for unit in context.draft.roster:
        primary, reanalysis = context.slot('primary:'+str(unit)), context.slot('reanalysis:'+str(unit))
        expected = inventory.root_raw(bundle, unit, context.parameters['contrast'], key)
        inventory.require(cas.json(primary['outputs']['raw_data'], 'raw') == expected and
                          primary['outputs']['raw_data'] == reanalysis['outputs']['raw_data'], 'Reanalysis changed raw observations')
        a = cas.json(primary['outputs']['metrics'], 'primary metric')[METRIC]
        b = cas.json(reanalysis['outputs']['metrics'], 'reanalysis metric')[METRIC]
        value = inventory.metric(expected)
        rows.append(api.Recomputation(schema_version=1, roster_unit=unit, metric=METRIC, recomputed=value,
                                      primary_recorded=a, reanalysis_recorded=b, primary_absolute_difference=abs(a-value),
                                      reanalysis_absolute_difference=abs(b-value), tolerance=context.numeric_tolerance))
    return rows


def analyse(context, cas, checks, recomputations):
    inventory.require(all(check.status == 'passed' for check in checks), 'Pack output check failed')
    bundle, key = source(context, cas); design = context.draft.typed_design()
    values = {row.roster_unit: row.recomputed for row in recomputations}
    inventory.require(sorted(values) == list(context.draft.roster), 'Missing root recomputation')
    mean = sum(values.values())/len(values)
    report = api.StatisticalReport.from_dict({
        'schema_version': 1, 'protocol_hash': context.protocol_hash,
        'estimand': api.supplied({'protocol_hash': context.protocol_hash, 'text': design.estimand}),
        'estimator': api.supplied({'name': 'paired_segment_count_delta', 'hook': 'recompute_metrics', 'description': 'Average paired count delta within each task root.'}),
        'point_estimate': api.supplied({'metric': METRIC, 'unit': 'segments per trace', 'value': mean,
                                      'by_roster_unit': [{'roster_unit': i, 'value': values[i]} for i in sorted(values)]}),
        'uncertainty': api.not_applicable('Preregistered development arithmetic without population inference.'),
        'confidence_interval': api.not_supplied('E0 not passed; no scientific interval claimed.'),
        'effect_size': api.not_supplied('Count delta is a technical feature, not an H0-H7 effect.'),
        'assumptions': api.supplied([{'assumption': 'Semantic measurement is scientifically valid.', 'status': 'unchecked', 'reference': 'E0 not passed.'}]),
        'sample_size': api.supplied({'experimental_unit': 'task_root', 'unit_scope': 'total', 'planned': design.sample_size,
                                    'planned_total': design.sample_size, 'analysed': len(values), 'exclusions': [], 'missing_slots': []}),
        'multiple_testing': api.not_applicable('No significance tests preregistered.'),
        'stopping_rule': api.supplied({'rule_sha256': inventory.sha(design.stopping_rule.rule.encode()), 'roster_complete': True, 'interim_looks': 0}),
        'sensitivity_analysis': api.supplied([]), 'deviations': api.supplied([])})
    return api.AnalysisReport(pack_id=PACK_ID, pack_version=PACK_VERSION, protocol_hash=context.protocol_hash,
                              statement=f'Development segmentation count delta: {mean}; raw-linked technical arithmetic only, scientific outcome unresolved.',
                              limitations=CAUTIONS, outcome='inconclusive', inference_mode='exploratory',
                              details={'mean': mean, 'roots': bundle['roots'], 'observed_attempts': len(bundle['observations']),
                                       'incomplete_or_failed': sum(r['status'] != 'completed' for r in bundle['observations']),
                                       'source_bundle_digest': key, 'dataset_digest': bundle['dataset_digest']}, statistical_report=report)
