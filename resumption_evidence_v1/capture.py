"""Read-only capture is the only file-reading hook."""
from pathlib import Path
from episteme.domains import api
from .inventory import verify


def capture(source):
    root = Path(source)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Capture requires a plain directory")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Capture links are forbidden")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    manifest = verify(files)
    return api.CaptureBundle(pack_id="resumption_evidence_v1", pack_version="1",
        source_label="previously_observed_resumption_artifacts", files=files,
        audit={"purpose": manifest["purpose"], "artifacts": len(manifest["artifacts"]),
               "scientific_validity": "not_assessed", "historical_exposure": "already_observed"})
