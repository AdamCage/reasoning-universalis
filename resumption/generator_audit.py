"""Offline audits and independent strict reference grading for RU tasks.

Feasibility labels in the shortcut audit are properties of a problem instance;
they are deliberately not called model correctness labels. No API is used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import itertools
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_VERSION = "ru-reference-v1"
SUPPORTED_GENERATORS = frozenset((
    "d1-d4-development-v1", "stage3-generators-v2", "stage3-generators-v3",
    "stage3-generators-v4", "resumption-generators-v1",
))
DIFFICULTIES = ("easy", "medium", "hard")
MOVES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _integer(value: Any) -> int:
    if type(value) is not int:
        raise ValueError("Expected an integer, not bool or float")
    return value


def _check_task(task: dict) -> None:
    if task.get("generator_version") not in SUPPORTED_GENERATORS:
        raise ValueError("Unknown generator version")
    if task.get("domain") not in ("math", "logic", "algorithms", "planning"):
        raise ValueError("Unknown task domain")
    if not isinstance(task.get("data"), dict):
        raise ValueError("Missing task data")


def canonical_instance_key(task: dict) -> str:
    """Hash exact normalized problem data, ignoring provenance and family names.

    Clause order, literal order, edge order and obstacle order are irrelevant
    to the specified task and are normalized. This does not promise graph
    isomorphism or arbitrary algebraic equivalence detection.
    """
    _check_task(task)
    data = {key: value for key, value in task["data"].items() if key != "family"}
    if "clauses" in data:
        data["clauses"] = sorted({tuple(sorted(set(c))) for c in data["clauses"]})
    for key in ("edges", "obstacles"):
        if key in data:
            data[key] = sorted({tuple(item) for item in data[key]})
    return hashlib.sha256(_canonical({"domain": task["domain"], "data": data})).hexdigest()


def _arithmetic(start: int, steps: list) -> int:
    value = _integer(start)
    for operation, argument in steps:
        argument = _integer(argument)
        if operation == "add":
            value += argument
        elif operation == "sub":
            value -= argument
        elif operation == "mul":
            value *= argument
        else:
            raise ValueError("Unsupported arithmetic operation")
    return value


def _math_reference(task: dict) -> int:
    d = task["data"]
    if {"a", "b", "c", "power"} <= d.keys():
        value = 1
        for _ in range(_integer(d["power"])):
            value *= _integer(d["a"]) + _integer(d["b"])
        return value - _integer(d["c"])
    if "coefficients" in d:
        c = d["coefficients"]
        return (c["a"] + c["b"]) * c["c"] - (c["d"] + c["e"]) * c["f"]
    if "moduli" in d or "modulus_a" in d:
        moduli = d.get("moduli", [d.get("modulus_a"), d.get("modulus_b")])
        residues = d.get("residues", [d.get("residue_a"), d.get("residue_b")])
        if len(moduli) != len(residues) or not moduli:
            raise ValueError("Malformed congruences")
        if any(_integer(modulus) < 1 for modulus in moduli):
            raise ValueError("Invalid modulus")
        found = next((value for value in range(_integer(d["span"]))
                      if all(value % modulus == residue
                             for modulus, residue in zip(moduli, residues))), None)
        if found is None:
            raise ValueError("No congruence witness")
        return found + _integer(d.get("offset", 0))
    if "steps" in d:
        value = _arithmetic(d["start"], d["steps"])
    elif "left" in d and "right" in d:
        value = _arithmetic(d["left_start"], d["left"]) - _arithmetic(d["right_start"], d["right"])
    else:
        raise ValueError("Unsupported arithmetic schema")
    return value % _integer(d["modulus"]) if "modulus" in d else value


def _logic_reference(data: dict) -> str:
    n = _integer(data["variables"])
    if not 0 < n <= 20:
        raise ValueError("CNF reference bound exceeded")
    for clause in data["clauses"]:
        if any(not 1 <= abs(_integer(literal)) <= n for literal in clause):
            raise ValueError("Invalid CNF literal")
    for values in itertools.product((False, True), repeat=n):
        if all(any(values[abs(literal) - 1] == (literal > 0) for literal in clause)
               for clause in data["clauses"]):
            return "SAT"
    return "UNSAT"


def _topological_reference(data: dict) -> list[int] | str:
    # Independent exhaustive reference, rather than the generator's Kahn code.
    n = _integer(data["nodes"])
    if not 0 <= n <= 8:
        raise ValueError("Topological reference bound exceeded")
    for edge in data["edges"]:
        if len(edge) != 2 or any(not 0 <= _integer(v) < n for v in edge):
            raise ValueError("Invalid graph edge")
    for order in itertools.permutations(range(n)):
        positions = {node: index for index, node in enumerate(order)}
        if all(positions[source] < positions[target] for source, target in data["edges"]):
            return list(order)
    return "IMPOSSIBLE"


def _counter_step(value: int, action: str) -> int:
    if action == "add2":
        return value + 2
    if action == "sub1":
        return value - 1
    if action == "double":
        return value * 2
    raise ValueError("Unknown counter action")


def _counter_bound(task: dict) -> int | None:
    # The v1 prompt has no upper bound; v2 explicitly says 30; v3 says 25.
    if task["generator_version"] == "d1-d4-development-v1":
        return None
    return 30 if task.get("family") == "counter_walk" else 25


def _planning_reference(task: dict) -> list[str] | str:
    d = task["data"]
    limit = _integer(d["max_steps"])
    if limit < 0:
        return "IMPOSSIBLE"
    if "width" in d:
        start, goal = tuple(d["start"]), tuple(d["goal"])
        blocked = {tuple(item) for item in d["obstacles"]}
        queue = deque([(start, [])])
        seen = {start}
        while queue:
            cell, actions = queue.popleft()
            if cell == goal:
                return actions
            if len(actions) >= limit:
                continue
            for action, (dx, dy) in MOVES.items():
                nxt = cell[0] + dx, cell[1] + dy
                if (0 <= nxt[0] < d["width"] and 0 <= nxt[1] < d["height"]
                        and nxt not in blocked and nxt not in seen):
                    seen.add(nxt)
                    queue.append((nxt, actions + [action]))
    else:
        start = d.get("start", d.get("initial"))
        target = _integer(d["target"])
        queue = deque([(_integer(start), [])])
        seen = {start}
        bound = _counter_bound(task)
        while queue:
            value, actions = queue.popleft()
            if value == target:
                return actions
            if len(actions) >= limit:
                continue
            for action in d["operations"]:
                nxt = _counter_step(value, action)
                if nxt < 0 or (bound is not None and nxt > bound) or nxt in seen:
                    continue
                # In v1 both actions are monotone; larger values cannot return.
                if bound is None and nxt > target:
                    continue
                seen.add(nxt)
                queue.append((nxt, actions + [action]))
    return "IMPOSSIBLE"


def solve_reference(task: dict) -> int | str | list:
    """Return an exact answer or an independently searched planning witness."""
    _check_task(task)
    if task["domain"] == "math":
        return _math_reference(task)
    if task["domain"] == "logic":
        return _logic_reference(task["data"])
    if task["domain"] == "algorithms":
        return _topological_reference(task["data"])
    return _planning_reference(task)


def _plan_valid(task: dict, actions: list) -> bool:
    d = task["data"]
    if type(actions) is not list or any(type(action) is not str for action in actions):
        return False
    if len(actions) > d["max_steps"]:
        return False
    if "width" in d:
        cell = tuple(d["start"])
        blocked = {tuple(item) for item in d["obstacles"]}
        for action in actions:
            if action not in MOVES:
                return False
            dx, dy = MOVES[action]
            cell = cell[0] + dx, cell[1] + dy
            if not (0 <= cell[0] < d["width"] and 0 <= cell[1] < d["height"]) or cell in blocked:
                return False
        return cell == tuple(d["goal"])
    value = d.get("start", d.get("initial"))
    bound = _counter_bound(task)
    for action in actions:
        if action not in d["operations"]:
            return False
        value = _counter_step(value, action)
        if value < 0 or (bound is not None and value > bound):
            return False
    return value == d["target"]


def verify_answer(task: dict, text: str) -> dict:
    """Strict final ANSWER line; planning is graded by full bounded simulation.

    Unknown versions and malformed problem data are programmer errors, raised
    before answer parsing, rather than silently turned into model failures.
    """
    expected = solve_reference(task)
    result = {"verifier_id": VERIFIER_VERSION + ":" + task["domain"],
              "verifier_version": VERIFIER_VERSION, "grading_uncertainty": False}
    try:
        if type(text) is not str:
            raise ValueError("Answer must be text")
        marker = text.strip().splitlines()[-1]
        if not marker.startswith("ANSWER: "):
            raise ValueError("Missing final answer marker")
        value = marker[len("ANSWER: "):].strip()
        if task["domain"] == "math":
            if len(value) > 1000 or re.fullmatch(r"[+-]?[0-9]+", value) is None:
                raise ValueError("Expected integer text")
            correct = int(value) == expected
        elif task["domain"] == "logic":
            if value not in ("SAT", "UNSAT"):
                raise ValueError("Expected SAT or UNSAT")
            correct = value == expected
        elif value == "IMPOSSIBLE":
            correct = expected == "IMPOSSIBLE"
        else:
            parsed = json.loads(value)
            if type(parsed) is not list:
                raise ValueError("Expected JSON array")
            if task["domain"] == "algorithms":
                if any(type(v) is not int for v in parsed):
                    raise ValueError("Node identifiers must be integers")
                correct = parsed == expected
            else:
                if any(type(v) is not str for v in parsed):
                    raise ValueError("Actions must be strings")
                correct = _plan_valid(task, parsed)
        result["verdict"] = "correct" if correct else "incorrect"
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        result.update(verdict="unparseable", grading_uncertainty=True)
    return result


def witness_text(task: dict) -> str:
    answer = solve_reference(task)
    return "ANSWER: " + (answer if type(answer) is str else json.dumps(answer))


def _version_modules():
    from stage2 import datasets
    from stage3 import generators_v2, generators_v3, generators_v4
    return {"v1": datasets, "v2": generators_v2, "v3": generators_v3, "v4": generators_v4}


def _published_tasks(version: str) -> list[dict]:
    suffix = "" if version == "v1" else "_" + version.upper()
    return json.loads((ROOT / "design" / ("PILOT_SECTION_5_5_ROSTER" + suffix + ".json")).read_bytes())["tasks"]


def extended_tasks(version: str, seeds_per_cell: int = 48) -> list[dict]:
    module = _version_modules()[version]
    if version == "v1":
        return [module.generate(domain, seed, difficulty)
                for domain in module.DOMAINS for difficulty in DIFFICULTIES
                for seed in range(seeds_per_cell)]
    return [module.generate(domain, family, difficulty, seed)
            for domain, families in module.FAMILIES.items() for family in families
            for difficulty in DIFFICULTIES for seed in range(seeds_per_cell)]


def _fast_answer(task: dict):
    module = next(module for module in _version_modules().values()
                  if module.VERSION == task["generator_version"])
    return module.solve(task)


def feasibility(task: dict, answer=None) -> int:
    """Binary instance feasibility; excludes math, never a model outcome."""
    if task["domain"] == "math":
        raise ValueError("Math exact answers are not binary feasibility labels")
    answer = _fast_answer(task) if answer is None else answer
    return int(answer != "UNSAT" and answer != "IMPOSSIBLE")


def _components(tasks: list[dict], include_design_pairs: bool = False) -> list[str]:
    """Connected root/instance groups, optionally also dependent target pairs."""
    parent = list(range(len(tasks)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    seen = {}
    for i, task in enumerate(tasks):
        keys = [("declared", task["root_id"]), ("instance", canonical_instance_key(task))]
        if include_design_pairs and task["generator_version"] in ("stage3-generators-v3", "stage3-generators-v4"):
            keys.append(("design_pair", task["generator_version"], task["domain"],
                         task.get("family"), task["difficulty"], task["seed"] // 2))
        for key in keys:
            if key in seen:
                union(i, seen[key])
            else:
                seen[key] = i
    return [str(find(i)) for i in range(len(tasks))]


def duplicate_audit(tasks: list[dict]) -> dict:
    prompts = defaultdict(list)
    instances = defaultdict(list)
    for task in tasks:
        prompts[task["prompt"]].append(task)
        instances[canonical_instance_key(task)].append(task)
    # A conventional task-id-hash partition is reproduced to show the risk of
    # treating fresh seed/root identifiers as sufficient independence.
    def split(task):
        return int(hashlib.sha256(task["task_id"].encode()).hexdigest()[:8], 16) % 5

    crossing = [rows for rows in instances.values() if len({split(row) for row in rows}) > 1]
    groups = _components(tasks)
    examples = [[row["task_id"] for row in rows[:5]] for rows in instances.values() if len(rows) > 1][:8]
    return {
        "task_count": len(tasks), "declared_root_count": len({t["root_id"] for t in tasks}),
        "unique_prompt_count": len(prompts),
        "duplicate_prompt_excess": sum(len(rows) - 1 for rows in prompts.values()),
        "unique_canonical_instance_count": len(instances),
        "duplicate_canonical_instance_excess": sum(len(rows) - 1 for rows in instances.values()),
        "conservative_component_count": len(set(groups)),
        "canonical_groups_crossing_task_id_hash_folds": len(crossing),
        "rows_in_crossing_canonical_groups": sum(map(len, crossing)),
        "canonical_duplicate_examples": examples,
        "scope": "Exact normalized data; not full graph isomorphism or algebraic equivalence",
    }


def _surface(task: dict) -> list[float]:
    text, d = task["prompt"], task["data"]
    return [len(text), len(text.encode("utf-8")), len(text.split()), text.count("-"),
            text.count("["), text.count(","), sum(c.isdigit() for c in text),
            len(d.get("clauses", [])), len(d.get("edges", [])), len(d.get("obstacles", [])),
            d.get("variables", 0), d.get("nodes", 0), d.get("width", 0), d.get("height", 0),
            d.get("max_steps", 0)]


def heldout_shortcuts(tasks: list[dict]) -> dict:
    """Fixed descriptive baselines; every fitted parameter uses train folds only."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.tree import DecisionTreeClassifier

    result = {}
    for domain in ("logic", "algorithms", "planning"):
        rows = [task for task in tasks if task["domain"] == domain]
        y = np.array([feasibility(task) for task in rows])
        groups = np.array(_components(rows, include_design_pairs=True))
        X = np.array([_surface(task) for task in rows], dtype=float)
        folds = min(5, len(set(groups)))
        if folds < 2:
            result[domain] = {"status": "insufficient_independent_groups", "groups": int(len(set(groups)))}
            continue
        model_names = ("training_majority", "family_and_level_lookup", "seed_parity_lookup",
                       "prompt_length_stump", "structure_count_stump", "surface_tree_depth3",
                       "prompt_char_ngram_logistic")
        predictions = {name: np.zeros(len(y), dtype=float) for name in model_names}
        fold_sizes = []
        for train, test in GroupKFold(n_splits=folds).split(X, y, groups):
            assert not (set(groups[train]) & set(groups[test]))
            majority = Counter(y[train]).most_common(1)[0][0]
            predictions["training_majority"][test] = float(np.mean(y[train]))
            for name, key_fn in (
                ("family_and_level_lookup", lambda t: (t.get("family", t["generator_id"]), t["difficulty"])),
                ("seed_parity_lookup", lambda t: t["seed"] % 2),
            ):
                fitted = defaultdict(list)
                for i in train:
                    fitted[key_fn(rows[i])].append(int(y[i]))
                for i in test:
                    values = fitted.get(key_fn(rows[i]), list(y[train]))
                    predictions[name][i] = sum(values) / len(values)
            structure_column = 7 if domain == "logic" else 8 if domain == "algorithms" else 14
            for name, indices, depth in (
                ("prompt_length_stump", [0], 1),
                ("structure_count_stump", [structure_column], 1),
                ("surface_tree_depth3", list(range(X.shape[1])), 3),
            ):
                model = DecisionTreeClassifier(max_depth=depth, random_state=20261108)
                model.fit(X[train][:, indices], y[train])
                p = model.predict_proba(X[test][:, indices])
                predictions[name][test] = p[:, list(model.classes_).index(1)] if 1 in model.classes_ else 0
            if len(set(y[train])) == 1:
                predictions["prompt_char_ngram_logistic"][test] = majority
            else:
                vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5),
                                             min_df=2, max_features=6000, lowercase=False)
                encoded = vectorizer.fit_transform([rows[i]["prompt"] for i in train])
                model = LogisticRegression(C=1.0, max_iter=400, solver="liblinear", random_state=20261108)
                model.fit(encoded, y[train])
                predictions["prompt_char_ngram_logistic"][test] = model.predict_proba(
                    vectorizer.transform([rows[i]["prompt"] for i in test]))[:, 1]
            fold_sizes.append({"train_tasks": len(train), "test_tasks": len(test),
                               "train_groups": len(set(groups[train])), "test_groups": len(set(groups[test]))})
        scores = {}
        for name, probabilities in predictions.items():
            guessed = (probabilities > 0.5).astype(int)
            # Deterministic tie rule is negative; no target labels are read.
            scores[name] = {"accuracy": float(accuracy_score(y, guessed)),
                           "balanced_accuracy": float(balanced_accuracy_score(y, guessed)) if len(set(y)) > 1 else None,
                           "roc_auc": float(roc_auc_score(y, probabilities)) if len(set(y)) > 1 else None}
        result[domain] = {"tasks": len(rows), "groups": len(set(groups)),
                          "class_counts": {str(int(k)): int(v) for k, v in Counter(y).items()},
                          "folds": fold_sizes, "scores": scores}
    return {"target": "instance_feasibility_not_model_correctness", "fit_scope": "training_folds_only",
            "group_rule": "connected_declared_root_plus_normalized_instance_plus_v3_v4_target_seed_pairs",
            "seed": 20261108, "metrics_status": "descriptive_offline_audit_not_confirmatory",
            "one_class_domain_auc_and_balanced_accuracy": "null", "domains": result}


