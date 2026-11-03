"""Opt-in protection traces cannot serialize credentials or conversation data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.protection_trace import (  # noqa: E402
    TRACE_DIRECTORY_ENV,
    ProtectionTrace,
    protection_trace_from_environment,
)


class ProtectionTraceTests(unittest.TestCase):
    def test_app_milestones_keep_only_status_enums_and_exception_class(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = ProtectionTrace(Path(directory))
            self.addCleanup(trace.close)
            trace(
                {
                    "event": "key_result",
                    "auth_status": "pin_choice_required",
                    "same_key_view": True,
                    "setup_token_present": True,
                    "message": "synthetic sensitive value",
                    "api_key": "synthetic sensitive value",
                }
            )
            trace(
                {
                    "event": "pin_setup_failed",
                    "exception_class": "TypeError",
                    "error": "synthetic sensitive value",
                }
            )
            trace(
                {
                    "event": "system_event",
                    "system_reason": "synthetic sensitive value",
                    "auth_status": "synthetic sensitive value",
                    "exception_class": "synthetic sensitive value",
                }
            )
            text = trace.path.read_text()
            records = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(records[1]["auth_status"], "pin_choice_required")
            self.assertTrue(records[1]["setup_token_present"])
            self.assertEqual(records[2]["exception_class"], "TypeError")
            self.assertEqual(set(records[3]), {"event", "seconds"})
            self.assertNotIn("synthetic sensitive value", text)

    def test_only_typed_allowlisted_metadata_reaches_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = ProtectionTrace(Path(directory))
            self.addCleanup(trace.close)
            trace(
                {
                    "event": "normal_reaction",
                    "test": 3,
                    "generation": 1,
                    "reason": "normal_seal_failed",
                    "data_open": False,
                    "pin_visible": True,
                    "api_key": "synthetic sensitive value",
                    "pin": "synthetic sensitive value",
                    "draft": "synthetic sensitive value",
                    "source": "synthetic sensitive value",
                    "session_open": "synthetic sensitive value",
                    "app_generation": True,
                }
            )
            trace({"event": "synthetic sensitive value"})
            trace({"event": "screen_finished", "reason": "synthetic sensitive value"})
            records = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[1]["test"], 3)
            self.assertTrue(records[1]["pin_visible"])
            self.assertFalse(records[1]["data_open"])
            self.assertNotIn("synthetic sensitive value", trace.path.read_text())
            self.assertNotIn("session_open", records[1])
            self.assertNotIn("app_generation", records[1])
            self.assertEqual(trace.path.stat().st_mode & 0o777, 0o600)

    def test_absent_opt_in_creates_nothing_and_invalid_directory_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {TRACE_DIRECTORY_ENV: ""}):
                self.assertIsNone(protection_trace_from_environment())
            self.assertEqual(list(Path(directory).iterdir()), [])
            Path(directory).chmod(0o755)
            with patch.dict(os.environ, {TRACE_DIRECTORY_ENV: directory}):
                self.assertIsNone(protection_trace_from_environment())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_symlink_directory_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "target"
            target.mkdir(mode=0o700)
            link = parent / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                ProtectionTrace(link)
            self.assertEqual(list(target.iterdir()), [])

    def test_trace_size_is_bounded_and_closed_writer_is_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = ProtectionTrace(Path(directory))
            with patch("platform_security.protection_trace._MAX_BYTES", 256):
                for _ in range(20):
                    trace({"event": "app_state", "data_open": False})
            before = trace.path.read_bytes()
            trace.close()
            trace({"event": "closed"})
            self.assertLessEqual(len(before), 256)
            self.assertEqual(trace.path.read_bytes(), before)
