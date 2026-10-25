#!/usr/bin/env python3
"""Kindle Dashboard Starter 墨水屏本地 Web 控制台。

轻量级本地网页管理平台：
1. 备选模板浏览与即时预览（猫的打工小屋 / 打工猫的工位 / 集群监控）；
2. 模块自定义设置（额度、金句、城市天气、旋转方向、前光）；
3. 一键发布与 USB SSH 立即远程刷屏；
4. 暴露 /kindle-dashboard.png 供 Kindle 客户端定时拉取。
"""

import argparse
import base64
import copy
import datetime
import io
import json
import os
import subprocess
import socket
import sys
import threading
import re
import uuid
from pathlib import Path
from starter_runtime import DATA_DIR, connection, ssh_options
from weather import fetch_weather, validate_weather
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageOps, UnidentifiedImageError

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 模块引入与路径自适应
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
LEGACY_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "console.example.json")
USER_DATA_DIR = DATA_DIR
CONFIG_FILE = str(USER_DATA_DIR / "console_config.json")
UPLOAD_DIR = USER_DATA_DIR / "uploads"
CONFIG_LOCK = threading.RLock()
RENDER_LOCK = threading.Lock()
DEVICE_LOCK = threading.Lock()
CURRENT_IMG = str(USER_DATA_DIR / "current_dashboard.png")

# Allow the device session to finish rendering or restoring the native screen.
MODE_SWITCH_TIMEOUT = 120
# KUAL and USB use the same device-side session and power-button listener.
DASHBOARD_REFRESH_COMMAND = "/mnt/us/dashboard/refresh.sh --once"
DASHBOARD_RESTORE_COMMAND = "/mnt/us/dashboard/refresh.sh --restore"

sys.path.insert(0, BASE_DIR)
from render_plan_b import render_plan_b_dashboard
from render_calendar import render_calendar_dashboard
from render_dashboard import render_dashboard
from dashboard_modules import schema as module_schema, validate_customizations, apply_customizations
from mockup_library import catalog as mockup_catalog, prepare_image as prepare_mockup

# 全局活跃配置
DEFAULT_CONFIG = {
    "template": "cat_office",      # cat_office, calendar, cluster
    "quota": 85,
    "quote": "“别催了，爪子都敲出火星了。”",
    "city": "示例城市",
    "weather": {"mode": "demo", "latitude": None, "longitude": None},
    "rotation": 270,               # 270: Logo在右, 90: Logo在左
    "battery": "未读取",
    "frontlight": 2,
    "last_published": "尚未发布",
    "customizations": {},
}
ACTIVE_CONFIG = copy.deepcopy(DEFAULT_CONFIG)


def validate_config(value):
    if not isinstance(value, dict):
        raise ValueError("配置必须是对象")
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update({key: copy.deepcopy(val) for key, val in value.items() if key in DEFAULT_CONFIG})
    if cfg['template'] not in ('cat_office', 'calendar', 'cluster'):
        raise ValueError("未知模板")
    for key, low, high in [('quota', 0, 100), ('frontlight', 0, 24), ('rotation', 90, 270)]:
        try:
            cfg[key] = int(cfg[key])
        except (ValueError, TypeError):
            raise ValueError(f"{key} 必须是数字") from None
        if not low <= cfg[key] <= high:
            raise ValueError(f"{key} 超出范围")
    if cfg['rotation'] not in (90, 270):
        raise ValueError("旋转方向应为 90 或 270")
    for key, maximum in [('quote', 300), ('city', 80), ('battery', 30)]:
        if not isinstance(cfg[key], str) or len(cfg[key]) > maximum:
            raise ValueError(f"{key} 内容过长或格式错误")
    cfg['weather'] = validate_weather(cfg['weather'])
    cfg['customizations'] = validate_customizations(cfg['customizations'])
    return cfg


def config_snapshot():
    with CONFIG_LOCK:
        return copy.deepcopy(ACTIVE_CONFIG)

