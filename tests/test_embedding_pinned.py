"""New provider conditions preserve old attempts and never bypass unknowns."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from resumption.runner import EMBEDDERS, Runner, Settings, chunks, sha
from stage0.runner import StopRun, capture_body, encode


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("embedding_pinned", ROOT / "scripts/collect_embedding_pinned.py")
pinned = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pinned)


class Transport:
    def __init__(self):
        self.calls = []
        self.provider = "FakeProvider"
        self.returned = None
        self.unknown = False

    def __call__(self, path, key=None, body=None, timeout=30):
        if path.endswith("/endpoints"):
            return {"http_status": 200, "json": {"data": {"endpoints": [{
                "provider_name": "FakeProvider", "pricing_units": {"prompt": "token", "completion": "token"},
                "pricing": {"prompt": "0.000001", "completion": 0}}]}}}
        self.calls.append(copy.deepcopy(body))
        if self.unknown:
            return {"http_status": None, "network_error": "SyntheticTimeout", "json": {}}
        dimension = 1024 if body["model"] == EMBEDDERS[0] else 4096
        payload = {"model": self.returned or body["model"].upper(), "provider": self.provider,
                   "data": [{"index": index, "embedding": [1.] + [0.] * (dimension - 1)}
                            for index in range(len(body["input"]))]}
        return {"http_status": 200, **capture_body(encode(payload), key)}


class PinnedEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.protocol = self.project / "protocol.json"
        self.protocol.write_bytes(encode({"synthetic_fixture": True}))
        self.corpus = self.project / "corpus.json"
        self.corpus.write_bytes(encode({"tasks": []}))
        self.transport = Transport()
        self.runner = Runner(Settings(state=self.project / "state", key="fixture-credential"), self.transport)
        self.runner.bind(self.protocol, self.corpus)
        self.document = {"protocol_sha256": self.runner.protocol_digest, "corpus_sha256": self.runner.tasks_digest,
                         "records": [{"trace_id": "original-trace", "status": "completed", "text": "word " * 48}]}
        self.results = self.project / "results.json"
        self.results.write_bytes(encode(self.document))
        self.segments = chunks(self.document["records"][0]["text"])
        self.parents, self.bad = [], []
        for model, position, rejected in ((EMBEDDERS[0], 0, False), (EMBEDDERS[0], 1, True),
                                         (EMBEDDERS[1], 0, False), (EMBEDDERS[1], 1, False),
                                         (EMBEDDERS[1], 2, True)):
            self.transport.provider = "OtherProvider" if rejected else "FakeProvider"
            self.transport.returned = "parasail-bge-m3" if rejected and model == EMBEDDERS[0] else None
            segment = self.segments[position]
            result = self.runner.paid("embedding", [("original-trace", segment["start"], segment["end"])], model,
                                      {"model": model, "input": [segment["text"]]})
            self.parents.append(result["call_id"])
            if rejected:
                self.bad.append(result["call_id"])
        self.transport.provider, self.transport.returned = "FakeProvider", None
        self.script = self.project / pinned.COLLECTOR_PATH
        self.script.parent.mkdir()
        self.script.write_bytes((ROOT / pinned.COLLECTOR_PATH).read_bytes())
        self.amendment = self.project / pinned.AMENDMENT_PATH
        self.amendment.parent.mkdir()
        self.amendment_value = {"schema_version": 1, "amendment_id": "synthetic-pinned-condition",
            "base_protocol_sha256": self.runner.protocol_digest, "script_sha256": sha(self.script.read_bytes()),
            "model_identity_rule": pinned.RULE, "models": list(EMBEDDERS),
            "expected_routes": {EMBEDDERS[0]: {"provider": "FakeProvider", "dimension": 1024},
                                EMBEDDERS[1]: {"provider": "FakeProvider", "dimension": 4096}},
            "parent_call_ids": self.parents, "allowed_replacement_call_ids": self.bad,
            "created_utc": datetime.now(timezone.utc).isoformat()}
        self.amendment.write_bytes(encode(self.amendment_value))

    def bind(self):
        return pinned.bind_condition(self.runner, self.amendment, self.protocol, self.results, project=self.project)

    def test_three_known_good_batches_reused_and_only_declared_bad_routes_remeasured(self):
        before = json.loads(self.runner.ledger_path.read_bytes())
        source_before = (self.runner.state / "source-inventory.json").read_bytes()
        original_raw = {call: (self.runner.calls / call / "response.json").read_bytes() for call in self.parents}
        binding, mapping = self.bind()
        outputs = [pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), model, binding, mapping, 1)
                   for model in EMBEDDERS]
        self.assertEqual(len(self.transport.calls), 8)  # five prior + two BGE + one Qwen
        self.assertEqual([(out["reused_known_chunks"], out["new_condition_chunks"]) for out in outputs], [(1, 2), (2, 1)])
        for body in self.transport.calls[5:]:
            self.assertEqual(body["provider"], {"order": ["FakeProvider"], "allow_fallbacks": False})
        after = json.loads(self.runner.ledger_path.read_bytes())
        self.assertEqual(after[:len(before)], before)
        self.assertEqual((self.runner.state / "source-inventory.json").read_bytes(), source_before)
        for call, data in original_raw.items():
            self.assertEqual((self.runner.calls / call / "response.json").read_bytes(), data)
        for model, output in zip(EMBEDDERS, outputs):
            record = output["records"][0]
            self.assertEqual(record["trace_id"], "original-trace")
            for segment in record["embeddings"][model]:
                if segment["reused_known_valid"]:
                    self.assertFalse(segment["request_route_pinned"])
                    self.assertEqual(segment["paid_trace_id"], "original-trace")
                else:
                    self.assertTrue(segment["request_route_pinned"])
                    self.assertEqual(mapping["trace_mapping"][segment["paid_trace_id"]], "original-trace")
            path = self.runner.state / (model.replace("/", "_") + "-embedded.json")
            self.assertEqual(path.read_bytes(), encode(output))
        paid = len(self.transport.calls)
        pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), paid)

    def test_unknown_attempt_in_another_condition_blocks_new_dispatch(self):
        other = "b" * 64
        directory = self.runner.state / "embedding-conditions" / other
        directory.mkdir(parents=True)
        (directory / "mapping.json").write_bytes(encode({"condition_sha256": other,
            "trace_mapping": {other + ":original-trace": "original-trace"}}))
        segment = self.segments[2]
        self.transport.unknown = True
        self.runner.paid("embedding", [(other + ":original-trace", segment["start"], segment["end"])], EMBEDDERS[0],
                         {"model": EMBEDDERS[0], "input": [segment["text"]],
                          "provider": {"order": ["FakeProvider"], "allow_fallbacks": False}})
        before = self.runner.ledger_path.read_bytes()
        calls = len(self.transport.calls)
        binding, mapping = self.bind()
        with self.assertRaisesRegex(StopRun, "Unknown/network"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(self.runner.ledger_path.read_bytes(), before)

    def test_unfinalized_condition_intent_also_blocks_dispatch(self):
        other = "c" * 64
        directory = self.runner.state / "embedding-conditions" / other / "intents"
        directory.mkdir(parents=True)
        segment = self.segments[2]
        (directory / ("d" * 64 + ".json")).write_bytes(encode({"model": EMBEDDERS[0],
            "original_identity": [["original-trace", segment["start"], segment["end"]]]}))
        binding, mapping = self.bind()
        with self.assertRaisesRegex(StopRun, "Unresolved provider-condition intent"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), 5)

    def test_missing_parent_ledger_commitment_and_undeclared_rejection_fail_closed(self):
        ledger = json.loads(self.runner.ledger_path.read_bytes())
        self.runner.ledger_path.write_bytes(encode(ledger[:-1]))
        with self.assertRaisesRegex(StopRun, "shared ledger"):
            self.bind()
        self.runner.ledger_path.write_bytes(encode(ledger))
        self.amendment_value["allowed_replacement_call_ids"] = []
        self.amendment.write_bytes(encode(self.amendment_value))
        binding, mapping = self.bind()
        with self.assertRaisesRegex(StopRun, "Known rejected attempt"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), 5)

    def test_wrong_provider_in_new_condition_is_preserved_and_not_retried(self):
        binding, mapping = self.bind()
        self.transport.provider = "StillWrongProvider"
        with self.assertRaisesRegex(StopRun, "Known rejected attempt"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), 6)
        with self.assertRaisesRegex(StopRun, "Known rejected attempt"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), 6)
        self.assertFalse((self.runner.state / "baai_bge-m3-embedded.json").exists())

    def test_changed_reservation_identity_cannot_hide_an_original_chunk(self):
        binding, mapping = self.bind()
        path = self.runner.calls / self.bad[0] / "reservation.json"
        context = json.loads(path.read_bytes())
        context["identity"][0][0] = "unrelated-trace"
        path.write_bytes(encode(context))
        with self.assertRaisesRegex(StopRun, "reservation identity/request integrity"):
            pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        self.assertEqual(len(self.transport.calls), 5)

    def test_completed_intent_cache_reuses_status_and_invalidates_changed_or_missing_result(self):
        binding, mapping = self.bind()
        pinned.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, mapping, 1)
        targets = {("original-trace", segment["start"], segment["end"]): segment for segment in self.segments}
        index = pinned.AttemptIndex(self.runner, EMBEDDERS[0], targets, binding)
        index.refresh()
        original_read = pinned.read_json
        result_reads = []
        def counting_read(path):
            if Path(path).name == "result.json":
                result_reads.append(Path(path))
            return original_read(path)
        with mock.patch.object(pinned, "read_json", side_effect=counting_read):
            index.refresh()
        self.assertEqual(result_reads, [])
        condition = self.runner.state / "embedding-conditions" / binding["condition_sha256"]
        intent = next((condition / "intents").glob("*.json"))
        result_path = self.runner.calls / intent.stem / "result.json"
        result = json.loads(result_path.read_bytes())
        result["http_status"] = None
        result_path.write_bytes(encode(result))
        with self.assertRaisesRegex(StopRun, "Unknown provider-condition"):
            index.refresh()
        result_path.unlink()
        with self.assertRaisesRegex(StopRun, "Unresolved provider-condition intent"):
            index.refresh()


if __name__ == "__main__":
    unittest.main()
