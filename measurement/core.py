import hashlib
import json
import re
import unicodedata


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def split_manifest(tasks, seed='measurement-development-v1'):
    """All variants share root_id. Unknown ancestry must not reach this function."""
    groups, ids, prompts = {}, set(), {}
    for task in tasks:
        required = ('task_id', 'root_id', 'domain', 'generator_id', 'prompt')
        if any(not isinstance(task.get(k), str) or not task[k].strip() for k in required):
            raise ValueError('Missing task identity or resolved ancestry')
        if task['task_id'] in ids:
            raise ValueError('Duplicate task ID')
        ids.add(task['task_id'])
        fingerprint = text_hash(' '.join(unicodedata.normalize('NFKC', task['prompt']).split()))
        if fingerprint in prompts and prompts[fingerprint] != task['root_id']:
            raise ValueError('Duplicate prompt across task roots; resolve ancestry first')
        prompts[fingerprint] = task['root_id']
        root = task['root_id']
        if task.get('previously_observed') and task.get('forced_split') != 'development':
            raise ValueError('Previously inspected task must remain development-only')
        forced = task.get('forced_split')
        if forced not in (None, 'development'):
            raise ValueError('Only exclusion to development may override allocation')
        metadata = (task['domain'], task['generator_id'])
        if root in groups and groups[root]['metadata'] != metadata:
            raise ValueError('Root spans domains/generators; resolve grouping before split')
        bucket = int(digest([seed, root])[:16], 16) % 100
        split = 'development' if bucket < 60 else 'measurement_validation' if bucket < 80 else 'confirmatory'
        if forced == 'development':
            split = 'development'
        if root in groups and groups[root]['split'] != split:
            raise ValueError('Variants have inconsistent exclusion flags')
        groups.setdefault(root, {'metadata': metadata, 'split': split, 'task_ids': []})['task_ids'].append(task['task_id'])
    rows = [{'task_id': t['task_id'], 'root_id': t['root_id'], 'domain': t['domain'],
             'generator_id': t['generator_id'], 'prompt_sha256': text_hash(t['prompt']),
             'split': groups[t['root_id']]['split']} for t in sorted(tasks, key=lambda t: t['task_id'])]
    payload = {'version': 'task-splits-v1', 'seed': seed, 'allocation': [60, 20, 20],
               'status': 'development_design_not_G2', 'tasks': rows,
               'task_set_digest': digest(sorted(tasks, key=lambda t: t['task_id']))}
    return {**payload, 'manifest_digest': digest(payload)}


def validate_token_map(text, mapping):
    if mapping.get('text_sha256') != text_hash(text) or not mapping.get('tokenizer_id') or not mapping.get('tokenizer_revision'):
        raise ValueError('Token map must bind exact text and tokenizer revision')
    offsets = mapping.get('offsets')
    if not isinstance(offsets, list) or not offsets:
        raise ValueError('Missing real token offsets')
    previous = 0
    for pair in offsets:
        if not isinstance(pair, list) or len(pair) != 2 or any(type(x) is not int for x in pair):
            raise ValueError('Invalid token offset')
        start, end = pair
        if not previous <= start < end <= len(text) or text[previous:start].strip():
            raise ValueError('Overlapping token map or uncovered non-whitespace text')
        previous = end
    if text[previous:].strip():
        raise ValueError('Token map does not cover trace')
    return offsets


def sentence_boundaries(text):
    protected = [m.span() for m in re.finditer(r'```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$', text)]
    boundaries = []
    for match in re.finditer(r'[.!?](?:["\u201d\u2019)]*)(?=\s|$)|\n\s*\n', text):
        if any(start <= match.start() < end for start, end in protected):
            continue
        prefix = text[:match.start() + 1]
        if re.search(r'(?:^|\n)\s*\d+[.]$', prefix) or re.search(r'\b(?:Dr|Mr|Mrs|Ms|Prof|vs|etc|e\.g|i\.e)[.]$', prefix, re.I):
            continue
        boundaries.append(match.end())
    consolidated = [0]
    for end in sorted(set([*boundaries, len(text)])):
        if text[consolidated[-1]:end].strip():
            consolidated.append(end)
        elif end == len(text) and len(consolidated) > 1:
            consolidated[-1] = end
    return consolidated


