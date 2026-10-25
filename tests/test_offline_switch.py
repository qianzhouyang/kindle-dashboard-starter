"""Run the actual PW3 event parser against binary input_event recordings."""

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class OfflineSwitchTests(unittest.TestCase):
    def setUp(self):
        if os.name == "nt":
            shell = Path("C:/Program Files/Git/bin/bash.exe")
            self.shell = str(shell) if shell.exists() else None
        else:
            self.shell = shutil.which("sh")
        if not self.shell:
            self.skipTest("Git Bash or a native POSIX shell is required")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def parse(self, events, trailing=b""):
        source = self.directory / "events.bin"
        source.write_bytes(b"".join(
            struct.pack("<IIHHi", 1792680000 + ms // 1000, ms % 1000 * 1000, kind, code, value)
            for ms, kind, code, value in events
        ) + trailing)
        env = dict(os.environ, DASHBOARD_POWER_DEVICE=source.as_posix(),
                   DASHBOARD_RUN_DIR=self.directory.as_posix())
        return subprocess.run([self.shell, (ROOT / "scripts/watch_power.sh").as_posix()],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_short_press_requires_correct_key_and_release(self):
        result = self.parse([(0, 0, 0, 0), (0, 1, 30, 1), (0, 1, 30, 0),
                             (100, 1, 116, 1), (150, 0, 0, 0),
                             (180, 1, 116, 2), (350, 1, 116, 0)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("POWER_SHORT duration_ms=250", result.stdout)

    def test_press_without_release_does_not_restore(self):
        result = self.parse([(0, 1, 116, 1)])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("POWER_SHORT", result.stdout)

    def test_long_press_is_ignored_then_next_short_press_works(self):
        result = self.parse([(0, 1, 116, 1), (3000, 1, 116, 0),
                             (4000, 1, 116, 1), (4200, 1, 116, 0)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("POWER_LONG_IGNORED duration_ms=3000", result.stdout)
        self.assertIn("POWER_SHORT duration_ms=200", result.stdout)

    def test_release_without_press_is_not_a_short_press(self):
        result = self.parse([(100, 1, 116, 0)])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("POWER_SHORT", result.stdout)

    def test_truncated_event_fails_without_restoring_on_random_bytes(self):
        result = self.parse([], trailing=b"1234567")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("short power-button record", result.stdout)
        self.assertFalse(list(self.directory.glob("power-event.*")))

    def test_missing_cache_keeps_native_interface_untouched(self):
        env = dict(os.environ, DASHBOARD_DIR=self.directory.as_posix(),
                   DASHBOARD_RUN_DIR=(self.directory / "run").as_posix(),
                   DASHBOARD_INITCTL="nonexistent-initctl-for-test")
        for mode in ("--start", "--once"):
            result = subprocess.run(
                [self.shell, (ROOT / "scripts/refresh.sh").as_posix(), mode],
                env=env, capture_output=True, text=True, timeout=5,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("nonexistent-initctl", result.stderr)
        self.assertFalse((self.directory / "run/session.pid").exists())

    def test_kual_registration_points_to_packaged_menu_and_actions(self):
        extension = ROOT / "scripts/extensions/dashboard"
        registration = ET.parse(extension / "config.xml")
        menu = extension / registration.findtext("menus/menu")
        actions = json.loads(menu.read_text(encoding="utf-8"))["items"][0]["items"]
        self.assertEqual(len(actions), 3)
        for item in actions:
            self.assertTrue((extension / item["action"]).is_file())
            self.assertTrue(item["exitmenu"])

    def run_failing_session(self, renderer_fails, ui_ready=True, reuse_pid=False):
        directory = self.directory
        runtime = directory / "run"
        runtime.mkdir()
        commands = directory / "bin"
        commands.mkdir()
        shutil.copyfile(ROOT / "scripts/refresh.sh", directory / "refresh.sh")
        (directory / "dashboard.png").write_bytes(b"cached-image")
        sources = {
            "lipc-set-prop": "exit 0\n",
            "lipc-get-prop": 'if [ "$3" = frameworkStarted ]; then echo "$FAKE_UI_READY"; else echo active; fi\n',
            "pidof": '''for name in "$@"; do
case "$name" in awesome) echo 101 ;; cvm) echo 102 ;; esac
done
''',
            "gui-kill": '''printf '%s %s\\n' "$1" "$2" >> "$DASHBOARD_RUN_DIR/signals"
case "$1" in -STOP) state=T ;; -CONT) state=S ;; *) exit 9 ;; esac
sed -i "s/) [ST] /) $state /" "$DASHBOARD_PROC_DIR/$2/stat"
''',
            "timeout": 'shift; exec "$@"\n',
            "initctl": '''case "$1" in
status) printf '%s %s\\n' "$2" "$(cat "$DASHBOARD_RUN_DIR/$2.service")" ;;
start) echo start/running > "$DASHBOARD_RUN_DIR/$2.service" ;;
stop) echo stop/waiting > "$DASHBOARD_RUN_DIR/$2.service" ;;
esac
''',
            "eips": ('''if [ "$1" = -s ]; then
[ "$2" = w=1072,h=1448 ] && [ "$3" = -f ] || exit 8
cp "$DASHBOARD_FB_DEVICE" "$DASHBOARD_RUN_DIR/panel-frame"
exit 0
fi
if [ "$2" = -g ]; then echo dashboard-frame > "$DASHBOARD_FB_DEVICE"; cp "$DASHBOARD_FB_DEVICE" "$DASHBOARD_RUN_DIR/panel-frame"; '''
                     + ('''awk '{$3="S"; $22=99999; print}' "$DASHBOARD_PROC_DIR/101/stat" > "$DASHBOARD_PROC_DIR/101/new"; mv "$DASHBOARD_PROC_DIR/101/new" "$DASHBOARD_PROC_DIR/101/stat"; ''' if reuse_pid else "")
                     +
                     f'exit {7 if renderer_fails else 0}; fi\nexit 0\n'),
        }
        for name, body in sources.items():
            script = commands / name
            script.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
            script.chmod(0o755)
        watcher = directory / "watch_power.sh"
        watcher.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$$" > "$DASHBOARD_RUN_DIR/watcher.ready"\n'
            + ("trap 'exit 0' TERM; while true; do sleep 1; done\n" if renderer_fails
               else "sleep 0.2; exit 7\n"), encoding="utf-8", newline="\n",
        )
        watcher.chmod(0o755)
        processes = directory / "proc"
        for pid, name in ((101, "awesome"), (102, "cvm"), (103, "unrelated")):
            process = processes / str(pid)
            process.mkdir(parents=True)
            fields = [str(pid), f"({name})", "S"] + ["0"] * 18 + [str(pid * 100)]
            (process / "stat").write_text(" ".join(fields) + "\n")
        framebuffer = directory / "fb0"
        framebuffer.write_bytes(b"original-native-reading-frame")
        for service in ("x", "lab126_gui"):
            (runtime / f"{service}.service").write_text("start/running\n")
        env = dict(os.environ, DASHBOARD_DIR=directory.as_posix(),
                   DASHBOARD_RUN_DIR=runtime.as_posix(), TEST_BIN=commands.as_posix(),
                   FAKE_UI_READY="1" if ui_ready else "0",
                   DASHBOARD_PROC_DIR=processes.as_posix(), DASHBOARD_GUI_NAMES="awesome cvm",
                   DASHBOARD_GUI_KILL=(commands / "gui-kill").as_posix(),
                   DASHBOARD_FB_DEVICE=framebuffer.as_posix(),
                   TEST_SCRIPT=(directory / "refresh.sh").as_posix(),
                   DASHBOARD_INITCTL=(commands / "initctl").as_posix(),
                   DASHBOARD_EIPS=(commands / "eips").as_posix())
        path_setup = 'TEST_BIN="$(cygpath -u "$TEST_BIN")"; ' if os.name == "nt" else ""
        result = subprocess.run(
            [self.shell, "-c", path_setup + 'PATH="$TEST_BIN:$PATH"; export PATH; exec sh "$TEST_SCRIPT" --worker offline'],
            env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((runtime / "state").read_text().strip(), "ERROR")
        self.assertFalse((runtime / "session.pid").exists())
        self.assertFalse((runtime / "session.lock").exists())
        for service in ("x", "lab126_gui"):
            self.assertEqual((runtime / f"{service}.service").read_text().strip(), "start/running")
        log = (directory / "refresh.log").read_text()
        if ui_ready:
            self.assertIn("Rendering", log)
            if reuse_pid:
                self.assertNotIn("Native GUI restored", log)
                self.assertIn("saved GUI process 101 no longer exists", log)
            else:
                self.assertIn("Native GUI restored", log)
            self.assertEqual(framebuffer.read_bytes(), b"original-native-reading-frame")
            # Memory restoration alone leaves the E-Ink panel showing the dashboard.
            self.assertEqual((runtime / "panel-frame").read_bytes(), b"original-native-reading-frame")
            self.assertEqual((runtime / "signals").read_text().splitlines(),
                             ["-STOP 101", "-STOP 102"] + ([] if reuse_pid else ["-CONT 101"]) + ["-CONT 102"])
        else:
            self.assertNotIn("Rendering", log)
            self.assertFalse((runtime / "signals").exists())
        self.assertEqual((processes / "103/stat").read_text().split()[2], "S")
        self.assertEqual((runtime / "gui-paused").exists(), reuse_pid)
        self.assertEqual((runtime / "native-framebuffer.bin").exists(), reuse_pid)

    def test_render_failure_restores_native_services_and_clears_session(self):
        self.run_failing_session(renderer_fails=True)

    def test_unexpected_listener_exit_restores_native_services(self):
        self.run_failing_session(renderer_fails=False)

    def test_unready_native_ui_is_not_paused_or_reported_as_success(self):
        self.run_failing_session(renderer_fails=True, ui_ready=False)

    def test_reused_process_id_is_never_resumed(self):
        self.run_failing_session(renderer_fails=True, reuse_pid=True)


if __name__ == "__main__":
    unittest.main()
