"""Development supplement v4. Surface features do not encode the label.

Rosters v1, v2 and v3 stay published. The label is a property of the instance,
not of family, seed parity, or a count that differs by class.
"""
import hashlib
import random

from measurement.core import digest
from stage3.generators_v2 import _apply_counter, _satisfiable, _topo

VERSION = "stage3-generators-v4"
DOMAINS = ("math", "logic", "algorithms", "planning")
FAMILIES = {
    "math": ("fixed_fold", "fixed_tracks", "fixed_residues"),
    "logic": ("cnf_a", "cnf_b", "cnf_c"),
    "algorithms": ("graph_a", "graph_b", "graph_c"),
    "planning": ("grid_a", "grid_b", "grid_c"),
}
LOGIC_CLAUSES = {"easy": 18, "medium": 22, "hard": 28}
LOGIC_VARIABLES = {"easy": 4, "medium": 5, "hard": 6}
GRAPH_EDGES = {"easy": 6, "medium": 8, "hard": 10}
GRAPH_NODES = {"easy": 5, "medium": 6, "hard": 7}


def _target(family, difficulty, seed):
    pair = seed // 2
    bit = seed % 2
    digest_hex = hashlib.sha256(f"{VERSION}:{family}:{difficulty}:{pair}".encode()).hexdigest()
    first_is_positive = int(digest_hex[0], 16) % 2 == 0
    return first_is_positive == (bit == 0)


def _rng(domain, family, difficulty, seed, nonce):
    return random.Random(f"{VERSION}:{domain}:{family}:{difficulty}:{seed}:{nonce}")


def _task(domain, family, difficulty, seed, prompt, data):
    root = f"{VERSION}:{domain}:{family}:{difficulty}:{seed}"
    task = {
        "task_id": root, "root_id": root, "domain": domain, "family": family,
        "generator_id": VERSION + ":" + domain + ":" + family, "generator_version": VERSION,
        "seed": seed, "difficulty": difficulty,
        "difficulty_basis": "size_schedule_not_a_confirmatory_definition",
        "prompt": prompt, "data": data, "previously_observed": True, "forced_split": "development",
        "exposure": "published_in_stage3_development_v4", "cohort": VERSION,
        "confirmatory_excluded": True, "executed": False,
    }
    task["task_digest"] = digest({key: value for key, value in task.items() if key != "task_digest"})
    return task


def generate(domain, family, difficulty, seed):
    if domain not in DOMAINS or family not in FAMILIES[domain] or difficulty not in LOGIC_CLAUSES:
        raise ValueError("Unknown stage-3 v4 family")
    if type(seed) is not int or seed < 0:
        raise ValueError("Invalid seed")
    if domain == "math":
        return _math(family, difficulty, seed)
    if domain == "logic":
        return _logic(family, difficulty, seed)
    if domain == "algorithms":
        return _algorithms(family, difficulty, seed)
    return _planning(family, difficulty, seed)


def _logic(family, difficulty, seed):
    variables = LOGIC_VARIABLES[difficulty]
    count = LOGIC_CLAUSES[difficulty]
    want_sat = _target(family, difficulty, seed)
    for nonce in range(800):
        rng = _rng("logic", family, difficulty, seed, nonce)
        clauses = []
        for _ in range(count):
            chosen = rng.sample(range(1, variables + 1), 3)
            clauses.append([rng.choice((-1, 1)) * variable for variable in chosen])
        if _satisfiable(variables, clauses) == want_sat:
            data = {"family": family, "variables": variables, "clauses": clauses}
            prompt = ("Development item v4. Decide SAT or UNSAT for this CNF. Positive integers are variables and negative "
                      f"integers are negations: {clauses}. Return ANSWER: SAT or ANSWER: UNSAT.")
            return _task("logic", family, difficulty, seed, prompt, data)
    raise RuntimeError("3-CNF label search failed")


def _algorithms(family, difficulty, seed):
    nodes = GRAPH_NODES[difficulty]
    count = GRAPH_EDGES[difficulty]
    want_cycle = not _target(family, difficulty, seed)
    for nonce in range(800):
        rng = _rng("algorithms", family, difficulty, seed, nonce)
        edges = []
        while len(edges) < count:
            source, target = rng.sample(range(nodes), 2)
            edge = [source, target]
            if edge not in edges:
                edges.append(edge)
        cyclic = _topo(nodes, edges) is None
        if cyclic == want_cycle:
            data = {"family": family, "nodes": nodes, "edges": edges}
            prompt = (f"Development item v4. Return the lexicographically smallest topological order of nodes 0..{nodes - 1} "
                      f"with directed edges {edges}, or ANSWER: IMPOSSIBLE if the graph has a cycle. "
                      "Return ANSWER: <JSON array> or ANSWER: IMPOSSIBLE.")
            return _task("algorithms", family, difficulty, seed, prompt, data)
    raise RuntimeError("Graph label search failed")


