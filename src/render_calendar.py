#!/usr/bin/env python3
"""Kindle Dashboard Starter PW3 E-Ink 仪表盘模板：打工猫的工位（双历日历版）。

分辨率：1448 × 1072 (横屏)，经 rotate(270) 映射为 1072 × 1448 物理屏
特色：
1. 左侧大字号额度、进度条、倒计时与趣味像素猫下班状态；
2. 右侧完整的公历+农历当月日历（当天反白高亮）；
3. 右侧 Token 每日统计与账户累计；
4. 顶部时钟、日期与可配置天气。
"""

import argparse
import calendar
import datetime
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# 引入天气与基础方法
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_plan_b import get_font, fetch_weather, get_lunar_day_str

WIDTH = 1448
HEIGHT = 1072

def draw_calendar_grid(draw: ImageDraw.ImageDraw, box, year: int, month: int, today: int):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0

    font_th = get_font(24, bold=True)
    font_day = get_font(24, bold=True)
    font_lunar = get_font(16, bold=False)

    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    col_w = w / 7.0

    # 绘制星期表头
    for i, wd in enumerate(weekdays):
        cx = x0 + i * col_w + col_w / 2
        draw.text((cx - 10, y0 + 10), wd, fill=0, font=font_th)

    cal = calendar.monthcalendar(year, month)
    row_h = (h - 50) / float(len(cal))

    for r_idx, week in enumerate(cal):
        curr_y = y0 + 50 + r_idx * row_h
        for c_idx, day in enumerate(week):
            if day == 0:
                continue
            cx = x0 + c_idx * col_w + col_w / 2

            lunar_txt = get_lunar_day_str(datetime.date(year, month, day)).split('月')[-1]

            is_today = (day == today)
            if is_today:
                # 当天实心黑块反白高亮
                cell_box = [
                    x0 + c_idx * col_w + 6,
                    curr_y - 2,
                    x0 + (c_idx + 1) * col_w - 6,
                    curr_y + row_h - 6,
                ]
                draw.rounded_rectangle(cell_box, radius=8, fill=0)
                # 白字
                draw.text((cx - 12 if day >= 10 else cx - 6, curr_y + 4), str(day), fill=255, font=font_day)
                draw.text((cx - 16, curr_y + 32), lunar_txt, fill=255, font=font_lunar)
            else:
                # 正常黑字
                draw.text((cx - 12 if day >= 10 else cx - 6, curr_y + 4), str(day), fill=0, font=font_day)
                draw.text((cx - 16, curr_y + 32), lunar_txt, fill=100, font=font_lunar)

