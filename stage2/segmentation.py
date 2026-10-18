"""Non-LLM semantic-operation heuristic and independent segmentation comparison."""
import re
from measurement.core import segments, sentence_boundaries, digest, previous_context

MARKERS = (r'\b(?:plan|strategy|first|next|сначала|план|далее)\b',
           r'\b(?:check|verify|провер|подставим)\w*',
           r'\b(?:alternatively|instead|or we|альтернатив|другой)\w*',
           r'\b(?:wait|mistake|wrong|correcting|ошиб|исправ)\w*',
           r'\b(?:therefore|finally|answer is|thus the answer|итак|ответ)\w*')


def semantic_boundaries(text):
    """Group adjacent sentences until an explicit operation marker changes.

    No labels are assigned. This conservative heuristic is testable, not human
    annotation or validated semantic recovery; E0 must measure its error.
    """
    sentence = sentence_boundaries(text); boundaries = []; previous = None
    for start, end in zip(sentence, sentence[1:]):
        prefix = text[start:end].lstrip()[:160]
        marker = next((i for i, pattern in enumerate(MARKERS) if re.search(pattern, prefix, re.I)), None)
        if start and marker is not None and marker != previous:
            boundaries.append(start)
        if marker is not None:
            previous = marker
    return boundaries


def measure(trace, method, token_map, block_size=64, human_boundaries=None):
    boundaries = None
    if method == 'S1':
        boundaries = human_boundaries if human_boundaries is not None else semantic_boundaries(trace['visible_reasoning'])
    rows = segments(trace, method, token_map, boundaries, block_size)
    if method == 'S1' and human_boundaries is None:
        for row in rows:
            row['segmentation_version'] = 'operation-cue-heuristic-v1'
            row['measurement_config_digest'] = digest({'base': row['measurement_config_digest'],
                                                       'segmentation_version': row['segmentation_version']})
            row['segment_id'] = digest([trace['trace_id'], row['trace_sha256'],
                                        row['measurement_config_digest'], row['char_start'], row['char_end']])
    for index, row in enumerate(rows):
        row['previous_context'] = previous_context(rows, index)
        row['method'] = method
        row['tokenizer_scope'] = token_map.get('tokenizer_scope', 'supplied_model_map')
    return rows


def transitions(rows):
    groups = {}
    for row in rows:
        key = (row['trace_id'], row['measurement_config_digest'])
        groups.setdefault(key, []).append(row)
    edges = []
    for key in sorted(groups):
        seq = sorted(groups[key], key=lambda row: row['position'])
        if [r['position'] for r in seq] != list(range(len(seq))):
            raise ValueError('Missing/duplicate positions in trajectory')
        for a, b in zip(seq, seq[1:]):
            if a['char_end'] != b['char_start']:
                raise ValueError('Noncontiguous segments')
            edges.append({'trace_id': key[0], 'from': a['segment_id'], 'to': b['segment_id']})
    return edges


def compare_segmentations(left, right):
    """Pair raw observations, retaining distinct segment IDs; no test alignment."""
    def group(rows):
        result = {}
        for row in rows:
            result.setdefault(row['trace_id'], []).append(row)
        return result
    a, b = group(left), group(right); common = sorted(set(a)&set(b)); pairs = []
    for trace in common:
        for field in ('raw_response_sha256', 'trace_sha256', 'root_id'):
            if {r[field] for r in a[trace]} != {r[field] for r in b[trace]} or len({r[field] for r in a[trace]}) != 1:
                raise ValueError('Cross-segmentation raw/root mismatch')
        pairs.append({'trace_id': trace, 'root_id': a[trace][0]['root_id'],
                      'left_segments': len(a[trace]), 'right_segments': len(b[trace])})
    return {'pairs': pairs, 'excluded_left': sorted(set(a)-set(b)), 'excluded_right': sorted(set(b)-set(a))}
