"""Portable offline Stage 2 evidence: hashes, source bytes, kernel backup and code."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile
from .observations import canonical
from .episteme_bridge import ROOT, register
from episteme.store import Store
from episteme.recovery import backup
from episteme import domain_packs
from episteme.kernel import Kernel, Actor
from reasoning_universalis_v1 import inventory


def chain(store):
    analysis=next(e for e in reversed(store.events()) if e['kind']=='pack_analysis')
    payload=analysis['payload']; _,context,cas=domain_packs.analysis_inputs(store,store.events(),payload['batch'])
    unit=context.draft.roster[0];slot=context.slot('primary:'+str(unit))
    raw=cas.json(slot['outputs']['raw_data'],'root raw')
    segment=raw['segments'][0]
    observation=next(r for r in raw['observations'] if r['identity']['trace_id']==segment['trace_id'])
    record=observation['raw_observations']; response=cas.read(record['raw_response_digest'])
    body=json.loads(response)['json'] if record['capture_kind']=='historical_envelope' else json.loads(response)
    if segment['text']!=inventory.explicit(body)[segment['char_start']:segment['char_end']]:
        raise ValueError('Provenance slice differs')
    request=json.loads(cas.read(record['raw_request_digest']));task=next(t for t in cas.json(context.protocol['data'],'input')['source_bundle']['tasks'] if t['task_id']==segment['task_id'])
    if task['prompt']!=request['request']['messages'][0]['content']:
        raise ValueError('Provenance prompt differs')
    return {'statistical_result_artifact':payload['statistical_report'], 'statistical_protocol_hash':payload['protocol_hash'],
            'primary_metric_artifact':slot['outputs']['metrics'], 'feature':'paired count of native segmentation rows within root',
            'segment_id':segment['segment_id'], 'segment_offsets':[segment['char_start'],segment['char_end']],
            'visible_trace_digest':segment['trace_sha256'], 'raw_response_digest':record['raw_response_digest'],
            'raw_request_digest':record['raw_request_digest'], 'inference_run_digest':observation['run_digest'],
            'inference_identity':observation['identity'], 'provider':observation['inference']['runtime_manifest']['provider'],
            'task_digest':observation['provenance']['task_digest'], 'task_id':task['task_id'],
            'inference_protocol_digest':observation['provenance']['protocol_digest'], 'external_inference':True,
            'local_analysis_run':slot['run'], 'claim':payload['claim'], 'scientific_validity':'not_assessed'}


def export(workspace, destination):
    workspace=Path(workspace);destination=Path(destination);register()
    all_files={}
    for p in (workspace/'import'/'source').rglob('*'):
        if p.is_file(): all_files['source/'+p.relative_to(workspace/'import'/'source').as_posix()]=p.read_bytes()
    with tempfile.TemporaryDirectory(prefix='stage2-export-') as tmp:
        with Store(workspace/'store') as store:
            proof=chain(store);backup(store,Path(tmp)/'backup')
        for p in (Path(tmp)/'backup').rglob('*'):
            if p.is_file(): all_files['kernel-backup/'+p.relative_to(Path(tmp)/'backup').as_posix()]=p.read_bytes()
    all_files['provenance-chain.json']=canonical(proof)
    all_files['workflow-result.json']=(workspace/'workflow-result.json').read_bytes()
    for directory in ('stage2','reasoning_universalis_v1'):
        for p in sorted((ROOT/directory).glob('*.py')):
            all_files['code/'+directory+'/'+p.name]=p.read_bytes()
    rows=[{'path':path,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for path,data in sorted(all_files.items())]
    all_files['manifest.json']=canonical({'schema_version':1,'purpose':'stage2_technical_evidence_not_E0',
                                         'scientific_validity':'not_assessed','files':rows})
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists(): raise ValueError('Evidence export must not overwrite an archive')
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as z:
        for path,data in sorted(all_files.items()):
            info=zipfile.ZipInfo(path,(2026,10,14,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    return {'path':str(destination),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':len(all_files)}


def verify(archive):
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)): raise ValueError('Duplicate ZIP entries')
        manifest=json.loads(z.read('manifest.json'));expected={r['path'] for r in manifest['files']}|{'manifest.json'}
        if set(names)!=expected: raise ValueError('ZIP inventory differs')
        for row in manifest['files']:
            data=z.read(row['path'])
            if hashlib.sha256(data).hexdigest()!=row['sha256'] or len(data)!=row['bytes']:
                raise ValueError('ZIP artifact changed')
        source={n[len('source/'):]:z.read(n) for n in names if n.startswith('source/')}
        bundle=inventory.verify(source)
        proof=json.loads(z.read('provenance-chain.json'))
        raw=source['artifacts/'+proof['raw_response_digest']+'.bin'];body=json.loads(raw)['json']
        selected=next(s for s in bundle['segments'] if s['segment_id']==proof['segment_id'])
        if selected['text']!=inventory.explicit(body)[selected['char_start']:selected['char_end']]:
            raise ValueError('Exported provenance link differs')
        result=json.loads(z.read('workflow-result.json'))
        if result['outcome']!='inconclusive' or result['scientific_validity']!='not_assessed':
            raise ValueError('Technical evidence claims scientific success')
    return {'integrity':'verified','attempts':len(bundle['observations']),'segments':len(bundle['segments']),
            'methods':{m:sum(s['method']==m for s in bundle['segments']) for m in ('S1','S2','S3')},
            'provenance_chain':'verified','E0':'not_passed','scientific_validity':'not_assessed','network_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path);parser.add_argument('--workspace',type=Path)
    parser.add_argument('--verify',type=Path);args=parser.parse_args()
    if args.export:
        if args.workspace is None: parser.error('--workspace required for export')
        print(json.dumps(export(args.workspace,args.export),indent=2))
    elif args.verify: print(json.dumps(verify(args.verify),indent=2))
    else: parser.error('Choose --export or --verify')


if __name__=='__main__': main()
