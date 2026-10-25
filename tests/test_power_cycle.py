"""Exercise the real cycle/cleanup functions with separate RF, cache and panel state."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def png(width=1072, height=1448):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff' * width) * height)) + chunk(b'IEND', b''))


class PowerCycleTests(unittest.TestCase):
    def setUp(self):
        self.shell = str(Path('C:/Program Files/Git/bin/bash.exe')) if os.name == 'nt' else shutil.which('sh')
        if not self.shell or not Path(self.shell).exists():
            self.skipTest('Git Bash or POSIX shell required')
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for name in ('run', 'bin', 'net/usb0'):
            (self.dir / name).mkdir(parents=True)
        (self.dir / 'radio').write_text('1\n'); (self.dir / 'wifi').write_text('1\n')
        (self.dir / 'alarm').write_text(''); (self.dir / 'power').write_text('awake')
        (self.dir / 'clock').write_text('1000\n')
        (self.dir / 'net/usb0/carrier').write_text('0\n')
        (self.dir / 'new.png').write_bytes(png())
        (self.dir / 'dashboard.png').write_bytes(b'old-valid-cache')
        commands = {
            'lipc-get-prop': '''case "$1:$2" in
com.lab126.cmd:wirelessEnable) cat "$TEST_DIR/radio" ;;
com.lab126.wifid:enable) cat "$TEST_DIR/wifi" ;;
com.lab126.wifid:cmState) echo CONNECTED ;;
com.lab126.powerd:isCharging) echo "${TEST_CHARGING:-0}" ;;
*) exit 8 ;; esac
''',
            'lipc-set-prop': '''[ "$1" = -i ] && shift
case "$1:$2" in
com.lab126.cmd:wirelessEnable) echo "$3" > "$TEST_DIR/radio" ;;
com.lab126.wifid:enable) echo "$3" > "$TEST_DIR/wifi" ;;
*) exit 8 ;; esac
''',
            'curl': '''while [ "$#" -gt 0 ]; do
if [ "$1" = -o ]; then shift; destination=$1; fi
shift; done
echo partial > "$destination"
[ "${TEST_CURL_FAIL:-0}" != 1 ] || exit 22
cp "$TEST_DIR/new.png" "$destination"
''',
            'sleep': '''echo "$1" >> "$TEST_DIR/sleeps"
if [ "$(cat "$TEST_DIR/power")" = mem ] && [ "${TEST_EARLY_WAKE:-0}" != 1 ]; then
 cat "$TEST_DIR/alarm" > "$TEST_DIR/clock"
fi
''',
            'date': '''if [ "$1" = +%s ]; then cat "$TEST_DIR/clock"; else exec /bin/date "$@"; fi
''',
            'sync': 'exit 0\n',
        }
        for name, body in commands.items():
            path = self.dir / 'bin' / name
            path.write_text('#!/bin/sh\n' + body, encoding='utf-8', newline='\n'); path.chmod(0o755)

    def run_case(self, body, **extra):
        env = dict(os.environ, TEST_DIR=self.dir.as_posix(),
                   TEST_BIN=(self.dir / 'bin').as_posix(),
                   POWER_HELPER=(ROOT / 'scripts/power-cycle.sh').as_posix(),
                   DASHBOARD_RTC_ALARM=(self.dir / 'alarm').as_posix(),
                   DASHBOARD_POWER_STATE=(self.dir / 'power').as_posix(),
                   DASHBOARD_NET_SYS=(self.dir / 'net').as_posix(), **extra)
        setup = 'TEST_BIN="$(cygpath -u "$TEST_BIN")"; ' if os.name == 'nt' else ''
        script = setup + '''PATH="$TEST_BIN:$PATH"; export PATH
DASHBOARD_DIR=$TEST_DIR RUN_DIR="$TEST_DIR/run" LOG_PATH="$TEST_DIR/log"
IMAGE_PATH="$TEST_DIR/dashboard.png" JOB_PID= interval=30 url=http://example.invalid/image.png
log() { echo "$*" >> "$LOG_PATH"; }
render_image() {
 [ "$(cat "$TEST_DIR/radio")" = 0 ] && [ "$(cat "$TEST_DIR/wifi")" = 0 ] || return 9
 cp "${1:-$IMAGE_PATH}" "$TEST_DIR/panel"
}
. "$POWER_HELPER"
''' + body
        return subprocess.run([self.shell, '-c', script], env=env, capture_output=True, text=True, timeout=8)

    def test_download_turns_radio_off_before_render_and_restores_original_on_exit(self):
        result = self.run_case('printf "1\\n1\\n" > "$NET_SAVED"; network_cycle && network_cleanup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'dashboard.png').read_bytes(), png())
        self.assertEqual((self.dir / 'panel').read_bytes(), png())
        self.assertEqual((self.dir / 'radio').read_text().strip(), '1')
        self.assertFalse((self.dir / 'run/network-state').exists())
        log = (self.dir / 'log').read_text()
        self.assertLess(log.index('FETCH_OK'), log.index('WIFI_DISABLED'))
        self.assertLess(log.index('WIFI_DISABLED'), log.index('CYCLE_RENDERED'))

    def test_bad_dimensions_preserve_cache_and_turn_wifi_off(self):
        (self.dir / 'new.png').write_bytes(png(100, 100))
        result = self.run_case('network_cycle')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'dashboard.png').read_bytes(), b'old-valid-cache')
        self.assertEqual((self.dir / 'wifi').read_text().strip(), '0')
        self.assertFalse((self.dir / 'panel').exists())

    def test_failed_fetch_discards_partial_download_and_turns_wifi_off(self):
        result = self.run_case('network_cycle', TEST_CURL_FAIL='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'dashboard.png').read_bytes(), b'old-valid-cache')
        self.assertEqual((self.dir / 'radio').read_text().strip(), '0')
        self.assertFalse(list(self.dir.glob('download.*.png')))

    def test_connection_timeout_keeps_cache_and_turns_wifi_off(self):
        result = self.run_case('network_cycle', DASHBOARD_WIFI_WAIT='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WIFI_TIMEOUT', (self.dir / 'log').read_text())
        self.assertEqual((self.dir / 'wifi').read_text().strip(), '0')

    def test_cleanup_cancels_own_alarm(self):
        (self.dir / 'alarm').write_text('12345\n'); (self.dir / 'run/rtc-owned').write_text('12345\n')
        result = self.run_case('network_cleanup && network_cleanup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'alarm').read_text().strip(), '0')
        self.assertFalse((self.dir / 'run/rtc-owned').exists())

    def test_cleanup_leaves_another_owners_alarm_untouched(self):
        (self.dir / 'alarm').write_text('99999\n'); (self.dir / 'run/rtc-owned').write_text('12345\n')
        result = self.run_case('network_cleanup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'alarm').read_text().strip(), '99999')

    def test_arm_refuses_to_overwrite_another_owners_alarm(self):
        (self.dir / 'alarm').write_text('99999\n')
        result = self.run_case('rtc_arm')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.dir / 'alarm').read_text().strip(), '99999')

    def test_disconnected_usb_interface_does_not_prevent_suspend(self):
        result = self.run_case('power_wait')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'power').read_text().strip(), 'mem')
        self.assertIn('SUSPEND_RESUME', (self.dir / 'log').read_text())

    def test_connected_usb_does_not_suspend(self):
        (self.dir / 'net/usb0/carrier').write_text('1\n')
        result = self.run_case('power_wait')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dir / 'power').read_text(), 'awake')
        self.assertEqual((self.dir / 'sleeps').read_text().strip(), '30')

    def test_repeated_early_wakes_fail_without_an_extra_network_cycle(self):
        result = self.run_case('power_wait; status=$?; network_cleanup; exit "$status"', TEST_EARLY_WAKE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('repeated early wakes', (self.dir / 'log').read_text())
        self.assertEqual((self.dir / 'alarm').read_text().strip(), '0')
        self.assertEqual((self.dir / 'dashboard.png').read_bytes(), b'old-valid-cache')

    def test_missing_ota_protection_refuses_network_initialization(self):
        result = self.run_case('network_init')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.dir / 'run/network-state').exists())

    def test_exit_request_prevents_suspend_and_cancels_alarm_in_cleanup(self):
        (self.dir / 'run/exit-request').touch()
        result = self.run_case('power_wait; status=$?; network_cleanup; exit "$status"')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.dir / 'power').read_text(), 'awake')
        self.assertEqual((self.dir / 'alarm').read_text().strip(), '0')


if __name__ == '__main__':
    unittest.main()
