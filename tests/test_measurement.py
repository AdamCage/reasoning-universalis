import copy
import unittest
import json
from pathlib import Path
import tempfile
import subprocess
import sys

from measurement.core import digest, segments, text_hash, split_manifest, previous_context, paired_embeddings
from measurement.lexical import LexicalBaseline
from measurement.lexical import ROLES
from measurement.evaluation import role_metrics, grouped_interval, boundary_f1, cohen_kappa
from measurement.demo import prepare


def task(i, root=None):
    return {'task_id': str(i), 'root_id': root or str(i), 'domain': 'D1',
            'generator_id': 'fixture-v1', 'prompt': 'Solve fixture ' + str(i)}


def trace(text):
    return {'trace_id': 'trace-1', 'task_id': '1', 'root_id': '1', 'family': 'fixture',
            'split': 'development', 'visible_reasoning': text, 'raw_response_sha256': 'fixture-hash'}


class MeasurementTests(unittest.TestCase):
    def test_grouping_is_order_independent_and_variants_never_split(self):
        tasks = [task(1), task(2, '1'), task(3)]
        a, b = split_manifest(tasks), split_manifest(list(reversed(tasks)))
        self.assertEqual(a, b)
        self.assertEqual(a['tasks'][0]['split'], a['tasks'][1]['split'])

    def test_duplicate_prompt_and_inconsistent_ancestry_rejected(self):
        tasks = [task(1), task(2)]
        tasks[1]['prompt'] = tasks[0]['prompt']
        with self.assertRaises(ValueError):
            split_manifest(tasks)

    def test_historical_task_cannot_enter_holdout(self):
        value = task(1)
        value['previously_observed'] = True
        with self.assertRaises(ValueError):
            split_manifest([value])
        value['forced_split'] = 'development'
        self.assertEqual(split_manifest([value])['tasks'][0]['split'], 'development')
        tasks = [task(1), task(2, '1')]
        tasks[1]['generator_id'] = 'other-generator'
        with self.assertRaises(ValueError):
            split_manifest(tasks)

    def test_sentence_boundaries_preserve_bytes_lists_decimals_abbreviations_code_math(self):
        text = '1. Compute x = 1.25. Dr. Smith checks.\r\n```python\r\nx = 3.\r\n```\r\nUse $a. b$ here. Done!'
        rows = segments(trace(text), 'S2')
        self.assertEqual(''.join(r['text'] for r in rows), text)
        self.assertTrue(all(r['text'].strip() for r in rows))
        self.assertTrue(rows[0]['text'].startswith('1. Compute x = 1.25.'))
        self.assertTrue(any('Dr. Smith checks.' in r['text'] for r in rows))
        self.assertTrue(any('x = 3.' in r['text'] and '```python' in r['text'] for r in rows))
        for row in rows:
            self.assertEqual(text[row['char_start']:row['char_end']], row['text'])

    def test_semantic_boundaries_are_explicit_and_hash_bound(self):
        rows = segments(trace('Plan. Compute.'), 'S1', semantic_boundaries=[5])
        self.assertEqual(len(rows), 2)
        with self.assertRaises(ValueError):
            segments(trace('Plan. Compute.'), 'S1')
        changed = segments(trace('Plan. Compute!'), 'S1', semantic_boundaries=[5])
        self.assertNotEqual(rows[0]['segment_id'], changed[0]['segment_id'])

    def test_fixed_tokens_require_real_aligned_map(self):
        text = 'a bb c'
        mapping = {'text_sha256': text_hash(text), 'tokenizer_id': 'fixture-tokenizer',
                   'tokenizer_revision': 'synthetic-test-only', 'offsets': [[0, 1], [2, 4], [5, 6]]}
        rows = segments(trace(text), 'S3', mapping, block_size=2)
        self.assertEqual([r['token_end']-r['token_start'] for r in rows], [2, 1])
        self.assertEqual(''.join(r['text'] for r in rows), text)
        mapping['text_sha256'] = 'changed'
        with self.assertRaises(ValueError):
            segments(trace(text), 'S3', mapping)
        with self.assertRaises(ValueError):
            segments(trace(text), 'S3')

    def test_context_is_past_only_and_cannot_cross_traces(self):
        rows = segments(trace('Plan. Compute. Check.'), 'S2')
        self.assertEqual(previous_context(rows, 1), rows[0]['text'])
        self.assertNotIn('Check', previous_context(rows, 1))
        rows[0]['trace_id'] = 'other'
        with self.assertRaises(ValueError):
            previous_context(rows, 1)

    def test_paired_embedders_use_identical_common_selection(self):
        a = [{'segment_id': 'a', 'identity_verified': True, 'valid': True},
             {'segment_id': 'b', 'identity_verified': False, 'valid': True}]
        b = [{'segment_id': 'a', 'identity_verified': True, 'valid': True},
             {'segment_id': 'b', 'identity_verified': True, 'valid': True}]
        for row in a+b:
            row.update(trace_sha256='same', char_start=0, char_end=5,
                       measurement_config_digest='same', input_sha256='same')
        pair = paired_embeddings(a, b)
        self.assertEqual(pair['segment_ids'], ['a'])
        self.assertEqual(pair['excluded_right'], ['b'])
        b[0]['input_sha256'] = 'changed'
        with self.assertRaises(ValueError):
            paired_embeddings(a, b)

    def training(self):
        tasks = [task(i) for i in range(30)]
        manifest = split_manifest(tasks)
        chosen = [r for r in manifest['tasks'] if r['split'] == 'development'][:2]
        rows = [{**r, 'segment_id': 's'+str(i), 'family': 'train-family', 'text': text, 'role': role}
                for i, (r, text, role) in enumerate(zip(chosen, ['plan strategy', 'verify check'], ['planning', 'verification']))]
        return rows, manifest

    def test_tfidf_vocabulary_fitted_only_on_allowed_training(self):
        rows, manifest = self.training()
        model = LexicalBaseline().fit(rows, manifest, ['heldout-family'])
        self.assertEqual(model.predict('verify check')['role'], 'verification')
        before = copy.deepcopy(model.idf)
        self.assertEqual(model.predict('unseenword')['role'], 'ambiguous_other')
        self.assertEqual(before, model.idf)

    def test_training_rejects_holdout_tasks_families_and_manifest_mutation(self):
        rows, manifest = self.training()
        with self.assertRaises(ValueError):
            LexicalBaseline().fit(rows, manifest, ['train-family'])
        rows[0]['split'] = 'measurement_validation'
        with self.assertRaises(ValueError):
            LexicalBaseline().fit(rows, manifest)
        rows, manifest = self.training()
        manifest['seed'] = 'changed'
        with self.assertRaises(ValueError):
            LexicalBaseline().fit(rows, manifest)

    def test_e0_metrics_do_not_hide_absent_classes_or_degenerate_agreement(self):
        rows = [{'root_id': str(i), 'gold': role, 'predicted': role} for i, role in enumerate(ROLES[:-1])]
        self.assertEqual(role_metrics(rows)['macro_f1'], 1.)
        self.assertEqual(role_metrics(rows[:1])['macro_f1'], .125)
        self.assertEqual(grouped_interval(rows[:1])['interval'], None)
        self.assertEqual(grouped_interval(rows, replicates=20), grouped_interval(rows, replicates=20))
        self.assertEqual(cohen_kappa([('planning', 'planning'), ('verification', 'verification')])['cohen_kappa'], 1.)
        self.assertIsNone(cohen_kappa([('planning', 'planning')])['cohen_kappa'])
        self.assertEqual(boundary_f1([5, 8], [5], 12)['f1'], 2/3)

    def test_real_historical_import_and_duplicate_generation_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, traces = prepare(root)
            output = root / 'measured.json'
            args = [sys.executable, '-m', 'measurement.cli', '--tasks', str(tasks), '--traces', str(traces), '--output', str(output)]
            subprocess.run(args, check=True, capture_output=True)
            measured = json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(measured['scientific_approved'])
            self.assertFalse(measured['token_alignment_complete'])
            self.assertTrue(all(r['split'] == 'development' for r in measured['segments']))
            self.assertEqual(len({r['trace_id'] for r in measured['segments']}), 6)
            values = json.loads(traces.read_text(encoding='utf-8'))
            duplicate = {**values[0], 'trace_id': 'different-id-same-generation'}
            traces.write_text(json.dumps(values+[duplicate]), encoding='utf-8')
            failure = subprocess.run(args, capture_output=True)
            self.assertNotEqual(failure.returncode, 0)
            self.assertIn(b'Repeated raw generation', failure.stderr)

    def test_hypothesis_snapshot_matches_unchanged_normalized_source(self):
        snapshot = json.loads(Path('design/hypotheses.json').read_text(encoding='utf-8'))
        source = Path('RESEARCH_SPECIFICATION.md').read_text(encoding='utf-8')
        self.assertEqual(snapshot['source_sha256_lf'], text_hash(source))
        self.assertEqual({r['id'] for r in snapshot['hypotheses']}, {'H'+str(i) for i in range(8)})
        self.assertTrue(all(r['source_text'] in source for r in snapshot['hypotheses']))


if __name__ == '__main__':
    unittest.main()
