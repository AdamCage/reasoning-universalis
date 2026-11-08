"""Post-data descriptive selection analysis of closed development A/R1 only.

No API, fit, v1 per-task test input, new corpus or change to old artifacts.
The new output explains observed support losses; it cannot identify why an
uncompleted answer would have been right or wrong, or a causal cap effect.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from pilot_v2 import statistical_design as frozen_statistics

VERSION = "post-v2-selection-descriptive-v1"
PREFIXES = (128, 256, 512)
CAPS = (2048, 8192)
DS = "deepseek/deepseek-v4.1-flash"
INPUT_NAMES = ("tasks", "a-protocol", "a-results", "r1-protocol", "r1-results", "r1-support", "source-inventory")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def quantiles(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "min": None, "q25": None, "median": None, "q75": None, "max": None}
    def q(fraction):
        position = (len(values) - 1) * fraction
        index = int(position)
        following = min(index + 1, len(values) - 1)
        return values[index] + (values[following] - values[index]) * (position - index)
    return {"n": len(values), "min": values[0], "q25": q(.25), "median": q(.5), "q75": q(.75), "max": values[-1]}


def reference_type(task):
    """Certificate type is task feasibility, never model answer correctness."""
    certificate = task.get("reference_certificate", {})
    if certificate.get("kind") == "directed_cycle_witness":
        return "IMPOSSIBLE"
    answer = certificate.get("answer")
    if isinstance(answer, str) and answer in ("SAT", "UNSAT", "IMPOSSIBLE"):
        return answer
    return "feasible"


def lengths(record):
    raw = record.get("raw_reasoning_text")
    text = record.get("text", "")
    require(isinstance(text, str), "Predictor text must be a string")
    if raw is None:
        require(not text, "A nonempty trace needs the original raw reasoning text")
        return {"reasoning_present": False, "answer_marker_present": False, "raw_reasoning_words": None,
                "prefix_before_answer_words": None, "suffix_after_answer_words": None,
                "answer_marker_character": None}
    require(isinstance(raw, str), "Raw reasoning must be a string")
    position = raw.find("ANSWER:")
    prefix = raw if position < 0 else raw[:position]
    require(text == prefix, "Saved predictor text differs from first-ANSWER censoring")
    return {"reasoning_present": bool(raw.strip()), "answer_marker_present": position >= 0,
            "raw_reasoning_words": len(raw.split()), "prefix_before_answer_words": len(prefix.split()),
            "suffix_after_answer_words": len(raw[position + len("ANSWER:"):].split()) if position >= 0 else None,
            "answer_marker_character": position if position >= 0 else None}


def outcome(record):
    require(record.get("correct") is None or type(record["correct"]) is bool, "Correctness is Boolean or null")
    if record.get("status") == "not_dispatched" or record.get("attempted") is False:
        return "not_dispatched"
    if (record.get("request_state") == "unknown" or record.get("status") in
            ("unknown", "unresolved_attempt", "unresolved_intent") or record.get("http_status") is None):
        return "transport_unknown"
    if record.get("budget_censored") is True or record.get("finish_reason") == "length":
        require(record.get("correct") is None, "Censored primary labels must remain null")
        return "censored"
    accepted = (record.get("status") == "completed" and record.get("finish_reason") == "stop"
                and record.get("identity_verified") is True and record.get("provider_route_verified") is True
                and record.get("observed_trace_status") == "visible_trace_candidate" and record.get("http_status") == 200)
    if accepted and type(record.get("correct")) is bool and record.get("gradable") is True:
        return "completed_correct" if record["correct"] else "completed_incorrect"
    if accepted:
        return "completed_unparseable"
    return "operational_excluded"


def matrix(records, tasks, models):
    lookup = {task["task_id"]: task for task in tasks}
    expected = {(task_id, model, cap) for task_id in lookup for model in models for cap in CAPS}
    keys = [(row["task_id"], row["model"], row["output_budget_tokens"]) for row in records]
    require(len(keys) == len(set(keys)) == len(expected) and set(keys) == expected,
            "All planned task/model/cap rows must be represented exactly once")
    require(len({record["trace_id"] for record in records}) == len(records), "Repeated physical trace identity")
    rows = []
    for record in records:
        task = lookup[record["task_id"]]
        require(record["root_id"] == task["root_id"] and record["domain"] == task["domain"]
                and record.get("tier", record.get("difficulty")) == task.get("tier", task.get("difficulty")),
                "Task/root/domain/tier lineage changed")
        row = {key: record[key] for key in ("task_id", "root_id", "model", "provider", "output_budget_tokens", "trace_id")}
        row.update({"domain": task["domain"], "tier": task.get("tier", task.get("difficulty")),
            "reference_type": reference_type(task), "seed": record["seed"], "sample_index": record.get("sample_index", 0),
            "attempted": record.get("attempted") is True, "outcome": outcome(record),
            "primary_correct": record.get("correct"), "source_protocol_sha256": record.get("protocol_sha256"),
            **lengths(record)})
        row["completed_gradeable"] = row["outcome"] in ("completed_correct", "completed_incorrect")
        require(not row["completed_gradeable"] or row["reasoning_present"],
                "Completed physical observation has no returned reasoning")
        for prefix in PREFIXES:
            row[f"eligible_{prefix}"] = row["completed_gradeable"] and (row["prefix_before_answer_words"] or 0) >= prefix
        rows.append(row)
    return sorted(rows, key=lambda row: (row["model"], row["output_budget_tokens"], row["task_id"]))


def subgroups(rows):
    yield {"scope": "all", "domain": "all", "tier": "all", "reference_type": "all"}, rows
    for scope, names in (("domain", ("domain",)), ("tier", ("tier",)),
                         ("domain_tier", ("domain", "tier")), ("domain_reference", ("domain", "reference_type"))):
        grouped = defaultdict(list)
        for row in rows:
            grouped[tuple(row[name] for name in names)].append(row)
        for key, selected in sorted(grouped.items()):
            identity = {"scope": scope, "domain": "all", "tier": "all", "reference_type": "all"}
            identity.update(zip(names, key))
            yield identity, selected


def support_summary(rows, prefix):
    roots = {row["root_id"] for row in rows}
    correct = [row for row in rows if row[f"eligible_{prefix}"] and row["primary_correct"] is True]
    errors = [row for row in rows if row[f"eligible_{prefix}"] and row["primary_correct"] is False]
    correct_roots, error_roots = ({row["root_id"] for row in values} for values in (correct, errors))
    complete = [row for row in rows if row["completed_gradeable"]]
    return {"prefix_words": prefix, "planned_attempts": len(rows), "planned_roots": len(roots),
        "recorded_attempts": sum(row["attempted"] for row in rows),
        "not_dispatched": sum(row["outcome"] == "not_dispatched" for row in rows),
        "transport_unknown": sum(row["outcome"] == "transport_unknown" for row in rows),
        "operational_excluded": sum(row["outcome"] == "operational_excluded" for row in rows),
        "completed_unparseable": sum(row["outcome"] == "completed_unparseable" for row in rows),
        "censored": sum(row["outcome"] == "censored" for row in rows),
        "completed_gradeable": len(complete), "completion_fraction_of_planned": len(complete) / len(rows),
        "completed_correct": sum(row["primary_correct"] is True for row in complete),
        "completed_incorrect": sum(row["primary_correct"] is False for row in complete),
        "completed_but_short": len(complete) - len(correct) - len(errors),
        "completed_raw_below_prefix": sum(row["raw_reasoning_words"] < prefix for row in complete),
        "completed_raw_long_but_preanswer_short": sum(row["raw_reasoning_words"] >= prefix
            and row["prefix_before_answer_words"] < prefix for row in complete),
        "censored_with_answer_marker": sum(row["outcome"] == "censored" and row["answer_marker_present"] for row in rows),
        "eligible_traces": len(correct) + len(errors), "correct_traces": len(correct), "error_traces": len(errors),
        "correct_roots": len(correct_roots), "error_roots": len(error_roots),
        "mixed_roots": len(correct_roots & error_roots),
        "no_eligible_class_roots": len(roots - correct_roots - error_roots)}


def grouped_support(rows):
    grouped, root_rows, length_rows = [], [], []
    for model in sorted({row["model"] for row in rows}):
        for cap in CAPS:
            condition = [row for row in rows if row["model"] == model and row["output_budget_tokens"] == cap]
            for identity, selected in subgroups(condition):
                for prefix in PREFIXES:
                    grouped.append({"model": model, "output_budget_tokens": cap, **identity,
                                    **support_summary(selected, prefix)})
                for label in ["all"] + sorted({row["outcome"] for row in selected}):
                    observed = selected if label == "all" else [row for row in selected if row["outcome"] == label]
                    traces = [row for row in observed if row["reasoning_present"]]
                    length_rows.append({"model": model, "output_budget_tokens": cap, **identity, "outcome": label,
                        "condition_planned_attempts": len(selected), "outcome_group_attempts": len(observed),
                        "returned_reasoning_traces": len(traces),
                        "first_answer_marker_traces": sum(row["answer_marker_present"] for row in traces),
                        **{name: quantiles([row[name] for row in traces if row[name] is not None]) for name in
                           ("raw_reasoning_words", "prefix_before_answer_words", "suffix_after_answer_words")}})
            for root in sorted({row["root_id"] for row in condition}):
                selected = [row for row in condition if row["root_id"] == root]
                for prefix in PREFIXES:
                    root_rows.append({"model": model, "output_budget_tokens": cap, "root_id": root,
                        "domain": selected[0]["domain"], "tier": selected[0]["tier"],
                        "reference_type": selected[0]["reference_type"], **support_summary(selected, prefix)})
    return grouped, root_rows, length_rows


def paired_caps(rows):
    lookup = {(row["task_id"], row["model"], row["output_budget_tokens"]): row for row in rows}
    pairs = []
    for task_id, model in sorted({(row["task_id"], row["model"]) for row in rows}):
        low, high = (lookup[(task_id, model, cap)] for cap in CAPS)
        require(all(low[name] == high[name] for name in ("root_id", "domain", "tier", "reference_type", "seed", "sample_index")),
                "Cap pair changed root/stratum/reference or requested sampling seed")
        pair = {key: low[key] for key in ("task_id", "root_id", "domain", "tier", "reference_type", "model", "seed")}
        pair.update({"low_cap": CAPS[0], "high_cap": CAPS[1], "low_outcome": low["outcome"], "high_outcome": high["outcome"],
            "low_completed": low["completed_gradeable"], "high_completed": high["completed_gradeable"],
            "completion_delta": int(high["completed_gradeable"]) - int(low["completed_gradeable"]),
            "low_correct": low["primary_correct"], "high_correct": high["primary_correct"],
            "low_prefix_words": low["prefix_before_answer_words"], "high_prefix_words": high["prefix_before_answer_words"],
            "prefix_length_delta": high["prefix_before_answer_words"] - low["prefix_before_answer_words"]
                if low["reasoning_present"] and high["reasoning_present"] else None})
        for prefix in PREFIXES:
            pair[f"low_eligible_{prefix}"] = low[f"eligible_{prefix}"]
            pair[f"high_eligible_{prefix}"] = high[f"eligible_{prefix}"]
        pairs.append(pair)
    summaries, root_pairs = [], []
    for model in sorted({pair["model"] for pair in pairs}):
        selected_model = [pair for pair in pairs if pair["model"] == model]
        for identity, selected in subgroups(selected_model):
            transitions = Counter((pair["low_outcome"], pair["high_outcome"]) for pair in selected)
            root_deltas = defaultdict(int)
            for pair in selected:
                root_deltas[pair["root_id"]] += pair["completion_delta"]
            summaries.append({"model": model, **identity, "planned_task_pairs": len(selected),
                "independent_root_blocks": len(root_deltas), "completion_gained_pairs": sum(pair["completion_delta"] > 0 for pair in selected),
                "completion_lost_pairs": sum(pair["completion_delta"] < 0 for pair in selected),
                "both_complete_pairs": sum(pair["low_completed"] and pair["high_completed"] for pair in selected),
                "neither_complete_pairs": sum(not pair["low_completed"] and not pair["high_completed"] for pair in selected),
                "roots_with_net_completion_gain": sum(delta > 0 for delta in root_deltas.values()),
                "roots_with_net_completion_loss": sum(delta < 0 for delta in root_deltas.values()),
                "roots_with_no_net_completion_change": sum(delta == 0 for delta in root_deltas.values()),
                "outcome_transitions": [{"low": key[0], "high": key[1], "task_pairs": count} for key, count in sorted(transitions.items())],
                "prefix_transitions": [{"prefix_words": prefix,
                    "eligible_gained_pairs": sum(not pair[f"low_eligible_{prefix}"] and pair[f"high_eligible_{prefix}"] for pair in selected),
                    "eligible_lost_pairs": sum(pair[f"low_eligible_{prefix}"] and not pair[f"high_eligible_{prefix}"] for pair in selected),
                    "roots_with_any_eligible_gain": sum(any(not pair[f"low_eligible_{prefix}"] and pair[f"high_eligible_{prefix}"]
                        for pair in selected if pair["root_id"] == root) for root in root_deltas),
                    "roots_with_any_eligible_loss": sum(any(pair[f"low_eligible_{prefix}"] and not pair[f"high_eligible_{prefix}"]
                        for pair in selected if pair["root_id"] == root) for root in root_deltas)}
                    for prefix in PREFIXES]})
        for root in sorted({pair["root_id"] for pair in selected_model}):
            selected = [pair for pair in selected_model if pair["root_id"] == root]
            root_pairs.append({"model": model, "root_id": root, "domain": selected[0]["domain"], "tier": selected[0]["tier"],
                "reference_type": selected[0]["reference_type"], "dependent_variant_pairs": len(selected),
                "low_completed_variants": sum(pair["low_completed"] for pair in selected),
                "high_completed_variants": sum(pair["high_completed"] for pair in selected),
                "net_completed_variant_delta": sum(pair["completion_delta"] for pair in selected),
                "mean_variant_prefix_length_delta": sum(pair["prefix_length_delta"] for pair in selected) / len(selected)
                    if all(pair["prefix_length_delta"] is not None for pair in selected) else None,
                **{f"{side}_eligible_variants_{prefix}": sum(pair[f"{side}_eligible_{prefix}"] for pair in selected)
                   for side in ("low", "high") for prefix in PREFIXES}})
    return pairs, summaries, root_pairs


def analyze(records, tasks, models):
    rows = matrix(records, tasks, models)
    support, roots, word_lengths = grouped_support(rows)
    pairs, transitions, root_pairs = paired_caps(rows)
    reference_counts = []
    for domain in sorted({task["domain"] for task in tasks}):
        for kind in sorted({reference_type(task) for task in tasks if task["domain"] == domain}):
            selected = [task for task in tasks if task["domain"] == domain and reference_type(task) == kind]
            reference_counts.append({"domain": domain, "reference_type": kind, "tasks": len(selected),
                                     "roots": len({task["root_id"] for task in selected})})
    errors = [{key: row[key] for key in ("task_id", "root_id", "model", "provider", "domain", "tier", "output_budget_tokens",
               "prefix_before_answer_words", "raw_reasoning_words", "answer_marker_present", "eligible_128", "eligible_256", "eligible_512")}
              for row in rows if row["outcome"] == "completed_incorrect"]
    return {"attempts": rows, "grouped_support": support, "root_support": roots, "word_lengths": word_lengths,
            "paired_cap_attempts": pairs, "paired_cap_summary": transitions, "paired_cap_roots": root_pairs,
            "reference_counts": reference_counts, "completed_errors": errors,
            "outcome_counts": dict(sorted(Counter(row["outcome"] for row in rows).items()))}


def validate_inputs(docs, raw):
    tasks, a, r1 = docs["tasks"]["tasks"], docs["a-results"], docs["r1-results"]
    frozen_statistics.validate_probe_layout(tasks)
    require(a["phase"] == "pilot_v2_stage_A" and r1["phase"] == "pilot_v2_provider_recovery_R1",
            "Only closed development A/R1 inputs are supported")
    require(a["protocol_sha256"] == sha(raw["a-protocol"]) and r1["protocol_sha256"] == sha(raw["r1-protocol"])
            and a["corpus_sha256"] == r1["corpus_sha256"] == sha(raw["tasks"]), "Protocol/corpus/result hashes disagree")
    p = docs["r1-protocol"]
    require(p["recovery"]["parent_results_sha256"] == sha(raw["a-results"]) == r1["parent_results_sha256"]
            and p["measurement"] == docs["a-protocol"]["measurement"]
            and p["measurement"]["observed_prefix_words"] == list(PREFIXES)
            and p["measurement"]["primary_prefix_words"] == 256
            and p["measurement"]["allow_budget_censored_gradeable"] is False,
            "Recovery lineage or prospective measurement criteria changed")
    require(r1["source_inventory_sha256"] == sha(raw["source-inventory"])
            and docs["source-inventory"]["files"]["pilot_v2/statistical_design.py"] == sha(Path(frozen_statistics.__file__).read_bytes()),
            "Frozen statistics source binding changed")
    models = [spec["model"] for spec in p["models"]]
    old_ds = {row["trace_id"]: row for row in a["records"] if row["model"] == DS}
    new_ds = {row["trace_id"]: row for row in r1["records"] if row["model"] == DS}
    require(len(old_ds) == 96 and old_ds == new_ds, "R1 changed the original DeepSeek observations")
    support = frozen_statistics.summarize_support(r1["records"], tasks, models, output_budgets=CAPS,
                prefix_budgets=PREFIXES, stage="development_probe")
    if "input_sha256" in docs["r1-support"]:
        support["input_sha256"] = {"records": sha(raw["r1-results"]), "tasks": sha(raw["tasks"])}
    require(support == docs["r1-support"], "Closed R1 support differs from frozen-statistics replay")
    return tasks, models, support


def check_global_counts(analysis, support):
    for row in analysis["grouped_support"]:
        if row["scope"] != "all":
            continue
        original = next(group for group in support["groups"] if group["model"] == row["model"]
                        and group["output_budget_tokens"] == row["output_budget_tokens"]
                        and group["prefix_budget_words"] == row["prefix_words"])
        for ours, theirs in (("planned_attempts", "planned_attempts"), ("planned_roots", "planned_roots"),
                             ("recorded_attempts", "recorded_attempts"), ("completed_gradeable", "completed_gradeable"),
                             ("censored", "censored_attempts"), ("eligible_traces", "eligible_traces"),
                             ("correct_traces", "correct_traces"), ("error_traces", "error_traces"),
                             ("correct_roots", "correct_roots"), ("error_roots", "error_roots"), ("mixed_roots", "mixed_roots")):
            require(row[ours] == original[theirs], "New descriptive aggregation differs from frozen support: " + ours)


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def markdown(document, output_dir, report_path):
    r1 = document["R1"]
    lines = ["# Post-v2: наблюдаемый отбор завершённых ответов и поддержки ошибок", "",
        "Это новый post-data описательный анализ закрытых A/R1. Он не меняет выборку, метки, исходный failed gate "
        "или протокол. Причины ненаблюдённой правильности обрезанных ответов и причинный эффект cap не идентифицированы.", "",
        "R1 содержит 192 строки на 48 задачах и 24 roots: 96 исходных DeepSeek наблюдений A и 96 новых GPT/AkashML. "
        f"A анализируется отдельно; reuse не удваивает N. Всего A+R1 содержат "
        f"{document['unique_sent_physical_calls_A_union_R1']} различных отправленных физических вызова.", "",
        "## Последовательные потери support", "",
        "| Model | Cap | План | Completed gradeable | Censored | Short at 256: raw / after censor | Eligible256 | Error traces / roots | Correct / mixed roots |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in r1["grouped_support"]:
        if row["scope"] == "all" and row["prefix_words"] == 256:
            lines.append(f"| {row['model'].split('/')[-1]} | {row['output_budget_tokens']} | {row['planned_attempts']} | "
                f"{row['completed_gradeable']} | {row['censored']} | {row['completed_raw_below_prefix']} / "
                f"{row['completed_raw_long_but_preanswer_short']} | {row['eligible_traces']} | "
                f"{row['error_traces']} / {row['error_roots']} | {row['correct_roots']} / {row['mixed_roots']} |")
    lines += ["", "При 256 словах считаются лишь completed+gradeable ответы с достаточным текстом до первого буквального ANSWER:. "
        "Censored ответы имеют null primary correctness; их нельзя считать ошибками или угаданными успехами. "
        "Short raw означает исходный reasoning короче 256 слов; after censor — исходный reasoning достигал 256, "
        "но текст до первого ANSWER: не достигал. Это разные причины prefix-исключения. "
        "Feasibility reference certificate также не является модельной правильностью.", "",
        "## Завершённость по domain", "",
        "| Model | Cap | Domain | Completed / planned | Eligible256 | Completed errors |",
        "|---|---:|---|---:|---:|---:|"]
    for row in r1["grouped_support"]:
        if row["scope"] == "domain" and row["prefix_words"] == 256:
            lines.append(f"| {row['model'].split('/')[-1]} | {row['output_budget_tokens']} | {row['domain']} | "
                f"{row['completed_gradeable']} / {row['planned_attempts']} | {row['eligible_traces']} | {row['completed_incorrect']} |")
    lines += ["", "## Парное сравнение caps", "",
        "Сопоставлены те же task/model и requested seed. Два варианта остаются внутри одного root; ниже показаны "
        "счётчики пар и root blocks, без p-values, CI или предположения независимости 48 вариантов. "
        "Совпадение requested seed не доказывает его фактическое применение внешним backend.", "",
        "| Model | Task pairs / root blocks | Стали completed | Потеряли completed | Roots net completion gain / loss / unchanged | Eligible256 gain / loss pairs |",
        "|---|---:|---:|---:|---:|---:|"]
    for row in r1["paired_cap_summary"]:
        if row["scope"] == "all":
            prefix = next(value for value in row["prefix_transitions"] if value["prefix_words"] == 256)
            lines.append(f"| {row['model'].split('/')[-1]} | {row['planned_task_pairs']} / {row['independent_root_blocks']} | "
                f"{row['completion_gained_pairs']} | {row['completion_lost_pairs']} | {row['roots_with_net_completion_gain']} / "
                f"{row['roots_with_net_completion_loss']} / {row['roots_with_no_net_completion_change']} | "
                f"{prefix['eligible_gained_pairs']} / {prefix['eligible_lost_pairs']} |")
    lines += ["", "Эти переходы описывают фиксированные полученные ответы. Они не позволяют утверждать, "
        "что более высокий cap причинно исправляет или ухудшает ответ либо сколько обрезанных ответов были бы неверны.", "",
        "## Длины и исходные типы задач", "",
        "Подсчёт — Unicode non-whitespace spans, отдельно в исходном reasoning, до первого ANSWER: и после него. "
        "API final-answer channel не добавляется в reasoning; suffix не возвращается в prefix. Отсутствие reasoning "
        "не заменяется нулевой длиной в сводках возвращённых текстов. Suffix оценивается только на traces с ANSWER marker; "
        "raw/prefix — на всех возвращённых reasoning. Эти медианы не требуется складывать. "
        "Квантили описательные, линейная интерполяция, не интервалы уверенности.", "",
        "| Model | Cap | Returned reasoning | С ANSWER marker | Median raw / pre-ANSWER / suffix words |",
        "|---|---:|---:|---:|---:|"]
    for row in r1["word_lengths"]:
        if row["scope"] == "all" and row["outcome"] == "all":
            values = [row[name]["median"] for name in ("raw_reasoning_words", "prefix_before_answer_words", "suffix_after_answer_words")]
            lines.append(f"| {row['model'].split('/')[-1]} | {row['output_budget_tokens']} | {row['returned_reasoning_traces']} | "
                f"{row['first_answer_marker_traces']} | {' / '.join('null' if value is None else str(value) for value in values)} |")
    lines += ["", "| Domain | Reference type | Tasks / roots |", "|---|---|---:|"]
    for row in r1["reference_counts"]:
        lines.append(f"| {row['domain']} | {row['reference_type']} | {row['tasks']} / {row['roots']} |")
    target = os.path.relpath(Path(output_dir) / "selection-analysis.json", Path(report_path).parent).replace("\\", "/")
    errors = r1["completed_errors"]
    eligible_errors = [row for row in errors if row["eligible_256"]]
    lines += ["", "Все strata, отрицательные группы, roots, raw/prefix/suffix длины и парные переходы сохранены в "
        f"[selection-analysis.json]({target}). "
        "Распределения по reference type являются описанием данного набора, а не балансом модельных ошибок.", "",
        f"Завершённых ошибок: {len(errors)}, на {len({row['root_id'] for row in errors})} roots; "
        f"при 256 словах остаётся {len(eligible_errors)} traces на {len({row['root_id'] for row in eligible_errors})} roots. "
        f"Ошибок короче 128 слов: {sum(not row['eligible_128'] for row in errors)}. "
        "Эти счётчики относятся к наблюдённой completed подвыборке и не объясняют контрфактическую правильность censored.", "",
        "Окончательный N и новый test не выбраны. Этот post-data анализ может мотивировать только новый development-дизайн, "
        "который потребуется зафиксировать отдельно до новых ответов. Он не оценивает power, не подбирает test до ошибок, "
        "не проверяет H0–H7, не создаёт человеческое E0 или scientific approval. Новых API вызовов не выполнено."]
    return "\n".join(lines) + "\n"


def build(paths, output_dir, report_path, overwrite_owned=False):
    raw = {name: Path(path).read_bytes() for name, path in paths.items()}
    docs = {name: json.loads(data) for name, data in raw.items()}
    tasks, models, support = validate_inputs(docs, raw)
    a = analyze(docs["a-results"]["records"], tasks, models)
    r1 = analyze(docs["r1-results"]["records"], tasks, models)
    check_global_counts(r1, support)
    document = {"version": VERSION, "status": "post_data_descriptive_only", "primary_prefix_words": 256,
        "prefix_words": list(PREFIXES), "output_caps": list(CAPS), "independent_task_roots": 24,
        "new_API_calls": 0, "unique_sent_physical_calls_A_union_R1": len({row["trace_id"]
            for result in (docs["a-results"], docs["r1-results"]) for row in result["records"] if row.get("attempted") is True}),
        "R1_DeepSeek_A_reuse_not_new_independent_data": True,
        "original_R1_selected_common_output_cap": support["selected_common_output_cap"],
        "original_R1_entire_roster_resolved": support["entire_fixed_roster_resolved"], "no_new_gate_defined": True,
        "final_N_selected": None, "new_test_generated": False, "A": a, "R1": r1,
        "limitations": ["Descriptive post-data counts, not causal cap effects or validated power.",
            "Conditioning on completion, grading and prefix availability can change the observed task/domain composition.",
            "Censored answer correctness is not identified; null is neither false nor true.",
            "Same roots and variants remain dependent; no independence is claimed for repeated model/cap observations.",
            "Operational reference feasibility does not equal model correctness; E0 remains unpassed.",
            "No v1 per-task test labels or new model calls are read or made."],
        "input_sha256": {name: sha(data) for name, data in raw.items()}}
    report = markdown(document, output_dir, report_path)
    require(all(Path(path).read_bytes() == raw[name] for name, path in paths.items()), "Input snapshot changed during analysis")
    output_dir, report_path = Path(output_dir), Path(report_path)
    existing = output_dir.exists() and any(output_dir.iterdir())
    if existing or report_path.exists():
        require(overwrite_owned and (output_dir / "manifest.json").is_file(), "Choose new output paths or explicitly replace owned post-v2 outputs")
        previous = json.loads((output_dir / "manifest.json").read_bytes())
        require(previous.get("version") == VERSION
                and previous.get("inputs") == {name: {"path": location_for_manifest(paths[name]), "sha256": sha(data)} for name, data in raw.items()}
                and {path.name for path in output_dir.iterdir()} == set(previous["outputs"]) | {"manifest.json"}
                and all(sha((output_dir / name).read_bytes()) == digest for name, digest in previous["outputs"].items())
                and report_path.is_file() and sha(report_path.read_bytes()) == previous["report"]["sha256"],
                "Existing outputs were not created by this analysis or have been edited")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"selection-analysis.json": canonical(document) + b"\n"}
    for name, data in outputs.items():
        (output_dir / name).write_bytes(data)
    csv_tables = {"attempt-matrix.csv": r1["attempts"], "grouped-support.csv": r1["grouped_support"],
        "root-support.csv": r1["root_support"], "paired-cap-transitions.csv": r1["paired_cap_attempts"],
        "paired-cap-roots.csv": r1["paired_cap_roots"]}
    for name, rows in csv_tables.items():
        write_csv(output_dir / name, rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    manifest = {"version": VERSION, "script_sha256": sha(Path(__file__).read_bytes()),
        "frozen_statistics_sha256": sha(Path(frozen_statistics.__file__).read_bytes()),
        "inputs": {name: {"path": location_for_manifest(paths[name]), "sha256": sha(data)} for name, data in raw.items()},
        "outputs": {name: sha((output_dir / name).read_bytes()) for name in list(outputs) + list(csv_tables)},
        "report": {"path": location_for_manifest(report_path), "sha256": sha(report_path.read_bytes())},
        "new_API_calls": 0, "new_test_generated": False, "scientific_validity": "not_assessed"}
    (output_dir / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return document


def location_for_manifest(path):
    resolved = Path(path).resolve()
    return resolved.relative_to(PROJECT).as_posix() if resolved.is_relative_to(PROJECT) else resolved.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in INPUT_NAMES:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--overwrite-owned-output", action="store_true", help="Replace only unchanged outputs already identified by this analysis manifest")
    args = parser.parse_args()
    document = build({name: getattr(args, name.replace("-", "_")) for name in INPUT_NAMES}, args.output_dir, args.report,
                     overwrite_owned=args.overwrite_owned_output)
    print(json.dumps({"version": VERSION, "R1_rows": len(document["R1"]["attempts"]),
                      "new_API_calls": 0, "selected_N": None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
