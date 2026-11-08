"""Export, verify and restore a bounded, allowlisted local evidence snapshot.

No network access. Export only after collection has stopped: a changing source
snapshot is rejected. Scientific validity is never inferred from this archive.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from urllib.parse import quote
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
CHUNK_BYTES = 8 * 1024 * 1024
SHARD_BYTES = 32 * 1024 * 1024
FORMAT = "reasoning-universalis-local-evidence-v1"
STATE_FILES = {
    "ledger.json", "source-inventory.json", "protocol.json", "corpus.json",
    "dispatch-window.json", "admissions.json", "admission-results.json",
    "results.json", "pre-dispatch-plan.json", "catalog-summary.json",
    "embedding-attempted-chunks.json",
}
CALL_FILES = {"request.json", "response.json", "reservation.json", "trace.json", "result.json",
              "embedding-compatibility.json"}
CODE_DIRECTORIES = {"resumption", "stage0", "stage2", "stage3", "measurement",
                    "reasoning_universalis_v1", "resumption_evidence_v1", "scripts"}
DERIVED_EMBEDDINGS = ("baai_bge-m3-embedded.json", "qwen_qwen3-embedding-8b-embedded.json")
OUTPUT_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv", ".md", ".txt", ".pdf",
                   ".png", ".svg", ".tex", ".bib", ".gz", ".html"}
HEX = re.compile(r"^[0-9a-f]{64}$")


class ExportError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    # Identical JSON encoding to Runner.save, required for exact result recovery.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8")


def checked_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ExportError("Unsafe bundle path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in (".", "..") for part in path.parts):
        raise ExportError("Unsafe bundle path")
    if any(":" in part for part in path.parts):
        raise ExportError("Unsafe bundle path")
    return path


def regular(path, root):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ExportError("Evidence source is not a regular file inside its declared root")
    # Refuse a symlinked ancestor as well as a final symlink.
    for ancestor in path.parents:
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ExportError("Evidence source has a symlinked ancestor")


def credentials(env_file=None):
    """Load only for in-memory scanning; never serialize configuration values."""
    values = []
    if env_file is not None and Path(env_file).exists():
        sys.path.insert(0, str(PROJECT))
        from stage0.config import parse_env
        local = parse_env(env_file)
        if local.get("ROUTERAI_API_KEY"):
            values.append(local["ROUTERAI_API_KEY"])
    if os.environ.get("ROUTERAI_API_KEY"):
        values.append(os.environ["ROUTERAI_API_KEY"])
    return tuple(set(values))


def scan(data, secrets):
    for secret in secrets:
        if not secret:
            continue
        variants = (secret, json.dumps(secret)[1:-1], quote(secret, safe=""))
        if any(value.encode("utf-8") in data for value in variants):
            raise ExportError("Credential detected; export refused without exposing its value")


def check_json_privacy(value, secrets, http_wrapper=False):
    """Raw HTTP headers are outside the public export contract."""
    if not isinstance(value, dict):
        return
    if http_wrapper and "headers" in value:
        raise ExportError("HTTP headers found in evidence; clean explicit source revision required")
    if http_wrapper and isinstance(value.get("body_base64"), str):
        try:
            raw = base64.b64decode(value["body_base64"], validate=True)
        except (ValueError, TypeError):
            raise ExportError("Invalid raw-body base64") from None
        scan(raw, secrets)


def is_canonical(data, value):
    try:
        return data == encoded(value)
    except (TypeError, ValueError):
        return False


def compact_capture(data, value):
    """Omit decoded copies only after proving their exact reconstruction.

    Original HTTP body bytes stay in body_base64; JSON numeric precision and
    Unicode are unchanged. A noncanonical or malformed capture stays verbatim.
    """
    if not isinstance(value, dict) or not is_canonical(data, value):
        return None
    if not isinstance(value.get("body_base64"), str) or not isinstance(value.get("raw_body"), str):
        return None
    try:
        raw = base64.b64decode(value["body_base64"], validate=True)
        text = raw.decode("utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or text != value["raw_body"] or parsed != value.get("json"):
            return None
        reconstructed = dict(value, raw_body=text, json=parsed)
        if not is_canonical(data, reconstructed):
            return None
        context = dict(value)
        del context["raw_body"]
        del context["json"]
        return encoded(context)
    except (ValueError, TypeError):
        return None


def state_allowed(relative):
    parts = PurePosixPath(relative).parts
    if len(parts) == 1:
        return (relative in STATE_FILES or
                bool(re.fullmatch(r"(?:baai_bge-m3|qwen_qwen3-embedding-8b)-embedding-route\.json", relative)))
    if parts[0] == "calls":
        return (len(parts) == 3 and bool(HEX.fullmatch(parts[1])) and
                (parts[2] in CALL_FILES or bool(re.fullmatch(r"embedding-pinned-[0-9a-f]{64}\.json", parts[2]))))
    if parts[0] == "metadata":
        return (len(parts) == 2 or len(parts) == 3 and parts[1] == "history") and parts[-1].endswith(".json")
    if parts[0] == "source":
        # The frozen collector closure is an explicit Python-only source inventory.
        return len(parts) == 3 and parts[1] in ("resumption", "stage0") and parts[-1].endswith(".py")
    if parts[0] == "compatibility":
        return (len(parts) == 3 and parts[1] == "embedding-ascii-casefold-v1" and
                parts[-1] in ("amendment.json", "collector.py", "binding.json"))
    if parts[0] == "embedding-conditions":
        return (len(parts) >= 3 and bool(HEX.fullmatch(parts[1])) and
                (len(parts) == 3 and (parts[-1] in ("amendment.json", "collector.py", "binding.json", "mapping.json") or
                 bool(re.fullmatch(r"(?:baai_bge-m3|qwen_qwen3-embedding-8b)-embedding-route\.json", parts[-1]))) or
                 len(parts) == 4 and parts[2] == "intents" and bool(re.fullmatch(r"[0-9a-f]{64}\.json", parts[-1]))))
    return False


def project_allowed(relative):
    path = PurePosixPath(relative)
    if len(path.parts) == 2 and path.parts[0] in CODE_DIRECTORIES and path.suffix == ".py":
        return True
    if relative in {"LOCAL_RESUME.md", "AGENTS.md", "RESEARCH_SPECIFICATION.md",
                    "requirements-resumption.txt", "requirements-publication.txt",
                    "design/LOCAL_PILOT_2026_11_08.json", "design/LOCAL_EMBEDDING_COMPAT_2026_11_08.json",
                    "design/LOCAL_EMBEDDING_PINNED_2026_11_08.json", "artifacts/local/error-audit.json",
                    "scripts/export_local_evidence.py"}:
        return True
    if path.suffix.lower() not in OUTPUT_SUFFIXES:
        return False
    if relative.startswith("artifacts/resumption-2026-11-08/") or relative.startswith("manuscript/"):
        return True
    if relative.startswith("output/pdf/") and path.suffix.lower() == ".pdf":
        return True
    if relative.startswith("literature/resumption_2026_11_08/") and path.suffix.lower() == ".md":
        return True
    if path.parent.as_posix() == "reports":
        return path.name.startswith("LOCAL_") or path.name in {
            "RESUMPTION_SCOPE_2026_11_08.md", "RESUMPTION_STATISTICAL_AUDIT.md",
            "SEMANTIC_AFTERLIFE_TRANSFER.md", "GENERATOR_AUDIT_2026_11_08.md",
            "EPISTEMEOS_RESUMPTION_AUDIT.md", "MODEL_LICENSES.md"}
    return False


def selected_files(state, project, include_project=True):
    files = {}
    for path in sorted(state.rglob("*")):
        relative = path.relative_to(state).as_posix()
        if path.is_file() and state_allowed(relative):
            regular(path, state)
            files["state/" + relative] = path
    for required in ("ledger.json", "protocol.json", "corpus.json", "source-inventory.json"):
        if "state/" + required not in files:
            raise ExportError("Required state artifact is absent: " + required)
    if include_project:
        candidates = [project / p for p in ("LOCAL_RESUME.md", "AGENTS.md", "RESEARCH_SPECIFICATION.md",
                                           "requirements-resumption.txt", "requirements-publication.txt",
                                           "design/LOCAL_PILOT_2026_11_08.json", "design/LOCAL_EMBEDDING_COMPAT_2026_11_08.json",
                                           "design/LOCAL_EMBEDDING_PINNED_2026_11_08.json", "artifacts/local/error-audit.json",
                                           "scripts/export_local_evidence.py")]
        for directory in ("reports", "manuscript", "artifacts/resumption-2026-11-08", "output/pdf",
                          "literature/resumption_2026_11_08", *sorted(CODE_DIRECTORIES)):
            root = project / directory
            if root.exists():
                candidates.extend(root.rglob("*"))
        for path in sorted(candidates):
            relative = path.relative_to(project).as_posix()
            if path.is_file() and project_allowed(relative):
                regular(path, project)
                files["project/" + relative] = path
    return files


def snapshot(files):
    return {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in files.items()}


class JsonStream:
    """Stdlib streaming reader, bounded by one JSON value such as one record."""
    def __init__(self, source):
        self.source, self.buffer, self.offset, self.eof = source, "", 0, False
        self.decoder = json.JSONDecoder()

    def more(self):
        if self.offset:
            self.buffer = self.buffer[self.offset:]
            self.offset = 0
        block = self.source.read(512 * 1024)
        self.eof = not block
        self.buffer += block

    def peek(self):
        while True:
            while self.offset < len(self.buffer) and self.buffer[self.offset].isspace():
                self.offset += 1
            if self.offset < len(self.buffer):
                return self.buffer[self.offset]
            if self.eof:
                return ""
            self.more()

    def take(self, expected):
        if self.peek() != expected:
            raise ExportError("Malformed derived aggregate JSON")
        self.offset += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.offset)
                if end == len(self.buffer) and not self.eof:
                    self.more()
                    continue
                self.offset = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise ExportError("Malformed derived aggregate JSON") from None
                self.more()


def derived_embedding_registry(state, secrets):
    entries = []
    for filename in DERIVED_EMBEDDINGS:
        path = state / filename
        entry = {"path": "state/" + filename, "file_present": path.is_file()}
        if not entry["file_present"]:
            entry["reason"] = "No completed aggregate file in snapshot; raw batches alone do not establish completion"
            entries.append(entry)
            continue
        regular(path, state)
        digest, size, tail = hashlib.sha256(), 0, b""
        overlap = max((len(s.encode("utf-8")) * 6 + 16 for s in secrets), default=0)
        with path.open("rb") as source:
            for block in iter(lambda: source.read(CHUNK_BYTES), b""):
                digest.update(block)
                size += len(block)
                scan(tail + block, secrets)
                tail = (tail + block)[-overlap:] if overlap else b""
        entry.update(original_sha256=digest.hexdigest(), original_bytes=size, header={}, records=[])
        with path.open("r", encoding="utf-8") as source:
            stream = JsonStream(source)
            stream.take("{")
            seen = set()
            while stream.peek() != "}":
                key = stream.value()
                if not isinstance(key, str) or key in seen:
                    raise ExportError("Duplicate or invalid derived aggregate field")
                seen.add(key)
                stream.take(":")
                if key != "records":
                    entry["header"][key] = stream.value()
                else:
                    stream.take("[")
                    while stream.peek() != "]":
                        record = stream.value()
                        if not isinstance(record, dict):
                            raise ExportError("Derived aggregate record is not an object")
                        slots = []
                        for model, segments in record.get("embeddings", {}).items():
                            if not isinstance(segments, list):
                                raise ExportError("Derived embedding segments are not a list")
                            for index, segment in enumerate(segments):
                                if not isinstance(segment, dict):
                                    raise ExportError("Derived embedding segment is not an object")
                                present = "vector" in segment
                                descriptor = {"model": model, "segment_index": index, "present": present}
                                if present:
                                    vector = segment.pop("vector")
                                    if not isinstance(vector, list):
                                        raise ExportError("Derived embedding vector is not a list")
                                    descriptor.update(dimension=len(vector), vector_sha256=sha(encoded(vector)))
                                slots.append(descriptor)
                        entry["records"].append({"record": record, "vector_slots": slots})
                        if stream.peek() == ",":
                            stream.take(",")
                            if stream.peek() == "]":
                                raise ExportError("Trailing comma in derived aggregate")
                        else:
                            break
                    stream.take("]")
                if stream.peek() == ",":
                    stream.take(",")
                    if stream.peek() == "}":
                        raise ExportError("Trailing comma in derived aggregate")
                else:
                    break
            stream.take("}")
            if stream.peek() or "records" not in seen:
                raise ExportError("Incomplete derived aggregate JSON")
        entry["record_order"] = [row["record"].get("trace_id") for row in entry["records"]]
        entry["restore"] = "Restore every declared vector slot from exact raw call identity; Runner.save JSON; require original SHA-256"
        entries.append(entry)
    return {"schema_version": 1, "purpose": "completion evidence for omitted derived embedding aggregates",
            "vector_hash_encoding": "UTF-8 sorted indent=2 JSON, ensure_ascii=False, allow_nan=False",
            "files": entries}


def attempt_registry(files):
    ledger = json.loads(files["state/ledger.json"].read_bytes())
    ledger_by_id = {row["id"]: row for row in ledger}
    call_ids = sorted({PurePosixPath(name).parts[2] for name in files if name.startswith("state/calls/")})
    rows = []
    for call_id in call_ids:
        prefix = "state/calls/" + call_id + "/"
        reservation_path = files.get(prefix + "reservation.json")
        context = json.loads(reservation_path.read_bytes()) if reservation_path else {}
        commitment = ledger_by_id.get(context.get("reservation_id"))
        row = {"call_id": call_id, "kind": context.get("kind"), "model": context.get("model"),
               "identity": context.get("identity"), "reservation_id": context.get("reservation_id"),
               "ledger_state": commitment.get("state") if commitment else None,
               "charged_or_reserved_rub": commitment.get("charged_or_reserved_rub") if commitment else None,
               "files": [name for name in sorted(files) if name.startswith(prefix)],
               "response_retained": prefix + "response.json" in files,
               "result_finalized": prefix + "result.json" in files,
               "trace_retained": prefix + "trace.json" in files}
        rows.append(row)
    return {"schema_version": 1, "purpose": "all_allowlisted_attempt_directories_in_this_snapshot",
            "scientific_validity": "not_assessed", "attempts": rows,
            "counts": dict(Counter(row["ledger_state"] or "unbound" for row in rows)),
            "ledger_rows_without_matching_attempt_directory": len(ledger) - len({
                row["reservation_id"] for row in rows if row["reservation_id"] in ledger_by_id}),
            "unmatched_ledger_rule": "Retained without inferring history or releasing a commitment",
            "missing_result_rule": "retained as not finalized; never authorization to resend"}


class Shards:
    def __init__(self, directory, chunk_bytes=CHUNK_BYTES, shard_bytes=SHARD_BYTES):
        if not 0 < chunk_bytes <= CHUNK_BYTES or not chunk_bytes <= shard_bytes <= SHARD_BYTES:
            raise ExportError("Chunk/shard sizes exceed the public limits")
        self.directory = directory
        self.chunk_bytes, self.shard_bytes = chunk_bytes, shard_bytes
        self.chunks, self.shards = {}, []
        self.archive, self.current, self.current_bytes = None, None, 0

    def _close(self):
        if self.archive is not None:
            self.archive.close()
            data = (self.directory / self.current).read_bytes()
            self.shards.append({"path": self.current, "sha256": sha(data), "bytes": len(data),
                                "uncompressed_bytes": self.current_bytes})
            self.archive = None

    def add(self, data):
        identities = []
        for offset in range(0, len(data), self.chunk_bytes):
            part = data[offset:offset + self.chunk_bytes]
            digest = sha(part)
            identities.append(digest)
            if digest in self.chunks:
                continue
            if self.archive is None or self.current_bytes + len(part) > self.shard_bytes:
                self._close()
                self.current = "shard-" + str(len(self.shards) + 1).zfill(4) + ".zip"
                self.archive = zipfile.ZipFile(self.directory / self.current, "x", zipfile.ZIP_DEFLATED,
                                              compresslevel=6, allowZip64=False)
                self.current_bytes = 0
            member = "chunks/" + digest
            info = zipfile.ZipInfo(member, date_time=(2026, 11, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            self.archive.writestr(info, part)
            self.current_bytes += len(part)
            self.chunks[digest] = {"shard": self.current, "member": member, "bytes": len(part)}
        return identities

    def finish(self):
        self._close()


def export_bundle(state, output, *, project=PROJECT, secrets=(), include_project=True,
                  chunk_bytes=CHUNK_BYTES, shard_bytes=SHARD_BYTES):
    state, output, project = Path(state).resolve(strict=True), Path(output).absolute(), Path(project).resolve(strict=True)
    if output.exists():
        raise ExportError("Output already exists; choose a new export directory")
    if output.resolve().is_relative_to(state) or state.is_relative_to(output.resolve()):
        raise ExportError("Output and live state must be separate directories")
    files = selected_files(state, project, include_project)
    derived_paths = {"derived/" + name: state / name for name in DERIVED_EMBEDDINGS if (state / name).is_file()}
    before = snapshot({**files, **derived_paths})
    frozen = json.loads(files["state/source-inventory.json"].read_bytes()).get("files", {})
    for relative, digest in frozen.items():
        checked_relative(relative)
        source_name = "state/source/" + relative
        if source_name not in files or sha(files[source_name].read_bytes()) != digest:
            raise ExportError("Frozen source snapshot is absent or differs from its inventory")
        project_name = "project/" + relative
        if project_name in files and sha(files[project_name].read_bytes()) != digest:
            raise ExportError("Current source differs from the exact bound collection snapshot")
    output.mkdir(parents=True)
    writer = Shards(output, chunk_bytes, shard_bytes)
    rows = []
    try:
        registry = encoded(attempt_registry(files))
        generated = {"bundle/attempt-registry.json": registry,
                     "bundle/derived-embedding-files.json": encoded(derived_embedding_registry(state, secrets))}
        sources = list(files.items()) + [(name, None) for name in generated]
        for name, path in sources:
            checked_relative(name)
            data = path.read_bytes() if path is not None else generated[name]
            scan(data, secrets)
            stored = data
            transformation = None
            if name.startswith("state/calls/") and name.endswith(".json"):
                value = json.loads(data)
                if name.endswith("/response.json"):
                    check_json_privacy(value, secrets, http_wrapper=True)
                    compact = compact_capture(data, value)
                    if compact is not None:
                        stored = compact
                        transformation = {"kind": "omit_capture_decoded_copies",
                                          "restore": "decode body_base64 as UTF-8; parse body JSON; add raw_body and json; Runner.save JSON"}
                elif name.endswith("/result.json") and isinstance(value, dict):
                    check_json_privacy(value.get("response"), secrets, http_wrapper=True)
                    response_name = name.rsplit("/", 1)[0] + "/response.json"
                    if "response" in value and response_name in files and is_canonical(data, value):
                        response = json.loads(files[response_name].read_bytes())
                        if value["response"] != response:
                            raise ExportError("Result response differs from the retained response artifact")
                        context = dict(value)
                        del context["response"]
                        stored = encoded(context)
                        transformation = {"kind": "omit_duplicate_result_response",
                                          "response_file": response_name,
                                          "restore": "parse context and response; merge response; UTF-8 sorted indent=2 JSON"}
            elif name.startswith("state/metadata/"):
                check_json_privacy(json.loads(data).get("response"), secrets, http_wrapper=True)
            row = {"path": name, "original_sha256": sha(data), "original_bytes": len(data),
                   "stored_sha256": sha(stored), "stored_bytes": len(stored), "chunks": writer.add(stored)}
            if transformation:
                row["transformation"] = transformation
            rows.append(row)
        writer.finish()
        after_files = selected_files(state, project, include_project)
        after_derived = {"derived/" + name: state / name for name in DERIVED_EMBEDDINGS if (state / name).is_file()}
        if set(after_files) != set(files) or snapshot({**after_files, **after_derived}) != before:
            raise ExportError("Source snapshot changed during export; stop collection and export into a new directory")
        manifest = {"schema_version": 1, "format": FORMAT,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "state_label": state.name, "scientific_validity": "not_assessed",
                    "scope": "allowlisted exact snapshot; omitted private settings, locks and derived embedded aggregates",
                    "chunk_limit_bytes": chunk_bytes, "shard_uncompressed_limit_bytes": shard_bytes,
                    "files": rows, "chunks": writer.chunks, "shards": writer.shards,
                    "secret_scan": "configured credential and common encodings checked in-memory, including raw body base64",
                    "restoration": "verify manifest then --unpack; original bytes checked after reconstruction"}
        manifest_data = encoded(manifest)
        scan(manifest_data, secrets)
        (output / "manifest.json").write_bytes(manifest_data)
        result = verify_bundle(output / "manifest.json")
        result.update({"manifest": str(output / "manifest.json"), "manifest_sha256": sha(manifest_data)})
        return result
    finally:
        writer.finish()


def load_manifest(path):
    path = Path(path).resolve(strict=True)
    if path.is_dir():
        path = path / "manifest.json"
    data = json.loads(path.read_bytes())
    if (data.get("schema_version") != 1 or data.get("format") != FORMAT or
            data.get("scientific_validity") != "not_assessed"):
        raise ExportError("Unknown bundle manifest or scientific status")
    if not 0 < data.get("chunk_limit_bytes", 0) <= CHUNK_BYTES:
        raise ExportError("Invalid chunk limit")
    if not data["chunk_limit_bytes"] <= data.get("shard_uncompressed_limit_bytes", 0) <= SHARD_BYTES:
        raise ExportError("Invalid shard limit")
    names = [row["path"] for row in data["files"]]
    if len(names) != len(set(names)):
        raise ExportError("Duplicate restored path")
    for name in names:
        checked_relative(name)
        if not name.startswith(("state/", "project/", "bundle/")):
            raise ExportError("Unrecognized restored path prefix")
    return path, data


def verify_bundle(manifest_path, unpack=None):
    path, manifest = load_manifest(manifest_path)
    root = path.parent
    chunks = manifest["chunks"]
    if any(not HEX.fullmatch(key) for key in chunks):
        raise ExportError("Invalid chunk identity")
    shard_names = [row["path"] for row in manifest["shards"]]
    if len(shard_names) != len(set(shard_names)):
        raise ExportError("Duplicate shard path")
    verified_chunks = set()
    for shard in manifest["shards"]:
        relative = checked_relative(shard["path"])
        if len(relative.parts) != 1 or not re.fullmatch(r"shard-[0-9]{4}\.zip", relative.name):
            raise ExportError("Unsafe shard filename")
        shard_path = root / relative.name
        regular(shard_path, root)
        raw = shard_path.read_bytes()
        if len(raw) != shard["bytes"] or sha(raw) != shard["sha256"]:
            raise ExportError("Shard hash/size mismatch")
        expected = {row["member"]: (digest, row) for digest, row in chunks.items() if row["shard"] == relative.name}
        with zipfile.ZipFile(shard_path) as archive:
            infos = archive.infolist()
            if len(infos) != len(expected) or {i.filename for i in infos} != set(expected):
                raise ExportError("Shard member roster mismatch")
            total = sum(info.file_size for info in infos)
            if total != shard["uncompressed_bytes"] or total > manifest["shard_uncompressed_limit_bytes"]:
                raise ExportError("Shard uncompressed limit/size mismatch")
            for info in infos:
                digest, entry = expected[info.filename]
                if (info.filename != "chunks/" + digest or info.file_size != entry["bytes"] or
                        not 0 < info.file_size <= manifest["chunk_limit_bytes"]):
                    raise ExportError("Chunk member identity/size mismatch")
                data = archive.read(info)
                if sha(data) != digest:
                    raise ExportError("Chunk hash mismatch")
                verified_chunks.add(digest)
    if verified_chunks != set(chunks):
        raise ExportError("Chunk references an absent shard")
    rows = {row["path"]: row for row in manifest["files"]}
    if unpack is not None and Path(unpack).exists():
        raise ExportError("Unpack destination already exists; no files overwritten")
    # Reconstruct on disk, keeping memory bounded to a chunk, or to one JSON
    # response while recovering a compact result. Never hold the whole bundle.
    with tempfile.TemporaryDirectory(prefix="ru-evidence-verify-") as temporary:
        workspace = Path(temporary)
        for name, row in rows.items():
            target = workspace / Path(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with target.open("xb") as output:
                for identity in row["chunks"]:
                    if identity not in chunks:
                        raise ExportError("File references a missing chunk")
                    entry = chunks[identity]
                    with zipfile.ZipFile(root / entry["shard"]) as archive:
                        data = archive.read(entry["member"])
                    digest.update(data)
                    size += len(data)
                    output.write(data)
            if size != row["stored_bytes"] or digest.hexdigest() != row["stored_sha256"]:
                raise ExportError("Stored file hash/size mismatch")
        # Restore capture wrappers before result contexts that depend on them.
        for name, row in rows.items():
            transformation = row.get("transformation", {})
            if transformation.get("kind") != "omit_capture_decoded_copies":
                continue
            target = workspace / Path(*PurePosixPath(name).parts)
            context = json.loads(target.read_bytes())
            if not isinstance(context, dict) or "raw_body" in context or "json" in context:
                raise ExportError("Invalid compact capture context")
            try:
                raw = base64.b64decode(context["body_base64"], validate=True)
                text = raw.decode("utf-8")
                parsed = json.loads(text)
            except (KeyError, ValueError, TypeError):
                raise ExportError("Compact capture body cannot be reconstructed") from None
            if not isinstance(parsed, dict):
                raise ExportError("Compact capture body is not an object")
            context.update(raw_body=text, json=parsed)
            recovered = encoded(context)
            if len(recovered) != row["original_bytes"] or sha(recovered) != row["original_sha256"]:
                raise ExportError("Restored capture original hash/size mismatch")
            target.write_bytes(recovered)
        for name, row in rows.items():
            target = workspace / Path(*PurePosixPath(name).parts)
            transformation = row.get("transformation")
            if transformation and transformation.get("kind") != "omit_capture_decoded_copies":
                if transformation.get("kind") != "omit_duplicate_result_response":
                    raise ExportError("Unknown reconstruction transformation")
                reference = transformation.get("response_file")
                checked_relative(reference)
                if (reference not in rows or rows[reference].get("transformation", {}).get("kind") not in
                        (None, "omit_capture_decoded_copies")):
                    raise ExportError("Missing or transformed response dependency")
                context = json.loads(target.read_bytes())
                if not isinstance(context, dict) or "response" in context:
                    raise ExportError("Invalid compact result context")
                response_path = workspace / Path(*PurePosixPath(reference).parts)
                context["response"] = json.loads(response_path.read_bytes())
                target.write_bytes(encoded(context))
            digest, size = hashlib.sha256(), 0
            with target.open("rb") as source:
                for block in iter(lambda: source.read(CHUNK_BYTES), b""):
                    digest.update(block)
                    size += len(block)
            if size != row["original_bytes"] or digest.hexdigest() != row["original_sha256"]:
                raise ExportError("Restored original hash/size mismatch")
        if unpack is not None:
            import shutil
            destination = Path(unpack).absolute()
            shutil.copytree(workspace, destination)
            (destination / "bundle-manifest.json").write_bytes(path.read_bytes())
    return {"verified": True, "files": len(rows), "chunks": len(chunks),
            "shards": len(manifest["shards"]),
            "restored_bytes": sum(row["original_bytes"] for row in rows.values()),
            "scientific_validity": "not_assessed", "unpacked": unpack is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--export", type=Path, metavar="STATE")
    commands.add_argument("--verify", type=Path, metavar="MANIFEST")
    parser.add_argument("--output", type=Path, help="New directory for manifest.json and ZIP shards")
    parser.add_argument("--unpack", type=Path, help="Restore original bytes after --verify, into a new directory")
    parser.add_argument("--env-file", type=Path, default=PROJECT / ".env",
                        help="Local credential source used only for in-memory scanning")
    args = parser.parse_args()
    if args.export and (args.output is None or args.unpack):
        parser.error("--export requires --output and cannot be combined with --unpack")
    if args.verify and args.output:
        parser.error("--output is only valid with --export")
    try:
        result = (export_bundle(args.export, args.output, secrets=credentials(args.env_file)) if args.export
                  else verify_bundle(args.verify, args.unpack))
    except (ExportError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        # Do not echo parser contents or upstream exception messages: raw input
        # can be malformed or contain a reflected credential.
        if isinstance(exc, ExportError):
            print("Export refused: " + str(exc), file=sys.stderr)
        else:
            print("Export verification failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
