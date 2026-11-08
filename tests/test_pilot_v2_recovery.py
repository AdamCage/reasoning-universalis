"""Recovery is one finite new provider condition, never a retry/reset of A."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pilot_v2_runner as fixtures
from pilot_v2.runner import PilotV2Runner
from resumption.runner import Runner, Settings, read_json, sha
from scripts.collect_pilot_v2_recovery import RecoveryRunner, STATUS, GPT, DEEPSEEK, SCRIPT
from stage0.runner import StopRun, encode, capture_body


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        fixtures.PilotV2RunnerTests.setUp(self)
        original = self.transport
        self.akash_mode = "stop"
        self.gpt_a_outage = False
        self.akash_paid = []
        def transport(path, key=None, body=None, timeout=30):
            if path.endswith("/endpoints"):
                return {"http_status": 200, "json": {"data": {"endpoints": [
                    {"provider_name": provider, "pricing_units": {"prompt": "token", "completion": "token"},
                     "pricing": {"prompt": original.price, "completion": original.price}}
                    for provider in ("BytePlus", "DeepInfra", "AkashML")]}}}
            if body["model"] == GPT and self.gpt_a_outage and body.get("provider", {}).get("order") == ["DeepInfra"]:
                original.paid.append(copy.deepcopy(body))
                return {"http_status": 200, **capture_body(encode({"error": {"code": 503, "message": "fixture outage"}}), key)}
            if body["model"] == GPT and (not body.get("provider") or body["provider"]["order"] == ["AkashML"]):
                self.akash_paid.append(copy.deepcopy(body))
                if self.akash_mode == "unknown":
                    return {"http_status": None, "json": {}, "network_error": "SyntheticTimeout"}
                if self.akash_mode == "error":
                    return {"http_status": 200, **capture_body(encode({"error": {"code": 503}}), key)}
                payload = {"model": GPT, "provider": "AkashML", "usage": {"cost": "0.001"},
                    "choices": [{"finish_reason": "length" if self.akash_mode == "length" else "stop",
                                 "message": {"reasoning": "word " * 300, "content": "ANSWER: 5"}}]}
                return {"http_status": 200, **capture_body(encode(payload), key)}
            return original(path, key=key, body=body, timeout=timeout)
        self.recovery_transport = transport
        parent = Runner(Settings(state=self.state, key="fixture-key", cap=Decimal(3000), collection_cap=Decimal(3000),
                                 deadline="2099-01-01T00:00:00+00:00"), transport)
        parent.bind(self.project / "parent-protocol.json", self.project / "parent-tasks.json")
        admitted = parent.chat(GPT, {"task_id": "akash-admission", "root_id": "akash-admission", "prompt": "fixture",
                                   "domain": "math", "difficulty": "high", "split": "development"}, -2, admission=True)
        launch = (self.state / "ledger.json").read_bytes()
        amount = sum((Decimal(row["charged_or_reserved_rub"]) for row in json.loads(launch)), Decimal(0))
        self.protocol["parent"].update(launch_ledger_sha256=sha(launch), launch_ledger_rows=len(json.loads(launch)),
                                       launch_charged_or_reserved_rub=str(amount))
        self.protocol["budget"]["absolute_stage_ceiling_rub"] = str(amount + Decimal(1200))
        self.protocol_path.write_bytes(encode(self.protocol))
        self.a = PilotV2Runner(Settings(state=self.state, key="fixture-key", cap=Decimal(3000), collection_cap=Decimal(3000)),
            self.protocol_path, self.tasks_path, transport, project=self.project, execute=True, fixture_verifier=fixtures.fixture_grade)
        self.a.preflight()
        for cell in self.a.plan["cells"]:
            if cell["model"] == DEEPSEEK:
                self.a.execute_cell(cell)
        self.gpt_a_outage = True
        gpt = [cell for cell in self.a.plan["cells"] if cell["model"] == GPT]
        self.a.execute_cell(gpt[0]); self.a.execute_cell(gpt[1])
        self.a_output = self.a.run()
        self.a_snapshot = {str(path.relative_to(self.state)): path.read_bytes()
                           for path in self.a.scope.rglob("*") if path.is_file()}
        for cell in self.a.plan["cells"]:
            directory = self.a.calls / cell["call_id"]
            if directory.is_dir():
                self.a_snapshot.update({str(path.relative_to(self.state)): path.read_bytes() for path in directory.iterdir() if path.is_file()})
        script = self.project / SCRIPT
        script.parent.mkdir(exist_ok=True)
        script.write_bytes((fixtures.ROOT / SCRIPT).read_bytes())
        launch = (self.state / "ledger.json").read_bytes()
        rows = json.loads(launch)
        amount = sum((Decimal(row["charged_or_reserved_rub"]) for row in rows), Decimal(0))
        self.decision = {"status": "design_recovery_condition_before_class_tally",
            "original_condition_sha256": self.a.protocol_digest,
            "original_results_sha256": sha((self.a.scope / "results.json").read_bytes()),
            "next_condition": {"model": GPT, "provider": "AkashML", "parent_admission_call_id": admitted["trace_id"],
                               "parent_request_sha256": admitted["request_sha256"], "parent_response_sha256": admitted["response_sha256"]},
            "budget": {"charged_or_reserved_before_recovery": str(amount)}}
        decision_path = self.project / "decision.json"
        decision_path.write_bytes(encode(self.decision))
        self.r_protocol = copy.deepcopy(self.protocol)
        self.r_protocol.update(status=STATUS, protocol_id="synthetic-provider-recovery-R1")
        self.r_protocol["parent"].update(launch_ledger_sha256=sha(launch), launch_ledger_rows=len(rows),
                                         launch_charged_or_reserved_rub=str(amount))
        self.r_protocol["models"] = [self.protocol["models"][0], self.decision["next_condition"]]
        self.r_protocol["generation"]["new_calls_max"] = 96
        self.r_protocol["recovery"] = {"condition": "R1", "decision_path": "decision.json", "decision_sha256": sha(decision_path.read_bytes()),
            "collector_sha256": sha(script.read_bytes()), "parent_scope": self.a.scope.relative_to(self.state).as_posix(),
            "parent_protocol_sha256": self.a.protocol_digest, "parent_results_sha256": sha((self.a.scope / "results.json").read_bytes()),
            "parent_dispatch_plan_sha256": sha((self.a.scope / "dispatch-plan.json").read_bytes()),
            "parent_source_inventory_sha256": self.a.source_inventory_digest, "new_model": GPT, "new_provider": "AkashML",
            "reused_model": DEEPSEEK, "new_calls": 96, "reused_records": 96, "max_recovery_conditions": 1}
        self.r_path = self.project / "recovery.json"
        self.r_path.write_bytes(encode(self.r_protocol))
        self.akash_paid.clear()

    def recovery(self, execute=True, state=None):
        return RecoveryRunner(Settings(state=self.state if state is None else state, key="fixture-key", cap=Decimal(3000), collection_cap=Decimal(3000)),
            self.r_path, self.tasks_path, self.recovery_transport, project=self.project, execute=execute,
            fixture_verifier=fixtures.fixture_grade)

    def test_full192_reuses_all96_original_records_without_modifying_a_or_reissuing(self):
        runner = self.recovery()
        out = runner.run()
        self.assertEqual(len(out["records"]), 192)
        self.assertEqual(len(self.akash_paid), 96)
        lineage = runner.reuse_mapping["new_records"]
        self.assertEqual(len({row["parent_trace_id"] for row in lineage}), 96)
        self.assertEqual(sum(row["parent_response_sha256"] is not None for row in lineage), 2)
        old = [row for row in self.a_output["records"] if row["model"] == DEEPSEEK]
        new = [row for row in out["records"] if row["model"] == DEEPSEEK]
        self.assertEqual({row["trace_id"]: row for row in old}, {row["trace_id"]: row for row in new})
        for name, data in self.a_snapshot.items():
            self.assertEqual((self.state / name).read_bytes(), data, name)
        self.assertTrue(all(body["provider"] == {"order": ["AkashML"], "allow_fallbacks": False} for body in self.akash_paid))
        ledger = (self.state / "ledger.json").read_bytes()
        runner.settings.key, runner.settings.deadline = "", "2000-01-01T00:00:00+00:00"
        runner.run()
        self.assertEqual(len(self.akash_paid), 96)
        self.assertEqual((self.state / "ledger.json").read_bytes(), ledger)

    def test_unknown_recovery_attempt_kept_and_never_resent(self):
        runner = self.recovery(); runner.preflight()
        self.akash_mode = "unknown"
        first = runner.execute_cell(runner.new_cells[0])
        ledger = (self.state / "ledger.json").read_bytes()
        runner.execute_cell(runner.new_cells[0])
        self.assertEqual(first["request_state"], "unknown")
        self.assertEqual(len(self.akash_paid), 1)
        self.assertEqual((self.state / "ledger.json").read_bytes(), ledger)

    def test_two_known_errors_stop_new_route_but_cached_errors_are_not_resent(self):
        runner = self.recovery(); runner.preflight(); self.akash_mode = "error"
        for cell in runner.new_cells[:2]:
            runner.execute_cell(cell)
        with self.assertRaisesRegex(StopRun, "two observed operational"):
            runner.execute_cell(runner.new_cells[2])
        runner.execute_cell(runner.new_cells[0])
        self.assertEqual(len(self.akash_paid), 2)

    def test_reused_cells_cannot_be_dispatched_and_stage_cap_is_not_reset(self):
        runner = self.recovery(); runner.preflight()
        with self.assertRaisesRegex(StopRun, "only its new fixed"):
            runner.paid_cell(next(cell for cell in runner.plan["cells"] if cell["model"] == DEEPSEEK))
        self.assertEqual(runner.stage_ceiling, Decimal(self.protocol["budget"]["absolute_stage_ceiling_rub"]))
        runner.stage_ceiling = runner._read_retained_ledger().committed
        with self.assertRaisesRegex(StopRun, "ceiling"):
            runner.execute_cell(runner.new_cells[0])
        self.assertEqual(self.akash_paid, [])

    def test_parent_unknown_or_hidden_attempt_and_changed_scientific_contract_block(self):
        unsent = next(row for row in self.a_output["records"] if row["status"] == "not_dispatched")
        path = self.a.scope / "intents" / (unsent["trace_id"] + ".json")
        path.write_bytes(encode({"unfinished": True}))
        with self.assertRaisesRegex(StopRun, "underlying attempt"):
            self.recovery()
        path.unlink()
        self.r_protocol["measurement"]["primary_prefix_words"] = 128
        self.r_path.write_bytes(encode(self.r_protocol))
        with self.assertRaisesRegex(StopRun, "scientific contract"):
            self.recovery()
        self.assertEqual(self.akash_paid, [])

    def test_length_is_retained_censored_not_route_failure_or_primary_label(self):
        runner = self.recovery(); runner.preflight(); self.akash_mode = "length"
        record = runner.execute_cell(runner.new_cells[0])
        self.assertEqual(record["status"], "truncated")
        self.assertIsNone(record["correct"])
        self.assertFalse(record["gradable"])
        self.assertFalse(record["operational_failure"])
        self.assertEqual(runner._route_state()["operational_failure_calls"], {})

    def test_second_protocol_namespace_cannot_hide_unknown_recovery_attempt(self):
        runner = self.recovery(); runner.preflight(); self.akash_mode = "unknown"
        runner.execute_cell(runner.new_cells[0])
        self.r_protocol["protocol_id"] = "unapproved-second-recovery-namespace"
        self.r_path.write_bytes(encode(self.r_protocol))
        with self.assertRaisesRegex(StopRun, "immutable artifact changed"):
            self.recovery()
        self.assertEqual(len(self.akash_paid), 1)

    def test_unmapped_original_intent_blocks_recovery_before_new_dispatch(self):
        path = self.a.scope / "intents" / ("f" * 64 + ".json")
        path.write_bytes(encode({"unknown_original_subject": True}))
        with self.assertRaisesRegex(StopRun, "Unmapped original A intent"):
            self.recovery()
        self.assertEqual(self.akash_paid, [])

    def test_state_alias_is_canonical_before_inherited_reservation_writer(self):
        runner = self.recovery(state=self.state / ".." / "live")
        self.assertEqual(runner.state, self.state.resolve(strict=True))
        runner.preflight()
        record = runner.execute_cell(runner.new_cells[0])
        self.assertEqual(record["status"], "completed")
        reservation = read_json(runner.calls / record["trace_id"] / "reservation.json")
        self.assertEqual(reservation["quote_namespace"], runner.scope.relative_to(runner.state).as_posix() + "/metadata/history")

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 alias regression")
    def test_windows_short_state_alias_resolves_before_paid_dispatch(self):
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        function = ctypes.windll.kernel32.GetShortPathNameW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        function.restype = ctypes.c_uint32
        count = function(str(self.state), buffer, len(buffer))
        if not count or count >= len(buffer) or buffer.value.casefold() == str(self.state).casefold():
            self.skipTest("No distinct Windows 8.3 alias is available")
        runner = self.recovery(state=Path(buffer.value))
        self.assertEqual(runner.state, self.state.resolve(strict=True))
        runner.preflight()
        self.assertEqual(runner.execute_cell(runner.new_cells[0])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