def reference_audit(tasks: list[dict]) -> dict:
    disagreements, witnesses_rejected, wrong_marker_accepted = [], [], []
    by_domain = Counter()
    for task in tasks:
        old = _fast_answer(task)
        new = solve_reference(task)
        equivalent = (feasibility(task, old) == feasibility(task, new)
                      if task["domain"] == "planning" else old == new)
        if not equivalent:
            disagreements.append({"task_id": task["task_id"], "old": old, "reference": new})
        text = "ANSWER: " + (new if type(new) is str else json.dumps(new))
        verdict = verify_answer(task, text)["verdict"]
        by_domain[task["domain"]] += 1
        if verdict != "correct":
            witnesses_rejected.append({"task_id": task["task_id"], "verdict": verdict})
        if verify_answer(task, "ANSWER: garbage")["verdict"] == "correct":
            wrong_marker_accepted.append(task["task_id"])
    return {"tasks_checked": len(tasks), "by_domain": dict(by_domain),
            "old_solver_reference_disagreements": disagreements,
            "reference_witnesses_rejected": witnesses_rejected,
            "garbage_answers_accepted": wrong_marker_accepted}


def v4_legacy_verifier_audit(tasks: list[dict]) -> dict:
    from stage3.generators_v2 import verify as verify_v2
    from stage3.generators_v3 import verify as verify_v3
    result = {}
    for label, verifier in (("v2_verify_reused", verify_v2), ("v3_verify_reused", verify_v3)):
        counts = defaultdict(Counter)
        examples = []
        for task in tasks:
            text = witness_text(task)
            verdict = verifier(task, text)["verdict"]
            counts[task["domain"]][verdict] += 1
            if verdict != "correct" and len(examples) < 8:
                examples.append({"task_id": task["task_id"], "verdict": verdict})
        result[label] = {"independently_valid_witness_verdicts_by_domain":
                         {d: dict(c) for d, c in counts.items()}, "examples": examples}
    return {"v4_has_own_verify_function": False,
            "interpretation": "Compatibility test of hypothetical reuse; no assertion that an actual paid run used these functions",
            "results": result}


