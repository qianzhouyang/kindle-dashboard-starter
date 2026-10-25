#!/usr/bin/env python3
"""Kindle Dashboard Starter PW3 E-Ink 仪表盘方案 B：猫的打工小屋。

分辨率：1448 × 1072 (横屏)，经 rotate(270) 映射为 1072 × 1448 物理屏
特色：
1. 左侧大画幅工作猫猫线稿插图与幽默金句；
2. 右侧高密度时钟、农历、收工倒计时；
3. 拟物化“粮仓”玻璃密封罐展示每周额度储备与补货倒计时；
4. 底部通栏“小账本”整合 Token 用量、前光与免打扰状态。
"""

import argparse
import datetime
import json
import math
import os
import sys
from weather import fetch_weather
from lunar_python import Solar
from PIL import Image, ImageDraw, ImageFont

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, ".."))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")

WIDTH = 1448
HEIGHT = 1072

def get_font(size: int, bold: bool = False):
    candidates = [
        os.environ.get('KINDLE_DASHBOARD_FONT_BOLD' if bold else 'KINDLE_DASHBOARD_FONT', ''),
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc' if bold else '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def get_lunar_day_str(dt: datetime.date) -> str:
    lunar = Solar.fromYmd(dt.year, dt.month, dt.day).getLunar()
    return lunar.getMonthInChinese() + '月' + lunar.getDayInChinese()


def draw_granary_jar(draw: ImageDraw.ImageDraw, box, quota_pct: int, reset_str: str, countdown_str: str):
    # 绘制可爱的“粮仓”玻璃密封罐
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2

    font_title = get_font(30, bold=True)
    font_sub = get_font(22, bold=False)
    font_pct = get_font(52, bold=True)
    font_meta = get_font(20, bold=False)

    # 1. 顶部小睡猫简笔画
    cat_y = y0 + 15
    draw.arc([cx - 35, cat_y - 20, cx + 35, cat_y + 15], 180, 360, fill=0, width=3) # 猫身弧线
    draw.polygon([(cx - 30, cat_y - 12), (cx - 38, cat_y - 25), (cx - 20, cat_y - 18)], fill=0) # 左耳
    draw.polygon([(cx - 15, cat_y - 20), (cx - 5, cat_y - 26), (cx, cat_y - 18)], fill=0) # 右耳
    draw.arc([cx - 22, cat_y - 6, cx - 14, cat_y], 0, 180, fill=0, width=2) # 闭眼
    draw.arc([cx - 10, cat_y - 6, cx - 2, cat_y], 0, 180, fill=0, width=2)

    # 2. 玻璃罐盖子
    lid_y0 = y0 + 35
    lid_y1 = y0 + 55
    draw.rounded_rectangle([cx - 75, lid_y0, cx + 75, lid_y1], radius=8, fill=255, outline=0, width=3)
    draw.rectangle([cx - 60, lid_y1, cx + 60, lid_y1 + 10], fill=0) # 密封圈

    # 3. 玻璃罐身
    body_y0 = lid_y1 + 10
    body_y1 = y1 - 20
    draw.rounded_rectangle([x0 + 15, body_y0, x1 - 15, body_y1], radius=24, fill=255, outline=0, width=4)

    # 4. 内部“粮仓”内容
    draw.text((cx - 30, body_y0 + 20), "粮仓", fill=0, font=font_title)
    draw.text((cx - 65, body_y0 + 60), "每周额度剩余", fill=60, font=font_sub)

    # 百分比数字
    pct_text = f"{quota_pct}%"
    draw.text((cx - 50, body_y0 + 95), pct_text, fill=0, font=font_pct)

    # 罐中进度条与小鱼干/饼干颗粒填充
    bar_x0 = x0 + 40
    bar_x1 = x1 - 40
    bar_y0 = body_y0 + 175
    bar_y1 = bar_y0 + 18
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=255, outline=0, width=2)
    fill_w = int((bar_x1 - bar_x0) * (quota_pct / 100.0))
    if fill_w > 0:
        draw.rectangle([bar_x0, bar_y0, bar_x0 + fill_w, bar_y1], fill=0)

    # 底部补货说明
    draw.line([x0 + 35, bar_y1 + 18, x1 - 35, bar_y1 + 18], fill=200, width=1)
    draw.text((cx - 75, bar_y1 + 28), f"补货 {reset_str}", fill=40, font=font_meta)
    draw.text((cx - 70, bar_y1 + 54), f"还剩 {countdown_str}", fill=40, font=font_meta)

