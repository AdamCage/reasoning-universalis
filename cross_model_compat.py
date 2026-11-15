"""One finite transport addendum after two failed probes and zero study calls.

The frozen scientific design and local vote parser are reused unchanged. The
initial condition is closed; no attempted request is retried or overwritten.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cross_model.annotation import request_body as original_body
from cross_model.common import ARTIFACT as ORIGINAL_ARTIFACT, PROTOCOL as ORIGINAL_PROTOCOL, ROUTES, read, sha
from cross_model.runner import Collector as OriginalCollector
from stage0.runner import http

ARTIFACT = "artifacts/cross-model-compat-2026-11-15"
PROTOCOL = "design/CROSS_MODEL_TRANSPORT_ADDENDUM_2026_11_15.json"


def request_body(item, codebook, model, provider, condition="full_context"):
    body = original_body(item, codebook, model, provider, condition)
    # Backend grammar does not implement uniqueItems. The unchanged complete
    # schema remains in the user prompt and local parser still enforces it.
    body["response_format"]["json_schema"]["schema"]["properties"]["secondary_roles"].pop("uniqueItems", None)
    if model == "openai/gpt-oss-20b":
        body["reasoning"] = {"enabled": True, "effort": "low"}
    return body


def cells(document, codebook):
    # The initial TWO attempted probes consume two of the authorized194calls.
    # Exactly192 never-attempted study cells remain. First full-context item
    # doubles as each route's technical admission; its valid label is retained.
    return [{"model": model, "provider": provider, "condition": condition, "item_id": item["item_id"],
             "request": request_body(item, codebook, model, provider, condition)}
            for model, provider in ROUTES
            for condition, items in (("full_context", document["items"]),
                ("without_context", [i for i in document["items"] if i["item_id"] in document["ablation_ids"]]))
            for item in items]


class Collector(OriginalCollector):
    def __init__(self, project, transport=http):
        self.project = Path(project).resolve()
        self.base = self.project / ARTIFACT
        self.protocol_path = self.project / PROTOCOL
        self.protocol = read(self.protocol_path)
        self.digest = sha(self.protocol_path.read_bytes())
        self.document, self.codebook = read(self.base / "input-items.json"), read(self.base / "codebook.json")
        self.items = {i["item_id"]: i for i in self.document["items"]}
        self.state = self.project / ".research/resumption-2026-11-08-live"
        self.ledger_path = self.state / "ledger.json"
        self.launch = read(self.base / "ledger-launch.json")
        self.launch_amount = sum((Decimal(r["charged_or_reserved_rub"]) for r in self.launch), Decimal(0))
        original_launch = read(self.project / ORIGINAL_ARTIFACT / "cost-quote.json")["launch_charged_or_reserved_rub"]
        self.cap = min(Decimal(3300), Decimal(original_launch) + Decimal(400))
        self.scope = self.state / "cross-model" / self.digest
        self.transport = transport
        self.quote = read(self.base / "cost-quote.json")
        self.roster = cells(self.document, self.codebook)
        self.verify_frozen()
