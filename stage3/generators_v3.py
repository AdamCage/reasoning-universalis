"""Development supplement whose label is not a function of the family name.

Roster v2 stays unchanged. These tasks are still not a mass pilot.
"""
import random

from measurement.core import digest
from stage3.generators_v2 import _apply_counter, _satisfiable, _topo

VERSION = "stage3-generators-v3"
DOMAINS = ("math", "logic", "algorithms", "planning")
FAMILIES = {
    "math": ("left_fold", "two_tracks", "residues"),
    "logic": ("sparse_cnf", "dense_cnf", "growing_cnf"),
    "algorithms": ("sparse_dag", "dense_dag", "overlapping_dag"),
    "planning": ("budget_grid", "budget_counter", "budget_maze"),
}


def _rng(domain, family, difficulty, seed):
    return random.Random(f"{VERSION}:{domain}:{family}:{difficulty}:{seed}")


def _task(domain, family, difficulty, seed, prompt, data):
    root = f"{VERSION}:{domain}:{family}:{difficulty}:{seed}"
    task = {
        "task_id": root, "root_id": root, "domain": domain, "family": family,
        "generator_id": VERSION + ":" + domain + ":" + family, "generator_version": VERSION,
        "seed": seed, "difficulty": difficulty,
        "difficulty_basis": "structure_changes_with_level_not_a_confirmatory_definition",
        "prompt": prompt, "data": data, "previously_observed": True, "forced_split": "development",
        "exposure": "published_in_stage3_development_v3", "cohort": VERSION,
        "confirmatory_excluded": True, "executed": False,
    }
    task["task_digest"] = digest({key: value for key, value in task.items() if key != "task_digest"})
    return task


def generate(domain, family, difficulty, seed):
    if domain not in DOMAINS or family not in FAMILIES[domain] or difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Unknown stage-3 v3 family")
    if type(seed) is not int or seed < 0:
        raise ValueError("Invalid seed")
    rng = _rng(domain, family, difficulty, seed)
    if domain == "math":
        return _math(family, difficulty, seed, rng)
    if domain == "logic":
        return _logic(family, difficulty, seed, rng)
    if domain == "algorithms":
        return _algorithms(family, difficulty, seed, rng)
    return _planning(family, difficulty, seed, rng)


def _sizes(difficulty):
    return {"easy": 4, "medium": 5, "hard": 6}[difficulty]


def _random_clauses(rng, variables, count):
    clauses = []
    for _ in range(count):
        chosen = rng.sample(range(1, variables + 1), 3)
        clauses.append([rng.choice((-1, 1)) * variable for variable in chosen])
    return clauses


def _clauses_for_label(rng, variables, count, want_sat):
    for nonce in range(500):
        local = random.Random(f"{rng.random()}:{nonce}:{want_sat}:{count}")
        clauses = _random_clauses(local, variables, count)
        if _satisfiable(variables, clauses) == want_sat:
            return clauses
    raise RuntimeError("Could not sample a 3-CNF with the requested label")


def _logic(family, difficulty, seed, rng):
    variables = _sizes(difficulty)
    want_sat = seed % 2 == 0
    base = {"sparse_cnf": 3, "dense_cnf": 4, "growing_cnf": 3}[family]
    count = variables * (base if want_sat else base + 4)
    if family == "growing_cnf" and not want_sat:
        clauses = _clauses_for_label(rng, variables, variables * base, True)
        for extra in range(variables * 6):
            clauses = clauses + _random_clauses(rng, variables, 1)
            if not _satisfiable(variables, clauses):
                break
        else:
            clauses = _clauses_for_label(rng, variables, count, False)
    else:
        clauses = _clauses_for_label(rng, variables, count, want_sat)
    data = {"family": family, "variables": variables, "clauses": clauses}
    prompt = ("Decide SAT or UNSAT for this CNF. Positive integers are variables and negative "
              f"integers are negations: {clauses}. Return ANSWER: SAT or ANSWER: UNSAT.")
    return _task("logic", family, difficulty, seed, prompt, data)


def _permutation(size, seed):
    import math
    index = (seed + 1) % math.factorial(size)
    pool = list(range(size))
    order = []
    for remaining in range(size, 0, -1):
        block = math.factorial(remaining - 1)
        choice, index = divmod(index, block)
        order.append(pool.pop(choice))
    return order


