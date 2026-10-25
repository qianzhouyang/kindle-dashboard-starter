"""Mockup pixels, publication isolation, and USB failure/locking behavior."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import mockup_library as library
import web_console as console
from http_harness import request as memory_request, MockDeviceCase


class MockupPixelsTests(unittest.TestCase):
    def test_all_six_previews_and_both_rotation_directions_preserve_exact_pixels(self):
        self.assertEqual(len(library.catalog()), 6)
        for item in library.catalog():
            with self.subTest(id=item['id']):
                preview = Image.open(io.BytesIO(library.prepare_image(item['id'], '.', preview=True)))
                self.assertEqual(preview.size, (item['width'], item['height']))
                for angle in (90, 270):
                    frame = Image.open(io.BytesIO(library.prepare_image(item['id'], '.', angle)))
                    expected = preview.rotate(angle, expand=True) if preview.width > preview.height else preview
                    self.assertEqual(frame.size, (1072, 1448))
                    self.assertEqual(frame.mode, 'L')
                    self.assertIsNone(ImageChops.difference(frame, expected).getbbox())

    def test_uploaded_portrait_is_not_rotated_and_invalid_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image_id = 'a' * 32 + '.png'
            image = Image.new('L', (1072, 1448), 234)
            image.paste(0, (0, 0, 100, 200)); image.save(Path(directory) / image_id)
            result = Image.open(io.BytesIO(library.prepare_image(image_id, directory, 90)))
            self.assertIsNone(ImageChops.difference(image, result).getbbox())
            for invalid in ('../console_config.json', '/etc/passwd', None, 7, 'missing'):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    library.prepare_image(invalid, directory)
            for angle in (0, 180, '270', True):
                with self.assertRaises(ValueError):
                    library.prepare_image(image_id, directory, angle)
            Image.new('L', (800, 600)).save(Path(directory) / image_id)
            with self.assertRaisesRegex(ValueError, '不会拉伸'):
                library.prepare_image(image_id, directory)
            (Path(directory) / image_id).write_bytes(b'not an image')
            with self.assertRaises(ValueError):
                library.prepare_image(image_id, directory)


class MockupHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = self.root / 'console.json'; self.cfg.write_text('{"existing":"keep"}')
        self.published = self.root / 'current.png'; self.published.write_bytes(b'existing published image')
        for change in [patch.object(console, 'ACTIVE_CONFIG', copy.deepcopy(console.DEFAULT_CONFIG)),
                       patch.object(console, 'CONFIG_FILE', str(self.cfg)),
                       patch.object(console, 'CURRENT_IMG', str(self.published)),
                       patch.object(console, 'UPLOAD_DIR', self.root / 'uploads')]:
            change.start(); self.addCleanup(change.stop)

    def request(self, path, payload=None, origin=None):
        headers = {'Origin': origin} if origin else None
        code, body, _ = memory_request(console, path, payload, headers)
        return code, body

    @patch.object(console, 'trigger_ssh_refresh', return_value=(True, 'device command complete'))
    @patch.object(console, 'generate_image_bytes', side_effect=AssertionError('mockups must bypass live renderer'))
    def test_catalog_preview_push_are_isolated_from_published_settings(self, render, push):
        before = copy.deepcopy(console.ACTIVE_CONFIG)
        code, content = self.request('/api/mockups')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(content)['default_id'], 'D-life-household')
        code, content = self.request('/api/mockup-preview?id=D-life-household')
        self.assertEqual(code, 200)
        preview = Image.open(io.BytesIO(content))
        self.assertEqual(preview.size, (1448, 1072))
        code, result = self.request('/api/push-mockup', {'id': 'D-life-household', 'rotation': 90})
        self.assertEqual(code, 200, result)
        self.assertEqual(push.call_args.args, ({},))
        actual = Image.open(io.BytesIO(push.call_args.kwargs['png_bytes']))
        self.assertIsNone(ImageChops.difference(actual, preview.rotate(90, expand=True)).getbbox())
        self.assertEqual(console.ACTIVE_CONFIG, before)
        self.assertEqual(self.cfg.read_text(), '{"existing":"keep"}')
        self.assertEqual(self.published.read_bytes(), b'existing published image')

    @patch.object(console, 'trigger_ssh_refresh', return_value=(False, 'USB disconnected'))
    def test_invalid_cross_origin_and_disconnected_pushes_do_not_report_success(self, push):
        self.assertEqual(self.request('/api/push-mockup', {'id': '../secret'})[0], 400)
        self.assertEqual(self.request('/api/push-mockup', {'id': 'A-work-companion', 'rotation': 180})[0], 400)
        self.assertEqual(self.request('/api/push-mockup', {'id': 'A-work-companion'}, 'http://unrelated.example')[0], 400)
        push.assert_not_called()
        code, result = self.request('/api/push-mockup', {'id': 'A-work-companion'})
        self.assertEqual(code, 503)
        self.assertFalse(json.loads(result)['ok'])
        self.assertIn('USB disconnected', json.loads(result)['message'])


class MockupUSBTests(MockDeviceCase):
    @patch.object(console, 'generate_image_bytes', side_effect=AssertionError('must use supplied pixels'))
    @patch.object(console.subprocess, 'run')
    def test_usb_transfers_exact_png_then_enters_cached_mode_without_changing_light(self, run, render):
        image = library.prepare_image('F-life-week', '.')
        transferred = []
        def execute(command, **kwargs):
            if command[0] == 'scp':
                transferred.append(Path(command[-2]).read_bytes())
                self.assertTrue(command[-1].endswith('/mockup-upload.png'))
            return subprocess.CompletedProcess(command, 0, '', '')
        run.side_effect = execute
        ok, _ = console.trigger_ssh_refresh({}, png_bytes=image)
        self.assertTrue(ok); self.assertEqual(transferred, [image])
        self.assertEqual(run.call_count, 3)
        command = run.call_args.args[0][-1]
        self.assertTrue(command.startswith(console.DASHBOARD_RESTORE_COMMAND + ' && mv '))
        self.assertTrue(command.endswith(' && ' + console.DASHBOARD_REFRESH_COMMAND))
        self.assertNotIn('flIntensity', ' '.join(str(c) for c in run.call_args_list))
        self.assertFalse(Path(run.call_args_list[1].args[0][-2]).exists())

    @patch.object(console.subprocess, 'run')
    def test_failed_transfer_never_runs_restore_or_refresh(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0, '', ''),
                           subprocess.CompletedProcess([], 1, '', 'transfer failed')]
        ok, message = console.trigger_ssh_refresh({}, png_bytes=b'png')
        self.assertFalse(ok); self.assertIn('transfer failed', message)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(Path(run.call_args_list[1].args[0][-2]).exists())

    @patch.object(console.subprocess, 'run')
    def test_refresh_failure_or_timeout_is_not_success_and_releases_lock(self, run):
        for last in (subprocess.CompletedProcess([], 7, '', 'refresh failed'), subprocess.TimeoutExpired('ssh', 120)):
            run.side_effect = [subprocess.CompletedProcess([], 0, '', ''),
                               subprocess.CompletedProcess([], 0, '', ''), last]
            self.assertFalse(console.trigger_ssh_refresh({}, png_bytes=b'png')[0])
            self.assertFalse(console.DEVICE_LOCK.locked())

    @patch.object(console.subprocess, 'run')
    def test_overlapping_push_or_restore_does_not_touch_device(self, run):
        with console.DEVICE_LOCK:
            self.assertFalse(console.trigger_ssh_refresh({}, png_bytes=b'png')[0])
            self.assertFalse(console.trigger_ssh_refresh({})[0])
            self.assertFalse(console.trigger_ssh_restore()[0])
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
