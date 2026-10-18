"""Stage 3 task families. Stage 2 generators stay untouched and development-only.

Each seed is its own structural root. Verifiers recompute from the published
problem data and do not read a planted answer. No model is called.
"""
import heapq
import math
import random

from measurement.core import digest

VERSION = "stage3-generators-v2"
DOMAINS = ("math", "logic", "algorithms", "planning")
FAMILIES = {
    "math": ("operation_chain", "two_moduli", "nested_difference"),
    "logic": ("planted_sat", "unit_contradiction", "implication_cycle"),
    "algorithms": ("forced_chain", "forward_dag", "back_edge"),
    "planning": ("open_grid", "blocked_column", "counter_walk"),
}
SIZES = {"easy": 4, "medium": 5, "hard": 6}


def _rng(domain, family, difficulty, seed):
    return random.Random(f"{VERSION}:{domain}:{family}:{difficulty}:{seed}")


def _task(domain, family, difficulty, seed, prompt, data):
    root = f"{VERSION}:{domain}:{family}:{difficulty}:{seed}"
    task = {
        "task_id": root,
        "root_id": root,
        "domain": domain,
        "family": family,
        "generator_id": VERSION + ":" + domain + ":" + family,
        "generator_version": VERSION,
        "seed": seed,
        "difficulty": difficulty,
        "difficulty_basis": "structural_size_not_a_confirmatory_definition",
        "prompt": prompt,
        "data": data,
        "previously_observed": True,
        "forced_split": "development",
        "exposure": "published_in_stage3_roster_v2",
        "cohort": VERSION,
        "confirmatory_excluded": True,
        "executed": False,
    }
    task["task_digest"] = digest({key: value for key, value in task.items() if key != "task_digest"})
    return task


def _answer_line(text):
    marker = text.strip().splitlines()[-1]
    if not marker.startswith("ANSWER: "):
        raise ValueError("Missing final answer marker")
    return marker[len("ANSWER: "):].strip()


def generate(domain, family, difficulty, seed):
    if domain not in DOMAINS or family not in FAMILIES[domain] or difficulty not in SIZES:
        raise ValueError("Unknown stage-3 task family")
    if type(seed) is not int or seed < 0:
        raise ValueError("Invalid seed")
    rng = _rng(domain, family, difficulty, seed)
    size = SIZES[difficulty]
    if domain == "math":
        return _math(family, difficulty, seed, rng, size)
    if domain == "logic":
        return _logic(family, difficulty, seed, rng, size)
    if domain == "algorithms":
        return _algorithms(family, difficulty, seed, rng, size)
    return _planning(family, difficulty, seed, rng, size)


def _math(family, difficulty, seed, rng, size):
    if family == "operation_chain":
        start = rng.randint(2, 8)
        steps = []
        for _ in range(size):
            steps.append([rng.choice(("add", "sub", "mul")), rng.randint(2, 8)])
        shown = ", ".join(op + " " + str(arg) for op, arg in steps)
        prompt = (f"Start with {start}. Apply the operations in order, left to right: {shown}. "
                  "Return ANSWER: <integer>.")
        data = {"family": family, "start": start, "steps": steps}
    elif family == "two_moduli":
        pairs = ((5, 7), (5, 8), (5, 9), (7, 8), (7, 9), (8, 9))
        modulus_a, modulus_b = pairs[seed % len(pairs)]
        span = modulus_a * modulus_b
        value = seed % span
        data = {"family": family, "modulus_a": modulus_a, "modulus_b": modulus_b,
                "residue_a": value % modulus_a, "residue_b": value % modulus_b, "span": span}
        prompt = (f"Find the integer x with 0 <= x < {span}, x ≡ {data['residue_a']} (mod {modulus_a}) "
                  f"and x ≡ {data['residue_b']} (mod {modulus_b}). Return ANSWER: <integer>.")
    else:
        coefficients = [rng.randint(2, 8) for _ in range(6)]
        names = ("a", "b", "c", "d", "e", "f")
        data = {"family": family, "coefficients": dict(zip(names, coefficients))}
        a, b, c, d, e, f = coefficients
        prompt = (f"Compute (a+b)*c - (d+e)*f for a={a}, b={b}, c={c}, d={d}, e={e}, f={f}. "
                  "Return ANSWER: <integer>.")
    return _task("math", family, difficulty, seed, prompt, data)


def _logic(family, difficulty, seed, rng, size):
    if family == "planted_sat":
        assignment = [rng.randrange(2) for _ in range(size)]
        clauses = []
        for _ in range(size + 3):
            indexes = [rng.randrange(size) for _ in range(3)]
            forced = rng.randrange(3)
            clause = []
            for position, index in enumerate(indexes):
                sign = 1 if assignment[index] else -1
                if position != forced:
                    sign = rng.choice((-1, 1))
                clause.append(sign * (index + 1))
            clauses.append(clause)
    elif family == "unit_contradiction":
        clauses = [[1], [-1]]
        for _ in range(size):
            clauses.append([rng.choice((-1, 1)) * rng.randint(1, size) for _ in range(3)])
    else:
        pivot = 1 + (seed % size)
        clauses = [[pivot]]
        order = [(pivot - 1 + offset) % size + 1 for offset in range(size)]
        for left, right in zip(order, order[1:]):
            clauses.append([-left, right])
        clauses.append([-order[-1], -pivot])
        for bit in range(5):
            sign = 1 if (seed >> bit) & 1 else -1
            clauses.append([sign * (size + 1 + bit)])
        size += 5
    data = {"family": family, "variables": size, "clauses": clauses}
    prompt = ("Decide SAT or UNSAT for this CNF. Positive integers are variables and negative "
              f"integers are negations: {clauses}. Return ANSWER: SAT or ANSWER: UNSAT.")
    return _task("logic", family, difficulty, seed, prompt, data)


