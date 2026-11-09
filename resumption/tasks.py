"""Deterministic, independently checked development corpus for local resumption.

No model calls. A root contains two independently sampled instances from the
same stratum; the pair is kept together in every split. Feasibility is balanced
for search problems, and is not confused with model answer correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from resumption.generator_audit import canonical_instance_key, solve_reference
from stage3.generators_v2 import _satisfiable, _topo
from stage3.generators_v4 import _grid_reaches


VERSION = "resumption-generators-v1"
DOMAINS = ("math", "logic", "algorithms", "planning")
DIFFICULTIES = ("easy", "medium", "hard")
FAMILIES = {
    "math": ("fixed_tracks", "fixed_residues"),
    "logic": ("two_cnf", "three_cnf"),
    "algorithms": ("local_graph", "global_graph"),
    "planning": ("rectangular_grid", "square_grid"),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _make(domain, family, difficulty, pair, member, namespace):
    identity = f"{VERSION}:{namespace}:{domain}:{family}:{difficulty}:{pair}:{member}"
    rng = random.Random(identity)
    level = DIFFICULTIES.index(difficulty)
    # Randomized within-pair orientation; neither parity nor member is sent.
    positive_first = int(sha({"orientation": identity.rsplit(":", 1)[0]})[:8], 16) % 2 == 0
    want_positive = positive_first == (member == 0)
    data = {"family": family}
    if domain == "math":
        if family == "fixed_residues":
            moduli = ((5, 7), (7, 11), (7, 11, 13))[level]
            span = 1
            for modulus in moduli:
                span *= modulus
            value = rng.randrange(span)
            data.update(moduli=list(moduli), residues=[value % m for m in moduli], span=span)
            congruences = ", ".join(f"x ≡ {r} (mod {m})" for r, m in zip(data["residues"], moduli))
            prompt = f"Find the unique integer x with 0 <= x < {span} satisfying {congruences}."
        else:
            size = (4, 7, 10)[level]
            operators = ("add", "sub", "mul")
            data.update(left_start=rng.randrange(11, 100), right_start=rng.randrange(11, 100),
                        left=[[rng.choice(operators), rng.randrange(2, 15)] for _ in range(size)],
                        right=[[rng.choice(operators), rng.randrange(2, 15)] for _ in range(size)])
            prompt = (f"Compute A - B using exact integer arithmetic. A starts at {data['left_start']} "
                      f"and applies {data['left']}. B starts at {data['right_start']} and applies "
                      f"{data['right']}. Apply each track's operations in order, left to right.")
        prompt += " Put the integer result on the final line: ANSWER: <integer>."
    elif domain == "logic":
        n = (5, 6, 8)[level]
        width = 2 if family == "two_cnf" else 3
        count = ((7, 10, 14) if width == 2 else (20, 27, 36))[level]
        for _ in range(10000):
            clauses = [[v * rng.choice((-1, 1)) for v in rng.sample(range(1, n + 1), width)]
                       for _ in range(count)]
            if _satisfiable(n, clauses) == want_positive:
                break
        else:
            raise RuntimeError("CNF rejection bound exhausted")
        data.update(variables=n, clauses=clauses)
        prompt = (f"Decide satisfiability of this CNF over variables 1..{n}. Each inner list is a "
                  f"disjunction, outer list a conjunction, and negative integers are negations: {clauses}. "
                  "Put the result on the final line: ANSWER: SAT or ANSWER: UNSAT.")
    elif domain == "algorithms":
        n, count = ((5, 6), (6, 8), (8, 12))[level]
        for _ in range(10000):
            labels = rng.sample(range(n), n)
            candidates = [(labels[a], labels[b]) for a in range(n) for b in range(n)
                          if a != b and (family == "global_graph" or abs(a - b) <= 2)]
            edges = [list(edge) for edge in rng.sample(candidates, count)]
            if (_topo(n, edges) is not None) == want_positive:
                break
        else:
            raise RuntimeError("Graph rejection bound exhausted")
        data.update(nodes=n, edges=edges)
        prompt = (f"Return the lexicographically smallest topological order of all nodes 0..{n - 1} "
                  f"for directed edges {edges}. If a cycle prevents ordering, return IMPOSSIBLE. "
                  "Put the result on the final line: ANSWER: <JSON array> or ANSWER: IMPOSSIBLE.")
    else:
        width = (4, 5, 6)[level]
        height = width if family == "square_grid" else width - 1
        count = (4, 7, 10)[level]
        limit = width + height + (0, 0, 2)[level]
        cells = [(x, y) for x in range(width) for y in range(height)
                 if (x, y) not in ((0, 0), (width - 1, height - 1))]
        for _ in range(10000):
            data.update(width=width, height=height, start=[0, 0], goal=[width - 1, height - 1],
                        obstacles=[list(cell) for cell in rng.sample(cells, count)], max_steps=limit)
            if _grid_reaches(data) == want_positive:
                break
        else:
            raise RuntimeError("Grid rejection bound exhausted")
        prompt = (f"Grid width {width}, height {height}, coordinates x=0..{width-1}, y=0..{height-1}. "
                  f"Start at [0, 0], reach {data['goal']}, avoid obstacles {data['obstacles']}. "
                  f"Use at most {limit} moves. N=(0,-1), E=(1,0), S=(0,1), W=(-1,0). "
                  "Stay inside the grid. Put a valid move sequence, or IMPOSSIBLE if none exists, "
                  "on the final line: ANSWER: <JSON array of moves> or ANSWER: IMPOSSIBLE.")
    prompt = "Solve the problem carefully. Give your final answer in the requested format.\n\n" + prompt
    task = {"task_id": identity, "root_id": identity.rsplit(":", 1)[0], "domain": domain,
            "family": family, "difficulty": difficulty, "generator_version": VERSION,
            "generator_id": VERSION + ":" + domain + ":" + family,
            "seed": int(sha({"identity": identity})[:8], 16), "prompt": prompt, "data": data,
            "confirmatory_excluded": True, "exposure": "local_resumption_development",
            "split": "development", "forced_split": "development"}
    answer = solve_reference(task)
    if domain != "math" and ((answer != "IMPOSSIBLE" and answer != "UNSAT") != want_positive):
        raise ValueError("Independent reference disagrees with generator feasibility")
    task["instance_sha256"] = canonical_instance_key(task)
    return task


def build():
    tasks = [_make(domain, family, difficulty, pair, member, "primary")
             for domain in DOMAINS for difficulty in DIFFICULTIES for family in FAMILIES[domain]
             for pair in range(2) for member in range(2)]
    # 48 paired roots, assigned without observing any model response. Splits are
    # blocked by domain; difficulty/family are diagnostics, not independent OOD families.
    for domain in DOMAINS:
        roots = sorted({task["root_id"] for task in tasks if task["domain"] == domain},
                       key=lambda root: sha({"split": root, "salt": "ru-resumption-split-v1"}))
        assignments = {root: ("train" if index < 6 else "validation" if index < 8 else "test")
                       for index, root in enumerate(roots)}
        for task in tasks:
            if task["domain"] == domain:
                task["split"] = assignments[task["root_id"]]
    admissions = [_make(domain, FAMILIES[domain][0], "hard", 99, 0, "admission") for domain in DOMAINS]
    for task in tasks + admissions:
        task["task_digest"] = sha(task)
    if len({task["prompt"] for task in tasks + admissions}) != len(tasks + admissions):
        raise ValueError("Duplicate prompt in new corpus")
    if len({task["instance_sha256"] for task in tasks + admissions}) != len(tasks + admissions):
        raise ValueError("Duplicate exact normalized instance in new corpus")
    document = {"schema_version": 1, "protocol_id": "ru-local-resumption-2026-11-08-v1",
                "generator_version": VERSION, "status": "unexecuted_development_plan",
                "confirmatory_excluded": True, "E0": "not_passed", "tasks": tasks,
                "admission_tasks": admissions,
                "counts": {"tasks": len(tasks), "roots": len({t['root_id'] for t in tasks}),
                           "by_split": dict(Counter(t['split'] for t in tasks)),
                           "by_domain": dict(Counter(t['domain'] for t in tasks))},
                "limitations": ["Labels are feasibility-balanced only for search domains; correctness is observed later.",
                                "Named families are generator variants, not certified independent task families.",
                                "Difficulty is an input size schedule, not calibrated human or model difficulty.",
                                "Canonical keys remove exact duplicates, not all isomorphic or algebraically equivalent tasks.",
                                "Root pairs, repetitions and models must remain grouped in uncertainty estimates."]}
    document["corpus_sha256"] = sha(document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/resumption-2026-11-08/tasks.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build()
    data = canonical(document) + b"\n"
    if args.check:
        if args.output.read_bytes() != data:
            raise SystemExit("Task corpus differs from its deterministic builder")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists() and args.output.read_bytes() != data:
            raise SystemExit("Refusing to overwrite an existing different task corpus")
        args.output.write_bytes(data)
    print(json.dumps({"path": str(args.output), "counts": document["counts"],
                      "corpus_sha256": document["corpus_sha256"], "paid_calls": 0}))


if __name__ == "__main__":
    main()
