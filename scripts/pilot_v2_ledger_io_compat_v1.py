"""Post-data cooperative ledger I/O adapter, never part of measured A or R1.

The original Windows CI exposed an unlocked retained-ledger reader racing an
atomic ledger replacement. This mixin coordinates readers and writers through
the existing thread/OS budget lock and adds owner-thread reentry. It changes no
request, grading, reservation or retry policy.

Current production protocols do not authorize this adapter. Synthetic fixtures
may use it; any future live adapter must freeze this file in its own inventory
and bind its exact hash in a new execution_io_compatibility protocol section.
All participating processes must use cooperative reads. External programs or
unmodified collectors can still hold Windows handles without delete sharing.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import threading

from resumption.runner import _THREAD_LOCK
from stage0.runner import StopRun


VERSION = "pilot-v2-ledger-read-compat-v1"
SOURCE_PATH = "scripts/pilot_v2_ledger_io_compat_v1.py"
_OWNED = threading.local()


class LedgerIOCompatibilityError(StopRun):
    pass


class CooperativeLedgerIOMixin:
    """Place before the frozen runner in a new, explicitly bound adapter MRO."""

    @contextmanager
    def locked(self):
        # The same global RLock also coordinates inherited writers. A single
        # owner acquires the OS lock once even when inherited code nests reads.
        key = os.path.normcase(str(Path(self.state).resolve(strict=True)))
        with _THREAD_LOCK:
            owned = getattr(_OWNED, "states", None)
            if owned is None:
                owned = _OWNED.states = {}
            if key in owned:
                owned[key] += 1
                try:
                    yield
                finally:
                    owned[key] -= 1
                return
            with super().locked():
                owned[key] = 1
                try:
                    yield
                finally:
                    del owned[key]

    def _read_retained_ledger(self):
        with self.locked():
            return super()._read_retained_ledger()

    def _check_ledger(self):
        with self.locked():
            return super()._check_ledger()

    def _authorize_io_compatibility(self):
        protocol = getattr(self, "protocol", {})
        if protocol.get("synthetic_fixture") is True:
            return
        digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        expected = {"version": VERSION, "path": SOURCE_PATH, "sha256": digest}
        inventory_path = Path(self.scope) / "source-inventory.json"
        # Import only the stdlib parser. Never amend an existing frozen closure.
        import json
        inventory = json.loads(inventory_path.read_bytes()) if inventory_path.is_file() else {}
        snapshot = Path(self.scope) / "source" / SOURCE_PATH
        if (protocol.get("execution_io_compatibility") != expected
                or inventory.get("files", {}).get(SOURCE_PATH) != digest
                or not snapshot.is_file() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != digest):
            raise LedgerIOCompatibilityError(
                "Ledger I/O compatibility requires a new protocol and exact frozen source binding; "
                "measured A/R1 protocols are not authorized")

    def paid_cell(self, cell):
        self._authorize_io_compatibility()
        return super().paid_cell(cell)
