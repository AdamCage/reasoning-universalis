"""Deterministic reporting of a closed, mixed-provenance R1 development roster.

No collection, model fitting, new task generation or holdout release occurs.
Original A and its physical records are inputs, never rewritten by this helper.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from pilot_v2 import statistical_design as statistics
from scripts import summarize_pilot_v2 as base

VERSION = "pilot-v2-recovery-report-v1"
GPT, DEEPSEEK = "openai/gpt-oss-20b", "deepseek/deepseek-v4.1-flash"
INPUTS = ("protocol", "tasks", "results", "launch-ledger", "ledger", "class-support", "planning", "cost-plan",
          "source-inventory", "parent-protocol", "parent-results", "parent-cost-plan", "reuse-mapping")
require, sha, canonical = base.require, base.sha, statistics.canonical


def encode(value):
    # Match the frozen physical-record serializer without importing its unused
    # live runner dependencies into the portable reporting path.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def cell_key(row):
    return row["task_id"], row["model"], row["output_budget_tokens"]


def quote_binding(plan, result, count):
    require(all(plan[field] == result[field] for field in
                ("protocol_sha256", "source_inventory_sha256", "dispatch_plan_sha256")),
            "Quotation plan belongs to another physical collection")
    cells = plan["cells"]
    require(len(cells) == count and len({row["call_id"] for row in cells}) == count,
            "Quotation roster has a missing or repeated cell")
    require(all(base.amount(row["reservation_rub"]) > 0 and row.get("quote_receipt_sha256") for row in cells),
            "Forecast requires positive conservative quotes and their metadata receipts")


def validate(docs, raw):
    p, a, result, original = (docs[name] for name in ("protocol", "parent-protocol", "results", "parent-results"))
    r, mapping, tasks = p["recovery"], docs["reuse-mapping"], docs["tasks"]["tasks"]
    statistics.validate_probe_layout(tasks)
    require(p.get("status") == "prospective_frozen_provider_recovery" and r.get("condition") == "R1"
            and result.get("phase") == "pilot_v2_provider_recovery_R1" and result.get("condition") == "R1",
            "Inputs are not the prospectively frozen R1 condition")
    require(result.get("all_planned_cells") == 192 and result.get("new_planned_calls") == 96
            and result.get("reused_records") == 96 and result.get("independent_roots") == 24,
            "R1 must retain 192 rows: 96 reused plus 96 new, on 24 roots")
    require(result["protocol_sha256"] == sha(raw["protocol"])
            and result["corpus_sha256"] == p["tasks"]["file_sha256"] == sha(raw["tasks"])
            and result["source_inventory_sha256"] == sha(raw["source-inventory"])
            and result["reuse_mapping_sha256"] == sha(raw["reuse-mapping"]),
            "R1 result/protocol/corpus/source/reuse hashes disagree")
    require(r["parent_protocol_sha256"] == sha(raw["parent-protocol"]) == original["protocol_sha256"]
            and r["parent_results_sha256"] == sha(raw["parent-results"]) == result["parent_results_sha256"]
            and r["parent_dispatch_plan_sha256"] == original["dispatch_plan_sha256"]
            and r["parent_source_inventory_sha256"] == original["source_inventory_sha256"]
            and original.get("phase") == "pilot_v2_stage_A" and original.get("all_planned_cells") == 192,
            "Original A provenance differs from the recovery declaration")
    require(a.get("status") == "prospective_frozen_development_probe"
            and all(p.get(field) == a.get(field) for field in
                    ("tasks", "measurement", "stage_A", "future_study", "statistical_plan", "planning_scenarios", "budget"))
            and {key: value for key, value in p["generation"].items() if key != "new_calls_max"} == a["generation"],
            "Recovery changed the original scientific criteria, budget or generation policy")
    require(p["measurement"]["primary_prefix_words"] == 256
            and p["measurement"]["allow_budget_censored_gradeable"] is False
            and p["generation"].get("new_calls_max") == 96,
            "Unexpected primary eligibility or recovery allocation")
    inventory = docs["source-inventory"]["files"]
    require(inventory.get("pilot_v2/statistical_design.py") == sha(Path(statistics.__file__).read_bytes())
            and inventory.get("scripts/collect_pilot_v2_recovery.py") == r["collector_sha256"],
            "Statistics or collector source differs from the frozen R1 inventory")
    models = [row["model"] for row in p["models"]]
    require({row["model"]: row["provider"] for row in p["models"]} == {DEEPSEEK: "BytePlus", GPT: "AkashML"},
            "R1 does not use the declared two model/provider conditions")
    expected = {(task["task_id"], model, cap) for task in tasks for model in models
                for cap in p["generation"]["output_budget_tokens"]}
    for document in (result, original):
        rows = document["records"]
        require(len(rows) == 192 and len({cell_key(row) for row in rows}) == 192
                and {cell_key(row) for row in rows} == expected
                and len({row["trace_id"] for row in rows}) == 192,
                "A or R1 omits/repeats/replaces a planned task/model/cap cell")
    old = {cell_key(row): row for row in original["records"]}
    rows = {cell_key(row): row for row in result["records"]}
    old_ids = {row["trace_id"] for row in original["records"]}
    reused, fresh = mapping["reused_records"], mapping["new_records"]
    require(mapping.get("condition") == "R1" and mapping.get("independent_roots") == 24
            and mapping.get("parent_results_sha256") == sha(raw["parent-results"])
            and len(reused) == len(fresh) == 96
            and len({entry["trace_id"] for entry in reused + fresh}) == 192,
            "Reuse mapping does not identify exactly 96+96 physical observations")
    require({entry["trace_id"] for entry in reused} == {row["trace_id"] for row in rows.values() if row["model"] == DEEPSEEK}
            and {entry["trace_id"] for entry in fresh} == {row["trace_id"] for row in rows.values() if row["model"] == GPT},
            "Reuse mapping and R1 physical rows disagree")
    for entry in reused:
        key = entry["task_id"], DEEPSEEK, entry["output_budget_tokens"]
        row, previous = rows[key], old[key]
        require(row == previous and entry["trace_id"] == row["trace_id"]
                and entry["record_sha256"] == sha(encode(previous))
                and all(entry[field] == previous[field] for field in
                        ("root_id", "request_sha256", "response_sha256", "source_inventory_sha256")),
                "A reused DeepSeek row was changed, omitted or relabelled")
    for entry in fresh:
        key = entry["task_id"], GPT, entry["output_budget_tokens"]
        row, previous = rows[key], old[key]
        require(row["provider"] == entry["provider"] == "AkashML" and row["trace_id"] not in old_ids
                and row["root_id"] == previous["root_id"] == entry["root_id"]
                and row["seed"] == previous["seed"] == entry["seed"]
                and row["protocol_sha256"] == result["protocol_sha256"]
                and entry["parent_trace_id"] == previous["trace_id"]
                and entry["parent_condition_id"] == previous["condition_id"]
                and entry["parent_status"] == previous["status"]
                and entry["parent_response_sha256"] == previous.get("response_sha256"),
                "New GPT row is not the declared whole-roster AkashML measurement")
        if row.get("response_sha256") is not None:
            require(row.get("source_inventory_sha256") == result["source_inventory_sha256"]
                    and row.get("corpus_sha256") == result["corpus_sha256"]
                    and row.get("phase") in ("pilot_v2_stage_A", "pilot_v2_provider_recovery_R1"),
                    "New GPT physical source/corpus/legacy-phase binding changed")
    quote_binding(docs["cost-plan"], result, 96)
    quote_binding(docs["parent-cost-plan"], original, 192)
    require({row["call_id"] for row in docs["cost-plan"]["cells"]} == {entry["trace_id"] for entry in fresh}
            and {row["call_id"] for row in docs["parent-cost-plan"]["cells"]} == old_ids,
            "A/R1 quotation cells do not match their respective physical rosters")
    merged_quotes = {**docs["cost-plan"], "cells": docs["cost-plan"]["cells"] + [
        row for row in docs["parent-cost-plan"]["cells"] if row["call_id"] in {entry["trace_id"] for entry in reused}]}
    require(docs["planning"].get("status") == "scenario_planning_only_not_observed_or_validated_power"
            and sha(raw["planning"]) == p["planning_scenarios"]["sha256"], "Planning artifact changed")
    kwargs = {"output_budgets": tuple(p["generation"]["output_budget_tokens"]),
              "prefix_budgets": tuple(p["measurement"]["observed_prefix_words"]), "stage": "development_probe"}
    support = statistics.summarize_support(result["records"], tasks, models, **kwargs)
    saved = docs["class-support"]
    if "input_sha256" in saved:
        support["input_sha256"] = {"records": sha(raw["results"]), "tasks": sha(raw["tasks"])}
    require(support == saved, "Saved R1 support differs from exact frozen statistics replay")
    a_support = statistics.summarize_support(original["records"], tasks, models, **kwargs)
    require(a_support["selected_common_output_cap"] is None and not a_support["entire_fixed_roster_resolved"],
            "Original A is not the declared incomplete original condition")
    closed = datetime.fromisoformat(result["completed_utc"].replace("Z", "+00:00"))
    require(closed.tzinfo is not None, "Closed R1 needs a timezone")
    parent_closed = datetime.fromisoformat(original["completed_utc"].replace("Z", "+00:00"))
    require(parent_closed.tzinfo is not None and closed >= parent_closed, "Recovery closure precedes original A closure")
    provenance = {"condition": "R1", "original_A_preserved": True, "original_A_selected_cap": None,
        "original_A_entire_roster_resolved": False, "original_A_results_sha256": sha(raw["parent-results"]),
        "reused_DeepSeek_records_unchanged": 96, "new_GPT_AkashML_planned_records": 96,
        "independent_roots": 24, "independent_replication": False, "unseen_model_family_test": False,
        "physical_record_phase_policy": result["physical_record_phase_policy"],
        "execution_revision_quantization": "unknown; same requested model ID does not prove same checkpoint/backend",
        "quote_provenance": {DEEPSEEK: "Original A final cost plan; historical BytePlus quote, not refreshed by R1",
                             GPT: "R1 pinned AkashML cost plan"}}
    return closed, support, merged_quotes, provenance


def render(protocol, results, support, budget, decision, output_dir, report_path):
    selected = decision["selected_output_cap_for_future_design"]
    lines = ["# Результат provider recovery R1 пилота v2", "",
        "**Общий output cap не выбран; следующий дизайн пока не готов.**" if selected is None else
        f"**Engineering floor выполнен для общего cap {selected}; окончательный дизайн не выбран.**", "",
        "Первоначальный A остаётся неполным, с исходным отрицательным решением о выборе cap. R1 — отдельное "
        "техническое восстановление после известных API503, а не исправление A или независимая репликация. "
        "Все 96 физических DeepSeek/BytePlus записей A повторно использованы без изменения текста, статуса, "
        "обрезания или меток. Все 96 GPT-OSS ячеек запланированы заново на AkashML, без выборочного смешения GPT из A.", "",
        f"Протокол `{protocol['protocol_id']}`; реестр закрыт `{results['completed_utc']}`.", "",
        "Комбинированный реестр содержит 192 строки на тех же 48 задачах и **24 независимых roots**. "
        "Повторное использование и два варианта не увеличивают независимый N. Ревизия/квантизация внешнего backend "
        "неизвестна; одинаковый requested model ID не доказывает одинаковый checkpoint.", "",
        "| Модель / provider | Cap | План / recorded | Завершены и оцениваемы | Prefix256 eligible | Error / correct roots | Censored | Unknown | Engineering floor |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    providers = {row["model"]: row["provider"] for row in protocol["models"]}
    for row in support["groups"]:
        if row["prefix_budget_words"] != 256:
            continue
        lines.append(f"| {row['model'].split('/')[-1]} / {providers[row['model']]} | {row['output_budget_tokens']} | "
            f"{row['planned_attempts']} / {row['recorded_attempts']} | {row['completed_gradeable']} "
            f"({row['completed_gradeable_fraction_of_planned']:.1%}) | {row['eligible_traces']} | "
            f"{row['error_roots']} / {row['correct_roots']} | {row['censored_attempts']} | {row['unknown_attempts']} | "
            f"{'выполнен' if row['engineering_readiness'] else 'не выполнен'} |")
    ds = [row for row in support["groups"] if row["model"] == DEEPSEEK and row["prefix_budget_words"] == 256]
    if all(row["error_roots"] == 0 for row in ds):
        lines += ["", "В сохранённых DeepSeek primary условиях нет завершённых eligible ошибок. "
            "Поэтому общий 3-error/3-correct gate не может пройти независимо от новых GPT исходов. "
            "Это отсутствие наблюдённого error support в данном development корпусе, не доказательство безошибочности модели."]
    lines += ["", "Знаменатель каждой строки — все 48 плановых попыток, включая unsent. Выбор общего cap требует "
        "всех 192 разрешённых исходов без transport unknown, ≥75% completed+gradeable каждой model/cap и минимум "
        "трёх error и трёх correct roots при 256 словах. Length остаётся incomplete с primary correct=null; диагностический "
        "ответ не заменяет это условие. Prefix обрезан перед первым буквальным ANSWER:. Missing не заменяется false.", "",
        f"Все 128/256/512 и отрицательные условия: [coverage]({base.link(output_dir / 'coverage.md', report_path)}), "
        f"[CSV]({base.link(output_dir / 'coverage.csv', report_path)}), [JSON]({base.link(output_dir / 'coverage.json', report_path)}); "
        f"все strata: [CSV]({base.link(output_dir / 'coverage-by-stratum.csv', report_path)}).", "",
        "## Единый бюджет", "",
        f"Перед R1: {budget['launch']['charged_or_reserved_rub']} RUB; после: "
        f"{budget['current']['charged_or_reserved_rub']} RUB charged-or-reserved. Прирост R1: "
        f"{budget['since_launch']['charged_or_reserved_rub']} RUB. Reported cost всего: "
        f"{budget['current']['reported_cost_rub']} RUB; резерв сверх reported: "
        f"{budget['current']['retained_reservation_above_reported_cost_rub']} RUB; без reported cost удерживается "
        f"{budget['current']['commitments_without_reported_cost_rub']} RUB. Все старые строки сохранены.", "",
        f"Общий потолок 3000 RUB и исходный абсолютный Stage-A потолок {budget['absolute_stage_ceiling_rub']} RUB "
        "не увеличивались. Допуск 1200 RUB относится к исходному launch A, а не к новому launch R1; бюджет не обнулён. "
        f"[Полный расчёт]({base.link(output_dir / 'budget-final.json', report_path)}).", "",
        "## Условное планирование", "",
        "Floor 3/3 roots означает feasibility, не готовность будущих train 10/10, validation 5/5, target 20/20, "
        "не валидированная мощность и не evidence prediction. Ни один classifier не обучался. Ниже сценарии "
        "при root SD = 0.10 и целевой half width = 0.01; все train/validation/target roots будущие и непересекающиеся. "
        "Они используют заранее заданные вероятности классов и условную normal-precision формулу, не fitted эффект пилота.", "",
        "| Сценарий | Cap | Train / validation / target roots | Только генерация, условный верх RUB |",
        "|---|---:|---:|---:|"]
    for row in decision["conditional_future_forecasts"]:
        if row["assumed_root_sd"] == .1 and row["target_CI_half_width"] == .01:
            cost = row["conditional_generation_only_reservation_rub"]
            lines.append(f"| {row['scenario']} | {row['output_budget_tokens']} | {row['source_train_roots']} / "
                f"{row['source_validation_roots']} / {row['conditional_target_roots']} | "
                f"{format(base.amount(cost), '.2f') if cost is not None else 'не оценено'} |")
    lines += ["", "DeepSeek использует исторические котировки A/BytePlus; GPT — R1/AkashML. Это не новая котировка "
        "DeepSeek. Будущие цены, provider, sampling/cap и UTF-8 prompt upper bound предполагаются не дороже probe; "
        "перед новым сбором нужны свежие котировки. На root берётся двойной максимальный single-variant quote "
        "каждой модели, а не максимальная конкретная старая пара. Эмбеддинги, admission, E0/человеческая разметка, "
        "review и дополнительные повторы не включены. Условно доступные генерации не означают доступный полный study.", "",
        f"[Все сценарии и ограничения]({base.link(output_dir / 'future-design-decision.json', report_path)}). "
        "**Окончательный N не выбран, holdout не раскрыт и новый test не сгенерирован.** Нельзя продолжать сбор "
        "до появления удобных ошибок или выбирать test по outcomes. Новых recovery conditions после R1 не предусмотрено.", "",
        "E0 не пройден. H0–H7 сохранены; этот development результат не проверяет универсальную когницию, "
        "предсказательную ценность динамики или causal stopping. Отсутствие поддержки классов не доказывает отсутствие "
        "сигнала. Человеческое научное ревью, G2–G4 и внешняя preregistration не создавались."]
    return "\n".join(lines) + "\n"


def build(paths, output_dir, report_path):
    output_dir, report_path = Path(output_dir), Path(report_path)
    raw = {name: Path(path).read_bytes() for name, path in paths.items()}
    docs = {name: json.loads(value) for name, value in raw.items()}
    closed, support, quotes, provenance = validate(docs, raw)
    protocol, results = docs["protocol"], docs["results"]
    budget = base.budget_result(protocol, docs["launch-ledger"], docs["ledger"], raw["launch-ledger"], raw["ledger"], results)
    budget.update({"new_stage_allowance_rub": "0", "original_A_launch_charged_or_reserved_rub":
                   docs["parent-protocol"]["parent"]["launch_charged_or_reserved_rub"], "stage_budget_reset": False})
    decision = base.future_design(protocol, docs["tasks"]["tasks"], results, support, docs["planning"], quotes, budget)
    decision.update(provenance)
    decision["forecast_assumptions"].append("DeepSeek prices are inherited original-A BytePlus quotations; R1 refreshes only GPT/AkashML, so fresh future quotes are mandatory.")
    rows, strata = base.coverage_rows(support)
    report = render(protocol, results, support, budget, decision, output_dir, report_path)
    require(all(Path(path).read_bytes() == raw[name] for name, path in paths.items()), "Inputs changed while constructing R1 report")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"budget-final.json": budget, "coverage.json": rows, "coverage-by-stratum.json": strata,
               "future-design-decision.json": decision, "provenance.json": provenance}
    for name, value in outputs.items():
        (output_dir / name).write_bytes(canonical(value) + b"\n")
    base.write_csv(output_dir / "coverage.csv", rows)
    base.write_csv(output_dir / "coverage-by-stratum.csv", strata)
    lines = ["# Все prefix budgets R1 (96 exact reuse + 96 new; 24 roots)", "",
        "| Model | Cap | Prefix | Planned | Recorded | Completed gradeable | Eligible | Error / correct / mixed roots | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['model']} | {row['output_budget_tokens']} | {row['prefix_budget_words']} | {row['planned_attempts']} | "
            f"{row['recorded_attempts']} | {row['completed_gradeable']} | {row['eligible_traces']} | "
            f"{row['error_roots']} / {row['correct_roots']} / {row['mixed_roots']} | {row['unknown_attempts']} |")
    (output_dir / "coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    names = list(outputs) + ["coverage.csv", "coverage-by-stratum.csv", "coverage.md"]
    manifest = {"schema_version": 1, "report_version": VERSION, "protocol_id": protocol["protocol_id"],
        "condition": "R1", "closed_utc": closed.isoformat(), "script_sha256": sha(Path(__file__).read_bytes()),
        "source_sha256": {"scripts/summarize_pilot_v2.py": sha(Path(base.__file__).read_bytes()),
                          "pilot_v2/statistical_design.py": sha(Path(statistics.__file__).read_bytes())},
        "inputs": {name: base.evidence(paths[name], value) for name, value in raw.items()},
        "outputs": [{"path": name, "sha256": sha((output_dir / name).read_bytes())} for name in names],
        "report": base.evidence(report_path, report_path.read_bytes()), "new_model_calls": 0,
        "original_A_unchanged": True, "no_refit_or_test_release": True, "scientific_validity": "not_assessed"}
    (output_dir / "report-manifest.json").write_bytes(canonical(manifest) + b"\n")
    return {"selected_common_output_cap": support["selected_common_output_cap"], "output_dir": str(output_dir),
            "report": str(report_path), "new_model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in INPUTS:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/PILOT_V2_RECOVERY_RESULT.md"))
    args = parser.parse_args()
    paths = {name: getattr(args, name.replace("-", "_")) for name in INPUTS}
    print(json.dumps(build(paths, args.output_dir, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
