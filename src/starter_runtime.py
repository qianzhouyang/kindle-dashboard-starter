"""User-owned runtime files and opt-in device access; no legacy data migration."""
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get('KINDLE_DASHBOARD_DATA_DIR',
                               Path.home() / '.kindle-dashboard-starter')).expanduser().resolve()


def device_config():
    path = DATA_DIR / 'device.json'
    if not path.is_file():
        raise ValueError('USB 尚未配置：请按 docs/02-kindle-usb.md 创建 device.json')
    try:
        cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('device.json 无法读取或不是有效 JSON') from exc
    if not isinstance(cfg, dict) or cfg.get('enabled') is not True:
        raise ValueError('USB 尚未启用：在 device.json 中明确设置 enabled 为 true')
    host, user = cfg.get('host', ''), cfg.get('user', 'root')
    if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', host):
        raise ValueError('请填写有效的 Kindle USB IPv4 地址或主机名')
    if not isinstance(user, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}', user):
        raise ValueError('SSH 用户名无效')
    port = cfg.get('port', 22)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('SSH 端口必须为 1–65535 的整数')
    paths = {}
    for field in ('identity_file', 'known_hosts_file'):
        value = cfg.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f'请设置 {field}')
        target = Path(value).expanduser()
        if not target.is_absolute() or not target.is_file():
            raise ValueError(f'{field} 必须指向本机已有文件，请使用绝对路径或 ~/ 路径')
        paths[field] = str(target)
    return {**cfg, **paths, 'host': host, 'user': user, 'port': port}


def connection():
    cfg = device_config()
    return cfg['identity_file'], cfg['known_hosts_file'], f"{cfg['user']}@{cfg['host']}"


def ssh_options(scp=False):
    cfg = device_config()
    options = ['-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
               '-P' if scp else '-p', str(cfg['port'])]
    if scp:
        options.insert(0, '-O')  # USBNetwork on older Kindles uses legacy SCP, not SFTP.
    return options
