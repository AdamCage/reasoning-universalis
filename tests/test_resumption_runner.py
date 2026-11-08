"""Offline tests of dispatch safety, provenance, and exact resumption.

These transports never access RouterAI or incur model costs.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest

from resumption.runner import CANDIDATES, HISTORICAL_SHA, Runner, Settings, balanced_tasks, chunks, sha
from stage0.runner import StopRun, capture_body, encode


def task(task_id="item0", root="root0", split="train"):
    return {"task_id": task_id, "root_id": root, "split": split, "domain": "math",
            "family": "fixed_fold", "difficulty": "hard",
            "generator_version": "resumption-generators-v1",
            "prompt": "Start with 2 and add 3. Return ANSWER: <integer>.",
            "data": {"start": 2, "steps": [["add", 3]]}}


class FakeTransport:
    def __init__(self, *, paid=None, price="0.00001"):
        self.calls = []
        self.paid = paid
        self.price = price
        self.lock = threading.Lock()

    def __call__(self, path, key=None, body=None, timeout=30):
        with self.lock:
            self.calls.append((path, body))
        if path == "/models":
            return {"http_status": 200, "json": {"data": [{"id": m} for m in CANDIDATES]}}
        if path.endswith("/endpoints"):
            return {"http_status": 200, "json": {"data": {"endpoints": [
                {"pricing_units": {"prompt": "token", "completion": "token"},
                 "pricing": {"prompt": self.price, "completion": self.price}}]}}}
        if self.paid:
            return self.paid(path, body)
        if path == "/embeddings":
            payload = {"model": body["model"], "data": [
                {"index": i, "embedding": [1.] + [0.] * 1023} for i in range(len(body["input"]))]}
        else:
            payload = {"model": body["model"], "provider": "FakeProvider", "usage": {"cost": .001},
                       "choices": [{"finish_reason": "stop", "message": {
                           "reasoning": "Two plus three is five.", "content": "ANSWER: 5"}}]}
        return {"http_status": 200, **capture_body(encode(payload), key)}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.protocol = self.base / "protocol-source.json"
        self.protocol.write_text('{"design":"offline-test-only"}', encoding="utf-8")
        self.corpus = self.base / "tasks-source.json"
        self.corpus.write_bytes(encode({"tasks": [task()]}))

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, transport=None, **settings):
        config = Settings(state=self.base / "state", key="offline-secret", **settings)
        runner = Runner(config, transport or FakeTransport())
        runner.bind(self.protocol, self.corpus)
        return runner

    def test_historical_ledger_restored_exactly_and_not_reset(self):
        runner = self.runner()
        self.assertEqual(sha(runner.ledger_path.read_bytes()), HISTORICAL_SHA)
        self.assertEqual(runner.budget()["charged_or_reserved_rub"], "246.7988793802352")
        runner.ledger_path.write_text("[]", encoding="utf-8")
        with self.assertRaises(StopRun):
            Runner(Settings(state=runner.state), FakeTransport())

    def test_dry_run_uses_no_network_or_key(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        runner.settings.key = ""
        result = runner.dry_run({"tasks": [task()]}, CANDIDATES)
        self.assertEqual(result["paid_requests"], 0)
        self.assertFalse(result["credential_present"])
        self.assertEqual(transport.calls, [])
        self.assertEqual(sha(runner.ledger_path.read_bytes()), HISTORICAL_SHA)

    def test_protocol_and_corpus_are_immutable(self):
        runner = self.runner()
        self.protocol.write_text("{}", encoding="utf-8")
        with self.assertRaises(StopRun):
            runner.bind(self.protocol, self.corpus)

    def test_operational_admission_does_not_claim_full_trace_or_e0(self):
        runner = self.runner()
        record = runner.chat(CANDIDATES[0], task(), -1, admission=True)
        self.assertEqual(record["status"], "completed")
        self.assertTrue(record["correct"])
        self.assertFalse(record["full_visible_trace"])
        self.assertEqual(record["E0"], "not_passed")
        self.assertTrue(runner._routes()[0]["observed_trace_admitted"])

    def test_unadmitted_model_stops_before_paid_call(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        with self.assertRaises(StopRun):
            runner.chat(CANDIDATES[0], task())
        self.assertEqual(transport.calls, [])

    def test_admission_identity_mismatch_and_truncation_rejected(self):
        for change in ("model", "finish"):
            def paid(path, body):
                return {"http_status": 200, "json": {"model": "wrong" if change == "model" else body["model"],
                        "provider": "FakeProvider", "choices": [{
                            "finish_reason": "length" if change == "finish" else "stop",
                            "message": {"reasoning": "Some observed words", "content": "ANSWER: 5"}}]}}
            state = self.base / change
            runner = Runner(Settings(state=state, key="offline-secret"), FakeTransport(paid=paid))
            runner.bind(self.protocol, self.corpus)
            self.assertEqual(runner.chat(CANDIDATES[0], task(), -1, True)["status"], "excluded")
            self.assertEqual(runner._routes(), [])

    def test_saved_admission_evidence_tampering_blocks_collection(self):
        runner = self.runner()
        record = runner.chat(CANDIDATES[0], task(), -1, True)
        (runner.calls / record["trace_id"] / "response.json").write_text("{}")
        with self.assertRaises(StopRun):
            runner.chat(CANDIDATES[0], task())

    def test_unknown_attempt_is_reserved_and_never_resent(self):
        def fail(path, body):
            raise RuntimeError("offline-secret must never be written")
        transport = FakeTransport(paid=fail)
        runner = self.runner(transport)
        a = runner.chat(CANDIDATES[0], task(), -1, True)
        b = runner.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(a["trace_id"], b["trace_id"])
        self.assertEqual(sum(p == "/chat/completions" for p, _ in transport.calls), 1)
        self.assertGreater(Decimal(runner.budget()["charged_or_reserved_rub"]), Decimal("246.7988793802352"))
        self.assertEqual(json.loads(runner.ledger_path.read_text())[-1]["state"], "unknown")
        for path in runner.state.rglob("*.json"):
            self.assertNotIn("offline-secret", path.read_text())

    def test_provider_drift_is_excluded(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        runner.chat(CANDIDATES[0], task(), -1, True)
        def drift(path, body):
            return {"http_status": 200, "json": {"model": body["model"], "provider": "ChangedProvider",
                    "choices": [{"finish_reason": "stop", "message": {
                        "reasoning": "Observed words", "content": "ANSWER: 5"}}]}}
        transport.paid = drift
        record = runner.chat(CANDIDATES[0], task())
        self.assertEqual(record["status"], "excluded")
        self.assertFalse(record["provider_route_verified"])

    def test_concurrent_reservations_never_cross_known_cap(self):
        runner = self.runner()
        runner.price(CANDIDATES[0])
        # Leave less than one conservative request reservation available.
        runner.settings.cap = Decimal(runner.budget()["charged_or_reserved_rub"]) + Decimal("0.01")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(runner.chat, CANDIDATES[0], task(str(i), str(i)), -1, True) for i in range(3)]
        for future in futures:
            with self.assertRaises(StopRun):
                future.result()
        self.assertEqual(sha(runner.ledger_path.read_bytes()), HISTORICAL_SHA)

    def test_reported_cost_cannot_reduce_reservation(self):
        runner = self.runner()
        runner.chat(CANDIDATES[0], task(), -1, True)
        row = json.loads(runner.ledger_path.read_text())[-1]
        self.assertGreater(Decimal(row["reservation_rub"]), Decimal(row["reported_cost_rub"]))
        self.assertEqual(row["reservation_rub"], row["charged_or_reserved_rub"])

    def test_paired_root_tasks_may_share_split_but_cannot_cross(self):
        runner = self.runner()
        other = task("item1", "root0", "test")
        with self.assertRaises(StopRun):
            runner.collect([task(), other], [CANDIDATES[0]], admission=True)
        other["split"] = "train"
        # The prompts happen to match, but dispatch identity includes task id.
        result = runner.collect([task(), other], [CANDIDATES[0]], admission=True)
        self.assertEqual(len({r["trace_id"] for r in result["records"]}), 2)

    def test_embedding_validation_and_offsets(self):
        runner = self.runner()
        record = runner.chat(CANDIDATES[0], task(), -1, True)
        record["text"] = "  " + "\t".join("word" + str(i) for i in range(34))
        result = runner.embed([record], "baai/bge-m3", 2)
        segments = result["records"][0]["embeddings"]["baai/bge-m3"]
        self.assertEqual([s["word_end"] for s in segments], [16, 32, 34])
        for segment in segments:
            self.assertEqual(record["text"][segment["start"]:segment["end"]], segment["text"])
            self.assertEqual(len(segment["vector"]), 1024)

    def test_deadline_is_preserved_on_resume_and_blocks_before_dispatch(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        runner = self.runner(deadline=past)
        fresh = Runner(Settings(state=runner.state, key="offline-secret"), FakeTransport())
        fresh.bind(self.protocol, self.corpus)
        self.assertEqual(fresh.settings.deadline, past)
        with self.assertRaises(StopRun):
            fresh.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(sha(fresh.ledger_path.read_bytes()), HISTORICAL_SHA)

    def test_chunk_maximum_never_reads_future_words(self):
        text = " ".join(str(i) for i in range(600))
        segments = chunks(text)
        self.assertEqual(len(segments), 32)
        self.assertEqual(segments[-1]["word_end"], 512)
        self.assertEqual(segments[-1]["text"].split()[-1], "511")

    def test_censored_semantic_records_are_accepted_by_analysis(self):
        from resumption.analysis import prefixes
        transport = FakeTransport()
        def answer_marker(path, body):
            return {"http_status": 200, "json": {"model": body["model"], "provider": "FakeProvider",
                    "choices": [{"finish_reason": "stop", "message": {
                        "reasoning": " ".join("word" + str(i) for i in range(128)) + " ANSWER: internal label",
                        "content": "ANSWER: 5"}}]}}
        transport.paid = answer_marker
        runner = self.runner(transport)
        runner.chat(CANDIDATES[0], task(), -1, True)
        record = runner.chat(CANDIDATES[0], task())
        self.assertNotIn("ANSWER:", record["text"])
        self.assertIn("ANSWER:", record["raw_reasoning_text"])
        self.assertIsNotNone(record["predictor_censor"]["first_answer_marker_character"])
        transport.paid = None
        output = runner.embed([record], "baai/bge-m3")
        eligible, _ = prefixes(output["records"], 128, "baai/bge-m3")
        self.assertEqual(len(eligible), 1)
        for segment in output["records"][0]["embeddings"]["baai/bge-m3"]:
            self.assertEqual(segment["model_id"], "baai/bge-m3")
            self.assertTrue(segment["identity_verified"])
            self.assertEqual(segment["input_sha256"], sha(segment["text"].encode()))

    def test_collection_queue_interleaves_models_for_every_task(self):
        runner = self.runner(concurrency=1)
        order = []
        def fake_chat(model, item, sample_index=0, admission=False):
            order.append((model, item["task_id"], sample_index))
            return {"trace_id": str(len(order)), "status": "completed"}
        runner.chat = fake_chat
        selected = [task("b", "b"), task("a", "a", "test"), task("c", "c", "validation")]
        runner.collect(selected, CANDIDATES, samples=2)
        first_task = balanced_tasks(selected)[0]["task_id"]
        self.assertEqual(order[:3], [(model, first_task, 0) for model in CANDIDATES])
        self.assertEqual({entry[2] for entry in order[:len(selected) * 3]}, {0})

    def test_collection_ceiling_preserves_embedding_headroom(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        runner.settings.collection_cap = Decimal(runner.budget()["charged_or_reserved_rub"]) + Decimal("0.01")
        with self.assertRaisesRegex(StopRun, "reserved for embeddings"):
            runner.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(sum(p == "/chat/completions" for p, _ in transport.calls), 0)
        self.assertEqual(sha(runner.ledger_path.read_bytes()), HISTORICAL_SHA)

    def test_metadata_plan_does_not_make_paid_requests_or_promises(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        plan = runner.plan({"tasks": [task()], "admission_tasks": [task("admission", "admission")]}, CANDIDATES, 2)
        self.assertEqual(plan["paid_requests"], 0)
        self.assertEqual(plan["generation_requests"], 6)
        self.assertEqual(plan["maximum_admission_requests"], 3)
        self.assertTrue(all(body is None for _, body in transport.calls))
        self.assertIn("not a cost guarantee", plan["embedding_cost"])
        self.assertEqual(sha(runner.ledger_path.read_bytes()), HISTORICAL_SHA)

    def test_placeholder_and_whitespace_credentials_rejected(self):
        for key in (" ", "two words", "YOUR_LOCAL_KEY", "CHANGE_ME", "<ROUTERAI_API_KEY>"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Settings(key=key)

    def test_changed_completion_cap_cannot_resend_logical_attempt(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        runner.chat(CANDIDATES[0], task(), -1, True)
        runner.settings.max_tokens = 8192
        with self.assertRaisesRegex(StopRun, "logical request changed"):
            runner.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(sum(p == "/chat/completions" for p, _ in transport.calls), 1)

    def test_protocol_sampling_mismatch_blocks_before_any_network(self):
        self.protocol.write_bytes(encode({"generation": {"max_output_tokens": 8192}}))
        transport = FakeTransport()
        runner = Runner(Settings(state=self.base / "state"), transport)
        with self.assertRaisesRegex(StopRun, "Sampling configuration differs"):
            runner.bind(self.protocol, self.corpus)
        self.assertEqual(transport.calls, [])

    def test_source_snapshot_bound_and_drift_blocks_before_dispatch(self):
        transport = FakeTransport()
        runner = self.runner(transport)
        inventory_path = runner.state / "source-inventory.json"
        inventory = json.loads(inventory_path.read_text())
        self.assertEqual(sha(inventory_path.read_bytes()), runner.source_inventory_digest)
        for name, digest in inventory["files"].items():
            self.assertEqual(sha((runner.state / "source" / name).read_bytes()), digest)
        source_files = runner._source_files()
        source_files["resumption/runner.py"] += b"\n# simulated source drift\n"
        runner._source_files = lambda: source_files
        with self.assertRaisesRegex(StopRun, "source changed"):
            runner.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(transport.calls, [])
        resumed = Runner(Settings(state=runner.state), FakeTransport())
        resumed._source_files = lambda: source_files
        with self.assertRaisesRegex(StopRun, "source changed"):
            resumed.bind(self.protocol, self.corpus)

    def test_trace_records_bind_source_inventory_and_verifier(self):
        runner = self.runner()
        record = runner.chat(CANDIDATES[0], task(), -1, True)
        self.assertEqual(record["source_inventory_sha256"], runner.source_inventory_digest)
        inventory = json.loads((runner.state / "source-inventory.json").read_text())
        self.assertEqual(record["verifier_source_sha256"], inventory["files"]["resumption/generator_audit.py"])

    def test_unknown_embedding_chunks_cannot_be_resent_by_rebatching(self):
        def unknown(path, body):
            raise RuntimeError("simulated lost embedding response")
        transport = FakeTransport(paid=unknown)
        runner = self.runner(transport)
        record = {"trace_id": "test-trace", "status": "completed", "text": "word " * 64}
        with self.assertRaisesRegex(StopRun, "Embedding identity"):
            runner.embed([record], "baai/bge-m3", batch_size=2)
        with self.assertRaisesRegex(StopRun, "already attempted in another batch"):
            runner.embed([record], "baai/bge-m3", batch_size=1)
        self.assertEqual(sum(path == "/embeddings" for path, _ in transport.calls), 1)
        rows = json.loads(runner.ledger_path.read_text())
        self.assertEqual(len(rows), 33)
        self.assertEqual(rows[-1]["state"], "unknown")
        registry = json.loads((runner.state / "embedding-attempted-chunks.json").read_text())
        self.assertEqual(len(registry["chunks"]), 2)

    def test_resuming_can_tighten_deadline_but_never_extend_it(self):
        initial = (datetime.now(timezone.utc) + timedelta(hours=7)).isoformat()
        runner = self.runner(deadline=initial)
        tighter = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        resumed = Runner(Settings(state=runner.state, deadline=tighter), FakeTransport())
        resumed.bind(self.protocol, self.corpus)
        self.assertEqual(resumed.settings.deadline, tighter)
        later = Runner(Settings(state=runner.state, deadline=initial), FakeTransport())
        later.bind(self.protocol, self.corpus)
        self.assertEqual(later.settings.deadline, tighter)

    def test_completed_collection_recovers_after_deadline_without_key_or_network(self):
        runner = self.runner()
        runner.chat(CANDIDATES[0], task(), -1, True)
        initial = runner.collect([task()], [CANDIDATES[0]], samples=1)
        self.assertEqual(len(initial["records"]), 1)
        budget_before = runner.ledger_path.read_bytes()
        calls = []
        def no_network(*args, **kwargs):
            calls.append(args)
            raise AssertionError("offline recovery accessed the network")
        expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        recovered = Runner(Settings(state=runner.state, key="", deadline=expired), no_network)
        recovered.bind(self.protocol, self.corpus)
        result = recovered.collect([task()], [CANDIDATES[0]], samples=1)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["trace_id"], initial["records"][0]["trace_id"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(len(json.loads((runner.state / "results.json").read_text())["records"]), 1)
        self.assertEqual(calls, [])
        self.assertEqual(recovered.ledger_path.read_bytes(), budget_before)

    def test_protocol_deadline_caps_the_default_local_window(self):
        declared = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        self.protocol.write_text(json.dumps({"generation": {"dispatch_deadline_utc": declared}}))
        runner = self.runner()
        self.assertEqual(runner.settings.deadline, declared)
        resumed = Runner(Settings(state=runner.state), FakeTransport())
        resumed.bind(self.protocol, self.corpus)
        self.assertEqual(resumed.settings.deadline, declared)

    def test_completed_embeddings_recover_after_deadline_without_key_or_network(self):
        runner = self.runner()
        record = {"trace_id": "test-trace", "status": "completed", "text": "word " * 32}
        initial = runner.embed([record], "baai/bge-m3", batch_size=2)
        budget_before = runner.ledger_path.read_bytes()
        calls = []
        def no_network(*args, **kwargs):
            calls.append(args)
            raise AssertionError("offline recovery accessed the network")
        expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        recovered = Runner(Settings(state=runner.state, key="", deadline=expired), no_network)
        recovered.bind(self.protocol, self.corpus)
        result = recovered.embed([record], "baai/bge-m3", batch_size=2)
        self.assertEqual(result["records"], initial["records"])
        self.assertEqual(calls, [])
        self.assertEqual(recovered.ledger_path.read_bytes(), budget_before)


if __name__ == "__main__":
    unittest.main()
