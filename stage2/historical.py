"""Bound import of the public Stage 0 ZIP, without network or .env."""
import json
import hashlib
from pathlib import Path
import zipfile
from measurement.core import digest, split_manifest
from stage0.tasks import verify_answer
from .observations import ObservationStore, canonical
from .tokenization import ResearchBPE
from .segmentation import measure, transitions
from .datasets import generate, DOMAINS
from .representations import Tfidf, inputs as representation_inputs
from .discovery import StateDiscovery, nested_lexical_discovery


def prepare(output, archive='evidence/stage0-2026-10-12.zip'):
    archive_bytes = Path(archive).read_bytes()
    archive_digest = hashlib.sha256(archive_bytes).hexdigest()
    if archive_digest != '420949cd9176713534f1152be1a8cbfa90c7eace91e5b267aa9e6cfc1de7ba1d':
        raise ValueError('Historical archive differs from the published immutable evidence')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Import requires a new or empty directory')
    output.mkdir(parents=True, exist_ok=True)
    cas = ObservationStore(output/'artifacts-cas'); tasks = []; inputs = []
    method = {'revision': 'stage2-development-v1', 'methods': ['S1', 'S2', 'S3'], 'block_size': 64,
              'S1': 'operation-cue-heuristic-v1', 'S3': 'independent_research_bpe', 'E0': 'not_passed'}
    with zipfile.ZipFile(archive) as z:
        selected = sorted(n for n in z.namelist() if '/pilot-openai_' in n and n.endswith('-response.json'))
        review_name = next(n for n in z.namelist() if n.endswith('trace-review.json'))
        origin_manifest = z.read('manifest.json')
        origin_paths = {}
        review_key = cas.put(z.read(review_name)); budget_key = cas.put(z.read('evidence/stage0-budget.json'))
        for response_name in selected:
            directory = response_name.rsplit('/', 1)[0]; index = int(response_name.rsplit('-', 2)[1])
            context_bytes = z.read(directory+'/context.json'); context = json.loads(context_bytes)
            old = context['tasks'][index]; task_id = 'historical-stage0-'+old['id']
            task = {'task_id': task_id, 'root_id': task_id, 'domain': old['domain'],
                    'generator_id': 'stage0-fixed-manifest', 'prompt': old['prompt'],
                    'previously_observed': True, 'forced_split': 'development'}
            tasks.append(task)
            request_name = response_name.replace('-response.json', '-request.json')
            request_bytes, response_bytes = z.read(request_name), z.read(response_name)
            origin_paths['import-'+task_id] = {'request': request_name, 'response': response_name}
            context_key = cas.put(context_bytes); body = json.loads(response_bytes)['json']
            req = json.loads(request_bytes)['request']
            execution = {'model_id': body['model'], 'provider': body.get('provider', 'unknown'),
                         'model_revision': 'unknown', 'family': 'openai-gpt-oss', 'quantization': 'unknown',
                         'tokenizer_revision': 'unknown', 'inference_engine': 'unknown', 'inference_engine_version': 'unknown',
                         'gpu_model': 'unknown', 'cuda_runtime': 'unknown', 'driver': 'unknown',
                         'dtype': 'unknown', 'license': 'Apache-2.0 (historical MODEL_LICENSES report)',
                         'seed': req.get('seed'), 'decoding_config': {k: req.get(k) for k in ('temperature', 'top_p', 'max_tokens')},
                         'start_time': 'unknown', 'end_time': body.get('created', 'unknown'),
                         'source_code_digest': digest(context['source_sha256']), 'historical_source_git_head': context['git_head'],
                         'historical_context_digest': context_key, 'trace_review_reference': review_key,
                         'historical_budget_digest': budget_key, 'external_inference': True}
            inputs.append((task, old, request_bytes, response_bytes, execution))
    manifest = split_manifest(tasks)
    protocol = {'study_id': 'reasoning-universalis-stage2-development', 'mode': 'development',
                'dataset_digest': digest(tasks), 'task_set_digest': digest(sorted(tasks, key=lambda t: t['task_id'])),
                'split_digest': manifest['manifest_digest'], 'method_digest': digest(method),
                'G1_approved_commit': '68fc12da05000674e3d770a07e449c37a4fbc119', 'E0': 'not_passed'}
    observations = []
    for task, old, request, response, execution in inputs:
        def verifier(_task, answer, old=old):
            result = verify_answer(old, answer)
            return {'verifier_id': 'stage0-fixed-independent-marker', 'verifier_version': 'stage0-v1',
                    'verdict': 'correct' if result['correct'] else 'incorrect', 'grading_uncertainty': result['parsed'] is None}
        record, key = cas.record_attempt('import-'+task['task_id'], request, response, 200,
                                         task, protocol, execution, verifier, historical_envelope=True)
        observations.append(record)
    eligible = [r for r in observations if r['status'] == 'completed']
    tokenizer = ResearchBPE().fit([r['raw_observations']['visible_reasoning'] for r in eligible],
                                  [r['identity']['problem_id'] for r in eligible])
    rows = []; maps = {}
    for record in eligible:
        identity = record['identity']; task = next(t for t in tasks if t['task_id'] == identity['problem_id'])
        trace = {'trace_id': identity['trace_id'], 'task_id': task['task_id'], 'root_id': task['root_id'],
                 'family': 'openai-gpt-oss', 'split': 'development', 'visible_reasoning': record['raw_observations']['visible_reasoning'],
                 'raw_response_sha256': record['raw_observations']['raw_response_digest']}
        mapping = tokenizer.mapping(trace['visible_reasoning']); maps[trace['trace_id']] = mapping
        for method_id in method['methods']:
            rows.extend(measure(trace, method_id, mapping, method['block_size']))
    transitions(rows)
    bundle = {'schema_version': 1, 'purpose': 'stage2_development_not_E0',
              'historical_archive_sha256': archive_digest, 'origin_paths': origin_paths, 'tasks': tasks,
              'split_manifest': manifest, 'dataset_digest': protocol['dataset_digest'], 'task_set_digest': protocol['task_set_digest'],
              'method_digest': protocol['method_digest'], 'method': method, 'protocol': protocol,
              'observations': observations, 'segments': rows, 'token_maps': maps,
              'roots': sorted({t['root_id'] for t in tasks}), 'external_inference': True,
              'scientific_validity': 'not_assessed', 'E0': 'not_passed'}
    native = [r for r in rows if r['method'] == 'S2']
    representations = []
    for mode in ('Local', 'Contextual'):
        prepared = representation_inputs(native, mode)
        fit_rows = [{**row, 'text': observation['input']} for row, observation in zip(native, prepared)]
        lexical = Tfidf().fit(fit_rows, manifest)
        for row, observation in zip(native, prepared):
            representations.append({**observation, 'representation': 'TF-IDF', 'fit_revision': lexical.revision,
                                    'training_provenance': lexical.provenance, 'vector': lexical.transform(observation['input'])})
    nested = nested_lexical_discovery(native, manifest, candidates=(2, 3, 4), outer_folds=3, inner_folds=2)
    selected = min(fold['selected_k'] for fold in nested['outer_folds'])
    lexical = Tfidf().fit(native, manifest)
    states = StateDiscovery().fit(native, [lexical.transform(row['text']) for row in native], manifest, selected)
    state_document = {'status': 'development_uninterpreted_not_E0', 'nested_diagnostics': nested,
                      'selection': 'smallest_outer_selected_K_engineering_development_rule', 'selected_k': selected,
                      'fit_revision': states.revision, 'fit_provenance': states.provenance,
                      'states': [{'segment_id': row['segment_id'], **states.predict(lexical.transform(row['text']))} for row in native]}
    representation_bytes = canonical({'schema_version': 1, 'status': 'development_not_E0', 'rows': representations})
    state_bytes = canonical(state_document)
    bundle['representation_artifact_digest'] = hashlib.sha256(representation_bytes).hexdigest()
    bundle['state_artifact_digest'] = hashlib.sha256(state_bytes).hexdigest()
    source = output/'source'; source.mkdir(); (source/'artifacts').mkdir()
    (source/'representations-lexical.json').write_bytes(representation_bytes)
    (source/'lexical-states.json').write_bytes(state_bytes)
    (source/'bundle.json').write_bytes(canonical(bundle))
    (source/'origin-manifest.json').write_bytes(origin_manifest)
    for path in cas.root.iterdir():
        (source/'artifacts'/(path.name+'.bin')).write_bytes(cas.read(path.name))
    files = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source.rglob('*') if p.is_file()}
    (source/'inventory.json').write_bytes(canonical({'files': files}))
    (output/'development-tasks.json').write_bytes(canonical([generate(domain, seed, level) for domain in DOMAINS
                                                            for level in ('easy', 'medium', 'hard') for seed in range(3)]))
    return source
