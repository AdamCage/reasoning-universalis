"""Deterministic and failure-path measurement tests; fixtures are not E0."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from measurement.core import digest, split_manifest, text_hash, paired_embeddings
from stage2.datasets import generate, solve, verify, DOMAINS
from stage2.tokenization import ResearchBPE
from stage2.segmentation import measure, transitions, compare_segmentations
from stage2.observations import ObservationStore, validate_record, canonical
from stage2.representations import Tfidf, EmbeddingAdapter, inputs
from stage2.discovery import StateDiscovery, nested_lexical_discovery
from stage2.annotation import render, panel, parse_vote


def fixture():
    tasks = [{'task_id': str(i), 'root_id': str(i), 'domain': 'math', 'generator_id': 'fixture',
              'prompt': 'Fixture '+str(i), 'previously_observed': True, 'forced_split': 'development'} for i in range(6)]
    rows = [{'task_id': str(i), 'root_id': str(i), 'family': 'fixture-family', 'split': 'development',
             'segment_id': str(i), 'text': ('compute value' if i%2 else 'verify result')+' '+str(i)} for i in range(6)]
    return tasks, rows, split_manifest(tasks)


class DevelopmentTests(unittest.TestCase):
    def test_four_domains_independent_verifiers_and_negative_answers(self):
        for domain in DOMAINS:
            for level in ('easy', 'medium', 'hard'):
                for seed in range(5):
                    task = generate(domain, seed, level)
                    expected = solve(task)
                    answer = json.dumps(expected) if type(expected) is list else str(expected)
                    self.assertEqual(verify(task, 'ANSWER: '+answer)['verdict'], 'correct')
                    self.assertNotEqual(verify(task, 'ANSWER: invalid')['verdict'], 'correct')
                    self.assertEqual(task, generate(domain, seed, level))
        task = generate('planning', 1)
        self.assertEqual(verify(task, 'ANSWER: ["delete"]')['verdict'], 'unparseable')

    def test_parameter_variants_share_conservative_root(self):
        a, b = generate('math', 1), generate('math', 2)
        self.assertEqual(a['root_id'], b['root_id'])
        manifest = split_manifest([a, b])
        self.assertEqual({r['split'] for r in manifest['tasks']}, {'development'})

    def test_all_segmentations_have_actual_named_token_intervals_and_exact_slices(self):
        text = 'Plan: compute x.\n\nNow calculate 2+2=4. Verify the value. Wait, correct the sign. Answer is 4.'
        mapping = ResearchBPE().fit([text], ['fixture-root']).mapping(text)
        trace = {'trace_id': 't', 'task_id': '0', 'root_id': '0', 'family': 'fixture', 'split': 'development',
                 'visible_reasoning': text, 'raw_response_sha256': 'raw'}
        configs = {}
        for method in ('S1', 'S2', 'S3'):
            rows = measure(trace, method, mapping, 4); configs[method] = rows
            self.assertEqual(''.join(r['text'] for r in rows), text)
            self.assertTrue(all(r['token_start'] is not None and r['token_end']>r['token_start'] for r in rows))
            self.assertTrue(all(r['tokenizer_scope']=='independent_research_not_model' for r in rows))
        self.assertGreater(len(configs['S1']), 1)
        paired = compare_segmentations(configs['S1'], configs['S3'])
        self.assertEqual(paired['pairs'][0]['trace_id'], 't')
        self.assertNotEqual({r['segment_id'] for r in configs['S1']}, {r['segment_id'] for r in configs['S3']})
        changed = copy.deepcopy(configs['S3']); changed[0]['root_id']='foreign'
        with self.assertRaises(ValueError): compare_segmentations(configs['S1'], changed)

    def test_no_cross_trace_edges_or_context(self):
        all_rows = []
        for trace_id in ('a', 'b'):
            text = 'First calculate. Then verify.'; mapping=ResearchBPE().fit([text], ['root']).mapping(text)
            trace = {'trace_id': trace_id, 'task_id': '0', 'root_id': '0', 'family': 'fixture',
                     'split': 'development', 'visible_reasoning': text, 'raw_response_sha256': 'raw'}
            all_rows.extend(measure(trace, 'S2', mapping))
        edges = transitions(all_rows); by_id={r['segment_id']:r for r in all_rows}
        self.assertTrue(all(by_id[e['from']]['trace_id']==by_id[e['to']]['trace_id'] for e in edges))
        contexts=inputs(all_rows, 'Contextual')
        self.assertEqual(contexts[len(all_rows)//2]['context_sha256'], text_hash(''))
        self.assertNotEqual(inputs(all_rows, 'Local')[-1]['input_sha256'], contexts[-1]['input_sha256'])

    def test_embedding_allowlist_dimensions_drift_and_common_inputs(self):
        with self.assertRaises(ValueError): EmbeddingAdapter('other/model', None)
        text='First compute. Then verify.'; mapping=ResearchBPE().fit([text], ['root']).mapping(text)
        trace={'trace_id':'t','task_id':'0','root_id':'0','family':'fixture','split':'development','visible_reasoning':text,'raw_response_sha256':'raw'}
        rows=measure(trace,'S2',mapping)
        def transport(path, request):
            dim=1024 if request['model']=='baai/bge-m3' else 4
            return {'http_status':200,'json':{'model':request['model'], 'data':[{'index':i,'embedding':[1.]*dim} for i in range(len(request['input']))]}}
        a=EmbeddingAdapter('baai/bge-m3',transport).collect(rows);b=EmbeddingAdapter('qwen/qwen3-embedding-8b',transport).collect(rows)
        self.assertEqual(len(paired_embeddings(a,b)['segment_ids']),len(rows))
        bad=EmbeddingAdapter('baai/bge-m3',lambda *_: {'http_status':200,'json':{'model':'parasail-bge-m3','data':[]}}).collect(rows)
        self.assertFalse(any(r['valid'] for r in bad))

    def test_cluster_first_fit_guards_and_nested_training_without_labels(self):
        _, rows, manifest=fixture(); representation=Tfidf().fit(rows,manifest)
        model=StateDiscovery().fit(rows,[representation.transform(r['text']) for r in rows],manifest,2)
        self.assertEqual(len(model.centers),2)
        self.assertEqual(model.predict(representation.transform('compute'))['role'],'uninterpreted')
        with self.assertRaises(ValueError): Tfidf().fit(rows,manifest,['fixture-family'])
        bad=copy.deepcopy(rows);bad[0]['split']='confirmatory'
        with self.assertRaises(ValueError): StateDiscovery().fit(bad,[[1] for _ in bad],manifest,2)
        with self.assertRaises(ValueError): model.freeze_mapping({'0':'planning','1':'verification'},'votes',['foreign-root'])
        nested=nested_lexical_discovery(rows,manifest,candidates=(1,2),outer_folds=3,inner_folds=2)
        for fold in nested['outer_folds']:
            self.assertFalse(set(fold['training_roots']) & set(fold['outer_test_roots']))

    def test_finite_annotation_panels_quotes_and_no_metadata_leak(self):
        prompt=render('anon','data','Verify x.', ['past'],'definitions')
        self.assertNotIn('provider',json.loads(prompt['user']))
        vote={'item_id':'anon','primary_role':'verification','secondary_roles':[], 'confidence':'high',
              'reason_code':'check_existing','evidence_quotes':[{'source_id':'anon','quote':'Verify'}]}
        parsed=parse_vote(canonical(vote),'anon',{'anon':'Verify x.'})
        self.assertEqual(panel([parsed]*5,1)['status'],'resolved')
        self.assertEqual(panel([parsed]*4+[None],1)['status'],'technical_unresolved')
        votes=[{**vote,'primary_role':r} for r in ('planning','verification','exploration','conclusion','uncertainty')]
        self.assertEqual(panel(votes,1)['next_round'],2)
        self.assertEqual(panel(votes,2)['status'],'ambiguous_unresolved')
        vote['evidence_quotes'][0]['quote']='not present'
        with self.assertRaises(ValueError): parse_vote(canonical(vote),'anon',{'anon':'Verify x.'})

    def test_live_transport_cannot_reset_historical_budget_or_change_host(self):
        from stage2.inference import RouterAITransport
        from stage0.runner import StopRun
        from types import SimpleNamespace
        cfg=SimpleNamespace(values={'ROUTERAI_BASE_URL':'https://routerai.ru/api/v1'})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(StopRun):
                RouterAITransport(cfg,Path(root)/'missing.json','0'*64,{},Path(root)/'journal',{})
        from stage2.inference import generate_trace
        from unittest.mock import patch
        review={'models':{'openai/gpt-oss-20b':{'provider':'reviewed'}}}
        with patch('stage2.inference.validate_review'):
            with self.assertRaisesRegex(StopRun,'provider differs'):
                generate_trace(cfg,{'prompt':'fixture'},review,SimpleNamespace(providers={'openai/gpt-oss-20b':'unreviewed'}))

    def test_parser_failure_incomplete_trace_and_reflected_key_preserved_safely(self):
        with tempfile.TemporaryDirectory() as root:
            cas=ObservationStore(root); task=generate('math',0)
            protocol={'study_id':'fixture','dataset_digest':digest([task]),'task_set_digest':digest([task]),
                      'split_digest':'split','method_digest':'method'}
            execution={'model_id':'openai/gpt-oss-20b','provider':'fixture','source_code_digest':'source'}
            record,_=cas.record_attempt('broken',b'{}',b'{bad secret}',200,task,protocol,execution,secret='secret')
            self.assertEqual(record['status'],'failed')
            self.assertIn(b'[REDACTED]',cas.read(record['raw_observations']['raw_response_digest']))
            self.assertNotIn(b'secret',cas.read(record['raw_observations']['raw_response_digest']))
            body={'model':'openai/gpt-oss-20b','provider':'fixture','id':'g1', 'choices':[{'finish_reason':'length',
                  'message':{'reasoning':'wrong calculation. repeat repeat.', 'content':'unfinished'}}]}
            record,_=cas.record_attempt('incomplete',b'{}',canonical(body),200,task,protocol,execution)
            self.assertEqual(record['status'],'incomplete');self.assertIn('repeat repeat',record['raw_observations']['visible_reasoning'])
            validate_record(record,cas)
            record['raw_observations']['visible_reasoning']='fixed'
            with self.assertRaises(ValueError): validate_record(record,cas)
