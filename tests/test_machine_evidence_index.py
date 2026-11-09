"""Synthetic integrity-index tests, never model calls or scientific claims."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("machine_integrity_index", ROOT / "scripts/build_machine_evidence_index.py")
INDEX = importlib.util.module_from_spec(spec)
spec.loader.exec_module(INDEX)


def data(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


class MachineEvidenceIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = {}
        def put(name, value):
            path = self.root / (name + ".json")
            path.write_bytes(data(value))
            self.paths[name] = path
            return path
        self.put = put
        self.inputs = {"items": [{"item_id": "item-" + str(i)} for i in range(200)],
                       "audit_item_ids": ["item-" + str(i) for i in range(20)]}
        self.input_path = put("inputs", self.inputs)
        self.inventory = {"files": {"fixture.py": INDEX.sha(b"# exact source\r\n"), "empty.py": INDEX.sha(b"")}}
        self.inventory_bytes = data(self.inventory)
        self.launch = [{"id": "prior-" + str(i), "reservation_rub": "0", "charged_or_reserved_rub": "0",
                        "reported_cost_rub": None, "state": "finished"} for i in range(984)]
        self.ledger = self.launch + [{"id": "new-1", "reservation_rub": ".01", "charged_or_reserved_rub": ".01",
                                      "reported_cost_rub": None, "state": "unknown"}]
        self.ledger_path = put("ledger-final", self.ledger)
        self.protocol = {"status": "prospective_frozen_machine_development",
            "inputs": {"items": 200, "roots": 24, "file_sha256": INDEX.sha(self.input_path.read_bytes())},
            "allocation": {"maximum_calls": 2100},
            "source_freeze": {"expected_source_inventory_sha256": INDEX.sha(self.inventory_bytes)},
            "parent": {"launch_ledger_rows": 984, "launch_ledger_sha256": INDEX.sha(data(self.launch))}}
        protocol_path = put("protocol", self.protocol)
        digest = INDEX.sha(protocol_path.read_bytes())
        self.scope = self.root / "live/machine-development" / digest
        self.scope.mkdir(parents=True)
        (self.root / "live/ledger.json").write_bytes(b"This live ledger must never be opened.")
        for name, raw in (("protocol.json", protocol_path.read_bytes()), ("items.json", self.input_path.read_bytes()),
                          ("source-inventory.json", self.inventory_bytes), ("ledger-launch.json", data(self.launch)),
                          ("cost-plan.json", data({"fixture": True}))):
            (self.scope / name).write_bytes(raw)
        (self.scope / "source").mkdir()
        (self.scope / "source/fixture.py").write_bytes(b"# exact source\r\n")
        (self.scope / "source/empty.py").write_bytes(b"")
        self.plan = {"cells": [{"call_id": format(i, "064x")} for i in range(2100)],
                     "source_inventory_sha256": INDEX.sha(self.inventory_bytes)}
        (self.scope / "dispatch-plan.json").write_bytes(data(self.plan))
        self.observed = {"phase": "machine_development_annotation", "protocol_sha256": digest,
            "items_sha256": INDEX.sha(self.input_path.read_bytes()), "source_inventory_sha256": INDEX.sha(self.inventory_bytes),
            "dispatch_plan_sha256": INDEX.sha(data(self.plan)), "maximum_calls": 2100,
            "completed_utc": "2026-11-08T23:00:00+00:00", "charged_or_reserved_rub": ".01",
            "all_planned_calls": self.plan["cells"], "items": self.inputs["items"],
            "audits": {identity: {} for identity in self.inputs["audit_item_ids"]},
            "E0": "not_passed", "human_gold": "not_created", "scientific_validity": "not_assessed"}
        result_path = put("results", self.observed)
        (self.scope / "results.json").write_bytes(result_path.read_bytes())
        summary = {"planned_items": 200, "distinct_root_blocks": 24, "accuracy_estimated": False,
            "audit_updates_primary": False, "protocol_sha256": digest, "call_coverage": {"all_planned_slots": 2100},
            "E0": "not_passed", "human_gold": "not_created", "scientific_validity": "not_assessed",
            "input_sha256": {"protocol": digest, "items": INDEX.sha(self.input_path.read_bytes()),
                "results": INDEX.sha(result_path.read_bytes()), "inventory": INDEX.sha(self.inventory_bytes),
                "plan": INDEX.sha(data(self.plan)), "ledger": INDEX.sha(self.ledger_path.read_bytes()),
                "launch_ledger": INDEX.sha(data(self.launch))}}
        summary_path = put("summary", summary)
        put("budget", {"launch_prefix_preserved": True, "launch": {"rows": 984},
                       "final": {"rows": 985, "charged_or_reserved_rub": ".01"}})
        manifest_path = put("export", {"format": INDEX.FORMAT,
            "payload": {"protocol_sha256": digest, "source_inventory_sha256": INDEX.sha(self.inventory_bytes)}})
        put("reproduction", {"status": "passed", "network_attempts": 0, "results_exact": True, "summary_exact": True,
            "bundle_manifest_sha256": INDEX.sha(manifest_path.read_bytes()),
            "results_sha256": INDEX.sha(result_path.read_bytes()), "summary_sha256": INDEX.sha(summary_path.read_bytes())})

    def build(self, **changes):
        args = {"scope": self.scope, "protocol": self.paths["protocol"], "inputs": self.input_path,
                "results": self.paths["results"], "summary": self.paths["summary"], "budget": self.paths["budget"],
                "ledger_snapshot": self.ledger_path, "export_manifest": self.paths["export"],
                "reproduction": self.paths["reproduction"], "root": self.root}
        return INDEX.build_index(**{**args, **changes})

    def test_exact_snapshot_source_and_empty_inventory_keep_pending_scientific_status(self):
        index = self.build()
        roles = {row["role"] for row in index["artifacts"]}
        self.assertTrue({"protocol", "tasks", "results", "source"} <= roles)
        source = next(row for row in index["artifacts"] if row["role"] == "source")
        self.assertEqual(source["sha256"], INDEX.sha(b"# exact source\r\n"))
        self.assertEqual(index["empty_source_files_retained_in_inventory"][0]["sha256"], INDEX.sha(b""))
        self.assertTrue(all(row["bytes"] > 0 for row in index["artifacts"]))
        self.assertEqual(index["E0"], "not_passed")
        self.assertEqual(index["review"], "not_requested")
        self.assertEqual(index["scientific_validity"], "not_assessed")
        self.assertTrue(index["registered_after_collection"])

    def test_live_ledger_and_incomplete_or_corrupt_sources_are_refused(self):
        with self.assertRaisesRegex(ValueError, "FINAL ledger"):
            self.build(ledger_snapshot=self.root / "live/ledger.json")
        path = self.scope / "source/fixture.py"
        path.write_bytes(b"# exact source\n")
        with self.assertRaisesRegex(ValueError, "exact source snapshot"):
            self.build()
        path.write_bytes(b"# exact source\r\n")
        bad = copy.deepcopy(self.observed)
        bad["all_planned_calls"].pop()
        self.put("results", bad)
        (self.scope / "results.json").write_bytes(self.paths["results"].read_bytes())
        with self.assertRaisesRegex(ValueError, "registry lost"):
            self.build()

    def test_failed_or_network_using_replay_never_binds_a_completed_integrity_roster(self):
        replay = json.loads(self.paths["reproduction"].read_bytes())
        replay["network_attempts"] = 1
        self.put("reproduction", replay)
        with self.assertRaisesRegex(ValueError, "zero-network"):
            self.build()


if __name__ == "__main__":
    unittest.main()
