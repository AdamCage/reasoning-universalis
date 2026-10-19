"""Offline diagnostic-difficulty audit. No model and no paid call."""
from collections import Counter, defaultdict

from stage3.generators_v2 import solve as solve_v2
from stage3.generators_v3 import solve as solve_v3


def outcome(task):
    version = task.get("generator_version")
    if version == "stage3-generators-v4":
        from stage3.generators_v4 import solve as solve_v4
        label = solve_v4(task)
    elif version == "stage3-generators-v3":
        label = solve_v3(task)
    else:
        label = solve_v2(task)
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


def _seed(task):
    return int(str(task["task_id"]).rsplit(":", 1)[-1])


def _majority_map(pairs):
    grouped = defaultdict(list)
    for key, label in pairs:
        grouped[key].append(label)
    majority = {key: Counter(labels).most_common(1)[0][0] for key, labels in grouped.items()}
    hits = sum(label == majority[key] for key, label in pairs)
    return hits / len(pairs)


def _per_domain(tasks, feature):
    scores = []
    for domain in sorted({task["domain"] for task in tasks if task["domain"] != "math"}):
        subset = [task for task in tasks if task["domain"] == domain]
        scores.append(_majority_map([(feature(task), outcome(task)) for task in subset]))
    return max(scores) if scores else 0


def seed_parity_accuracy(tasks):
    return _per_domain(tasks, lambda task: _seed(task) % 2)


def _threshold_accuracy(values, labels):
    if len(set(values)) <= 1:
        majority = Counter(labels).most_common(1)[0][1] / len(labels)
        return majority
    best = 0
    for split in sorted(set(values))[:-1]:
        for positive in (True, False):
            predicted = [labels[index] for index, value in enumerate(values) if (value <= split) == positive]
            if not predicted:
                continue
            guess = Counter(predicted).most_common(1)[0][0]
            other = Counter(label for index, label in enumerate(labels) if (values[index] <= split) != positive)
            other_guess = other.most_common(1)[0][0] if other else guess
            hits = sum((label == guess) if (value <= split) == positive else (label == other_guess)
                       for value, label in zip(values, labels))
            best = max(best, hits / len(labels))
    return best


def _domain_threshold(tasks, value_of):
    scores = []
    for domain in sorted({task["domain"] for task in tasks if task["domain"] != "math"}):
        subset = [task for task in tasks if task["domain"] == domain]
        scores.append(_threshold_accuracy([value_of(task) for task in subset], [outcome(task) for task in subset]))
    return max(scores) if scores else 0


def length_accuracy(tasks):
    return _domain_threshold(tasks, lambda task: len(task["prompt"]))


def structure_count_accuracy(tasks):
    def value_of(task):
        data = task["data"]
        if "clauses" in data:
            return len(data["clauses"])
        if "edges" in data:
            return len(data["edges"])
        return int(data.get("max_steps", 0))
    return _domain_threshold(tasks, value_of)


def surface_audit(tasks):
    summary = summarize(tasks)
    summary["seed_parity_accuracy"] = seed_parity_accuracy(tasks)
    summary["prompt_length_accuracy"] = length_accuracy(tasks)
    summary["structure_count_accuracy"] = structure_count_accuracy(tasks)
    return summary


def summarize(tasks):
    return {
        "family_majority_accuracy": family_majority_accuracy(tasks),
        "logic_always_sat": logic_constant_accuracy(tasks, "SAT"),
        "logic_always_unsat": logic_constant_accuracy(tasks, "UNSAT"),
        "math": math_structure(tasks),
    }
