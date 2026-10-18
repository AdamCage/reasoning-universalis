"""New DomainPack contract and persisted kernel failure paths over real saved bytes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

from stage2.historical import prepare
from stage2.episteme_bridge import register, run, command, PLANNER, ANALYST
from stage2.observations import canonical
from episteme.domains import api, registry
from episteme import domain_packs
from episteme.store import Store
from episteme.kernel import Actor, Kernel
from episteme.recovery import backup, restore
from episteme.reporting import PaperBuilder
from reasoning_universalis_v1 import inventory


def files(source):
    return {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*') if p.is_file()}


def refresh(source_files, bundle):
    source_files['bundle.json'] = canonical(bundle)
    source_files['inventory.json'] = canonical({'files': {p:hashlib.sha256(b).hexdigest() for p,b in source_files.items() if p!='inventory.json'}})
    return source_files


def rehash_record(row):
    row['run_digest'] = inventory.sha(canonical({k:v for k,v in row.items() if k not in ('run_digest','recorded_at')}))


class DomainPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='stage2-contract-');cls.base=Path(cls.temp.name)
        cls.source=prepare(cls.base/'import');cls.loaded=register()
        cls.data=files(cls.source);cls.bundle=json.loads(cls.data['bundle.json'])
        cls.result=run(cls.base/'store',cls.source)
        with Store(cls.base/'store') as store:
            backup(store,cls.base/'backup')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        registry.PACKS.pop('reasoning_universalis_v1',None)

    def clone(self):
        tmp=tempfile.TemporaryDirectory(prefix='stage2-copy-');self.addCleanup(tmp.cleanup)
        target=Path(tmp.name)/'store';restore(self.base/'backup',target)
        store=Store(target);self.addCleanup(store.close);return store

    def test_contract_envelopes_pure_hooks_and_old_pack_continuity(self):
        self.assertEqual(registry.import_violations(registry.pack_files(self.loaded.root)),[])
        self.assertEqual(self.loaded.manifest.pack_id,'reasoning_universalis_v1')
        for name in ('synthetic_causal_v1','afterlife_seed_v1','tabular_classification_v1','risen_universalis_v1'):
            old=registry.load_pack(name);self.assertEqual(old.hook('describe')().pack_id,name)
        capture=self.loaded.hook('capture')(str(self.source))
        request=api.CompileRequest(parameters={'contrast':'S2-S1','bundle_digest':inventory.sha(self.data['bundle.json']),
                                              'method_digest':self.bundle['method_digest']},host_inputs={},capture=capture)
        a=self.loaded.hook('compile_protocol')(request);b=self.loaded.hook('compile_protocol')(request)
        self.assertEqual(a.digest(),b.digest())
        self.assertIsInstance(self.loaded.hook('compile_execution')(request),api.ExecutionPlanV2)
        with self.assertRaises(ValueError):
            self.loaded.hook('validate_parameters')({'contrast':'S2-S1','bundle_digest':'0'*64,'method_digest':'0'*64,'scientific_approved':True})

    def test_real_raw_to_metric_path_identity_and_separate_digests(self):
        checked=inventory.verify(self.data)
        self.assertEqual(len(checked['observations']),6)
        reps=json.loads(self.data['representations-lexical.json'])['rows']
        self.assertEqual({r['context_mode'] for r in reps},{'Local','Contextual'})
        states=json.loads(self.data['lexical-states.json'])
        self.assertTrue(all(s['role']=='uninterpreted' for s in states['states']))
        with self.clone() as store:
            result=self.result;_,ctx,cas=domain_packs.analysis_inputs(store,store.events(),result['batch'])
            output=self.loaded.hook('analyse')(ctx,cas,self.loaded.hook('validate_outputs')(ctx,cas),self.loaded.hook('recompute_metrics')(ctx,cas))
            self.assertEqual(output.outcome,'inconclusive')
            self.assertEqual(output.inference_mode,'exploratory')
            raw=cas.json(ctx.slot('primary:0')['outputs']['raw_data'],'raw')
            seg=raw['segments'][0];observation=next(r for r in raw['observations'] if r['identity']['trace_id']==seg['trace_id'])
            source=cas.read(observation['raw_observations']['raw_response_digest'])
            self.assertEqual(seg['text'],inventory.explicit(json.loads(source)['json'])[seg['char_start']:seg['char_end']])
            provenance=observation['provenance']
            keys=['dataset_digest','task_digest','task_set_digest','split_digest','method_digest','protocol_digest']
            self.assertEqual(len({provenance[k] for k in keys}),len(keys))
            self.assertNotEqual(observation['run_digest'],observation['raw_observations']['raw_response_digest'])
            self.assertTrue(cas.read(observation['raw_observations']['raw_request_digest']))

    def test_foreign_task_binding_and_altered_raw_are_rejected(self):
        bundle=copy.deepcopy(self.bundle);bundle['observations'][0]['identity']['problem_id']=bundle['tasks'][1]['task_id']
        rehash_record(bundle['observations'][0])
        with self.assertRaisesRegex(ValueError,'Foreign raw task'):
            inventory.verify(refresh(copy.deepcopy(self.data),bundle))
        changed=copy.deepcopy(self.data);path=next(p for p in changed if p.startswith('artifacts/'))
        changed[path]+=b'changed'
        with self.assertRaisesRegex(ValueError,'Captured bytes changed'): inventory.verify(changed)
        bundle=copy.deepcopy(self.bundle);bundle['segments'][0]['text']='repaired reasoning'
        with self.assertRaisesRegex(ValueError,'Segment differs'): inventory.verify(refresh(copy.deepcopy(self.data),bundle))

    def test_rehashed_split_violation_and_repeated_generation_rejected(self):
        bundle=copy.deepcopy(self.bundle);bundle['split_manifest']['tasks'][0]['split']='confirmatory'
        bundle['split_manifest']['manifest_digest']=inventory.sha(canonical({k:v for k,v in bundle['split_manifest'].items() if k!='manifest_digest'}))
        with self.assertRaisesRegex(ValueError,'cross split'): inventory.verify(refresh(copy.deepcopy(self.data),bundle))
        bundle=copy.deepcopy(self.bundle);row=copy.deepcopy(bundle['observations'][0]);row['attempt_id']='new-id-same-generation'
        rehash_record(row);bundle['observations'].append(row);bundle['origin_paths'][row['attempt_id']]=bundle['origin_paths'][bundle['observations'][0]['attempt_id']]
        with self.assertRaisesRegex(ValueError,'not independent replication'): inventory.verify(refresh(copy.deepcopy(self.data),bundle))

    def test_failed_and_incomplete_attempts_remain_inventory_not_success(self):
        bundle=copy.deepcopy(self.bundle);row=copy.deepcopy(bundle['observations'][0]);row['attempt_id']='fixture-failed-duplicate-dispatch'
        row['status']='failed';row['parse_or_admission_error']='synthetic_parse_failure';rehash_record(row);bundle['observations'].append(row);bundle['origin_paths'][row['attempt_id']]=bundle['origin_paths'][bundle['observations'][0]['attempt_id']]
        checked=inventory.verify(refresh(copy.deepcopy(self.data),bundle))
        self.assertEqual(len(checked['observations']),7)
        self.assertEqual(checked['observations'][-1]['status'],'failed')

    def test_negative_and_zero_count_contrasts_keep_dataset_identity(self):
        positive=inventory.metric(inventory.root_raw(self.bundle,0,'S2-S1',inventory.sha(self.data['bundle.json'])))
        negative=inventory.metric(inventory.root_raw(self.bundle,0,'S1-S2',inventory.sha(self.data['bundle.json'])))
        zero=inventory.metric(inventory.root_raw(self.bundle,0,'S2-S2',inventory.sha(self.data['bundle.json'])))
        self.assertEqual(negative,-positive);self.assertLess(negative,0);self.assertEqual(zero,0)
        self.assertEqual(self.bundle['dataset_digest'],inventory.verify(self.data)['dataset_digest'])

    def test_pinned_code_change_requires_new_revision(self):
        with tempfile.TemporaryDirectory(prefix='stage2-drift-') as tmp:
            import shutil,importlib
            target=Path(tmp)/'reasoning_universalis_v1';shutil.copytree(self.loaded.root,target,ignore=shutil.ignore_patterns('__pycache__'))
            p=target/'programs.py';p.write_bytes(p.read_bytes()+b'\n# changed after binding\n')
            sys.path.insert(0,tmp);self.addCleanup(lambda: sys.path.remove(tmp))
            original=sys.modules.pop('reasoning_universalis_v1',None);importlib.invalidate_caches()
            try:
                fresh=registry.load_pack('reasoning_universalis_v1')
                self.assertNotEqual(fresh.pack_code_digest,self.loaded.pack_code_digest)
                with self.assertRaisesRegex(ValueError,'differs from the pinned'):
                    fresh.require_pin(pack_id=self.loaded.pack_id,pack_version=self.loaded.pack_version,pack_code_digest=self.loaded.pack_code_digest)
            finally:
                if original is not None: sys.modules['reasoning_universalis_v1']=original
                importlib.invalidate_caches()

    def test_new_pack_cannot_raise_claim_or_enter_paper_without_human_review(self):
        with self.clone() as store:
            register();history=store.events();claim=Kernel._get(history,self.result['claim'],'claim')
            self.assertEqual(claim['payload']['outcome'],'inconclusive')
            observer=Kernel(store,Actor('test-observer','observer'))
            self.assertEqual(observer.next_action(claim['id'])['action'],'scientific_review')
            gate=observer.gate(claim['id'])
            self.assertEqual(gate['scientific_validity'],'not_assessed')
            with self.assertRaisesRegex(ValueError,'not eligible for paper'):
                PaperBuilder(store,Actor('test-writer','writer')).build(title='Fixture only',claims=[claim['id']],expected_bases={claim['id']:gate['basis_hash']})
            protocol=Kernel._get(history,self.result['protocol'],'protocol')['payload']
            with self.assertRaisesRegex(ValueError,'admitted only by pack.analyse'):
                Kernel(store,ANALYST).claim(protocol=self.result['protocol'],statement='Universal reasoning proven',scope=protocol['scope'],
                                            evidence=[ctx['id'] for ctx in history if ctx['kind']=='run'],limitations=['fixture'],outcome='supports',inference_mode='confirmatory')

    def test_negative_reviewer_finding_survives_new_claim_attempt(self):
        with self.clone() as store:
            register();observer=Kernel(store,Actor('test-observer','observer'));claim=self.result['claim']
            command(store,'replanning.record_review',{'claim':claim,'verdict':'reject','rationale':'Synthetic negative finding: E0 missing',
                    'findings':[{'kind':'discriminating_experiment','action':'Validate the measurement','closure_criterion':'Independent E0 evidence reviewed','evidence_refs':[claim]}],
                    'expected_basis':observer.gate(claim)['basis_hash'],'link_assessments':None},actor=Actor('test-fixture-negative-reviewer','reviewer'))
            self.assertEqual(observer.next_action(claim)['action'],'replan')
            _,ctx,cas=domain_packs.analysis_inputs(store,store.events(),self.result['batch'])
            hooks=domain_packs.run_hooks(self.loaded,ctx,cas)
            settlement=next(e for e in store.events() if e['kind']=='batch_settlement' and e['payload']['batch']==self.result['batch'])
            payload={'batch':self.result['batch'],'expected_settlement':settlement['id'],'pack_id':self.loaded.pack_id,
                     'pack_version':self.loaded.pack_version,'pack_code_digest':self.loaded.pack_code_digest,
                     **{key:hooks[key] for key in ('checks','recomputations','report','statistical_report')},'reviewer_actor':'future-human-reviewer'}
            with self.assertRaisesRegex(ValueError,'already applied'):
                command(store,'pack.analyse',payload,actor=ANALYST)
            self.assertEqual(observer.next_action(claim)['action'],'replan')
