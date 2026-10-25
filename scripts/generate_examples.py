"""Generate the six starter examples without reading any personal runtime data."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def generate():
    with tempfile.TemporaryDirectory(prefix='kindle-starter-demo-') as temporary:
        os.environ['KINDLE_DASHBOARD_DATA_DIR'] = temporary
        sys.path.insert(0, str(ROOT / 'src'))
        import web_console as console
        from mockup_library import catalog
        example = copy.deepcopy(console.DEFAULT_CONFIG)
        (ROOT / 'config' / 'console.example.json').write_text(
            json.dumps(example, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        templates = ['cat_office', 'calendar', 'cat_office', 'calendar', 'cluster', 'cluster']
        for index, item in enumerate(catalog()):
            cfg = copy.deepcopy(example)
            cfg.update(template=templates[index], quota=42, battery='未读取', quote='慢慢来，也会到达。')
            if index in (2, 3):
                region = 'main' if index == 2 else 'note'
                cfg['customizations'] = {cfg['template']: {region: {'type': 'image', 'image_id': 'builtin:home'}}}
            cfg['customizations'].setdefault(cfg['template'], {})['footer'] = {
                'type': 'text', 'text': 'STARTER · 示例数据 · 额度为手工值 · 电量未读取', 'font_size': 22}
            data = console.generate_image_bytes(cfg)
            with Image.open(io.BytesIO(data)) as frame:
                shown = frame.rotate(-cfg['rotation'], expand=True) if cfg['template'] != 'cluster' else frame.copy()
                assert shown.size == (item['width'], item['height'])
                shown.save(ROOT / 'assets' / 'mockups' / (item['id'] + '.png'), 'PNG', optimize=True)
        print('Generated six examples and a clean console configuration.')


if __name__ == '__main__':
    generate()