def load_config():
    source = CONFIG_FILE if os.path.exists(CONFIG_FILE) else LEGACY_CONFIG_FILE
    if os.path.exists(source):
        try:
            with open(source, "r", encoding="utf-8") as f:
                cfg = validate_config(json.load(f))
            with CONFIG_LOCK:
                ACTIVE_CONFIG.clear(); ACTIVE_CONFIG.update(cfg)
            if source != CONFIG_FILE:
                save_config()
        except (OSError, ValueError, TypeError) as exc:
            print(f"配置读取失败，保留当前配置: {exc}")

def save_config():
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with CONFIG_LOCK:
        temporary = CONFIG_FILE + '.tmp'
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(ACTIVE_CONFIG, f, ensure_ascii=False, indent=2)
        os.replace(temporary, CONFIG_FILE)

def generate_image_bytes(cfg: dict) -> bytes:
    with RENDER_LOCK:
        return _generate_image_bytes(validate_config(cfg))


def _generate_image_bytes(cfg: dict) -> bytes:
    buf = io.BytesIO()
    tpl = cfg.get("template", "cat_office")
    quota = int(cfg.get("quota", 85))
    rotation = int(cfg.get("rotation", 270))
    battery = cfg.get("battery", "未读取")
    frontlight = int(cfg.get("frontlight", 2))
    quote = cfg.get("quote", "“别催了，爪子都敲出火星了。”")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    weather = fetch_weather(cfg["weather"], cfg["city"]) if tpl != "cluster" else None
    try:
        if tpl == "cat_office":
            render_plan_b_dashboard(tmp_path, battery=battery, frontlight=frontlight, quota_pct=quota, quote=quote, rotation=rotation, weather=weather)
        elif tpl == "calendar":
            render_calendar_dashboard(tmp_path, battery=battery, quota_pct=quota, rotation=rotation, quote=quote, frontlight=frontlight, weather=weather)
        else:
            render_dashboard(tmp_path, device_battery=battery)
        with Image.open(tmp_path) as im:
            rendered = apply_customizations(im.convert('L'), cfg, UPLOAD_DIR, ASSETS_DIR)
            rendered.save(buf, format='PNG', optimize=True)
        data = buf.getvalue()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return data

def trigger_ssh_refresh(cfg: dict = None, *, png_bytes=None) -> tuple[bool, str]:
    if not DEVICE_LOCK.acquire(blocking=False):
        return False, 'Kindle 正在推送或恢复，请等待当前操作完成后重试。'
    try:
        return _trigger_ssh_refresh(cfg, png_bytes=png_bytes)
    except ValueError as exc:
        return False, str(exc)
    finally:
        DEVICE_LOCK.release()


