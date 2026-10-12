"""Segment imported explicit traces offline; never generate or infer reasoning."""
import argparse
import json
from pathlib import Path

from .core import digest, segments, previous_context, split_manifest
from stage0.traces import inspect_trace
import hashlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=Path, required=True, help='JSON list of task identities and prompts')
    parser.add_argument('--traces', type=Path, required=True, help='JSON list of explicit trace records')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--methods', nargs='+', choices=('S1', 'S2', 'S3'), default=['S2'])
    parser.add_argument('--block-size', type=int, default=64)
    args = parser.parse_args()
    tasks = json.loads(args.tasks.read_text(encoding='utf-8'))
    traces = json.loads(args.traces.read_text(encoding='utf-8'))
    if not tasks or not traces:
        raise ValueError('Empty measurement input')
    manifest = split_manifest(tasks)
    assigned = {r['task_id']: r for r in manifest['tasks']}
    ids, raw_ids, generation_ids, rows = set(), set(), set(), []
    for trace in traces:
        task = assigned.get(trace['task_id'])
        if task is None or trace['trace_id'] in ids or trace['root_id'] != task['root_id']:
            raise ValueError('Unknown task, duplicate trace or changed ancestry')
        ids.add(trace['trace_id'])
        raw_path = Path(trace['raw_response_path'])
        if not raw_path.is_absolute():
            raw_path = args.traces.parent / raw_path
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != trace['raw_response_sha256']:
            raise ValueError('Raw response changed')
        if trace['raw_response_sha256'] in raw_ids:
            raise ValueError('Repeated raw generation is not an independent observation')
        raw_ids.add(trace['raw_response_sha256'])
        response = json.loads(raw)
        payload = response.get('json', {})
        generation = payload.get('id')
        if not generation or generation in generation_ids:
            raise ValueError('Missing or repeated generation identity')
        generation_ids.add(generation)
        observed = inspect_trace(payload)
        if response.get('http_status') != 200 or payload.get('error') is not None or payload.get('model') != trace['model_id'] or observed['status'] != 'visible_trace_candidate' or observed['trace'] != trace['visible_reasoning']:
            raise ValueError('Imported trace is not bound to explicit successful model response')
        if trace.get('split', task['split']) != task['split']:
            raise ValueError('Trace split differs from manifest')
        trace = {**trace, 'split': task['split']}
        for method in args.methods:
            measured = segments(trace, method, trace.get('token_map'), trace.get('semantic_boundaries'), args.block_size)
            for i, row in enumerate(measured):
                row['previous_context'] = previous_context(measured, i)
            rows.extend(measured)
    result = {'schema': 'measurement-development-v1', 'scientific_approved': False,
              'token_alignment_complete': all(r['token_alignment'] == 'available' for r in rows),
              'manifest': manifest, 'input_digest': digest(traces), 'segments': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
