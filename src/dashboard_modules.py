"""Bounded region overrides on top of the existing Kindle templates."""
import calendar
import datetime
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from render_plan_b import get_font, fetch_weather

TYPE_LABELS = {
    'inherit': '模板默认', 'text': '自定义文字 / 清单', 'image': '图片',
    'clock': '时间与日期', 'weather': '天气', 'calendar': '本月月历',
    'quota': '百分比进度', 'metric': '自定义指标', 'blank': '留白',
}

LAYOUTS = {
    'cat_office': {'size': [1448, 1072], 'regions': [
        ('heading', '标题与台词', [55, 35, 850, 205]),
        ('main', '左侧主画面', [55, 215, 850, 990]),
        ('weather', '右上信息', [900, 35, 1395, 140]),
        ('clock', '右中时间区', [900, 150, 1395, 320]),
        ('quota', '右下主信息', [900, 330, 1395, 990]),
        ('footer', '底部信息栏', [55, 1012, 1395, 1065]),
    ]},
    'calendar': {'size': [1448, 1072], 'regions': [
        ('heading', '顶部标题', [60, 35, 1390, 94]),
        ('clock', '左上时间区', [60, 105, 815, 260]),
        ('weather', '右上天气区', [855, 105, 1390, 260]),
        ('main', '左侧主信息', [60, 285, 800, 700]),
        ('calendar', '右侧月历区', [855, 285, 1390, 700]),
        ('note', '左下留言区', [60, 725, 800, 985]),
        ('stats', '右下指标区', [855, 725, 1390, 985]),
        ('footer', '底部信息栏', [60, 1012, 1390, 1065]),
    ]},
    'cluster': {'size': [1072, 1448], 'regions': [
        ('heading', '顶部摘要', [30, 30, 1042, 340]),
        ('main', '节点信息区', [30, 370, 1042, 760]),
        ('tasks', '任务信息区', [30, 790, 1042, 1150]),
        ('note', '说明区', [30, 1180, 1042, 1398]),
        ('footer', '底部信息栏', [30, 1400, 1042, 1448]),
    ]},
}


def allowed_types(box):
    height = box[3] - box[1]
    if height < 90:
        return ['inherit', 'text', 'metric', 'blank']
    if height < 220:
        return ['inherit', 'text', 'image', 'clock', 'weather', 'metric', 'blank']
    return list(TYPE_LABELS)


def schema():
    return {'types': TYPE_LABELS, 'layouts': {
        name: {'size': data['size'], 'regions': [
            {'id': rid, 'name': label, 'box': box, 'types': allowed_types(box)}
            for rid, label, box in data['regions']
        ]} for name, data in LAYOUTS.items()
    }, 'tokens': ['{time}', '{date}', '{weekday}', '{quota}', '{quote}', '{battery}', '{frontlight}']}


def validate_customizations(value):
    if not isinstance(value, dict):
        raise ValueError('分区设置必须是对象')
    result = {}
    for template, regions in value.items():
        if template not in LAYOUTS or not isinstance(regions, dict):
            raise ValueError('未知模板或分区设置格式错误')
        boxes = {rid: box for rid, _, box in LAYOUTS[template]['regions']}
        result[template] = {}
        for rid, module in regions.items():
            if rid not in boxes or not isinstance(module, dict):
                raise ValueError('未知分区')
            kind = module.get('type', 'inherit')
            if kind not in allowed_types(boxes[rid]):
                raise ValueError('所选模块不适合这个分区')
            clean = {'type': kind}
            for field, maximum in [('title', 100), ('text', 2000), ('value', 120)]:
                text = module.get(field, '')
                if not isinstance(text, str) or len(text) > maximum:
                    raise ValueError(f'{field} 内容过长或格式错误')
                clean[field] = text.replace('\r\n', '\n').replace('\r', '\n')
            try:
                clean['font_size'] = int(module.get('font_size', 32))
            except (TypeError, ValueError):
                raise ValueError('字号必须是数字') from None
            if not 18 <= clean['font_size'] <= 72:
                raise ValueError('字号范围为 18–72')
            clean['align'] = module.get('align', 'left')
            clean['fit'] = module.get('fit', 'contain')
            if clean['align'] not in ('left', 'center') or clean['fit'] not in ('contain', 'cover'):
                raise ValueError('对齐或图片适应方式无效')
            image_id = module.get('image_id', '')
            if not isinstance(image_id, str) or (image_id not in ('', 'builtin:cat', 'builtin:home', 'builtin:work') and
                                                not re.fullmatch(r'[a-f0-9]{32}\.png', image_id)):
                raise ValueError('图片标识无效，请通过工作台上传')
            clean['image_id'] = image_id
            if kind == 'quota' and clean['value']:
                try:
                    percent = float(clean['value'])
                except ValueError:
                    raise ValueError('进度值应为 0–100 的数字') from None
                if not 0 <= percent <= 100:
                    raise ValueError('进度值应为 0–100 的数字')
            result[template][rid] = clean
    return result