def _algorithms(family, difficulty, seed, rng):
    size = _sizes(difficulty)
    hidden = _permutation(size, seed + {"sparse_dag": 19, "dense_dag": 41, "overlapping_dag": 73}[family])
    probability = {"sparse_dag": 0.35, "dense_dag": 0.55, "overlapping_dag": 0.75}[family]
    if seed % 2 == 1:
        edges = [[hidden[index], hidden[index + 1]] for index in range(size - 1)]
        edges.append([hidden[-1], hidden[0]])
        if family != "sparse_dag":
            edges.append([hidden[0], hidden[min(2, size - 1)]])
        if family == "overlapping_dag":
            edges.append([hidden[min(1, size - 2)], hidden[-1]])
    else:
        edges = []
        for earlier in range(size):
            for later in range(earlier + 1, size):
                if rng.random() < probability:
                    edges.append([hidden[earlier], hidden[later]])
        if not edges:
            edges.append([hidden[0], hidden[min(2, size - 1)]])
    data = {"family": family, "nodes": size, "edges": edges}
    prompt = (f"Return the lexicographically smallest topological order of nodes 0..{size - 1} "
              f"with directed edges {edges}, or ANSWER: IMPOSSIBLE if the graph has a cycle. "
              "Return ANSWER: <JSON array> or ANSWER: IMPOSSIBLE.")
    return _task("algorithms", family, difficulty, seed, prompt, data)


def _fold(start, steps):
    value = start
    for operation, argument in steps:
        if operation == "add":
            value += argument
        elif operation == "sub":
            value -= argument
        elif operation == "mul":
            value *= argument
        else:
            raise ValueError("Unknown arithmetic operation")
    return value


