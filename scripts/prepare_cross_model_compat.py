"""Freeze one premeasurement transport addendum, without changing v1 artifacts."""
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model.common import ARTIFACT as ORIGINAL_ARTIFACT, PROTOCOL as ORIGINAL_PROTOCOL, ROUTES, immutable, read, sha, utcnow, write
from cross_model_compat import ARTIFACT, PROTOCOL, cells
from resumption.runner import ceiling_rates
from stage0.runner import encode, estimate


def prepare(project=ROOT):
    project = Path(project)
    old, base = project / ORIGINAL_ARTIFACT, project / ARTIFACT
    initial = read(old / "new-annotations.json")["cells"]
    attempted = [c for c in initial if "call_id" in c]
    if len(attempted) != 2 or any(c["condition"] != "schema_probe" or c["vote"] is not None for c in attempted):
        raise ValueError("Compatibility addendum only after exactly2 failed probes and zero study outputs")
    if any(c.get("vote") is not None for c in initial):
        raise ValueError("Do not amend after viewing study labels")
    for name in ("input-items.json", "mapping.json", "codebook.json", "selection-summary.json"):
        data = (old / name).read_bytes()
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Compatibility inputs differ")
        target.write_bytes(data)
    (base / "metadata").mkdir(exist_ok=True)
    for path in (old / "metadata").glob("*.json"):
        target = base / "metadata" / path.name
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise ValueError("Compatibility metadata differs")
        shutil.copyfile(path, target)
    protected = read(old / "parent-integrity.json")
    extra = [project / ORIGINAL_PROTOCOL, old / "new-annotations.json", old / "budget-final.json", old / "ledger-final.json"]
    extra.extend(path for path in (old / "raw").rglob("*.json"))
    protected["files"].update({p.relative_to(project).as_posix(): sha(p.read_bytes()) for p in extra})
    immutable(base / "parent-integrity.json", protected)
    roster = cells(read(base / "input-items.json"), read(base / "codebook.json"))
    ledger_path = project / ".research/resumption-2026-11-08-live/ledger.json"
    ledger = read(ledger_path)
    if ledger != read(old / "ledger-final.json") or len(ledger) != 2111:
        raise ValueError("Initial failed probes and obligations must remain intact")
    immutable(base / "ledger-launch.json", ledger)
    routes = []
    for model, provider in ROUTES:
        receipt_path = base / "metadata" / (model.replace("/", "_") + ".json")
        receipt = read(receipt_path)
        price = ceiling_rates(receipt["response"], provider)
        selected = [c for c in roster if c["model"] == model]
        total = sum((estimate(c["request"], price) for c in selected), Decimal(0))
        routes.append({"model": model, "provider": provider, "calls": len(selected), "reservation_rub": str(total),
            "prompt_rub_per_token_ceiling": str(price[0]), "completion_rub_per_token_ceiling": str(price[1]),
            "metadata_path": receipt_path.relative_to(project).as_posix(), "metadata_sha256": sha(receipt_path.read_bytes())})
    commitment = sum((Decimal(r["charged_or_reserved_rub"]) for r in ledger), Decimal(0))
    original = Decimal(read(old / "cost-quote.json")["launch_charged_or_reserved_rub"])
    total = sum((Decimal(r["reservation_rub"]) for r in routes), Decimal(0))
    if commitment - original + total > 400 or commitment + total > 3300:
        raise ValueError("Addendum and initial failures exceed accepted total new cap")
    quoted = {"maximum_new_calls": len(roster), "maximum_total_calls_including_initial_failed_probes": 194,
        "prior_failed_probe_calls": 2, "prior_failed_probe_reservation_rub": str(commitment-original), "routes": routes,
        "worst_case_reservation_rub": str(total), "all_new_reservation_including_initial_failures_rub": str(commitment-original+total),
        "launch_charged_or_reserved_rub": str(commitment), "new_cap_rub": "400", "paid_requests": 0,
        "authorization": "existing explicit400RUB approval; never-attempted study cells only; no sample expansion or failed-case repeat"}
    immutable(base / "cost-quote.json", quoted)
    # Derive an exact copy of the frozen analysis with ONLY routing imports and
    # artifact constants changed. The statistical algorithms are byte-identical.
    original_source = (project / "scripts/reproduce_cross_model.py").read_text(encoding="utf-8")
    source = original_source.replace("from cross_model.common import ARTIFACT, ROUTES, PROTOCOL, read, sha, write", "from cross_model.common import ROUTES, read, sha, write\nfrom cross_model_compat import ARTIFACT, PROTOCOL")
    source = source.replace("from cross_model.runner import cells as expected_cells", "from cross_model_compat import cells as expected_cells")
    target = project / "scripts/reproduce_cross_model_compat.py"
    data = source.encode("utf-8")
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Compatibility analysis differs from exact frozen derivation")
    target.write_bytes(data)
    files = {p: digest for p,digest in read(project / ORIGINAL_PROTOCOL)["frozen_files"].items()}
    files.update({p.relative_to(project).as_posix():sha(p.read_bytes()) for p in extra})
    names = ["cross_model_compat.py", "scripts/collect_cross_model_compat.py", "scripts/prepare_cross_model_compat.py", "scripts/reproduce_cross_model_compat.py", "tests/test_cross_model_compat.py"]
    files.update({p:sha((project / p).read_bytes()) for p in names})
    files.update({(base / p).relative_to(project).as_posix():sha((base / p).read_bytes()) for p in
                 ("input-items.json", "mapping.json", "codebook.json", "selection-summary.json", "parent-integrity.json", "ledger-launch.json", "cost-quote.json")})
    prior = read(project / ORIGINAL_PROTOCOL)
    protocol = {"protocol_id": "cross-model-2026-11-15-transport-addendum1", "created_utc": utcnow(),
        "parent_protocol": ORIGINAL_PROTOCOL, "parent_protocol_sha256": sha((project / ORIGINAL_PROTOCOL).read_bytes()),
        "stage": "premeasurement after technical admission failures, zero study outputs observed",
        "scientific_design": "Every sampling, ontology, parsing, comparison, bootstrap, example-selection and interpretation rule of parent remains in force",
        "changes": ["Transport grammar only omits unsupported uniqueItems; exact original schema in prompt and local strict parser unchanged",
                    "GPT-OSS requires reasoning; request enabled=true effort=low, include_reasoning=false. Content-only labels; returned reasoning flagged, ignored for labeling",
                    "No extra probes: first fixed full-context study item gates each route. At most2initial+192study=194calls total. A failed first study item stops route; no further transport amendments"],
        "transport_failures": [{k:c[k] for k in ("model", "call_id", "response_sha256", "technical_status")} for c in attempted],
        "allocation": {"initial_probe_calls": 2, "remaining_full_context": 144, "remaining_without_context": 48, "maximum_total_calls": 194},
        "budget": {"new_cap_rub": "400", "same_explicit_authorization": True, "all_prior_obligations_retained": True,
            "no_additional_calls_above_original194": True, "worst_case_all_new_rub": quoted["all_new_reservation_including_initial_failures_rub"]},
        "execution": prior["execution"], "frozen_files": files}
    protocol_path = project / PROTOCOL
    if protocol_path.exists():
        protocol["created_utc"] = read(protocol_path)["created_utc"]
    immutable(protocol_path, protocol)
    print({"protocol_sha256":sha(protocol_path.read_bytes()), "study_calls":len(roster), "worst_case_all_new_rub":quoted["all_new_reservation_including_initial_failures_rub"], "paid_requests":0})


if __name__ == "__main__":
    prepare()