def segments(trace, method, token_map=None, semantic_boundaries=None, block_size=64):
    text = trace['visible_reasoning']
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Explicit visible reasoning required')
    offsets = validate_token_map(text, token_map) if token_map is not None else None
    if method == 'S1':
        if semantic_boundaries is None:
            raise ValueError('S1 requires independently annotated semantic boundaries')
        boundaries = [0, *semantic_boundaries, len(text)]
        if any(type(x) is not int for x in boundaries) or boundaries != sorted(set(boundaries)) or any(x < 0 or x > len(text) for x in boundaries):
            raise ValueError('Invalid semantic boundaries')
        version = 'human-semantic-v1'
    elif method == 'S2':
        boundaries, version = sentence_boundaries(text), 'protected-sentence-v1'
    elif method == 'S3':
        if offsets is None or type(block_size) is not int or block_size < 1:
            raise ValueError('S3 requires a real token map and positive block size')
        boundaries = [0, *[offsets[i][0] for i in range(block_size, len(offsets), block_size)], len(text)]
        version = 'fixed-token-v1'
    else:
        raise ValueError('Unknown segmentation')
    config = {'method': method, 'version': version, 'block_size': block_size if method == 'S3' else None,
              'token_map_digest': digest(token_map) if token_map else None,
              'semantic_boundaries': semantic_boundaries if method == 'S1' else None}
    result = []
    for position, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        token_ids = [i for i, (a, b) in enumerate(offsets or []) if a < end and b > start]
        row = {'trace_id': trace['trace_id'], 'task_id': trace['task_id'], 'root_id': trace['root_id'],
               'family': trace['family'], 'split': trace['split'], 'raw_response_sha256': trace['raw_response_sha256'],
               'text': text[start:end], 'char_start': start, 'char_end': end,
               'token_start': min(token_ids) if token_ids else None,
               'token_end': max(token_ids) + 1 if token_ids else None,
               'token_alignment': 'available' if offsets is not None else 'unavailable',
               'position': position, 'relative_progress': end / len(text),
               'length_characters': end - start, 'trace_sha256': text_hash(text),
               'measurement_config_digest': digest(config), 'segmentation_version': version}
        row['segment_id'] = digest([trace['trace_id'], row['trace_sha256'], digest(config), start, end])
        result.append(row)
    return result


def previous_context(rows, index, count=2, character_cap=1000):
    """Only earlier segments in this trace. Retrospective progress is not an online feature."""
    current = rows[index]
    previous = rows[max(0, index-count):index]
    if any(r['trace_id'] != current['trace_id'] or r['char_end'] > current['char_start'] for r in previous):
        raise ValueError('Context crosses trace boundary or looks ahead')
    return ''.join(r['text'] for r in previous)[-character_cap:]


def paired_embeddings(left, right):
    """Compare both embedders on exactly the same eligible segments."""
    def eligible(rows):
        if len({r['segment_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate embedding observation')
        return {r['segment_id']: r for r in rows if r['identity_verified'] and r['valid']}
    a, b = eligible(left), eligible(right)
    shared = sorted(a.keys() & b.keys())
    for segment_id in shared:
        for field in ('trace_sha256', 'char_start', 'char_end', 'measurement_config_digest', 'input_sha256'):
            if field not in a[segment_id] or field not in b[segment_id] or a[segment_id][field] != b[segment_id][field]:
                raise ValueError('Paired embeddings have different text, boundaries or measurement conditions')
    return {'segment_ids': shared, 'excluded_left': sorted(a.keys()-b.keys()),
            'excluded_right': sorted(b.keys()-a.keys()), 'pairing_digest': digest(shared)}
