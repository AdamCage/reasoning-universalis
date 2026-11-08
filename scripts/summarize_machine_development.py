"""Strict offline machine-annotation summary; no dispatch, repair or E0 claim."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from machine_development import annotation as ann
from scripts.collect_machine_development import _MachineCore, KIND, MODEL, PROVIDER
from resumption.runner import ceiling_rates
from stage0.runner import encode, estimate

VERSION = "machine-development-offline-summary-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def amount(value):
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, "Invalid financial amount")
    return result


def ledger_totals(rows):
    total = reported = margin = unknown = Decimal(0)
    for row in rows:
        value = amount(row["charged_or_reserved_rub"])
        require(value >= amount(row["reservation_rub"]), "A retained reservation was reduced")
        total += value
        if row.get("reported_cost_rub") is None:
            unknown += value
        else:
            cost = amount(row["reported_cost_rub"])
            require(cost <= value, "Reported billing exceeds retained obligation")
            reported += cost
            margin += value - cost
    require(total == reported + margin + unknown, "Budget decomposition failed")
    return {"rows": len(rows), "charged_or_reserved_rub": str(total), "reported_cost_rub": str(reported),
            "retained_margin_above_reported_rub": str(margin), "commitments_without_reported_cost_rub": str(unknown),
            "states": dict(sorted(Counter(row["state"] for row in rows).items()))}


def verify_scope(scope, protocol_path, input_path, codebook_path, mapping_path, ledger_path, *, source_root=ROOT, calls=None):
    scope, source_root = Path(scope), Path(source_root)
    calls = Path(calls) if calls is not None else scope.parent.parent / "calls"
    paths = {"protocol": Path(protocol_path), "items": Path(input_path), "codebook": Path(codebook_path),
             "mapping": Path(mapping_path), "ledger": Path(ledger_path), "results": scope / "results.json",
             "launch_ledger": scope / "ledger-launch.json", "inventory": scope / "source-inventory.json",
             "plan": scope / "dispatch-plan.json"}
    registry_path = scope.parent / "condition-v1.json"
    if registry_path.is_file():
        paths["condition_registry"] = registry_path
    raw = {name: path.read_bytes() for name, path in paths.items()}
    docs = {name: read(path) for name, path in paths.items()}
    p, result, inventory = docs["protocol"], docs["results"], docs["inventory"]
    require(p["status"] == "prospective_frozen_machine_development" and result["phase"] == "machine_development_annotation",
            "Only closed, frozen machine-development observations are supported")
    require(raw["protocol"] == (scope / "protocol.json").read_bytes()
            and result["protocol_sha256"] == ann.sha(raw["protocol"])
            and result["items_sha256"] == ann.sha(raw["items"]) == p["inputs"]["file_sha256"]
            and result["source_inventory_sha256"] == ann.sha(raw["inventory"])
            and result["dispatch_plan_sha256"] == ann.sha(raw["plan"]), "Result/protocol/input/source/roster hashes disagree")
    for name in ("items", "codebook", "mapping"):
        spec = p["inputs"] if name == "items" else p["inputs"][name]
        require(ann.sha(raw[name]) == spec["file_sha256"] and raw[name] == (scope / (name + ".json")).read_bytes(),
                "Public and bound machine input differ: " + name)
    for name, digest in inventory["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts
                and ann.sha((scope / "source" / relative).read_bytes()) == digest
                and ann.sha((source_root / relative).read_bytes()) == digest,
                "Frozen machine source/config bytes changed: " + name)
    inputs, codebook, mapping = docs["items"], docs["codebook"], docs["mapping"]["items"]
    items = inputs["items"]
    require(len(items) == len({item["item_id"] for item in items}) == p["inputs"]["items"]
            and set(mapping) == {item["item_id"] for item in items}, "Machine item/mapping roster changed")
    core = _MachineCore.__new__(_MachineCore)
    core.protocol, core.protocol_digest = p, ann.sha(raw["protocol"])
    core.items_digest, core.source_inventory_digest = ann.sha(raw["items"]), ann.sha(raw["inventory"])
    core.item_lookup = {item["item_id"]: item for item in items}
    core.audit_ids = ann.audit_item_ids(items)
    core.rendered = {identity: ann.render_item(item, codebook, max_input_bytes=p["generation"].get("maximum_input_utf8_bytes"))
                     for identity, item in core.item_lookup.items()}
    expected_plan = core._make_plan()
    require(encode(expected_plan) == raw["plan"] and inputs["audit_item_ids"] == core.audit_ids,
            "The exact planned primary/conditional/audit identities changed")
    n, maximum = len(items), p["allocation"]["maximum_calls"]
    require(maximum == 10 * n + 5 * len(core.audit_ids) <= 2100 and result["maximum_calls"] == maximum,
            "Machine allocation exceeds its prospective finite roster")
    if not p.get("synthetic_fixture"):
        require(n == 200 and p["parent"]["launch_ledger_rows"] == 984
                and Decimal(p["parent"]["launch_charged_or_reserved_rub"]) == Decimal("823.5589067445220"),
                "The accepted full200/984-row historical condition changed")
    require(result.get("E0") == "not_passed" and result.get("human_gold") == "not_created"
            and result.get("audit_effect_on_primary_consensus") == "none", "Machine consensus was falsely promoted or repaired by audits")
    closed = datetime.fromisoformat(result["completed_utc"].replace("Z", "+00:00"))
    require(closed.tzinfo is not None, "Closed results need a timezone")
    launch, ledger = docs["launch_ledger"], docs["ledger"]
    require(ann.sha(raw["launch_ledger"]) == p["parent"]["launch_ledger_sha256"]
            and len(launch) == p["parent"]["launch_ledger_rows"] and ledger[:len(launch)] == launch,
            "Earlier shared-ledger obligations changed or disappeared")
    index = {row["id"]: row for row in ledger}
    require(len(index) == len(ledger), "Repeated shared reservation identity")
    before, final, delta = ledger_totals(launch), ledger_totals(ledger), ledger_totals(ledger[len(launch):])
    require(Decimal(before["charged_or_reserved_rub"]) == Decimal(p["parent"]["launch_charged_or_reserved_rub"])
            and Decimal(final["charged_or_reserved_rub"]) == Decimal(result["charged_or_reserved_rub"]),
            "Closed result and retained ledger snapshot are not synchronized")
    planned = {cell["call_id"]: cell for cell in expected_plan["cells"]}
    registry = result["all_planned_calls"]
    require(len(registry) == maximum and [row["call_id"] for row in registry] == [cell["call_id"] for cell in expected_plan["cells"]],
            "All requested/conditional/audit cells must remain exactly once in planned order")
    item_results = {item["item_id"]: item for item in result["items"]}
    require(len(item_results) == len(result["items"]) == n and set(item_results) == set(core.item_lookup)
            and set(result["audits"]) == set(core.audit_ids), "Primary or fixed audit item denominator changed")
    executed, primary, votes = {}, {}, {}
    for identity, item_result in item_results.items():
        first, second = item_result["round1"], item_result["round2"]
        require(len(first) == 5 and [row["vote_index"] for row in first] == list(range(5))
                and all(row["item_id"] == identity and row["round_number"] == 1 and row["audit"] is False for row in first),
                "First-round requested denominator or vote order changed")
        first_votes = [row["vote"] for row in first]
        should_repeat = ann.panel_result(first_votes, 1).get("next_round") == 2
        require(len(second) == (5 if should_repeat else 0), "Conditional second panel was omitted or opened after a technical/resolved first panel")
        if second:
            require([row["vote_index"] for row in second] == list(range(5))
                    and all(row["item_id"] == identity and row["round_number"] == 2 and row["audit"] is False for row in second),
                    "Second-round item/seed order changed")
        calculated = ann.resolve_primary(first_votes, [row["vote"] for row in second] if second else None)
        require(calculated == item_result["primary"], "Saved primary consensus differs from frozen, unpooled panel resolution")
        primary[identity] = calculated
        votes[identity] = {1: first_votes, **({2: [row["vote"] for row in second]} if second else {})}
        for row in first + second:
            require(row["call_id"] not in executed, "A physical vote was reused as a second observation")
            executed[row["call_id"]] = row
    for identity, audit in result["audits"].items():
        eligible = all(value is not None for value in votes[identity][1])
        require(len(audit["votes"]) == (5 if eligible else 0), "Fixed audit repaired or retried a technically incomplete original panel")
        for row in audit["votes"]:
            require(row["item_id"] == identity and row["round_number"] == 1 and row["audit"] is True
                    and row["call_id"] not in executed, "Audit is not a distinct first-round same-seed observation")
            executed[row["call_id"]] = row
    reservations = set()
    for saved in registry:
        cell = planned[saved["call_id"]]
        directory = calls / cell["call_id"]
        intent_path = scope / "intents" / (cell["call_id"] + ".json")
        if cell["call_id"] not in executed:
            require(saved == {**cell, "technical_status": "not_scheduled_by_fixed_condition", "request_state": "not_dispatched", "vote": None}
                    and not directory.exists() and not intent_path.exists(), "A condition-not-needed cell hides an actual attempt")
            continue
        require(saved == executed[cell["call_id"]], "Registry and panel vote records differ")
        if saved["technical_status"] in ("valid", "invalid"):
            request_bytes, response_bytes = (directory / "request.json").read_bytes(), (directory / "response.json").read_bytes()
            context, raw_result = read(directory / "reservation.json"), read(directory / "result.json")
            response = read(directory / "response.json")
            require(request_bytes == encode(core.body(cell)) and ann.sha(request_bytes) == cell["request_sha256"] == saved["request_sha256"]
                    and ann.sha(response_bytes) == saved["response_sha256"] == raw_result["response_sha256"]
                    and raw_result["response"] == response and all(raw_result.get(key) == value for key, value in context.items()),
                    "Raw vote request/response/reservation binding changed")
            require(context["protocol_sha256"] == core.protocol_digest and context["items_sha256"] == core.items_digest
                    and context["source_inventory_sha256"] == core.source_inventory_digest
                    and context["kind"] == KIND and context["identity"] == cell["identity"]
                    and context["seed_requested"] == cell["seed"] and context["model"] == MODEL and context["provider"] == PROVIDER
                    and all(context[key] == cell[key] for key in ("call_id", "item_id", "round_number", "vote_index", "audit"))
                    and context["quote_namespace"] == "machine-development/" + core.protocol_digest + "/metadata/history",
                    "Physical annotation vote lost its frozen source/route/seed identity")
            require(read(intent_path) == {"schema_version": 1, "cell": cell, "protocol_sha256": core.protocol_digest,
                    "source_inventory_sha256": core.source_inventory_digest, "items_sha256": core.items_digest}, "Pre-network logical vote intent changed")
            require(ann.canonical(core._parsed(cell, raw_result)) == ann.canonical(saved), "Strict frozen content-only vote parsing differs from saved labels")
            quote_path = scope / "metadata/history" / (context["quote_receipt_sha256"] + ".json")
            quote = read(quote_path)
            require(ann.sha(quote_path.read_bytes()) == context["quote_receipt_sha256"]
                    and quote["endpoint"] == "/models/" + MODEL + "/endpoints" and quote["response"]["http_status"] == 200
                    and not quote["response"].get("json", {}).get("error"), "Pinned quotation receipt changed")
            price = ceiling_rates(quote["response"], PROVIDER)
            require(price == (Decimal(context["quoted_prompt_rub_per_token"]), Decimal(context["quoted_completion_rub_per_token"]))
                    and estimate(core.body(cell), price) == Decimal(context["reservation_rub"]), "Conservative vote reservation differs from its provider quote")
            cost_path = scope / "cost-plans" / (context["cost_plan_sha256"] + ".json")
            cost = read(cost_path)
            require(ann.sha(cost_path.read_bytes()) == context["cost_plan_sha256"]
                    and cost["protocol_sha256"] == core.protocol_digest and cost["source_inventory_sha256"] == core.source_inventory_digest
                    and cost["dispatch_plan_sha256"] == result["dispatch_plan_sha256"]
                    and {row["call_id"] for row in cost["cells"]} == set(planned)
                    and len(cost["cells"]) == maximum and cost["full_roster_fits_stage_budget"] is True,
                    "The complete worst-case quotation was not bound before dispatch")
            reservation_id = context["reservation_id"]
            require(reservation_id == saved["reservation_id"] and reservation_id in index
                    and Decimal(index[reservation_id]["reservation_rub"]) == Decimal(context["reservation_rub"]),
                    "A physical vote lost or changed its retained shared reserve")
            require(reservation_id not in reservations, "Two physical votes share one budget reservation")
            reservations.add(reservation_id)
        else:
            reserved, intended = (directory / "reservation.json").is_file(), intent_path.is_file()
            expected = "unresolved_attempt" if reserved else "unresolved_intent" if intended else "not_dispatched"
            require(saved["technical_status"] == expected and saved.get("vote") is None, "Unsent/unknown vote was silently relabelled")
            if reserved:
                context = read(directory / "reservation.json")
                identity = context["reservation_id"]
                require(identity in index and index[identity]["state"] in ("pending", "unknown") and identity not in reservations,
                        "Unknown vote lost its reserve or duplicated another vote")
                reservations.add(identity)
    require(reservations == {row["id"] for row in ledger[len(launch):]}, "New ledger rows are missing, duplicated or unrelated to this finite roster")
    require(not reservations or "condition_registry" in docs and docs["condition_registry"] == core._condition_registry(),
            "The paid condition does not own its exact immutable shared-state registry")
    require(all(path.read_bytes() == raw[name] for name, path in paths.items()), "Input snapshot changed during offline validation")
    budget = {"launch": before, "final": final, "since_launch": delta, "launch_prefix_preserved": True,
        "cap_total_rub": p["budget"]["cap_total_rub"], "absolute_stage_ceiling_rub": p["budget"]["absolute_stage_ceiling_rub"],
        "within_total_cap": Decimal(final["charged_or_reserved_rub"]) <= Decimal(p["budget"]["cap_total_rub"]),
        "within_stage_cap": Decimal(final["charged_or_reserved_rub"]) <= Decimal(p["budget"]["absolute_stage_ceiling_rub"])}
    return docs, raw, paths, items, mapping, primary, votes, budget


def audit_summary(result, votes):
    items = []
    primary_rows = {item["item_id"]: item["round1"] for item in result.get("items", [])}
    for identity, audit in sorted(result["audits"].items()):
        first = votes[identity][1]
        repeated = [row["vote"] for row in audit["votes"]]
        pairs = [(left, right) for left, right in zip(first, repeated) if left is not None and right is not None]
        initial, later = ann.panel_result(first, 1), ann.panel_result(repeated, 1)
        comparable = initial.get("role") is not None and later.get("role") is not None
        raw_pairs = [(left.get("response_sha256"), right.get("response_sha256"))
                     for left, right in zip(primary_rows.get(identity, []), audit["votes"])
                     if left.get("response_sha256") is not None and right.get("response_sha256") is not None]
        items.append({"item_id": identity, "planned_audit_votes": 5, "represented_audit_attempts": len(repeated),
            "valid_audit_votes": sum(value is not None for value in repeated), "comparable_valid_vote_pairs": len(pairs),
            "same_primary_role_vote_pairs": sum(left["primary_role"] == right["primary_role"] for left, right in pairs),
            "identical_parsed_vote_pairs": sum(left == right for left, right in pairs),
            "comparable_raw_response_pairs": len(raw_pairs), "identical_raw_response_pairs": sum(left == right for left, right in raw_pairs),
            "original_round1_status": initial["status"], "audit_round1_status": later["status"],
            "comparable_consensus": comparable, "same_consensus_role": initial["role"] == later["role"] if comparable else None})
    return {"preselected_audit_items": len(items), "planned_audit_votes": 5 * len(items), "items": items,
        "comparable_consensus_items": sum(row["comparable_consensus"] for row in items),
        "same_consensus_items": sum(row["same_consensus_role"] is True for row in items),
        "primary_consensus_updated": False, "comparison": "original round1 versus one fixed same-input/seed/route round1 audit; never pooled"}


def source_trace_lengths(mapping_document, items, *, source_root=ROOT):
    """Read only the pinned old source map, never another person's labels."""
    source = mapping_document.get("source")
    if not source:
        return {}
    package = Path(source_root) / source["path"]
    manifest_path = package / "coordinator/package-manifest.json"
    require(ann.sha(manifest_path.read_bytes()) == source["manifest_sha256"], "Original source packet manifest changed")
    manifest = read(manifest_path)
    map_path = package / "coordinator/source-map.json"
    expected = next(row["sha256"] for row in manifest["files"] if row["path"] == "coordinator/source-map.json")
    require(ann.sha(map_path.read_bytes()) == expected, "Original exact source coordinates changed")
    original = read(map_path)
    lengths = {}
    for item in items:
        identity = item["item_id"]
        mapping = mapping_document["items"][identity]
        previous = original["roles_s2"][mapping["source_item_id"]]
        require(all(mapping[key] == previous[key] for key in ("root_id", "physical_trace_id", "segment_id", "char_start", "char_end", "text_sha256"))
                and ann.sha(item["current_segment"]["text"].encode("utf-8")) == previous["text_sha256"],
                "Machine item differs from its exact original S2 text/offsets")
        total = original["traces"][previous["trace_item_id"]]["source_text_characters"]
        require(type(total) is int and 0 <= previous["char_start"] < previous["char_end"] <= total,
                "Source code-point coordinates are outside the full trace")
        lengths[identity] = total
    return lengths


