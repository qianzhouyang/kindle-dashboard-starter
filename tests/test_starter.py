"""The sharing boundary: clean defaults, no implicit device access, LAN limits."""
import copy
import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import web_console as console
import starter_runtime
import weather
from render_plan_b import get_lunar_day_str
from http_harness import request


class StarterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for change in [patch.object(console, 'ACTIVE_CONFIG', copy.deepcopy(console.DEFAULT_CONFIG)),
                       patch.object(console, 'USER_DATA_DIR', self.directory),
                       patch.object(console, 'CONFIG_FILE', str(self.directory / 'console_config.json')),
                       patch.object(console, 'CURRENT_IMG', str(self.directory / 'current.png')),
                       patch.object(console, 'UPLOAD_DIR', self.directory / 'uploads'),
                       patch.object(starter_runtime, 'DATA_DIR', self.directory),
                       patch.object(weather, 'DATA_DIR', self.directory)]:
            change.start()
            self.addCleanup(change.stop)

    @patch.object(console.subprocess, 'run', side_effect=AssertionError('No implicit SSH'))
    @patch.object(weather.urllib.request, 'urlopen', side_effect=AssertionError('Demo must be offline'))
    def test_fresh_start_renders_all_templates_without_network_or_device(self, network, process):
        console.load_config()
        self.assertEqual(console.ACTIVE_CONFIG['weather']['mode'], 'demo')
        self.assertFalse(console.check_kindle_online())
        self.assertFalse(console.trigger_ssh_refresh()[0])
        self.assertFalse(console.trigger_ssh_restore()[0])
        for template in ('cat_office', 'calendar', 'cluster'):
            cfg = {**console.config_snapshot(), 'template': template}
            code, png, _ = request(console, '/api/preview', cfg)
            self.assertEqual(code, 200)
            with Image.open(io.BytesIO(png)) as image:
                self.assertEqual(image.mode, 'L')
                self.assertEqual(image.size, (1072, 1448) if template == 'cluster' else (1448, 1072))
            code, result, _ = request(console, '/api/publish', cfg)
            self.assertEqual(code, 200, result)
            code, result, _ = request(console, '/kindle-dashboard.png')
            with Image.open(io.BytesIO(result)) as physical:
                self.assertEqual(physical.size, (1072, 1448))
        network.assert_not_called()
        process.assert_not_called()

    def test_lan_can_only_read_display_image_and_rebinding_host_is_rejected(self):
        for path in ('/', '/api/status', '/api/module-schema', '/api/assets/' + 'a' * 32 + '.png'):
            self.assertEqual(request(console, path, remote='192.0.2.10')[0], 403)
        for path in ('/api/publish', '/api/restore_kindle', '/api/upload-image'):
            self.assertEqual(request(console, path, {}, remote='192.0.2.10')[0], 403)
        self.assertEqual(request(console, '/api/status', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(request(console, '/api/status', headers={'Host': '[invalid'})[0], 403)
        code, png, _ = request(console, '/kindle-dashboard.png', remote='192.0.2.10')
        self.assertEqual(code, 200)
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1072, 1448))
        self.assertFalse((self.directory / 'current.png').exists())

    def test_personal_upload_is_saved_only_in_user_directory_and_survives_restart(self):
        import base64
        source = Image.new('L', (120, 100), 30)
        buffer = io.BytesIO(); source.save(buffer, 'PNG')
        code, result, _ = request(console, '/api/upload-image', {'data': base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(code, 200)
        image_id = json.loads(result)['id']
        cfg = {'template': 'cat_office', 'customizations': {'cat_office': {
            'main': {'type': 'image', 'image_id': image_id}}}}
        self.assertEqual(request(console, '/api/publish', cfg)[0], 200)
        console.ACTIVE_CONFIG.clear(); console.load_config()
        self.assertEqual(console.ACTIVE_CONFIG['customizations']['cat_office']['main']['image_id'], image_id)
        self.assertTrue((self.directory / 'uploads' / image_id).is_file())

    def test_builtin_home_and_work_images_are_distinct_and_renderable(self):
        images = []
        for name in ('cat', 'home', 'work'):
            code, png, _ = request(console, '/api/builtin-' + name + '.png')
            self.assertEqual(code, 200)
            images.append(png)
            cfg = {'customizations': {'cat_office': {'main': {'type': 'image', 'image_id': 'builtin:' + name}}}}
            self.assertEqual(request(console, '/api/preview', cfg)[0], 200)
        self.assertEqual(len(set(images)), 3)

    def test_lunar_calendar_is_not_a_hardcoded_single_month(self):
        for year, month, day in ((2025, 1, 29), (2026, 2, 17), (2027, 2, 6)):
            self.assertEqual(get_lunar_day_str(datetime.date(year, month, day)), '正月初一')

    def test_device_config_requires_opt_in_files_and_strict_fingerprint_check(self):
        key = self.directory / 'key'; key.write_text('fixture')
        hosts = self.directory / 'hosts'; hosts.write_text('fixture')
        cfg = {'enabled': False, 'host': '192.0.2.50', 'identity_file': str(key), 'known_hosts_file': str(hosts)}
        path = self.directory / 'device.json'
        path.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError): starter_runtime.device_config()
        cfg['enabled'] = True; path.write_text(json.dumps(cfg))
        self.assertEqual(starter_runtime.connection()[2], 'root@192.0.2.50')
        self.assertIn('StrictHostKeyChecking=yes', starter_runtime.ssh_options())
        self.assertIn('-O', starter_runtime.ssh_options(scp=True))
        cfg['host'] = '-oProxyCommand=example'; path.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError): starter_runtime.device_config()
        self.assertEqual(console.validate_config({'identity_file': 'not-a-setting'}).get('identity_file'), None)

    def test_live_weather_uses_coordinates_cache_and_marks_failure_instead_of_demo(self):
        settings = {'mode': 'live', 'latitude': 0, 'longitude': 0}
        payload = {'current': {'temperature_2m': 20.3, 'weather_code': 0},
                   'daily': {'temperature_2m_min': [10], 'temperature_2m_max': [24]}}
        with patch.object(weather.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            first = weather.fetch_weather(settings, 'Test City')
            self.assertEqual(first['source'], 'Open-Meteo')
            self.assertIn('latitude=0.0', fetch.call_args.args[0].full_url)
        with patch.object(weather.urllib.request, 'urlopen', side_effect=OSError('offline')) as fetch:
            self.assertEqual(weather.fetch_weather(settings, 'Test City'), first)
            fetch.assert_not_called()
            other = weather.fetch_weather({**settings, 'longitude': 1}, 'Other City')
            self.assertEqual(other['source'], 'unavailable')
            with patch.object(weather.time, 'time', return_value=0):
                stale = weather.fetch_weather(settings, 'Test City')
            self.assertEqual(stale['source'], 'stale')
            self.assertIn('旧缓存', stale['cond'])
        with self.assertRaises(ValueError):
            console.validate_config({'weather': {'mode': 'live', 'latitude': 91, 'longitude': 0}})


if __name__ == '__main__':
    unittest.main()
