"""Descriptive E0 metrics. Synthetic scores never establish scientific validity."""
from collections import Counter, defaultdict
import random

from .lexical import ROLES


def role_metrics(rows):
    matrix = Counter()
    if not rows:
        raise ValueError('No observations')
    for row in rows:
        if row['gold'] not in ROLES or row['predicted'] not in ROLES:
            raise ValueError('Unknown role')
        matrix[row['gold'], row['predicted']] += 1
    scores = {}
    for role in ROLES[:-1]:
        tp = matrix[role, role]
        gold = sum(v for (a, b), v in matrix.items() if a == role)
        predicted = sum(v for (a, b), v in matrix.items() if b == role)
        scores[role] = {'support': gold, 'precision': tp/predicted if predicted else 0,
                        'recall': tp/gold if gold else 0,
                        'f1': 2*tp/(gold+predicted) if gold+predicted else 0}
    return {'macro_f1': sum(r['f1'] for r in scores.values())/8, 'per_role': scores,
            'ambiguous_gold_fraction': sum(r['gold'] == ROLES[-1] for r in rows)/len(rows),
            'confusion': [{'gold': a, 'predicted': b, 'count': v} for (a, b), v in sorted(matrix.items())]}


def grouped_interval(rows, replicates=1000, seed=20261012):
    if type(replicates) is not int or replicates < 2:
        raise ValueError('Bootstrap requires at least two replicates')
    groups = defaultdict(list)
    for row in rows:
        groups[row['root_id']].append(row)
    keys = sorted(groups)
    if len(keys) < 2:
        return {'interval': None, 'reason': 'fewer_than_two_task_roots'}
    rng = random.Random(seed)
    values = sorted(role_metrics([r for _ in keys for r in groups[rng.choice(keys)]])['macro_f1']
                    for _ in range(replicates))
    return {'interval': [values[int(.025*(replicates-1))], values[int(.975*(replicates-1))]],
            'unit': 'task_root', 'replicates': replicates, 'seed': seed}


def boundary_f1(gold, predicted, length):
    # Start/end are structural, not counted as successes.
    if any(type(x) is not int or not 0 < x < length for x in gold+predicted):
        raise ValueError('Invalid internal boundary')
    a, b = set(gold), set(predicted)
    if len(a) != len(gold) or len(b) != len(predicted):
        raise ValueError('Duplicate boundary')
    return {'f1': 2*len(a & b)/(len(a)+len(b)) if a or b else 1.,
            'gold_boundaries': len(a), 'predicted_boundaries': len(b)}


def cohen_kappa(pairs):
    if not pairs:
        raise ValueError('No independent annotation pairs')
    if any(a not in ROLES or b not in ROLES for a, b in pairs):
        raise ValueError('Unknown annotation role')
    n = len(pairs)
    left, right = Counter(a for a, b in pairs), Counter(b for a, b in pairs)
    observed = sum(a == b for a, b in pairs)/n
    expected = sum(left[r]*right[r] for r in ROLES)/(n*n)
    return {'raw_agreement': observed, 'cohen_kappa': (observed-expected)/(1-expected) if expected < 1 else None,
            'degenerate_marginals': expected == 1, 'count': n}
