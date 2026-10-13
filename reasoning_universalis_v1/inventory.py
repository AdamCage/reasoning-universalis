"""Pure checks linking measured segments to immutable external observations."""
import hashlib
import math
import json
from episteme.domains import api


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def explicit(body):
    choices = body.get('choices', [])
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    for key in ('reasoning', 'reasoning_content'):
        if isinstance(message.get(key), str) and message[key].strip():
            return message[key]
    return '\n'.join(d['text'] for d in message.get('reasoning_details', [])
                     if d.get('type') == 'reasoning.text' and d.get('text'))


def verify(files):
    require('inventory.json' in files and 'bundle.json' in files, 'Missing captured bundle inventory')
    inventory = api.strict_loads(files['inventory.json'])
    require(set(files) == set(inventory['files']) | {'inventory.json'}, 'Capture inventory differs')
    for path, key in inventory['files'].items():
        require(sha(files[path]) == key, 'Captured bytes changed: '+path)
    require('origin-manifest.json' in files and sha(files['origin-manifest.json']) == 'a6aa1248ddce0c111bcdf5c4d31512b41f134ebca208d891d1e6781e414438e8', 'Published origin manifest differs')
    origins = {r['path']: r['sha256'] for r in api.strict_loads(files['origin-manifest.json'])['files']}
    bundle = api.strict_loads(files['bundle.json'])
    require(bundle['schema_version'] == 1 and bundle['purpose'] == 'stage2_development_not_E0', 'Wrong bundle schema')
    require(bundle['historical_archive_sha256'] == '420949cd9176713534f1152be1a8cbfa90c7eace91e5b267aa9e6cfc1de7ba1d', 'Historical evidence identity changed')
    require(bundle['method_digest'] == sha(canonical(bundle['method'])), 'Method revision drift')
    require(bundle['split_manifest']['manifest_digest'] == sha(canonical({k: v for k, v in bundle['split_manifest'].items() if k != 'manifest_digest'})), 'Changed split manifest')
    tasks = {t['task_id']: t for t in bundle['tasks']}
    require(len(tasks) == len(bundle['tasks']), 'Duplicate task identity')
    require(bundle['dataset_digest'] == sha(canonical(bundle['tasks'])), 'Changed dataset identity')
    require(bundle['task_set_digest'] == sha(canonical(sorted(bundle['tasks'], key=lambda t: t['task_id']))), 'Changed task set')
    assignment = {t['task_id']: t for t in bundle['split_manifest']['tasks']}
    require(set(tasks) == set(assignment), 'Split roster differs from tasks')
    for task in tasks.values():
        declared = assignment[task['task_id']]
        require(declared['root_id'] == task['root_id'] and declared['split'] == 'development' and
                declared['prompt_sha256'] == sha(task['prompt'].encode()), 'Raw tasks cross split or prompt binding')
    traces = {}; generations = set(); raw_keys = set(); attempts = set()
    for record in bundle['observations']:
        require(record['attempt_id'] not in attempts, 'Duplicate attempt')
        attempts.add(record['attempt_id'])
        identity, raw, provenance = record['identity'], record['raw_observations'], record['provenance']
        task = tasks.get(identity['problem_id'])
        require(task is not None and provenance['task_digest'] == sha(canonical(task)), 'Foreign raw task binding')
        require(provenance['protocol_digest'] == sha(canonical(bundle['protocol'])), 'Observation protocol drift')
        require(provenance['dataset_digest'] == bundle['dataset_digest'] and provenance['split_id'] == 'development' and
                provenance['split_digest'] == bundle['split_manifest']['manifest_digest'] and
                provenance['method_digest'] == bundle['method_digest'], 'Observation provenance changed')
        require(record['run_digest'] == sha(canonical({k: v for k, v in record.items() if k not in ('recorded_at', 'run_digest')})), 'Observation record changed')
        for field in ('raw_request_digest', 'raw_response_digest'):
            key = raw[field]; require('artifacts/'+key+'.bin' in files, 'Raw parent missing')
            require(sha(files['artifacts/'+key+'.bin']) == key, 'Raw parent digest mismatch')
        origin = bundle['origin_paths'].get(record['attempt_id'])
        require(origin is not None and origins.get(origin['request']) == raw['raw_request_digest'] and
                origins.get(origin['response']) == raw['raw_response_digest'], 'Observation differs from the published source attempt')
        if record['status'] not in ('completed', 'incomplete'):
            continue  # Failed/unknown raw is retained in the inventory and denominators.
        source = api.strict_loads(files['artifacts/'+raw['raw_response_digest']+'.bin'])
        body = source['json'] if raw['capture_kind'] == 'historical_envelope' else source
        require(explicit(body) == raw['visible_reasoning'] and body.get('id') == identity['trace_id'] and
                body.get('model') == identity['model_id'], 'Raw observation differs from source')
        require(raw['token_usage'] == body.get('usage', {}) and raw['final_answer'] == (body['choices'][0]['message'].get('content') or ''), 'Raw answer/usage differs')
        require(record['inference']['stop_reason'] == body['choices'][0]['finish_reason'], 'Stop reason differs')
        require(body.get('provider', 'unknown') == record['inference']['runtime_manifest'].get('provider', 'unknown'), 'Provider changed')
        request_source = api.strict_loads(files['artifacts/'+raw['raw_request_digest']+'.bin'])
        request = request_source.get('request', request_source.get('body', request_source))
        require(request.get('model') == identity['model_id'], 'Request model differs')
        require(record['inference']['seed'] == request.get('seed') and
                all(value == request.get(key) for key, value in record['inference']['decoding_config'].items()), 'Decoding identity differs')
        require(any(task['prompt'] == message.get('content') for message in request.get('messages', [])), 'Request prompt differs')
        require(identity['trace_id'] not in generations and raw['raw_response_digest'] not in raw_keys, 'Repeated generation is not independent replication')
        generations.add(identity['trace_id']); raw_keys.add(raw['raw_response_digest'])
        traces[identity['trace_id']] = record
    for row in bundle['segments']:
        record = traces.get(row['trace_id'])
        require(record is not None and record['status'] == 'completed', 'Segment without eligible raw trace')
        text = record['raw_observations']['visible_reasoning']
        task = tasks[row['task_id']]
        require(type(row['char_start']) is int and type(row['char_end']) is int and
                0 <= row['char_start'] < row['char_end'] <= len(text), 'Invalid segment bounds')
        require(row['root_id'] == task['root_id'] and row['split'] == 'development', 'Segment split/root drift')
        require(row['trace_sha256'] == sha(text.encode()) and row['raw_response_sha256'] == record['raw_observations']['raw_response_digest'] and
                row['text'] == text[row['char_start']:row['char_end']], 'Segment differs from raw trace')
        token_map = bundle['token_maps'][row['trace_id']]
        require(token_map['text_sha256'] == row['trace_sha256'], 'Token map text mismatch')
        require(''.join(token_map['token_texts']) == text and token_map['tokenizer_scope'] == 'independent_research_not_model', 'Research tokenizer misrepresented')
        expected_revision = sha(canonical({'algorithm': 'unicode-initial-bpe-v1', 'merges': token_map['merges'], 'provenance': token_map['training_provenance']}))
        require(token_map['tokenizer_revision'] == expected_revision, 'Tokenizer revision drift')
        offsets = token_map['offsets']
        require(len(offsets) == len(token_map['token_texts']) and offsets[0][0] == 0 and offsets[-1][1] == len(text) and
                all(type(a) is int and type(b) is int and 0 <= a < b <= len(text) and text[a:b] == token for (a, b), token in zip(offsets, token_map['token_texts'])) and
                all(a[1] == b[0] for a, b in zip(offsets, offsets[1:])), 'Tokenizer offsets drift')
        overlap = [i for i, (a, b) in enumerate(offsets) if a < row['char_end'] and b > row['char_start']]
        require(overlap and row['token_start'] == min(overlap) and row['token_end'] == max(overlap)+1, 'Token interval drift')
    groups = {}
    for row in bundle['segments']:
        groups.setdefault((row['trace_id'], row['method']), []).append(row)
    for (trace, method), rows in groups.items():
        rows.sort(key=lambda r: r['position'])
        text = traces[trace]['raw_observations']['visible_reasoning']
        require([r['position'] for r in rows] == list(range(len(rows))) and rows[0]['char_start'] == 0 and
                rows[-1]['char_end'] == len(text) and ''.join(r['text'] for r in rows) == text and
                all(a['char_end'] == b['char_start'] for a, b in zip(rows, rows[1:])), 'Segment gaps/cross-trajectory edge')
    require(sha(files['representations-lexical.json']) == bundle['representation_artifact_digest'] and
            sha(files['lexical-states.json']) == bundle['state_artifact_digest'], 'Representation/state artifact binding differs')
    native = {s['segment_id']: s for s in bundle['segments'] if s['method'] == 'S2'}
    representations = api.strict_loads(files['representations-lexical.json'])['rows']
    require(len(representations) == 2*len(native) and
            {(r['segment_id'], r['context_mode']) for r in representations} == {(key, mode) for key in native for mode in ('Local', 'Contextual')}, 'Representation roster differs')
    for row in representations:
        segment = native[row['segment_id']]
        require(row['input_sha256'] == sha(row['input'].encode()) and row['trace_sha256'] == segment['trace_sha256'] and
                row['measurement_config_digest'] == segment['measurement_config_digest'], 'Representation source drift')
        require(type(row['vector']) is list and row['vector'] and all(type(x) in (int, float) and math.isfinite(x) for x in row['vector']), 'Invalid lexical vector')
        if row['context_mode'] == 'Local':
            require(row['input'] == segment['text'], 'Local representation includes other context')
        else:
            before = sorted([s for s in native.values() if s['trace_id'] == segment['trace_id'] and s['position'] < segment['position']], key=lambda s: s['position'])[-2:]
            context = ''.join(s['text'] for s in before)[-1000:]
            require(row['input'] == context+segment['text'], 'Contextual representation looks ahead/crosses trace')
        require(set(row['training_provenance']['training_roots']) <= set(bundle['roots']), 'Representation fit sees foreign roots')
    states = api.strict_loads(files['lexical-states.json'])
    require({r['segment_id'] for r in states['states']} == set(native) and all(r['role'] == 'uninterpreted' for r in states['states']), 'Unvalidated functional labels in development state artifact')
    require(bundle['roots'] == sorted({task['root_id'] for task in tasks.values()}), 'Root roster changed')
    return bundle


def root_raw(bundle, index, contrast, source_digest):
    root = bundle['roots'][index]
    observations = [r for r in bundle['observations'] if next(t for t in bundle['tasks'] if t['task_id'] == r['identity']['problem_id'])['root_id'] == root]
    rows = [s for s in bundle['segments'] if s['root_id'] == root]
    return {'schema_version': 1, 'root_id': root, 'roster_unit': index, 'contrast': contrast,
            'source_bundle_digest': source_digest, 'observations': observations, 'segments': rows}


def metric(raw):
    left, right = raw['contrast'].split('-')
    # Mean difference per eligible trace, then one root is one estimator unit.
    traces = sorted({s['trace_id'] for s in raw['segments']})
    require(bool(traces), 'No measurable complete trace in root; do not replace missing with zero')
    values = []
    for trace in traces:
        selected = [s for s in raw['segments'] if s['trace_id'] == trace]
        require({left, right} <= {s['method'] for s in selected}, 'Missing paired segmentation')
        values.append(sum(s['method'] == left for s in selected)-sum(s['method'] == right for s in selected))
    return sum(values)/len(values)
