"""CLI refusal, synthetic staging and operational-budget failure reporting."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from .fixture import make_fixture


ROOT = Path(__file__).resolve().parents[3]


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pilot-cli-")
        cls.fixture = make_fixture(Path(cls.temporary.name) / "compact")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self, *arguments, overrides=None):
        environment = dict(os.environ)
        environment.pop("SLURM_JOB_ID", None)
        environment.pop("PILOT_START_EPOCH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(ROOT / "src") + (
            os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
        )
        environment.update(overrides or {})
        return subprocess.run([sys.executable, "-B", "-m", "pilot_encoder", *map(str, arguments)],
                              cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30)

    def test_production_refuses_without_slurm_before_opening_nonexistent_data(self):
        with tempfile.TemporaryDirectory(prefix="pilot-refusal-") as temporary:
            out = Path(temporary) / "result.json"
            result = self.invoke("--compact", Path(temporary) / "does-not-exist", "--out", out)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must run inside SLURM", result.stderr)
            self.assertNotIn("FileNotFoundError", result.stderr)
            self.assertFalse(out.exists())

    def test_synthetic_staging_writes_report_and_omits_poison(self):
        with tempfile.TemporaryDirectory(prefix="pilot-cli-stage-") as temporary:
            out, staged = Path(temporary) / "stage.json", Path(temporary) / "compact"
            result = self.invoke("--synthetic-smoke", "--device", "cpu", "--compact", self.fixture,
                                 "--stage-to", staged, "--out", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["status"], "staged")
            self.assertTrue(report["synthetic"])
            self.assertFalse(report["pass_decision"])
            self.assertFalse(report["test_opened"])
            self.assertEqual(report["staging"]["replays"], 160)
            self.assertFalse((staged / "rlcs-2026").exists())

    def test_expired_budget_writes_failure_json_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory(prefix="pilot-cli-expired-") as temporary:
            out = Path(temporary) / "expired.json"
            result = self.invoke("--synthetic-smoke", "--device", "cpu", "--compact", self.fixture,
                                 "--out", out, overrides={"PILOT_START_EPOCH": "0"})
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertFalse(report["pass_decision"])
            self.assertFalse(report["test_opened"])
            self.assertEqual(report["error"]["type"], "TimeoutError")
            self.assertIn("budget", report["error"]["message"])


if __name__ == "__main__":
    unittest.main()
