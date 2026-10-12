import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from stage0.config import Config, ConfigurationError
from stage0.runner import Ledger, StopRun, redact, estimate, http, NoRedirect, run
from stage0.traces import inspect_trace, inspect_embeddings
from stage0.tasks import manifest, verify_answer


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '.env'
        self.base = Path('env.example').read_text(encoding='utf-8').replace('ROUTERAI_API_KEY=', 'ROUTERAI_API_KEY=test-secret')

    def load(self, content):
        self.path.write_text(content, encoding='utf-8')
        return Config.load(self.path)

    def test_valid_secret_not_in_repr_or_public(self):
        config = self.load(self.base)
        self.assertNotIn('test-secret', repr(config))
        self.assertNotIn('test-secret', json.dumps(config.public()))

    def test_fail_closed_before_network(self):
        changes = [('test-secret', ''), ('https://routerai.ru/api/v1', 'https://evil.example'),
                   ('baai/bge-m3', 'other/model'), ('RU_MAX_SPEND_RUB=900', 'RU_MAX_SPEND_RUB=NaN'),
                   ('RU_REQUIRE_VISIBLE_REASONING=true', 'RU_REQUIRE_VISIBLE_REASONING=false'),
                   ('RU_RESEARCH_ROOT=.research/reasoning-universalis', 'RU_RESEARCH_ROOT=../outside')]
        with patch('urllib.request.OpenerDirector.open') as network:
            for before, after in changes:
                with self.subTest(before=before):
                    with self.assertRaises(ConfigurationError):
                        self.load(self.base.replace(before, after))
            network.assert_not_called()

    def test_duplicate_and_unknown_keys(self):
        for suffix in ('\nRU_SEED=99', '\nUNKNOWN=yes'):
            with self.assertRaises(ConfigurationError):
                self.load(self.base + suffix)


