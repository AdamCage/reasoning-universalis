"""Immutable observation capture and explicit attempt/schema/provenance records."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
from measurement.core import digest, text_hash
from stage0.traces import inspect_trace
from stage0.runner import capture_body


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON')
    value = json.loads(data, object_pairs_hook=unique, parse_constant=invalid)
    canonical(value)
    return value


class ObservationStore:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data):
        if type(data) is not bytes:
            raise ValueError('CAS takes bytes')
        key = hashlib.sha256(data).hexdigest(); target = self.root/key
        if target.is_symlink():
            raise ValueError('CAS link forbidden')
        try:
            with target.open('xb') as out:
                out.write(data)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError('CAS corruption')
        return key

    def json(self, value):
        return self.put(canonical(value))

    def read(self, key):
        if not re.fullmatch('[0-9a-f]{64}', key):
            raise ValueError('Invalid CAS digest')
        path = self.root/key
        if path.is_symlink():
            raise ValueError('CAS link forbidden')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != key:
            raise ValueError('CAS corruption')
        return data

    def record_attempt(self, attempt_id, request_bytes, response_bytes, http_status,
                       task, protocol, execution, verifier=None, secret=None,
                       historical_envelope=False):
        # Capture safe raw before parsing. Failed and unknown attempts remain immutable.
        request = capture_body(request_bytes, secret)
        response = capture_body(response_bytes, secret)
        req_key = self.put(base64.b64decode(request['body_base64']))
        raw_key = self.put(base64.b64decode(response['body_base64']))
        now = datetime.now(timezone.utc).isoformat()
        record = {'schema_version': 1, 'attempt_id': attempt_id,
                  'identity': {'study_id': protocol['study_id'], 'problem_id': task['task_id'],
                               'model_id': execution['model_id'], 'model_revision': execution.get('model_revision', 'unknown'),
                               'trace_id': None, 'run_id': attempt_id, 'sample_index': execution.get('sample_index', 0)},
                  'inference': {'prompt_digest': text_hash(task['prompt']),
                                'decoding_config': execution.get('decoding_config', {}),
                                'seed': execution.get('seed'), 'runtime_manifest': execution,
                                'start_time': execution.get('start_time', 'unknown'),
                                'end_time': execution.get('end_time', 'unknown'), 'stop_reason': None},
                  'raw_observations': {'raw_request_digest': req_key, 'raw_response_digest': raw_key,
                                       'body_storage': response['body_storage'],
                                       'capture_kind': 'historical_envelope' if historical_envelope else 'HTTP_body',
                                       'visible_reasoning': '', 'final_answer': '', 'token_usage': {}},
                  'outcome': {'verifier_id': 'not_run', 'verifier_version': 'not_run',
                              'verdict': 'unavailable', 'verification_artifact': None, 'grading_uncertainty': True},
                  'provenance': {'dataset_digest': protocol['dataset_digest'],
                                 'task_digest': digest(task), 'task_set_digest': protocol['task_set_digest'],
                                 'split_id': 'development', 'split_digest': protocol['split_digest'],
                                 'method_digest': protocol['method_digest'], 'protocol_digest': digest(protocol),
                                 'source_code_digest': execution['source_code_digest'],
                                 'environment_digest': digest({'python': platform.python_version(), 'kind': 'offline_import'}),
                                 'parent_artifacts': [req_key, raw_key]},
                  'http_status': http_status, 'status': 'unknown' if http_status is None else 'failed',
                  'recorded_at': now, 'scientific_validity': 'not_assessed'}
        try:
            parsed = strict(self.read(raw_key))
            body = parsed['json'] if historical_envelope else parsed
            if not isinstance(body, dict) or not isinstance(body.get('id'), str) or not body['id']:
                raise ValueError('Missing generation identity or non-object response')
            if http_status != 200 or body.get('error') is not None:
                raise ValueError('HTTP/API failure')
            if body.get('model', '').casefold() != execution['model_id'].casefold():
                raise ValueError('Model drift')
            if execution.get('provider') and body.get('provider') != execution['provider']:
                raise ValueError('Provider drift')
            observation = inspect_trace(body)
            record['identity']['trace_id'] = body.get('id')
            record['inference']['stop_reason'] = observation['finish_reason']
            record['raw_observations'].update(visible_reasoning=observation['trace'],
                                            final_answer=observation['answer'], token_usage=body.get('usage', {}))
            record['status'] = 'completed' if observation['status'] == 'visible_trace_candidate' else 'incomplete'
            record['trace_admission'] = {'status': observation['status'],
                                        'review_reference': execution.get('trace_review_reference', 'not_reviewed'),
                                        'internal_computation_complete': 'not_established'}
            if verifier:
                outcome = verifier(task, observation['answer'])
                record['outcome'] = {**outcome, 'verification_artifact': self.json(outcome)}
        except (ValueError, KeyError, TypeError, UnicodeError, IndexError, AttributeError) as exc:
            record['parse_or_admission_error'] = type(exc).__name__
        record['run_digest'] = digest({k: v for k, v in record.items() if k != 'recorded_at'})
        return record, self.json(record)


def validate_record(record, cas):
    for group in ('identity', 'inference', 'raw_observations', 'outcome', 'provenance'):
        if type(record.get(group)) is not dict:
            raise ValueError('Missing observation group')
    raw = record['raw_observations']
    cas.read(raw['raw_request_digest']); response = cas.read(raw['raw_response_digest'])
    if record['status'] in ('completed', 'incomplete'):
        envelope = strict(response)
        body = envelope['json'] if raw['capture_kind'] == 'historical_envelope' else envelope
        observation = inspect_trace(body)
        if observation['trace'] != raw['visible_reasoning'] or observation['answer'] != raw['final_answer']:
            raise ValueError('Observation no longer equals original response')
        if body.get('id') != record['identity']['trace_id'] or body.get('model') != record['identity']['model_id']:
            raise ValueError('Observation identity drift')
    if record['run_digest'] != digest({k: v for k, v in record.items() if k not in ('recorded_at', 'run_digest')}):
        raise ValueError('Observation digest drift')
