"""Training-only lexical representation and provenance-bound RouterAI adapters."""
from collections import Counter
import math
from measurement.core import digest, text_hash, previous_context
from measurement.lexical import terms, normalize
from stage0.config import EMBEDDERS
from stage0.traces import inspect_embeddings


def training_rows(rows, manifest, heldout_families=()):
    if manifest['manifest_digest'] != digest({k: v for k, v in manifest.items() if k != 'manifest_digest'}):
        raise ValueError('Split manifest changed')
    assignments = {r['task_id']: r for r in manifest['tasks']}; seen = set(); roots = {}
    for task in manifest['tasks']:
        if task['root_id'] in roots and roots[task['root_id']] != task['split']:
            raise ValueError('Root crosses splits')
        roots[task['root_id']] = task['split']
    for row in rows:
        task = assignments.get(row['task_id'])
        if task is None or task['split'] != 'development' or row['split'] != 'development' or row['root_id'] != task['root_id']:
            raise ValueError('Fit crosses development roots')
        if row['family'] in heldout_families or row['segment_id'] in seen:
            raise ValueError('Heldout family or duplicate segment in fit')
        seen.add(row['segment_id'])
    if not rows:
        raise ValueError('Empty fit')
    return rows


class Tfidf:
    def fit(self, rows, manifest, heldout_families=()):
        rows = training_rows(rows, manifest, heldout_families); df = Counter()
        for row in rows:
            df.update(set(terms(row['text'])))
        self.vocabulary = sorted(df)
        self.idf = [math.log((1+len(rows))/(1+df[t]))+1 for t in self.vocabulary]
        self.provenance = {'training_roots': sorted({r['root_id'] for r in rows}),
                           'training_families': sorted({r['family'] for r in rows}),
                           'training_digest': digest(rows), 'manifest_digest': manifest['manifest_digest'],
                           'heldout_families': sorted(heldout_families)}
        self.revision = digest({'vocabulary': self.vocabulary, 'idf': self.idf, 'provenance': self.provenance})
        return self

    def transform(self, text):
        counts = Counter(terms(text))
        vector = [(1+math.log(counts[t]))*idf if counts[t] else 0 for t, idf in zip(self.vocabulary, self.idf)]
        norm = math.sqrt(sum(v*v for v in vector))
        return [v/norm for v in vector] if norm else vector


def inputs(rows, context_mode='Local'):
    if context_mode not in ('Local', 'Contextual'):
        raise ValueError('Unknown embedding condition')
    result = []; histories = {}
    for i, row in enumerate(rows):
        history = histories.setdefault((row['trace_id'], row['measurement_config_digest']), [])
        context = ''.join(r['text'] for r in history[-2:])[-1000:] if context_mode == 'Contextual' else ''
        if history and history[-1]['char_end'] > row['char_start']:
            raise ValueError('Embedding context sees future or duplicate segments')
        history.append(row)
        text = context+row['text']
        result.append({'segment_id': row['segment_id'], 'input': text, 'input_sha256': text_hash(text),
                       'context_mode': context_mode, 'context_sha256': text_hash(context),
                       'trace_sha256': row['trace_sha256'], 'char_start': row['char_start'],
                       'char_end': row['char_end'], 'measurement_config_digest': row['measurement_config_digest']})
    return result


class EmbeddingAdapter:
    """Injected transport must journal/reserve; no unbudgeted HTTP implementation."""
    def __init__(self, model, transport):
        if model not in EMBEDDERS:
            raise ValueError('Only the two approved semantic embedders')
        self.model, self.transport = model, transport

    def collect(self, rows, context_mode='Local'):
        observations = inputs(rows, context_mode)
        request = {'model': self.model, 'input': [row['input'] for row in observations]}
        response = self.transport('/embeddings', request)
        inspection = inspect_embeddings(response.get('json', {}), self.model, len(rows))
        valid = response.get('http_status') == 200 and inspection['valid']
        indexed = {d['index']: d['embedding'] for d in response.get('json', {}).get('data', [])
                   if isinstance(d, dict) and type(d.get('index')) is int and 'embedding' in d}
        return [{**row, 'model_id': self.model, 'returned_model': response.get('json', {}).get('model'),
                 'provider': response.get('json', {}).get('provider', 'unknown'),
                 'model_revision': response.get('model_revision', 'unknown'),
                 'vector': indexed.get(i) if valid else None, 'valid': bool(valid),
                 'identity_verified': bool(valid), 'request_digest': digest(request),
                 'response_digest': digest(response), 'condition_digest': digest([self.model, context_mode]),
                 'reason': None if valid else inspection.get('reason', 'HTTP/shape failure')}
                for i, row in enumerate(observations)]
