"""Bounded, journaled RouterAI collection for the resumption study.

No command retries an attempted request. Operational trace admission establishes
only a visible text channel, never its faithfulness, human validity, or E0.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import quote
import zipfile

from stage0.runner import Ledger, StopRun, encode, estimate, http, rates, redact
from stage0.traces import inspect_embeddings, inspect_trace
from stage0.config import parse_env

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_SHA = "e062d9bdd228933ddcca0047d9ee15e564b82413bf88f92c5d06550c9febb88d"
HISTORICAL_MEMBER = "evidence/stage0-budget.json"
HISTORICAL_ARCHIVE = ROOT / "evidence/stage0-2026-10-12.zip"
CANDIDATES = ("qwen/qwen3-32b", "deepseek/deepseek-v4.1-flash", "openai/gpt-oss-20b")
EMBEDDERS = ("baai/bge-m3", "qwen/qwen3-embedding-8b")
CAP = Decimal("900")
AUTHORIZED_CAP = Decimal("3000")  # Explicit user increase, 8 November 2026.
_THREAD_LOCK = threading.RLock()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ceiling_rates(response, provider=None):
    """Reserve the maximum declared rate, never a guessed time-of-day discount.

    Provider-specific rates apply only to a request pinned to that exact provider.
    Historical stage0 pricing and its evidence are deliberately unchanged.
    """
    endpoints = response.get("json", {}).get("data", {}).get("endpoints", [])
    if provider is not None:
        endpoints = [e for e in endpoints if e.get("provider_name") == provider]
        if not endpoints:
            raise StopRun("Pinned provider has no exact endpoint quotation")
    bounded = []
    for endpoint in endpoints:
        units = endpoint.get("pricing_units", {})
        if units.get("prompt") != "token" or units.get("completion", "token") != "token":
            raise StopRun("Unknown pricing units; cannot reserve budget")
        base = endpoint.get("pricing", {})
        if any(key not in units for key in base):
            raise StopRun("Endpoint charge lacks explicit units")
        variants = [base]
        for variation in endpoint.get("variable_pricings", []):
            if variation.get("type") not in ("prompt-threshold", "time-of-day"):
                raise StopRun("Unsupported variable pricing")
            if variation.get("pricing_units", units) != units:
                raise StopRun("Variable pricing changes units")
            variants.append({**base, **variation})
        for price in variants:
            # These are mutually alternative input/cache rates. Taking their
            # maximum also covers a cache miss. Other nonzero charges fail closed.
            for key, value in price.items():
                if key in units and key not in ("prompt", "completion", "input_cache_read", "input_cache_write"):
                    if Decimal(str(value)) != 0:
                        raise StopRun("Additional nonzero endpoint charge is unsupported")
            prompt = max(Decimal(str(price[key])) for key in
                         ("prompt", "input_cache_read", "input_cache_write") if key in price)
            completion = Decimal(str(price.get("completion", 0)))
            if any(not x.is_finite() or x < 0 or x >= 1 for x in (prompt, completion)):
                raise StopRun("Endpoint price is not a finite supported rub/token rate")
            bounded.append((prompt, completion))
    if not bounded:
        raise StopRun("No endpoint quotation is available")
    return max(p[0] for p in bounded), max(p[1] for p in bounded)


def chunks(text: str, words: int = 16, maximum: int = 512) -> list[dict]:
    """Non-overlapping observed-word chunks; offsets index original text.

    A partial final chunk is retained but prefixes use only complete chunks.
    These are whitespace words, not native model tokens.
    """
    spans = list(re.finditer(r"\S+", text))[:maximum]
    return [{"text": text[spans[i].start():spans[min(i + words, len(spans)) - 1].end()],
             "start": spans[i].start(), "end": spans[min(i + words, len(spans)) - 1].end(),
             "word_start": i, "word_end": min(i + words, len(spans))}
            for i in range(0, len(spans), words)]


def balanced_tasks(tasks):
    """Round-robin fixed root groups across split/domain/difficulty strata.

    Both paired task members stay together. No model output or label enters
    the order. All models for one task/sample are queued consecutively.
    """
    roots = defaultdict(list)
    for task in tasks:
        roots[task["root_id"]].append(task)
    strata = defaultdict(list)
    for root, members in roots.items():
        attributes = {(m["split"], m["domain"], m["difficulty"]) for m in members}
        if len(attributes) != 1:
            raise StopRun("A root group crosses allocation strata")
        strata[next(iter(attributes))].append((root, members))
    queues = {key: deque(sorted(rows, key=lambda row: sha(encode(["allocation-v1", row[0]]))))
              for key, rows in strata.items()}
    ordered = []
    while any(queues.values()):
        for key in sorted(queues):
            if queues[key]:
                _, members = queues[key].popleft()
                ordered.extend(sorted(members, key=lambda t: t.get("task_id", t["root_id"])))
    return ordered


@dataclass
class Settings:
    state: Path = field(default_factory=lambda: ROOT / ".research/resumption-2026-11-08")
    key: str = field(default="", repr=False)
    cap: Decimal = CAP
    collection_cap: Decimal = Decimal("800")
    max_tokens: int = 4096
    concurrency: int = 3
    timeout: int = 900
    seed: int = 42
    temperature: float = .7
    top_p: float = .95
    deadline: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat())

    def __post_init__(self):
        self.state = Path(self.state)
        self.cap = Decimal(str(self.cap))
        self.collection_cap = Decimal(str(self.collection_cap))
        if not self.cap.is_finite() or not 0 < self.cap <= AUTHORIZED_CAP:
            raise ValueError("Cap must be finite, positive, and no greater than 3000 RUB")
        if not self.collection_cap.is_finite() or not 0 < self.collection_cap <= self.cap:
            raise ValueError("Collection cap must be positive and within the total cap")
        if self.key and (not self.key.strip() or any(char.isspace() for char in self.key)
                         or self.key in ("YOUR_API_KEY", "YOUR_LOCAL_KEY", "your_key_here", "CHANGE_ME", "<ROUTERAI_API_KEY>")):
            raise ValueError("ROUTERAI_API_KEY is blank, malformed, or a placeholder")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 8192:
            raise ValueError("Completion cap must be in 1..8192")
        if type(self.concurrency) is not int or not 1 <= self.concurrency <= 3:
            raise ValueError("Concurrency must be in 1..3")
        if self.timeout < 1 or not 0 <= self.temperature <= 2 or not 0 < self.top_p <= 1:
            raise ValueError("Invalid transport or sampling settings")
        if self.deadline:
            deadline = datetime.fromisoformat(self.deadline.replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                raise ValueError("Deadline must include a timezone")


class Runner:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport or http
        self.state = settings.state
        self.state.mkdir(parents=True, exist_ok=True)
        self.calls = self.state / "calls"
        self.calls.mkdir(exist_ok=True)
        self.ledger_path = self.state / "ledger.json"
        self.prices: dict[str, tuple[Decimal, Decimal]] = {}
        self.price_receipts = {}
        self.protocol_digest = None
        self.tasks_digest = None
        self.source_inventory_digest = None
        self.verifier_source_digest = None
        self._initialize_ledger()

    @contextmanager
    def locked(self):
        # OS locks handle separate processes; RLock handles worker threads.
        with _THREAD_LOCK:
            with (self.state / "budget.lock").open("a+b") as lock:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0, os.SEEK_END)
                    if lock.tell() == 0:
                        lock.write(b"0")
                        lock.flush()
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if os.name == "nt":
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)

    def _initialize_ledger(self):
        with zipfile.ZipFile(HISTORICAL_ARCHIVE) as bundle:
            historical = bundle.read(HISTORICAL_MEMBER)
        if sha(historical) != HISTORICAL_SHA:
            raise StopRun("Published historical ledger digest mismatch")
        self.historical_rows = json.loads(historical)
        with self.locked():
            if not self.ledger_path.exists():
                self.ledger_path.write_bytes(historical)
            self._check_ledger()

    def _check_ledger(self):
        rows = read_json(self.ledger_path)
        if not isinstance(rows, list) or rows[:len(self.historical_rows)] != self.historical_rows:
            raise StopRun("Historical ledger rows were removed or changed")
        for row in rows:
            value = Decimal(str(row["charged_or_reserved_rub"]))
            if not value.is_finite() or value < 0:
                raise StopRun("Ledger contains invalid commitments")
        ledger = Ledger(self.ledger_path, self.settings.cap)
        if ledger.committed > self.settings.cap:
            raise StopRun("Budget exhausted; historical commitments are retained")
        return ledger

    def save(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = encode(value)
        if self.settings.key:
            data = redact(data.decode("utf-8"), self.settings.key).encode("utf-8")
        temporary = path.with_name(path.name + ".tmp-" + str(threading.get_ident()))
        temporary.write_bytes(data)
        os.replace(temporary, path)
        return sha(data)

    def bind(self, protocol_path, corpus_path=None):
        self._freeze_sources()
        protocol = read_json(protocol_path)
        generation = protocol.get("generation", {})
        for declared, attribute in (("max_output_tokens", "max_tokens"), ("temperature", "temperature"),
                                    ("top_p", "top_p"), ("seed", "seed")):
            if declared in generation and generation[declared] != getattr(self.settings, attribute):
                raise StopRun("Sampling configuration differs from the bound protocol: " + declared)
        declared_corpus = protocol.get("tasks", {}).get("file_sha256")
        if corpus_path is not None and declared_corpus and sha(Path(corpus_path).read_bytes()) != declared_corpus:
            raise StopRun("Corpus digest differs from the prospective protocol")
        for name, source in (("protocol", protocol_path), ("corpus", corpus_path)):
            if source is None:
                continue
            data = Path(source).read_bytes()
            digest = sha(data)
            with self.locked():
                destination = self.state / (name + ".json")
                if destination.exists() and sha(destination.read_bytes()) != digest:
                    raise StopRun(name + " changed after the run snapshot was bound")
                if not destination.exists():
                    destination.write_bytes(data)
            setattr(self, "protocol_digest" if name == "protocol" else "tasks_digest", digest)
        if corpus_path is None and (self.state / "corpus.json").exists():
            self.tasks_digest = sha((self.state / "corpus.json").read_bytes())
        declared_deadline = generation.get("dispatch_deadline_utc")
        if declared_deadline:
            declared_time = datetime.fromisoformat(declared_deadline.replace("Z", "+00:00"))
            if declared_time.tzinfo is None:
                raise StopRun("Protocol dispatch deadline must include a timezone")
            requested_time = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
            if declared_time < requested_time:
                self.settings.deadline = declared_deadline
        with self.locked():
            deadline_path = self.state / "dispatch-window.json"
            if deadline_path.exists():
                # Resuming a command cannot silently extend its paid window.
                window = read_json(deadline_path)
                existing = window["deadline"]
                if self.settings.deadline and existing:
                    requested_time = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
                    existing_time = datetime.fromisoformat(existing.replace("Z", "+00:00"))
                    if requested_time < existing_time:
                        window["deadline"] = self.settings.deadline
                        window["tightened_at"] = utcnow()
                        self.save(deadline_path, window)
                self.settings.deadline = window["deadline"]
            else:
                self.save(deadline_path, {"started_at": utcnow(), "deadline": self.settings.deadline})

    def _source_files(self):
        paths = sorted((ROOT / "resumption").glob("*.py"))
        paths += [ROOT / "stage0" / name for name in ("runner.py", "traces.py", "config.py")]
        return {str(path.relative_to(ROOT)).replace(os.sep, "/"): path.read_bytes() for path in paths}

    def _freeze_sources(self):
        sources = self._source_files()
        inventory = {"schema_version": 1,
                     "scope": "resumption/*.py and stage0/{runner,traces,config}.py exact source bytes",
                     "files": {name: sha(data) for name, data in sorted(sources.items())}}
        data = encode(inventory)
        path = self.state / "source-inventory.json"
        with self.locked():
            if path.exists():
                if path.read_bytes() != data:
                    raise StopRun("Research source changed after the run snapshot was bound")
                for name, digest in inventory["files"].items():
                    snapshot = self.state / "source" / name
                    if not snapshot.exists() or sha(snapshot.read_bytes()) != digest:
                        raise StopRun("Frozen source snapshot is missing or changed")
            else:
                for name, content in sources.items():
                    if self.settings.key and self.settings.key.encode() in content:
                        raise StopRun("Credential literal appears in source; snapshot refused")
                    target = self.state / "source" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                path.write_bytes(data)
        self.source_inventory_digest = sha(data)
        self.verifier_source_digest = inventory["files"]["resumption/generator_audit.py"]

    def _check_sources(self):
        if not self.source_inventory_digest:
            raise StopRun("Source snapshot is required before paid dispatch")
        inventory_path = self.state / "source-inventory.json"
        if not inventory_path.exists() or sha(inventory_path.read_bytes()) != self.source_inventory_digest:
            raise StopRun("Bound source inventory is missing or changed")
        expected = read_json(inventory_path)["files"]
        actual = {name: sha(data) for name, data in self._source_files().items()}
        if actual != expected:
            raise StopRun("Research source changed before paid dispatch")

    def _embedding_chunk_guard(self, call_id, model, identities, register=False):
        """Derive a chunk registry from all attempts, including unknown ones.

        Regrouping chunks into a different batch cannot turn a failed/unknown
        logical chunk into a fresh paid request. Completed original batches are
        reusable without transport; regrouping fails closed.
        """
        entries = {}
        for path in sorted(self.calls.glob("*/reservation.json")):
            context = read_json(path)
            if context.get("kind") != "embedding":
                continue
            for identity in context.get("identity", []):
                chunk = sha(encode([context.get("protocol_sha256"), context.get("model"), identity]))
                previous = entries.setdefault(chunk, context["call_id"])
                if previous != context["call_id"]:
                    raise StopRun("Embedding journals contain repeated logical chunks")
        requested = [sha(encode([self.protocol_digest, model, identity])) for identity in identities]
        if len(set(requested)) != len(requested):
            raise StopRun("Embedding request repeats a logical chunk")
        if any(chunk in entries and entries[chunk] != call_id for chunk in requested):
            raise StopRun("Embedding chunk was already attempted in another batch; it cannot be resent")
        if register:
            entries.update({chunk: call_id for chunk in requested})
            self.save(self.state / "embedding-attempted-chunks.json", {"schema_version": 1, "chunks": entries})

    def _deadline(self):
        if self.settings.deadline:
            deadline = datetime.fromisoformat(self.settings.deadline.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= deadline:
                raise StopRun("Dispatch deadline reached")

    def _metadata(self, path, name):
        response = self.transport(path, timeout=min(self.settings.timeout, 30))
        record = {"retrieved_at": utcnow(), "endpoint": path,
                  "response": {k: v for k, v in response.items() if k != "headers"}}
        receipt = self.save(self.state / "metadata" / (name + ".json"), record)
        self.save(self.state / "metadata" / "history" / (receipt + ".json"), record)
        if response.get("http_status") != 200 or response.get("json", {}).get("error"):
            raise StopRun("Metadata unavailable: " + name)
        return {**response, "metadata_receipt_sha256": receipt}

    def catalog(self, models=()):
        catalog = self._metadata("/models", "catalog")
        data = catalog.get("json", {}).get("data", [])
        if not isinstance(data, list):
            raise StopRun("Model catalog is not a list")
        available = {row.get("id") for row in data if isinstance(row, dict)}
        selected = list(models) or list(CANDIDATES + EMBEDDERS)
        summary = {"retrieved_at": utcnow(), "models": [], "paid_requests": 0}
        for model in selected:
            row = {"model": model, "listed": model in available}
            if model in available:
                try:
                    price = self.price(model)
                    row["max_prompt_rub_per_token"] = str(price[0])
                    row["max_completion_rub_per_token"] = str(price[1])
                except StopRun:
                    row["price_status"] = "unavailable_or_unsupported"
            summary["models"].append(row)
        self.save(self.state / "catalog-summary.json", summary)
        return summary

    def price(self, model, provider=None):
        if model not in CANDIDATES + EMBEDDERS:
            raise StopRun("Model is outside the explicit resumption candidates")
        cache_key = (model, provider)
        with _THREAD_LOCK:
            if cache_key not in self.prices:
                response = self._metadata("/models/" + quote(model, safe="/") + "/endpoints", model.replace("/", "_") + "-endpoints")
                try:
                    price = ceiling_rates(response, provider)
                    if price is None or any(not p.is_finite() or p < 0 or p >= 1 for p in price):
                        raise ValueError
                except (KeyError, TypeError, ValueError, ArithmeticError):
                    raise StopRun("Pricing is missing, malformed, or outside the supported rub/token contract") from None
                self.prices[cache_key] = price
                self.price_receipts[cache_key] = response["metadata_receipt_sha256"]
            return self.prices[cache_key]

    def _cached_call(self, directory, expected_request):
        if not directory.exists():
            return None
        request_path = directory / "request.json"
        if not request_path.exists() or sha(request_path.read_bytes()) != sha(expected_request):
            raise StopRun("Previously attempted logical request changed; it cannot be resent")
        result_path = directory / "result.json"
        if not result_path.exists():
            raise StopRun("Previously attempted request has no finalized result; do not retry")
        result = read_json(result_path)
        result["reused_record_without_resend"] = True
        return result

    def paid(self, kind, identity, model, body):
        if not self.protocol_digest:
            raise StopRun("Bind an immutable protocol before paid dispatch")
        self._check_sources()
        # Logical identity does not include mutable sampling parameters: changing
        # a completion cap must never turn an unknown attempt into a new request.
        call_id = sha(encode({"kind": kind, "identity": identity, "protocol": self.protocol_digest, "model": model}))
        expected_request = encode(body)
        if self.settings.key:
            expected_request = redact(expected_request.decode(), self.settings.key).encode()
        directory = self.calls / call_id
        with self.locked():
            if kind == "embedding":
                self._embedding_chunk_guard(call_id, model, identity)
            cached = self._cached_call(directory, expected_request)
            if cached is not None:
                return cached
        # Recovery of recorded results is entirely offline, including after the
        # deadline or without a credential. Only a genuinely new request needs
        # a current quote, credential, dispatch window, and budget reservation.
        if not self.settings.key:
            raise StopRun("ROUTERAI_API_KEY is not configured")
        self._deadline()
        pinned = body.get("provider", {})
        provider = (pinned["order"][0] if pinned.get("allow_fallbacks") is False
                    and len(pinned.get("order", [])) == 1 else None)
        price = self.price(model, provider)
        amount = estimate(body, price)
        with self.locked():
            # A second worker/process could have reserved while metadata loaded.
            if kind == "embedding":
                self._embedding_chunk_guard(call_id, model, identity)
            cached = self._cached_call(directory, expected_request)
            if cached is not None:
                return cached
            self._deadline()
            ledger = self._check_ledger()
            if ledger.committed + amount > self.settings.cap:
                raise StopRun("Reservation would exceed the shared budget")
            if kind in ("generation", "admission") and ledger.committed + amount > self.settings.collection_cap:
                raise StopRun("Collection ceiling reached; remaining total budget is reserved for embeddings")
            directory.mkdir()
            request_digest = self.save(directory / "request.json", body)
            reservation = ledger.reserve(amount, "resumption:" + kind + ":" + model)
            context = {"call_id": call_id, "kind": kind, "identity": identity, "model": model,
                       "protocol_sha256": self.protocol_digest, "corpus_sha256": self.tasks_digest,
                       "source_inventory_sha256": self.source_inventory_digest,
                       "verifier_source_sha256": self.verifier_source_digest,
                       "request_sha256": request_digest, "reservation_id": reservation["id"],
                       "quote_receipt_sha256": self.price_receipts[(model, provider)],
                       "quoted_prompt_rub_per_token": str(price[0]),
                       "quoted_completion_rub_per_token": str(price[1]),
                       "quoted_provider": provider,
                       "reservation_rub": str(amount), "reserved_at": utcnow(), "automatic_retries": 0}
            self.save(directory / "reservation.json", context)
            if kind == "embedding":
                self._embedding_chunk_guard(call_id, model, identity, register=True)
        endpoint = "/embeddings" if kind == "embedding" else "/chat/completions"
        try:
            response = self.transport(endpoint, key=self.settings.key, body=body, timeout=self.settings.timeout)
        except Exception as exc:
            # Never log an exception message: some transports reflect credentials.
            response = {"http_status": None, "json": {}, "network_error": type(exc).__name__}
        safe = {key: value for key, value in response.items() if key != "headers"}
        response_digest = self.save(directory / "response.json", safe)
        with self.locked():
            ledger = self._check_ledger()
            row = next((row for row in ledger.rows if row["id"] == reservation["id"]), None)
            if row is None:
                raise StopRun("Reserved ledger row disappeared")
            overrun = False
            try:
                ledger.finish(row, safe)
            except StopRun:
                overrun = True
            result = {**context, "response_sha256": response_digest,
                      "http_status": safe.get("http_status"), "budget_overrun": overrun,
                      "ledger_sha256": sha(self.ledger_path.read_bytes()),
                      "response": safe, "completed_at": utcnow()}
            self.save(directory / "result.json", result)
        if overrun:
            raise StopRun("Reported cost exceeded the cap; all subsequent calls are blocked")
        return result

    def _routes(self):
        path = self.state / "admissions.json"
        routes = read_json(path).get("routes", []) if path.exists() else []
        for route in routes:
            directory = self.calls / route["evidence_trace_id"]
            try:
                request_data = (directory / "request.json").read_bytes()
                response_data = (directory / "response.json").read_bytes()
                request_body, response = json.loads(request_data), json.loads(response_data)
                payload = response.get("json", {})
                valid = (sha(request_data) == route["request_sha256"]
                         and sha(response_data) == route["response_sha256"]
                         and request_body["model"] == route["model"] == payload.get("model")
                         and payload.get("provider") == route["provider"]
                         and response.get("http_status") == 200
                         and request_body.get("reasoning", {}).get("enabled") is True
                         and request_body.get("include_reasoning") is True
                         and inspect_trace(payload)["status"] == "visible_trace_candidate")
            except (OSError, ValueError, KeyError, TypeError):
                valid = False
            if not valid:
                raise StopRun("Admission evidence is missing or changed")
        return routes

    def chat(self, model, task, sample_index=0, admission=False):
        if model not in CANDIDATES:
            raise StopRun("Unselected candidate: no automatic model substitution")
        root = task["root_id"]
        task_id = task.get("task_id", root)
        seed = self.settings.seed + int(sha(encode([task_id, model, sample_index, admission]))[:7], 16)
        body = {"model": model, "messages": [{"role": "user", "content": task["prompt"]}],
                "max_tokens": self.settings.max_tokens, "temperature": self.settings.temperature,
                "top_p": self.settings.top_p, "seed": seed, "stream": False,
                "reasoning": {"enabled": True}, "include_reasoning": True}
        allowed = [r for r in self._routes() if r["model"] == model and r.get("observed_trace_admitted") is True
                   and r.get("protocol_sha256") == self.protocol_digest]
        if not admission:
            if not allowed:
                raise StopRun("No observed-trace admission for this model and protocol")
            body["provider"] = {"order": [allowed[0]["provider"]], "allow_fallbacks": False}
        result = self.paid("admission" if admission else "generation", [task_id, sample_index], model, body)
        payload = result["response"].get("json", {})
        inspected = inspect_trace(payload)
        raw_reasoning = inspected["trace"]
        answer_marker = raw_reasoning.find("ANSWER:")
        predictor_text = raw_reasoning[:answer_marker] if answer_marker >= 0 else raw_reasoning
        provider = payload.get("provider")
        identity_ok = payload.get("model") == model and isinstance(provider, str) and bool(provider.strip())
        route_ok = admission or bool(allowed and allowed[0]["provider"] == provider)
        ok = (result["http_status"] == 200 and payload.get("error") is None and identity_ok and route_ok
              and inspected["status"] == "visible_trace_candidate")
        from resumption.generator_audit import verify_answer
        try:
            grading = verify_answer(task, inspected["answer"]) if ok else {"verdict": "unparseable"}
        except (ValueError, TypeError, KeyError):
            grading = {"verdict": "unparseable", "grading_uncertainty": True, "verifier_error": True}
        correct = {"correct": True, "incorrect": False}.get(grading.get("verdict"))
        record = {"trace_id": result["call_id"], "root_id": root,
                  "task_id": task.get("task_id", root), "model": model, "provider": provider,
                  "split": "admission" if admission else task["split"],
                  **{k: task.get(k) for k in ("domain", "family", "difficulty")},
                  "sample_index": sample_index, "seed": seed,
                  "text": predictor_text, "answer": inspected["answer"],
                  "raw_reasoning_text": raw_reasoning, "raw_reasoning_sha256": sha(raw_reasoning.encode()),
                  "predictor_censor": {"first_answer_marker_character": answer_marker if answer_marker >= 0 else None,
                                       "retained_characters": len(predictor_text)},
                  "correct": correct, "gradable": correct is not None, "grading": grading,
                  "status": "completed" if ok and predictor_text.strip() else "excluded",
                  "observed_generation_status": "completed" if ok else "excluded",
                  "observed_trace_status": inspected["status"],
                  "full_visible_trace": False, "E0": "not_passed",
                  "identity_verified": identity_ok, "provider_route_verified": bool(route_ok),
                  "finish_reason": inspected["finish_reason"], "source": inspected["source"],
                  "usage": payload.get("usage"), "protocol_sha256": self.protocol_digest,
                  "source_inventory_sha256": self.source_inventory_digest,
                  "verifier_source_sha256": self.verifier_source_digest,
                  "task_sha256": sha(encode(task)), "request_sha256": result["request_sha256"],
                  "response_sha256": result["response_sha256"], "phase": "admission" if admission else "collection"}
        self.save(self.calls / result["call_id"] / "trace.json", record)
        if admission and ok:
            with self.locked():
                routes = self._routes()
                if not any(r["model"] == model and r["provider"] == provider
                           and r["protocol_sha256"] == self.protocol_digest for r in routes):
                    routes.append({"model": model, "provider": provider,
                                   "observed_trace_admitted": True, "full_visible_trace": False,
                                   "E0": "not_passed", "protocol_sha256": self.protocol_digest,
                                   "evidence_trace_id": result["call_id"],
                                   "request_sha256": result["request_sha256"],
                                   "response_sha256": result["response_sha256"]})
                self.save(self.state / "admissions.json", {"routes": routes})
        return record

    def collect(self, tasks, models, samples=2, admission=False, limit=None):
        if samples < 1 or samples > 10:
            raise ValueError("Samples must be in 1..10")
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("Limit must be a positive integer")
        if len(set(models)) != len(models):
            raise StopRun("Model list repeats a model")
        selected = tasks[:limit] if limit is not None else tasks
        if len({t.get("task_id", t["root_id"]) for t in selected}) != len(selected):
            raise StopRun("Corpus repeats task IDs")
        root_splits = {}
        for task in selected:
            if task["root_id"] in root_splits and root_splits[task["root_id"]] != task["split"]:
                raise StopRun("A root group crosses splits")
            root_splits[task["root_id"]] = task["split"]
        if not models or not selected:
            raise StopRun("No models or tasks selected")
        jobs = [(model, task, -1 if admission else index)
                for index in range(1 if admission else samples)
                for task in balanced_tasks(selected) for model in models]
        records, failures = [], []
        if admission:
            # Serial within a candidate enables a finite two-failure stop.
            for model in models:
                failures_for_model = 0
                for job_model, task, index in jobs:
                    if job_model != model or failures_for_model >= 2:
                        continue
                    try:
                        record = self.chat(model, task, index, admission=True)
                        records.append(record)
                        failures_for_model += record["status"] != "completed"
                    except StopRun as exc:
                        failures.append({"model": model, "root_id": task["root_id"], "error": str(exc)})
                        failures_for_model += 1
        else:
            with ThreadPoolExecutor(max_workers=self.settings.concurrency) as pool:
                futures = {pool.submit(self.chat, model, task, index): (model, task["root_id"], index)
                           for model, task, index in jobs}
                for future in as_completed(futures):
                    model, root, index = futures[future]
                    try:
                        records.append(future.result())
                    except StopRun as exc:
                        failures.append({"model": model, "root_id": root, "sample_index": index, "error": str(exc)})
        document = {"protocol_sha256": self.protocol_digest, "corpus_sha256": self.tasks_digest,
                    "phase": "admission" if admission else "collection", "records": sorted(records, key=lambda r: r["trace_id"]),
                    "failures": failures, "E0": "not_passed", "scientific_validity": "not_assessed",
                    "finished_at": utcnow(), "budget": self.budget()}
        self.save(self.state / ("admission-results.json" if admission else "results.json"), document)
        return document

    def dry_run(self, corpus, models, samples=2):
        """Validate local setup without a key, metadata request, or reservation."""
        from resumption.generator_audit import canonical_instance_key, solve_reference
        tasks = corpus["tasks"] if isinstance(corpus, dict) else corpus
        roots = [task["root_id"] for task in tasks]
        task_ids = [task.get("task_id", task["root_id"]) for task in tasks]
        if not tasks or len(set(task_ids)) != len(task_ids):
            raise StopRun("Empty corpus or repeated task IDs")
        root_splits = {}
        for task in tasks:
            if task.get("split") not in ("train", "validation", "val", "test", "development"):
                raise StopRun("Corpus contains an unknown split")
            if task["root_id"] in root_splits and root_splits[task["root_id"]] != task["split"]:
                raise StopRun("A root group crosses splits")
            root_splits[task["root_id"]] = task["split"]
            solve_reference(task)
        instances = [canonical_instance_key(task) for task in tasks]
        if len(set(instances)) != len(instances):
            raise StopRun("Corpus repeats semantic instances")
        return {"dry_run": True, "network_requests": 0, "paid_requests": 0,
                "tasks": len(tasks), "root_groups": len(set(roots)), "models": list(models),
                "planned_generation_requests": len(tasks) * len(models) * samples,
                "observed_trace_admissions_required": True, "E0": "not_passed",
                "deadline": self.settings.deadline, "budget": self.budget(),
                "credential_present": bool(self.settings.key), "protocol_sha256": self.protocol_digest,
                "source_inventory_sha256": self.source_inventory_digest,
                "verifier_source_sha256": self.verifier_source_digest,
                "corpus_sha256": self.tasks_digest, "price_quote": "not_retrieved_in_dry_run"}

    def plan(self, corpus, models, samples=2):
        """Quote generation reservations using metadata only, without paid calls.

        Embedding inputs do not exist yet. Its headroom is a budget allocation,
        not a promise that both embedders will fit it.
        """
        tasks = corpus["tasks"] if isinstance(corpus, dict) else corpus
        admission_tasks = corpus.get("admission_tasks", []) if isinstance(corpus, dict) else []
        if not tasks or not models or samples < 1:
            raise StopRun("Cannot quote an empty allocation")
        quotes = []
        for model in models:
            allowed = [r for r in self._routes() if r["model"] == model
                       and r.get("protocol_sha256") == self.protocol_digest]
            provider = allowed[0]["provider"] if allowed else None
            price = self.price(model, provider)
            total = Decimal(0)
            admission_total = Decimal(0)
            for task, repeats in [(t, samples) for t in tasks] + [(t, 1) for t in admission_tasks]:
                body = {"model": model, "messages": [{"role": "user", "content": task["prompt"]}],
                        "max_tokens": self.settings.max_tokens, "temperature": self.settings.temperature,
                        "top_p": self.settings.top_p, "seed": 999999999, "stream": False,
                        "reasoning": {"enabled": True}, "include_reasoning": True,
                        "provider": {"order": [" " * 256], "allow_fallbacks": False}}
                # Admission has no pinned route and requires the all-route ceiling.
                is_admission = task in admission_tasks
                amount = estimate(body, self.price(model) if is_admission else price) * repeats
                total += amount
                if is_admission:
                    admission_total += amount
            quotes.append({"model": model, "prompt_rub_per_token": str(price[0]),
                           "completion_rub_per_token": str(price[1]),
                           "generation_and_admission_reservation_envelope_rub": str(total),
                           "admission_reservation_envelope_rub": str(admission_total),
                           "collection_provider": provider,
                           "pricing_rule": "maximum_declared_rate_across_all_time_bands"})
        embedding_quotes = []
        for model in EMBEDDERS:
            try:
                price = self.price(model)
                embedding_quotes.append({"model": model, "prompt_rub_per_token": str(price[0]),
                                         "completion_rub_per_token": str(price[1]), "quote_available": True})
            except StopRun:
                embedding_quotes.append({"model": model, "quote_available": False})
        budget = self.budget()
        total = sum((Decimal(q["generation_and_admission_reservation_envelope_rub"]) for q in quotes), Decimal(0))
        admission_total = sum((Decimal(q["admission_reservation_envelope_rub"]) for q in quotes), Decimal(0))
        result = {"metadata_only": True, "paid_requests": 0, "created_at": utcnow(),
                  "protocol_sha256": self.protocol_digest, "corpus_sha256": self.tasks_digest,
                  "generation_requests": len(tasks) * len(models) * samples,
                  "maximum_admission_requests": len(admission_tasks) * len(models),
                  "quotes": quotes, "embedding_quotes": embedding_quotes,
                  "allocation_envelope_rub": str(total), "budget": budget,
                  "admission_envelope_rub": str(admission_total),
                  "admission_fits_collection_ceiling": Decimal(budget["charged_or_reserved_rub"]) + admission_total <= self.settings.collection_cap,
                  "full_allocation_fits_collection_ceiling": Decimal(budget["charged_or_reserved_rub"]) + total <= self.settings.collection_cap,
                  "embedding_cost": "unknown until observed chunks; headroom is an allocation, not a cost guarantee",
                  "incomplete_blocks": "balanced queue stops before crossing either ceiling; report all exclusions",
                  "currency_contract": "RouterAI rubles per token, matching endpoint pricing_units; other units rejected"}
        self.save(self.state / "pre-dispatch-plan.json", result)
        return result

    def embed(self, records, model, batch_size=32):
        if model not in EMBEDDERS or not 1 <= batch_size <= 128:
            raise ValueError("Invalid embedding model or batch size")
        targets = []
        for record in records:
            if record.get("status") != "completed":
                continue
            segments = chunks(record["text"])
            record.setdefault("embeddings", {})[model] = segments
            targets.extend((record["trace_id"], segment) for segment in segments)
        route_path = self.state / (model.replace("/", "_") + "-embedding-route.json")
        route = read_json(route_path) if route_path.exists() else None
        for offset in range(0, len(targets), batch_size):
            batch = targets[offset:offset + batch_size]
            body = {"model": model, "input": [segment["text"] for _, segment in batch]}
            result = self.paid("embedding", [(trace, s["start"], s["end"]) for trace, s in batch], model, body)
            payload = result["response"].get("json", {})
            inspection = inspect_embeddings(payload, model, len(batch))
            if (result["http_status"] != 200 or not inspection["valid"] or payload.get("model") != model
                    or any(not any(item["embedding"]) for item in payload.get("data", []))):
                raise StopRun("Embedding identity, shape, or response validation failed; no automatic retry")
            provider = payload.get("provider")
            if not isinstance(provider, str) or not provider.strip():
                provider = None
            dimension = len(payload["data"][0]["embedding"])
            observed = {"model": model, "provider": provider, "dimension": dimension}
            if route is None:
                route = {**observed, "first_response_sha256": result["response_sha256"],
                         "provider_identity_verified": provider is not None,
                         "revision": "not_reported_not_inferred"}
                self.save(route_path, route)
            elif any(route.get(key) != value for key, value in observed.items()):
                raise StopRun("Embedding provider or dimension drift; raw attempt retained, no automatic retry")
            for item in sorted(payload["data"], key=lambda d: d["index"]):
                _, segment = batch[item["index"]]
                segment["vector"] = item["embedding"]
                segment["model_id"] = model
                segment["identity_verified"] = True
                segment["input_sha256"] = sha(segment["text"].encode())
                segment["request_sha256"] = result["request_sha256"]
                segment["response_sha256"] = result["response_sha256"]
                segment["provider"] = provider
                segment["provider_identity_verified"] = provider is not None
        output = {"records": records, "embedding_model": model, "word_chunk_size": 16,
                  "max_observed_words": 512, "budget": self.budget(),
                  "protocol_sha256": self.protocol_digest, "embedding_route": route,
                  "scientific_validity": "not_assessed"}
        self.save(self.state / (model.replace("/", "_") + "-embedded.json"), output)
        return output

    def budget(self):
        with self.locked():
            ledger = self._check_ledger()
            return {"cap_rub": str(self.settings.cap), "charged_or_reserved_rub": str(ledger.committed),
                    "collection_cap_rub": str(self.settings.collection_cap),
                    "minimum_embedding_headroom_rub": str(self.settings.cap - self.settings.collection_cap),
                    "remaining_rub": str(self.settings.cap - ledger.committed), "attempts_including_historical": len(ledger.rows),
                    "historical_ledger_sha256": HISTORICAL_SHA}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--catalog", action="store_true")
    commands.add_argument("--admit", type=Path)
    commands.add_argument("--collect", type=Path)
    commands.add_argument("--embed", type=Path)
    commands.add_argument("--budget", action="store_true")
    commands.add_argument("--dry-run", type=Path)
    commands.add_argument("--plan", type=Path, help="Retrieve metadata and quote allocation; no paid requests")
    parser.add_argument("--state", type=Path, default=ROOT / ".research/resumption-2026-11-08")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--models", default=",".join(CANDIDATES))
    parser.add_argument("--embedding-model", choices=EMBEDDERS, default=EMBEDDERS[0])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--collection-cap-rub", type=Decimal, default=Decimal("800"),
                        help="Shared-ledger ceiling for generation/admission, leaving total-cap room for embeddings")
    parser.add_argument("--cap-total-rub", type=Decimal,
                        help="Explicit shared cap; maximum authorized 3000 RUB including historical commitments")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--deadline", help="Absolute timezone-qualified dispatch deadline; default eight hours from first bound command")
    parser.add_argument("--env-file", type=Path, help="Strict KEY=value local file; process environment takes precedence")
    args = parser.parse_args()
    local_env = parse_env(args.env_file) if args.env_file else {}
    settings_env = {**local_env, **os.environ}
    if settings_env.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1") != "https://routerai.ru/api/v1":
        parser.error("Only the prescribed RouterAI URL is supported")
    config = Settings(state=args.state, key=settings_env.get("ROUTERAI_API_KEY", ""),
                      cap=args.cap_total_rub if args.cap_total_rub is not None else Decimal(settings_env.get("RU_MAX_SPEND_RUB", "900")),
                      collection_cap=args.collection_cap_rub,
                      max_tokens=args.max_tokens, concurrency=args.concurrency, timeout=args.timeout,
                      deadline=args.deadline or (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat())
    runner = Runner(config)
    models = tuple(model.strip() for model in args.models.split(",") if model.strip())
    if any(model not in CANDIDATES for model in models):
        parser.error("--models must be selected from the explicit three resumption candidates")
    try:
        if args.catalog:
            result = runner.catalog(models + EMBEDDERS)
        elif args.budget:
            result = runner.budget()
        else:
            if args.protocol is None:
                parser.error("--protocol is required for paid commands")
            corpus = args.admit or args.collect or args.dry_run or args.plan
            runner.bind(args.protocol, corpus)
            if args.dry_run:
                result = runner.dry_run(read_json(args.dry_run), models, args.samples)
            elif args.plan:
                result = runner.plan(read_json(args.plan), models, args.samples)
            elif args.embed:
                document = read_json(args.embed)
                records = document["records"] if isinstance(document, dict) else document
                result = runner.embed(records, args.embedding_model, args.batch_size)
            else:
                document = read_json(corpus)
                tasks = (document.get("admission_tasks", document["tasks"]) if args.admit
                         else document["tasks"]) if isinstance(document, dict) else document
                result = runner.collect(tasks, models, args.samples, bool(args.admit), args.limit)
        # Compact summaries avoid dumping raw text, vectors, or credentials.
        print(json.dumps({key: value for key, value in result.items() if key not in ("records",)}, ensure_ascii=False))
    except StopRun as exc:
        print(json.dumps({"stopped": True, "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
