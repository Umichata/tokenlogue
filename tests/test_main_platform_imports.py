"""Importing the real Android entrypoint never imports Linux-only modules."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class MainPlatformImportTests(unittest.TestCase):
    def test_android_available_modules_import_real_entrypoint_without_linux(self):
        source = Path(__file__).resolve().parents[1] / "src"
        probe = """
import importlib.abc
import json
import sys

sys.path.insert(0, sys.argv[1])
blocked = []

class AndroidModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"grp", "pwd"} or fullname.startswith("platform_security.linux_"):
            blocked.append(fullname)
            raise ModuleNotFoundError("Linux module unavailable on Android", name=fullname)
        return None

for name in ("grp", "pwd"):
    sys.modules.pop(name, None)
sys.meta_path.insert(0, AndroidModules())
import main
assert callable(main.main)
assert callable(main.start_linux_session_watch)
assert not blocked, blocked
assert not any(name.startswith("platform_security.linux_") for name in sys.modules)
print(json.dumps({"entrypoint_imported": True, "linux_modules_loaded": False}))
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", probe, str(source)],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"entrypoint_imported": True, "linux_modules_loaded": False},
        )