def render_calendar_dashboard(
    output_path: str,
    battery: str = "未读取",
    quota_pct: int = 64,
    rotation: int = 270,
    quote: str = "“键盘还没关，心已经到家了。”",
    frontlight: int = 2,
    weather=None,
):
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y / %m / %d")
    weekday_map = {0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"}
    weekday_str = weekday_map.get(now.weekday(), "")
    lunar_header = get_lunar_day_str(now.date())

    # 字体
    font_top_title = get_font(32, bold=True)
    font_top_badge = get_font(24, bold=False)
    font_clock_huge = get_font(130, bold=True)
    font_date = get_font(26, bold=False)
    font_weather = get_font(36, bold=True)
    font_weather_sub = get_font(24, bold=False)
    font_quota_label = get_font(28, bold=True)
    font_quota_big = get_font(140, bold=True)
    font_quota_info = get_font(28, bold=False)
    font_cat_title = get_font(26, bold=True)
    font_cat_quote = get_font(24, bold=False)
    font_footer = get_font(22, bold=False)

    # 1. 顶部 Header
    draw.text((60, 45), "STARTER / 打工猫的工位", fill=0, font=font_top_title)
    draw.text((WIDTH - 380, 48), f"电量 {battery}（手工）", fill=40, font=font_top_badge)
    draw.line([60, 95, WIDTH - 60, 95], fill=0, width=2)

    # 2. 顶部时钟与天气块 (高度约 180px)
    draw.text((60, 110), time_str, fill=0, font=font_clock_huge)
    draw.text((440, 150), date_str, fill=0, font=font_date)
    draw.text((440, 195), weekday_str, fill=80, font=font_date)

    weather = weather or fetch_weather()
    draw.text((860, 120), f"{weather['city']} · {weather['cond']}", fill=0, font=font_weather_sub)
    draw.text((860, 160), weather['temp'], fill=0, font=font_weather)
    draw.text((1020, 172), weather['range'], fill=60, font=font_weather_sub)
    draw.text((860, 225), f"更新 {weather['update']}", fill=100, font=get_font(20))

    draw.line([60, 270, WIDTH - 60, 270], fill=210, width=1)

    # 3. 主体垂直分割
    split_x = 830
    draw.line([split_x, 270, split_x, 990], fill=210, width=1)

    # ── 左侧：额度与下班小猫 ──
    draw.text((60, 300), "每周额度 · 剩余", fill=0, font=font_quota_label)
    draw.text((split_x - 130, 305), "手工", fill=80, font=font_quota_label)

    # 大数字百分比
    draw.text((60, 350), f"{quota_pct}%", fill=0, font=font_quota_big)
    draw.text((480, 465), f"已用 {100 - quota_pct}%", fill=60, font=get_font(26))

    # 额度进度条
    bar_x0 = 60
    bar_x1 = split_x - 60
    bar_y0 = 540
    bar_y1 = 570
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=240, outline=0, width=2)
    fill_len = int((bar_x1 - bar_x0) * (quota_pct / 100.0))
    if fill_len > 0:
        draw.rectangle([bar_x0, bar_y0, bar_x0 + fill_len, bar_y1], fill=0)

    # 重置说明
    draw.text((60, 600), "进度可在工作台手动调整", fill=0, font=font_quota_info)
    draw.text((60, 645), "不读取个人账号或用量文件", fill=60, font=font_quota_info)

    draw.line([60, 710, split_x - 60, 710], fill=220, width=1)

    # 下班倒计时小猫盒子
    # 绘制可爱像素小猫与金句
    cat_box_y = 730
    # 小猫简笔画
    cx = 110
    cy = cat_box_y + 60
    draw.arc([cx - 30, cy - 10, cx + 30, cy + 30], 180, 360, fill=0, width=3)
    draw.polygon([(cx - 25, cy - 8), (cx - 32, cy - 22), (cx - 15, cy - 15)], fill=0)
    draw.polygon([(cx + 15, cy - 15), (cx + 32, cy - 22), (cx + 25, cy - 8)], fill=0)
    draw.arc([cx - 16, cy - 2, cx - 8, cy + 4], 0, 180, fill=0, width=2)
    draw.arc([cx + 8, cy - 2, cx + 16, cy + 4], 0, 180, fill=0, width=2)
    draw.line([cx - 4, cy + 10, cx + 4, cy + 10], fill=0, width=2)

    draw.text((180, cat_box_y + 15), "下班倒计时", fill=0, font=font_cat_title)
    draw.text((180, cat_box_y + 55), quote, fill=40, font=font_cat_quote)
    draw.text((180, cat_box_y + 95), "把今天的一件小事做好", fill=80, font=font_date)

    # ── 右侧：公农历双注月历与 Token 统计 ──
    rx = split_x + 35
    draw.text((rx, 300), f"{now.year}年 {now.month}月", fill=0, font=font_quota_label)
    draw.text((rx + 190, 305), lunar_header, fill=80, font=font_date)

    # 绘制日历网格 (高约 340px)
    cal_box = [rx, 340, WIDTH - 55, 690]
    draw_calendar_grid(draw, cal_box, now.year, now.month, now.day)

    draw.line([rx, 710, WIDTH - 55, 710], fill=220, width=1)

    # Token 用量
    draw.text((rx, 735), "本周小目标 / 示例", fill=0, font=font_cat_title)
    draw.text((rx, 785), "阅读 3 次 · 散步 2 次", fill=0, font=get_font(30, bold=True))
    draw.text((rx, 835), "整理书桌 · 给植物浇水", fill=0, font=get_font(30, bold=True))
    draw.text((rx, 895), "可通过分区编辑替换这些内容", fill=100, font=get_font(20))

    # 4. 底部通栏状态条
    draw.line([60, 1005, WIDTH - 60, 1005], fill=0, width=2)
    draw.text((60, 1025), "短按电源键退出 · 额度为手工值", fill=60, font=font_footer)
    draw.text((WIDTH // 2 - 60, 1025), f"前光 {frontlight}/24", fill=60, font=font_footer)
    draw.text((WIDTH - 280, 1025), f"天气: {weather['source']}", fill=60, font=font_footer)

    # 旋转以匹配物理屏
    rotated = img.rotate(rotation, expand=True)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    rotated.save(output_path, "PNG", optimize=True)
    print(f"Calendar Dashboard rendered to {output_path} ({rotated.size[0]}x{rotated.size[1]})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render Kindle Calendar Dashboard")
    default_out = os.path.join(os.path.dirname(__file__), "..", "assets", "dashboard_calendar.png")
    parser.add_argument("-o", "--output", default=os.path.abspath(default_out), help="Output PNG path")
    parser.add_argument("--battery", default="未读取", help="Device battery level")
    parser.add_argument("--quota", type=int, default=64, help="Quota percent")
    parser.add_argument("--rotation", type=int, default=270, help="Rotation angle (90 or 270)")
    args = parser.parse_args()

    render_calendar_dashboard(args.output, battery=args.battery, quota_pct=args.quota, rotation=args.rotation)
