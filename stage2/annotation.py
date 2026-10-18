"""Finite single-model annotation protocol, rendered offline without dispatch."""
import json
from pathlib import Path
from measurement.core import digest
from .observations import strict

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    return json.loads((ROOT/'design/ANNOTATION_CONFIG.json').read_bytes())


def render(item_id, problem, current, previous, ontology, cluster_representatives=None):
    cfg = configuration(); schema = json.loads((ROOT/cfg['response_schema']).read_bytes())
    template = cfg['cluster_prompt'] if cluster_representatives is not None else cfg['segment_prompt']
    system = (ROOT/template).read_text().split('```text\n', 1)[1].split('\n```', 1)[0]
    if cluster_representatives is None:
        previous = list(previous[-2:]); total = ''.join(previous)[-1000:]
        payload = {'item_id': item_id, 'problem_statement': problem, 'current_segment': current,
                   'previous_segments': [total] if total else [], 'ontology_definitions': ontology, 'response_schema': schema}
    else:
        for representative in cluster_representatives:
            if set(representative) != {'source_id', 'problem_statement', 'previous_segments', 'current_segment'}:
                raise ValueError('Cluster representative exposes forbidden metadata')
            if len(representative['previous_segments']) > 2 or sum(len(t) for t in representative['previous_segments']) > 1000:
                raise ValueError('Cluster context exceeds fixed protocol')
        payload = {'item_id': item_id, 'representatives': cluster_representatives,
                   'ontology_definitions': ontology, 'response_schema': schema}
    return {'system': system, 'user': json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False),
            'prompt_revision': template, 'input_digest': digest(payload), 'schema_digest': digest(schema)}


def parse_vote(data, item_id, sources):
    result = strict(data); cfg = configuration()
    required = {'item_id', 'primary_role', 'secondary_roles', 'confidence', 'reason_code', 'evidence_quotes'}
    if set(result) != required or result['item_id'] != item_id or result['primary_role'] not in cfg['roles']:
        raise ValueError('Annotation schema or identity mismatch')
    secondary = result['secondary_roles']
    if type(secondary) is not list or len(secondary)>3 or len(set(secondary)) != len(secondary) or any(
            x not in cfg['roles'][:-1] or x == result['primary_role'] for x in secondary):
        raise ValueError('Invalid secondary roles')
    schema = json.loads((ROOT/cfg['response_schema']).read_bytes())
    if result['confidence'] not in schema['properties']['confidence']['enum'] or result['reason_code'] not in schema['properties']['reason_code']['enum']:
        raise ValueError('Invalid confidence/reason')
    quotes = result['evidence_quotes']
    if type(quotes) is not list or not 1<=len(quotes)<=3:
        raise ValueError('Missing evidence quotes')
    for q in quotes:
        if set(q) != {'source_id', 'quote'} or q['source_id'] not in sources or not isinstance(q['quote'], str) or not 1<=len(q['quote'])<=400 or q['quote'] not in sources[q['source_id']]:
            raise ValueError('Quote not present in supplied current source')
    return result


def panel(votes, round_number):
    cfg = configuration()
    if round_number not in (1, 2) or len(votes) != cfg['panel_size'] or any(v is None for v in votes):
        return {'status': 'technical_unresolved', 'next_round': None}
    counts = {role: sum(v['primary_role']==role for v in votes) for role in cfg['roles']}
    majority = next((role for role, count in counts.items() if count>=cfg['majority_required']), None)
    if majority:
        return {'status': 'resolved_ambiguous' if majority=='ambiguous_other' else 'resolved',
                'role': majority, 'round_used': round_number, 'next_round': None, 'counts': counts}
    return {'status': 'repeat_required' if round_number==1 else 'ambiguous_unresolved',
            'next_round': 2 if round_number==1 else None, 'counts': counts}
