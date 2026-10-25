"""Check publication isolation, persisted content, image inputs and actual raster boundaries."""
import base64
import copy
import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import dashboard_modules as modules
import web_console as console
from http_harness import request as memory_request


class ModuleRenderingTests(unittest.TestCase):
    def test_override_cannot_modify_pixels_outside_selected_region_in_either_rotation(self):
        for rotation in (90, 270):
            with self.subTest(rotation=rotation):
                base = Image.new('L', (1448, 1072), 190)
                cfg = console.validate_config({'template': 'cat_office', 'rotation': rotation,
                    'customizations': {'cat_office': {'main': {'type': 'text', 'title': 'My board', 'text': 'A task\n' * 200}}}})
                result = modules.apply_customizations(base.rotate(rotation, expand=True), cfg, '.', '.')
                self.assertEqual(result.size, (1072, 1448))
                result = result.rotate(-rotation, expand=True)
                region = next(box for rid, _, box in modules.LAYOUTS['cat_office']['regions'] if rid == 'main')
                difference = ImageChops.difference(base, result)
                self.assertIsNotNone(difference.getbbox())
                difference.paste(0, region)
                self.assertIsNone(difference.getbbox())

    def test_template_settings_are_isolated(self):
        original = Image.new('L', (1072, 1448), 255)
        cfg = console.validate_config({'template': 'calendar', 'customizations': {
            'cat_office': {'main': {'type': 'text', 'text': 'Only cat'}}}})
        self.assertIsNone(ImageChops.difference(original, modules.apply_customizations(original, cfg, '.', '.')).getbbox())

    def test_tokens_are_literal_substitution_without_code_execution(self):
        now = datetime.datetime(2026, 10, 22, 9, 8)
        value = modules.expand('{date} {time} {quota} {unknown}', {'quota': 42}, now)
        self.assertEqual(value, '2026-10-22 09:08 42% {unknown}')

    def test_invalid_region_type_filename_and_oversized_text_are_rejected(self):
        for setting in [
            {'cat_office': {'missing': {'type': 'text'}}},
            {'cat_office': {'footer': {'type': 'calendar'}}},
            {'cat_office': {'main': {'type': 'image', 'image_id': '../private.png'}}},
            {'cat_office': {'main': {'type': 'text', 'text': 'a' * 2001}}},
            {'cat_office': {'main': {'type': 'quota', 'value': 'nan'}}},
        ]:
            with self.subTest(setting=repr(setting)[:80]), self.assertRaises(ValueError):
                modules.validate_customizations(setting)


class WorkbenchHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.uploads = self.root / 'uploads'
        self.config_file = self.root / 'private' / 'console.json'
        self.legacy = self.root / 'legacy.json'
        self.legacy.write_text(json.dumps({'template': 'calendar', 'quota': '61', 'quote': 'existing quote'}))
        patches = [
            patch.object(console, 'ACTIVE_CONFIG', copy.deepcopy(console.DEFAULT_CONFIG)),
            patch.object(console, 'CONFIG_FILE', str(self.config_file)),
            patch.object(console, 'LEGACY_CONFIG_FILE', str(self.legacy)),
            patch.object(console, 'UPLOAD_DIR', self.uploads),
            patch.object(console, 'CURRENT_IMG', str(self.root / 'published.png')),
            patch.object(console, 'check_kindle_online', return_value=False),
        ]
        def base_render(path, **kwargs):
            Image.new('L', (1072, 1448), 255).save(path)
        patches += [patch.object(console, name, side_effect=base_render) for name in
                    ('render_plan_b_dashboard', 'render_calendar_dashboard', 'render_dashboard')]
        for item in patches:
            item.start(); self.addCleanup(item.stop)
        console.load_config()

    def request(self, path, data=None, headers=None):
        return memory_request(console, path, data, headers)

    def test_preview_does_not_publish_and_saved_device_image_matches_preview(self):
        cfg = {'template': 'cat_office', 'customizations': {'cat_office': {
            'main': {'type': 'text', 'title': 'My own content', 'text': 'Read\nExercise\nA real note'},
            'footer': {'type': 'metric', 'title': 'Focus', 'value': '3 / 5'},
        }}}
        before = self.config_file.read_bytes()
        status, preview, headers = self.request('/api/preview', cfg)
        self.assertEqual(status, 200)
        self.assertEqual(Image.open(io.BytesIO(preview)).size, (1448, 1072))
        self.assertEqual(self.config_file.read_bytes(), before)
        self.assertEqual(console.ACTIVE_CONFIG['template'], 'calendar')
        status, result, _ = self.request('/api/publish', cfg)
        self.assertEqual(status, 200, result)
        self.assertEqual(console.ACTIVE_CONFIG['customizations']['cat_office']['main']['text'], cfg['customizations']['cat_office']['main']['text'])
        status, physical, _ = self.request('/kindle-dashboard.png')
        with Image.open(io.BytesIO(preview)) as shown, Image.open(io.BytesIO(physical)) as device:
            self.assertEqual(device.size, (1072, 1448))
            self.assertIsNone(ImageChops.difference(shown.rotate(270, expand=True), device).getbbox())
        console.ACTIVE_CONFIG.clear(); console.load_config()
        self.assertEqual(console.ACTIVE_CONFIG['customizations']['cat_office']['main']['title'], 'My own content')
        self.assertEqual(json.loads(self.legacy.read_text())['quote'], 'existing quote')
        self.assertNotIn('customizations', json.loads(self.legacy.read_text()))

    def test_upload_normalizes_transparency_and_renders_in_selected_region(self):
        source = Image.new('RGBA', (80, 60), (0, 0, 0, 0))
        source.paste((0, 0, 0, 255), (20, 10, 60, 50))
        buffer = io.BytesIO(); source.save(buffer, 'PNG')
        status, response, _ = self.request('/api/upload-image', {'data': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(status, 200, response)
        image_id = json.loads(response)['id']
        with Image.open(self.uploads / image_id) as saved:
            self.assertEqual(saved.mode, 'L'); self.assertEqual(saved.getpixel((0, 0)), 255)
            self.assertEqual(saved.getpixel((40, 30)), 0)
        status, body, _ = self.request('/api/preview', {'template': 'cat_office', 'customizations': {
            'cat_office': {'main': {'type': 'image', 'image_id': image_id, 'fit': 'contain'}}}})
        self.assertEqual(status, 200, body[:80])
        with Image.open(io.BytesIO(body)) as rendered:
            self.assertLess(rendered.crop((55, 215, 850, 990)).getextrema()[0], 255)
        self.assertEqual(self.request('/api/assets/' + image_id)[0], 200)
        self.assertEqual(self.request('/api/assets/../../legacy.json')[0], 404)

    def test_invalid_upload_and_cross_origin_edits_do_not_change_settings(self):
        before = self.config_file.read_bytes()
        self.assertEqual(self.request('/api/upload-image', {'data': 'not an image'})[0], 400)
        self.assertEqual(self.request('/api/publish', {'quote': 'changed'}, {'Origin': 'http://unrelated.example'})[0], 400)
        self.assertEqual(self.request('/api/publish', {'customizations': {'calendar': {'main': {'type': 'image', 'image_id': '/etc/passwd'}}}})[0], 400)
        self.assertEqual(self.config_file.read_bytes(), before)
        self.assertFalse(self.uploads.exists())

    def test_reset_one_region_preserves_other_regions_and_templates(self):
        data = {'cat_office': {'main': {'type': 'text', 'text': 'Cat'}, 'footer': {'type': 'text', 'text': 'Footer'}},
                'calendar': {'note': {'type': 'text', 'text': 'Calendar'}}}
        self.assertEqual(self.request('/api/publish', {'customizations': data})[0], 200)
        del data['cat_office']['main']
        self.assertEqual(self.request('/api/publish', {'customizations': data})[0], 200)
        state = json.loads(self.request('/api/status')[1])['config']['customizations']
        self.assertNotIn('main', state['cat_office'])
        self.assertEqual(state['cat_office']['footer']['text'], 'Footer')
        self.assertEqual(state['calendar']['note']['text'], 'Calendar')


if __name__ == '__main__':
    unittest.main()
