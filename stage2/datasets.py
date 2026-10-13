"""Deterministic development generators with independent, non-model verifiers."""
import itertools
import json
import math
import random
from measurement.core import digest

DOMAINS = ('math', 'logic', 'algorithms', 'planning')
VERSION = 'd1-d4-development-v1'


def generate(domain, seed, difficulty='medium'):
    if domain not in DOMAINS or type(seed) is not int or seed < 0:
        raise ValueError('Invalid domain/seed')
    if difficulty not in ('easy', 'medium', 'hard'):
        raise ValueError('Invalid solver-based difficulty')
    rng = random.Random(seed)
    n = {'easy': 3, 'medium': 5, 'hard': 7}[difficulty]
    if domain == 'math':
        a, b, c = rng.randint(2, 9), rng.randint(1, 9), rng.randint(1, 9)
        data = {'a': a, 'b': b, 'c': c, 'power': n}
        prompt = f'Compute ({a}+{b})^{n}-{c} exactly. Return ANSWER: <integer>.'
        solver_work = n
    elif domain == 'logic':
        # Random CNF; no planted answer or solved label is included in the prompt.
        data = {'variables': n, 'clauses': [[rng.choice((-1, 1))*rng.randint(1, n)
                                          for _ in range(3)] for _ in range(n+2)]}
        prompt = ('Determine whether this CNF is satisfiable (positive integer means variable, '
                  'negative means negation): '+json.dumps(data)+'. Return ANSWER: SAT or ANSWER: UNSAT.')
        solver_work = 2**n
    elif domain == 'algorithms':
        edges = [[a, b] for a in range(n) for b in range(a+1, n) if rng.random() < .45]
        data = {'nodes': n, 'edges': edges}
        prompt = ('Find the lexicographically smallest topological ordering of nodes 0..'
                  f'{n-1} with directed edges {edges}. No tools. Return ANSWER: <JSON array>.')
        solver_work = math.factorial(n)
    else:
        data = {'initial': rng.randint(1, 3), 'target': rng.randint(12, 20), 'max_steps': n+2,
                'operations': ['add2', 'double']}
        prompt = ('Starting at '+str(data['initial'])+', reach '+str(data['target'])+
                  ' using add2 or double, at most '+str(data['max_steps'])+
                  ' actions. Return ANSWER: <JSON array of actions> or ANSWER: IMPOSSIBLE.')
        solver_work = 2**(n+2)
    # Conservative grouping: all instances of one structural template stay together.
    root = f'{VERSION}:{domain}:{difficulty}:template1'
    task = {'task_id': f'{VERSION}:{domain}:{difficulty}:{seed}', 'root_id': root,
            'domain': domain, 'generator_id': VERSION+':'+domain, 'generator_version': VERSION,
            'seed': seed, 'difficulty': difficulty, 'difficulty_basis': {'solver_search_bound': solver_work},
            'prompt': prompt, 'data': data, 'previously_observed': True, 'forced_split': 'development'}
    task['task_digest'] = digest(task)
    return task


def solve(task):
    d, domain = task['data'], task['domain']
    if domain == 'math':
        # Independent repeated multiplication, not the generator's exponent expression.
        product = 1
        for _ in range(d['power']):
            product *= d['a']+d['b']
        return product-d['c']
    if domain == 'logic':
        return 'SAT' if any(all(any(bits[abs(v)-1] == (v > 0) for v in clause)
                                   for clause in d['clauses'])
                            for bits in itertools.product((False, True), repeat=d['variables'])) else 'UNSAT'
    if domain == 'algorithms':
        # Exhaustive reference independent of a model or greedy Kahn implementation.
        for order in itertools.permutations(range(d['nodes'])):
            positions = {v: i for i, v in enumerate(order)}
            if all(positions[a] < positions[b] for a, b in d['edges']):
                return list(order)
        return 'IMPOSSIBLE'
    frontier = [(d['initial'], [])]
    for step in range(d['max_steps']+1):
        for value, actions in frontier:
            if value == d['target']:
                return actions
        if step < d['max_steps']:
            frontier = [(v+2 if op == 'add2' else 2*v, actions+[op])
                        for v, actions in frontier for op in d['operations'] if v <= d['target']]
    return 'IMPOSSIBLE'


def verify(task, answer):
    """Strict marker, no eval/exec of model code; planning checked by simulation."""
    try:
        marker = answer.strip().splitlines()[-1]
        if not marker.startswith('ANSWER: '):
            raise ValueError('Missing final answer marker')
        value = marker[len('ANSWER: '):].strip()
        domain = task['domain']
        expected = solve(task)
        if domain == 'math':
            parsed = int(value)
            correct = parsed == expected
        elif domain == 'logic':
            correct = value in ('SAT', 'UNSAT') and value == expected
        elif value == 'IMPOSSIBLE':
            correct = expected == value
        else:
            parsed = json.loads(value)
            if type(parsed) is not list:
                raise ValueError('Expected array')
            if domain == 'algorithms':
                correct = all(type(x) is int for x in parsed) and parsed == expected
            else:
                d = task['data']; position = d['initial']
                for action in parsed:
                    if action not in d['operations']:
                        raise ValueError('Illegal action')
                    position = position+2 if action == 'add2' else position*2
                correct = position == d['target'] and len(parsed) <= d['max_steps']
        return {'verifier_id': VERSION+':'+domain, 'verifier_version': VERSION,
                'verdict': 'correct' if correct else 'incorrect', 'grading_uncertainty': False}
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        return {'verifier_id': VERSION+':'+task.get('domain', 'unknown'), 'verifier_version': VERSION,
                'verdict': 'unparseable', 'grading_uncertainty': True, 'reason': type(exc).__name__}