def _trigger_ssh_refresh(cfg: dict = None, *, png_bytes=None) -> tuple[bool, str]:
    if cfg is None:
        cfg = ACTIVE_CONFIG

    key_path, hosts_path, target = connection()

    # 1. 快速探测 SSH 连通性
    test_cmd = [
        "ssh", *ssh_options(), "-i", key_path,
        "-o", f"UserKnownHostsFile={hosts_path}",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=3",
        target,
        "echo 1"
    ]
    try:
        t_res = subprocess.run(test_cmd, capture_output=True, text=True, timeout=4)
        if t_res.returncode != 0:
            return False, "Kindle 未连接或未处于 USB 网络模式（请检查 Micro-USB 数据线是否已插入，并在 Kindle 搜索栏输入 ;un 开启网络）"
    except Exception as e:
        return False, f"Kindle USB SSH 连接超时: {e}"

    # 2. 生成目标图像并写入临时文件
    is_mockup = png_bytes is not None
    if png_bytes is None:
        png_bytes = generate_image_bytes(cfg)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name

    try:
        # 3. 通过 SCP 传输图像
        scp_cmd = [
            "scp", *ssh_options(scp=True), "-i", key_path,
            "-o", f"UserKnownHostsFile={hosts_path}",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            tmp_path,
            target + ":/mnt/us/dashboard/" +
            ("mockup-upload.png" if is_mockup else "dashboard.png")
        ]
        scp_res = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=10)
        if scp_res.returncode != 0:
            return False, f"传输图像失败: {scp_res.stderr.strip()}"

        # 4. 前光亮度调节 (若配置了 frontlight)
        fl = cfg.get("frontlight")
        if fl is not None:
            fl_cmd = [
                "ssh", *ssh_options(), "-i", key_path,
                "-o", f"UserKnownHostsFile={hosts_path}",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=4",
                target,
                f"lipc-set-prop com.lab126.powerd flIntensity {fl} 2>/dev/null"
            ]
            subprocess.run(fl_cmd, capture_output=True, text=True, timeout=5)

        # 5. 等待统一设备会话完成切换与刷屏（会话负责按键监听）。
        # Hold the static mockup in cached mode: stop any automatic refresh first.
        # Transfer to a staging file, then replace the display cache atomically.
        command = DASHBOARD_REFRESH_COMMAND
        if is_mockup:
            command = (DASHBOARD_RESTORE_COMMAND +
                       " && mv /mnt/us/dashboard/mockup-upload.png /mnt/us/dashboard/dashboard.png && " +
                       DASHBOARD_REFRESH_COMMAND)
        refresh_cmd = [
            "ssh", *ssh_options(), "-i", key_path,
            "-o", f"UserKnownHostsFile={hosts_path}",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            target,
            command
        ]
        ref_res = subprocess.run(refresh_cmd, capture_output=True, text=True, timeout=MODE_SWITCH_TIMEOUT)
        if ref_res.returncode == 0:
            if is_mockup:
                return True, 'Mockup 已传输，设备刷屏命令完成。请查看 Kindle 实际效果；短按电源或点击“恢复阅读”退出试屏。'
            return True, "图像已传输，设备刷屏命令完成；请查看 Kindle 实际显示。"
        return False, f"刷屏脚本执行失败: {ref_res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "推送等待超时，尚未确认切换与刷屏完成；请检查 Kindle 画面和 refresh.log。"
    except Exception as e:
        return False, f"推送异常: {e}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def trigger_ssh_restore() -> tuple[bool, str]:
    if not DEVICE_LOCK.acquire(blocking=False):
        return False, 'Kindle 正在推送或恢复，请等待当前操作完成后重试。'
    try:
        return _trigger_ssh_restore()
    except ValueError as exc:
        return False, str(exc)
    finally:
        DEVICE_LOCK.release()


def _trigger_ssh_restore() -> tuple[bool, str]:
    key_path, hosts_path, target = connection()
    cmd = [
        "ssh", *ssh_options(), "-i", key_path,
        "-o", f"UserKnownHostsFile={hosts_path}",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        target,
        DASHBOARD_RESTORE_COMMAND
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=MODE_SWITCH_TIMEOUT)
        if res.returncode == 0:
            return True, "已成功恢复 Kindle 原版图书阅读界面！"
        return False, f"恢复失败: {res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "恢复阅读等待超时，尚未确认原生界面恢复；请检查 Kindle 当前画面。"
    except Exception as e:
        return False, f"恢复执行异常: {e}"

