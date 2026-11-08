"""Synthetic, offline checks of reconstruction from original embedding evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


reproduction = module(ROOT / "scripts/reproduce_local.py", "local_reproduction_tested")
exporter = module(ROOT / "scripts/export_local_evidence.py", "local_reproduction_exporter")


class LocalReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.model = "baai/bge-m3"
        self.protocol = {"measurement": {"observed_prefix_words": [128, 256, 512], "chunk_words": 16}}
        self.write("protocol.json", self.protocol)
        self.write("corpus.json", {"synthetic_fixture": True})
        inventory = {"files": {}}
        for relative in ("resumption/analysis.py", "resumption/generator_audit.py"):
            data = (ROOT / relative).read_bytes()
            path = self.state / "source" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            inventory["files"][relative] = reproduction.sha(data)
        self.write("source-inventory.json", inventory)
        self.bindings = {
            "protocol_sha256": reproduction.sha((self.state / "protocol.json").read_bytes()),
            "corpus_sha256": reproduction.sha((self.state / "corpus.json").read_bytes()),
            "source_inventory_sha256": reproduction.sha((self.state / "source-inventory.json").read_bytes()),
            "verifier_source_sha256": inventory["files"]["resumption/generator_audit.py"]}
        self.originals = [{"trace_id": "synthetic-trace", "root_id": "synthetic-root", "model": "fixture",
                           "domain": "logic", "difficulty": "hard", "split": "test",
                           "text": " ".join("word" + str(index) for index in range(128)),
                           "correct": True, "status": "completed", "phase": "collection"}]
        self.write("results.json", {"phase": "collection", "records": self.originals})
        chunks = reproduction.expected_chunks(self.originals[0]["text"])
        identities = [["synthetic-trace", chunk["start"], chunk["end"]] for chunk in chunks]
        self.call_id = reproduction.sha(reproduction.encoded(
            {"kind": "embedding", "identity": identities,
             "protocol": self.bindings["protocol_sha256"], "model": self.model}))
        self.prefix = "calls/" + self.call_id + "/"
        self.request = {"model": self.model, "input": [chunk["text"] for chunk in chunks]}
        self.write(self.prefix + "request.json", self.request)
        self.response = {"http_status": 200, "json": {"model": self.model, "provider": "synthetic-provider",
                         "data": [{"index": index, "embedding": [float(index + 1)] + [0.0] * 1023}
                                  for index in range(len(chunks))]}}
        self.write(self.prefix + "response.json", self.response)
        self.reservation = {**self.bindings, "call_id": self.call_id, "kind": "embedding",
                            "identity": identities, "model": self.model,
                            "request_sha256": reproduction.sha(reproduction.encoded(self.request)),
                            "reservation_id": "synthetic-reservation"}
        self.write(self.prefix + "reservation.json", self.reservation)
        self.result = {**self.reservation, "http_status": 200,
                       "response_sha256": reproduction.sha(reproduction.encoded(self.response)),
                       "response": self.response}
        self.write(self.prefix + "result.json", self.result)
        self.write("ledger.json", [{"id": "synthetic-reservation", "state": "charged",
                                   "charged_or_reserved_rub": "1"}])
        self.route = {"model": self.model, "provider": "synthetic-provider", "dimension": 1024,
                      "first_response_sha256": self.result["response_sha256"],
                      "provider_identity_verified": True, "revision": "not_reported_not_inferred"}
        self.write("baai_bge-m3-embedding-route.json", self.route)
        records = copy.deepcopy(self.originals)
        records[0]["embeddings"] = {self.model: []}
        for chunk, item in zip(chunks, self.response["json"]["data"]):
            records[0]["embeddings"][self.model].append({
                **chunk, "vector": item["embedding"], "model_id": self.model,
                "identity_verified": True, "provider_identity_verified": True, "provider": "synthetic-provider",
                "input_sha256": reproduction.sha(chunk["text"].encode()),
                "request_sha256": self.reservation["request_sha256"],
                "response_sha256": self.result["response_sha256"]})
        self.aggregate = {"records": records, "embedding_model": self.model, "word_chunk_size": 16,
                          "max_observed_words": 512, "protocol_sha256": self.bindings["protocol_sha256"],
                          "embedding_route": self.route, "scientific_validity": "not_assessed"}
        self.write("baai_bge-m3-embedded.json", self.aggregate)
        markers = exporter.derived_embedding_registry(self.state, ())
        self.marker = next(row for row in markers["files"] if row["file_present"])

    def write(self, relative, value):
        path = self.state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(reproduction.encoded(value))

    def rebuild(self):
        return reproduction.reconstruct_embedding(self.state, self.marker, self.originals, self.bindings)

    def update_response(self):
        self.write(self.prefix + "response.json", self.response)
        self.result["response"] = self.response
        self.result["response_sha256"] = reproduction.sha(reproduction.encoded(self.response))
        self.write(self.prefix + "result.json", self.result)

    def authorize_casefold_fixture(self):
        self.response["json"]["model"] = "BAAI/bge-m3"
        self.update_response()
        self.route["first_response_sha256"] = self.result["response_sha256"]
        self.write("baai_bge-m3-embedding-route.json", self.route)
        project = self.root / "project"
        collector_path = project / reproduction.COMPAT_COLLECTOR
        collector_path.parent.mkdir(parents=True)
        collector_path.write_bytes(b"# Explicit synthetic compatibility collector fixture; no API code.\n")
        collector_sha = reproduction.sha(collector_path.read_bytes())
        amendment = {"schema_version": 1, "amendment_id": "synthetic-ascii-casefold-only",
                     "base_protocol_sha256": self.bindings["protocol_sha256"], "script_sha256": collector_sha,
                     "model_identity_rule": reproduction.COMPAT_RULE, "models": [self.model],
                     "expected_routes": {self.model: {"provider": "synthetic-provider", "dimension": 1024}},
                     "created_utc": "2026-11-08T10:00:00+00:00"}
        amendment_path = project / reproduction.COMPAT_AMENDMENT
        amendment_path.parent.mkdir(parents=True)
        amendment_path.write_bytes(reproduction.encoded(amendment))
        amendment_sha = reproduction.sha(amendment_path.read_bytes())
        directory = self.state / reproduction.COMPAT_STATE
        directory.mkdir(parents=True)
        (directory / "amendment.json").write_bytes(amendment_path.read_bytes())
        (directory / "collector.py").write_bytes(collector_path.read_bytes())
        binding = {"schema_version": 1, "amendment_id": amendment["amendment_id"],
                   "amendment_sha256": amendment_sha, "collector_sha256": collector_sha,
                   "base_protocol_sha256": self.bindings["protocol_sha256"],
                   "source_inventory_sha256": self.bindings["source_inventory_sha256"],
                   "corpus_sha256": self.bindings["corpus_sha256"],
                   "results_sha256": reproduction.sha((self.state / "results.json").read_bytes()),
                   "results_document_sha256": reproduction.sha(reproduction.encoded(
                       json.loads((self.state / "results.json").read_bytes()))),
                   "model_identity_rule": reproduction.COMPAT_RULE, "models": [self.model],
                   "expected_routes": amendment["expected_routes"],
                   "amendment_path": reproduction.COMPAT_AMENDMENT,
                   "collector_path": reproduction.COMPAT_COLLECTOR, "scientific_validity": "not_assessed"}
        (directory / "binding.json").write_bytes(reproduction.encoded(binding))
        self.route.update(identity_rule=reproduction.COMPAT_RULE,
                          amendment_sha256=amendment_sha, collector_sha256=collector_sha)
        self.write("baai_bge-m3-embedding-route.json", self.route)
        self.write(self.prefix + "embedding-compatibility.json", {
            "schema_version": 1, "call_id": self.call_id, "requested_model": self.model,
            "returned_model_id": "BAAI/bge-m3", "provider": "synthetic-provider", "dimension": 1024,
            "identity_rule": reproduction.COMPAT_RULE, "request_sha256": self.reservation["request_sha256"],
            "response_sha256": self.result["response_sha256"], "amendment_sha256": amendment_sha,
            "collector_sha256": collector_sha, "cached_without_resend": True,
            "scientific_validity": "not_assessed"})
        self.aggregate.update(identity_rule=reproduction.COMPAT_RULE,
            embedding_route=self.route,
            execution_compatibility={"amendment_path": reproduction.COMPAT_AMENDMENT,
                "amendment_sha256": amendment_sha, "collector_path": reproduction.COMPAT_COLLECTOR,
                "collector_sha256": collector_sha, "model_identity_rule": reproduction.COMPAT_RULE,
                "canonical_requested_model": self.model, "returned_model_identity_preserved": True,
                "base_protocol_sha256": self.bindings["protocol_sha256"],
                "state_binding_path": reproduction.COMPAT_STATE + "/binding.json"})
        for segment in self.aggregate["records"][0]["embeddings"][self.model]:
            segment.update(identity_rule=reproduction.COMPAT_RULE,
                           returned_model_id=self.response["json"]["model"],
                           response_sha256=self.result["response_sha256"])
        self.write("baai_bge-m3-embedded.json", self.aggregate)
        markers = exporter.derived_embedding_registry(self.state, ())
        self.marker = next(row for row in markers["files"] if row["file_present"])

    def authorize_pinned_fixture(self, new_request=False):
        if new_request:
            self.response["json"]["model"] = "parasail-bge-m3"
            self.update_response()
        project = self.root / "project"
        script = project / reproduction.PINNED_COLLECTOR
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(b"# Synthetic separately pinned provider collector, never executed.\n")
        script_sha = reproduction.sha(script.read_bytes())
        amendment = {"schema_version": 1, "amendment_id": "synthetic-pinned-provider-v1",
            "created_utc": "2026-11-08T11:00:00+00:00", "base_protocol_sha256": self.bindings["protocol_sha256"],
            "script_sha256": script_sha, "model_identity_rule": reproduction.COMPAT_RULE,
            "models": [self.model], "expected_routes": {self.model: {"provider": "synthetic-provider", "dimension": 1024}},
            "parent_call_ids": [self.call_id], "allowed_replacement_call_ids": [self.call_id] if new_request else []}
        amendment_path = project / reproduction.PINNED_AMENDMENT
        amendment_path.parent.mkdir(parents=True, exist_ok=True)
        amendment_path.write_bytes(reproduction.encoded(amendment))
        condition = reproduction.sha(amendment_path.read_bytes())
        directory_name = "embedding-conditions/" + condition
        directory = self.state / directory_name
        directory.mkdir(parents=True)
        (directory / "amendment.json").write_bytes(amendment_path.read_bytes())
        (directory / "collector.py").write_bytes(script.read_bytes())
        binding = {"schema_version": 1, "condition_sha256": condition, "amendment_id": amendment["amendment_id"],
            "amendment_sha256": condition, "collector_sha256": script_sha,
            "base_protocol_sha256": self.bindings["protocol_sha256"],
            "source_inventory_sha256": self.bindings["source_inventory_sha256"],
            "corpus_sha256": self.bindings["corpus_sha256"],
            "results_sha256": reproduction.sha((self.state / "results.json").read_bytes()),
            "results_document_sha256": reproduction.sha(reproduction.encoded(
                json.loads((self.state / "results.json").read_bytes()))),
            "model_identity_rule": reproduction.COMPAT_RULE, "models": [self.model],
            "expected_routes": amendment["expected_routes"], "parent_call_ids": [self.call_id],
            "allowed_replacement_call_ids": amendment["allowed_replacement_call_ids"],
            "amendment_path": reproduction.PINNED_AMENDMENT, "collector_path": reproduction.PINNED_COLLECTOR,
            "scientific_validity": "not_assessed"}
        (directory / "binding.json").write_bytes(reproduction.encoded(binding))
        mapping = {"schema_version": 1, "condition_sha256": condition,
                   "trace_mapping": {condition + ":" + row["trace_id"]: row["trace_id"]
                                     for row in self.originals if row["status"] == "completed"}}
        (directory / "mapping.json").write_bytes(reproduction.encoded(mapping))
        selected_call, selected_request, selected_response = self.call_id, self.request, self.response
        selected_identity = self.reservation["identity"]
        if new_request:
            selected_identity = [[condition + ":" + trace, start, end] for trace, start, end in selected_identity]
            selected_call = reproduction.sha(reproduction.encoded({"kind": "embedding", "identity": selected_identity,
                         "protocol": self.bindings["protocol_sha256"], "model": self.model}))
            selected_request = {**self.request, "provider": {"order": ["synthetic-provider"], "allow_fallbacks": False}}
            selected_response = copy.deepcopy(self.response)
            selected_response["json"]["model"] = self.model
            reservation = {**self.bindings, "call_id": selected_call, "kind": "embedding", "identity": selected_identity,
                "model": self.model, "request_sha256": reproduction.sha(reproduction.encoded(selected_request)),
                "reservation_id": "synthetic-pinned-reservation"}
            result = {**reservation, "http_status": 200, "response": selected_response,
                      "response_sha256": reproduction.sha(reproduction.encoded(selected_response))}
            for name, value in (("reservation", reservation), ("request", selected_request),
                                ("response", selected_response), ("result", result)):
                self.write("calls/" + selected_call + "/" + name + ".json", value)
            self.write("ledger.json", [{"id": name, "state": "charged", "charged_or_reserved_rub": "1"}
                                       for name in ("synthetic-reservation", "synthetic-pinned-reservation")])
            intent = {"schema_version": 1, "condition_sha256": condition, "model": self.model,
                "original_identity": self.reservation["identity"], "paid_identity": selected_identity,
                "request_body_sha256": reproduction.sha(reproduction.encoded(selected_request)), "amendment_sha256": condition}
            self.write(directory_name + "/intents/" + selected_call + ".json", intent)
        request_sha = reproduction.sha(reproduction.encoded(selected_request))
        response_sha = reproduction.sha(reproduction.encoded(selected_response))
        route = {"model": self.model, "provider": "synthetic-provider", "dimension": 1024,
            "first_response_sha256": response_sha, "provider_identity_verified": True,
            "revision": "not_reported_not_inferred", "identity_rule": reproduction.COMPAT_RULE,
            "condition_sha256": condition, "amendment_sha256": condition, "collector_sha256": script_sha}
        self.write(directory_name + "/baai_bge-m3-embedding-route.json", route)
        receipt_name = "calls/" + selected_call + "/embedding-pinned-" + condition + ".json"
        input_mapping = []
        records = copy.deepcopy(self.aggregate["records"])
        for index, segment in enumerate(records[0]["embeddings"][self.model]):
            paid_trace = selected_identity[index][0]
            segment.update(model_id=self.model, returned_model_id=selected_response["json"]["model"],
                identity_rule=reproduction.COMPAT_RULE, measurement_condition_sha256=condition,
                embedding_call_id=selected_call, paid_trace_id=paid_trace, pinned_receipt_path=receipt_name,
                reused_known_valid=not new_request, parent_rejected_call_ids=amendment["allowed_replacement_call_ids"],
                request_route_pinned=new_request,
                request_sha256=request_sha, response_sha256=response_sha)
            input_mapping.append({"response_index": index, "original_trace_id": "synthetic-trace",
                "paid_trace_id": paid_trace, "start": segment["start"], "end": segment["end"],
                "input_sha256": segment["input_sha256"]})
        receipt = {"schema_version": 1, "condition_sha256": condition, "call_id": selected_call,
            "request_sha256": request_sha, "response_sha256": response_sha, "requested_model": self.model,
            "returned_model_id": selected_response["json"]["model"], "provider": "synthetic-provider", "dimension": 1024,
            "identity_rule": reproduction.COMPAT_RULE, "amendment_sha256": condition, "collector_sha256": script_sha,
            "accepted_source": "condition_request" if new_request else "reused_known_valid_unpinned",
            "input_mapping": input_mapping, "parent_rejected_call_ids": amendment["allowed_replacement_call_ids"],
            "body_provider_pinned": new_request, "scientific_validity": "not_assessed"}
        self.write(receipt_name, receipt)
        execution = {key: binding[key] for key in ("amendment_path", "amendment_sha256", "collector_path", "collector_sha256",
            "model_identity_rule", "base_protocol_sha256", "condition_sha256", "parent_call_ids", "allowed_replacement_call_ids")}
        execution.update(canonical_requested_model=self.model, returned_model_identity_preserved=True,
            provider="synthetic-provider", dimension=1024, state_binding_path=directory_name + "/binding.json",
            condition_mapping_path=directory_name + "/mapping.json")
        self.aggregate.update(records=records, embedding_route=route, identity_rule=reproduction.COMPAT_RULE,
            measurement_condition_sha256=condition, execution_pinned_condition=execution,
            reused_known_chunks=0 if new_request else len(input_mapping),
            new_condition_chunks=len(input_mapping) if new_request else 0)
        self.write("baai_bge-m3-embedded.json", self.aggregate)
        self.marker = next(row for row in exporter.derived_embedding_registry(self.state, ())["files"] if row["file_present"])
        return {"condition": condition, "directory_name": directory_name, "selected_call": selected_call,
                "receipt_name": receipt_name, "execution": execution}

    def test_exact_aggregate_reconstruction_and_frozen_source_inventory(self):
        records, audit = self.rebuild()
        self.assertEqual(records, self.aggregate["records"])
        self.assertEqual(audit["status"], "reconstructed_exact")
        self.assertEqual(audit["original_sha256"], reproduction.sha(reproduction.encoded(self.aggregate)))
        self.assertEqual(audit["validated_modes"][self.model]["chunks"], 8)
        reproduction.verify_frozen_sources(self.state)
        (self.state / "source/resumption/analysis.py").write_bytes(b"tampered")
        with self.assertRaisesRegex(reproduction.ReproductionError, "Frozen source differs"):
            reproduction.verify_frozen_sources(self.state)

    def test_case_only_response_identity_requires_bound_amendment_and_collector(self):
        self.response["json"]["model"] = "BAAI/bge-m3"
        self.update_response()
        with self.assertRaisesRegex(reproduction.ReproductionError, "HTTP/API/model"):
            self.rebuild()
        self.authorize_casefold_fixture()
        records, audit = self.rebuild()
        self.assertEqual(audit["execution_compatibility"]["model_identity_rule"], "ascii_casefold_only")
        self.assertEqual(records[0]["embeddings"][self.model][0]["model_id"], self.model)
        self.assertEqual(records[0]["embeddings"][self.model][0]["returned_model_id"], "BAAI/bge-m3")
        self.assertEqual(audit["validated_modes"][self.model]["returned_model_ids"], ["BAAI/bge-m3"])

    def test_casefold_amendment_never_permits_an_alias_or_whitespace_variant(self):
        self.authorize_casefold_fixture()
        for returned in ("parasail-bge-m3", "baai/bge-m3 ", "different/bge-m3"):
            with self.subTest(returned=returned):
                self.response["json"]["model"] = returned
                self.update_response()
                with self.assertRaisesRegex(reproduction.ReproductionError, "HTTP/API/model"):
                    self.rebuild()

    def test_casefold_amendment_script_and_raw_returned_identity_cannot_be_tampered(self):
        self.authorize_casefold_fixture()
        amendment_path = self.root / "project" / reproduction.COMPAT_AMENDMENT
        original = amendment_path.read_bytes()
        amendment_path.write_bytes(original + b"\n")
        with self.assertRaisesRegex(reproduction.ReproductionError, "amendment/collector SHA-256"):
            self.rebuild()
        amendment_path.write_bytes(original)
        marker = copy.deepcopy(self.marker)
        marker["records"][0]["record"]["embeddings"][self.model][0].pop("returned_model_id")
        with self.assertRaisesRegex(reproduction.ReproductionError, "preserve the exact returned"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)
        (self.root / "project" / reproduction.COMPAT_COLLECTOR).write_bytes(b"changed synthetic script")
        with self.assertRaisesRegex(reproduction.ReproductionError, "amendment/collector SHA-256"):
            self.rebuild()

    def test_authorized_casefold_binding_survives_portable_export_and_reanalysis(self):
        self.authorize_casefold_fixture()
        exported = exporter.export_bundle(self.state, self.root / "case-bundle", project=self.root / "project",
                                          include_project=True, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "case-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "reconstructed_exact")
        execution = report["embedding_modes"][self.model]["execution_compatibility"]
        self.assertEqual(execution["canonical_requested_model"], self.model)
        self.assertEqual(execution["model_identity_rule"], "ascii_casefold_only")

    def test_original_request_sha_and_exact_chunk_text_are_required(self):
        self.request["input"][0] = "changed synthetic text"
        self.write(self.prefix + "request.json", self.request)
        with self.assertRaisesRegex(reproduction.ReproductionError, "request SHA-256"):
            self.rebuild()
        self.reservation["request_sha256"] = reproduction.sha(reproduction.encoded(self.request))
        self.write(self.prefix + "reservation.json", self.reservation)
        self.result["request_sha256"] = self.reservation["request_sha256"]
        self.write(self.prefix + "result.json", self.result)
        with self.assertRaisesRegex(reproduction.ReproductionError, "changed text"):
            self.rebuild()

    def test_pinned_condition_reuses_known_valid_parent_without_replacing_its_raw_call(self):
        fixture = self.authorize_pinned_fixture()
        before = (self.state / self.prefix / "request.json").read_bytes()
        records, audit = self.rebuild()
        self.assertEqual(audit["execution_pinned_condition"]["condition_sha256"], fixture["condition"])
        self.assertEqual(audit["validated_modes"][self.model]["reused_known_chunks"], 8)
        self.assertEqual((self.state / self.prefix / "request.json").read_bytes(), before)
        self.assertTrue(records[0]["embeddings"][self.model][0]["reused_known_valid"])

    def test_pinned_condition_binds_new_provider_request_to_known_rejected_parent(self):
        fixture = self.authorize_pinned_fixture(new_request=True)
        records, audit = self.rebuild()
        self.assertEqual(audit["validated_modes"][self.model]["new_condition_chunks"], 8)
        segment = records[0]["embeddings"][self.model][0]
        self.assertEqual(segment["embedding_call_id"], fixture["selected_call"])
        self.assertEqual(segment["parent_rejected_call_ids"], [self.call_id])
        self.assertEqual(json.loads((self.state / self.prefix / "response.json").read_bytes())["json"]["model"], "parasail-bge-m3")

    def test_pinned_condition_cannot_hide_an_unknown_underlying_original_chunk(self):
        self.authorize_pinned_fixture(new_request=True)
        identities = self.reservation["identity"][:1]
        call_id = reproduction.sha(reproduction.encoded({"kind": "embedding", "identity": identities,
            "protocol": self.bindings["protocol_sha256"], "model": self.model}))
        request = {"model": self.model, "input": self.request["input"][:1]}
        self.write("calls/" + call_id + "/request.json", request)
        self.write("calls/" + call_id + "/reservation.json", {**self.bindings, "kind": "embedding", "model": self.model,
            "identity": identities, "call_id": call_id, "reservation_id": "unknown-synthetic",
            "request_sha256": reproduction.sha(reproduction.encoded(request))})
        with self.assertRaisesRegex(reproduction.ReproductionError, "unknown underlying chunk"):
            self.rebuild()

    def test_pinned_condition_rejects_fallback_and_missing_prospective_intent(self):
        fixture = self.authorize_pinned_fixture(new_request=True)
        intent = self.state / fixture["directory_name"] / "intents" / (fixture["selected_call"] + ".json")
        original_intent = intent.read_bytes()
        intent.unlink()
        with self.assertRaisesRegex(reproduction.ReproductionError, "prospective original/paid intent"):
            self.rebuild()
        intent.write_bytes(original_intent)
        directory = self.state / "calls" / fixture["selected_call"]
        request = json.loads((directory / "request.json").read_bytes())
        request["provider"]["allow_fallbacks"] = True
        (directory / "request.json").write_bytes(reproduction.encoded(request))
        digest = reproduction.sha(reproduction.encoded(request))
        for name in ("reservation", "result"):
            value = json.loads((directory / (name + ".json")).read_bytes())
            value["request_sha256"] = digest
            (directory / (name + ".json")).write_bytes(reproduction.encoded(value))
        with self.assertRaisesRegex(reproduction.ReproductionError, "pin the exact provider"):
            self.rebuild()

    def test_pinned_condition_mapping_and_per_chunk_parent_links_are_not_optional(self):
        fixture = self.authorize_pinned_fixture(new_request=True)
        marker = copy.deepcopy(self.marker)
        marker["records"][0]["record"]["embeddings"][self.model][0]["parent_rejected_call_ids"] = []
        with self.assertRaisesRegex(reproduction.ReproductionError, "segment provenance"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)
        mapping_path = self.state / fixture["directory_name"] / "mapping.json"
        mapping = json.loads(mapping_path.read_bytes())
        mapping["trace_mapping"] = {}
        mapping_path.write_bytes(reproduction.encoded(mapping))
        with self.assertRaisesRegex(reproduction.ReproductionError, "changes the original"):
            self.rebuild()

    def test_pinned_condition_portable_export_reconstructs_new_and_reused_evidence(self):
        self.authorize_pinned_fixture(new_request=True)
        exported = exporter.export_bundle(self.state, self.root / "pinned-bundle", project=self.root / "project",
                                          include_project=True, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "pinned-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "reconstructed_exact")
        self.assertEqual(report["embedding_modes"][self.model]["validated_modes"][self.model]["new_condition_chunks"], 8)

    def test_invalid_batch_model_provider_dimension_and_vectors_fail_closed(self):
        for kind in ("model", "provider", "dimension", "bool_vector"):
            with self.subTest(kind=kind):
                saved = copy.deepcopy(self.response)
                if kind in ("model", "provider"):
                    self.response["json"][kind] = "different-synthetic-identity"
                elif kind == "dimension":
                    for item in self.response["json"]["data"]:
                        item["embedding"] = [1.0]
                else:
                    self.response["json"]["data"][0]["embedding"][0] = True
                self.update_response()
                with self.assertRaises(reproduction.ReproductionError):
                    self.rebuild()
                self.response = saved
                self.update_response()

    def test_missing_finalization_and_absent_completion_marker_are_not_recovered_as_success(self):
        (self.state / self.prefix / "result.json").unlink()
        with self.assertRaisesRegex(reproduction.ReproductionError, "no finalized"):
            self.rebuild()
        marker = copy.deepcopy(self.marker)
        marker["file_present"] = False
        with self.assertRaisesRegex(reproduction.ReproductionError, "absent or unfinished"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)

    def test_vector_slot_tampering_and_original_aggregate_digest_are_rejected(self):
        marker = copy.deepcopy(self.marker)
        marker["records"][0]["vector_slots"][0]["vector_sha256"] = "f" * 64
        with self.assertRaisesRegex(reproduction.ReproductionError, "vector/hash/metadata"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)
        marker = copy.deepcopy(self.marker)
        marker["original_sha256"] = "f" * 64
        with self.assertRaisesRegex(reproduction.ReproductionError, "original SHA-256/size"):
            reproduction.reconstruct_embedding(self.state, marker, self.originals, self.bindings)

    def test_response_original_bytes_are_bound_even_when_json_content_is_unchanged(self):
        response_path = self.state / self.prefix / "response.json"
        response_path.write_bytes(response_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(reproduction.ReproductionError, "response/result binding"):
            self.rebuild()

    def test_exported_bundle_reanalysis_is_offline_and_retains_ledger(self):
        exported = exporter.export_bundle(self.state, self.root / "bundle", project=self.root,
                                          include_project=False, secrets=())
        with patch.object(socket, "create_connection", side_effect=AssertionError("No network in reproduction")) as network:
            result = reproduction.reproduce(exported["manifest"], self.root / "reanalysis", bootstrap_samples=0)
            network.assert_not_called()
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["network_or_model_calls"], 0)
        self.assertEqual(report["embedding_modes"][self.model]["status"], "reconstructed_exact")
        self.assertEqual(report["embedding_modes"]["qwen/qwen3-embedding-8b"]["status"], "unavailable")
        self.assertEqual(len(report["analyses"]), 2)
        self.assertEqual(report["ledger_sha256_unchanged"], reproduction.sha((self.state / "ledger.json").read_bytes()))
        with self.assertRaisesRegex(reproduction.ReproductionError, "already exists"):
            reproduction.reproduce(exported["manifest"], self.root / "reanalysis")

    def test_valid_raw_batches_without_completed_aggregate_are_not_analyzed_semantically(self):
        (self.state / "baai_bge-m3-embedded.json").unlink()
        exported = exporter.export_bundle(self.state, self.root / "unfinished-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "unfinished-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "unavailable")
        self.assertEqual(len(report["analyses"]), 1)
        self.assertEqual(report["matched_embedding_status"], "unavailable_both_complete_modes_required")

    def test_invalid_batch_excludes_the_whole_embedding_mode_but_retains_lexical_analysis(self):
        self.response["json"]["data"][0]["embedding"][0] = True
        self.update_response()
        exported = exporter.export_bundle(self.state, self.root / "invalid-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "invalid-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(report["embedding_modes"][self.model]["status"], "unavailable_invalid_whole_mode")
        self.assertEqual(len(report["analyses"]), 1)
        self.assertEqual(report["analyses"][0]["representation"], "lexical")

    def test_two_exact_completed_modes_enable_both_supplementary_matched_analyses(self):
        second_model = "qwen/qwen3-embedding-8b"
        request = copy.deepcopy(self.request)
        request["model"] = second_model
        identity = self.reservation["identity"]
        call_id = reproduction.sha(reproduction.encoded(
            {"kind": "embedding", "identity": identity,
             "protocol": self.bindings["protocol_sha256"], "model": second_model}))
        prefix = "calls/" + call_id + "/"
        reservation = {**self.bindings, "call_id": call_id, "kind": "embedding", "identity": identity,
                       "model": second_model, "request_sha256": reproduction.sha(reproduction.encoded(request)),
                       "reservation_id": "synthetic-second-reservation"}
        response = copy.deepcopy(self.response)
        response["json"]["model"] = second_model
        for item in response["json"]["data"]:
            item["embedding"] = item["embedding"][:8]
        response_sha = reproduction.sha(reproduction.encoded(response))
        result = {**reservation, "http_status": 200, "response_sha256": response_sha, "response": response}
        for name, value in (("request", request), ("response", response),
                            ("reservation", reservation), ("result", result)):
            self.write(prefix + name + ".json", value)
        route = {**self.route, "model": second_model, "dimension": 8, "first_response_sha256": response_sha}
        self.write("qwen_qwen3-embedding-8b-embedding-route.json", route)
        aggregate = copy.deepcopy(self.aggregate)
        aggregate.update(embedding_model=second_model, embedding_route=route)
        segments = aggregate["records"][0]["embeddings"].pop(self.model)
        aggregate["records"][0]["embeddings"][second_model] = segments
        for segment, item in zip(segments, response["json"]["data"]):
            segment.update(vector=item["embedding"], model_id=second_model,
                           request_sha256=reservation["request_sha256"], response_sha256=response_sha)
        self.write("qwen_qwen3-embedding-8b-embedded.json", aggregate)
        self.write("ledger.json", [{"id": name, "state": "charged", "charged_or_reserved_rub": "1"}
                                   for name in ("synthetic-reservation", "synthetic-second-reservation")])
        exported = exporter.export_bundle(self.state, self.root / "two-mode-bundle", project=self.root,
                                          include_project=False, secrets=())
        result = reproduction.reproduce(exported["manifest"], self.root / "two-mode-reanalysis", bootstrap_samples=0)
        report = json.loads(Path(result["report"]).read_bytes())
        self.assertEqual(len(report["analyses"]), 5)
        self.assertEqual(report["matched_embedding_status"], "supplementary_matched_analyses_completed")
        self.assertEqual(sum(row["analysis_population"] == "supplementary_matched_embedding_prefixes"
                             for row in report["analyses"]), 2)


if __name__ == "__main__":
    unittest.main()