def _permutation(rng, size, seed):
    del rng
    index = (seed + 1) % math.factorial(size)
    pool = list(range(size))
    order = []
    for remaining in range(size, 0, -1):
        block = math.factorial(remaining - 1)
        choice, index = divmod(index, block)
        order.append(pool.pop(choice))
    if order == list(range(size)):
        order[0], order[1] = order[1], order[0]
    return order


def _chain(order):
    return [[order[index], order[index + 1]] for index in range(len(order) - 1)]


def _algorithms(family, difficulty, seed, rng, size):
    order = _permutation(rng, size, seed)
    edges = _chain(order)
    if family == "forward_dag":
        for index in range(size - 2):
            if rng.random() < 0.7:
                edges.append([order[index], order[index + 2]])
    elif family == "back_edge":
        edges.append([order[-1], order[0]])
    data = {"family": family, "nodes": size, "edges": edges}
    prompt = (f"Return the lexicographically smallest topological order of nodes 0..{size - 1} "
              f"with directed edges {edges}, or ANSWER: IMPOSSIBLE if the graph has a cycle. "
              "Return ANSWER: <JSON array> or ANSWER: IMPOSSIBLE.")
    return _task("algorithms", family, difficulty, seed, prompt, data)


def _planning(family, difficulty, seed, rng, size):
    if family == "counter_walk":
        start = seed % 5
        value = start
        limit = size + 3 + (seed % 7)
        for _ in range(size):
            operation = rng.choice(("add2", "sub1", "double"))
            nxt = _apply_counter(value, operation)
            if 0 <= nxt <= 30:
                value = nxt
        data = {"family": family, "start": start, "target": value, "max_steps": limit,
                "operations": ["add2", "sub1", "double"]}
        prompt = (f"Start at {start} and reach {value}. Operations are add2, sub1, and double. "
                  f"Values must stay between 0 and 30. Use at most {limit} operations. "
                  "Return ANSWER: <JSON array of operations> or ANSWER: IMPOSSIBLE.")
        return _task("planning", family, difficulty, seed, prompt, data)
    width = size + seed + 2
    height = 2 + (seed % 2)
    obstacles = []
    if family == "blocked_column":
        obstacles = [[1, row] for row in range(height)]
    data = {"family": family, "width": width, "height": height, "start": [0, 0],
            "goal": [width - 1, height - 1], "obstacles": obstacles, "max_steps": width * height}
    prompt = (f"Grid width {width}, height {height}. Start at [0, 0] and reach {data['goal']}. "
              f"Obstacles are {obstacles}. Moves are N, E, S, W by one cell. "
              f"Use at most {data['max_steps']} moves and stay inside the grid. "
              "Return ANSWER: <JSON array of moves> or ANSWER: IMPOSSIBLE.")
    return _task("planning", family, difficulty, seed, prompt, data)


def _apply_counter(value, operation):
    if operation == "add2":
        return value + 2
    if operation == "sub1":
        return value - 1
    if operation == "double":
        return value * 2
    raise ValueError("Unknown counter operation")


def _fold_chain(start, steps):
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


def _satisfiable(variables, clauses):
    for mask in range(1 << variables):
        bits = [(mask >> index) & 1 == 1 for index in range(variables)]
        if all(any(bits[abs(literal) - 1] == (literal > 0) for literal in clause) for clause in clauses):
            return True
    return False


