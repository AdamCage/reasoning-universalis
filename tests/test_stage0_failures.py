import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
import io

from stage0.config import Config
from stage0.runner import StopRun, capture_body, http, run, validate_review, main
from stage0.traces import inspect_embeddings
from stage0.evidence import verify


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = Path(self.temp.name) / '.env'
        self.env.write_text(Path('env.example').read_text(encoding='utf-8').replace(
            'ROUTERAI_API_KEY=', 'ROUTERAI_API_KEY=test-secret'), encoding='utf-8')
        self.config = Config.load(self.env)

    def review(self):
        model = 'openai/gpt-oss-20b'
        directory = self.config.root / 'fixture'
        directory.mkdir(parents=True, exist_ok=True)
        sent = {'model': model, 'request': {'model': model, 'reasoning': {'enabled': True}, 'include_reasoning': True}}
        received = {'http_status': 200, 'json': {'model': model, 'provider': 'fixture-provider',
                    'choices': [{'finish_reason': 'stop', 'message': {'reasoning': 'Compute x.', 'content': 'ANSWER: 31'}}]}}
        evidence = {'full_visible_trace': True, 'provider': 'fixture-provider'}
        for kind, value, hash_key in (('request', sent, 'request_sha256'), ('response', received, 'sha256')):
            path = directory / ('probe-' + kind + '.json')
            data = json.dumps(value).encode()
            path.write_bytes(data)
            evidence[kind + '_path'] = str(path)
            evidence[hash_key] = hashlib.sha256(data).hexdigest()
        return {'scope': 'technical_probe_trace_review', 'models': {model: evidence}}

    def test_review_identity_status_route_and_request_bound_before_network(self):
        for target, change in (
            ('response', lambda x: x['json'].update(model='different/model')),
            ('request', lambda x: x['request'].update(model='different/model')),
            ('response', lambda x: x.update(http_status=503)),
            ('response', lambda x: x['json'].update(error={'code': 400})),
            ('response', lambda x: x['json'].update(provider='different-provider')),
            ('request', lambda x: x['request']['reasoning'].update(enabled=False)),
        ):
            with self.subTest(target=target, change=change):
                review = self.review()
                evidence = next(iter(review['models'].values()))
                path = Path(evidence[target + '_path'])
                value = json.loads(path.read_bytes())
                change(value)
                data = json.dumps(value).encode()
                path.write_bytes(data)
                evidence['sha256' if target == 'response' else 'request_sha256'] = hashlib.sha256(data).hexdigest()
                review_path = self.config.root / 'review.json'
                review_path.write_text(json.dumps(review))
                with patch('stage0.runner.http') as network, self.assertRaises(StopRun):
                    run(self.config, review_path=review_path)
                network.assert_not_called()
        self.assertEqual(validate_review(self.config, self.review())['scope'], 'technical_probe_trace_review')

    def test_embeddings_reject_identity_error_and_malformed_rows(self):
        for value in ({'model': 'different/model', 'data': [{'index': 0, 'embedding': [0.] * 1024}]},
                      {'model': 'baai/bge-m3', 'error': {}, 'data': [{'index': 0, 'embedding': [0.] * 1024}]},
                      {'model': 'baai/bge-m3', 'data': None},
                      {'model': 'baai/bge-m3', 'data': [{'index': True, 'embedding': [0.] * 1024}]}):
            self.assertFalse(inspect_embeddings(value, 'baai/bge-m3', 1)['valid'])

    def test_review_rejects_changed_hash_and_legacy_unbound_review(self):
        review = self.review()
        evidence = next(iter(review['models'].values()))
        evidence['sha256'] = '0' * 64
        with self.assertRaises(StopRun):
            validate_review(self.config, review)
        review = self.review()
        del next(iter(review['models'].values()))['request_sha256']
        with self.assertRaises(StopRun):
            validate_review(self.config, review)

    def test_evidence_recounts_historical_results_and_flags_alias(self):
        result = verify(Path('evidence/stage0-2026-10-12.zip'))
        self.assertEqual((result['paid_attempts'], result['pilot_correct'], result['segments'], result['vectors']), (32, 6, 105, 210))
        self.assertEqual(result['identity_verified_vectors'], 175)
        self.assertEqual(len(result['embedding_failures']), 2)
        self.assertEqual(result['confirmed_cost_rub'], '0.41653321870992')

    def test_evidence_rejects_tampered_member(self):
        path = Path(self.temp.name) / 'tampered.zip'
        with zipfile.ZipFile('evidence/stage0-2026-10-12.zip') as source, zipfile.ZipFile(path, 'w') as target:
            for name in source.namelist():
                data = source.read(name)
                if name.endswith('stage0-budget.json'):
                    data += b' '
                target.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verify(path)

    def test_invalid_utf8_survives_http_capture(self):
        response = MagicMock()
        response.status = 200
        response.headers = {}
        response.read.return_value = b'\xff\x00invalid'
        response.__enter__.return_value = response
        with patch('stage0.runner.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            result = http('/models')
        self.assertEqual(base64.b64decode(result['body_base64']), b'\xff\x00invalid')
        self.assertEqual(result['decode_error'], 'invalid_utf8')
        self.assertEqual(result['http_status'], 200)

    def test_secret_redacted_before_base64_and_labelled(self):
        result = capture_body(b'{"reflected":"test-secret"}', 'test-secret')
        self.assertNotIn(b'test-secret', base64.b64decode(result['body_base64']))
        self.assertEqual(result['body_storage'], 'redacted_bytes_original_not_retained')
        self.assertNotEqual(result['received_body_sha256'], result['body_sha256'])

    def test_http_error_keeps_non_utf8_bytes(self):
        failure = HTTPError('https://routerai.ru/api/v1/models', 503, 'error', {}, io.BytesIO(b'\xfferror'))
        with patch('stage0.runner.request.build_opener') as opener:
            opener.return_value.open.side_effect = failure
            result = http('/models')
        self.assertEqual(result['http_status'], 503)
        self.assertEqual(base64.b64decode(result['body_base64']), b'\xfferror')
        self.assertEqual(result['decode_error'], 'invalid_utf8')

    def test_pilot_invalid_embeddings_complete_but_fail_technical_criteria(self):
        review_path = self.config.root / 'review.json'
        review_path.parent.mkdir(parents=True)
        review_path.write_text(json.dumps(self.review()))
        def transport(endpoint, key=None, body=None, timeout=30):
            if endpoint == '/models':
                value = {'data': [{'pricing': {'prompt': 0.000001, 'completion': 0.000001},
                    'pricing_units': {'prompt': 'token', 'completion': 'token'},
                    'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']}}]}
            elif endpoint.endswith('/endpoints'):
                value = {'data': {'endpoints': [{'pricing': {'prompt': 0.000001, 'completion': 0.000001},
                    'pricing_units': {'prompt': 'token', 'completion': 'token'}}]}}
            elif endpoint == '/embeddings':
                value = {'model': body['model'], 'data': []}
            else:
                value = {'model': body['model'], 'provider': 'fixture-provider', 'choices': [
                    {'finish_reason': 'stop', 'message': {'reasoning': 'Compute x.', 'content': 'ANSWER: 31'}}]}
            return {'http_status': 200, 'json': value, 'elapsed_seconds': .01}
        with patch('stage0.runner.http', side_effect=transport), patch('builtins.print'):
            summary = run(self.config, tasks=5, review_path=review_path)
        self.assertTrue(summary['process_completed'])
        self.assertFalse(summary['technical_criteria_met'])
        self.assertEqual(len(summary['failed_requirements']), 10)
        self.assertTrue((Path(summary['directory']) / 'summary.json').is_file())
        with patch('sys.argv', ['stage0', '--env', str(self.env), '--live']), patch('stage0.runner.run', return_value=summary), patch('builtins.print'):
            self.assertEqual(main(), 1)
        def changed_provider(*args, **kwargs):
            response = transport(*args, **kwargs)
            if args[0] == '/chat/completions':
                response['json']['provider'] = 'different-provider'
            return response
        with patch('stage0.runner.http', side_effect=changed_provider), patch('builtins.print'):
            changed = run(self.config, tasks=5, review_path=review_path)
        self.assertFalse(changed['technical_criteria_met'])
        self.assertTrue(all(r['trace']['status'] == 'reviewed_provider_changed' for r in changed['observations']))
        self.assertEqual(len(changed['observations']), 5)


if __name__ == '__main__':
    unittest.main()
