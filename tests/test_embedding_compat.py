"""Case-only embedding repair uses cached attempts and the existing budget."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from resumption.runner import EMBEDDERS, Runner, Settings, sha
from stage0.runner import StopRun, capture_body, encode


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("embedding_compat", ROOT / "scripts/collect_embedding_compat.py")
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)


class FakeEmbeddingTransport:
    def __init__(self):
        self.paid = 0
        self.returned = {EMBEDDERS[0]: "BAAI/bge-m3", EMBEDDERS[1]: "Qwen/Qwen3-Embedding-8B"}
        self.provider = "FakeProvider"
        self.unknown = False

    def __call__(self, path, key=None, body=None, timeout=30):
        if path.endswith("/endpoints"):
            return {"http_status": 200, "json": {"data": {"endpoints": [{
                "provider_name": "FakeProvider", "pricing_units": {"prompt": "token", "completion": "token"},
                "pricing": {"prompt": "0.000001", "completion": 0}}]}}}
        self.paid += 1
        if self.unknown:
            return {"http_status": None, "json": {}, "network_error": "SyntheticTimeout"}
        dimension = 1024 if body["model"] == EMBEDDERS[0] else 4096
        payload = {"model": self.returned[body["model"]], "provider": self.provider,
                   "data": [{"index": i, "embedding": [1.] + [0.] * (dimension - 1)}
                            for i in range(len(body["input"]))]}
        return {"http_status": 200, **capture_body(encode(payload), key)}


class EmbeddingCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.protocol = self.project / "protocol.json"
        self.protocol.write_bytes(encode({"synthetic_fixture": True}))
        self.corpus = self.project / "corpus.json"
        self.corpus.write_bytes(encode({"tasks": [], "synthetic_fixture": True}))
        self.transport = FakeEmbeddingTransport()
        self.runner = Runner(Settings(state=self.project / "state", key="synthetic-credential"), self.transport)
        self.runner.bind(self.protocol, self.corpus)
        self.document = {"protocol_sha256": self.runner.protocol_digest, "corpus_sha256": self.runner.tasks_digest,
                         "records": [{"trace_id": "synthetic-trace", "status": "completed", "text": "word " * 16}]}
        self.results = self.project / "results.json"
        self.results.write_bytes(encode(self.document))
        self.script = self.project / compat.COLLECTOR_PATH
        self.script.parent.mkdir()
        self.script.write_bytes((ROOT / compat.COLLECTOR_PATH).read_bytes())
        self.amendment = self.project / compat.AMENDMENT_PATH
        self.amendment.parent.mkdir()
        self.amendment.write_bytes(encode({"schema_version": 1, "amendment_id": "synthetic-case-repair",
            "base_protocol_sha256": self.runner.protocol_digest, "script_sha256": sha(self.script.read_bytes()),
            "model_identity_rule": compat.RULE, "models": list(EMBEDDERS),
            "expected_routes": {EMBEDDERS[0]: {"provider": "FakeProvider", "dimension": 1024},
                                EMBEDDERS[1]: {"provider": "FakeProvider", "dimension": 4096}},
            "created_utc": datetime.now(timezone.utc).isoformat()}))

    def binding(self):
        return compat.bind_compatibility(self.runner, self.amendment, self.protocol, self.results, project=self.project)

    def test_two_known_first_batches_are_reused_without_new_paid_calls_or_budget_reset(self):
        for model in EMBEDDERS:
            with self.assertRaisesRegex(StopRun, "Embedding identity"):
                self.runner.embed(copy.deepcopy(self.document["records"]), model, batch_size=1)
        self.assertEqual(self.transport.paid, 2)
        budget_before = self.runner.ledger_path.read_bytes()
        source_before = (self.runner.state / "source-inventory.json").read_bytes()
        binding = self.binding()
        for model in EMBEDDERS:
            result = compat.collect_embeddings(self.runner, copy.deepcopy(self.document), model, binding, batch_size=1)
            segment = result["records"][0]["embeddings"][model][0]
            self.assertEqual(segment["model_id"], model)
            self.assertEqual(segment["returned_model_id"], self.transport.returned[model])
            self.assertEqual(result["cached_batches_reused"], 1)
            self.assertEqual(result["identity_rule"], compat.RULE)
        self.assertEqual(self.transport.paid, 2)
        self.assertEqual(self.runner.ledger_path.read_bytes(), budget_before)
        self.assertEqual((self.runner.state / "source-inventory.json").read_bytes(), source_before)
        self.assertEqual(len(list(self.runner.calls.glob("*/embedding-compatibility.json"))), 2)

    def test_unknown_attempt_is_not_resent_or_released(self):
        self.transport.unknown = True
        with self.assertRaises(StopRun):
            self.runner.embed(copy.deepcopy(self.document["records"]), EMBEDDERS[0], 1)
        before = self.runner.ledger_path.read_bytes()
        with self.assertRaises(StopRun):
            compat.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], self.binding(), 1)
        self.assertEqual(self.transport.paid, 1)
        self.assertEqual(self.runner.ledger_path.read_bytes(), before)
        self.assertEqual(json.loads(before)[-1]["state"], "unknown")

    def test_alias_whitespace_and_nonascii_identity_are_not_authorized(self):
        for returned in ("parasail-bge-m3", " BAAI/bge-m3", "BAAI/bge-m3 ", "baai/bge-mſ"):
            self.assertFalse(compat.ascii_identity(returned, EMBEDDERS[0]))
        self.assertTrue(compat.ascii_identity("BAAI/bge-m3", EMBEDDERS[0]))
        self.transport.returned[EMBEDDERS[0]] = "parasail-bge-m3"
        with self.assertRaises(StopRun):
            self.runner.embed(copy.deepcopy(self.document["records"]), EMBEDDERS[0], 1)
        before = self.runner.ledger_path.read_bytes()
        with self.assertRaises(StopRun):
            compat.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], self.binding(), 1)
        self.assertEqual(self.transport.paid, 1)
        self.assertEqual(self.runner.ledger_path.read_bytes(), before)

    def test_changed_amendment_or_script_binding_fails_without_dispatch(self):
        binding = self.binding()
        self.assertEqual(binding["results_sha256"], sha(self.results.read_bytes()))
        self.script.write_bytes(self.script.read_bytes() + b"\n# changed\n")
        with self.assertRaisesRegex(StopRun, "script hash mismatch"):
            self.binding()
        self.assertEqual(self.transport.paid, 0)

    def test_provider_drift_is_retained_and_rejected(self):
        document = copy.deepcopy(self.document)
        document["records"][0]["text"] = "word " * 32
        self.results.write_bytes(encode(document))
        original = self.transport.__call__
        def transport(path, **kwargs):
            if path == "/embeddings" and self.transport.paid:
                self.transport.provider = "OtherProvider"
            return original(path, **kwargs)
        self.runner.transport = transport
        with self.assertRaisesRegex(StopRun, "expected provider/dimension"):
            compat.collect_embeddings(self.runner, document, EMBEDDERS[0], self.binding(), 1)
        self.assertEqual(self.transport.paid, 2)
        self.assertEqual(len(list(self.runner.calls.glob("*/response.json"))), 2)
        self.assertFalse((self.runner.state / "baai_bge-m3-embedded.json").exists())

    def test_changed_route_is_rejected_before_a_new_request(self):
        binding = self.binding()
        route = self.runner.state / "baai_bge-m3-embedding-route.json"
        route.write_bytes(encode({"model": EMBEDDERS[0], "provider": "OtherProvider", "dimension": 1024}))
        with self.assertRaisesRegex(StopRun, "before dispatch"):
            compat.collect_embeddings(self.runner, copy.deepcopy(self.document), EMBEDDERS[0], binding, 1)
        self.assertEqual(self.transport.paid, 0)


if __name__ == "__main__":
    unittest.main()