def source_descriptives(items, mapping, primary, trace_lengths=None):
    groups = defaultdict(Counter)
    details = []
    trace_lengths = trace_lengths or {}
    for item in items:
        identity, text = item["item_id"], item["current_segment"]["text"]
        source = mapping[identity]
        size = len(text)
        length_bin = "1-128cp" if size <= 128 else "129-512cp" if size <= 512 else "513-2000cp" if size <= 2000 else ">2000cp"
        total = trace_lengths.get(identity)
        relative = source["char_start"] / total if total is not None else None
        position_bin = str(min(int(relative * 5), 4) * 20) + "-" + str((min(int(relative * 5), 4) + 1) * 20) + "%" if relative is not None else "unavailable"
        row = {"item_id": identity, "root_id": source["root_id"], "source_model": source.get("source_model", "unknown"),
            "source_provider": source.get("source_provider", "unknown"), "source_status": source.get("source_status", "unknown"),
            "domain": source.get("domain", "unknown"), "tier": source.get("tier", "unknown"),
            "segment_characters": size, "segment_words": len(text.split()), "length_bin": length_bin,
            "char_start": source.get("char_start"), "char_end": source.get("char_end"),
            "full_trace_characters": total, "relative_position_start": relative,
            "relative_position_end": source["char_end"] / total if total is not None else None,
            "position_bin": position_bin,
            "relative_position_status": "retrospective_exact_full_trace_coordinate" if total is not None else "full_trace_length_unavailable",
            "primary_status": primary[identity]["status"], "consensus_role": primary[identity].get("role")}
        for field in ("source_model", "source_status", "domain", "tier", "length_bin", "position_bin", "root_id"):
            groups[field + ":" + str(row[field])]["planned_items"] += 1
            groups[field + ":" + str(row[field])][row["primary_status"]] += 1
            if row["consensus_role"] is not None:
                groups[field + ":" + str(row[field])]["role:" + row["consensus_role"]] += 1
        details.append(row)
    for values in groups.values():
        for role in ann.ROLES:
            values.setdefault("role:" + role, 0)
    return {"items": details, "strata": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
        "position_scope": "Retrospective full-trace coordinates only, never supplied in annotation prompts or treated as online prediction features; unavailable lengths remain null",
        "natural_role_prevalence_estimated": False}


