"""Pure checks of an explicit artifact roster; no claim about scientific completeness."""
import base64
import hashlib
import json
from episteme.domains import api

REQUIRED_ROLES = {"protocol", "tasks", "results", "source"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify(files):
    require("manifest.json" in files, "Missing evidence manifest")
    manifest = api.strict_loads(files["manifest.json"])
    require(manifest.get("schema_version") == 1 and
            manifest.get("purpose") == "resumption_artifact_integrity_only" and
            manifest.get("scientific_validity") == "not_assessed" and
            manifest.get("inference_mode") == "exploratory", "Wrong evidence manifest/status")
    rows = manifest.get("artifacts")
    require(type(rows) is list and bool(rows), "Empty artifact roster")
    require({r["role"] for r in rows} >= REQUIRED_ROLES, "Missing required protocol/tasks/results/source role")
    for role in ("protocol", "tasks", "results"):
        require(sum(r["role"] == role for r in rows) == 1, "Missing or duplicate required role: " + role)
    paths = [r["path"] for r in rows]
    require(len(set(paths)) == len(paths) and set(files) == set(paths) | {"manifest.json"}, "Capture roster differs from declared artifacts")
    for row in rows:
        path = row["path"]
        require(type(path) is str and path and not path.startswith("/") and "\\" not in path and
                all(part not in ("", ".", "..") for part in path.split("/")), "Unsafe artifact path")
        data = files[path]
        require(type(row["bytes"]) is int and row["bytes"] > 0 and len(data) == row["bytes"] and sha(data) == row["sha256"],
                "Captured bytes changed or empty: " + path)
        require(row["format"] in ("json", "bytes"), "Unsupported artifact format")
        if row["format"] == "json":
            api.strict_loads(data)
    return manifest


def compiled(manifest, files):
    return {"manifest": manifest, "manifest_sha256": sha(files["manifest.json"]),
            "artifacts": [{**row, "base64": base64.b64encode(files[row["path"]]).decode("ascii")}
                          for row in manifest["artifacts"]]}


def expected_raw(data, unit):
    return {"schema_version": 1, "roster_unit": unit, "manifest_sha256": data["manifest_sha256"],
            "artifact": data["artifacts"][unit]}


def metric(raw):
    artifact = raw["artifact"]
    data = base64.b64decode(artifact["base64"], validate=True)
    require(len(data) == artifact["bytes"] and sha(data) == artifact["sha256"], "Raw artifact integrity mismatch")
    if artifact["format"] == "json":
        api.strict_loads(data)
    return len(data)