def check_kindle_online() -> bool:
    try:
        key_path, hosts_path, target = connection()
    except ValueError:
        return False
    cmd = [
        "ssh", *ssh_options(), "-i", key_path,
        "-o", f"UserKnownHostsFile={hosts_path}",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=2",
        target,
        "echo 1"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kindle Dashboard Starter E-Ink 控制台</title>
<style>
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --accent-hover: #0ea5e9;
    --success: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px;
  }
  header h1 { font-size: 24px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
  .badge { background: #334155; padding: 4px 10px; border-radius: 9999px; font-size: 13px; color: var(--accent); }
  .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; background: #64748b; }
  .status-dot.online { background: var(--success); box-shadow: 0 0 8px var(--success); }

  .layout { display: grid; grid-template-columns: 460px 1fr; gap: 32px; }
  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px;
  }
  .card h2 { font-size: 16px; color: var(--muted); margin-bottom: 14px; text-transform: uppercase; letter-spacing: 0.5px; }

  /* 模板卡片选择器 */
  .template-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 16px; }
  .template-btn {
    background: #0f172a; border: 2px solid var(--border); border-radius: 8px; padding: 12px 8px;
    color: var(--text); cursor: pointer; text-align: center; transition: all 0.2s; font-size: 13px;
  }
  .template-btn:hover { border-color: var(--accent); }
  .template-btn.active { border-color: var(--accent); background: #0369a1; font-weight: 700; }
  .template-btn span { font-size: 20px; display: block; margin-bottom: 4px; }

  /* 表单项 */
  .form-group { margin-bottom: 16px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
  input[type="text"], input[type="range"], select {
    width: 100%; background: #0f172a; border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 12px; color: var(--text); font-size: 14px;
  }
  .slider-val { display: inline-block; width: 45px; text-align: right; color: var(--accent); font-weight: bold; }

  /* 按钮动作 */
  .btn-group { display: flex; gap: 12px; margin-top: 20px; }
  button.action-btn {
    flex: 1; padding: 12px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer;
    transition: all 0.2s; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px;
  }
  .btn-preview { background: #334155; color: #fff; }
  .btn-preview:hover { background: #475569; }
  .btn-publish { background: var(--accent); color: #0f172a; }
  .btn-publish:hover { background: var(--accent-hover); }
  .btn-push { background: #10b981; color: #fff; }
  .btn-push:hover { background: #059669; }

  /* 墨水屏拟真预览区 */
  .preview-wrapper { text-align: center; }
  .kindle-frame {
    display: inline-block; background: #18181b; padding: 32px 42px 32px 28px;
    border-radius: 24px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7);
    border: 3px solid #27272a; position: relative; transition: padding 0.3s ease;
  }
  .kindle-brand {
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%) rotate(90deg);
    color: #52525b; font-size: 14px; font-weight: 700; letter-spacing: 2px;
    transition: all 0.3s ease;
  }
  .kindle-frame.logo-left {
    padding: 32px 28px 32px 42px;
  }
  .kindle-frame.logo-left .kindle-brand {
    right: auto;
    left: 12px;
    transform: translateY(-50%) rotate(-90deg);
  }
  .kindle-screen {
    width: 724px; height: 536px; background: #e5e5e5; border-radius: 4px;
    overflow: hidden; border: 1px solid #71717a; box-shadow: inset 0 2px 6px rgba(0,0,0,0.3);
  }
  .kindle-screen img {
    width: 100%; height: 100%; object-fit: contain; filter: contrast(1.05); display: block;
  }
  .toast {
    margin-top: 12px; padding: 8px 12px; border-radius: 6px; font-size: 13px; display: none;
  }
  .toast.success { background: #064e3b; color: #6ee7b7; display: block; }
  .toast.error { background: #7f1d1d; color: #fca5a5; display: block; }
</style>
<link rel="stylesheet" href="/workbench.css">
</head>
<body>
<div class="container">
  <header>
    <h1>🐱 Kindle Dashboard Starter 墨水屏控制台 <span class="badge">PW3 · 本地版</span></h1>
    <div style="display:flex; align-items:center; gap:16px;">
      <span id="connStatus"><span class="status-dot"></span> 检测中...</span>
      <span class="badge" id="lastPublishedTime">上次发布: 加载中</span>
    </div>
  </header>

  <details class="card mockup-panel" id="mockupPanel" open>
    <summary>Mockup 试屏 <span>示例数据 · 整张图片通过 USB 显示</span></summary>
    <div class="mockup-layout">
      <div class="mockup-controls">
        <div class="form-group"><label for="mockupChoice">选择预制示例图</label><select id="mockupChoice" disabled><option>正在加载示例图…</option></select></div>
        <div class="form-group"><label for="mockupRotation">横屏摆放方向</label><select id="mockupRotation"><option value="270">Logo 在右边框（270°）</option><option value="90">Logo 在左边框（90°）</option></select></div>
        <p id="mockupDimensions" class="help"></p>
        <div class="form-group"><label for="mockupUpload">或上传整屏图片（PNG / JPEG / WebP，最大 8 MiB）</label><input id="mockupUpload" type="file" accept="image/png,image/jpeg,image/webp"><p class="help">横屏 1448 × 1072，竖屏 1072 × 1448；横屏请用正常阅读方向的原图。</p></div>
        <div class="secondary-actions"><button type="button" class="action-btn btn-push" id="mockupPush" disabled>推送这张图 · USB</button><button type="button" class="action-btn btn-preview" id="mockupRestore">恢复阅读</button></div>
        <p class="help">静态试屏会暂停设备自动刷新，保持当前前光，不修改已保存的工作台配置。退出后可在 Kindle 的 KUAL 中重新开启自动模式。</p>
        <p id="mockupStatus" class="mockup-status" role="status" aria-live="polite">所有时间、天气与额度均为样稿示例数据。</p>
      </div>
      <figure class="mockup-preview"><img id="mockupPreview" alt="当前选中 mockup 的整屏预览" hidden><figcaption id="mockupCaption"></figcaption></figure>
    </div>
  </details>
  <div class="layout">
    <div class="controls">
      <div class="card">
        <h2>1 · 选择版式</h2>
        <div class="template-grid">
          <button type="button" class="template-btn" data-template="cat_office" onclick="setTemplate('cat_office')"><span>🐱</span>打工小屋</button>
          <button type="button" class="template-btn" data-template="calendar" onclick="setTemplate('calendar')"><span>📅</span>双历工位</button>
          <button type="button" class="template-btn" data-template="cluster" onclick="setTemplate('cluster')"><span>🖥️</span>集群监控</button>
        </div>
      </div>
      <div class="card" id="moduleEditor">
        <h2>2 · 分区定制</h2>
        <p class="help">选择一个区域，再选择模块、填写内容。也可以直接点击右侧预览中的区域。</p>
        <div id="regionList" class="region-grid" aria-label="画面区域"></div>
        <div class="editor-title"><strong id="editorRegionName">正在加载…</strong><button type="button" class="small-button" onclick="resetRegion()">恢复此区域</button></div>
        <div class="form-group"><label for="moduleType">内容模块</label><select id="moduleType" onchange="setModule('type',this.value)"></select></div>
        <p id="inheritHelp" class="help">保留模板原有画面。选择其他模块后，只替换这个区域的内容。</p>
        <div class="form-group" id="titleField" hidden><label for="moduleTitle">区域标题（可留空）</label><input type="text" id="moduleTitle" maxlength="100" placeholder="例如：今日重点" oninput="setModule('title',this.value)"></div>
        <div class="form-group" id="valueField" hidden><label id="moduleValueLabel" for="moduleValue">数值或重点文字</label><input type="text" id="moduleValue" maxlength="120" oninput="setModule('value',this.value)"></div>
        <div class="form-group" id="textField" hidden>
          <label id="moduleTextLabel" for="moduleText">内容 / 补充说明</label>
          <textarea id="moduleText" maxlength="2000" rows="5" placeholder="输入自己的文字、计划或清单，每行一项。" oninput="setModule('text',this.value)"></textarea>
          <div class="token-row" id="tokenButtons" aria-label="插入动态内容"></div>
          <p class="help"><span id="textCount">0 / 2000</span> · 点击变量插入实时内容；文字自动换行，过长时缩小或省略。</p>
        </div>
        <div id="imageField" hidden>
          <div class="form-group"><label for="imageChoice">图片素材</label><select id="imageChoice" onchange="setModule('image_id',this.value)"></select></div>
          <img id="imageThumb" class="image-thumb" alt="当前图片素材">
          <div class="form-group"><label for="imageUpload">上传自己的图片（PNG / JPEG / WebP，最大 8 MiB）</label><input id="imageUpload" type="file" accept="image/png,image/jpeg,image/webp" onchange="uploadImage(this.files[0])"><p id="uploadStatus" class="help" role="status"></p></div>
          <div class="form-group"><label for="imageFit">图片适应方式</label><select id="imageFit" onchange="setModule('fit',this.value)"><option value="contain">完整显示，保留留白</option><option value="cover">填满区域，居中裁切</option></select></div>
        </div>
        <div class="field-pair" id="formatFields" hidden>
          <div class="form-group"><label for="moduleFont">正文字号 <span id="moduleFontValue">32 px</span></label><input type="range" id="moduleFont" min="18" max="72" value="32" oninput="setModule('font_size',Number(this.value))"></div>
          <div class="form-group"><label for="moduleAlign">文字对齐</label><select id="moduleAlign" onchange="setModule('align',this.value)"><option value="left">左对齐</option><option value="center">居中</option></select></div>
        </div>
        <button type="button" class="small-button" onclick="resetTemplate()">恢复当前版式的全部默认模块</button>
      </div>
      <details class="card global-settings">
        <summary>3 · 全局数据与设备参数</summary>
        <div>
          <div class="form-group"><label for="quotaInput">全局额度 / 进度 <span id="quotaVal" class="slider-val">85%</span></label><input type="range" id="quotaInput" min="0" max="100" value="85" oninput="editGlobal()"></div>
          <div class="form-group"><label for="quoteInput">默认台词 / 金句</label><input type="text" id="quoteInput" maxlength="300" value="“别催了，爪子都敲出火星了。”" oninput="editGlobal()"></div>
          <div class="form-group"><label for="rotationInput">横屏旋转方向</label><select id="rotationInput" onchange="editGlobal()"><option value="270">Logo 在右边框（270°）</option><option value="90">Logo 在左边框（90°）</option></select></div>
          <div class="form-group"><label for="frontlightInput">前光亮度（0–24）</label><select id="frontlightInput" onchange="editGlobal()"><option value="0">0 · 关闭</option><option value="2">2 · 微弱柔光</option><option value="8">8 · 暗光阅读</option><option value="14">14 · 常规亮度</option><option value="20">20 · 高亮</option><option value="24">24 · 最高亮度</option></select></div>
          <div class="form-group"><label for="cityInput">天气城市（显示名称）</label><input id="cityInput" type="text" maxlength="80" oninput="editGlobal()"></div>
        <div class="form-group"><label for="weatherMode">天气来源</label><select id="weatherMode" onchange="editGlobal()"><option value="demo">示例天气（离线）</option><option value="live">Open-Meteo 实时天气</option></select></div>
        <div class="form-group"><label for="latitudeInput">纬度（实时天气必填）</label><input id="latitudeInput" type="text" inputmode="decimal" oninput="editGlobal()"></div>
        <div class="form-group"><label for="longitudeInput">经度（实时天气必填）</label><input id="longitudeInput" type="text" inputmode="decimal" oninput="editGlobal()"></div>
        <p class="help">默认离线示例。实时天气每三小时缓存；城市名称不自动查询坐标。额度、电量为手工值；前光在 USB 推送时应用。</p>
        </div>
      </details>
      <div class="card actions">
        <div class="btn-group"><button class="action-btn btn-preview" onclick="refreshPreview()">刷新预览</button><button class="action-btn btn-publish" onclick="publishConfig()">保存并发布</button></div>
        <div class="secondary-actions"><button class="action-btn btn-push" onclick="pushNow()">立即推送 · USB</button><button class="action-btn" style="background:#475569;color:white" onclick="restoreKindle()">恢复阅读</button></div>
        <p class="help">修改先预览，保存后供 Kindle 下次联网刷新。立即推送需要 USB 网络连接。</p>
        <div id="toast" class="toast" role="status" aria-live="polite"></div>
      </div>
    </div>
    <div class="preview-wrapper">
      <div class="card preview-card">
        <div class="preview-heading"><h2>画布预览</h2><span id="saveState" class="save-state">正在加载配置…</span></div>
        <div class="kindle-frame" id="kindleFrame">
          <div class="kindle-brand">kindle</div>
          <div class="kindle-screen" id="kindleScreen">
            <img id="previewImg" alt="Kindle 看板预览">
            <div id="regionOverlay" class="region-overlays"></div>
            <div id="previewLoading" class="preview-loading">正在生成预览…</div>
          </div>
        </div>
        <div class="canvas-meta"><span id="canvasSize">1448 × 1072</span><label class="check-row"><input type="checkbox" id="regionOverlayToggle" checked>显示分区边框</label></div>
        <p id="selectedRegionLabel" class="help" style="text-align:left"></p>
        <p id="previewStatus" class="sr-status" role="status"></p>
        <p class="help endpoint">Kindle 拉取地址：<code>http://&lt;电脑局域网IP&gt;:__SERVER_PORT__/kindle-dashboard.png</code></p>
      </div>
    </div>
  </div>
</div>

<script src="/workbench.js" defer></script>
<script src="/mockups.js" defer></script>
</body>
</html>
"""

class WebConsoleHandler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def send_png(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def read_json(self, limit=262144):
        origin = self.headers.get('Origin')
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get('Host'):
            raise ValueError('请从工作台本身提交修改')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('请求长度无效') from None
        if size < 0 or size > limit:
            raise ValueError('内容过大，请减少文字或压缩图片后重试')
        try:
            value = json.loads(self.rfile.read(size) or b'{}')
        except (ValueError, UnicodeDecodeError):
            raise ValueError('请求不是有效的 JSON') from None
        if not isinstance(value, dict):
            raise ValueError('请求必须是对象')
        return value

    def preview(self, cfg):
        data = generate_image_bytes(cfg)
        if cfg['template'] != 'cluster':
            with Image.open(io.BytesIO(data)) as image:
                image = image.rotate(-int(cfg['rotation']), expand=True)
                output = io.BytesIO(); image.save(output, 'PNG')
                data = output.getvalue()
        self.send_png(data)

    def management_allowed(self):
        # LAN clients can fetch only the PNG; personal editor content stays local.
        try:
            host = urllib.parse.urlsplit('//' + self.headers.get('Host', '')).hostname
        except ValueError:
            return False
        return self.client_address[0] in ('127.0.0.1', '::1') and host in ('localhost', '127.0.0.1', '::1')

    def builtin_image(self, name):
        with Image.open(Path(ASSETS_DIR) / 'illustrations' / name) as image:
            output = io.BytesIO()
            image.convert('L').save(output, 'PNG')
            self.send_png(output.getvalue())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path not in ('/kindle-dashboard.png', '/dashboard.png') and not self.management_allowed():
            self.send_error(403, 'Editor access is local only'); return
        try:
            if path == '/':
                data = HTML_PAGE.replace('__SERVER_PORT__', str(self.server.server_port)).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
            elif path in ('/workbench.js', '/workbench.css', '/mockups.js'):
                content = (Path(BASE_DIR) / path[1:]).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(content)
            elif path == '/api/builtin-cat.png':
                self.builtin_image('work-side.webp')
            elif path == '/api/builtin-home.png':
                self.builtin_image('home-wide.webp')
            elif path == '/api/builtin-work.png':
                self.builtin_image('work-wide.webp')
            elif path == '/api/status':
                cfg = config_snapshot()
                self.send_json({'online': check_kindle_online(), 'config': cfg,
                                'last_published': cfg.get('last_published', '尚未发布')})
            elif path == '/api/module-schema':
                self.send_json(module_schema())
            elif path == '/api/mockups':
                self.send_json({'items': mockup_catalog(), 'default_id': 'D-life-household'})
            elif path == '/api/mockup-preview':
                self.send_png(prepare_mockup(qs.get('id', [''])[0], UPLOAD_DIR, preview=True))
            elif path == '/api/preview':
                cfg = config_snapshot()
                for key in ('template', 'quota', 'quote', 'rotation', 'frontlight'):
                    if key in qs:
                        cfg[key] = qs[key][0]
                self.preview(validate_config(cfg))
            elif path in ('/kindle-dashboard.png', '/dashboard.png'):
                self.send_png(generate_image_bytes(config_snapshot()))
            elif path.startswith('/api/assets/'):
                image_id = path.removeprefix('/api/assets/')
                if not re.fullmatch(r'[a-f0-9]{32}\.png', image_id) or not (UPLOAD_DIR / image_id).is_file():
                    self.send_error(404)
                else:
                    self.send_png((UPLOAD_DIR / image_id).read_bytes())
            else:
                self.send_error(404)
        except (ValueError, TypeError) as exc:
            self.send_json({'ok': False, 'error': str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def upload_image(self, payload):
        data = payload.get('data', '')
        if not isinstance(data, str):
            raise ValueError('图片数据格式错误')
        if data.startswith('data:'):
            prefix, separator, data = data.partition(',')
            if not separator or prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
                raise ValueError('支持 PNG、JPEG 和 WebP 图片')
        try:
            raw = base64.b64decode(data, validate=True)
        except ValueError:
            raise ValueError('图片编码无效') from None
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('图片最大为 8 MiB')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 20000000:
                    raise ValueError('请使用 2000 万像素以内的 PNG、JPEG 或 WebP 图片')
                image = ImageOps.exif_transpose(image)
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    foreground = image.convert('RGBA')
                    background = Image.new('RGBA', image.size, 'white')
                    background.alpha_composite(foreground); image = background
                image = image.convert('L')
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                image_id = uuid.uuid4().hex + '.png'
                with (UPLOAD_DIR / image_id).open('xb') as output:
                    image.save(output, 'PNG', optimize=True)
                self.send_json({'ok': True, 'id': image_id, 'url': '/api/assets/' + image_id,
                                'width': image.width, 'height': image.height})
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
            raise ValueError('无法读取图片，请使用有效的 PNG、JPEG 或 WebP 文件') from None

    def do_POST(self):
        if not self.management_allowed():
            self.send_error(403, 'Editor access is local only'); return
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == '/api/upload-image':
                self.upload_image(self.read_json(12 * 1024 * 1024)); return
            data = self.read_json()
            if path == '/api/preview':
                cfg = config_snapshot(); cfg.update(data)
                self.preview(validate_config(cfg))
            elif path == '/api/push-mockup':
                png = prepare_mockup(data.get('id'), UPLOAD_DIR, data.get('rotation', 270))
                # No config save, publication timestamp, brightness change or render.
                ok, message = trigger_ssh_refresh({}, png_bytes=png)
                self.send_json({'ok': ok, 'message': message}, 200 if ok else 503)
            elif path in ('/api/publish', '/api/push_now'):
                cfg = config_snapshot(); cfg.update(data)
                cfg = validate_config(cfg)
                png = generate_image_bytes(cfg)
                cfg['last_published'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with CONFIG_LOCK:
                    previous = config_snapshot()
                    ACTIVE_CONFIG.clear(); ACTIVE_CONFIG.update(cfg)
                    try:
                        save_config()
                    except OSError:
                        ACTIVE_CONFIG.clear(); ACTIVE_CONFIG.update(previous)
                        raise
                with open(CURRENT_IMG, 'wb') as output:
                    output.write(png)
                if path == '/api/push_now':
                    ok, message = trigger_ssh_refresh(cfg)
                    if not ok:
                        message = '配置已保存；' + message
                    self.send_json({'ok': ok, 'message': message})
                else:
                    self.send_json({'ok': True, 'last_published': cfg['last_published']})
            elif path == '/api/restore_kindle':
                ok, message = trigger_ssh_restore()
                self.send_json({'ok': ok, 'message': message}, 200 if ok else 500)
            else:
                self.send_error(404)
        except (ValueError, TypeError) as exc:
            self.send_json({'ok': False, 'error': str(exc), 'message': str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            self.send_json({'ok': False, 'error': '无法保存到本机，请检查磁盘空间和目录权限'}, 500)

    def log_message(self, format, *args):
        pass


class WorkbenchHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits two listeners to silently share one port.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def run_console(host="127.0.0.1", port=8001):
    load_config()
    server_address = (host, port)
    httpd = WorkbenchHTTPServer(server_address, WebConsoleHandler)
    print(f"\n========================================================")
    print(f" Kindle Dashboard Starter 控制台已启动!")
    print(f" 本机网页控制台:   http://localhost:{port}")
    print(f" Kindle 拉取端点:  http://<局域网IP>:{port}/kindle-dashboard.png")
    print(f"========================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭控制台服务...")
        httpd.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kindle Dashboard Starter Local Web Console")
    parser.add_argument("--host", default="127.0.0.1", help="Listen host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="Listen port (default 8001)")
    args = parser.parse_args()
    run_console(args.host, args.port)
