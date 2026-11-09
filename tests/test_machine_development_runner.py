"""Fake transport only: finite machine annotation and retained financial history."""
import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import threading
import unittest

from machine_development import annotation
from scripts.collect_machine_development import MachineDevelopmentRunner, MachineSettings, MODEL, PROVIDER, STATUS
from scripts.prepare_machine_development import snapshot_codebook
from scripts.pilot_v2_ledger_io_compat_v1 import SOURCE_PATH, VERSION
from resumption.runner import sha
from stage0.runner import StopRun, capture_body, encode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pilot_v2_runner as parent_fixtures


class FakeAnnotationTransport:
    def __init__(self):
        self.paid = []
        self.metadata_calls = 0
        self.price = "0.000001"
        self.mode = "majority"
        self.barrier = None

    def __call__(self, path, key=None, body=None, timeout=30):
        if path.endswith("/endpoints"):
            self.metadata_calls += 1
            return {"http_status": 200, "json": {"data": {"endpoints": [
                {"provider_name": PROVIDER, "pricing_units": {"prompt": "token", "completion": "token"},
                 "pricing": {"prompt": self.price, "completion": self.price}}]}}}
        self.paid.append(copy.deepcopy(body))
        if self.barrier is not None:
            self.barrier.wait(timeout=10)
        if self.mode == "unknown":
            return {"http_status": None, "json": {}, "network_error": "SyntheticTimeout"}
        if self.mode == "null_json":
            return {"http_status": 200, "json": None, "raw_body": "null"}
        user = json.loads(body["messages"][1]["content"])
        seed = body["seed"]
        role = annotation.ROLES[seed - annotation.SEEDS[0][0]] if self.mode == "no_majority" and seed in annotation.SEEDS[0] else "planning"
        vote = {"item_id": user["item_id"], "primary_role": role, "secondary_roles": [], "confidence": "low",
                "reason_code": "strategy", "evidence_quotes": [{"source_id": user["item_id"], "quote": user["current_segment"]["text"][:30]}]}
        content = "not JSON" if self.mode == "malformed" else json.dumps(vote, ensure_ascii=False)
        message = {"content": content}
        if self.mode == "reasoning":
            message["reasoning"] = "Unexpected visible output, never parsed as the vote."
        payload = {"model": MODEL, "provider": "WrongProvider" if self.mode == "drift" else PROVIDER,
                   "usage": {"cost": "2500" if self.mode == "overrun" else "0.001"},
                   "choices": [{"finish_reason": "length" if self.mode == "length" else "stop", "message": message}]}
        if self.mode == "invalid_usage":
            payload["usage"] = ["invalid usage object"]
        return {"http_status": 200, **capture_body(encode(payload), key)}


class MachineDevelopmentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.parent = parent_fixtures.PilotV2RunnerTests()
        self.parent.setUp()
        self.addCleanup(self.parent.doCleanups)
        self.project, self.state = self.parent.project, self.parent.state
        required = ["scripts/collect_machine_development.py", SOURCE_PATH, "scripts/prepare_machine_development.py",
                    "stage2/__init__.py", "stage2/annotation.py", "stage2/observations.py",
                    "stage0/__init__.py", "stage0/tasks.py",
                    "measurement/__init__.py", "measurement/core.py", "measurement/lexical.py",
                    "design/ANNOTATION_CONFIG.json", "design/ANNOTATION_RESPONSE.schema.json",
                    "design/ANNOTATION_PROTOCOL.md", "design/prompts/segment-role-v1.md"]
        required += [path.relative_to(ROOT).as_posix() for path in (ROOT / "machine_development").glob("*.py")]
        for name in required:
            destination = self.project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        codebook = snapshot_codebook(self.project)
        items = [{"item_id": "machine-item-" + str(i), "problem_statement": "Synthetic task, not human gold.",
                  "current_segment": {"source_id": "machine-item-" + str(i), "text": "We choose the next method."},
                  "previous_segments": []} for i in range(24)]
        self.input_dir = self.project / "machine-inputs"
        self.input_dir.mkdir()
        inputs = {"items": items, "audit_item_ids": annotation.audit_item_ids(items), "E0": "not_passed", "human_gold": "not_created"}
        mapping = {"items": {item["item_id"]: {"root_id": "synthetic-root-" + str(i)} for i, item in enumerate(items)}}
        for name, value in (("items", inputs), ("codebook", codebook), ("mapping", mapping)):
            (self.input_dir / (name + ".json")).write_bytes(encode(value))
        parent = self.parent.protocol["models"][0]
        launch = (self.state / "ledger.json").read_bytes()
        rows = json.loads(launch)
        amount = sum((Decimal(row["charged_or_reserved_rub"]) for row in rows), Decimal(0))
        def input_spec(name):
            path = self.input_dir / (name + ".json")
            return {"path": path.relative_to(self.project).as_posix(), "file_sha256": sha(path.read_bytes())}
        self.protocol = {"schema_version": 1, "status": STATUS, "synthetic_fixture": True, "protocol_id": "synthetic-machine-development",
            "parent": {"protocol_sha256": sha((self.state / "protocol.json").read_bytes()),
                       "source_inventory_sha256": sha((self.state / "source-inventory.json").read_bytes()),
                       "launch_ledger_sha256": sha(launch), "launch_ledger_rows": len(rows), "launch_charged_or_reserved_rub": str(amount),
                       "admission_call_id": parent["parent_admission_call_id"],
                       "admission_request_sha256": parent["parent_request_sha256"],
                       "admission_response_sha256": parent["parent_response_sha256"]},
            "inputs": {**input_spec("items"), "items": 24, "roots": 24,
                       "codebook": input_spec("codebook"), "mapping": input_spec("mapping")},
            "annotation_config": {"path": "design/ANNOTATION_CONFIG.json",
                                  "file_sha256": sha((self.project / "design/ANNOTATION_CONFIG.json").read_bytes())},
            "generation": {"model": MODEL, "provider": PROVIDER, "temperature": .7, "top_p": 1.0, "max_output_tokens": 1024,
                           "request_timeout_seconds": 120, "concurrency_max": 3, "reasoning_enabled": False, "automatic_retries": 0,
                           "dispatch_deadline_utc": "2099-01-01T00:00:00+00:00", "operational_failure_limit_per_route": 2},
            "allocation": {"panel_size": 5, "majority_required": 3, "maximum_rounds": 2, "first_round_calls": 120,
                           "conditional_second_round_calls": 120, "audit_items": 3, "audit_calls": 15, "maximum_calls": 255},
            "budget": {"shared_state": "live", "cap_total_rub": "3300", "stage_additional_cap_rub": "2400",
                       "absolute_stage_ceiling_rub": str(amount + Decimal(2400))},
            "execution_io_compatibility": {"version": VERSION, "path": SOURCE_PATH, "sha256": sha((ROOT / SOURCE_PATH).read_bytes())}}
        self.protocol_path = self.project / "machine-protocol.json"
        self.protocol_path.write_bytes(encode(self.protocol))
        self.transport = FakeAnnotationTransport()

    def runner(self, execute=True):
        settings = MachineSettings(state=self.state, key="fixture-key", cap=Decimal(3300), collection_cap=Decimal(3300), top_p=1.0, max_tokens=1024)
        return MachineDevelopmentRunner(settings, self.protocol_path, self.transport, project=self.project, execute=execute)

    def test_dry_binding_and_worst_case_preflight_preserve_old_rows_and_all_roster(self):
        before = {name: (self.state / name).read_bytes() for name in ("ledger.json", "protocol.json", "corpus.json", "source-inventory.json")}
        runner = self.runner(False)
        preflight = runner.preflight()
        self.assertEqual(len(runner.plan["cells"]), 255)
        self.assertTrue(preflight["full_roster_fits_stage_budget"])
        self.assertEqual(self.transport.paid, [])
        self.assertEqual(before, {name: (self.state / name).read_bytes() for name in before})
        for cell in runner.plan["cells"]:
            body = runner.body(cell)
            self.assertEqual(body, annotation.request_body(runner.item_lookup[cell["item_id"]], runner.codebook,
                                                          cell["round_number"], cell["vote_index"]))
            self.assertEqual(body["provider"], {"order": [PROVIDER], "allow_fallbacks": False})
            self.assertFalse(body["reasoning"]["enabled"])
            self.assertFalse(body["include_reasoning"])
        with self.assertRaisesRegex(StopRun, "explicit --execute"):
            runner.paid_cell(runner.plan["cells"][0])

    def test_first_majorities_and_fixed_audit_are_distinct_and_recover_offline_without_calls(self):
        runner = self.runner()
        output = runner.run()
        self.assertEqual(len(self.transport.paid), 120 + 15)
        self.assertTrue(all(item["primary"]["status"] == "resolved" and not item["round2"] for item in output["items"]))
        self.assertEqual(len(output["all_planned_calls"]), 255)
        self.assertEqual(output["audit_effect_on_primary_consensus"], "none")
        ledger = (self.state / "ledger.json").read_bytes()
        trace_bytes = {path.relative_to(self.state).as_posix(): path.read_bytes() for path in runner.calls.glob("*/result.json")}
        count, metadata = len(self.transport.paid), self.transport.metadata_calls
        runner.settings.key, runner.settings.deadline = "", "2000-01-01T00:00:00+00:00"
        repeated = runner.run()
        self.assertEqual(len(self.transport.paid), count)
        self.assertEqual(self.transport.metadata_calls, metadata)
        self.assertEqual((self.state / "ledger.json").read_bytes(), ledger)
        self.assertEqual(trace_bytes, {path.relative_to(self.state).as_posix(): path.read_bytes() for path in runner.calls.glob("*/result.json")})
        self.assertEqual([item["primary"] for item in output["items"]], [item["primary"] for item in repeated["items"]])
        self.assertEqual(repeated["E0"], "not_passed")

    def test_complete_no_majority_alone_opens_round2_and_audits_do_not_pool(self):
        runner = self.runner()
        self.transport.mode = "no_majority"
        output = runner.run()
        self.assertEqual(len(self.transport.paid), 255)
        self.assertTrue(all(item["primary"]["status"] == "resolved" and item["primary"]["round_used"] == 2
                            and item["primary"]["pooled_rounds"] is False for item in output["items"]))
        self.assertTrue(all(len(item["round1"]) == len(item["round2"]) == 5 for item in output["items"]))

    def test_unknown_first_vote_blocks_direct_semantic_and_audit_retry_and_is_cached(self):
        runner = self.runner()
        runner.preflight()
        item_id = runner.audit_ids[0]
        cells = runner._item_cells(item_id, 1)
        self.transport.mode = "unknown"
        first = runner.vote(cells[0])
        count, ledger = len(self.transport.paid), runner.ledger_path.read_bytes()
        runner.vote(cells[0])
        self.assertEqual(len(self.transport.paid), count)
        self.assertEqual(runner.ledger_path.read_bytes(), ledger)
        self.assertEqual(first["request_state"], "unknown")
        with self.assertRaises(StopRun):
            runner.paid_cell(runner._item_cells(item_id, 2)[0])
        with self.assertRaises(StopRun):
            runner.paid_cell(runner._item_cells(item_id, 1, True)[0])
        self.assertEqual(len(self.transport.paid), count)

    def test_malformed_or_length_votes_never_open_round2_or_audits(self):
        runner = self.runner()
        self.transport.mode = "malformed"
        output = runner.run()
        self.assertEqual(len(self.transport.paid), 120)
        self.assertTrue(all(item["primary"]["status"] == "technical_unresolved" and not item["round2"] for item in output["items"]))
        self.assertTrue(all(value["status"].startswith("not_dispatched") for value in output["audits"].values()))
        self.assertFalse(any(path.is_file() for path in [runner.scope / "route-state.json"]))

    def test_unexpected_visible_reasoning_is_flag_only_and_not_used_as_vote(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "reasoning"
        record = runner.vote(runner.plan["cells"][0])
        self.assertEqual(record["technical_status"], "valid")
        self.assertTrue(record["returned_reasoning_present"])
        self.assertTrue(record["requested_reasoning_disabled"])
        self.assertEqual(record["effective_reasoning_mode"], "not_independently_confirmed")
        self.assertEqual(record["vote"]["primary_role"], "planning")

    def test_full_envelope_budget_and_deadline_stop_before_any_dispatch(self):
        runner = self.runner()
        self.transport.price = "0.5"
        output = runner.run()
        self.assertEqual(self.transport.paid, [])
        self.assertTrue(all(row["technical_status"] in ("not_dispatched", "not_scheduled_by_fixed_condition")
                            for row in output["all_planned_calls"]))
        current = json.loads((runner.scope / "cost-plan.json").read_bytes())
        self.assertFalse(current["full_roster_fits_stage_budget"])
        runner.settings.deadline = "2000-01-01T00:00:00+00:00"
        with self.assertRaises(StopRun):
            runner.paid_cell(runner.plan["cells"][0])
        self.assertEqual(self.transport.paid, [])

    def test_source_mutation_missing_result_and_second_namespace_cannot_hide_unknown(self):
        runner = self.runner()
        runner.preflight()
        cell = runner.plan["cells"][0]
        self.transport.mode = "unknown"
        runner.vote(cell)
        (runner.calls / cell["call_id"] / "result.json").unlink()
        with self.assertRaisesRegex(StopRun, "finalized.*result"):
            runner.paid_cell(cell)
        count = len(self.transport.paid)
        (self.project / "machine_development/new_hidden_module.py").write_bytes(b"# changed source roster\n")
        with self.assertRaisesRegex(StopRun, "changed after freeze"):
            runner.paid_cell(runner.plan["cells"][1])
        self.assertEqual(len(self.transport.paid), count)

    def test_two_inflight_known_overruns_are_finalized_and_further_calls_stop(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode, self.transport.barrier = "overrun", threading.Barrier(2)
        cells = runner._item_cells(runner.items[0]["item_id"], 1)[:2]
        with ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(runner.paid_cell, cells))
        self.assertEqual(len(outputs), 2)
        self.assertTrue(all(output["http_status"] == 200 and output["budget_overrun"] for output in outputs))
        self.assertTrue(all((runner.calls / cell["call_id"] / "result.json").is_file() for cell in cells))
        rows = json.loads(runner.ledger_path.read_bytes())
        self.assertEqual(rows[:len(runner.launch_rows)], runner.launch_rows)
        self.assertTrue(all(row["state"] == "finished" for row in rows[-2:]))
        self.transport.barrier = None
        with self.assertRaisesRegex(StopRun, "budget exhausted"):
            runner.paid_cell(runner._item_cells(runner.items[0]["item_id"], 1)[2])
        self.assertEqual(len(self.transport.paid), 2)

    def test_prebinding_expected_inventory_refuses_even_first_source_mutation(self):
        probe = MachineDevelopmentRunner.__new__(MachineDevelopmentRunner)
        probe.project, probe.state = self.project, self.state
        inventory = {"schema_version": 1, "scope": "machine-only annotation sources/config plus exact inherited closure",
                     "files": {name: sha(data) for name, data in probe._sources().items()}}
        self.protocol["source_freeze"] = {"expected_source_inventory_sha256": sha(encode(inventory))}
        self.protocol_path.write_bytes(encode(self.protocol))
        path = self.project / "stage2/annotation.py"
        path.write_bytes(path.read_bytes() + b"\n# pre-binding source change\n")
        with self.assertRaisesRegex(StopRun, "pre-binding inventory"):
            self.runner()
        self.assertEqual(self.transport.paid, [])

    def test_nonobject_JSON_is_known_invalid_and_finalized_without_releasing_cost(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "null_json"
        cell = runner.plan["cells"][0]
        record = runner.vote(cell)
        self.assertEqual(record["technical_status"], "invalid")
        self.assertEqual(record["request_state"], "finished")
        result = json.loads((runner.calls / cell["call_id"] / "result.json").read_bytes())
        self.assertIsNone(result["response"]["json"])
        self.assertEqual(result["accounting_payload_scope"], "nonobject_payload_cost_unavailable_reservation_retained")
        row = json.loads(runner.ledger_path.read_bytes())[-1]
        self.assertEqual(row["state"], "finished")
        self.assertEqual(row["charged_or_reserved_rub"], row["reservation_rub"])
        self.assertIsNone(row["reported_cost_rub"])

    def test_reduced_unknown_reserve_refuses_cache_and_any_new_dispatch(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "unknown"
        runner.vote(runner.plan["cells"][0])
        rows = json.loads(runner.ledger_path.read_bytes())
        rows[-1]["charged_or_reserved_rub"] = "0"
        runner.ledger_path.write_bytes(encode(rows))
        for cell in runner.plan["cells"][:2]:
            with self.assertRaisesRegex(StopRun, "obligation was reduced"):
                runner.paid_cell(cell)
        self.assertEqual(len(self.transport.paid), 1)

    def test_invalid_usage_retains_raw_known_response_and_reservation(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "invalid_usage"
        cell = runner.plan["cells"][0]
        record = runner.vote(cell)
        self.assertEqual(record["technical_status"], "valid")
        result = json.loads((runner.calls / cell["call_id"] / "result.json").read_bytes())
        self.assertEqual(result["response"]["json"]["usage"], ["invalid usage object"])
        self.assertEqual(result["accounting_payload_scope"], "usage_shape_normalized_for_accounting_raw_preserved")
        row = json.loads(runner.ledger_path.read_bytes())[-1]
        self.assertEqual(row["state"], "finished")
        self.assertEqual(row["charged_or_reserved_rub"], row["reservation_rub"])
        self.assertIsNone(row["reported_cost_rub"])

    def test_second_protocol_namespace_cannot_rotate_an_unknown_call_identity(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "unknown"
        runner.vote(runner.plan["cells"][0])
        current = runner.ledger_path.read_bytes()
        self.protocol["protocol_id"] = "unapproved-new-condition"
        self.protocol["parent"].update(launch_ledger_sha256=sha(current), launch_ledger_rows=len(json.loads(current)),
            launch_charged_or_reserved_rub=str(sum((Decimal(row["charged_or_reserved_rub"]) for row in json.loads(current)), Decimal(0))))
        self.protocol["budget"]["absolute_stage_ceiling_rub"] = str(Decimal(self.protocol["parent"]["launch_charged_or_reserved_rub"]) + Decimal(2400))
        self.protocol_path.write_bytes(encode(self.protocol))
        changed = self.runner()
        with self.assertRaisesRegex(StopRun, "different machine condition"):
            changed.preflight()
        self.assertEqual(len(self.transport.paid), 1)
        self.assertEqual(runner.ledger_path.read_bytes(), current)

    def test_known_raw_overrun_cannot_be_hidden_by_lowering_reported_and_committed_cost(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "overrun"
        cell = runner.plan["cells"][0]
        runner.paid_cell(cell)
        raw_result = (runner.calls / cell["call_id"] / "result.json").read_bytes()
        runner._read_retained_ledger()
        self.assertIn(cell["call_id"], runner._financial_cache)
        rows = json.loads(runner.ledger_path.read_bytes())
        rows[-1]["reported_cost_rub"] = rows[-1]["reservation_rub"]
        rows[-1]["charged_or_reserved_rub"] = rows[-1]["reservation_rub"]
        runner.ledger_path.write_bytes(encode(rows))
        for target in runner.plan["cells"][:2]:
            with self.assertRaisesRegex(StopRun, "original known raw cost"):
                runner.paid_cell(target)
        self.assertEqual((runner.calls / cell["call_id"] / "result.json").read_bytes(), raw_result)
        self.assertEqual(len(self.transport.paid), 1)


if __name__ == "__main__":
    unittest.main()