def _math(family, difficulty, seed, rng):
    if family == "residues":
        moduli = {"easy": (5, 7), "medium": (5, 7, 8), "hard": (5, 7)}[difficulty]
        value = seed % (5 * 7 * (8 if difficulty == "medium" else 1))
        residues = [value % modulus for modulus in moduli]
        data = {"family": family, "moduli": list(moduli), "residues": residues,
                "span": 1}
        for modulus in moduli:
            data["span"] *= modulus
        if difficulty == "hard":
            data["offset"] = 2 + (seed % 4)
            prompt = (f"Find x with 0 <= x < {data['span']} such that x ≡ {residues[0]} (mod {moduli[0]}), "
                      f"x ≡ {residues[1]} (mod {moduli[1]}), and then return x + {data['offset']}. "
                      "Return ANSWER: <integer>.")
        else:
            shown = ", ".join(f"x ≡ {residue} (mod {modulus})" for residue, modulus in zip(residues, moduli))
            prompt = (f"Find the integer x with 0 <= x < {data['span']} satisfying {shown}. "
                      "Return ANSWER: <integer>.")
        return _task("math", family, difficulty, seed, prompt, data)
    operators = ("add", "sub") if difficulty == "easy" else ("add", "sub", "mul")
    length = {"easy": 4, "medium": 6, "hard": 8}[difficulty]
    if family == "left_fold":
        start = 2 + (seed % 7)
        steps = []
        for index in range(length):
            operation = operators[index % len(operators)] if difficulty != "easy" else rng.choice(operators)
            if difficulty == "hard" and index == 1:
                operation = "mul"
            steps.append([operation, 2 + ((seed * 3 + index) % 7)])
        data = {"family": family, "start": start, "steps": steps}
        shown = ", ".join(operation + " " + str(argument) for operation, argument in steps)
        if difficulty == "hard":
            data["modulus"] = 7 + (seed % 5)
            prompt = (f"Start with {start}. Apply the operations in order, left to right: {shown}. "
                      f"Return the result modulo {data['modulus']}. Return ANSWER: <integer>.")
        else:
            prompt = (f"Start with {start}. Apply the operations in order, left to right: {shown}. "
                      "Return ANSWER: <integer>.")
        return _task("math", family, difficulty, seed, prompt, data)
    left = [[rng.choice(operators), rng.randint(2, 6)] for _ in range(length // 2)]
    right = [[rng.choice(operators), rng.randint(2, 6)] for _ in range(length // 2)]
    if difficulty != "easy":
        left[0][0] = "mul"
    data = {"family": family, "left_start": 3 + (seed % 4), "right_start": 2 + (seed % 3),
            "left": left, "right": right}
    if difficulty == "hard":
        data["modulus"] = 9 + (seed % 4)
        prompt = (f"Compute (A - B) mod {data['modulus']}. A starts at {data['left_start']} and applies {left}. "
                  f"B starts at {data['right_start']} and applies {right}. Return ANSWER: <integer>.")
    else:
        prompt = (f"Compute A - B. A starts at {data['left_start']} and applies {left}. "
                  f"B starts at {data['right_start']} and applies {right}. Return ANSWER: <integer>.")
    return _task("math", family, difficulty, seed, prompt, data)


def _shortest_grid(data):
    start = tuple(data["start"])
    goal = tuple(data["goal"])
    blocked = {tuple(item) for item in data["obstacles"]}
    width, height = data["width"], data["height"]
    queue = [(start, 0)]
    seen = {start}
    while queue:
        cell, steps = queue.pop(0)
        if cell == goal:
            return steps
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cell[0] + dx, cell[1] + dy)
            if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in blocked and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, steps + 1))
    return None


def _planning(family, difficulty, seed, rng):
    solvable = seed % 2 == 0
    if family == "budget_counter":
        start = (seed + {"easy": 0, "medium": 4, "hard": 8}[difficulty]) % 11
        operations = ["add2", "sub1", "double"]
        limit = {"easy": 3, "medium": 5, "hard": 7}[difficulty]
        value = start
        seen = {start}
        for _ in range(limit):
            operation = rng.choice(operations)
            nxt = _apply_counter(value, operation)
            if not 0 <= nxt <= 25 or nxt in seen:
                continue
            value = nxt
            seen.add(value)
        target = value
        distance = _counter_distance(start, target, operations, limit)
        if distance is None:
            target = start + 2
            distance = _counter_distance(start, target, operations, limit)
        max_steps = distance if solvable else max(0, distance - 1)
        data = {"family": family, "start": start, "target": target, "max_steps": max_steps,
                "operations": operations}
        prompt = (f"Start at {start} and reach {target}. Operations are add2, sub1, and double. "
                  f"Values must stay between 0 and 25. Use at most {max_steps} operations. "
                  "Return ANSWER: <JSON array of operations> or ANSWER: IMPOSSIBLE.")
        return _task("planning", family, difficulty, seed, prompt, data)
    width = {"easy": 4, "medium": 5, "hard": 6}[difficulty]
    height = {"easy": 3, "medium": 4, "hard": 4}[difficulty]
    obstacle_count = {"budget_grid": 1, "budget_maze": 3}[family] + (1 if difficulty == "hard" else 0)
    obstacles = []
    cells = [(x, y) for x in range(width) for y in range(height) if (x, y) not in ((0, 0), (width - 1, height - 1))]
    rng.shuffle(cells)
    for cell in cells:
        if len(obstacles) == obstacle_count:
            break
        trial = obstacles + [list(cell)]
        probe = {"width": width, "height": height, "start": [0, 0], "goal": [width - 1, height - 1],
                 "obstacles": trial}
        if _shortest_grid(probe) is not None:
            obstacles = trial
    data = {"family": family, "width": width, "height": height, "start": [0, 0],
            "goal": [width - 1, height - 1], "obstacles": obstacles, "max_steps": 0}
    shortest = _shortest_grid(data)
    data["max_steps"] = shortest if solvable else max(0, shortest - 1)
    prompt = (f"Grid width {width}, height {height}. Start at [0, 0] and reach {data['goal']}. "
              f"Obstacles are {obstacles}. Moves are N, E, S, W by one cell. "
              f"Use at most {data['max_steps']} moves and stay inside the grid. "
              "Return ANSWER: <JSON array of moves> or ANSWER: IMPOSSIBLE.")
    return _task("planning", family, difficulty, seed, prompt, data)


def solve(task):
    data = task["data"]
    family = task["family"]
    if task["domain"] == "logic":
        return "SAT" if _satisfiable(data["variables"], data["clauses"]) else "UNSAT"
    if task["domain"] == "algorithms":
        order = _topo(data["nodes"], data["edges"])
        return "IMPOSSIBLE" if order is None else order
    if family == "residues":
        moduli, residues = data["moduli"], data["residues"]
        found = next(value for value in range(data["span"])
                     if all(value % modulus == residue for modulus, residue in zip(moduli, residues)))
        return found + data["offset"] if "offset" in data else found
    if family == "left_fold":
        value = _fold(data["start"], data["steps"])
        return value % data["modulus"] if "modulus" in data else value
    if family == "two_tracks":
        value = _fold(data["left_start"], data["left"]) - _fold(data["right_start"], data["right"])
        return value % data["modulus"] if "modulus" in data else value
    if family == "budget_counter":
        return "SOLVABLE" if _counter_reaches(data) else "IMPOSSIBLE"
    return "SOLVABLE" if _grid_reaches(data) else "IMPOSSIBLE"


def _counter_distance(start, target, operations, limit):
    seen = {(start, 0)}
    queue = [(start, 0)]
    while queue:
        value, steps = queue.pop(0)
        if value == target:
            return steps
        if steps == limit:
            continue
        for operation in operations:
            nxt = _apply_counter(value, operation)
            state = (nxt, steps + 1)
            if 0 <= nxt <= 25 and state not in seen:
                seen.add(state)
                queue.append(state)
    return None


def _counter_reaches(data):
    seen = {(data["start"], 0)}
    queue = [(data["start"], 0)]
    while queue:
        value, steps = queue.pop(0)
        if value == data["target"]:
            return True
        if steps == data["max_steps"]:
            continue
        for operation in data["operations"]:
            nxt = _apply_counter(value, operation)
            state = (nxt, steps + 1)
            if 0 <= nxt <= 25 and state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def _grid_reaches(data):
    if data["max_steps"] < 0:
        return False
    start = tuple(data["start"])
    goal = tuple(data["goal"])
    blocked = {tuple(item) for item in data["obstacles"]}
    width, height = data["width"], data["height"]
    queue = [(start, 0)]
    seen = {(start, 0)}
    while queue:
        cell, steps = queue.pop(0)
        if cell == goal:
            return True
        if steps == data["max_steps"]:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cell[0] + dx, cell[1] + dy)
            state = (nxt, steps + 1)
            if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in blocked and state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def _answer_line(text):
    marker = text.strip().splitlines()[-1]
    if not marker.startswith("ANSWER: "):
        raise ValueError("Missing final answer marker")
    return marker[len("ANSWER: "):].strip()