def math_source_audit(tasks: list[dict]) -> dict:
    rows = [t for t in tasks if t["domain"] == "math"]
    residue = [t for t in rows if t.get("family") == "fixed_residues"]
    fold = [t for t in rows if t.get("family") == "fixed_fold"]
    return {
        "math_tasks_omitted_by_historical_surface_audit": len(rows),
        "fixed_residues_tasks": len(residue),
        "fixed_residues_answer_equals_seed_plus_one_mod_span": sum(
            solve_reference(t) == (t["seed"] + 1) % t["data"]["span"] for t in residue),
        "fixed_fold_tasks": len(fold), "fixed_fold_unique_prompts": len({t["prompt"] for t in fold}),
        "scope": "Seed/source-code access shortcut, not a prompt-visible seed leak; report separately from model-visible baselines",
    }


def run_audit(output: Path, seeds_per_cell: int = 48) -> dict:
    import gzip
    import importlib.metadata
    import platform
    from stage3.baseline_audit import surface_audit

    if seeds_per_cell < 8:
        raise ValueError("Use at least eight seeds per family/difficulty cell")
    output.mkdir(parents=True, exist_ok=True)
    summary = {"schema_version": 1, "status": "completed_offline_exploratory_generator_audit",
               "paid_calls": 0, "E0": "not_passed", "scientific_hypotheses_evaluated": [],
               "seeds_per_cell": seeds_per_cell, "seed_range": [0, seeds_per_cell - 1],
               "source_versions_preserved": True,
               "environment": {"python": platform.python_version(),
                               **{name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn")}},
               "historical_surface_gate_limitations": [
                   "fit and score on same data (resubstitution), not heldout prediction",
                   "math tasks omitted from family/parity/length/structure feasibility scores",
                   "reported parity/length/structure score is maximum over domains",
                   "binary instance feasibility is not a generated answer correctness label"],
               "versions": {}}
    manifest_rows = []
    for version in ("v1", "v2", "v3", "v4"):
        print("Auditing " + version, flush=True)
        published = _published_tasks(version)
        extended = extended_tasks(version, seeds_per_cell)
        result = {"published": {"duplicates": duplicate_audit(published),
                                "independent_reference": reference_audit(published),
                                "heldout_shortcuts": heldout_shortcuts(published)},
                  "extended": {"duplicates": duplicate_audit(extended),
                               "heldout_shortcuts": heldout_shortcuts(extended)}}
        if version != "v1":
            result["published"]["historical_resubstitution_gate"] = surface_audit(published)
        if version == "v4":
            result["published"]["legacy_verifier_compatibility"] = v4_legacy_verifier_audit(published)
            result["published"]["math_source_shortcuts"] = math_source_audit(published)
            result["extended"]["math_source_shortcuts"] = math_source_audit(extended)
        summary["versions"][version] = result
        for cohort, tasks in (("published", published), ("extended", extended)):
            for task in tasks:
                manifest_rows.append({"version": version, "cohort": cohort,
                                      "task_id": task["task_id"], "root_id": task["root_id"],
                                      "domain": task["domain"], "family": task.get("family"),
                                      "difficulty": task["difficulty"], "seed": task["seed"],
                                      "prompt_sha256": hashlib.sha256(task["prompt"].encode()).hexdigest(),
                                      "canonical_instance_sha256": canonical_instance_key(task),
                                      "answer": _fast_answer(task)})
    raw = b"".join(_canonical(row) + b"\n" for row in manifest_rows)
    manifest = output / "instances.jsonl.gz"
    manifest.write_bytes(gzip.compress(raw, mtime=0))
    inputs = [ROOT / "stage2" / "datasets.py", Path(__file__)]
    inputs += [ROOT / "stage3" / ("generators_" + v + ".py") for v in ("v2", "v3", "v4")]
    inputs += [ROOT / "stage3" / "baseline_audit.py"]
    inputs += [ROOT / "design" / ("PILOT_SECTION_5_5_ROSTER" + suffix + ".json")
               for suffix in ("", "_V2", "_V3", "_V4")]
    summary["input_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    summary["instance_manifest"] = {"path": manifest.name, "rows": len(manifest_rows),
                                    "compressed_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                                    "uncompressed_sha256": hashlib.sha256(raw).hexdigest()}
    (output / "summary.json").write_bytes(json.dumps(summary, ensure_ascii=False, sort_keys=True,
                                                     indent=2, allow_nan=False).encode() + b"\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "resumption-2026-11-08" / "generator_audit")
    parser.add_argument("--seeds-per-cell", type=int, default=48)
    args = parser.parse_args()
    report = run_audit(args.out, args.seeds_per_cell)
    print(json.dumps({"status": report["status"], "out": str(args.out),
                      "manifest_rows": report["instance_manifest"]["rows"]}))


if __name__ == "__main__":
    main()
