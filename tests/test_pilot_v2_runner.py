"""Synthetic requests only: shared budget, frozen cells and capped outcomes."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest

from pilot_v2.runner import PilotV2Runner, PROVIDERS, FINAL_STATUS
from resumption.runner import Runner, Settings, sha
from stage0.runner import StopRun, capture_body, encode
from scripts.pilot_v2_ledger_io_compat_v1 import CooperativeLedgerIOMixin


ROOT = Path(__file__).resolve().parents[1]


class SyntheticPilotV2Runner(CooperativeLedgerIOMixin, PilotV2Runner):
    """Post-data fixture I/O guard; original collector/business logic is frozen."""


class Transport:
    def __init__(self):
        self.paid = []
        self.mode = "stop"
        self.price = "0.000001"

    def __call__(self, path, key=None, body=None, timeout=30):
        if path.endswith("/endpoints"):
            return {"http_status": 200, "json": {"data": {"endpoints": [
                {"provider_name": provider, "pricing_units": {"prompt": "token", "completion": "token"},
                 "pricing": {"prompt": self.price, "completion": self.price}}
                for provider in PROVIDERS.values()]}}}
        self.paid.append(copy.deepcopy(body))
        if self.mode == "unknown":
            return {"http_status": None, "json": {}, "network_error": "SyntheticTimeout"}
        provider = "WrongProvider" if self.mode == "drift" else PROVIDERS[body["model"]]
        payload = {"model": body["model"], "provider": provider, "usage": {"cost": "0.001"},
                   "choices": [{"finish_reason": self.mode if self.mode in ("stop", "length") else "stop",
                                "message": {"reasoning": "word " * 300 + "ANSWER: hidden reasoning conclusion",
                                            "content": "ANSWER: 5"}}]}
        return {"http_status": 200, **capture_body(encode(payload), key)}


def fixture_grade(task, text):
    return {"verdict": "correct", "correct": True, "gradable": True,
            "verifier_id": "synthetic-fixture-only"}


class PilotV2RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # The frozen A adapter requires a canonical state spelling. On GitHub
        # Windows TEMP may use RUNNER~1 while resolve() expands runneradmin.
        # R1 normalizes this at its production boundary; A bytes stay frozen.
        self.project = Path(self.temporary.name).resolve()
        self.state = self.project / "live"
        self.transport = Transport()
        parent_protocol, parent_tasks = self.project / "parent-protocol.json", self.project / "parent-tasks.json"
        parent_protocol.write_bytes(encode({"synthetic_fixture": True}))
        parent_tasks.write_bytes(encode({"tasks": []}))
        parent = Runner(Settings(state=self.state, key="fixture-key", cap=Decimal(3000),
                                 collection_cap=Decimal(3000), deadline="2099-01-01T00:00:00+00:00"), self.transport)
        parent.bind(parent_protocol, parent_tasks)
        admissions = []
        for index, (model, provider) in enumerate(PROVIDERS.items()):
            task = {"task_id": "parent-" + str(index), "root_id": "parent-" + str(index), "prompt": "Synthetic parent",
                    "domain": "math", "difficulty": "high", "split": "development"}
            record = parent.chat(model, task, -1, admission=True)
            admissions.append({"model": model, "provider": provider,
                "parent_admission_call_id": record["trace_id"], "parent_request_sha256": record["request_sha256"],
                "parent_response_sha256": record["response_sha256"]})
        self.transport.paid.clear()
        inherited = json.loads((self.state / "source-inventory.json").read_bytes())
        for relative in inherited["files"]:
            destination = self.project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        package = self.project / "pilot_v2"
        package.mkdir()
        (package / "runner.py").write_bytes((ROOT / "pilot_v2/runner.py").read_bytes())
        (package / "tasks.py").write_bytes(b"# Independent synthetic fixture source; no scientific data.\n")
        tasks = []
        for root in range(24):
            domain = ("math", "logic", "algorithms", "planning")[root // 6]
            tier = ("low", "medium", "high")[(root // 2) % 3]
            for variant in range(2):
                tasks.append({"task_id": f"task-{root}-{variant}", "root_id": f"root-{root}", "domain": domain,
                              "tier": tier, "difficulty": tier, "prompt": f"Synthetic fixture {root}/{variant}; return ANSWER: 5",
                              "reference_certificate": {"never_send": "REFERENCE-PRIVATE-FIXTURE"},
                              "split": "development", "confirmatory_excluded": True})
        self.tasks_path = self.project / "tasks.json"
        self.tasks_path.write_bytes(encode({"tasks": tasks}))
        launch = (self.state / "ledger.json").read_bytes()
        self.launch_rows = json.loads(launch)
        amount = sum((Decimal(row["charged_or_reserved_rub"]) for row in self.launch_rows), Decimal(0))
        self.protocol = {"schema_version": 1, "protocol_id": "synthetic-pilot-v2", "synthetic_fixture": True,
            "created_utc": datetime.now(timezone.utc).isoformat(), "status": FINAL_STATUS,
            "parent": {"protocol_sha256": sha((self.state / "protocol.json").read_bytes()),
                       "source_inventory_sha256": sha((self.state / "source-inventory.json").read_bytes()),
                       "launch_ledger_sha256": sha(launch), "launch_ledger_rows": len(self.launch_rows),
                       "launch_charged_or_reserved_rub": str(amount)},
            "tasks": {"path": "tasks.json", "file_sha256": sha(self.tasks_path.read_bytes()), "tasks": 48, "roots": 24},
            "models": admissions, "generation": {"output_budget_tokens": [2048, 8192], "samples_per_task": 1,
                "max_calls": 192, "temperature": .7, "top_p": .95, "seed": 42, "concurrency_max": 3,
                "request_timeout_seconds": 180, "automatic_retries": 0, "operational_failure_limit_per_route": 2,
                "dispatch_deadline_utc": "2099-01-01T00:00:00+00:00"},
            "budget": {"cap_total_rub": "3000", "stage_additional_cap_rub": "1200",
                       "absolute_stage_ceiling_rub": str(amount + Decimal(1200)), "shared_state": "live"},
            "measurement": {"allow_budget_censored_gradeable": False, "embeddings_in_stage_A": False}}
        self.protocol_path = self.project / "v2-protocol.json"
        self.protocol_path.write_bytes(encode(self.protocol))

    def runner(self, execute=True):
        return SyntheticPilotV2Runner(Settings(state=self.state, key="fixture-key", cap=Decimal(3000), collection_cap=Decimal(3000)),
            self.protocol_path, self.tasks_path, self.transport, project=self.project, execute=execute, fixture_verifier=fixture_grade)

    def test_binding_and_preflight_preserve_v1_and_freeze_all_192_cells_without_calls(self):
        before = {name: (self.state / name).read_bytes() for name in
                  ("protocol.json", "corpus.json", "source-inventory.json", "ledger.json", "admissions.json")}
        runner = self.runner(False)
        plan = runner.preflight()
        self.assertEqual(len(runner.plan["cells"]), 192)
        self.assertTrue(plan["full_roster_fits_stage_budget"])
        self.assertEqual(self.transport.paid, [])
        for name, data in before.items():
            self.assertEqual((self.state / name).read_bytes(), data)
        self.assertTrue((runner.scope / "metadata/history").is_dir())
        self.assertFalse((self.state / "metadata" / "pilot-v2.json").exists())
        for cell in runner.plan["cells"]:
            body = runner.body(cell)
            self.assertEqual(body["max_tokens"], cell["output_budget_tokens"])
            self.assertEqual(body["provider"], {"order": [cell["provider"]], "allow_fallbacks": False})
            self.assertNotIn("REFERENCE-PRIVATE-FIXTURE", json.dumps(body))
        with self.assertRaisesRegex(StopRun, "explicit --execute"):
            runner.paid_cell(runner.plan["cells"][0])

    def test_paid_context_shared_ledger_and_cache_are_bound_to_v2_not_old_verifier(self):
        runner = self.runner()
        runner.preflight()
        cell = runner.plan["cells"][0]
        result = runner.execute_cell(cell)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("ANSWER:", result["text"])
        self.assertTrue(result["provider_route_verified"])
        self.assertEqual(result["output_budget_tokens"], cell["output_budget_tokens"])
        reservation = json.loads((runner.calls / cell["call_id"] / "reservation.json").read_bytes())
        self.assertEqual(reservation["source_inventory_sha256"], runner.source_inventory_digest)
        self.assertEqual(reservation["verifier_source_sha256"], sha((self.project / "pilot_v2/tasks.py").read_bytes()))
        self.assertEqual(reservation["protocol_sha256"], runner.protocol_digest)
        self.assertNotEqual(runner.protocol_digest, self.protocol["parent"]["protocol_sha256"])
        ledger = json.loads((self.state / "ledger.json").read_bytes())
        self.assertEqual(ledger[:len(self.launch_rows)], self.launch_rows)
        before = (self.state / "ledger.json").read_bytes()
        trace_before = (runner.calls / cell["call_id"] / "trace.json").read_bytes()
        runner.settings.key = ""
        runner.settings.deadline = "2000-01-01T00:00:00+00:00"
        cached = runner.execute_cell(cell)
        self.assertTrue(cached["reused_record_without_resend"])
        self.assertEqual(len(self.transport.paid), 1)
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)
        self.assertEqual((runner.calls / cell["call_id"] / "trace.json").read_bytes(), trace_before)

    def test_unknown_is_retained_and_not_resent(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "unknown"
        cell = runner.plan["cells"][0]
        record = runner.execute_cell(cell)
        self.assertEqual(record["request_state"], "unknown")
        self.assertIsNone(record["http_status"])
        before = (self.state / "ledger.json").read_bytes()
        runner.execute_cell(cell)
        self.assertEqual(len(self.transport.paid), 1)
        self.assertEqual((self.state / "ledger.json").read_bytes(), before)
        self.assertEqual(json.loads(before)[-1]["state"], "unknown")

    def test_length_is_censored_not_correct_and_does_not_stop_route(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "length"
        cells = [cell for cell in runner.plan["cells"] if cell["model"] == runner.plan["cells"][0]["model"]][:3]
        for cell in cells:
            record = runner.execute_cell(cell)
            self.assertEqual(record["status"], "truncated")
            self.assertTrue(record["budget_censored"])
            self.assertIsNone(record["correct"])
            self.assertFalse(record["gradable"])
            self.assertFalse(record["operational_failure"])
            self.assertEqual(record["raw_answer_grading"]["verdict"], "correct")
        self.assertEqual(len(self.transport.paid), 3)
        self.assertEqual(runner._route_state()["operational_failure_calls"], {})

    def test_route_failures_stop_future_calls_but_not_cached_records(self):
        runner = self.runner()
        runner.preflight()
        self.transport.mode = "drift"
        cells = [cell for cell in runner.plan["cells"] if cell["model"] == runner.plan["cells"][0]["model"]][:3]
        runner.execute_cell(cells[0]); runner.execute_cell(cells[1])
        with self.assertRaisesRegex(StopRun, "two observed operational"):
            runner.execute_cell(cells[2])
        runner.execute_cell(cells[0])
        self.assertEqual(len(self.transport.paid), 2)

    def test_changed_source_or_params_and_missing_intent_result_fail_before_dispatch(self):
        runner = self.runner()
        runner.preflight()
        changed = dict(runner.plan["cells"][0], output_budget_tokens=4096)
        with self.assertRaisesRegex(StopRun, "outside the frozen"):
            runner.paid_cell(changed)
        (self.project / "pilot_v2/new_module.py").write_bytes(b"# newly imported code\n")
        with self.assertRaisesRegex(StopRun, "code changed"):
            runner.paid_cell(runner.plan["cells"][0])
        self.assertEqual(self.transport.paid, [])

    def test_stage_budget_and_deadline_stop_before_network(self):
        runner = self.runner()
        runner.preflight()
        runner.stage_ceiling = runner._check_ledger().committed
        with self.assertRaisesRegex(StopRun, "ceiling"):
            runner.paid_cell(runner.plan["cells"][0])
        runner.stage_ceiling = Decimal(self.protocol["budget"]["absolute_stage_ceiling_rub"])
        runner.settings.deadline = "2000-01-01T00:00:00+00:00"
        with self.assertRaises(StopRun):
            runner.paid_cell(runner.plan["cells"][0])
        self.assertEqual(self.transport.paid, [])

    def test_separate_run_process_refreshes_the_complete_remaining_quote_before_any_dispatch(self):
        initial = self.runner()
        self.assertTrue(initial.preflight()["full_roster_fits_stage_budget"])
        self.transport.price = "0.01"
        fresh = self.runner()
        output = fresh.run()
        self.assertEqual(self.transport.paid, [])
        self.assertEqual(len(output["records"]), 192)
        self.assertTrue(all(row["status"] == "not_dispatched" for row in output["records"]))
        current = json.loads((fresh.scope / "cost-plan.json").read_bytes())
        self.assertFalse(current["full_roster_fits_stage_budget"])
        self.assertGreaterEqual(len(list((fresh.scope / "cost-plans").glob("*.json"))), 2)

    def test_unfinalized_intent_is_never_resent(self):
        runner = self.runner()
        runner.preflight()
        cell = runner.plan["cells"][0]
        path = runner.scope / "intents" / (cell["call_id"] + ".json")
        path.parent.mkdir()
        path.write_bytes(encode({"synthetic_unfinished_intent": True}))
        with self.assertRaisesRegex(StopRun, "Unfinalized pilot-v2 intent"):
            runner.execute_cell(cell)
        self.assertEqual(self.transport.paid, [])

    def test_fully_cached_run_recovers_offline_after_cutoff_without_any_metadata_requests(self):
        first = self.runner()
        initial = first.run()
        self.assertEqual(len(self.transport.paid), 192)
        self.assertEqual(len(initial["records"]), 192)
        ledger_before = (self.state / "ledger.json").read_bytes()
        trace_hashes = {cell["call_id"]: sha((first.calls / cell["call_id"] / "trace.json").read_bytes())
                        for cell in first.plan["cells"]}
        recovered = self.runner()
        recovered.settings.key = ""
        recovered.settings.deadline = "2000-01-01T00:00:00+00:00"
        def no_network(*args, **kwargs):
            raise AssertionError("Offline cache recovery cannot request metadata or paid responses")
        recovered.transport = no_network
        output = recovered.run()
        self.assertTrue(all(record["reused_record_without_resend"] for record in output["records"]))
        self.assertEqual((self.state / "ledger.json").read_bytes(), ledger_before)
        self.assertEqual(trace_hashes, {cell["call_id"]: sha((first.calls / cell["call_id"] / "trace.json").read_bytes())
                                       for cell in first.plan["cells"]})

    def test_two_inflight_known_responses_are_both_finalized_after_a_reported_stage_overrun(self):
        runner = self.runner()
        runner.preflight()
        first, second = runner.plan["cells"][:2]
        barrier = threading.Barrier(2)
        first_done = threading.Event()
        original_transport = self.transport
        def transport(path, **kwargs):
            if path != "/chat/completions":
                return original_transport(path, **kwargs)
            body = kwargs["body"]
            barrier.wait(timeout=10)
            is_first = sha(encode(body)) == first["request_sha256"]
            if not is_first:
                self.assertTrue(first_done.wait(timeout=10))
            response = original_transport(path, **kwargs)
            payload = response["json"]
            if is_first:
                payload["usage"]["cost"] = "1300"
            return {"http_status": 200, **capture_body(encode(payload), "fixture-key")}
        runner.transport = transport
        def complete_first():
            try:
                return runner.execute_cell(first)
            finally:
                first_done.set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(complete_first)
            second_future = pool.submit(runner.execute_cell, second)
            self.assertEqual(first_future.result()["status"], "completed")
            self.assertEqual(second_future.result()["status"], "completed")
        ledger = json.loads((self.state / "ledger.json").read_bytes())
        self.assertTrue(all(row["state"] == "finished" for row in ledger[-2:]))
        self.assertEqual(ledger[:len(self.launch_rows)], self.launch_rows)
        for cell in (first, second):
            result = json.loads((runner.calls / cell["call_id"] / "result.json").read_bytes())
            self.assertEqual(result["http_status"], 200)
            self.assertTrue(result["budget_overrun"])
        with self.assertRaisesRegex(StopRun, "exhausted|ceiling"):
            runner.paid_cell(runner.plan["cells"][2])
        self.assertEqual(len(self.transport.paid), 2)


if __name__ == "__main__":
    unittest.main()
