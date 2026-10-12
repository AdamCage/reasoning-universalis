"""Training-only TF-IDF nearest centroid baseline, without additional LLMs."""
from collections import Counter
import math
import re

from .core import digest

ROLES = ('problem_formulation', 'planning', 'deduction_computation', 'exploration',
         'verification', 'uncertainty', 'backtracking_correction', 'conclusion', 'ambiguous_other')


def terms(text):
    return re.findall(r'\w+', text.casefold())


def normalize(vector):
    length = math.sqrt(sum(x*x for x in vector.values()))
    return {k: v/length for k, v in vector.items()} if length else {}


class LexicalBaseline:
    def fit(self, rows, manifest, heldout_families=()):
        if not rows:
            raise ValueError('Empty training data')
        assignments = {r['task_id']: r for r in manifest['tasks']}
        if len(assignments) != len(manifest['tasks']):
            raise ValueError('Duplicate manifest task ID')
        root_splits = {}
        for task in manifest['tasks']:
            root = task['root_id']
            if root in root_splits and root_splits[root] != task['split']:
                raise ValueError('Task variants cross split boundaries')
            root_splits[root] = task['split']
        payload = {k: v for k, v in manifest.items() if k != 'manifest_digest'}
        if digest(payload) != manifest['manifest_digest']:
            raise ValueError('Changed split manifest')
        seen = set()
        for row in rows:
            task = assignments.get(row['task_id'])
            if task is None or task['root_id'] != row['root_id'] or task['split'] != 'development' or row['split'] != 'development':
                raise ValueError('Training crosses allowed task split')
            if row['family'] in heldout_families:
                raise ValueError('Held-out family in training')
            if row['segment_id'] in seen or row.get('role') not in ROLES:
                raise ValueError('Duplicate segment or invalid annotation')
            seen.add(row['segment_id'])
        df = Counter()
        for row in rows:
            df.update(set(terms(row['text'])))
        self.idf = {word: math.log((1+len(rows))/(1+count))+1 for word, count in df.items()}
        self.centroids = {}
        for row in rows:
            target = self.centroids.setdefault(row['role'], Counter())
            target.update(self.vector(row['text']))
        self.centroids = {role: normalize(values) for role, values in self.centroids.items()}
        self.provenance = {'version': 'tfidf-nearest-centroid-v1',
                           'training_digest': digest(rows), 'manifest_digest': manifest['manifest_digest'],
                           'heldout_families': sorted(heldout_families),
                           'training_roots': sorted({r['root_id'] for r in rows})}
        self.model_digest = digest({'idf': self.idf, 'centroids': self.centroids, 'provenance': self.provenance})
        return self

    def vector(self, text):
        frequencies = Counter(terms(text))
        return normalize({word: (1+math.log(count))*self.idf[word]
                          for word, count in frequencies.items() if word in self.idf})

    def predict(self, text):
        if not hasattr(self, 'centroids'):
            raise ValueError('Baseline is not fitted')
        vector = self.vector(text)
        if not vector:
            return {'role': 'ambiguous_other', 'reason': 'no_training_vocabulary', 'scores': {}}
        scores = {role: sum(value*centroid.get(word, 0) for word, value in vector.items())
                  for role, centroid in self.centroids.items()}
        return {'role': sorted(scores, key=lambda role: (-scores[role], role))[0],
                'scores': scores, 'model_digest': self.model_digest}
