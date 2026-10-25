"""Temporary full-screen mockup library; never modifies published configuration."""
import io
import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MOCKUP_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'mockups'
MOCKUPS = (
    ('A-work-companion', 'A · 猫咪搭班', '横屏 · 工作', 1448, 1072),
    ('B-work-console', 'B · 数据驾驶舱', '横屏 · 工作', 1448, 1072),
    ('C-life-slow', 'C · 慢慢过日子', '横屏 · 生活', 1448, 1072),
    ('D-life-household', 'D · 家庭调度台', '横屏 · 生活', 1448, 1072),
    ('E-work-brief', 'E · 每日简报', '竖屏 · 工作', 1072, 1448),
    ('F-life-week', 'F · 一周有数', '竖屏 · 生活', 1072, 1448),
)


def catalog():
    return [dict(id=key, name=name, category=category, width=w, height=h)
            for key, name, category, w, h in MOCKUPS]


def image_path(image_id, upload_dir):
    if not isinstance(image_id, str):
        raise ValueError('请先选择一张 mockup')
    if image_id in {item[0] for item in MOCKUPS}:
        path = MOCKUP_DIR / (image_id + '.png')
    elif re.fullmatch(r'[a-f0-9]{32}\.png', image_id):
        path = Path(upload_dir) / image_id
    else:
        raise ValueError('未知 mockup，请从列表选择或上传图片')
    if not path.is_file():
        raise ValueError('图片不存在，请重新选择或上传')
    return path


def prepare_image(image_id, upload_dir, rotation=270, preview=False):
    # Rotation uses the same Pillow counterclockwise convention as the console.
    if isinstance(rotation, bool) or rotation not in (90, 270):
        raise ValueError('横屏方向必须为 90 或 270')
    path = image_path(image_id, upload_dir)
    try:
        with Image.open(path) as source:
            if source.format != 'PNG' or source.size not in ((1448, 1072), (1072, 1448)):
                raise ValueError('整屏图片必须为横屏 1448×1072 或竖屏 1072×1448；不会拉伸或裁切')
            image = ImageOps.exif_transpose(source).convert('L')
            if image.size not in ((1448, 1072), (1072, 1448)):
                raise ValueError('图片方向或尺寸无效')
            if not preview and image.width > image.height:
                image = image.rotate(rotation, expand=True)
            output = io.BytesIO()
            image.save(output, 'PNG', optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError('无法读取 mockup 图片，请重新上传') from exc
