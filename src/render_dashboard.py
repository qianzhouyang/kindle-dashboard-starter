#!/usr/bin/env python3
"""A portrait node-status template with documentation-only sample addresses."""
import argparse
import datetime
from pathlib import Path

from PIL import Image, ImageDraw
from render_plan_b import get_font

WIDTH, HEIGHT = 1072, 1448


def render_dashboard(output_path, device_battery='未读取', **kwargs):
    image = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    now = datetime.datetime.now()

    def text(x, y, value, size=28, bold=False, fill=0):
        draw.text((x, y), value, font=get_font(size, bold), fill=fill)

    def card(top, bottom, title):
        draw.rounded_rectangle((30, top, 1042, bottom), radius=16, outline=0, width=3)
        text(60, top + 18, title, 32, True)
        draw.line((60, top + 70, 1012, top + 70), fill=0, width=2)

    card(30, 340, '我的设备看板 / 演示')
    text(60, 120, now.strftime('%H:%M'), 120, True)
    text(60, 275, now.strftime('%Y-%m-%d') + '  星期' + '一二三四五六日'[now.weekday()])
    text(680, 145, 'Kindle PW3', 32, True)
    text(680, 200, '电量：' + device_battery, 24)
    text(680, 242, '手工显示值 · 非遥测', 22, fill=80)

    card(370, 760, '节点示例 / 未连接监控系统')
    nodes = [('demo-server', 'Linux', '192.0.2.10', '示例'),
             ('demo-storage', 'Storage', '192.0.2.20', '示例'),
             ('demo-desktop', 'Desktop', '192.0.2.30', '示例'),
             ('demo-gateway', 'Router', '192.0.2.1', '示例')]
    for index, (name, system, address, status) in enumerate(nodes):
        y = 480 + index * 60
        for x, value in [(60, name), (365, system), (630, address), (900, status)]:
            text(x, y, value, 26)

    card(790, 1150, '下一步 / 个人清单示例')
    for index, value in enumerate(['□ 修改标题和说明', '□ 上传自己的插画',
                                   '□ 配置自己的 Kindle USB 连接', '□ 实机验证返回阅读功能']):
        text(60, 890 + index * 52, value, 29)

    card(1180, 1398, '使用说明')
    text(60, 1270, '示例地址不可用于连接实际设备。', 26)
    text(60, 1315, '时间来自电脑；节点、额度和电量需自行填写。', 26)
    text(60, 1410, 'Kindle Dashboard Starter · 示例数据 · ' + now.strftime('%H:%M'), 20, fill=80)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'PNG', optimize=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o', '--output', default='dashboard-cluster.png')
    args = parser.parse_args()
    render_dashboard(args.output)
