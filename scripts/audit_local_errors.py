"""Postcollection answer audit independent of the frozen task verifier.

Uses direct truth-table enumeration/resolution, coordinate simulation/BFS, and
bounded residue enumeration. Never rewrites correctness labels or runs models.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import itertools
import json
from pathlib import Path
import re


MOVES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def last_line(answer):
    return next((line.strip() for line in reversed(answer.splitlines()) if line.strip()), "")


def resolution_proof(clauses):
    nodes = [{"id": index + 1, "clause": sorted(set(clause)), "source_clause": index + 1}
             for index, clause in enumerate(clauses)]
    known = {tuple(node["clause"]): node["id"] for node in reversed(nodes)}
    while True:
        candidates = []
        for first, second in itertools.combinations(nodes, 2):
            left, right = set(first["clause"]), set(second["clause"])
            for literal in sorted(left):
                if -literal not in right:
                    continue
                resolvent = (left - {literal}) | (right - {-literal})
                if any(-item in resolvent for item in resolvent):
                    continue
                result = tuple(sorted(resolvent))
                if result not in known:
                    candidates.append((len(result), first["id"], second["id"], abs(literal), result))
        if not candidates:
            return None
        _, first, second, pivot, result = min(candidates)
        node = {"id": len(nodes) + 1, "parents": [first, second], "pivot_variable": pivot,
                "clause": list(result)}
        # Check the selected resolution step directly before accepting it.
        left, right = set(nodes[first - 1]["clause"]), set(nodes[second - 1]["clause"])
        expected = ((left - {pivot}) | (right - {-pivot})) if pivot in left and -pivot in right \
            else ((left - {-pivot}) | (right - {pivot}))
        assert expected == set(result)
        nodes.append(node)
        known[result] = node["id"]
        if not result:
            needed = set()
            def visit(identity):
                if identity in needed:
                    return
                needed.add(identity)
                for parent in nodes[identity - 1].get("parents", []):
                    visit(parent)
            visit(node["id"])
            return [item for item in nodes if item["id"] in needed]


def audit_logic(data, answer):
    variables, clauses = data["variables"], data["clauses"]
    satisfied = []
    first_violations = Counter()
    for assignment in itertools.product((False, True), repeat=variables):
        bad = next((index + 1 for index, clause in enumerate(clauses)
                    if not any(assignment[abs(literal) - 1] == (literal > 0) for literal in clause)), None)
        if bad is None:
            satisfied.append(list(assignment))
        else:
            first_violations[bad] += 1
    expected = "SAT" if satisfied else "UNSAT"
    match = re.fullmatch(r"ANSWER:\s*(SAT|UNSAT)", last_line(answer))
    assert match is not None
    proposed = match.group(1)
    proof = resolution_proof(clauses) if not satisfied else None
    assert satisfied or (proof and proof[-1]["clause"] == [])
    return {"method": "direct_truth_table_and_checked_binary_resolution",
            "variables": variables, "clauses": clauses, "assignments_checked": 2 ** variables,
            "satisfying_assignments": len(satisfied), "satisfying_witness": satisfied[0] if satisfied else None,
            "first_violated_clause_histogram": dict(sorted(first_violations.items())),
            "reference_answer": expected, "model_answer": proposed,
            "independently_incorrect": proposed != expected, "resolution_certificate": proof}


def simulate(data, moves):
    position = tuple(data["start"])
    obstacles = {tuple(point) for point in data["obstacles"]}
    first_failure = None
    for step, move in enumerate(moves, 1):
        if move not in MOVES:
            first_failure = {"step": step, "move": move, "constraint": "unknown move"}
            break
        dx, dy = MOVES[move]
        destination = position[0] + dx, position[1] + dy
        if not (0 <= destination[0] < data["width"] and 0 <= destination[1] < data["height"]):
            first_failure = {"step": step, "move": move, "from": list(position), "to": list(destination),
                             "constraint": "coordinate outside grid", "width": data["width"], "height": data["height"]}
            break
        if destination in obstacles:
            first_failure = {"step": step, "move": move, "from": list(position), "to": list(destination),
                             "constraint": "obstacle collision"}
            break
        position = destination
    if first_failure is None and len(moves) > data["max_steps"]:
        first_failure = {"constraint": "move budget exceeded", "steps": len(moves), "max_steps": data["max_steps"]}
    if first_failure is None and position != tuple(data["goal"]):
        first_failure = {"constraint": "goal not reached", "position": list(position), "goal": data["goal"]}
    return {"valid": first_failure is None, "first_violated_constraint": first_failure,
            "last_valid_position": list(position), "moves_supplied": len(moves)}


def bfs_witness(data):
    start, goal = tuple(data["start"]), tuple(data["goal"])
    obstacles = {tuple(point) for point in data["obstacles"]}
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        position, path = queue.popleft()
        if position == goal:
            assert simulate(data, path)["valid"]
            return path
        if len(path) >= data["max_steps"]:
            continue
        for move, (dx, dy) in MOVES.items():
            point = position[0] + dx, position[1] + dy
            if (0 <= point[0] < data["width"] and 0 <= point[1] < data["height"] and
                    point not in obstacles and point not in seen):
                seen.add(point)
                queue.append((point, path + [move]))
    return None


def audit_planning(data, answer):
    match = re.fullmatch(r"ANSWER:\s*(.+)", last_line(answer))
    assert match is not None
    proposed = json.loads(match.group(1))
    assert isinstance(proposed, list) and all(isinstance(move, str) for move in proposed)
    simulation = simulate(data, proposed)
    witness = bfs_witness(data)
    return {"method": "independent_coordinate_simulation_and_bounded_breadth_first_search",
            "task_data": data, "model_moves": proposed, "simulation": simulation,
            "valid_reference_witness": witness, "reference_witness_steps": len(witness) if witness is not None else None,
            "feasible_within_budget": witness is not None, "independently_incorrect": not simulation["valid"]}


def audit_format(data, answer):
    terminal = last_line(answer)
    strict = re.fullmatch(r"ANSWER:\s*([+-]?\d+)", terminal)
    assert strict is None
    # Diagnostic only: the frozen scorer and correctness labels remain intact.
    normalized = terminal.replace("**", "")
    match = re.fullmatch(r"ANSWER:\s*([+-]?\d+)", normalized)
    candidates = [value for value in range(data["span"])
                  if all(value % modulus == residue for modulus, residue in zip(data["moduli"], data["residues"]))]
    value = int(match.group(1)) if match else None
    return {"method": "strict_terminal_format_check_and_bounded_residue_enumeration",
            "terminal_line": terminal, "strict_format_match": False,
            "format_failure": "Markdown emphasis violates the required unadorned ANSWER line",
            "diagnostic_only_removed_markdown_line": normalized,
            "diagnostic_numeric_candidate": value, "task_data": data,
            "reference_values_in_required_range": candidates,
            "candidate_satisfies_arithmetic": value in candidates,
            "frozen_correctness_label_unchanged": None,
            "limitation": "Posthoc format normalization is diagnostic only and never enters primary correctness or prediction metrics."}


def audit(results, corpus):
    tasks = {task["task_id"]: task for task in corpus["tasks"]}
    cases = []
    for row in sorted(results["records"], key=lambda value: value["trace_id"]):
        incorrect = row.get("correct") is False
        unparseable = row.get("status") == "completed" and row.get("grading", {}).get("verdict") == "unparseable"
        if not incorrect and not unparseable:
            continue
        task = tasks[row["task_id"]]
        assert task["root_id"] == row["root_id"] and task["domain"] == row["domain"]
        if unparseable:
            assert row.get("correct") is None and task["domain"] == "math"
            diagnostic = audit_format(task["data"], row["answer"])
        elif task["domain"] == "logic":
            diagnostic = audit_logic(task["data"], row["answer"])
        elif task["domain"] == "planning":
            diagnostic = audit_planning(task["data"], row["answer"])
        else:
            raise ValueError("This recorded-error audit has no independent method for the unexpected domain")
        if incorrect:
            assert diagnostic["independently_incorrect"] is True
        cases.append({**{field: row.get(field) for field in ("trace_id", "task_id", "root_id", "model", "sample_index", "split", "domain", "correct", "finish_reason")},
                      "recorded_verdict": row["grading"]["verdict"],
                      "answer_sha256": hashlib.sha256(row["answer"].encode("utf-8")).hexdigest(),
                      "exact_terminal_answer": last_line(row["answer"]), "diagnostic": diagnostic})
    return {"audit_version": "local-answer-errors-v1", "scope": "postcollection_diagnostic_not_primary_selection_or_human_review",
            "primary_labels_changed": False, "E0": "not_passed", "scientific_validity": "not_assessed",
            "counts": dict(Counter(case["recorded_verdict"] for case in cases)), "cases": cases}


def report(document, command):
    lines = ["# Независимая программная проверка ошибок локального пилота", "",
             "Это диагностика после сбора: проверены все записи с `correct=false` и завершённые записи с `verdict=unparseable`. "
             "Проверка использует отдельный код без импорта основного `verify_answer`. Исходные labels, статистические метрики и состав первичной выборки сохранены. "
             "Проверка ИИ не является независимым человеческим G3; E0 не пройден.", "",
             f"Проверено: {document['counts'].get('incorrect', 0)} неверных и {document['counts'].get('unparseable', 0)} неразбираемых ответов. "
             "Все проверенные неверные ответы нарушают условие задачи; для этих случаев ошибка scorer не обнаружена.", "",
             "## Воспроизведение", "", "```powershell", command, "```", "",
             "Все вычисления выполняются локально и без API. JSON содержит точные task data и проверяемые сертификаты; hashes входов связывают отчёт с сохранённым состоянием."]
    for index, case in enumerate(document["cases"], 1):
        diagnostic = case["diagnostic"]
        lines += ["", f"## Случай {index}", "", f"Модель: `{case['model']}`; split: `{case['split']}`; sample: `{case['sample_index']}`.", "",
                  f"Trace: `{case['trace_id']}`.", "", f"Task: `{case['task_id']}`.", "", f"Root: `{case['root_id']}`.", "",
                  f"Записанный verdict: `{case['recorded_verdict']}`; исходный `correct={json.dumps(case['correct'])}`.", "",
                  "Последняя непустая строка ответа:", "", "```text", case["exact_terminal_answer"], "```", ""]
        if case["recorded_verdict"] == "unparseable":
            lines += ["Markdown emphasis мешает точному формату `ANSWER: <integer>`. Это завершённая генерация с нарушением формата ответа.", "",
                      f"Только для диагностики удаление `**` даёт число `{diagnostic['diagnostic_numeric_candidate']}`. "
                      f"Перебор диапазона `0 <= x < {diagnostic['task_data']['span']}` даёт решения `{diagnostic['reference_values_in_required_range']}`; "
                      f"остатки: `{diagnostic['task_data']['residues']}` по модулям `{diagnostic['task_data']['moduli']}`.", "",
                      ("Числовое содержание удовлетворяет арифметике." if diagnostic["candidate_satisfies_arithmetic"]
                       else "Диагностически извлечённое число не удовлетворяет арифметике."), "",
                      "Первичный label остаётся `null`, и запись не добавляется задним числом к gradeable выборке."]
        elif case["domain"] == "planning":
            failure = diagnostic["simulation"]["first_violated_constraint"]
            lines += ["Прямая симуляция координат обнаруживает первое нарушение:", "", "```json",
                      json.dumps(failure, ensure_ascii=False, sort_keys=True), "```", "",
                      f"Независимый поиск в ширину нашёл допустимый путь из {diagnostic['reference_witness_steps']} ходов при лимите "
                      f"{diagnostic['task_data']['max_steps']}:", "", "```json",
                      json.dumps(diagnostic["valid_reference_witness"]), "```", "",
                      "Этот путь повторно проверен отдельной симуляцией. Существование допустимого решения не делает предложенный моделью путь корректным."]
        else:
            lines += [f"Перебраны все `{diagnostic['assignments_checked']}` присваивания {diagnostic['variables']} переменным; "
                      f"удовлетворяющих присваиваний `{diagnostic['satisfying_assignments']}`. Ответ модели `{diagnostic['model_answer']}` противоречит этому результату.", "",
                      "Дополнительно каждый шаг следующего resolution-сертификата проверен символьным удалением противоположных литералов. "
                      "`C` с исходным номером обозначает дизъюнкт из сохранённого CNF; пустой дизъюнкт завершает доказательство UNSAT.", "", "```text"]
            for node in diagnostic["resolution_certificate"]:
                if "source_clause" in node:
                    lines.append(f"C{node['id']} = {node['clause']} (исходный дизъюнкт {node['source_clause']})")
                else:
                    lines.append(f"C{node['id']} = resolve(C{node['parents'][0]}, C{node['parents'][1]}; x{node['pivot_variable']}) = {node['clause']}")
            lines += ["```"]
    lines += ["", "## Границы вывода", "",
              "Это проверка конкретных ответов и конкретных ограничений задач. Она не устанавливает внутреннюю причину ошибки, верность CoT, overthinking или истинность H1–H7. "
              "Проверка не меняет frozen scorer и не исправляет формат ответов для первичного анализа. "
              "Наличие решений задач отделено от фактической корректности ответа каждой генерации."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    results_bytes, tasks_bytes = args.results.read_bytes(), args.tasks.read_bytes()
    document = audit(json.loads(results_bytes), json.loads(tasks_bytes))
    if args.results.read_bytes() != results_bytes or args.tasks.read_bytes() != tasks_bytes:
        raise ValueError("Audit inputs changed during the calculation")
    document["inputs"] = {"results_sha256": hashlib.sha256(results_bytes).hexdigest(),
                          "tasks_sha256": hashlib.sha256(tasks_bytes).hexdigest(),
                          "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    command = (f".venv/Scripts/python.exe -X utf8 scripts/audit_local_errors.py --results {args.results.as_posix()} "
               f"--tasks {args.tasks.as_posix()} --output {args.output.as_posix()} --report {args.report.as_posix()}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(document) + b"\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report(document, command), encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "report": str(args.report), "counts": document["counts"], "labels_changed": False}))


if __name__ == "__main__":
    main()
