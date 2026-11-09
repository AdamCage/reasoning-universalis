"""Small exact-reference development constructions, never a final/test corpus.

No network, paid collector, private holdout seed or model outcomes are read.
Construction tiers bound input/solver size, not empirical model difficulty.
"""
from __future__ import annotations

from collections import deque
from fractions import Fraction
import hashlib
import heapq
import itertools
import json
from pathlib import Path
import random
import re

VERSION = "post-v2-compact-answer-design-v1"
SEED = "post-v2-offline-development-2026-11-08"
DOMAINS = ("math", "logic", "algorithms", "planning")
TIERS = ("small", "medium", "large")
LIMITS = {
    "math": (12, 24, 36), "logic": (5, 7, 9),
    "algorithms": (8, 12, 16), "planning": (6, 8, 10),
}
FAMILIES = {"math": "conditional_modular_recurrence", "logic": "exact_cnf_model_count",
            "algorithms": "weighted_dag_shortest_cost", "planning": "ordered_key_grid_distance"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def rng_for(*parts):
    return random.Random(int(digest(list(parts)), 16))


def generate_data(domain, tier, rng):
    size = LIMITS[domain][tier]
    if domain == "math":
        steps = []
        for _ in range(size):
            p = rng.choice((3, 5, 7))
            steps.append({"test_mod": p, "threshold": rng.randrange(1, p),
                          "then_mul": rng.randint(2, 9), "then_add": rng.randint(-29, 29),
                          "else_mul": rng.randint(2, 9), "else_add": rng.randint(-29, 29)})
        return {"initial": rng.randrange(1000), "modulus": (1009, 10007, 100003)[tier], "steps": steps}
    if domain == "logic":
        universe = [tuple(sorted(sign * variable for sign, variable in zip(signs, variables)))
                    for variables in itertools.combinations(range(1, size + 1), 3)
                    for signs in itertools.product((-1, 1), repeat=3)]
        clauses = rng.sample(universe, (7, 11, 15)[tier])
        return {"variables": size, "clauses": [list(c) for c in sorted(clauses)]}
    if domain == "algorithms":
        order = rng.sample(range(size), size)
        positions = {(i, i + 1) for i in range(size - 1)}
        for i in range(size):
            for j in range(i + 2, size):
                if rng.random() < .22:
                    positions.add((i, j))
        return {"nodes": size, "start": order[0], "goal": order[-1],
                "edges": [[order[a], order[b], rng.randint(-9, 15)] for a, b in sorted(positions)]}
    if domain != "planning":
        raise ValueError("Unsupported domain")
    cells = [(x, y) for y in range(size) for x in range(size) if (x, y) not in ((0, 0), (size - 1, size - 1))]
    key_cells = rng.sample(cells, tier + 1)
    remainder = [c for c in cells if c not in key_cells]
    obstacles = rng.sample(remainder, (5, 10, 17)[tier])
    doors = [{"cell": list(key_cells[i]), "key": i - 1} for i in range(1, len(key_cells))]
    doors.append({"cell": [size - 1, size - 1], "key": len(key_cells) - 1})
    return {"width": size, "height": size, "start": [0, 0], "goal": [size - 1, size - 1],
            "keys": [{"cell": list(c), "key": i} for i, c in enumerate(key_cells)],
            "doors": doors, "obstacles": [list(c) for c in sorted(obstacles)]}


def _topology(data):
    n = data["nodes"]
    degree, adjacency = [0] * n, [[] for _ in range(n)]
    for a, b, w in data["edges"]:
        degree[b] += 1
        adjacency[a].append((b, w))
    ready = [v for v in range(n) if not degree[v]]
    heapq.heapify(ready)
    order = []
    while ready:
        a = heapq.heappop(ready)
        order.append(a)
        for b, _ in adjacency[a]:
            degree[b] -= 1
            if not degree[b]:
                heapq.heappush(ready, b)
    if len(order) != n:
        raise ValueError("Expected a DAG")
    return order, adjacency


def _grid_bfs(data):
    keys = {tuple(row["cell"]): row["key"] for row in data["keys"]}
    doors = {tuple(row["cell"]): row["key"] for row in data["doors"]}
    obstacles = set(map(tuple, data["obstacles"]))
    start = (*data["start"], 0)
    distances, queue = {start: 0}, deque([start])
    while queue:
        x, y, mask = current = queue.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            cell = x + dx, y + dy
            if not (0 <= cell[0] < data["width"] and 0 <= cell[1] < data["height"]):
                continue
            if cell in obstacles or (cell in doors and not mask & (1 << doors[cell])):
                continue
            new_mask = mask | ((1 << keys[cell]) if cell in keys else 0)
            state = (*cell, new_mask)
            if state not in distances:
                distances[state] = distances[current] + 1
                queue.append(state)
    candidates = [d for state, d in distances.items() if state[:2] == tuple(data["goal"])]
    return min(candidates) if candidates else "IMPOSSIBLE", distances


def reference(domain, data):
    if domain == "math":
        x, history = data["initial"], [data["initial"]]
        for step in data["steps"]:
            branch = "then" if x % step["test_mod"] < step["threshold"] else "else"
            x = (step[branch + "_mul"] * x + step[branch + "_add"]) % data["modulus"]
            history.append(x)
        result = {"answer": x, "history": history, "solver_work": {"steps": len(data["steps"])}}
    elif domain == "logic":
        n = data["variables"]
        full = (1 << (1 << n)) - 1
        patterns = [sum(1 << a for a in range(1 << n) if a & (1 << v)) for v in range(n)]
        feasible = full
        for clause in data["clauses"]:
            mask = 0
            for literal in clause:
                pattern = patterns[abs(literal) - 1]
                mask |= pattern if literal > 0 else full ^ pattern
            feasible &= mask
        result = {"answer": feasible.bit_count(), "assignment_bitmap_sha256": digest(str(feasible)),
                  "solver_work": {"assignment_bound": 1 << n, "clauses": len(data["clauses"])}}
    elif domain == "algorithms":
        order, adjacency = _topology(data)
        distance = [None] * data["nodes"]
        distance[data["start"]] = 0
        for a in order:
            if distance[a] is None:
                continue
            for b, w in adjacency[a]:
                candidate = distance[a] + w
                if distance[b] is None or candidate < distance[b]:
                    distance[b] = candidate
        result = {"answer": distance[data["goal"]] if distance[data["goal"]] is not None else "IMPOSSIBLE",
                  "topological_order": order, "distances": distance,
                  "solver_work": {"nodes": data["nodes"], "edges": len(data["edges"])}}
    elif domain == "planning":
        answer, distances = _grid_bfs(data)
        result = {"answer": answer, "distance_map_sha256": digest(sorted([list(s), d] for s, d in distances.items())),
                  "solver_work": {"reachable_states": len(distances),
                                  "state_upper_bound": data["width"] * data["height"] * 2 ** len(data["keys"])}}
    else:
        raise ValueError("Unsupported domain")
    return {"version": VERSION, "instance_sha256": digest({"domain": domain, "data": data}), **result}


def independent_answer(domain, data):
    """Distinct reference implementations, not a second call to reference()."""
    if domain == "math":
        value = Fraction(data["initial"])
        for row in data["steps"]:
            if int(value) % row["test_mod"] >= row["threshold"]:
                value = Fraction(row["else_add"]) + value * row["else_mul"]
            else:
                value = Fraction(row["then_add"]) + value * row["then_mul"]
            value = Fraction(value.numerator % data["modulus"], value.denominator)
        assert value.denominator == 1
        return int(value)
    if domain == "logic":
        # Recursive partial-assignment pruning independently counts every value
        # of every declared variable, including variables absent from clauses.
        def count(values):
            unresolved = False
            for clause in data["clauses"]:
                truth = [((values[abs(v) - 1] == (v > 0)) if abs(v) <= len(values) else None) for v in clause]
                if True in truth:
                    continue
                if None not in truth:
                    return 0
                unresolved = True
            if not unresolved:
                return 1 << (data["variables"] - len(values))
            return count(values + [False]) + count(values + [True])
        return count([])
    if domain == "algorithms":
        distance = {data["start"]: 0}
        for _ in range(data["nodes"] - 1):
            previous = dict(distance)
            for a, b, weight in data["edges"]:
                if a in previous:
                    value = previous[a] + weight
                    if b not in distance or value < distance[b]:
                        distance[b] = value
        return distance.get(data["goal"], "IMPOSSIBLE")
    if domain != "planning":
        raise ValueError("Unsupported domain")
    # Heap search with separate transition code checks minimal distance, not
    # merely feasibility of one path. Keys persist and are never consumed.
    blocked = {tuple(p) for p in data["obstacles"]}
    todo, seen = [(0, data["start"][0], data["start"][1], 0)], set()
    while todo:
        distance, x, y, inventory = heapq.heappop(todo)
        state = x, y, inventory
        if state in seen:
            continue
        seen.add(state)
        if [x, y] == data["goal"]:
            return distance
        for a, b in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if a < 0 or b < 0 or a >= data["width"] or b >= data["height"] or (a, b) in blocked:
                continue
            door = next((r["key"] for r in data["doors"] if r["cell"] == [a, b]), None)
            if door is not None and not inventory & 2 ** door:
                continue
            item = next((r["key"] for r in data["keys"] if r["cell"] == [a, b]), None)
            updated = inventory if item is None else inventory | 2 ** item
            if (a, b, updated) not in seen:
                heapq.heappush(todo, (distance + 1, a, b, updated))
    return "IMPOSSIBLE"


def perturb(domain, data, rng):
    value = json.loads(canonical(data))
    if domain == "logic":
        labels = rng.sample(range(1, value["variables"] + 1), value["variables"])
        value["clauses"] = [[(1 if x > 0 else -1) * labels[abs(x) - 1] for x in c] for c in value["clauses"]]
        rng.shuffle(value["clauses"])
        for c in value["clauses"]:
            rng.shuffle(c)
    elif domain == "algorithms":
        labels = rng.sample(range(value["nodes"]), value["nodes"])
        value["edges"] = [[labels[a], labels[b], w] for a, b, w in value["edges"]]
        value["start"], value["goal"] = labels[value["start"]], labels[value["goal"]]
        rng.shuffle(value["edges"])
    elif domain == "planning":
        width, height = value["width"], value["height"]
        def rotate(cell):
            return [height - 1 - cell[1], cell[0]]
        value["width"], value["height"] = height, width
        value["start"], value["goal"] = rotate(value["start"]), rotate(value["goal"])
        value["obstacles"] = [rotate(c) for c in value["obstacles"]]
        for name in ("keys", "doors"):
            value[name] = [{**row, "cell": rotate(row["cell"])} for row in value[name]]
    return value


def prompt(domain, data, member):
    opening = ("Solve the following precisely specified problem carefully. " if not member else
               "Work through this exact problem carefully under the stated rules. ")
    serialized = canonical(data).decode("utf-8")
    if domain == "math":
        description = ("Start with initial. For each listed step, using the OLD current x, test x % test_mod < threshold. "
                       "If true, replace x by (then_mul*x+then_add) % modulus; otherwise use (else_mul*x+else_add) % modulus. "
                       "Modulo is the least nonnegative remainder. Return x after all steps. ")
    elif domain == "logic":
        description = ("Count satisfying Boolean assignments to ALL declared variables 1..variables, including any unused variables. "
                       "Clauses are a conjunction of disjunctions; negative literals negate the indexed variable. Return the exact count, or 0 if none. ")
    elif domain == "algorithms":
        description = ("In this directed acyclic graph, edges are [source,target,integer_weight] and may have negative weight. "
                       "Return the minimum total weight of a path from start to goal; return IMPOSSIBLE if none exists. ")
    else:
        description = ("Find the minimum number of unit north/east/south/west moves from start to goal. Coordinates are [x,y], "
                       "0<=x<width and 0<=y<height. Stay inside and avoid obstacles. Initially hold no keys. Entering a key cell picks up "
                       "that key permanently and without extra move cost. Before entering a door cell you must already hold its indexed key; "
                       "keys are never consumed. A cell may hold both a door and a key: test the door before picking up the key. "
                       "Return IMPOSSIBLE if unreachable. ")
    answer_type = "the integer" if domain in ("math", "logic") else "the integer or IMPOSSIBLE"
    return opening + description + "Data: " + serialized + ". Put only " + answer_type + " after ANSWER: on the final line."


def structural_key(domain, data):
    # Conservative exact colored-graph summaries; no complete semantic or
    # arbitrary-isomorphism independence claim is made.
    from pilot_v2.tasks import _wl, structural_fingerprint
    if domain == "logic":
        return structural_fingerprint({"domain": "logic", "data": data})
    if domain == "algorithms":
        colors = [("start" if n == data["start"] else "goal" if n == data["goal"] else "node") for n in range(data["nodes"])]
        return "weighted-dag-wl8:" + _wl(colors, [(a, b, str(w)) for a, b, w in data["edges"]])
    if domain == "planning":
        values, item = [], data
        for _ in range(4):
            values.append(canonical({**item, "obstacles": sorted(item["obstacles"]),
                                    "keys": sorted(item["keys"], key=lambda r: r["key"]),
                                    "doors": sorted(item["doors"], key=lambda r: r["key"])}))
            item = perturb(domain, item, rng_for("rotation"))
        return "key-grid-C4:" + hashlib.sha256(min(values)).hexdigest()
    return "conditional-program-exact:" + digest(data)


def build(seed=SEED):
    tasks, structures = [], set()
    seed_namespace = digest([VERSION, seed])[:12]
    for domain in DOMAINS:
        for tier, name in enumerate(TIERS):
            for index in range(2):
                root = f"v3dev-{seed_namespace}-{domain}-{name}-{index}"
                for candidate in range(64):
                    data = generate_data(domain, tier, rng_for(seed, root, candidate))
                    cert = reference(domain, data)
                    key = structural_key(domain, data)
                    if key not in structures and (domain != "planning" or cert["answer"] != "IMPOSSIBLE"):
                        break
                else:
                    raise ValueError("Finite offline construction attempts exhausted")
                structures.add(key)
                for member in range(2):
                    variant = data if not member else perturb(domain, data, rng_for(seed, root, "presentation"))
                    certificate = reference(domain, variant)
                    if independent_answer(domain, variant) != certificate["answer"] or certificate["answer"] != cert["answer"]:
                        raise ValueError("Independent certificate or perturbation check failed")
                    tasks.append({"task_id": f"{root}-p{member}", "root_id": root, "domain": domain,
                                  "family": FAMILIES[domain], "tier": name, "variant": member,
                                  "previously_observed": True, "forced_split": "development",
                                  "data": variant, "prompt": prompt(domain, variant, member),
                                  "structural_key": key, "reference": certificate, "reference_sha256": digest(certificate),
                                  "construction_candidate_index": candidate})
    return {"schema_version": 1, "version": VERSION, "seed": seed,
            "status": "offline_exposed_development_preview_no_model_responses", "roots": 24, "tasks": tasks,
            "holdout": "No private seed read, no final/validation/test corpus generated.",
            "dependence": "Two presentation variants share each root; 24 root groups share four construction templates.",
            "limits": LIMITS, "corpus_sha256": digest(tasks)}


def verify_task(task):
    certificate = reference(task["domain"], task["data"])
    return (task["reference"] == certificate and task["reference_sha256"] == digest(certificate)
            and independent_answer(task["domain"], task["data"]) == certificate["answer"]
            and task["prompt"] == prompt(task["domain"], task["data"], task["variant"]))


def grade_answer(task, final_answer_channel):
    """Prospective strict last-line grammar; never reconstruct from reasoning.

This reports answer validity only. Completion/provider/prefix eligibility must
be checked separately by a future collector; a parsed answer never repairs a
length-censored response.
"""
    if not verify_task(task):
        raise ValueError("Reference certificate or task prompt is invalid")
    result = {"gradable": False, "parsed_answer": None, "correct": None}
    if not isinstance(final_answer_channel, str) or not final_answer_channel.strip():
        return result
    line = final_answer_channel.strip().splitlines()[-1].strip()
    match = re.fullmatch(r"ANSWER: (-?(?:0|[1-9][0-9]*)|IMPOSSIBLE)", line)
    if not match or (match[1] == "IMPOSSIBLE" and task["domain"] in ("math", "logic")):
        return result
    if len(match[1].lstrip("-")) > 1000:
        return result
    parsed = "IMPOSSIBLE" if match[1] == "IMPOSSIBLE" else int(match[1])
    return {"gradable": True, "parsed_answer": parsed, "correct": parsed == task["reference"]["answer"]}
