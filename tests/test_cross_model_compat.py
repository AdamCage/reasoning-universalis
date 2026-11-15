"""Transport-addendum engineering checks; no model calls or live ledger writes."""
import copy
import json
from pathlib import Path
import unittest

from cross_model.common import ARTIFACT as OLD, ROUTES, read, sha
from cross_model.annotation import request_body as old_body, parse_response
from cross_model_compat import cells, request_body

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def test_same_fixed_items_no_attempted_study_cell_or_probe_repeat(self):
        doc, codebook = read(ROOT / OLD / "input-items.json"), read(ROOT / OLD / "codebook.json")
        roster = cells(doc, codebook)
        self.assertEqual(len(roster), 192)
        self.assertEqual(len({(r['model'],r['condition'],r['item_id']) for r in roster}),192)
        self.assertFalse(any(r['condition']=='schema_probe' for r in roster))
        self.assertEqual(len({r['item_id'] for r in roster}),72)

    def test_only_known_transport_incompatibilities_change(self):
        doc, codebook = read(ROOT / OLD / "input-items.json"), read(ROOT / OLD / "codebook.json")
        item = doc['items'][0]
        before = copy.deepcopy(item)
        for model, provider in ROUTES:
            a = old_body(item,codebook,model,provider)
            b = request_body(item,codebook,model,provider)
            self.assertEqual(a['messages'],b['messages'])
            a['response_format']['json_schema']['schema']['properties']['secondary_roles'].pop('uniqueItems')
            if model=='openai/gpt-oss-20b':a['reasoning']={'enabled':True,'effort':'low'}
            self.assertEqual(a,b)
        self.assertEqual(item,before)
        self.assertTrue(codebook['response_schema']['properties']['secondary_roles']['uniqueItems'])

    def test_local_unique_secondary_validation_unchanged(self):
        item=read(ROOT / OLD / 'input-items.json')['items'][0]
        vote={'item_id':item['item_id'],'primary_role':'conclusion','secondary_roles':['planning','planning'],
              'confidence':'medium','reason_code':'answer_statement','evidence_quotes':[{'source_id':item['item_id'],'quote':item['current_segment']['text'][:30]}]}
        with self.assertRaises(ValueError):parse_response(json.dumps(vote),item)

    def test_failed_probes_preserved_and_no_scientific_label_was_viewed_before_addendum(self):
        initial=read(ROOT / OLD / 'new-annotations.json')['cells']
        attempted=[c for c in initial if 'call_id' in c]
        self.assertEqual(len(attempted),2)
        self.assertTrue(all(c['condition']=='schema_probe' and c['vote'] is None for c in attempted))
        self.assertTrue(all(c.get('vote') is None for c in initial))


if __name__=='__main__':unittest.main()
