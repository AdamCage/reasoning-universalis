"""Auditable development-only tasks; no model calls and no generated holdout.

Two explicitly dependent perturbations share each original root. Difficulty
changes problem data, while inference/output budgets belong to the runner.
Historical problem data are read only for overlap auditing, never model labels.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from fractions import Fraction
import gzip
import hashlib
import heapq
import importlib
import itertools
import json
from pathlib import Path
import random
import re
import secrets


ROOT = Path(__file__).resolve().parents[1]
VERSION = "pilot-v2-development-v1"
VERIFIER_VERSION = "pilot-v2-reference-v1"
DEFAULT_DEVELOPMENT_SEED = "pilot-v2-development-2026-11-08"
DOMAINS = ("math", "logic", "algorithms", "planning")
TIERS = ("low", "medium", "high")
MOVES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
PUBLIC_PATH = ROOT / "artifacts/pilot-v2-2026-11-08/development-tasks.json"
PRIVATE_HOLDOUT_PATH = ROOT / ".research/pilot-v2-holdout-seed.bin"
LIMITS = {
    "math": ({"tracks": 3, "operations_per_track": 12, "start_digits": 3, "operand_digits": 2},
             {"tracks": 3, "operations_per_track": 18, "start_digits": 4, "operand_digits": 3},
             {"tracks": 3, "operations_per_track": 24, "start_digits": 5, "operand_digits": 4}),
    "logic": ({"variables": 9, "clauses": 38}, {"variables": 11, "clauses": 47},
              {"variables": 13, "clauses": 56}),
    "algorithms": ({"nodes": 10, "edges": 18}, {"nodes": 14, "edges": 30},
                   {"nodes": 18, "edges": 46}),
    "planning": ({"width": 8, "obstacles": 12, "max_steps": 18},
                 {"width": 10, "obstacles": 23, "max_steps": 24},
                 {"width": 12, "obstacles": 40, "max_steps": 32}),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_prompt_key(text):
    return text_digest(" ".join(text.casefold().split()))


def integer(value):
    if type(value) is not int:
        raise ValueError("Expected an integer, not bool/float")
    return value


def normalized_data(task):
    data = {key: value for key, value in task["data"].items() if key != "family"}
    if "clauses" in data:
        data["clauses"] = sorted({tuple(sorted(set(clause))) for clause in data["clauses"]})
    for name in ("edges", "obstacles"):
        if name in data:
            data[name] = sorted({tuple(item) for item in data[name]})
    if "tracks" in data:
        data["tracks"] = sorted(data["tracks"], key=lambda row: canonical(row))
    return data


def exact_instance_key(task):
    return digest({"domain": task["domain"], "data": normalized_data(task)})


def _wl(colors, edges):
    """Isomorphism-invariant colored-graph summary, not a complete iso test."""
    adjacency = [[] for _ in colors]
    for source, target, label in edges:
        adjacency[source].append((target, "out:" + label))
        adjacency[target].append((source, "in:" + label))
    labels = [digest({"color": color}) for color in colors]
    for _ in range(8):
        labels = [digest([label, sorted((kind, labels[neighbor]) for neighbor, kind in adjacency[index])])
                  for index, label in enumerate(labels)]
    return digest({"nodes": len(colors), "edges": len(edges), "labels": sorted(labels)})


def grid_transform(data, rotation, reflection=False):
    width, height = data["width"], data["height"]
    def cell(point):
        x, y = point
        w, h = width, height
        if reflection:
            x = w - 1 - x
        for _ in range(rotation):
            x, y, w, h = h - 1 - y, x, h, w
        return [x, y]
    transformed = dict(data)
    transformed.update(width=height if rotation % 2 else width,
                       height=width if rotation % 2 else height,
                       start=cell(data["start"]), goal=cell(data["goal"]),
                       obstacles=sorted(cell(point) for point in data["obstacles"]))
    return transformed


def structural_fingerprint(task):
    domain, data = task["domain"], normalized_data(task)
    if domain == "logic" and {"variables", "clauses"} <= data.keys():
        colors = ["variable"] * data["variables"]
        edges = []
        for clause in data["clauses"]:
            clause_id = len(colors)
            colors.append("clause")
            for literal in clause:
                occurrence = len(colors)
                colors.append("positive" if literal > 0 else "negative")
                edges.extend(((clause_id, occurrence, "contains"),
                              (abs(literal) - 1, occurrence, "literal")))
        return "cnf-wl8:" + _wl(colors, edges)
    if domain == "algorithms" and {"nodes", "edges"} <= data.keys():
        return "directed-graph-wl8:" + _wl(["node"] * data["nodes"],
                                          [(a, b, "edge") for a, b in data["edges"]])
    if domain == "planning" and {"width", "height", "obstacles", "start", "goal"} <= data.keys():
        variants = []
        for mirror in (False, True):
            for rotation in range(4):
                transformed = grid_transform(data, rotation, mirror)
                variants.append(canonical({key: transformed[key] for key in
                    ("width", "height", "start", "goal", "obstacles", "max_steps")}))
        return "grid-D4:" + hashlib.sha256(min(variants)).hexdigest()
    if domain == "math":
        if "tracks" in data:
            programs = [([step[0] for step in track["steps"]], track["weight"]) for track in data["tracks"]]
        elif {"left", "right"} <= data.keys():
            programs = [([step[0] for step in data["left"]], 1),
                        ([step[0] for step in data["right"]], -1)]
        elif "steps" in data:
            programs = [([step[0] for step in data["steps"]], 1)]
        else:
            return "arithmetic-other-schema:" + digest(sorted(data))
        return "arithmetic-program-skeleton:" + digest(sorted(programs))
    return None


class LegacyIndex:
    def __init__(self):
        self.exact = set()
        self.prompts = set()
        self.structural = set()
        self.sources = []
        self.rows = 0
        self.unsupported_structural = Counter()

    def add(self, task):
        self.rows += 1
        if task.get("prompt"):
            self.prompts.add(normalized_prompt_key(task["prompt"]))
        if not isinstance(task.get("data"), dict) or task.get("domain") not in DOMAINS:
            self.unsupported_structural["missing_problem_data"] += 1
            return
        self.exact.add(exact_instance_key(task))
        fingerprint = structural_fingerprint(task)
        if fingerprint is None:
            self.unsupported_structural[task["domain"]] += 1
        else:
            self.structural.add(fingerprint)

    @classmethod
    def from_tasks(cls, tasks):
        result = cls()
        for task in tasks:
            result.add(task)
        return result

    def report(self):
        return {"source_rows": self.rows, "unique_normalized_instances": len(self.exact),
                "normalized_prompt_keys": len(self.prompts), "structural_fingerprints": len(self.structural),
                "unsupported_structural_rows": dict(self.unsupported_structural), "sources": self.sources,
                "interpretation": "Exact normalized overlap and conservative structural flags only; no proof of arbitrary graph isomorphism or algebraic inequivalence. Missing historical problem data remain explicit."}


def load_legacy_inventory(project_root=ROOT):
    """Use task data and audit metadata; never read v1 model outcomes/results."""
    project_root = Path(project_root)
    index = LegacyIndex()
    def source(relative):
        path = project_root / relative
        data = path.read_bytes()
        index.sources.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
        return data
    for suffix in ("", "_V2", "_V3", "_V4"):
        document = json.loads(source("design/PILOT_SECTION_5_5_ROSTER" + suffix + ".json"))
        for task in document["tasks"]:
            index.add(task)
    document = json.loads(source("artifacts/resumption-2026-11-08/tasks.json"))
    for task in document["tasks"] + document.get("admission_tasks", []):
        index.add(task)
    historical = json.loads(source("design/historical-development-manifest.json"))
    for task in historical["tasks"]:
        index.add(task)
    audit_relative = "artifacts/resumption-2026-11-08/generator_audit/instances.jsonl.gz"
    raw_audit = source(audit_relative)
    modules = {"v1": importlib.import_module("stage2.datasets"),
               **{version: importlib.import_module("stage3.generators_" + version)
                  for version in ("v2", "v3", "v4")}}
    for version, module in modules.items():
        relative = "stage2/datasets.py" if version == "v1" else "stage3/generators_" + version + ".py"
        source(relative)
    # The published audit has hashes/seed metadata, not problem data. Regenerate
    # previously unseen exact instances and verify their published input hashes.
    for line in gzip.decompress(raw_audit).splitlines():
        row = json.loads(line)
        expected_key = row["canonical_instance_sha256"]
        index.rows += 1
        if expected_key in index.exact:
            continue
        module = modules[row["version"]]
        task = (module.generate(row["domain"], row["seed"], row["difficulty"])
                if row["version"] == "v1" else
                module.generate(row["domain"], row["family"], row["difficulty"], row["seed"]))
        if exact_instance_key(task) != expected_key or text_digest(task["prompt"]) != row["prompt_sha256"]:
            raise ValueError("Historical audit input no longer matches its published generator hashes")
        index.rows -= 1
        index.add(task)
    return index


def _math_values(data, fraction=False):
    values, outputs = [], []
    for track in data["tracks"]:
        value = Fraction(integer(track["initial"])) if fraction else integer(track["initial"])
        history = [int(value)]
        for operation, operand in track["steps"]:
            operand = integer(operand)
            if operation == "add": value += operand
            elif operation == "sub": value -= operand
            elif operation == "mul": value *= operand
            else: raise ValueError("Unknown exact arithmetic operation")
            history.append(int(value))
        outputs.append(value * integer(track["weight"]))
        values.append(history)
    return int(sum(outputs)), values


def _logic_bitset(data):
    n = integer(data["variables"])
    if not 1 <= n <= 14:
        raise ValueError("Exact CNF certification is bounded at 14 variables")
    count = 1 << n
    universe = (1 << count) - 1
    variables = [sum(1 << assignment for assignment in range(count) if assignment & (1 << variable))
                 for variable in range(n)]
    solutions = universe
    for clause in data["clauses"]:
        satisfied = 0
        for literal in clause:
            if not 1 <= abs(integer(literal)) <= n:
                raise ValueError("CNF literal outside declared variables")
            satisfied |= variables[abs(literal) - 1] if literal > 0 else universe ^ variables[abs(literal) - 1]
        solutions &= satisfied
    return solutions, count


def _topology(data):
    n = integer(data["nodes"])
    if not 1 <= n <= 32:
        raise ValueError("Topological certificate bound exceeded")
    successors = [set() for _ in range(n)]
    indegree = [0] * n
    for source, target in data["edges"]:
        if not 0 <= integer(source) < n or not 0 <= integer(target) < n:
            raise ValueError("Graph node outside declared range")
        if target not in successors[source]:
            successors[source].add(target)
            indegree[target] += 1
    ready = [node for node in range(n) if not indegree[node]]
    heapq.heapify(ready)
    order, availability = [], []
    while ready:
        availability.append(sorted(ready))
        node = heapq.heappop(ready)
        order.append(node)
        for target in sorted(successors[node]):
            indegree[target] -= 1
            if not indegree[target]: heapq.heappush(ready, target)
    if len(order) == n:
        longest = [1] * n
        for node in order:
            for target in successors[node]: longest[target] = max(longest[target], longest[node] + 1)
        return order, {"kind": "lexicographic_topological_witness", "order": order, "availability_steps": availability,
                       "critical_path_nodes": max(longest), "maximum_ready_frontier": max(map(len, availability))}
    color, stack = [0] * n, []
    def visit(node):
        color[node] = 1
        stack.append(node)
        for target in sorted(successors[node]):
            if color[target] == 1:
                return stack[stack.index(target):] + [target]
            if not color[target]:
                found = visit(target)
                if found: return found
        stack.pop()
        color[node] = 2
        return None
    cycle = next(found for node in range(n) if not color[node] for found in [visit(node)] if found)
    return "IMPOSSIBLE", {"kind": "directed_cycle_witness", "cycle": cycle}


def _grid_search(data):
    width, height = integer(data["width"]), integer(data["height"])
    start, goal = tuple(data["start"]), tuple(data["goal"])
    blocked = {tuple(cell) for cell in data["obstacles"]}
    if (not 1 <= width <= 32 or not 1 <= height <= 32 or integer(data["max_steps"]) < 0
            or any(len(point) != 2 or any(type(value) is not int for value in point)
                   or not (0 <= point[0] < width and 0 <= point[1] < height)
                   for point in [start, goal, *blocked]) or start in blocked or goal in blocked):
        raise ValueError("Invalid grid endpoints")
    distances, parents = {start: 0}, {}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for move, (dx, dy) in MOVES.items():
            nxt = cell[0] + dx, cell[1] + dy
            if (0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in blocked and nxt not in distances):
                distances[nxt] = distances[cell] + 1
                parents[nxt] = cell, move
                queue.append(nxt)
    answer = "IMPOSSIBLE"
    if goal in distances and distances[goal] <= integer(data["max_steps"]):
        answer, cell = [], goal
        while cell != start:
            cell, move = parents[cell]
            answer.append(move)
        answer.reverse()
    return answer, distances


def reference_certificate(task):
    domain, data = task["domain"], task["data"]
    if domain == "math":
        answer, values = _math_values(data)
        certificate = {"kind": "exact_track_evaluation", "answer": answer, "track_values": values}
    elif domain == "logic":
        solutions, count = _logic_bitset(data)
        answer = "SAT" if solutions else "UNSAT"
        first = (solutions & -solutions).bit_length() - 1 if solutions else None
        certificate = {"kind": "exhaustive_cnf_truth_table", "answer": answer,
            "assignment_count": count, "satisfying_assignments": solutions.bit_count(),
            "witness": [(first >> variable) & 1 == 1 for variable in range(data["variables"])] if first is not None else None,
            "truth_table_sha256": hashlib.sha256(solutions.to_bytes((count + 7) // 8, "little")).hexdigest()}
    elif domain == "algorithms":
        answer, certificate = _topology(data)
    elif domain == "planning":
        answer, distances = _grid_search(data)
        certificate = {"kind": "complete_grid_bfs", "answer": answer,
            "reachable_cells": len(distances), "shortest_distance": distances.get(tuple(data["goal"])),
            "distance_map_sha256": digest(sorted((list(cell), value) for cell, value in distances.items()))}
    else:
        raise ValueError("Unknown task domain")
    return {"verifier_version": VERIFIER_VERSION, "instance_sha256": exact_instance_key(task), **certificate}


def solve_reference(task):
    certificate = reference_certificate(task)
    if task["domain"] == "algorithms":
        return certificate.get("order", "IMPOSSIBLE")
    return certificate["answer"]


def verify_certificate(task, certificate):
    """Separate algorithms from the primary bitset/heap/queue reference paths."""
    if (certificate.get("instance_sha256") != exact_instance_key(task)
            or certificate.get("verifier_version") != VERIFIER_VERSION):
        return False
    data, domain = task["data"], task["domain"]
    if domain == "math":
        # Separate operator dispatch and Fraction arithmetic deliberately avoid
        # sharing the primary evaluator's branches or intermediate values.
        values, terms = [], []
        for track in data["tracks"]:
            current = Fraction(integer(track["initial"]))
            history = [int(current)]
            operations = {"add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b}
            for name, operand in track["steps"]:
                if name not in operations: return False
                current = operations[name](current, Fraction(integer(operand)))
                history.append(int(current))
            values.append(history)
            terms.append(Fraction(integer(track["weight"])) * current)
        answer = int(sum(terms, Fraction(0)))
        return certificate.get("kind") == "exact_track_evaluation" and certificate.get("answer") == answer and certificate.get("track_values") == values
    if domain == "logic":
        n, count = data["variables"], 1 << data["variables"]
        if n > 14: return False
        truth, witnesses = bytearray((count + 7) // 8), []
        satisfying = 0
        for assignment in range(count):
            bits = [(assignment >> variable) & 1 == 1 for variable in range(n)]
            if all(any(bits[abs(literal) - 1] == (literal > 0) for literal in clause) for clause in data["clauses"]):
                truth[assignment // 8] |= 1 << (assignment % 8)
                satisfying += 1
                if not witnesses: witnesses = bits
        expected = {"kind": "exhaustive_cnf_truth_table", "answer": "SAT" if satisfying else "UNSAT",
            "assignment_count": count, "satisfying_assignments": satisfying,
            "witness": witnesses if satisfying else None,
            "truth_table_sha256": hashlib.sha256(truth).hexdigest()}
        return all(certificate.get(key) == value for key, value in expected.items())
    if domain == "algorithms":
        edges, n = set(map(tuple, data["edges"])), data["nodes"]
        if certificate.get("kind") == "directed_cycle_witness":
            cycle = certificate.get("cycle", [])
            return (len(cycle) >= 2 and cycle[0] == cycle[-1] and len(set(cycle[:-1])) == len(cycle) - 1
                    and all((a, b) in edges for a, b in zip(cycle, cycle[1:])))
        remaining, availability = set(range(n)), []
        order = certificate.get("order", [])
        if len(order) != n or set(order) != remaining: return False
        for node in order:
            ready = sorted(candidate for candidate in remaining if not any(b == candidate and a in remaining for a, b in edges))
            if not ready or node != ready[0]: return False
            availability.append(ready)
            remaining.remove(node)
        longest = {}
        for node in order:
            longest[node] = 1 + max((longest[a] for a, b in edges if b == node), default=0)
        return (certificate.get("kind") == "lexicographic_topological_witness"
                and certificate.get("availability_steps") == availability
                and certificate.get("critical_path_nodes") == max(longest.values())
                and certificate.get("maximum_ready_frontier") == max(map(len, availability)))
    if domain == "planning":
        start, goal = tuple(data["start"]), tuple(data["goal"])
        blocked = set(map(tuple, data["obstacles"]))
        distances, frontier, depth = {start: 0}, {start}, 0
        while frontier:
            following = set()
            for x, y in frontier:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = x + dx, y + dy
                    if (0 <= nxt[0] < data["width"] and 0 <= nxt[1] < data["height"]
                            and nxt not in blocked and nxt not in distances): following.add(nxt)
            depth += 1
            for cell in following: distances[cell] = depth
            frontier = following
        distance = distances.get(goal)
        answer = certificate.get("answer")
        feasible = distance is not None and distance <= data["max_steps"]
        return (certificate.get("kind") == "complete_grid_bfs" and certificate.get("reachable_cells") == len(distances)
                and certificate.get("shortest_distance") == distance
                and certificate.get("distance_map_sha256") == digest(sorted((list(cell), value) for cell, value in distances.items()))
                and (_valid_plan(data, answer) if feasible else answer == "IMPOSSIBLE"))
    return False


def _valid_plan(data, actions):
    if type(actions) is not list or len(actions) > data["max_steps"] or any(type(action) is not str or action not in MOVES for action in actions):
        return False
    cell, blocked = tuple(data["start"]), set(map(tuple, data["obstacles"]))
    for action in actions:
        dx, dy = MOVES[action]
        cell = cell[0] + dx, cell[1] + dy
        if not (0 <= cell[0] < data["width"] and 0 <= cell[1] < data["height"]) or cell in blocked: return False
    return cell == tuple(data["goal"])


def verify_answer(task, text):
    if task.get("generator_version") != VERSION or task.get("domain") not in DOMAINS:
        raise ValueError("Unknown pilot-v2 task/version")
    if (task.get("task_digest") != digest({key: value for key, value in task.items() if key != "task_digest"})
            or task.get("instance_sha256") != exact_instance_key(task)
            or task.get("reference_certificate_sha256") != digest(task.get("reference_certificate"))):
        raise ValueError("Pilot-v2 task or reference provenance was modified")
    certificate = reference_certificate(task)
    result = {"verifier_id": VERIFIER_VERSION + ":" + task["domain"], "verdict": "unparseable", "correct": None,
              "gradable": False, "parsed_answer": None, "reference_certificate_sha256": digest(certificate)}
    lines = [line.strip() for line in text.splitlines() if line.strip()] if isinstance(text, str) else []
    if not lines or not lines[-1].startswith("ANSWER: "): return result
    payload = lines[-1][8:].strip()
    domain = task["domain"]
    if domain == "math":
        if len(payload) > 1000 or not re.fullmatch(r"[+-]?[0-9]+", payload): return result
        parsed = int(payload)
        correct = parsed == certificate["answer"]
    elif domain == "logic":
        if payload not in ("SAT", "UNSAT"): return result
        parsed, correct = payload, payload == certificate["answer"]
    elif payload == "IMPOSSIBLE":
        parsed = payload
        correct = certificate.get("kind") == "directed_cycle_witness" if domain == "algorithms" else certificate["answer"] == payload
    else:
        try: parsed = json.loads(payload)
        except (ValueError, TypeError): return result
        if type(parsed) is not list: return result
        if domain == "algorithms":
            if any(type(item) is not int for item in parsed): return result
            correct = certificate.get("kind") == "lexicographic_topological_witness" and parsed == certificate["order"]
        else:
            if any(type(item) is not str or item not in MOVES for item in parsed): return result
            correct = _valid_plan(task["data"], parsed)
    result.update(verdict="correct" if correct else "incorrect", correct=bool(correct), gradable=True, parsed_answer=parsed)
    return result


def witness_text(task):
    answer = solve_reference(task)
    return "ANSWER: " + (json.dumps(answer) if isinstance(answer, list) else str(answer))


def _base(domain, tier, root_index, rng):
    limits = LIMITS[domain][TIERS.index(tier)]
    if domain == "math":
        tracks = []
        for weight in (1, -1, 1):
            steps = []
            for index in range(limits["operations_per_track"]):
                operation = rng.choice(("add", "sub", "mul"))
                operand = rng.randint(2, 9) if operation == "mul" else rng.randint(10 ** (limits["operand_digits"] - 1), 10 ** limits["operand_digits"] - 1)
                steps.append([operation, operand])
            tracks.append({"initial": rng.randint(10 ** (limits["start_digits"] - 1), 10 ** limits["start_digits"] - 1),
                           "steps": steps, "weight": weight})
        return {"tracks": tracks}
    if domain == "logic":
        n, clauses = limits["variables"], set()
        while len(clauses) < limits["clauses"]:
            clauses.add(tuple(sorted(rng.choice((-1, 1)) * variable for variable in rng.sample(range(1, n + 1), 3))))
        return {"variables": n, "clauses": [list(clause) for clause in sorted(clauses)]}
    if domain == "algorithms":
        n, count = limits["nodes"], limits["edges"]
        labels = rng.sample(range(n), n)
        if root_index == 0:
            edges = rng.sample([(labels[a], labels[b]) for a in range(n) for b in range(a + 1, n)], count)
        else:
            cycle = rng.sample(range(n), 4)
            edges = list(zip(cycle, cycle[1:] + cycle[:1]))
            edges += rng.sample([(a, b) for a in range(n) for b in range(n) if a != b and (a, b) not in edges], count - len(edges))
        return {"nodes": n, "edges": [list(edge) for edge in edges]}
    width = limits["width"]
    cells = [(x, y) for x in range(width) for y in range(width) if (x, y) not in ((0, 0), (width - 1, width - 1))]
    return {"width": width, "height": width, "start": [0, 0], "goal": [width - 1, width - 1],
            "obstacles": [list(cell) for cell in rng.sample(cells, limits["obstacles"])], "max_steps": limits["max_steps"]}


def _perturb(domain, base, rng, member):
    data = json.loads(canonical(base))
    if domain == "math":
        rng.shuffle(data["tracks"])
    elif domain == "logic":
        labels = rng.sample(range(1, data["variables"] + 1), data["variables"])
        data["clauses"] = [[(1 if literal > 0 else -1) * labels[abs(literal) - 1] for literal in clause] for clause in data["clauses"]]
        for clause in data["clauses"]: rng.shuffle(clause)
        rng.shuffle(data["clauses"])
    elif domain == "algorithms":
        labels = rng.sample(range(data["nodes"]), data["nodes"])
        data["edges"] = [[labels[a], labels[b]] for a, b in data["edges"]]
        rng.shuffle(data["edges"])
    else:
        data = grid_transform(data, member + 1, reflection=bool(member))
        rng.shuffle(data["obstacles"])
    return data


def _prompt(domain, data, member):
    opening = "Solve this problem carefully using the stated constraints. "
    if domain == "math":
        names = ("A", "B", "C") if member == 0 else ("X", "Y", "Z")
        tracks = "; ".join(f"{name} starts at {track['initial']} and applies {track['steps']}" for name, track in zip(names, data["tracks"]))
        output = " + ".join(f"({track['weight']})*{name}" for name, track in zip(names, data["tracks"]))
        text = f"Use exact integer arithmetic. {tracks}. Apply each track's operations in listed order, then compute {output}. Put the integer on the final line: ANSWER: <integer>."
    elif domain == "logic":
        text = f"Decide satisfiability over variables 1..{data['variables']} for CNF {data['clauses']}. Each inner list is a disjunction, the outer list a conjunction, and negative integers negate variables. Put ANSWER: SAT or ANSWER: UNSAT on the final line."
    elif domain == "algorithms":
        text = f"Return the lexicographically smallest topological order of all nodes 0..{data['nodes']-1} for directed edges {data['edges']}. If a directed cycle prevents ordering, return IMPOSSIBLE. Final line: ANSWER: <JSON array of nodes> or ANSWER: IMPOSSIBLE."
    else:
        text = f"Grid width {data['width']}, height {data['height']}, coordinates x=0..{data['width']-1}, y=0..{data['height']-1}. Start {data['start']}, goal {data['goal']}, obstacles {data['obstacles']}. Use at most {data['max_steps']} moves. N=(0,-1), E=(1,0), S=(0,1), W=(-1,0). Stay inside the grid and do not enter obstacle cells. Final line: ANSWER: <JSON array of moves> or ANSWER: IMPOSSIBLE."
    return opening + text


def complexity(task):
    domain, data = task["domain"], task["data"]
    if domain == "math":
        _, values = _math_values(data)
        return {"tracks": len(data["tracks"]), "arithmetic_operations": sum(len(track["steps"]) for track in data["tracks"]),
                "dependency_depth": max(len(track["steps"]) for track in data["tracks"]) + 2,
                "maximum_intermediate_bits": max(abs(value).bit_length() for history in values for value in history),
                "maximum_start_digits": max(len(str(abs(track["initial"]))) for track in data["tracks"])}
    if domain == "logic":
        return {"variables": data["variables"], "clauses": len(data["clauses"]),
                "literals": sum(map(len, data["clauses"])), "exhaustive_assignment_bound": 1 << data["variables"]}
    if domain == "algorithms":
        return {"nodes": data["nodes"], "edges": len(data["edges"]),
                "maximum_total_degree": max(sum(node in edge for edge in data["edges"]) for node in range(data["nodes"]))}
    return {"width": data["width"], "height": data["height"], "cells": data["width"] * data["height"],
            "obstacles": len(data["obstacles"]), "free_cells": data["width"] * data["height"] - len(data["obstacles"]),
            "max_plan_steps": data["max_steps"]}


def reserve_holdout(path=PRIVATE_HOLDOUT_PATH):
    path = Path(path)
    if path.exists():
        seed = path.read_bytes()
        if len(seed) != 32: raise ValueError("Private holdout seed has invalid length")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        seed = secrets.token_bytes(32)
        with path.open("xb") as stream: stream.write(seed)
    return hashlib.sha256(b"pilot-v2-fresh-holdout-v1\0" + seed).hexdigest()


def build_development(seed=DEFAULT_DEVELOPMENT_SEED, legacy=None, holdout_commitment=None):
    if not isinstance(seed, str) or not seed or "holdout" in seed.casefold() or "confirmatory" in seed.casefold():
        raise ValueError("Only an explicit development seed is accepted")
    if not isinstance(holdout_commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", holdout_commitment):
        raise ValueError("Reserve an unopened holdout seed commitment first")
    legacy = load_legacy_inventory() if legacy is None else legacy
    tasks, used_exact, used_structural, rejected = [], set(), set(), []
    for domain in DOMAINS:
        for tier in TIERS:
            for root_index in range(2):
                root_id = VERSION + ":" + digest([seed, domain, tier, root_index])[:24]
                for nonce in range(256):
                    root_seed = digest([seed, domain, tier, root_index, nonce])
                    base = _base(domain, tier, root_index, random.Random(root_seed))
                    probe = {"domain": domain, "data": base}
                    exact, structural = exact_instance_key(probe), structural_fingerprint(probe)
                    if exact in legacy.exact or exact in used_exact or structural in legacy.structural or structural in used_structural:
                        rejected.append({"root_id": root_id, "nonce": nonce, "reason": "exact_or_conservative_structural_overlap"})
                        continue
                    members = []
                    for member in range(2):
                        data = _perturb(domain, base, random.Random(digest([root_seed, "perturb", member])), member)
                        task = {"task_id": root_id + ":v" + str(member), "root_id": root_id, "domain": domain,
                            "difficulty": tier, "tier": tier, "variant_index": member, "data": data,
                            "prompt": _prompt(domain, data, member), "generator_version": VERSION,
                            "generator_id": VERSION + ":" + domain, "seed": int(root_seed[:16], 16),
                            "root_nonce": nonce, "split": "development", "forced_split": "development",
                            "confirmatory_excluded": True, "exposure": "pilot_v2_development_only",
                            "perturbation_dependence": "same_latent_problem_conservative_shared_root"}
                        if normalized_prompt_key(task["prompt"]) in legacy.prompts:
                            raise ValueError("New prompt exactly overlaps normalized historical input")
                        task["instance_sha256"] = exact_instance_key(task)
                        task["structural_fingerprint"] = structural_fingerprint(task)
                        if task["instance_sha256"] in legacy.exact or task["instance_sha256"] in used_exact:
                            raise ValueError("Perturbed instance overlaps historical data or another root")
                        if task["structural_fingerprint"] != structural:
                            raise ValueError("Perturbation changed the declared invariant structure")
                        task["complexity"] = complexity(task)
                        certificate = reference_certificate(task)
                        if not verify_certificate(task, certificate): raise ValueError("Independent reference certificate check failed")
                        task["reference_certificate"], task["reference_certificate_sha256"] = certificate, digest(certificate)
                        task["task_digest"] = digest(task)
                        members.append(task)
                    if members[0]["prompt"] == members[1]["prompt"]:
                        raise ValueError("Perturbations produced identical prompts")
                    tasks.extend(members)
                    used_exact.update(task["instance_sha256"] for task in members)
                    used_structural.add(structural)
                    break
                else: raise ValueError("Finite development root generation exhausted")
    document = {"schema_version": 1, "generator_version": VERSION, "status": "development_only_not_confirmatory",
        "development_seed": seed, "tasks": tasks, "counts": {"tasks": len(tasks), "roots": len({t['root_id'] for t in tasks}),
            "by_domain": dict(Counter(t["domain"] for t in tasks)), "by_tier": dict(Counter(t["tier"] for t in tasks)),
            "reference_feasibility": dict(Counter(t["domain"] + ":" + ("IMPOSSIBLE" if solve_reference(t) == "IMPOSSIBLE" else
                "UNSAT" if solve_reference(t) == "UNSAT" else "feasible") for t in tasks))},
        "generation_rejections": rejected, "legacy_overlap_audit": legacy.report(),
        "difficulty_schedule": LIMITS, "output_budget_in_task_data": False,
        "holdout": {"status": "seed_committed_tasks_not_generated", "seed_commitment_sha256": holdout_commitment,
            "commitment_rule": "SHA256(domain separator pilot-v2-fresh-holdout-v1 NUL + 32 private random bytes)",
            "future_procedure": "After development calibration and protocol freeze, a separate versioned tool may consume the unopened reserved seed to draw fresh independent roots. No holdout tasks, prompts, labels or answers are generated by this module; no existing development root may enter that holdout."},
        "limitations": ["Difficulty schedules describe measured task size/work, not validated model difficulty or error rates.",
            "Two perturbations of one problem are dependent and must remain in one root in every analysis.",
            "Graph WL fingerprints are conservative invariants, not complete isomorphism or Boolean/algebraic equivalence tests.",
            "Historical rows without problem data cannot receive structural fingerprints; their prompt checks and missingness are explicit.",
            "CNF/grid feasibility is not balanced model correctness. No v1 model test labels or new model responses are used."]}
    document["corpus_sha256"] = digest(document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=PUBLIC_PATH)
    parser.add_argument("--seed", default=DEFAULT_DEVELOPMENT_SEED)
    parser.add_argument("--holdout-seed-file", type=Path, default=PRIVATE_HOLDOUT_PATH)
    args = parser.parse_args()
    if args.check:
        existing = json.loads(args.output.read_bytes())
        commitment = existing["holdout"]["seed_commitment_sha256"]
    else:
        commitment = reserve_holdout(args.holdout_seed_file)
    document = build_development(args.seed, holdout_commitment=commitment)
    payload = canonical(document) + b"\n"
    if args.check:
        if args.output.read_bytes() != payload: raise SystemExit("Development corpus differs from its deterministic builder")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists() and args.output.read_bytes() != payload:
            raise SystemExit("Refusing to overwrite a different published development corpus")
        args.output.write_bytes(payload)
    print(json.dumps({"path": str(args.output), "corpus_sha256": document["corpus_sha256"],
                      "counts": document["counts"], "holdout_status": document["holdout"]["status"], "paid_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