def _math(family, difficulty, seed):
    rng = _rng("math", family, difficulty, seed, 0)
    if family == "fixed_residues":
        moduli = (5, 7, 9) if difficulty == "hard" else (5, 7)
        value = 1 + seed
        residues = [value % modulus for modulus in moduli]
        span = 1
        for modulus in moduli:
            span *= modulus
        data = {"family": family, "moduli": list(moduli), "residues": residues, "span": span}
        shown = ", ".join(f"x ≡ {residue} (mod {modulus})" for residue, modulus in zip(residues, moduli))
        prompt = f"Development item v4. Find the integer x with 0 <= x < {span} satisfying {shown}. Return ANSWER: <integer>."
        return _task("math", family, difficulty, seed, prompt, data)
    operators = ("add", "sub") if difficulty == "easy" else ("add", "sub", "mul")
    length = {"easy": 4, "medium": 6, "hard": 8}[difficulty]
    if family == "fixed_fold":
        start = 2 + (seed % 7)
        steps = [[operators[index % len(operators)], 2 + ((seed * 3 + index) % 7)] for index in range(length)]
        if difficulty == "hard":
            steps[1][0] = "mul"
        data = {"family": family, "start": start, "steps": steps}
        shown = ", ".join(operation + " " + str(argument) for operation, argument in steps)
        prompt = (f"Development item v4. Start with {start}. Apply the operations in order, left to right: {shown}. "
                  "Return ANSWER: <integer>.")
        return _task("math", family, difficulty, seed, prompt, data)
    left = [[operators[index % len(operators)], rng.randint(2, 6)] for index in range(length // 2)]
    right = [[operators[(index + 1) % len(operators)], rng.randint(2, 6)] for index in range(length // 2)]
    if difficulty == "hard":
        left[0][0] = "mul"
    data = {"family": family, "left_start": 3 + (seed % 4), "right_start": 2 + (seed % 3), "left": left, "right": right}
    prompt = (f"Development item v4. Compute A - B. A starts at {data['left_start']} and applies {left}. "
              f"B starts at {data['right_start']} and applies {right}. Return ANSWER: <integer>.")
    return _task("math", family, difficulty, seed, prompt, data)


def _planning(family, difficulty, seed):
    want_solvable = _target(family, difficulty, seed)
    width = {"easy": 4, "medium": 5, "hard": 5}[difficulty]
    height = {"easy": 3, "medium": 4, "hard": 4}[difficulty]
    limit = {"easy": 8, "medium": 8, "hard": 10}[difficulty]
    obstacle_count = {"easy": 4, "medium": 6, "hard": 7}[difficulty]
    for nonce in range(400):
        rng = _rng("planning", family, difficulty, seed, nonce)
        cells = [(x, y) for x in range(width) for y in range(height) if (x, y) not in ((0, 0), (width - 1, height - 1))]
        rng.shuffle(cells)
        obstacles = [list(cell) for cell in cells[:obstacle_count]]
        data = {"family": family, "width": width, "height": height, "start": [0, 0],
                "goal": [width - 1, height - 1], "obstacles": obstacles, "max_steps": limit}
        reachable = _grid_reaches(data)
        if reachable == want_solvable:
            prompt = (f"Development item v4. Grid width {width}, height {height}. Start at [0, 0] and reach {data['goal']}. "
                      f"Obstacles are {obstacles}. Moves are N, E, S, W by one cell. "
                      f"Use at most {limit} moves and stay inside the grid. "
                      "Return ANSWER: <JSON array of moves> or ANSWER: IMPOSSIBLE.")
            return _task("planning", family, difficulty, seed, prompt, data)
    raise RuntimeError("Grid label search failed")


def _counter_reaches(start, target, operations, limit):
    seen = {(start, 0)}
    queue = [(start, 0)]
    while queue:
        value, steps = queue.pop(0)
        if value == target:
            return True
        if steps == limit:
            continue
        for operation in operations:
            nxt = _apply_counter(value, operation)
            state = (nxt, steps + 1)
            if 0 <= nxt <= 25 and state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def _grid_reaches(data):
    start = tuple(data["start"])
    goal = tuple(data["goal"])
    blocked = {tuple(item) for item in data["obstacles"]}
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
            if 0 <= nxt[0] < data["width"] and 0 <= nxt[1] < data["height"] and nxt not in blocked and state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def solve(task):
    data = task["data"]
    family = task["family"]
    if task["domain"] == "logic":
        return "SAT" if _satisfiable(data["variables"], data["clauses"]) else "UNSAT"
    if task["domain"] == "algorithms":
        order = _topo(data["nodes"], data["edges"])
        return "IMPOSSIBLE" if order is None else order
    if family == "fixed_residues":
        return next(value for value in range(data["span"])
                    if all(value % modulus == residue for modulus, residue in zip(data["moduli"], data["residues"])))
    if family == "fixed_fold":
        value = data["start"]
        for operation, argument in data["steps"]:
            value = value + argument if operation == "add" else value - argument if operation == "sub" else value * argument
        return value
    if family == "fixed_tracks":
        def fold(start, steps):
            value = start
            for operation, argument in steps:
                value = value + argument if operation == "add" else value - argument if operation == "sub" else value * argument
            return value
        return fold(data["left_start"], data["left"]) - fold(data["right_start"], data["right"])
    if family == "counter_a":
        return "SOLVABLE" if _counter_reaches(data["start"], data["target"], data["operations"], data["max_steps"]) else "IMPOSSIBLE"
    return "SOLVABLE" if _grid_reaches(data) else "IMPOSSIBLE"