def verify(task, answer):
    try:
        value = _answer_line(answer)
        expected = solve(task)
        if task["domain"] == "math":
            correct = int(value) == expected
        elif task["domain"] == "logic":
            correct = value == expected
        elif task["domain"] == "algorithms":
            if value == "IMPOSSIBLE":
                correct = expected == "IMPOSSIBLE"
            else:
                import json
                correct = json.loads(value) == expected
        elif value == "IMPOSSIBLE":
            correct = expected == "IMPOSSIBLE"
        else:
            import json
            correct = expected == "SOLVABLE" and _submitted_plan_works(task, json.loads(value))
        return {"verifier_id": VERSION + ":" + task["family"], "verifier_version": VERSION,
                "verdict": "correct" if correct else "incorrect", "grading_uncertainty": False}
    except (ValueError, TypeError, KeyError, IndexError):
        return {"verifier_id": VERSION, "verifier_version": VERSION, "verdict": "unparseable",
                "grading_uncertainty": True}


def _submitted_plan_works(task, actions):
    data = task["data"]
    if len(actions) > data["max_steps"]:
        return False
    if task["family"] == "budget_counter":
        value = data["start"]
        for action in actions:
            if action not in data["operations"]:
                return False
            value = _apply_counter(value, action)
            if not 0 <= value <= 25:
                return False
        return value == data["target"]
    cell = tuple(data["start"])
    blocked = {tuple(item) for item in data["obstacles"]}
    moves = {"E": (1, 0), "W": (-1, 0), "S": (0, 1), "N": (0, -1)}
    for action in actions:
        if action not in moves:
            return False
        dx, dy = moves[action]
        cell = (cell[0] + dx, cell[1] + dy)
        if not (0 <= cell[0] < data["width"] and 0 <= cell[1] < data["height"]) or cell in blocked:
            return False
    return list(cell) == data["goal"]
