"""Cluster-first states: fitted training centroids, no fixed eight-role classifier."""
import math
import random
from measurement.core import digest
from .representations import training_rows


def distance(a, b):
    if len(a) != len(b) or not a:
        raise ValueError('Incompatible vectors')
    return sum((x-y)**2 for x, y in zip(a, b))


class StateDiscovery:
    def fit(self, rows, vectors, manifest, k, seed=0, heldout_families=(), iterations=50):
        training_rows(rows, manifest, heldout_families)
        if type(k) is not int or not 1 <= k <= len(vectors) or len(rows) != len(vectors):
            raise ValueError('Invalid state count/roster')
        dimension = len(vectors[0])
        if not dimension or any(len(v) != dimension or any(type(x) not in (int, float) or not math.isfinite(x) for x in v) for v in vectors):
            raise ValueError('Malformed vectors')
        rng = random.Random(seed)
        self.centers = [list(vectors[i]) for i in rng.sample(range(len(vectors)), k)]
        for _ in range(iterations):
            labels = [self.assign(v) for v in vectors]
            centers = []
            for j, old in enumerate(self.centers):
                members = [v for v, label in zip(vectors, labels) if label == j]
                centers.append([sum(v[d] for v in members)/len(members) for d in range(dimension)] if members else old)
            if centers == self.centers:
                break
            self.centers = centers
        self.provenance = {'version': 'training-kmeans-v1', 'k': k, 'seed': seed, 'iterations': iterations,
                           'training_roots': sorted({r['root_id'] for r in rows}),
                           'training_families': sorted({r['family'] for r in rows}),
                           'heldout_families': sorted(heldout_families), 'training_digest': digest([rows, vectors]),
                           'manifest_digest': manifest['manifest_digest']}
        self.revision = digest({'centers': self.centers, 'provenance': self.provenance})
        self.mapping = None
        return self

    def assign(self, vector):
        if not hasattr(self, 'centers'):
            raise ValueError('No fitted states')
        return min(range(len(self.centers)), key=lambda j: (distance(vector, self.centers[j]), j))

    def freeze_mapping(self, mapping, evidence, training_roots):
        if set(training_roots)-set(self.provenance['training_roots']):
            raise ValueError('Mapping sees heldout roots')
        if not evidence or set(mapping) != {str(j) for j in range(len(self.centers))}:
            raise ValueError('Mapping needs full roster and evidence')
        self.mapping = dict(mapping)
        self.mapping_revision = digest({'mapping': mapping, 'evidence': evidence, 'fit': self.revision})

    def predict(self, vector):
        state = str(self.assign(vector))
        return {'state': state, 'role': self.mapping.get(state, 'ambiguous_other') if self.mapping else 'uninterpreted',
                'fit_revision': self.revision, 'mapping_revision': getattr(self, 'mapping_revision', None)}


def grouped_folds(rows, count, seed=0):
    roots = sorted({r['root_id'] for r in rows})
    if type(count) is not int or not 2 <= count <= len(roots):
        raise ValueError('Insufficient independent root groups')
    random.Random(seed).shuffle(roots)
    return [set(roots[i::count]) for i in range(count)]


def select_k(rows, vectors, manifest, candidates, folds=3, seed=0, heldout_families=()):
    """Development-only grouped validation distortion with finite prespecified K.

    This engineering selection is not optimized for universality; full E0,
    stability and predictive checks remain separate scientific evaluations.
    """
    training_rows(rows, manifest, heldout_families); groups = grouped_folds(rows, folds, seed)
    scores = {}
    for k in sorted(set(candidates)):
        if type(k) is not int or k < 1:
            raise ValueError('Invalid finite K grid')
        by_root = {}
        for heldout in groups:
            train = [i for i, row in enumerate(rows) if row['root_id'] not in heldout]
            test = [i for i, row in enumerate(rows) if row['root_id'] in heldout]
            if k > len(train):
                raise ValueError('K exceeds fold training count')
            model = StateDiscovery().fit([rows[i] for i in train], [vectors[i] for i in train], manifest, k, seed, heldout_families)
            for i in test:
                by_root.setdefault(rows[i]['root_id'], []).append(distance(vectors[i], model.centers[model.assign(vectors[i])]))
        scores[k] = sum(sum(v)/len(v) for v in by_root.values())/len(by_root)
    selected = min(scores, key=lambda k: (scores[k], k))
    return selected, {'criterion': 'root_grouped_validation_distortion', 'scores': scores,
                      'fold_roots': [sorted(g) for g in groups], 'candidates': sorted(scores), 'seed': seed}


def nested_lexical_discovery(rows, manifest, candidates=(2, 3, 4), outer_folds=3, inner_folds=2,
                             seed=0, heldout_families=()):
    """Refit vocabulary/IDF and centers in every inner and outer training fold.

    Returns development diagnostics, never a scientific acceptance decision.
    Insufficient roots or model-family coverage is explicit, not segment CV.
    """
    from .representations import Tfidf
    training_rows(rows, manifest, heldout_families)
    outer = grouped_folds(rows, outer_folds, seed); diagnostics = []
    for outer_index, unseen in enumerate(outer):
        allowed = [r for r in rows if r['root_id'] not in unseen]
        inner = grouped_folds(allowed, inner_folds, seed+outer_index+1); scores = {}
        for k in sorted(set(candidates)):
            losses = {}
            for fold in inner:
                train = [r for r in allowed if r['root_id'] not in fold]
                valid = [r for r in allowed if r['root_id'] in fold]
                representation = Tfidf().fit(train, manifest, heldout_families)
                model = StateDiscovery().fit(train, [representation.transform(r['text']) for r in train],
                                            manifest, k, seed, heldout_families)
                for row in valid:
                    vector = representation.transform(row['text'])
                    losses.setdefault(row['root_id'], []).append(distance(vector, model.centers[model.assign(vector)]))
            means = [sum(v)/len(v) for v in losses.values()]
            average = sum(means)/len(means)
            se = math.sqrt(sum((v-average)**2 for v in means)/(len(means)*(len(means)-1))) if len(means)>1 else 0
            scores[k] = {'loss': average, 'standard_error': se}
        best = min(scores, key=lambda k: scores[k]['loss'])
        selected = min(k for k in scores if scores[k]['loss'] <= scores[best]['loss']+scores[best]['standard_error'])
        representation = Tfidf().fit(allowed, manifest, heldout_families)
        model = StateDiscovery().fit(allowed, [representation.transform(r['text']) for r in allowed],
                                    manifest, selected, seed, heldout_families)
        test = [r for r in rows if r['root_id'] in unseen]
        diagnostics.append({'outer_test_roots': sorted(unseen), 'training_roots': model.provenance['training_roots'],
                            'inner_scores': scores, 'selected_k': selected, 'criterion': 'smallest_K_within_one_root_SE',
                            'representation_revision': representation.revision, 'fit_revision': model.revision,
                            'test_states': [model.predict(representation.transform(r['text'])) for r in test]})
    return {'mode': 'development_nested_grouped', 'outer_folds': diagnostics,
            'heldout_families': sorted(heldout_families), 'E0': 'not_passed'}