def build(scope, protocol, inputs, codebook, mapping, ledger, output_dir, report, *, source_root=ROOT, calls=None):
    docs, raw, paths, items, source_mapping, primary, votes, budget = verify_scope(
        scope, protocol, inputs, codebook, mapping, ledger, source_root=source_root, calls=calls)
    result = docs["results"]
    summary = ann.summarize(items, primary, votes, source_mapping)
    summary["audit"] = audit_summary(result, votes)
    summary["call_coverage"] = {"all_planned_slots": len(result["all_planned_calls"]),
        "first_round_planned": 5 * len(items), "conditional_round2_planned": 5 * len(items), "audit_planned": 5 * len(result["audits"]),
        "by_phase": {phase: dict(sorted(Counter(row["technical_status"] for row in result["all_planned_calls"]
            if ("audit" if row["audit"] else "round2" if row["round_number"] == 2 else "round1") == phase).items()))
            for phase in ("round1", "round2", "audit")},
        "transport_unknown_slots": sum(row.get("request_state") == "unknown" for row in result["all_planned_calls"])}
    summary["requested_reasoning_disabled"] = True
    summary["effective_reasoning_mode"] = "not_independently_confirmed"
    summary["votes_with_returned_reasoning_flag"] = sum(row.get("returned_reasoning_present") is True for row in result["all_planned_calls"])
    lengths = source_trace_lengths(docs["mapping"], items, source_root=source_root)
    summary["source_descriptives"] = source_descriptives(items, source_mapping, primary, lengths)
    summary["protocol_sha256"] = result["protocol_sha256"]
    summary["input_sha256"] = {name: ann.sha(value) for name, value in raw.items()}
    output_dir, report = Path(output_dir), Path(report)
    filenames = ("results.json", "summary.json", "budget-final.json", "summary-manifest.json")
    require(not any((output_dir / name).exists() for name in filenames) and not report.exists(), "Choose new machine-summary outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_bytes(raw["results"])
    (output_dir / "summary.json").write_bytes(ann.canonical(summary) + b"\n")
    (output_dir / "budget-final.json").write_bytes(ann.canonical(budget) + b"\n")
    lines = ["# Машинная development-разметка наблюдаемого текста", "",
        f"Фиксировано {len(items)} S2 items на {summary['distinct_root_blocks']} root blocks; "
        f"максимум {len(result['all_planned_calls'])} primary/conditional/audit slots. Новых задач или человеческих ответов этот отчёт не создаёт.", "",
        "Это один multiseed DeepSeek/BytePlus измеритель. Его согласие не является точностью, human gold, независимой репликацией или E0 pass.", "",
        "| Primary status | Items / all planned |", "|---|---:|"]
    for status, count in summary["primary_status_counts"].items():
        lines.append(f"| {status} | {count} / {len(items)} |")
    lines += ["", "| Machine consensus role | Items / all planned |", "|---|---:|"]
    for role, count in summary["consensus_roles"].items():
        lines.append(f"| {role} | {count} / {len(items)} |")
    lines += ["", "| Phase | Planned | Technical status counts |", "|---|---:|---|"]
    for phase, count in (("round1", 5 * len(items)), ("round2", 5 * len(items)), ("audit", 5 * len(result["audits"]))):
        lines.append(f"| {phase} | {count} | {json.dumps(summary['call_coverage']['by_phase'][phase], ensure_ascii=False)} |")
    lines += ["", "Второй semantic раунд разрешён только после пяти технически valid голосов без majority. "
        "Неполная панель не повторяется семантически; результаты раундов не объединяются. Все ненужные conditional и "
        "заблокированные audit slots остаются в знаменателях. Audit сравнивает исходный round1 с одним повтором тех же seeds "
        "и никогда не исправляет primary consensus.", "",
        f"Общий ledger: {budget['final']['charged_or_reserved_rub']} RUB charged-or-reserved; reported cost "
        f"{budget['final']['reported_cost_rub']} RUB, резерв сверх reported {budget['final']['retained_margin_above_reported_rub']} RUB; "
        f"без reported cost удерживается {budget['final']['commitments_without_reported_cost_rub']} RUB. "
        f"Все {budget['launch']['rows']} старые строки сохранены. Это не окончательный биллинг.", "",
        "JSON сохраняет per-role counts, entropy, полные/неполные панели, same-model Cohen/Fleiss agreement и "
        "описательный task-root bootstrap с явными undefined случаями. Source-generator/domain/tier/length/root strata "
        "не означают естественную распространённость ролей. DeepSeek source-generator отдельно виден для generator=annotator bias.", "",
        "Relative position — только retrospective координата в уже наблюдённой полной текстовой записи, не online feature; "
        "она не передавалась разметчику. Выбранные S2 segments разрежены: transitions/dwell здесь не оцениваются. "
        "Сравнение raw response SHA включает API-envelope поля; отличие hash само по себе не означает изменение роли.", "",
        f"Reasoning запрошен disabled; returned-reasoning flag присутствует у {summary['votes_with_returned_reasoning_flag']} votes. "
        "Для роли читался только завершённый content JSON. Эффективный внутренний режим не подтверждён независимо. "
        "Transport unknown и отсутствие reported billing учитываются раздельно.", "",
        "E0 не пройден, human reference отложен, human gold не создан. Функциональная онтология и machine consensus "
        "не подтверждают H0–H7, stopping policy, научный review или будущий detector. Новый N/test не выбран. "
        "Этот consumer не выполняет API-запросов."]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    manifest = {"version": VERSION, "script_sha256": ann.sha(Path(__file__).read_bytes()),
        "inputs": {name: {"path": str(path), "sha256": ann.sha(raw[name])} for name, path in paths.items()},
        "outputs": {name: ann.sha((output_dir / name).read_bytes()) for name in filenames if name != "summary-manifest.json"},
        "report_sha256": ann.sha(report.read_bytes()), "new_API_calls": 0, "E0": "not_passed", "human_gold": "not_created"}
    (output_dir / "summary-manifest.json").write_bytes(ann.canonical(manifest) + b"\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scope", "protocol", "input-items", "codebook", "mapping", "ledger", "output-dir", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--calls", type=Path)
    args = parser.parse_args()
    result = build(args.scope, args.protocol, args.input_items, args.codebook, args.mapping, args.ledger,
                   args.output_dir, args.report, source_root=args.source_root, calls=args.calls)
    print(json.dumps({"planned_items": result["planned_items"], "E0": result["E0"], "new_API_calls": 0}))


if __name__ == "__main__":
    main()
