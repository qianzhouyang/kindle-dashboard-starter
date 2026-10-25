"""Regression checks for SSH waiting, failure propagation and listener reuse."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import web_console
from http_harness import MockDeviceCase


class RemoteShellTests(unittest.TestCase):
    def setUp(self):
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        # Do not pick WindowsApps/System32 bash aliases, which invoke WSL.
        if os.name == "nt":
            self.shell = str(git_bash) if git_bash.exists() else None
        else:
            self.shell = shutil.which("sh") or shutil.which("bash")
        if not self.shell:
            self.skipTest("POSIX shell is required (Git Bash works on Windows)")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def command(self, refresh_body):
        refresh = self.root / "refresh.sh"
        watcher = self.root / "watch_power.sh"
        refresh.write_text("#!/bin/sh\n" + refresh_body + "\n", encoding="utf-8", newline="\n")
        watcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
        refresh.chmod(0o755)
        watcher.chmod(0o755)
        command = web_console.DASHBOARD_REFRESH_COMMAND.replace(
            "/mnt/us/dashboard/refresh.sh", shlex.quote(refresh.as_posix())
        ).replace("/mnt/us/dashboard/watch_power.sh", shlex.quote(watcher.as_posix()))
        return command

    def run_shell(self, command):
        return subprocess.run(
            [self.shell, "-c", command], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )

    def test_ssh_shell_waits_until_render_completes(self):
        marker = self.root / "rendered"
        command = self.command(f"sleep 1; touch {shlex.quote(marker.as_posix())}")
        started = time.monotonic()
        result = self.run_shell(command)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(marker.exists(), "SSH must not report success before render finishes")
        self.assertGreaterEqual(time.monotonic() - started, 0.9)

    def test_failed_refresh_is_not_reported_as_success(self):
        self.assertEqual(self.run_shell(self.command("exit 7")).returncode, 7)

class ConsoleResultTests(MockDeviceCase):
    @patch.object(web_console.subprocess, "run")
    def test_restore_allows_real_device_startup_time(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "restored", "")
        self.assertTrue(web_console.trigger_ssh_restore()[0])
        self.assertGreaterEqual(run.call_args.kwargs["timeout"], 30)
        self.assertIn("BatchMode=yes", run.call_args.args[0])

    @patch.object(web_console.subprocess, "run")
    def test_restore_timeout_is_not_success(self, run):
        run.side_effect = subprocess.TimeoutExpired("ssh", 45)
        self.assertFalse(web_console.trigger_ssh_restore()[0])

    @patch.object(web_console, "generate_image_bytes", return_value=b"test-image")
    @patch.object(web_console.subprocess, "run")
    def test_push_waits_and_reports_refresh_failure(self, run, render):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "1", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 7, "", "refresh failed"),
        ]
        ok, message = web_console.trigger_ssh_refresh({})
        self.assertFalse(ok)
        self.assertIn("refresh failed", message)
        self.assertGreaterEqual(run.call_args.kwargs["timeout"], 30)
        temporary_image = run.call_args_list[1].args[0][-2]
        self.assertFalse(os.path.exists(temporary_image))


if __name__ == "__main__":
    unittest.main()
