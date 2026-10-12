"""Serial, journaled RouterAI probes. Failed/unknown attempts remain in the ledger."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib import error, parse, request
import uuid

from .config import BASE_URL, Config, ConfigurationError, MODELS, EMBEDDERS
from .tasks import manifest, verify_answer
from .traces import inspect_trace, inspect_embeddings, segment


class StopRun(RuntimeError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def redact(text, key):
    # Includes JSON escapes and common URL/header encodings of a reflected key.
    for secret in (key, json.dumps(key)[1:-1], parse.quote(key, safe='')):
        text = text.replace(secret, '[REDACTED]')
    return text


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')


class Journal:
    def __init__(self, config, directory):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'EpistemeOS' / 'src'))
        from episteme.store import Store
        self.store = Store(config.store_root)
        self.key = config.key
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)

    def save(self, name, value):
        data = redact(encode(value).decode('utf-8'), self.key).encode('utf-8')
        path = self.directory / name
        path.write_bytes(data)
        artifact = self.store.put(data)
        return {'path': str(path), 'artifact': artifact, 'sha256': hashlib.sha256(data).hexdigest()}


def http(path, key=None, body=None, timeout=30):
    if not path.startswith('/') or path.startswith('//'):
        raise StopRun('Invalid RouterAI path')
    headers = {'Accept': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = request.Request(BASE_URL + path, data=encode(body) if body is not None else None,
                          headers=headers)
    started = time.monotonic()
    try:
        with request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            status, raw, meta = response.status, response.read(), dict(response.headers)
    except error.HTTPError as exc:
        status, raw, meta = exc.code, exc.read(), dict(exc.headers)
    except Exception as exc:
        # No exception string: upstream errors may reflect Authorization headers.
        return {'http_status': None, 'raw_body': None, 'network_error': type(exc).__name__,
                'elapsed_seconds': time.monotonic() - started, 'json': {}}
    captured = capture_body(raw, key)
    return {'http_status': status, **captured, 'headers': meta,
            'elapsed_seconds': time.monotonic() - started}


def capture_body(raw, key=None):
    """Preserve received bytes, except explicitly labelled secret redaction."""
    original_hash = hashlib.sha256(raw).hexdigest()
    safe = raw
    if key:
        for secret in (key, json.dumps(key)[1:-1], parse.quote(key, safe='')):
            safe = safe.replace(secret.encode('utf-8'), b'[REDACTED]')
    result = {'body_base64': base64.b64encode(safe).decode('ascii'),
              'body_sha256': hashlib.sha256(safe).hexdigest(),
              'body_storage': 'original_bytes' if safe == raw else 'redacted_bytes_original_not_retained',
              'received_body_sha256': original_hash, 'raw_body': None, 'json': {}}
    try:
        result['raw_body'] = safe.decode('utf-8')
    except UnicodeDecodeError:
        result['decode_error'] = 'invalid_utf8'
        return result
    try:
        value = json.loads(result['raw_body'])
        if isinstance(value, dict):
            result['json'] = value
        else:
            result['json_error'] = 'non_object_json'
    except ValueError:
        result['json_error'] = 'invalid_json'
    return result


def validate_review(config, review):
    if review.get('scope') != 'technical_probe_trace_review' or not review.get('models'):
        raise StopRun('Missing explicit full-trace review')
    for model, evidence in review['models'].items():
        if model not in MODELS or evidence.get('full_visible_trace') is not True:
            raise StopRun('Unapproved trace model')
        documents = {}
        for kind, hash_key in (('response', 'sha256'), ('request', 'request_sha256')):
            if not evidence.get(kind + '_path') or not evidence.get(hash_key):
                raise StopRun('Review requires both request and response hashes')
            path = Path(evidence[kind + '_path']).resolve()
            if not path.is_relative_to(config.root.resolve()) or not path.is_file():
                raise StopRun('Trace review evidence outside research root or missing')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != evidence[hash_key]:
                raise StopRun('Trace review evidence changed')
            documents[kind] = json.loads(data)
        sent, received = documents['request'], documents['response']
        body, payload = sent.get('request', {}), received.get('json', {})
        if sent.get('model') != model or body.get('model') != model or payload.get('model') != model:
            raise StopRun('Trace review model identity mismatch')
        if received.get('http_status') != 200 or payload.get('error') is not None or received.get('decode_error') or received.get('network_error'):
            raise StopRun('Trace review response unsuccessful')
        if body.get('reasoning', {}).get('enabled') is not True or body.get('include_reasoning') is not True:
            raise StopRun('Trace review request did not enable reasoning')
        if not evidence.get('provider') or evidence['provider'] != payload.get('provider'):
            raise StopRun('Trace review provider mismatch or missing')
        request_path, response_path = Path(evidence['request_path']), Path(evidence['response_path'])
        if request_path.parent.resolve() != response_path.parent.resolve() or request_path.name.removesuffix('-request.json') != response_path.name.removesuffix('-response.json'):
            raise StopRun('Review request and response are not the same recorded attempt')
        if inspect_trace(payload)['status'] != 'visible_trace_candidate':
            raise StopRun('Review cannot override missing, summary or truncated trace')
    return review


class Ledger:
    def __init__(self, path, cap):
        self.path, self.cap = path, cap
        self.rows = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

    @property
    def committed(self):
        return sum((Decimal(r['charged_or_reserved_rub']) for r in self.rows), Decimal(0))

    def reserve(self, amount, purpose):
        if amount <= 0 or self.committed + amount > self.cap:
            raise StopRun('Budget exhausted before network call')
        row = {'id': uuid.uuid4().hex, 'purpose': purpose, 'reservation_rub': str(amount),
               'charged_or_reserved_rub': str(amount), 'state': 'pending', 'reported_cost_rub': None}
        self.rows.append(row)
        self.flush()
        return row

    def finish(self, row, response):
        usage = response.get('json', {}).get('usage') or {}
        cost = usage.get('cost')
        if cost is None:
            cost = response.get('json', {}).get('cost')
        if cost is not None:
            try:
                cost = Decimal(str(cost))
                if not cost.is_finite() or cost < 0:
                    raise ValueError
                row['reported_cost_rub'] = str(cost)
                row['charged_or_reserved_rub'] = str(max(cost, Decimal(row['reservation_rub'])))
            except Exception:
                row['cost_parse_error'] = True
        row['state'] = 'finished' if response.get('http_status') is not None else 'unknown'
        self.flush()
        if self.committed > self.cap:
            raise StopRun('Reported spend exceeds budget; further calls stopped')

    def flush(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(encode(self.rows))
        os.replace(temp, self.path)


def rates(endpoint_response):
    endpoints = endpoint_response.get('json', {}).get('data', {}).get('endpoints', [])
    prices = []
    for endpoint in endpoints:
        units = endpoint.get('pricing_units', {})
        p = endpoint.get('pricing', {})
        if units.get('prompt') != 'token' or units.get('completion', 'token') != 'token':
            raise StopRun('Unknown pricing units; cannot reserve budget')
        prices.append((Decimal(str(p['prompt'])), Decimal(str(p.get('completion', 0)))))
        for variation in endpoint.get('variable_pricings', []):
            if variation.get('type') != 'prompt-threshold':
                raise StopRun('Unsupported variable pricing')
            prices.append((Decimal(str(variation.get('prompt', p['prompt']))),
                           Decimal(str(variation.get('completion', p.get('completion', 0))))))
    if not prices:
        return None
    return max(p[0] for p in prices), max(p[1] for p in prices)


def estimate(body, price):
    # Conservative input bound in UTF-8 bytes plus protocol/template overhead.
    n = len(encode(body)) + 2048
    output = body.get('max_tokens', 0)
    return max(Decimal('0.01'), (price[0] * n + price[1] * output) * 2)


def chat_body(config, model, prompt, enabled, max_tokens=None):
    return {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': max_tokens or config.max_tokens, 'temperature': config.temperature,
            'top_p': config.top_p, 'seed': config.seed, 'stream': False,
            'reasoning': {'enabled': enabled}, 'include_reasoning': True}


def run(config, tasks=6, review_path=None):
    if not 5 <= tasks <= len(manifest()):
        raise StopRun('Technical pilot currently supports 5 or 6 fixed tasks')
    tracked = subprocess.check_output(['git', 'ls-files', '--', '.env']).decode().strip()
    if tracked:
        raise StopRun('.env is tracked by Git')
    config.root.mkdir(parents=True, exist_ok=True)
    lock = config.root / 'stage0.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise StopRun('Stage-zero lock exists; inspect pending attempts before removing it') from None
    os.close(descriptor)
    journal = None
    try:
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        directory = config.root / 'stage0' / run_id
        journal = Journal(config, directory)
        ledger = Ledger(config.root / 'stage0-budget.json', config.budget)
        context = {'run_id': run_id, 'config': config.public(), 'tasks': manifest()[:tasks],
                   'purpose': 'technical_harness_validation_not_specification_5.5',
                   'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
                   'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(Path('stage0').glob('*.py'))},
                   'python': sys.version, 'actor': 'Codex (explicit user authorization 2026-10-12)'}
        journal.save('context.json', context)
        journal.save('source-snapshot.json', {str(p): p.read_bytes().decode('utf-8')
                                             for p in sorted(Path('stage0').glob('*.py'))})
        review = None
        if review_path is not None:
            review = validate_review(config, json.loads(Path(review_path).read_text(encoding='utf-8')))
            journal.save('trace-review.json', review)
        catalog = http('/models')
        journal.save('catalog.json', catalog)
        if catalog['http_status'] != 200:
            raise StopRun('Public catalog unavailable')
        prices, endpoint_records = {}, {}
        for model in MODELS + EMBEDDERS:
            ep = http('/models/' + model + '/endpoints')
            endpoint_records[model] = journal.save(model.replace('/', '_') + '-endpoints.json', ep)
            prices[model] = rates(ep)
        # For the absent identifier's diagnostic call use the maximum published
        # token rate across the entire public catalog, with a small output cap.
        token_prices = [m['pricing'] for m in catalog['json']['data']
                        if m.get('pricing_units', {}).get('prompt') == 'token'
                        and m.get('pricing_units', {}).get('completion') == 'token'
                        and 'text' in m.get('architecture', {}).get('input_modalities', [])
                        and m.get('architecture', {}).get('output_modalities') == ['text']]
        diagnostic_price = (max(Decimal(str(p.get('prompt', 0))) for p in token_prices),
                            max(Decimal(str(p.get('completion', 0))) for p in token_prices))
        observations = []

        def call(model, body, label, embedding=False):
            if model not in (EMBEDDERS if embedding else MODELS):
                raise StopRun('Model outside prescribed allowlist')
            price = prices[model] or diagnostic_price
            reservation = ledger.reserve(estimate(body, price), label)
            before = {'model': model, 'request': body, 'budget_reservation': dict(reservation)}
            journal.save(label + '-request.json', before)
            response = http('/embeddings' if embedding else '/chat/completions',
                            config.key, body, config.timeout)
            raw = journal.save(label + '-response.json', response)
            ledger.finish(reservation, response)
            result = {'label': label, 'model': model, 'request': body,
                      'http_status': response['http_status'], 'elapsed_seconds': response['elapsed_seconds'],
                      'raw': raw, 'usage': response.get('json', {}).get('usage'),
                      'provider': response.get('json', {}).get('provider'),
                      'returned_model': response.get('json', {}).get('model'),
                      'api_error': response.get('json', {}).get('error'),
                      'budget': dict(reservation)}
            if embedding:
                result['embedding'] = inspect_embeddings(response['json'], model, len(body['input']))
                if response['http_status'] != 200 or response.get('decode_error') or response.get('network_error'):
                    result['embedding'].update(valid=False, reason='unsuccessful HTTP response')
                result['analysis_usable'] = result['embedding']['valid']
            else:
                result['trace'] = inspect_trace(response['json'])
                if response.get('json', {}).get('model') != model:
                    result['trace']['status'] = 'unavailable' if not response.get('json', {}).get('choices') else 'model_mismatch'
                if response['http_status'] != 200 or response.get('json', {}).get('error') is not None:
                    result['trace']['status'] = 'unsuccessful_response'
                if review is not None and result['provider'] != review['models'][model]['provider']:
                    result['trace']['status'] = 'reviewed_provider_changed'
                result['analysis_usable'] = result['trace']['status'] == 'visible_trace_candidate'
            observations.append(result)
            journal.save('observations.json', observations)
            print(label, 'HTTP', response['http_status'], flush=True)
            return result

        if review_path is None:
            prompt = manifest()[0]['prompt']
            for i, model in enumerate(MODELS):
                for enabled in (True, False):
                    cap = config.max_tokens if prices[model] else 128
                    call(model, chat_body(config, model, prompt, enabled, cap),
                         f'probe-{i}-reasoning-{str(enabled).lower()}')
            for i, model in enumerate(EMBEDDERS):
                call(model, {'model': model, 'input': ['A implies B. A is true.', 'Therefore B is true.']},
                     f'embedding-probe-{i}', True)
        else:
            for model, evidence in review['models'].items():
                for i, task in enumerate(manifest()[:tasks]):
                    result = call(model, chat_body(config, model, task['prompt'], True), f'pilot-{model.replace("/", "_")}-{i}')
                    result['task_id'] = task['id']
                    result['verification'] = verify_answer(task, result['trace']['answer'])
                    result['segments'] = segment(result['trace']['trace'])
                    result['usable_trace'] = result['analysis_usable'] and bool(result['segments'])
                    journal.save('observations.json', observations)
                    if result['usable_trace']:
                        for j, embedder in enumerate(EMBEDDERS):
                            call(embedder, {'model': embedder, 'input': result['segments']},
                                 f'pilot-embedding-{model.replace("/", "_")}-{i}-{j}', True)
        failures = [r['label'] for r in observations if 'embedding' in r and not r['embedding']['valid']]
        if review is not None:
            failures += [r['label'] for r in observations if 'task_id' in r and not r['usable_trace']]
            expected_embeddings = len(review['models']) * tasks * len(EMBEDDERS)
            if sum('embedding' in r for r in observations) != expected_embeddings:
                failures.append('missing_required_pilot_embeddings')
        elif not any(r['analysis_usable'] for r in observations if 'trace' in r and r['request']['reasoning']['enabled']):
            failures.append('no_visible_trace_candidate')
        summary = {'run_id': run_id, 'directory': str(directory), 'observations': observations,
                   'process_completed': True, 'technical_criteria_met': not failures,
                   'failed_requirements': failures,
                   'data_usability': 'per_observation_analysis_usable_requires_scientific_validation',
                   'budget_cap_rub': str(config.budget), 'committed_rub': str(ledger.committed),
                   'reported_cost_rub': str(sum((Decimal(r['reported_cost_rub']) for r in ledger.rows
                                               if r['reported_cost_rub'] is not None), Decimal(0))),
                   'unknown_cost_attempts': sum(r['reported_cost_rub'] is None for r in ledger.rows),
                   'scientific_status': 'not_accepted', 'endpoints': endpoint_records}
        journal.save('summary.json', summary)
        print('Saved', directory, flush=True)
        return summary
    except BaseException as exc:
        if journal:
            journal.save('interruption.json', {'type': type(exc).__name__, 'state': 'incomplete'})
        raise
    finally:
        if journal:
            journal.store.db.close()
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', default='.env')
    parser.add_argument('--live', action='store_true', help='Explicitly enable paid calls')
    parser.add_argument('--tasks', type=int, default=6)
    parser.add_argument('--review', help='Hash-bound probe review required for pilot')
    args = parser.parse_args()
    try:
        config = Config.load(args.env)
        if args.live:
            summary = run(config, args.tasks, args.review)
            if not summary['technical_criteria_met']:
                print('Process completed; mandatory technical criteria failed', file=sys.stderr)
                return 1
        else:
            print('Configuration valid; no network calls. Budget:', config.budget, 'RUB')
    except (ConfigurationError, StopRun) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print('Stage zero interrupted:', type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