class EvidenceTests(unittest.TestCase):
    def trace(self, message, finish='stop'):
        return inspect_trace({'choices': [{'message': message, 'finish_reason': finish}]})

    def test_answer_is_never_promoted(self):
        x = self.trace({'content': 'First think carefully. The answer is 31.'})
        self.assertEqual(x['status'], 'answer_only')
        self.assertFalse(x['full_visible_trace'])
        self.assertEqual(x['trace'], '')

    def test_summary_rejected_even_if_reasoning_text_present(self):
        x = self.trace({'reasoning': 'Some text', 'reasoning_details': [{'type': 'reasoning.summary', 'summary': 'brief'}]})
        self.assertEqual(x['status'], 'summary_or_truncated_or_unfinished')

    def test_truncated_reasoning_rejected(self):
        self.assertEqual(self.trace({'reasoning': 'Long reasoning'}, 'length')['status'], 'summary_or_truncated_or_unfinished')

    def test_explicit_trace_requires_review(self):
        x = self.trace({'reasoning': '3, 10, 17, 24, 31; 31 mod 5 is 1.', 'content': 'ANSWER: 31'})
        self.assertEqual(x['status'], 'visible_trace_candidate')
        self.assertFalse(x['full_visible_trace'])

    def test_encrypted_remainder_is_not_full_visible_trace(self):
        x = self.trace({'reasoning': 'Some text', 'reasoning_details': [{'type': 'reasoning.encrypted'}]})
        self.assertNotEqual(x['status'], 'visible_trace_candidate')

    def test_dimensions_finite_and_indices(self):
        value = {'model': 'BAAI/bge-m3', 'data': [{'index': 0, 'embedding': [0.1] * 1024}]}
        self.assertTrue(inspect_embeddings(value, 'baai/bge-m3', 1)['valid'])
        value['data'][0]['embedding'][3] = float('nan')
        self.assertFalse(inspect_embeddings(value, 'baai/bge-m3', 1)['valid'])
        value = {'model': 'qwen/qwen3-embedding-8b', 'data': [{'index': 0, 'embedding': [0.1] * 4097}]}
        self.assertFalse(inspect_embeddings(value, 'qwen/qwen3-embedding-8b', 1)['valid'])

    def test_secret_redacted_in_errors_and_raw_body(self):
        key = 'secret+with/slash'
        self.assertNotIn(key, redact('Authorization: Bearer ' + key, key))
        self.assertNotIn('secret%2Bwith%2Fslash', redact('secret%2Bwith%2Fslash', key))

    def test_redirect_never_carries_key(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_manifest_verifiers(self):
        tasks = manifest()
        self.assertEqual(len(tasks), 6)
        solutions = [next(i for i in range(1, 36) if i % 7 == 3 and i % 5 == 1),
                     sum(i % 3 == 0 or i % 5 == 0 for i in range(1, 101)), 'yes', 'yes', 4, 2 + max(3, 4) + 1]
        for task, solution in zip(tasks, solutions):
            self.assertTrue(verify_answer(task, 'ANSWER: ' + str(solution))['correct'])
            self.assertFalse(verify_answer(task, 'No final marker')['correct'])


class BudgetTests(unittest.TestCase):
    def test_restart_and_unknown_attempt_keep_reservation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'ledger.json'
            ledger = Ledger(path, Decimal('1'))
            row = ledger.reserve(Decimal('0.7'), 'test')
            ledger.finish(row, {'http_status': None, 'json': {}})
            reopened = Ledger(path, Decimal('1'))
            with self.assertRaises(StopRun):
                reopened.reserve(Decimal('0.4'), 'next')
            self.assertEqual(reopened.rows[0]['state'], 'unknown')

    def test_reported_overrun_stops_further_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Ledger(Path(temp) / 'ledger.json', Decimal('1'))
            row = ledger.reserve(Decimal('0.2'), 'test')
            with self.assertRaises(StopRun):
                ledger.finish(row, {'http_status': 200, 'json': {'usage': {'cost': '1.1'}}})
            self.assertEqual(ledger.committed, Decimal('1.1'))


class PipelineTests(unittest.TestCase):
    def test_live_probe_journals_all_attempts_and_redacts_reflections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.env'
            path.write_text(Path('env.example').read_text(encoding='utf-8').replace(
                'ROUTERAI_API_KEY=', 'ROUTERAI_API_KEY=integration-secret'), encoding='utf-8')
            config = Config.load(path)

            def transport(endpoint, key=None, body=None, timeout=30):
                if endpoint == '/models':
                    data = {'data': [{'pricing': {'prompt': 0.00001, 'completion': 0.00002},
                            'pricing_units': {'prompt': 'token', 'completion': 'token'},
                            'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']}}]}
                elif endpoint.endswith('/endpoints'):
                    data = {'data': {'endpoints': [{'pricing': {'prompt': 0.00001, 'completion': 0.00002},
                            'pricing_units': {'prompt': 'token', 'completion': 'token'}}]}}
                elif endpoint == '/embeddings':
                    n = 1024 if body['model'] == 'baai/bge-m3' else 4096
                    data = {'model': body['model'], 'data': [{'index': i, 'embedding': [0.1] * n}
                            for i in range(len(body['input']))], 'usage': {'cost': 0.01}}
                else:
                    data = {'model': body['model'], 'choices': [{'finish_reason': 'stop',
                            'message': {'content': 'ANSWER: 31', 'reasoning': 'Compute 31.'}}],
                            'usage': {'cost': 0.01}, 'reflected_authorization': key}
                return {'http_status': 200, 'json': data, 'raw_body': json.dumps(data),
                        'headers': {}, 'elapsed_seconds': 0.01}

            with patch('stage0.runner.http', side_effect=transport) as network, patch('builtins.print'):
                summary = run(config)
            self.assertEqual(len(summary['observations']), 14)
            self.assertEqual(sum(call.kwargs == {} and len(call.args) > 1
                                 for call in network.call_args_list), 14)
            for file in config.root.rglob('*'):
                if file.is_file():
                    self.assertNotIn(b'integration-secret', file.read_bytes())


if __name__ == '__main__':
    unittest.main()