def render_plan_b_dashboard(
    output_path: str,
    battery: str = "未读取",
    frontlight: int = 2,
    quota_pct: int = 85,
    quote: str = "“别催了，爪子都敲出火星了。”",
    rotation: int = 270,
    weather=None,
):
    # 创建 1448 × 1072 纯白画布
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y年%m月")
    day_str = now.strftime("%d")
    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    weekday_str = weekday_map.get(now.weekday(), "")
    lunar_str = get_lunar_day_str(now.date())

    # 计算收工倒计时 (目标当日 18:00)
    target_work_end = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now < target_work_end:
        rem_sec = int((target_work_end - now).total_seconds())
        rem_h = rem_sec // 3600
        rem_m = (rem_sec % 3600) // 60
        work_end_str = f"收工还有 {rem_h}时{rem_m:02d}分"
    else:
        work_end_str = "今日已收工休息"

    # 字体
    font_header_title = get_font(52, bold=True)
    font_header_sub = get_font(26, bold=False)
    font_quote = get_font(30, bold=False)
    font_weather_title = get_font(32, bold=True)
    font_weather_sub = get_font(22, bold=False)
    font_clock_label = get_font(24, bold=False)
    font_clock_big = get_font(72, bold=True)
    font_date_big = get_font(60, bold=True)
    font_date_sub = get_font(24, bold=False)
    font_footer = get_font(22, bold=False)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. 左侧区域 (0 ~ 870px)：猫的打工小屋插画
    # ──────────────────────────────────────────────────────────────────────────
    draw.text((60, 45), "猫的打工小屋", fill=0, font=font_header_title)
    draw.text((60, 115), "慢慢来，也会到达。 / STARTER", fill=80, font=font_header_sub)
    draw.text((60, 160), quote, fill=20, font=font_quote)

    # Project-owned generated illustration; never import personal uploads.
    cat_img_path = os.path.join(ASSETS_DIR, 'illustrations', 'work-side.webp')
    with Image.open(cat_img_path) as source:
        cat_im = source.convert('L')
        cat_im.thumbnail((795, 775), Image.Resampling.LANCZOS)
        img.paste(cat_im, (55 + (795 - cat_im.width) // 2, 215 + (775 - cat_im.height) // 2))

    # 垂直分割线
    draw.line([875, 45, 875, 985], fill=210, width=2)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. 右侧区域 (880 ~ 1448px)：数据看板区
    # ──────────────────────────────────────────────────────────────────────────
    rx = 910
    weather = weather or fetch_weather()

    # (1) 顶部天气
    draw.text((rx, 50), f"{weather['city']} · {weather['cond']} {weather['temp']}", fill=0, font=font_weather_title)
    draw.text((rx, 96), f"{weather['range']} · {weather['source']}", fill=80, font=font_weather_sub)
    draw.text((rx + 360, 96), f"更新 {weather['update']}", fill=100, font=font_weather_sub)

    draw.line([rx, 135, WIDTH - 55, 135], fill=0, width=2)

    # (2) 小屋时间与日历块
    y_time = 150
    draw.text((rx, y_time), "小屋时间", fill=80, font=font_clock_label)
    draw.text((rx, y_time + 30), time_str, fill=0, font=font_clock_big)
    draw.text((rx, y_time + 115), work_end_str, fill=40, font=font_clock_label)

    # 右侧日期大字
    rx_date = rx + 300
    draw.text((rx_date, y_time), date_str, fill=80, font=font_date_sub)
    draw.text((rx_date, y_time + 26), day_str, fill=0, font=font_date_big)
    draw.text((rx_date + 85, y_time + 34), weekday_str, fill=0, font=font_date_sub)
    draw.text((rx_date + 85, y_time + 68), lunar_str, fill=60, font=font_date_sub)

    draw.line([rx, y_time + 155, WIDTH - 55, y_time + 155], fill=210, width=1)

    # (3) “粮仓”玻璃密封罐 (每周额度)
    jar_box = [rx + 60, y_time + 180, rx + 440, y_time + 540]
    draw_granary_jar(
        draw,
        jar_box,
        quota_pct=quota_pct,
        reset_str="自行设置",
        countdown_str="手工指标",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. 底部通栏状态条 (高 65px)
    # ──────────────────────────────────────────────────────────────────────────
    draw.line([55, 1005, WIDTH - 55, 1005], fill=0, width=2)

    footer_left = "额度为手工值 · 非账号实时数据"
    footer_right = f"短按电源退出 · 前光 {frontlight}/24 · 电量 {battery}（手工）"

    draw.text((60, 1025), footer_left, fill=40, font=font_footer)
    draw.text((WIDTH - 760, 1025), footer_right, fill=40, font=font_footer)

    # 旋转指定角度适应 Kindle PW3 纵向物理帧缓冲 (270 或 90)
    rotated = img.rotate(rotation, expand=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    rotated.save(output_path, "PNG", optimize=True)
    print(f"Plan B Dashboard successfully rendered to {output_path} ({rotated.size[0]}x{rotated.size[1]})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render Kindle Plan B Dashboard")
    parser.add_argument("-o", "--output", default=os.path.join(ASSETS_DIR, "dashboard_plan_b.png"), help="Output PNG path")
    parser.add_argument("--battery", default="未读取", help="Device battery level")
    args = parser.parse_args()

    render_plan_b_dashboard(args.output, battery=args.battery)
