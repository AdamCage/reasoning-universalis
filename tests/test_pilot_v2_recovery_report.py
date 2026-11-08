"""Synthetic reporting shapes only; no real partial labels or exported fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pilot_v2.statistical_design import canonical, summarize_support
from scripts.summarize_pilot_v2_recovery import build, sha
from stage0.runner import encode

ROOT = Path(__file__).resolve().parents[1]
GPT, DS = "openai/gpt-oss-20b", "deepseek/deepseek-v4.1-flash"


class RecoveryReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.paths = {}
        def save(name, value, raw=None):
            path = self.work / (name + ".json")
            path.write_bytes(encode(value) if raw is None else raw)
            self.paths[name] = path
            return path.read_bytes()
        self.save = save
        tasks = []
        for root in range(24):
            for variant in range(2):
                tasks.append({"task_id": f"root{root}-v{variant}", "root_id": f"root{root}",
                    "domain": ("math", "logic", "algorithms", "planning")[root // 6],
                    "tier": ("low", "medium", "high")[(root // 2) % 3], "prompt": "Synthetic reporting-only prompt",
                    "split": "development", "confirmatory_excluded": True})
        taskraw = save("tasks", {"tasks": tasks})
        planning_path = ROOT / "artifacts/pilot-v2-2026-11-08/statistical-planning-scenarios.json"
        planning = json.loads(planning_path.read_bytes())
        save("planning", planning, planning_path.read_bytes())
        a = json.loads((ROOT / "design/PILOT_V2_PROTOCOL_2026_11_08.json").read_bytes())
        a["protocol_id"] = "synthetic-report-fixture-A"
        a["tasks"]["file_sha256"] = sha(taskraw)
        a["parent"]["launch_charged_or_reserved_rub"] = "80"
        a_raw = save("parent-protocol", a)
        a_source = sha(b"synthetic-A-source-inventory")
        original = []
        for task in tasks:
            for model in (DS, GPT):
                for cap in (2048, 8192):
                    number = len(original)
                    trace_id = sha(f"A-{number}".encode())
                    record = {**task, "trace_id": trace_id, "model": model, "output_budget_tokens": cap,
                        "provider": "BytePlus" if model == DS else "DeepInfra", "condition_id": sha(f"condition-{number}".encode()),
                        "seed": number, "sample_index": 0, "phase": "pilot_v2_stage_A", "status": "completed",
                        "finish_reason": "stop", "correct": True, "gradable": True, "text": "reason " * 512,
                        "attempted": True, "http_status": 200, "request_state": "finished", "identity_verified": True,
                        "provider_route_verified": True, "observed_trace_status": "visible_trace_candidate",
                        "protocol_sha256": sha(a_raw), "corpus_sha256": sha(taskraw), "source_inventory_sha256": a_source,
                        "request_sha256": sha(f"request-{number}".encode()), "response_sha256": sha(f"response-{number}".encode())}
                    if model == GPT:
                        record.update(status="not_dispatched", attempted=False, http_status=None, request_state="not_dispatched",
                                      finish_reason=None, correct=None, gradable=False, text="")
                        record.pop("response_sha256")
                        if sum(row["model"] == GPT for row in original) < 2:
                            record.update(status="excluded", attempted=True, http_status=200, request_state="finished",
                                          response_sha256=sha(f"known503-{number}".encode()))
                    original.append(record)
        a_result = {"phase": "pilot_v2_stage_A", "protocol_sha256": sha(a_raw), "corpus_sha256": sha(taskraw),
            "source_inventory_sha256": a_source, "dispatch_plan_sha256": sha(b"A-plan"), "all_planned_cells": 192,
            "records": original, "charged_or_reserved_rub": "100", "completed_utc": "2026-11-08T14:00:00+00:00"}
        a_result_raw = save("parent-results", a_result)
        launch = [{"id": "prior", "state": "finished", "charged_or_reserved_rub": "80", "reported_cost_rub": "75", "purpose": "prior"},
                  {"id": "A", "state": "unknown", "charged_or_reserved_rub": "20", "reported_cost_rub": None, "purpose": "A"}]
        launch_raw = save("launch-ledger", launch)
        save("ledger", launch + [{"id": "R1", "state": "finished", "charged_or_reserved_rub": "10", "reported_cost_rub": "8", "purpose": "R1"}])
        collector = (ROOT / "scripts/collect_pilot_v2_recovery.py").read_bytes()
        inventory = {"files": {"pilot_v2/statistical_design.py": sha((ROOT / "pilot_v2/statistical_design.py").read_bytes()),
                               "scripts/collect_pilot_v2_recovery.py": sha(collector)}}
        inventory_raw = save("source-inventory", inventory)
        p = copy.deepcopy(a)
        p.update(protocol_id="synthetic-report-fixture-R1", status="prospective_frozen_provider_recovery")
        p["models"][1]["provider"] = "AkashML"
        p["generation"]["new_calls_max"] = 96
        p["parent"].update(launch_ledger_sha256=sha(launch_raw), launch_ledger_rows=2, launch_charged_or_reserved_rub="100")
        p["recovery"] = {"condition": "R1", "collector_sha256": sha(collector), "parent_protocol_sha256": sha(a_raw),
            "parent_results_sha256": sha(a_result_raw), "parent_source_inventory_sha256": a_source,
            "parent_dispatch_plan_sha256": a_result["dispatch_plan_sha256"]}
        p_raw = save("protocol", p)
        records, reused, fresh = [], [], []
        for previous in original:
            row = copy.deepcopy(previous)
            if row["model"] == DS:
                reused.append({"task_id": row["task_id"], "root_id": row["root_id"], "model": DS,
                    "output_budget_tokens": row["output_budget_tokens"], "trace_id": row["trace_id"],
                    "record_sha256": sha(encode(row)), **{field: row[field] for field in
                        ("request_sha256", "response_sha256", "source_inventory_sha256")}})
            else:
                row.update(trace_id=sha(("R1-" + row["trace_id"]).encode()), provider="AkashML", status="completed",
                    correct=True, gradable=True, text="reason " * 512, attempted=True, http_status=200,
                    request_state="finished", finish_reason="stop", protocol_sha256=sha(p_raw),
                    source_inventory_sha256=sha(inventory_raw), response_sha256=sha(("R1response-" + row["trace_id"]).encode()))
                fresh.append({"task_id": row["task_id"], "root_id": row["root_id"], "trace_id": row["trace_id"],
                    "output_budget_tokens": row["output_budget_tokens"], "provider": "AkashML", "seed": row["seed"],
                    "parent_trace_id": previous["trace_id"], "parent_condition_id": previous["condition_id"],
                    "parent_status": previous["status"], "parent_response_sha256": previous.get("response_sha256")})
            records.append(row)
        mapping_raw = save("reuse-mapping", {"condition": "R1", "independent_roots": 24,
            "parent_results_sha256": sha(a_result_raw), "reused_records": reused, "new_records": fresh})
        result = {"phase": "pilot_v2_provider_recovery_R1", "condition": "R1", "protocol_sha256": sha(p_raw),
            "corpus_sha256": sha(taskraw), "source_inventory_sha256": sha(inventory_raw), "dispatch_plan_sha256": sha(b"R1-plan"),
            "reuse_mapping_sha256": sha(mapping_raw), "parent_results_sha256": sha(a_result_raw), "all_planned_cells": 192,
            "new_planned_calls": 96, "reused_records": 96, "independent_roots": 24, "records": records,
            "physical_record_phase_policy": "Legacy classifier phase; R1 protocol and membership mapping are explicit",
            "charged_or_reserved_rub": "110", "completed_utc": "2026-11-08T15:00:00+00:00"}
        save("results", result)
        for name, document, quote_rows in (("parent-cost-plan", a_result, original), ("cost-plan", result, [row for row in records if row["model"] == GPT])):
            save(name, {**{field: document[field] for field in ("protocol_sha256", "source_inventory_sha256", "dispatch_plan_sha256")},
                        "cells": [{"call_id": row["trace_id"], "reservation_rub": "0.04" if row["model"] == DS else "0.06",
                                   "quote_receipt_sha256": sha(b"fixture-quote")} for row in quote_rows]})
        self.support = summarize_support(records, tasks, [DS, GPT])
        save("class-support", self.support, canonical(self.support) + b"\n")
        self.output, self.report = self.work / "output", self.work / "report.md"

    def test_all_denominators_no_support_and_byte_identical_rerun(self):
        input_before = {name: path.read_bytes() for name, path in self.paths.items()}
        result = build(self.paths, self.output, self.report)
        self.assertIsNone(result["selected_common_output_cap"])
        rows = json.loads((self.output / "coverage.json").read_bytes())
        self.assertEqual(len(rows), 12)
        self.assertEqual(len(json.loads((self.output / "coverage-by-stratum.json").read_bytes())), 144)
        self.assertTrue(all(row["planned_attempts"] == 48 and row["planned_roots"] == 24 for row in rows))
        decision = json.loads((self.output / "future-design-decision.json").read_bytes())
        self.assertEqual(len(decision["conditional_future_forecasts"]), 36)
        self.assertIsNone(decision["final_N_selected"])
        self.assertFalse(decision["independent_replication"])
        self.assertEqual(decision["independent_roots"], 24)
        # 2 variants x(DS quote .04 +GPT quote .06)=.20 per future root.
        self.assertEqual(decision["conditional_future_forecasts"][0]["conditional_generation_root_upper_quote_rub"], "0.20")
        first = {path.name: path.read_bytes() for path in self.output.iterdir()}
        first_report = self.report.read_bytes()
        build(self.paths, self.output, self.report)
        self.assertEqual(first, {path.name: path.read_bytes() for path in self.output.iterdir()})
        self.assertEqual(first_report, self.report.read_bytes())
        self.assertEqual(input_before, {name: path.read_bytes() for name, path in self.paths.items()})

    def test_changed_reused_label_and_new_provider_fail_closed(self):
        result = json.loads(self.paths["results"].read_bytes())
        next(row for row in result["records"] if row["model"] == DS)["correct"] = False
        self.save("results", result)
        with self.assertRaisesRegex(ValueError, "reused DeepSeek row"):
            build(self.paths, self.output, self.report)

    def test_wrong_new_provider_fails_closed(self):
        result = json.loads(self.paths["results"].read_bytes())
        next(row for row in result["records"] if row["model"] == GPT)["provider"] = "DeepInfra"
        self.save("results", result)
        with self.assertRaisesRegex(ValueError, "whole-roster AkashML"):
            build(self.paths, self.output, self.report)

    def test_partial_r1_keeps48_denominator_and_no_cap(self):
        result = json.loads(self.paths["results"].read_bytes())
        row = next(row for row in result["records"] if row["model"] == GPT)
        row.update(status="not_dispatched", attempted=False, request_state="not_dispatched", http_status=None,
                   correct=None, gradable=False, text="", finish_reason=None)
        row.pop("response_sha256", None)
        self.save("results", result)
        tasks = json.loads(self.paths["tasks"].read_bytes())["tasks"]
        self.support = summarize_support(result["records"], tasks, [DS, GPT])
        self.save("class-support", self.support, canonical(self.support) + b"\n")
        build(self.paths, self.output, self.report)
        decision = json.loads((self.output / "future-design-decision.json").read_bytes())
        self.assertFalse(decision["entire_fixed_roster_resolved"])
        self.assertIsNone(decision["selected_output_cap_for_future_design"])
        rows = json.loads((self.output / "coverage.json").read_bytes())
        self.assertTrue(all(row["planned_attempts"] == 48 for row in rows))

    def test_exact_frozen_cli_optional_input_hashes_are_accepted_without_provenance_in_support(self):
        support = copy.deepcopy(self.support)
        support["input_sha256"] = {"records": sha(self.paths["results"].read_bytes()), "tasks": sha(self.paths["tasks"].read_bytes())}
        self.save("class-support", support, canonical(support) + b"\n")
        build(self.paths, self.output, self.report)
        self.assertEqual(json.loads(self.paths["class-support"].read_bytes()), support)

    def test_fabricated_cap_selection_in_saved_support_fails_replay(self):
        support = copy.deepcopy(self.support)
        support["selected_common_output_cap"] = 2048
        self.save("class-support", support, canonical(support) + b"\n")
        with self.assertRaisesRegex(ValueError, "frozen statistics replay"):
            build(self.paths, self.output, self.report)

    def test_gpt_support_cannot_overcome_zero_reused_deepseek_error_support(self):
        result = json.loads(self.paths["results"].read_bytes())
        for row in result["records"]:
            if row["model"] == GPT and row["task_id"] in {"root0-v0", "root1-v0", "root2-v0"}:
                row["correct"] = False
        self.save("results", result)
        tasks = json.loads(self.paths["tasks"].read_bytes())["tasks"]
        support = summarize_support(result["records"], tasks, [DS, GPT])
        self.save("class-support", support, canonical(support) + b"\n")
        build(self.paths, self.output, self.report)
        gpt = [row for row in support["groups"] if row["model"] == GPT and row["prefix_budget_words"] == 256]
        self.assertTrue(all(row["engineering_readiness"] for row in gpt))
        decision = json.loads((self.output / "future-design-decision.json").read_bytes())
        self.assertTrue(decision["entire_fixed_roster_resolved"])
        self.assertIsNone(decision["selected_output_cap_for_future_design"])

    def test_standalone_portable_report_needs_no_live_runner_or_stage0_dependencies(self):
        project = self.work / "flat-project"
        for name in ("pilot_v2/__init__.py", "pilot_v2/statistical_design.py", "scripts/summarize_pilot_v2.py",
                     "scripts/summarize_pilot_v2_recovery.py"):
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        command = [sys.executable, "-I", str(project / "scripts/summarize_pilot_v2_recovery.py")]
        for name, path in self.paths.items():
            command += ["--" + name, str(path)]
        command += ["--output-dir", str(self.work / "portable-output"), "--report", str(self.work / "portable-report.md")]
        result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["new_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
