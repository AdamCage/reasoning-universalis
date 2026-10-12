"""Read-only billing reconciliation and local integrity checks; no model calls."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from .config import Config
from .runner import http, encode, redact


def audit(config):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'EpistemeOS' / 'src'))
    from episteme.store import Store
    store = Store(config.store_root)
    billing = []
    total = Decimal(0)
    attempts = 0
    for path in sorted((config.root / 'stage0').glob('*/*-response.json')):
        attempts += 1
        data = json.loads(path.read_text(encoding='utf-8'))
        generation = data.get('json', {}).get('id')
        entry = {'response_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'generation_id': generation, 'total_cost_rub': None}
        if generation:
            result = http('/generation?id=' + quote(generation, safe=''), config.key)
            evidence = redact(encode(result).decode('utf-8'), config.key).encode('utf-8')
            dest = path.with_name(path.name.replace('-response.json', '-billing.json'))
            dest.write_bytes(evidence)
            entry['billing_artifact'] = store.put(evidence)
            reported = result.get('json', {}).get('data', {}).get('total_cost')
            if reported is not None:
                cost = Decimal(str(reported))
                if not cost.is_finite() or cost < 0:
                    raise ValueError('Invalid reported billing cost')
                entry['total_cost_rub'] = str(cost)
                total += cost
                entry['provider'] = result['json']['data'].get('provider')
        billing.append(entry)
    # Scan bytes for the literal key and JSON/URL encodings without printing it.
    secrets = [config.key.encode('utf-8'), json.dumps(config.key)[1:-1].encode('utf-8'),
               quote(config.key, safe='').encode('utf-8')]
    paths = list(config.root.rglob('*')) + list(Path('stage0').glob('*.py')) + list(Path('tests').glob('*.py'))
    scanned = 0
    for path in paths:
        if path.is_file():
            scanned += 1
            if any(secret in path.read_bytes() for secret in secrets):
                raise ValueError('Secret found in a research or source file; publication blocked')
    # CAS integrity: every content-addressed file must match its filename.
    cas_count = 0
    for path in store.blobs.rglob('*'):
        if path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
                raise ValueError('EpistemeOS artifact hash mismatch')
            cas_count += 1
    summary = {'billing': billing, 'response_attempts': attempts,
               'confirmed_cost_rub': str(total),
               'cost_unreported_attempts': sum(x['total_cost_rub'] is None for x in billing),
               'secret_scan_files': scanned, 'secret_scan_passed': True,
               'cas_verified_artifacts': cas_count, 'scientific_review': 'not_performed'}
    data = encode(summary)
    (config.root / 'stage0-audit.json').write_bytes(data)
    artifact = store.put(data)
    store.db.close()
    print('Billing confirmed:', total, 'RUB; unreported attempts:', summary['cost_unreported_attempts'])
    print('Secret scan and CAS integrity passed; audit artifact:', artifact)
    return summary


if __name__ == '__main__':
    audit(Config.load())
