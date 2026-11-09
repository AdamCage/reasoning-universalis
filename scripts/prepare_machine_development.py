"""Prepare one price-selected, finite machine-only annotation allocation offline."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from machine_development.annotation import (
    VERSION, MODEL, PROVIDER, ROLES, audit_item_ids, canonical, rank, request_body,
    require, select_balanced, sha,
)
from resumption.runner import ceiling_rates
from stage0.runner import encode, estimate

CANDIDATES = (24, 48, 72, 96, 120, 144, 168, 192)


def read(path):
    return json.loads(Path(path).read_bytes())


def snapshot_codebook(project=ROOT):
    project = Path(project)
    names = ("design/ANNOTATION_CONFIG.json", "design/ANNOTATION_RESPONSE.schema.json",
             "design/prompts/segment-role-v1.md", "design/ANNOTATION_PROTOCOL.md")
    raw = {name: (project / name).read_bytes() for name in names}
    config = json.loads(raw[names[0]])
    require(config["model"] == MODEL and config["panel_size"] == 5 and config["majority_required"] == 3
            and config["maximum_rounds"] == 2 and config["roles"] == list(ROLES), "Legacy annotation contract changed")
    template = raw[names[2]].decode("utf-8").replace("\r\n", "\n")
    rubric = raw[names[3]].decode("utf-8").replace("\r\n", "\n")
    system = template.split("```text\n", 1)[1].split("\n```", 1)[0]
    definitions = rubric.split("## Словарь\n", 1)[1].split("## Независимость", 1)[0].strip()
    return {"version": VERSION, "system": system, "ontology_definitions": definitions,
        "response_schema": json.loads(raw[names[1]]), "roles": list(ROLES),
        "source_sha256": {name: sha(value) for name, value in raw.items()},
        "definitions_sha256": sha(definitions.encode("utf-8")), "text_decoding": "UTF-8; CRLF-to-LF for method documents only",
        "observed_segment_text_normalized": False}


def load_pool(package):
    # Read a prepared source packet; do not release human roles or import labels.
    spec = importlib.util.spec_from_file_location("machine_source_packet_check", ROOT / "scripts/import_e0_human.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package, manifest, source_map = module.check_package(package)
    prepared = read(package / "coordinator/role-round2-prepared/A/items.json")
    require(len(prepared["items"]) == 200, "Use the fixed prepared200 S2 pool")
    items, mapping = [], {}
    for original in prepared["items"]:
        identity = sha(("machine-s2-v1:" + original["item_id"]).encode("utf-8"))[:24]
        item = {"item_id": identity, "problem_statement": original["problem_statement"],
            "current_segment": {"source_id": identity, "text": original["current_segment"]["text"]},
            "previous_segments": [{"source_id": identity + ":past:" + str(index), "text": value["text"]}
                                  for index, value in enumerate(original["previous_segments"])]}
        role_source = source_map["roles_s2"][original["item_id"]]
        trace_source = source_map["traces"][role_source["trace_item_id"]]
        # Task properties are coordinator provenance only, never prompt fields.
        mapping[identity] = {"source_item_id": original["item_id"], **role_source,
            "source_model": trace_source["model"], "source_provider": trace_source["provider"],
            "source_status": trace_source["source_status"], "task_id": trace_source["task_id"],
            "request_sha256": trace_source["request_sha256"], "response_sha256": trace_source["response_sha256"],
            "source_protocol_sha256": trace_source["source_protocol_sha256"]}
        items.append(item)
    require(len(mapping) == 200 and len({row["root_id"] for row in mapping.values()}) == 24, "Source pool root/identity roster differs")
    return items, mapping, {"path": package.relative_to(ROOT).as_posix() if package.is_relative_to(ROOT) else package.name,
        "manifest_sha256": sha((package / "coordinator/package-manifest.json").read_bytes()),
        "items_sha256": sha((package / "coordinator/role-round2-prepared/A/items.json").read_bytes()),
        "selection": "post-data fixed outcome-independent S2 pool; no human label, release or identity claim"}


def candidate_cost(pool, mapping, codebook, count, price):
    items = select_balanced(pool, mapping, count)
    audits = audit_item_ids(items)
    values, body_bytes = {}, []
    round1 = round2 = Decimal(0)
    for item in items:
        costs = []
        for round_number in (1, 2):
            total = Decimal(0)
            for vote in range(5):
                body = request_body(item, codebook, round_number, vote)
                body_bytes.append(len(encode(body)))
                total += estimate(body, price)
            costs.append(total)
        round1 += costs[0]
        round2 += costs[1]
        values[item["item_id"]] = costs[0]
    audit = sum((values[identity] for identity in audits), Decimal(0))
    distribution = Counter(Counter(mapping[item["item_id"]]["root_id"] for item in items).values())
    return {"items": count, "root_blocks": 24, "segments_per_root": count // 24 if count != 200 else None,
        "segments_per_root_distribution": {str(key): value for key, value in sorted(distribution.items())},
        "first_round_calls": 5 * count, "maximum_conditional_second_round_calls": 5 * count,
        "audit_items": len(audits), "audit_calls": 5 * len(audits), "maximum_calls": 10 * count + 5 * len(audits),
        "round1_reservation_rub": str(round1), "maximum_round2_reservation_rub": str(round2),
        "audit_reservation_rub": str(audit), "worst_case_reservation_rub": str(round1 + round2 + audit),
        "encoded_request_bytes_min": min(body_bytes), "encoded_request_bytes_max": max(body_bytes),
        "maximum_input_token_upper_bound": max(body_bytes) + 2048,
        "input_token_upper_bound_sum_all_primary_calls": sum(value + 2048 for value in body_bytes),
        "selected_item_ids": [item["item_id"] for item in items], "audit_item_ids": audits}


def build(package, metadata_path, ledger_path, output, additional_cap=Decimal(2400), total_cap=Decimal(3300)):
    output = Path(output)
    additional_cap = Decimal(str(additional_cap))
    total_cap = Decimal(str(total_cap))
    require(additional_cap == Decimal(2400) and total_cap == Decimal(3300),
            "Full200 allocation requires the explicitly accepted3300 total/2400 additional authorization")
    pool, mapping, source = load_pool(package)
    codebook = snapshot_codebook()
    metadata_bytes, ledger_bytes = Path(metadata_path).read_bytes(), Path(ledger_path).read_bytes()
    metadata, ledger = json.loads(metadata_bytes), json.loads(ledger_bytes)
    require(metadata["endpoint"] == "/models/" + MODEL + "/endpoints" and metadata.get("paid_calls") == 0
            and metadata["response"]["http_status"] == 200 and not metadata["response"].get("json", {}).get("error"),
            "Use the current metadata-only exact-route quote")
    price = ceiling_rates(metadata["response"], PROVIDER)
    amounts = [Decimal(row["charged_or_reserved_rub"]) for row in ledger]
    require(all(value.is_finite() and value >= 0 for value in amounts), "Invalid existing shared commitment")
    charged = sum(amounts, Decimal(0))
    require(charged + additional_cap <= total_cap, "The additional envelope would exceed the existing total budget")
    candidates = [candidate_cost(pool, mapping, codebook, count, price) for count in (*CANDIDATES, 200)]
    for candidate in candidates:
        candidate["fits_fixed_additional_cap"] = Decimal(candidate["worst_case_reservation_rub"]) <= additional_cap
        candidate["fits_historical_900_proposal"] = Decimal(candidate["worst_case_reservation_rub"]) <= Decimal(900)
    historical = [candidate for candidate in candidates if candidate["items"] in CANDIDATES and candidate["fits_historical_900_proposal"]]
    selected = next(candidate for candidate in candidates if candidate["items"] == 200)
    require(selected["fits_fixed_additional_cap"], "The accepted full200 worst case does not fit; do not dispatch or adapt after outcomes")
    chosen = select_balanced(pool, mapping, selected["items"])
    selected_mapping = {item["item_id"]: mapping[item["item_id"]] for item in chosen}
    # Add domain/tier from the already bound original corpus, outside prompts.
    provenance = read(Path(package) / "coordinator/source-provenance.json")
    corpus_path = ROOT / provenance["sources"]["tasks"]["path"]
    corpus = {task["task_id"]: task for task in read(corpus_path)["tasks"]}
    for value in mapping.values():
        task = corpus[value["task_id"]]
        value.update(domain=task["domain"], tier=task.get("tier", task.get("difficulty", "unknown")))
    input_document = {"schema_version": 1, "version": VERSION, "status": "machine_only_development_no_human_gold",
        "items": chosen, "audit_item_ids": selected["audit_item_ids"], "planned_items": len(chosen),
        "source_pool_items": 200, "root_blocks": 24, "source_package_manifest_sha256": source["manifest_sha256"],
        "codebook_sha256": sha(canonical(codebook) + b"\n"), "human_gold": "not_created", "E0": "not_passed"}
    table = {"schema_version": 1, "model": MODEL, "provider": PROVIDER, "metadata_sha256": sha(metadata_bytes),
        "prompt_rub_per_token": str(price[0]), "completion_rub_per_token": str(price[1]),
        "shared_ledger_sha256": sha(ledger_bytes), "shared_ledger_rows": len(ledger),
        "charged_or_reserved_before_machine_rub": str(charged), "additional_cap_rub": str(additional_cap),
        "absolute_stage_ceiling_rub": str(charged + additional_cap), "global_cap_rub": str(total_cap),
        "selection_rule": "complete fixed200 pool accepted with increased funding BEFORE any new machine calls; no outcome-dependent selection",
        "superseded_900_cost_only_rule": "largest N in24..192 step24 fitting both rounds plus fixed10% audit",
        "superseded_900_selected_items": max((value["items"] for value in historical), default=None),
        "candidates": candidates, "selected_items": len(chosen), "selected_maximum_calls": selected["maximum_calls"],
        "selected_worst_case_reservation_rub": selected["worst_case_reservation_rub"],
        "oversized_policy": "No dispatch and technical unresolved; full planned quote remains a conservative upper bound",
        "paid_calls": 0, "new_deadline_authorization": "separate execution protocol required"}
    outputs = {"input-items.json": input_document, "pool-items.json": {"version": VERSION, "items": pool},
        "machine-mapping.json": {"schema_version": 1, "items": selected_mapping, "source": source},
        "pool-mapping.json": {"schema_version": 1, "items": mapping, "source": source},
        "codebook.json": codebook, "candidate-cost-table.json": table,
        "selection-decision.json": {"rule": table["selection_rule"], "selected_items": len(chosen),
            "root_blocks": 24, "segments_per_root": None,
            "segments_per_root_distribution": selected["segments_per_root_distribution"], "audit_items": len(selected["audit_item_ids"]),
            "maximum_calls": selected["maximum_calls"], "worst_case_reservation_rub": selected["worst_case_reservation_rub"],
            "additional_cap_rub": str(additional_cap), "metadata_sha256": sha(metadata_bytes), "paid_calls": 0}}
    require(not any((output / name).exists() for name in list(outputs) + ["input-manifest.json"]), "Do not overwrite a prior machine allocation")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        (output / name).write_bytes(canonical(value) + b"\n")
    manifest = {"version": VERSION, "creator_sha256": sha(Path(__file__).read_bytes()),
        "annotation_module_sha256": sha((ROOT / "machine_development/annotation.py").read_bytes()),
        "source": source, "metadata_sha256": sha(metadata_bytes), "shared_ledger_sha256": sha(ledger_bytes),
        "files": {name: sha((output / name).read_bytes()) for name in outputs}, "paid_calls": 0,
        "E0": "not_passed", "human_gold": "not_created"}
    (output / "input-manifest.json").write_bytes(canonical(manifest) + b"\n")
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument("--route-metadata", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    table = build(args.source_package, args.route_metadata, args.ledger, args.output)
    print(json.dumps({key: table[key] for key in ("selected_items", "selected_maximum_calls", "selected_worst_case_reservation_rub", "paid_calls")}))


if __name__ == "__main__":
    main()
