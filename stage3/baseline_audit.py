"""Offline diagnostic-difficulty audit. No model and no paid call."""
from collections import Counter, defaultdict

from stage3.generators_v2 import solve as solve_v2
from stage3.generators_v3 import solve as solve_v3


def outcome(task):
    solver = solve_v3 if task.get("generator_version") == "stage3-generators-v3" else solve_v2
    label = solver(task)
    if isinstance(label, list):
        return "ORDER"
    return label


def family_majority_accuracy(tasks):
    grouped = defaultdict(list)
    considered = [task for task in tasks if task["domain"] != "math"]
    for task in considered:
        grouped[(task["domain"], task["family"])].append(outcome(task))
    majorities = {key: Counter(labels).most_common(1)[0][0] for key, labels in grouped.items()}
    hits = sum(outcome(task) == majorities[(task["domain"], task["family"])] for task in considered)
    return hits / len(considered)


def logic_constant_accuracy(tasks, guess):
    logic = [task for task in tasks if task["domain"] == "logic"]
    return sum(outcome(task) == guess for task in logic) / len(logic)


def math_structure(tasks):
    easy_mul = 0
    hard_modulus = 0
    easy_count = hard_count = 0
    for task in tasks:
        if task["domain"] != "math":
            continue
        if task["difficulty"] == "easy":
            easy_count += 1
            steps = task["data"].get("steps") or task["data"].get("left") or []
            if any(step[0] == "mul" for step in steps):
                easy_mul += 1
        if task["difficulty"] == "hard":
            hard_count += 1
            if "modulus" in task["data"] or "offset" in task["data"] or len(task["data"].get("moduli", [])) == 3:
                hard_modulus += 1
    return {"easy_with_multiplication": easy_mul, "easy_count": easy_count,
            "hard_with_extra_structure": hard_modulus, "hard_count": hard_count}


def summarize(tasks):
    return {
        "family_majority_accuracy": family_majority_accuracy(tasks),
        "logic_always_sat": logic_constant_accuracy(tasks, "SAT"),
        "logic_always_unsat": logic_constant_accuracy(tasks, "UNSAT"),
        "math": math_structure(tasks),
    }
