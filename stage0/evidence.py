"""Portable, offline Stage 0 evidence export and verification; no API calls."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import zipfile

from .config import Config
from .runner import encode, redact
from .tasks import verify_answer
from .traces import inspect_trace, inspect_embeddings, segment


def export(config, destination):
    files = sorted((config.root / 'stage0').glob('*/*.json'))
    files += [config.root / name for name in ('trace-review.json', 'stage0-audit.json', 'stage0-budget.json')]
    members, records = {}, []
    def portable(value):
        if isinstance(value, dict):
            return {k: portable(v) for k, v in value.items() if k != 'headers'}
        if isinstance(value, list):
            return [portable(v) for v in value]
        if isinstance(value, str):
            return redact(value.replace(str(config.root), 'evidence'), config.key)
        return value
    for path in files:
        if not path.is_file() or path.name in ('catalog.json', 'source-snapshot.json') or path.name.endswith('-endpoints.json'):
            continue
        original = path.read_bytes()
        data = encode(portable(json.loads(original)))
        if config.key.encode() in data:
            raise ValueError('Secret in export')
        name = 'evidence/' + path.relative_to(config.root).as_posix()
        members[name] = data
        records.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'original_artifact_sha256': hashlib.sha256(original).hexdigest()})
    members['manifest.json'] = encode({'version': 1, 'files': records,
        'transformations': ['Removed HTTP headers (including cookies)', 'Replaced research root with evidence',
                            'Redacted reflected API key encodings', 'Re-serialized JSON'],
        'limitations': ['Historical responses retain decoded text, not original wire bytes',
                       'Original hashes identify local artifacts; exported bytes have separate hashes',
                       'This package does not establish scientific validity or independent human review']})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return verify(destination)


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        manifest = json.loads(archive.read('manifest.json'))
        expected = {r['path']: r for r in manifest['files']}
        if set(names) != set(expected) | {'manifest.json'}:
            raise ValueError('Unlisted or missing member')
        documents = {}
        for name, record in expected.items():
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Evidence hash mismatch')
            documents[name] = json.loads(data)
    counts = {'paid_attempts': 0, 'pilot_answers': 0, 'pilot_correct': 0, 'segments': 0,
              'vectors': 0, 'identity_verified_vectors': 0, 'embedding_failures': []}
    for name, response in documents.items():
        if not name.endswith('-response.json'):
            continue
        request_name = name.removesuffix('-response.json') + '-request.json'
        sent = documents[request_name]
        model, payload = sent['model'], response.get('json', {})
        counts['paid_attempts'] += 1
        if '/pilot-embedding-' in name:
            check = inspect_embeddings(payload, model, len(sent['request']['input']))
            counts['vectors'] += len(payload['data'])
            if response['http_status'] != 200 or not check['valid']:
                counts['embedding_failures'].append({'path': name, 'requested_model': model,
                    'returned_model': payload.get('model'), 'reason': check.get('reason', 'unsuccessful HTTP')})
            else:
                counts['identity_verified_vectors'] += len(payload['data'])
        elif '/pilot-' in name:
            context = documents[name.rsplit('/', 1)[0] + '/context.json']
            task = context['tasks'][int(name.rsplit('-', 2)[1])]
            if response['http_status'] != 200 or payload.get('error') is not None or payload.get('model') != model:
                raise ValueError('Invalid pilot model response')
            trace = inspect_trace(payload)
            if trace['status'] != 'visible_trace_candidate':
                raise ValueError('Missing pilot trace')
            counts['pilot_answers'] += 1
            counts['pilot_correct'] += int(verify_answer(task, trace['answer'])['correct'])
            counts['segments'] += len(segment(trace['trace']))
    audit = documents['evidence/stage0-audit.json']
    billing = audit['billing']
    response_names = {name for name in documents if name.endswith('-response.json')}
    if {r['response_path'].replace('\\', '/') for r in billing} != response_names:
        raise ValueError('Billing audit does not cover recorded attempts')
    for row in billing:
        response_name = row['response_path'].replace('\\', '/')
        if row['sha256'] != expected[response_name]['original_artifact_sha256']:
            raise ValueError('Billing reference does not match original response hash')
    counts.update(confirmed_billing=sum(r.get('total_cost_rub') is not None for r in billing),
                  unknown_billing=sum(r.get('total_cost_rub') is None for r in billing),
                  confirmed_cost_rub=str(sum((Decimal(r['total_cost_rub']) for r in billing
                                             if r.get('total_cost_rub') is not None), Decimal(0))))
    # Recompute billing from the saved API receipts, rather than trust the audit totals.
    for row in billing:
        if row.get('total_cost_rub') is None:
            continue
        receipt_name = row['response_path'].replace('\\', '/').removesuffix('-response.json') + '-billing.json'
        receipt = documents[receipt_name]
        if receipt['http_status'] != 200 or Decimal(str(receipt['json']['data']['total_cost'])) != Decimal(row['total_cost_rub']):
            raise ValueError('Billing receipt mismatch')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--env', default='.env')
    args = parser.parse_args()
    if bool(args.export) == bool(args.verify):
        parser.error('Choose either --export or --verify')
    print(json.dumps(export(Config.load(args.env), args.export) if args.export else verify(args.verify), indent=2))


if __name__ == '__main__':
    main()