def _topo(nodes, edges):
    incoming = [0] * nodes
    outgoing = [[] for _ in range(nodes)]
    for source, target in edges:
        outgoing[source].append(target)
        incoming[target] += 1
    heap = [node for node in range(nodes) if incoming[node] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                heapq.heappush(heap, target)
    if len(order) != nodes:
        return None
    return order


def _grid_neighbors(data, cell):
    width, height = data["width"], data["height"]
    blocked = {tuple(item) for item in data["obstacles"]}
    for move, (dx, dy) in (("E", (1, 0)), ("W", (-1, 0)), ("S", (0, 1)), ("N", (0, -1))):
        nxt = (cell[0] + dx, cell[1] + dy)
        if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in blocked:
            yield move, nxt


def _grid_reachable(data):
    start = tuple(data["start"])
    goal = tuple(data["goal"])
    seen = {start}
    queue = [start]
    while queue:
        cell = queue.pop(0)
        if cell == goal:
            return True
        for _, nxt in _grid_neighbors(data, cell):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _counter_reachable(data):
    limit = data["max_steps"]
    seen = {(data["start"], 0)}
    queue = [(data["start"], 0)]
    while queue:
        value, steps = queue.pop(0)
        if value == data["target"]:
            return True
        if steps == limit:
            continue
        for operation in data["operations"]:
            nxt = _apply_counter(value, operation)
            state = (nxt, steps + 1)
            if 0 <= nxt <= 30 and state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def solve(task):
    data = task["data"]
    family = task["family"]
    if family == "operation_chain":
        return _fold_chain(data["start"], data["steps"])
    if family == "two_moduli":
        return next(value for value in range(data["span"])
                    if value % data["modulus_a"] == data["residue_a"]
                    and value % data["modulus_b"] == data["residue_b"])
    if family == "nested_difference":
        coefficient = data["coefficients"]
        return (coefficient["a"] + coefficient["b"]) * coefficient["c"] - (
            coefficient["d"] + coefficient["e"]) * coefficient["f"]
    if task["domain"] == "logic":
        return "SAT" if _satisfiable(data["variables"], data["clauses"]) else "UNSAT"
    if task["domain"] == "algorithms":
        order = _topo(data["nodes"], data["edges"])
        return "IMPOSSIBLE" if order is None else order
    if family == "counter_walk":
        return "SOLVABLE" if _counter_reachable(data) else "IMPOSSIBLE"
    return "SOLVABLE" if _grid_reachable(data) else "IMPOSSIBLE"


def witness(task):
    """One correct response string. Verification of a submitted plan does not call this."""
    import json
    expected = solve(task)
    if isinstance(expected, str):
        if expected == "SOLVABLE":
            plan = _search_plan(task)
            if plan is None:
                raise ValueError("Solver and search disagree")
            return "ANSWER: " + json.dumps(plan)
        return "ANSWER: " + expected
    return "ANSWER: " + json.dumps(expected)


def _search_plan(task):
    data = task["data"]
    if task["family"] == "counter_walk":
        queue = [(data["start"], [])]
        seen = {(data["start"], 0)}
        while queue:
            value, actions = queue.pop(0)
            if value == data["target"]:
                return actions
            if len(actions) == data["max_steps"]:
                continue
            for operation in data["operations"]:
                nxt = _apply_counter(value, operation)
                state = (nxt, len(actions) + 1)
                if 0 <= nxt <= 30 and state not in seen:
                    seen.add(state)
                    queue.append((nxt, actions + [operation]))
        return None
    start = tuple(data["start"])
    goal = tuple(data["goal"])
    queue = [(start, [])]
    seen = {start}
    while queue:
        cell, actions = queue.pop(0)
        if cell == goal:
            return actions
        if len(actions) == data["max_steps"]:
            continue
        for move, nxt in _grid_neighbors(data, cell):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, actions + [move]))
    return None


def verify(task, answer):
    """Simulate or recompute. Planning solvability is not taken from the submitted plan."""
    try:
        value = _answer_line(answer)
        expected = solve(task)
        family = task["family"]
        if task["domain"] == "math":
            correct = int(value) == expected
        elif task["domain"] == "logic":
            correct = value in ("SAT", "UNSAT") and value == expected
        elif task["domain"] == "algorithms":
            if value == "IMPOSSIBLE":
                correct = expected == "IMPOSSIBLE"
            else:
                parsed = json_list(value)
                correct = parsed == expected
        elif value == "IMPOSSIBLE":
            correct = expected == "IMPOSSIBLE"
        else:
            parsed = json_list(value)
            correct = _plan_succeeds(task, parsed) and expected == "SOLVABLE"
        return {"verifier_id": VERSION + ":" + family, "verifier_version": VERSION,
                "verdict": "correct" if correct else "incorrect", "grading_uncertainty": False}
    except (ValueError, TypeError, KeyError, IndexError):
        return {"verifier_id": VERSION + ":" + task.get("family", "unknown"), "verifier_version": VERSION,
                "verdict": "unparseable", "grading_uncertainty": True}


def json_list(value):
    import json
    parsed = json.loads(value)
    if type(parsed) is not list:
        raise ValueError("Expected a JSON array")
    return parsed


def _plan_succeeds(task, actions):
    data = task["data"]
    if len(actions) > data["max_steps"]:
        return False
    if task["family"] == "counter_walk":
        value = data["start"]
        for action in actions:
            if action not in data["operations"]:
                return False
            value = _apply_counter(value, action)
            if not 0 <= value <= 30:
                return False
        return value == data["target"]
    cell = tuple(data["start"])
    goal = tuple(data["goal"])
    blocked = {tuple(item) for item in data["obstacles"]}
    width, height = data["width"], data["height"]
    moves = {"E": (1, 0), "W": (-1, 0), "S": (0, 1), "N": (0, -1)}
    for action in actions:
        if action not in moves:
            return False
        dx, dy = moves[action]
        cell = (cell[0] + dx, cell[1] + dy)
        if not (0 <= cell[0] < width and 0 <= cell[1] < height) or cell in blocked:
            return False
    return cell == goal
