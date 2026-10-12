"""Small fixed technical manifest with deterministic verifiers, not §5.5 pilot."""
import re

TASKS = [
    ('math-1', 'math', 'Find the smallest positive integer x for which x mod 7 = 3 and x mod 5 = 1.', '31'),
    ('math-2', 'math', 'How many integers from 1 to 100 inclusive are divisible by 3 or 5?', '47'),
    ('logic-1', 'logic', 'All A are B. No B are C. Must it follow that no A are C? Answer yes or no.', 'yes'),
    ('logic-2', 'logic', 'Exactly one of P and Q is true. P implies R. R is false. Is Q true? Answer yes or no.', 'yes'),
    ('algorithms-1', 'algorithms', 'An initially empty stack receives push(4), push(7), pop(), push(2), pop(), pop(). What does the last pop return?', '4'),
    ('planning-1', 'planning', 'Tasks A,B,C,D take 2,3,4,1 hours. B and C both require A; D requires both B and C. With unlimited workers what is the earliest completion time in hours?', '7'),
]


def manifest():
    return [{'id': i, 'domain': d, 'prompt': p + '\nEnd with exactly ANSWER: <value>.',
             'expected': a} for i, d, p, a in TASKS]


def verify_answer(task, answer):
    matches = re.findall(r'(?im)^\s*ANSWER:\s*([^\n]+)\s*$', answer)
    if not matches:
        return {'correct': False, 'parsed': None, 'reason': 'required final marker absent'}
    parsed = matches[-1].strip().lower().rstrip('.').strip()
    return {'correct': parsed == task['expected'], 'parsed': parsed}
