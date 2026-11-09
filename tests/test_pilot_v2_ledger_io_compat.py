"""Post-data I/O compatibility tests; original collector bytes stay frozen."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from resumption.runner import Runner
from scripts.pilot_v2_ledger_io_compat_v1 import (
    CooperativeLedgerIOMixin, LedgerIOCompatibilityError, SOURCE_PATH, VERSION,
)
from stage0.runner import Ledger, encode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pilot_v2_recovery as recovery_fixtures


class TestBase:
    def __init__(self, state):
        self.state = state
        self.scope = state / "scope"
        self.ledger_path = state / "ledger.json"
        self.protocol = {}
        self.os_lock_entries = 0
        self.paid_invocations = 0
        self.ledger_path.write_bytes(encode([]))

    @contextmanager
    def locked(self):
        with Runner.locked(self):
            self.os_lock_entries += 1
            yield

    def _read_retained_ledger(self):
        return Ledger(self.ledger_path, Decimal(3000))

    def _check_ledger(self):
        return Ledger(self.ledger_path, Decimal(3000))

    def paid_cell(self, cell):
        self.paid_invocations += 1
        return cell


class SafeTestRunner(CooperativeLedgerIOMixin, TestBase):
    pass


class LedgerIOCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runner = SafeTestRunner(Path(self.temporary.name))

    def test_owner_reentry_uses_one_os_lock_and_releases_after_exception(self):
        with self.runner.locked():
            with self.runner.locked():
                self.assertEqual(self.runner._read_retained_ledger().rows, [])
                self.assertEqual(self.runner._check_ledger().rows, [])
        self.assertEqual(self.runner.os_lock_entries, 1)
        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            with self.runner.locked():
                with self.runner.locked():
                    raise RuntimeError("fixture failure")
        with self.runner.locked():
            pass
        self.assertEqual(self.runner.os_lock_entries, 3)

    def test_reader_blocks_atomic_writer_until_its_file_handle_is_closed(self):
        opened, release, writer_started, writer_entered = (threading.Event() for _ in range(4))
        original = Path.read_text
        def held_read(path, *args, **kwargs):
            if path == self.runner.ledger_path and threading.current_thread().name == "compat-reader":
                with path.open("r", encoding="utf-8") as source:
                    opened.set()
                    if not release.wait(3):
                        raise RuntimeError("Reader release timeout")
                    return source.read()
            return original(path, *args, **kwargs)
        def reader():
            threading.current_thread().name = "compat-reader"
            return self.runner._read_retained_ledger().rows
        def writer():
            writer_started.set()
            with self.runner.locked():
                writer_entered.set()
                ledger = self.runner._read_retained_ledger()
                ledger.reserve(Decimal(".01"), "synthetic-sharing-test")
        with patch.object(Path, "read_text", held_read), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(reader)
            self.assertTrue(opened.wait(2))
            second = pool.submit(writer)
            self.assertTrue(writer_started.wait(2))
            try:
                self.assertFalse(writer_entered.wait(.15))
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3), [])
            second.result(timeout=3)
        self.assertTrue(writer_entered.is_set())
        self.assertEqual(len(self.runner._read_retained_ledger().rows), 1)

    def test_current_live_protocol_is_refused_and_future_binding_is_exact(self):
        self.runner.protocol = {"status": "prospective_frozen_provider_recovery"}
        with self.assertRaisesRegex(LedgerIOCompatibilityError, "new protocol"):
            self.runner.paid_cell({"call": "synthetic"})
        self.assertEqual(self.runner.paid_invocations, 0)
        digest = hashlib.sha256((ROOT / SOURCE_PATH).read_bytes()).hexdigest()
        self.runner.protocol["execution_io_compatibility"] = {"version": VERSION, "path": SOURCE_PATH, "sha256": digest}
        self.runner.scope.mkdir()
        inventory = self.runner.scope / "source-inventory.json"
        inventory.write_bytes(encode({"files": {SOURCE_PATH: "0" * 64}}))
        with self.assertRaises(LedgerIOCompatibilityError):
            self.runner.paid_cell({"call": "synthetic"})
        inventory.write_bytes(encode({"files": {SOURCE_PATH: digest}}))
        with self.assertRaises(LedgerIOCompatibilityError):
            self.runner.paid_cell({"call": "synthetic"})
        snapshot = self.runner.scope / "source" / SOURCE_PATH
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes((ROOT / SOURCE_PATH).read_bytes())
        self.assertEqual(self.runner.paid_cell({"call": "synthetic"}), {"call": "synthetic"})
        self.assertEqual(self.runner.paid_invocations, 1)

    @unittest.skipUnless(os.name == "nt", "Native Windows sharing contract")
    def test_windows_handle_without_delete_sharing_reproduces_replace_failure(self):
        import ctypes
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                           ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes, close.restype = [ctypes.c_void_p], ctypes.c_int
        handle = create(str(self.runner.ledger_path), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            ledger = Ledger(self.runner.ledger_path, Decimal(3000))
            with self.assertRaises(PermissionError):
                ledger.flush()
        finally:
            close(handle)
        ledger.flush()
        self.assertEqual(self.runner.ledger_path.read_bytes(), encode([]))


class CompatibleRecoveryRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = recovery_fixtures.RecoveryTests()
        cls.fixture.setUp()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def test_requests_labels_raw_bytes_and_unknown_cache_are_unchanged(self):
        # Deliberately bypass the synthetic factory: this is the untouched
        # measured class, compared against the new I/O-only adapter below.
        original = recovery_fixtures.RecoveryRunner(
            recovery_fixtures.Settings(state=self.fixture.state, key="fixture-key",
                cap=Decimal(3000), collection_cap=Decimal(3000)),
            self.fixture.r_path, self.fixture.tasks_path, self.fixture.recovery_transport,
            project=self.fixture.project, execute=True,
            fixture_verifier=recovery_fixtures.fixtures.fixture_grade)
        original.preflight()
        observed = []
        for mode, cell in zip(("stop", "length"), original.new_cells[:2]):
            self.fixture.akash_mode = mode
            observed.append(original.execute_cell(cell))
        paths = [original.calls / row["trace_id"] / name for row in observed
                 for name in ("request.json", "reservation.json", "response.json", "result.json", "trace.json")]
        before = {str(path): path.read_bytes() for path in paths}
        ledger = original.ledger_path.read_bytes()
        count = len(self.fixture.akash_paid)
        class CompatibleRecovery(CooperativeLedgerIOMixin, recovery_fixtures.RecoveryRunner):
            pass
        safe = CompatibleRecovery(original.settings, self.fixture.r_path, self.fixture.tasks_path,
            self.fixture.recovery_transport, project=self.fixture.project, execute=True,
            fixture_verifier=recovery_fixtures.fixtures.fixture_grade)
        for cell, row in zip(safe.new_cells[:2], observed):
            self.assertEqual(safe.body(cell), original.body(cell))
            replayed = safe.execute_cell(cell)
            self.assertEqual({key: value for key, value in row.items() if key != "reused_record_without_resend"},
                             {key: value for key, value in replayed.items() if key != "reused_record_without_resend"})
        self.assertEqual(len(self.fixture.akash_paid), count)
        self.assertEqual(safe.ledger_path.read_bytes(), ledger)
        self.assertEqual(before, {str(path): path.read_bytes() for path in paths})
        safe.preflight()
        self.fixture.akash_mode = "unknown"
        cell = safe.new_cells[2]
        self.assertEqual(safe.body(cell), original.body(cell))
        unknown = safe.execute_cell(cell)
        count = len(self.fixture.akash_paid)
        ledger = safe.ledger_path.read_bytes()
        cached = safe.execute_cell(cell)
        self.assertEqual(unknown["request_state"], "unknown")
        self.assertIsNone(unknown["correct"])
        self.assertEqual(cached["request_state"], "unknown")
        self.assertEqual(len(self.fixture.akash_paid), count)
        self.assertEqual(safe.ledger_path.read_bytes(), ledger)


if __name__ == "__main__":
    unittest.main()
