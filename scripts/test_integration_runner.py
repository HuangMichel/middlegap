"""Behavior checks for verification isolation, failures and process cleanup."""

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from verify_integration import REPO, Processes, isolated_environment, wait_ready


class IntegrationRunnerTests(unittest.TestCase):
    def test_child_environment_excludes_live_service_configuration(self):
        source = {
            "PATH": os.environ.get("PATH", ""),
            "DATABASE_URL": "private-placeholder",
            "APP_MODE": "obsolete",
            "SUPABASE_SERVICE_ROLE_KEY": "private-placeholder",
            "MISTRAL_API_KEY": "private-placeholder",
            "NEXT_PUBLIC_API_URL": "https://production.invalid",
            "GOOGLE_DRIVE_MCP_TOKEN": "private-placeholder",
            "IMANAGE_MCP_URL": "https://production.invalid",
            "PYTHONPATH": "/unexpected/imports",
            "PYTHONOPTIMIZE": "1",
        }
        with patch.dict(os.environ, source, clear=True):
            environment = isolated_environment()
        self.assertEqual(environment, {"PATH": source["PATH"], "PYTHONUNBUFFERED": "1"})

    def test_failed_check_is_reported_and_running_children_are_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            processes = Processes(root, isolated_environment())
            child = processes.start("worker", [sys.executable, "-c", "import time; time.sleep(30)"], root)
            try:
                with self.assertRaisesRegex(RuntimeError, "exited with status 3"):
                    processes.run("broken", [sys.executable, "-c", "raise SystemExit(3)"], root)
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    processes.run("hung", [sys.executable, "-c", "import time; time.sleep(30)"], root, timeout=0.05)
            finally:
                processes.close()
            self.assertIsNotNone(child.poll())
            self.assertTrue((root / "broken.log").exists())

    def test_normal_api_endpoint_is_refused(self):
        process = unittest.mock.Mock(spec=subprocess.Popen)
        process.poll.return_value = None
        response = io.BytesIO(json.dumps({"status": "ok"}).encode())
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "production API endpoint"):
                wait_ready("http://127.0.0.1:8000/health", process, harness=True)

    @unittest.skipUnless(os.name == "posix", "Process groups require POSIX")
    def test_descendants_are_killed_even_if_parent_already_exited(self):
        with tempfile.TemporaryDirectory() as temporary:
            processes = Processes(Path(temporary), isolated_environment())
            parent = unittest.mock.Mock(spec=subprocess.Popen)
            parent.pid = 12345
            parent.poll.return_value = 0
            parent.wait.return_value = 0
            processes.children.append(parent)
            with patch("os.killpg") as kill:
                processes.close()
            kill.assert_has_calls([
                unittest.mock.call(12345, signal.SIGTERM),
                unittest.mock.call(12345, signal.SIGKILL),
            ])

    def test_optimized_python_cannot_report_unchecked_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-O", str(REPO / "scripts/verify_integration.py"),
                 "--transport", "in-process", "--artifacts", temporary],
                env=isolated_environment(), capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            records = list(Path(temporary).glob("run-*/verification.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertEqual(record["status"], "failed")
            self.assertIn("requires Python assertions", record["error"])


if __name__ == "__main__":
    unittest.main()
