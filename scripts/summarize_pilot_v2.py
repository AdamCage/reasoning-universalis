"""Summarize a closed pilot-v2 roster without fitting or collecting anything.

Inputs must be explicit finished snapshots. The frozen statistics module is
replayed exactly; this reporting script never chooses new tasks or schedules.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from pilot_v2.statistical_design import canonical, summarize_support, validate_probe_layout


VERSION = "pilot-v2-result-report-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def amount(value):
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, "Non-finite or negative financial amount")
    return result


def evidence(path, data):
    path = Path(path).resolve()
    relative = path.relative_to(PROJECT).as_posix() if path.is_relative_to(PROJECT) else path.name
    return {"path": relative, "sha256": sha(data)}


def ledger_totals(rows):
    committed, reported, retained, unknown = (Decimal(0) for _ in range(4))
    states = Counter()
    for row in rows:
        value = amount(row["charged_or_reserved_rub"])
        committed += value
        states[row["state"]] += 1
        if row.get("reported_cost_rub") is None:
            unknown += value
        else:
            cost = amount(row["reported_cost_rub"])
            require(cost <= value, "A reported cost exceeds its retained ledger obligation")
            reported += cost
            retained += value - cost
    require(committed == reported + retained + unknown, "Budget decomposition failed")
    return {"rows": len(rows), "states": dict(sorted(states.items())),
            "charged_or_reserved_rub": str(committed), "reported_cost_rub": str(reported),
            "retained_reservation_above_reported_cost_rub": str(retained),
            "commitments_without_reported_cost_rub": str(unknown)}


def budget_result(protocol, launch, current, launch_bytes, current_bytes, results):
    parent, policy = protocol["parent"], protocol["budget"]
    require(sha(launch_bytes) == parent["launch_ledger_sha256"] and len(launch) == parent["launch_ledger_rows"],
            "Launch ledger does not match the frozen protocol")
    require(current[:len(launch)] == launch, "Previously retained ledger rows changed or disappeared")
    old, total, new = ledger_totals(launch), ledger_totals(current), ledger_totals(current[len(launch):])
    require(amount(old["charged_or_reserved_rub"]) == amount(parent["launch_charged_or_reserved_rub"]),
            "Launch obligations differ from the protocol")
    require(amount(results["charged_or_reserved_rub"]) == amount(total["charged_or_reserved_rub"]),
            "Results and current shared ledger are not a synchronized closed snapshot")
    purposes = defaultdict(list)
    for row in current[len(launch):]:
        purposes[row["purpose"]].append(row)
    cap, stage_ceiling = amount(policy["cap_total_rub"]), amount(policy["absolute_stage_ceiling_rub"])
    return {"schema_version": 1, "protocol_id": protocol["protocol_id"],
            "launch_ledger_sha256": sha(launch_bytes), "current_ledger_sha256": sha(current_bytes),
            "launch_prefix_preserved": True, "launch": old, "current": total, "since_launch": new,
            "since_launch_by_purpose": {name: ledger_totals(rows) for name, rows in sorted(purposes.items())},
            "total_cap_rub": str(cap), "additional_stage_cap_rub": policy["stage_additional_cap_rub"],
            "absolute_stage_ceiling_rub": str(stage_ceiling),
            "remaining_shared_commitment_room_rub": str(cap - amount(total["charged_or_reserved_rub"])),
            "remaining_stage_commitment_room_rub": str(stage_ceiling - amount(total["charged_or_reserved_rub"])),
            "within_total_cap": amount(total["charged_or_reserved_rub"]) <= cap,
            "within_stage_ceiling": amount(total["charged_or_reserved_rub"]) <= stage_ceiling,
            "interpretation": "Reported costs, retained reserves above reported costs, and obligations without reported costs are separate. Unknown is not zero."}


def validate_inputs(protocol, tasks_document, results, support, planning, cost_plan, raw):
    tasks = tasks_document["tasks"]
    validate_probe_layout(tasks)
    require(protocol["status"] == "prospective_frozen_development_probe", "Protocol is not the frozen development probe")
    require(results.get("phase") == "pilot_v2_stage_A" and results.get("all_planned_cells") == 192,
            "Results are not the complete planned-cell document")
    require(isinstance(results.get("completed_utc"), str), "Only finished results may be summarized")
    closed = datetime.fromisoformat(results["completed_utc"].replace("Z", "+00:00"))
    require(closed.tzinfo is not None, "Result closure needs a timezone")
    require(results["protocol_sha256"] == sha(raw["protocol"]) and
            results["corpus_sha256"] == sha(raw["tasks"]) == protocol["tasks"]["file_sha256"],
            "Results/protocol/corpus hashes disagree")
    require(protocol["measurement"]["primary_prefix_words"] == 256 and
            protocol["measurement"]["allow_budget_censored_gradeable"] is False,
            "Unexpected primary measurement policy")
    models = [row["model"] for row in protocol["models"]]
    caps = protocol["generation"]["output_budget_tokens"]
    expected_cells = {(task["task_id"], model, cap) for task in tasks for model in models for cap in caps}
    cells = [(row["task_id"], row["model"], row["output_budget_tokens"]) for row in results["records"]]
    require(len(cells) == len(set(cells)) == 192 and set(cells) == expected_cells,
            "Results omit, repeat, or replace planned cells")
    computed = summarize_support(results["records"], tasks, models, output_budgets=tuple(caps),
                                 prefix_budgets=tuple(protocol["measurement"]["observed_prefix_words"]), stage="development_probe")
    if "input_sha256" in support:
        computed["input_sha256"] = {"records": sha(raw["results"]), "tasks": sha(raw["tasks"])}
    require(computed == support, "Saved class-support artifact differs from the exact frozen statistics replay")
    require(planning.get("status") == "scenario_planning_only_not_observed_or_validated_power" and
            sha(raw["planning"]) == protocol["planning_scenarios"]["sha256"],
            "Planning scenarios are not the frozen hypothetical artifact")
    require(cost_plan["protocol_sha256"] == results["protocol_sha256"] and
            cost_plan["source_inventory_sha256"] == results["source_inventory_sha256"] and
            cost_plan["dispatch_plan_sha256"] == results["dispatch_plan_sha256"],
            "Quotation plan belongs to a different protocol/source/dispatch roster")
    require(len(cost_plan["cells"]) == 192 and len({row["call_id"] for row in cost_plan["cells"]}) == 192
            and {row["call_id"] for row in cost_plan["cells"]} == {row["trace_id"] for row in results["records"]},
            "Quotation plan does not cover the exact 192 result cells")
    return closed, computed


def coverage_rows(support):
    fields = ("model", "output_budget_tokens", "prefix_budget_words", "planned_attempts", "represented_cells",
              "recorded_attempts", "not_dispatched", "unrecorded_attempts", "unknown_attempts", "unattempted_intents",
              "completed_gradeable", "completed_gradeable_fraction_of_planned", "eligible_traces", "correct_traces",
              "error_traces", "planned_roots", "error_roots", "correct_roots", "mixed_roots", "censored_attempts",
              "censored_diagnostic_gradeable", "censored_diagnostic_prefix_eligible", "engineering_readiness",
              "allocation_complete_and_no_unknown")
    rows = [{field: group[field] for field in fields} for group in support["groups"]]
    strata = [{"model": group["model"], "output_budget_tokens": group["output_budget_tokens"],
               "prefix_budget_words": group["prefix_budget_words"], "domain": row["domain"], "tier": row["tier"],
               "roots": row["roots"], **row["categories"]} for group in support["groups"] for row in group["strata"]]
    return rows, strata


def future_design(protocol, tasks, results, support, planning, cost_plan, budget):
    by_call = {row["trace_id"]: row for row in results["records"]}
    root_quotes, single_quotes = defaultdict(lambda: Decimal(0)), defaultdict(lambda: Decimal(0))
    for quote in cost_plan["cells"]:
        row = by_call[quote["call_id"]]
        key = row["model"], row["output_budget_tokens"]
        value = amount(quote["reservation_rub"])
        require(value > 0, "Future quote requires a positive reservation bound")
        root_quotes[key + (row["root_id"],)] += value
        single_quotes[key] = max(single_quotes[key], value)
    quote_rows = []
    models = sorted(row["model"] for row in protocol["models"])
    for model, cap in sorted(single_quotes):
        observed_max = max(value for (m, c, _), value in root_quotes.items() if (m, c) == (model, cap))
        upper = 2 * single_quotes[(model, cap)]
        quote_rows.append({"model": model, "output_budget_tokens": cap,
                           "maximum_observed_pair_root_quote_rub": str(observed_max),
                           "twice_maximum_single_variant_quote_rub": str(upper)})
    candidates = planning["conditional_required_N"]
    support_by_scenario = defaultdict(dict)
    for row in candidates["support"]:
        support_by_scenario[row["scenario"]][row["role"]] = row
    remaining = Decimal(budget["remaining_shared_commitment_room_rub"])
    forecasts = []
    for cap in sorted(protocol["generation"]["output_budget_tokens"]):
        paired_root_upper = sum((2 * single_quotes[(model, cap)] for model in models), Decimal(0))
        for scenario, roles in sorted(support_by_scenario.items()):
            require(set(roles) == {"probe", "source_train", "source_validation", "target"},
                    "Planning scenario omits a future role")
            train, validation, target = (roles[role]["required_roots"] for role in ("source_train", "source_validation", "target"))
            for precision in candidates["precision"]:
                target_n = max(target, precision["required_roots"]) if target is not None else None
                total = train + validation + target_n if None not in (train, validation, target_n) else None
                cost = paired_root_upper * total if total is not None else None
                forecasts.append({"scenario": scenario, "output_budget_tokens": cap,
                    "assumed_root_sd": precision["assumed_root_sd"], "target_CI_half_width": precision["target_CI_half_width"],
                    "source_train_roots": train, "source_validation_roots": validation,
                    "target_roots_from_class_support": target, "target_roots_from_precision": precision["required_roots"],
                    "conditional_target_roots": target_n, "conditional_total_disjoint_roots": total,
                    "generation_calls_per_root": 2 * len(models), "generation_calls": total * 2 * len(models) if total is not None else None,
                    "conditional_generation_root_upper_quote_rub": str(paired_root_upper),
                    "conditional_generation_only_reservation_rub": str(cost) if cost is not None else None,
                    "generation_only_within_current_remaining_rub": cost <= remaining if cost is not None else None})
    selected = support["selected_common_output_cap"]
    return {"schema_version": 1, "protocol_id": protocol["protocol_id"], "primary_prefix_words": 256,
            "decision": "engineering_floor_met_design_only" if selected is not None else "no_output_cap_selected",
            "selected_output_cap_for_future_design": selected,
            "entire_fixed_roster_resolved": support["entire_fixed_roster_resolved"],
            "class_support_artifact_validated": True, "future_training_readiness_established": False,
            "reason": "The 3/3-root probe floor and 75% completion rule do not establish future source train 10/10, validation 5/5 or target 20/20, precision, validity or power.",
            "final_N_selected": None, "future_test_generated": False, "holdout_release": "not_released",
            "holdout_seed_commitment": protocol["future_study"].get("holdout_seed_commitment"),
            "generation_quote_bounds": quote_rows, "conditional_future_forecasts": forecasts,
            "maximum_probe_prompt_utf8_bytes": max(len(task["prompt"].encode("utf-8")) for task in tasks),
            "forecast_assumptions": ["Future variants have UTF-8 prompt bounds no larger than the largest probe prompt, with the same request overhead, two variants and one call per model/cap/variant.",
                "Pinned providers, unit-price ceilings, sampling and chosen output cap remain no more expensive; fresh quotes are required before any future dispatch.",
                "The conservative bound is twice the maximum single-cell quote per model, summed across both models. The observed maximum paired-root quote is reported separately.",
                "The hypothetical class probabilities and root SDs are assumptions, not fitted v2 estimates. Train/validation/target roots are disjoint; paired variants do not increase N."],
            "omitted_future_costs": ["embeddings", "route admission or changed models", "independent human measurement validation", "annotation", "review", "additional repetitions", "unknown future reserves"],
            "interpretation": "Generation-only conditional feasibility forecast; no final protocol, total study budget, validated power, E0 or scientific approval is produced.",
            "E0": "not_passed", "scientific_validity": "not_assessed"}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def link(path, report_path):
    return os.path.relpath(Path(path).resolve(), report_path.parent.resolve()).replace("\\", "/")


def markdown_report(protocol, results, support, budget, decision, closed, output_dir, report_path):
    primary = [group for group in support["groups"] if group["prefix_budget_words"] == 256]
    closed_msk = closed.astimezone(timezone(timedelta(hours=3)))
    chosen = decision["selected_output_cap_for_future_design"]
    result = (f"Минимальный общий cap для обсуждения следующего дизайна: **{chosen} токенов**."
              if chosen is not None else "**Общий output cap не выбран:** предусмотренные engineering условия не выполнены.")
    lines = ["# Результат development пилота v2", "", result, "",
        f"Итоговый реестр сформирован {closed_msk:%d.%m.%Y %H:%M:%S} по Москве. Протокол `{protocol['protocol_id']}`. "
        "Все 24 roots относятся к development; новых calibration/final задач этим отчётом не создаётся.", "",
        "Проверены четыре primary ячейки model × output cap при 256 наблюдаемых словах. "
        "План содержит 192 вызова: 48 задач, две модели и caps 2048/8192; знаменатель каждой строки всегда 48, включая unsent.", "",
        "| Модель | Output cap | Запланировано / записано | Завершены и оцениваемы | Primary eligible traces | Error / correct roots | Mixed roots | Обрезаны | Unknown | Engineering gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for row in primary:
        name = row["model"].split("/")[-1]
        lines.append(f"| {name} | {row['output_budget_tokens']} | {row['planned_attempts']} / {row['recorded_attempts']} | "
            f"{row['completed_gradeable']} ({row['completed_gradeable_fraction_of_planned']:.1%}) | {row['eligible_traces']} | "
            f"{row['error_roots']} / {row['correct_roots']} | {row['mixed_roots']} | {row['censored_attempts']} | "
            f"{row['unknown_attempts']} | {'floor выполнен' if row['engineering_readiness'] else 'не выполнен'} |")
    lines += ["", "Общий cap требует разрешения всех 192 ячеек без transport unknown, не менее трёх error и трёх correct roots "
        "для каждой модели на 256 словах и ≥75% завершённых оцениваемых ответов от всех 48 попыток каждой model/cap. "
        "Отдельный mixed root может дать оба класса, но остаётся одним root. Усреднение по сегментам/вариантам не создаёт независимые задачи.", "",
        "Length-обрезания сохранены как incomplete: даже диагностически извлечённый ответ не даёт primary label. "
        "Missing/неразбираемые ответы не заменены `false`. Feasibility задачи не приравнивается к правильности модели. "
        "Текст после первого буквального `ANSWER:` исключён до подсчёта prefix.", "",
        f"Полные 128/256/512 counts: [таблица]({link(output_dir / 'coverage.md', report_path)}), "
        f"[CSV]({link(output_dir / 'coverage.csv', report_path)}), [JSON]({link(output_dir / 'coverage.json', report_path)}). "
        f"Все domain/tier strata сохранены в [отдельной таблице]({link(output_dir / 'coverage-by-stratum.csv', report_path)}). "
        "Неудачные условия и secondary budgets не исключаются из публикации.", "", "## Расходы и резервы", "",
        f"До v2 сохранялось {budget['launch']['charged_or_reserved_rub']} RUB обязательств. "
        f"После него общий Ledger содержит {budget['current']['charged_or_reserved_rub']} RUB charged-or-reserved, "
        f"из них известная reported cost — {budget['current']['reported_cost_rub']} RUB; "
        f"без сообщённой стоимости удерживается {budget['current']['commitments_without_reported_cost_rub']} RUB. "
        f"Прирост обязательств с launch: {budget['since_launch']['charged_or_reserved_rub']} RUB. "
        f"Остаток общего потолка: {budget['remaining_shared_commitment_room_rub']} RUB.", "",
        f"Все старые строки Ledger сохранены; расчёт разделяет reported cost, резерв сверх неё и unknown. "
        f"Подробности и hashes: [budget-final.json]({link(output_dir / 'budget-final.json', report_path)}).", "",
        "## Что это позволяет планировать", "",
        "Stage-A floor 3/3 — инженерный сигнал для обсуждения следующего дизайна. Он не устанавливает будущие floors "
        "10/10 source train, 5/5 source validation и 20/20 target, точность интервалов или валидированную мощность. "
        "Ни один эффект prediction здесь не подбирался и новый classifier не обучался.", "",
        "Ниже показан один из заранее заданных ориентиров точности: root SD=0.10 и half width=0.01. "
        "Во всех строках взяты новые непересекающиеся train/validation/target roots, target N равен максимуму "
        "классового candidate N и условного normal-precision N=385. Это гипотетические варианты, не выбранный объём.", "",
        "| Сценарий | Cap | Source train / validation / target roots | Только генерации, верхняя котировка RUB | Генерации помещаются в текущий общий остаток |",
        "|---|---:|---:|---:|---|"]
    for row in decision["conditional_future_forecasts"]:
        if row["assumed_root_sd"] != .10 or row["target_CI_half_width"] != .01:
            continue
        cost = row["conditional_generation_only_reservation_rub"]
        cost_text = f"{Decimal(cost):.2f}" if cost is not None else "не оценено"
        fits_text = ("да, условно" if row["generation_only_within_current_remaining_rub"] else "нет") if cost is not None else "не оценено"
        lines.append(f"| {row['scenario']} | {row['output_budget_tokens']} | {row['source_train_roots']} / "
            f"{row['source_validation_roots']} / {row['conditional_target_roots']} | "
            f"{cost_text} | {fits_text} |")
    lines += ["", "Котировка предполагает неизменные или меньшие цены закреплённых провайдеров и prompt UTF-8 upper bound "
        f"не больше {decision['maximum_probe_prompt_utf8_bytes']} bytes. Взята двойная максимальная single-variant котировка "
        "каждой модели, а не неподтверждённое предположение, что новая пара не длиннее конкретной старой пары. "
        "Эмбеддинги, новые admission, человеческая валидация, annotation/review и дополнительные повторы в эти суммы не входят; "
        "даже помещающаяся генерация не означает допустимый полный бюджет исследования.", "",
        f"Все сценарии, caps, варианты precision и ограничения: [future-design-decision.json]({link(output_dir / 'future-design-decision.json', report_path)}). "
        "Окончательное N не выбрано, holdout seed не раскрыт и test не выпущен. Будущий дизайн требует новой фиксации "
        "до закрытых ответов; нельзя добавлять test roots до появления ошибок или выбирать удобный test после outcomes.", "",
        "## Границы вывода", "",
        "Это фиксированный development probe поддержки классов. Его положительный инженерный gate не подтверждает "
        "предсказательную ценность динамики, H0/H1–H7, causal stopping или E0. Отрицательный/неполный probe также "
        "не доказывает отсутствия динамического сигнала. Человеческие E0/G3, G2/G4 и внешняя preregistration не созданы. "
        "Модели уже наблюдались при development; будущий holdout from fitting нельзя представлять новым невиданным семейством."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("protocol", "tasks", "results", "launch-ledger", "ledger", "class-support", "planning", "cost-plan"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/PILOT_V2_RESULT.md"))
    args = parser.parse_args()
    paths = {name: getattr(args, name.replace("-", "_")) for name in
             ("protocol", "tasks", "results", "launch-ledger", "ledger", "class-support", "planning", "cost-plan")}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    docs = {name: json.loads(data) for name, data in raw.items()}
    protocol, results, support = docs["protocol"], docs["results"], docs["class-support"]
    closed, _ = validate_inputs(protocol, docs["tasks"], results, support, docs["planning"], docs["cost-plan"], raw)
    budget = budget_result(protocol, docs["launch-ledger"], docs["ledger"], raw["launch-ledger"], raw["ledger"], results)
    decision = future_design(protocol, docs["tasks"]["tasks"], results, support, docs["planning"], docs["cost-plan"], budget)
    rows, strata = coverage_rows(support)
    report = markdown_report(protocol, results, support, budget, decision, closed, args.output_dir, args.report)
    require(all(path.read_bytes() == raw[name] for name, path in paths.items()), "Inputs changed during report construction")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"budget-final.json": budget, "coverage.json": rows, "coverage-by-stratum.json": strata,
               "future-design-decision.json": decision}
    for name, value in outputs.items():
        (args.output_dir / name).write_bytes(canonical(value) + b"\n")
    write_csv(args.output_dir / "coverage.csv", rows)
    write_csv(args.output_dir / "coverage-by-stratum.csv", strata)
    coverage_md = ["# Покрытие всех prefix budgets v2", "",
        "| Model | Output cap | Prefix words | Planned | Recorded | Gradeable complete | Eligible traces | Error / correct / mixed roots | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        coverage_md.append(f"| {row['model']} | {row['output_budget_tokens']} | {row['prefix_budget_words']} | "
            f"{row['planned_attempts']} | {row['recorded_attempts']} | {row['completed_gradeable']} | {row['eligible_traces']} | "
            f"{row['error_roots']} / {row['correct_roots']} / {row['mixed_roots']} | {row['unknown_attempts']} |")
    (args.output_dir / "coverage.md").write_text("\n".join(coverage_md) + "\n", encoding="utf-8", newline="\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8", newline="\n")
    filenames = list(outputs) + ["coverage.csv", "coverage-by-stratum.csv", "coverage.md"]
    manifest = {"schema_version": 1, "report_version": VERSION, "protocol_id": protocol["protocol_id"],
        "script_sha256": sha(Path(__file__).read_bytes()),
        "inputs": {name: evidence(paths[name], data) for name, data in raw.items()},
        "outputs": [{"path": name, "sha256": sha((args.output_dir / name).read_bytes())} for name in filenames],
        "report": evidence(args.report, args.report.read_bytes()), "new_model_calls": 0,
        "no_refit_or_test_release": True, "scientific_validity": "not_assessed"}
    (args.output_dir / "report-manifest.json").write_bytes(canonical(manifest) + b"\n")
    print(json.dumps({"output_dir": str(args.output_dir), "report": str(args.report),
                      "selected_common_output_cap": support["selected_common_output_cap"], "new_model_calls": 0}))


if __name__ == "__main__":
    main()
