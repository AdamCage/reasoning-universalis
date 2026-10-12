"""Offline S2 import of the six public historical traces, development only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from stage0.traces import inspect_trace


def prepare(directory, archive_path='evidence/stage0-2026-10-12.zip'):
    directory.mkdir(parents=True, exist_ok=True)
    tasks, traces = [], []
    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(n for n in archive.namelist() if '/pilot-openai_' in n and n.endswith('-response.json'))
        for name in names:
            index = int(name.rsplit('-', 2)[1])
            context = json.loads(archive.read(name.rsplit('/', 1)[0] + '/context.json'))
            task = context['tasks'][index]
            task_id = 'historical-stage0-' + task['id']
            tasks.append({'task_id': task_id, 'root_id': task_id, 'domain': task['domain'],
                          'generator_id': 'stage0-fixed-manifest', 'prompt': task['prompt'],
                          'previously_observed': True, 'forced_split': 'development'})
            raw = archive.read(name)
            response = json.loads(raw)
            local = Path(name).name
            (directory / local).write_bytes(raw)
            traces.append({'trace_id': response['json']['id'], 'task_id': task_id, 'root_id': task_id,
                           'family': 'openai-gpt-oss', 'model_id': response['json']['model'],
                           'visible_reasoning': inspect_trace(response['json'])['trace'],
                           'raw_response_path': local, 'raw_response_sha256': hashlib.sha256(raw).hexdigest()})
    for filename, value in (('tasks.json', tasks), ('traces.json', traces)):
        (directory / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return directory / 'tasks.json', directory / 'traces.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.research/measurement-demo'))
    args = parser.parse_args()
    tasks, traces = prepare(args.output)
    output = args.output / 'measured.json'
    subprocess.run([sys.executable, '-m', 'measurement.cli', '--tasks', str(tasks), '--traces', str(traces),
                    '--output', str(output)], check=True)
    result = json.loads(output.read_text(encoding='utf-8'))
    print(json.dumps({'historical_traces': len(json.loads(traces.read_text(encoding='utf-8'))),
                      'segments_s2': len(result['segments']), 'input_digest': result['input_digest'],
                      'manifest_digest': result['manifest']['manifest_digest'],
                      'scientific_approved': False, 'token_alignment_complete': result['token_alignment_complete']}, indent=2))


if __name__ == '__main__':
    main()
