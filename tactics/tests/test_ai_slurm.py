"""Local shell guards and mocked submission; never invoke a real scheduler."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SlurmTests(unittest.TestCase):
    def test_shell_syntax_and_login_host_guards(self):
        for name in ("ai_smoke.sh", "ai_full.sh", "ai_submit_full.sh"):
            result = subprocess.run(["bash", "-n", str(ROOT / "slurm" / name)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        env = {k: v for k, v in os.environ.items() if not k.startswith("SLURM_")}
        for name in ("ai_smoke.sh", "ai_full.sh"):
            result = subprocess.run(["bash", str(ROOT / "slurm" / name)], env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to run outside SLURM", result.stderr)

    def test_submission_dependencies_and_all_task_ids_with_fake_scheduler(self):
        with tempfile.TemporaryDirectory(prefix="ai-shell-") as scratch:
            target = Path(scratch)
            (target / "slurm").mkdir()
            (target / "bin").mkdir()
            shutil.copyfile(ROOT / "slurm" / "ai_submit_full.sh", target / "slurm" / "ai_submit_full.sh")
            fake = target / "bin" / "sbatch"
            fake.write_text("#!/bin/bash\n"
                            "n=100; if [ -f \"$AI_TEST_COUNTER\" ]; then read -r n < \"$AI_TEST_COUNTER\"; fi\n"
                            "n=$((n+1)); printf '%s\\n' \"$n\" > \"$AI_TEST_COUNTER\"\n"
                            "printf '%s %s\\n' \"${AI_PHASE:-smoke}\" \"$*\" >> \"$AI_TEST_CALLS\"\n"
                            "printf '%s;mock-cluster\\n' \"$n\"\n")
            fake.chmod(0o755)
            env = dict(os.environ, AI_TACT=str(target), AI_COMPACT="/approved/compact",
                       AI_TEST_COUNTER=str(target / "counter"), AI_TEST_CALLS=str(target / "calls"),
                       PATH=str(target / "bin") + os.pathsep + os.environ.get("PATH", ""))
            env.pop("AI_PHASE", None)
            result = subprocess.run(["bash", str(target / "slurm" / "ai_submit_full.sh")],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (target / "calls").read_text().splitlines()
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[0], "smoke --parsable slurm/ai_smoke.sh")
            self.assertIn("diagnose --parsable --dependency=afterok:101", calls[1])
            self.assertIn("full --parsable --dependency=afterok:102 --array=0-59%4", calls[2])
            self.assertEqual(result.stdout.count("Full task ID:"), 60)
            self.assertIn("Full task ID: 103_59", result.stdout)
            # A forbidden explicit holdout path must not reach the scheduler.
            (target / "calls").unlink()
            env["AI_COMPACT"] = "/approved/rlcs-2026/compact"
            result = subprocess.run(["bash", str(target / "slurm" / "ai_submit_full.sh")],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "calls").exists())

    def test_invalid_array_index_rejected_before_environment_or_inputs(self):
        env = dict(os.environ, SLURM_JOB_ID="synthetic-test", SLURM_SUBMIT_DIR="/not-opened",
                   SLURM_ARRAY_TASK_ID="60", TMPDIR="/not-opened", AI_COMPACT="/not-opened",
                   AI_PHASE="full")
        result = subprocess.run(["bash", str(ROOT / "slurm" / "ai_full.sh")], env=env,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Array index must be in 0..59", result.stderr)


if __name__ == "__main__":
    unittest.main()