def expand(text, cfg, now):
    values = {'time': now.strftime('%H:%M'), 'date': now.strftime('%Y-%m-%d'),
              'weekday': '星期' + '一二三四五六日'[now.weekday()],
              'quota': str(cfg.get('quota', 85)) + '%', 'quote': str(cfg.get('quote', '')),
              'battery': str(cfg.get('battery', '')), 'frontlight': str(cfg.get('frontlight', 0))}
    for key, value in values.items():
        text = text.replace('{' + key + '}', value)
    return text


def wrap(text, font, width):
    lines = []
    for paragraph in text.expandtabs(4).split('\n'):
        line = ''
        for character in paragraph:
            if line and font.getlength(line + character) > width:
                lines.append(line); line = character
            else:
                line += character
        lines.append(line)
    return lines


def text_block(tile, text, box, size=32, bold=False, align='left'):
    """Fit and clip inside the tile; long content cannot spill into other modules."""
    x0, y0, x1, y1 = box
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    size = min(size, max(12, height - 4))
    while True:
        font = get_font(size, bold)
        lines = wrap(text, font, width)
        step = size + max(4, size // 5)
        if len(lines) * step <= height or size <= 18:
            break
        size -= 1
    count = max(1, height // step)
    if len(lines) > count:
        lines = lines[:count]
        while lines[-1] and font.getlength(lines[-1] + '…') > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    draw = ImageDraw.Draw(tile)
    for n, line in enumerate(lines):
        x = x0 + (width - font.getlength(line)) / 2 if align == 'center' else x0
        draw.text((x, y0 + n * step), line, fill=0, font=font)


def draw_module(tile, module, cfg, upload_dir, assets_dir, now):
    width, height = tile.size
    kind = module['type']; padding = 12
    title = expand(module.get('title', ''), cfg, now)
    body = expand(module.get('text', ''), cfg, now)
    value = expand(module.get('value', ''), cfg, now)
    size = module.get('font_size', 32); align = module.get('align', 'left')
    box = [padding, padding, width - padding, height - padding]
    if kind == 'blank':
        return
    if height < 90:
        text = ' · '.join(v for v in [title, value if kind == 'metric' else body] if v)
        text_block(tile, text, box, min(size, 28), align=align)
        return
    if title:
        text_block(tile, title, [padding, padding, width - padding, padding + 38], min(size, 30), True, align)
        box[1] += 44
    if kind == 'text':
        text_block(tile, body, box, size, align=align)
    elif kind == 'image':
        image_id = module.get('image_id', '')
        builtins = {'builtin:cat': 'work-side.webp', 'builtin:home': 'home-wide.webp', 'builtin:work': 'work-wide.webp'}
        path = Path(assets_dir) / 'illustrations' / builtins[image_id] if image_id in builtins else Path(upload_dir) / image_id
        if not image_id or not path.is_file():
            text_block(tile, '请在工作台选择或上传图片', box, 26)
            return
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert('L')
            target = (box[2] - box[0], box[3] - box[1])
            image = (ImageOps.fit(image, target, Image.Resampling.LANCZOS) if module.get('fit') == 'cover'
                     else ImageOps.contain(image, target, Image.Resampling.LANCZOS))
            tile.paste(image, (box[0] + (target[0] - image.width) // 2, box[1] + (target[1] - image.height) // 2))
    elif kind == 'clock':
        big = min(130, max(32, (box[3] - box[1]) // 2))
        text_block(tile, now.strftime('%H:%M'), [*box[:2], box[2], box[1] + big + 12], big, True, align)
        text_block(tile, body or expand('{date}  {weekday}', cfg, now),
                   [box[0], box[1] + big + 16, box[2], box[3]], min(size, 28), align=align)
    elif kind == 'weather':
        weather = fetch_weather(cfg.get('weather'), cfg.get('city', '示例城市'))
        summary = f"{weather['city']} · {weather['cond']}  {weather['temp']}"
        text_block(tile, summary + '\n' + weather['range'] + ' · 更新 ' + weather['update'], box, min(size, 32), align=align)
    elif kind == 'metric':
        big = min(100, max(size, (box[3] - box[1]) // 3))
        text_block(tile, value or '—', [*box[:2], box[2], box[1] + big + 16], big, True, align)
        text_block(tile, body, [box[0], box[1] + big + 20, box[2], box[3]], size, align=align)
    elif kind == 'quota':
        percent = float(module['value']) if module.get('value') else int(cfg.get('quota', 85))
        big = min(140, max(40, (box[3] - box[1]) // 3))
        text_block(tile, f'{percent:g}%', [*box[:2], box[2], box[1] + big + 16], big, True, align)
        y = box[1] + big + 25; draw = ImageDraw.Draw(tile)
        draw.rectangle([box[0], y, box[2], y + 24], fill=240, outline=0, width=2)
        if percent > 0:
            draw.rectangle([box[0], y, box[0] + int((box[2] - box[0]) * percent / 100), y + 24], fill=0)
        text_block(tile, body, [box[0], y + 40, box[2], box[3]], size, align=align)
    elif kind == 'calendar':
        text_block(tile, f'{now.year} 年 {now.month} 月', [*box[:2], box[2], box[1] + 40], 30, True)
        weeks = calendar.monthcalendar(now.year, now.month)
        top = box[1] + 50; cell_w = (box[2] - box[0]) / 7
        cell_h = (box[3] - top) / (len(weeks) + 1)
        draw = ImageDraw.Draw(tile); font = get_font(min(28, max(16, int(cell_h) - 10)))
        for row, values in enumerate([list('一二三四五六日')] + weeks):
            for col, day in enumerate(values):
                if not day:
                    continue
                x = box[0] + col * cell_w; y = top + row * cell_h
                active = row > 0 and day == now.day
                if active:
                    draw.rounded_rectangle([x + 2, y + 1, x + cell_w - 2, y + cell_h - 2], radius=5, fill=0)
                label = str(day)
                draw.text((x + (cell_w - font.getlength(label)) / 2, y + 3), label, font=font, fill=255 if active else 0)


def apply_customizations(image, cfg, upload_dir, assets_dir, now=None):
    template = cfg.get('template', 'cat_office')
    regions = cfg.get('customizations', {}).get(template, {})
    if not regions:
        return image
    now = now or datetime.datetime.now()
    rotation = int(cfg.get('rotation', 270))
    canvas = image.rotate(-rotation, expand=True) if template != 'cluster' else image.copy()
    if tuple(LAYOUTS[template]['size']) != canvas.size:
        raise ValueError('模板尺寸不匹配')
    for rid, _, box in LAYOUTS[template]['regions']:
        module = regions.get(rid, {'type': 'inherit'})
        if module['type'] == 'inherit':
            continue
        x0, y0, x1, y1 = box
        tile = Image.new('L', (x1 - x0, y1 - y0), 255)
        draw_module(tile, module, cfg, upload_dir, assets_dir, now)
        canvas.paste(tile, (x0, y0))
    return canvas.rotate(rotation, expand=True) if template != 'cluster' else canvas
