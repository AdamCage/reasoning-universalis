"""Restore a Stage 2 evidence ZIP and refuse a workflow claim that is not in the store.

stage2.evidence.verify checks archive hashes and one provenance slice. A rewritten
workflow claim can still match those checks after its own hash is updated. This
audit restores the kernel backup and requires the claim id to exist there.
"""
import json
import tempfile
import zipfile
from pathlib import Path

from stage2.episteme_bridge import register
from stage2.evidence import verify as verify_archive


def audit(archive):
    register()
    summary = verify_archive(archive)
    from episteme.recovery import restore
    from episteme.store import Store
    with tempfile.TemporaryDirectory(prefix="stage3-audit-") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(archive) as bundle:
            workflow = json.loads(bundle.read("workflow-result.json"))
            bundle.extractall(root)
        restore(root / "kernel-backup", root / "restored")
        with Store(root / "restored") as store:
            claim_id = workflow["claim"]
            found = [event for event in store.events() if event["id"] == claim_id]
            if len(found) != 1 or found[0]["kind"] != "claim":
                raise ValueError("Workflow claim is not the restored kernel claim")
            payload = found[0]["payload"]
            if payload.get("outcome") != "inconclusive" or payload.get("inference_mode") != "exploratory":
                raise ValueError("Restored claim is stronger than the Stage 2 result")
    summary["kernel_claim"] = "restored"
    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), indent=2))


if __name__ == "__main__":
    main()
