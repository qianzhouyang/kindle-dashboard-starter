"""Validate the public file allowlist. Does not read user runtime directories."""
import hashlib
import json
import os
from pathlib import Path
import re

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'README.md', 'AGENTS.md', 'LICENSE', 'requirements.txt', 'requirements-lock.txt',
              '.gitignore', '.gitattributes', 'start_console.bat'}
GROUPS = {'src': {'.py', '.js', '.css'}, 'tests': {'.py'}, 'docs': {'.md'},
          'config': {'.json'}, 'scripts': {'.py', '.sh', '.example', '.xml', '.json'},
          'assets': {'.md', '.png', '.webp'}}
TEXT = {'.py', '.js', '.css', '.md', '.json', '.sh', '.xml', '.example', '.txt', '.bat'}


def files():
    result = [ROOT / name for name in ROOT_FILES if (ROOT / name).is_file()]
    for group, suffixes in GROUPS.items():
        for path in (ROOT / group).rglob('*'):
            if path.is_symlink():
                raise ValueError('Symlink is not allowed: ' + path.relative_to(ROOT).as_posix())
            if '__pycache__' in path.parts or not path.is_file():
                continue
            if path.suffix not in suffixes:
                raise ValueError('Unexpected file in share directory: ' + path.relative_to(ROOT).as_posix())
            result.append(path)
    return sorted(result)


def check():
    issues = []
    # Personal project markers, real-world private ranges, credential material.
    patterns = [r'(?i)C:[/\\](?:Users[/\\](?!Public\b)|Agents[/\\])',
                r'\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+\b',
                r'\b192\.168\.\d+\.\d+\b', r'\b10\.\d+\.\d+\.\d+\b',
                r'HA-\d{8}-', r'kindle_pw3_\d{8}',
                r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
                r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{30,}',
                r'sk-[A-Za-z0-9_-]{24,}', r'204\.84|16\.37']
    # The scanner necessarily contains these marker patterns itself.
    own_path = Path(__file__).resolve()
    private_markers = []
    if os.environ.get('KINDLE_SHARE_DENYLIST'):
        private_markers = json.loads(Path(os.environ['KINDLE_SHARE_DENYLIST']).read_text(encoding='utf-8'))
    for path in files():
        rel = path.relative_to(ROOT).as_posix()
        if path.name in ('device.json', 'console_config.json', 'weather_cache.json', 'network.conf'):
            issues.append(rel + ': runtime file')
        if path.suffix in TEXT or path.name in ('.gitignore', '.gitattributes', 'LICENSE'):
            text = path.read_text(encoding='utf-8')
            if path.resolve() != own_path:
                if any(marker.casefold() in text.casefold() for marker in private_markers):
                    issues.append(rel + ': local denylist match')
                for pattern in patterns:
                    if re.search(pattern, text):
                        issues.append(rel + ': private marker or credential pattern')
                        break
            if path.suffix == '.sh' and b'\r' in path.read_bytes():
                issues.append(rel + ': shell script must use LF')
        if path.suffix in ('.png', '.webp'):
            with Image.open(path) as image:
                if image.getexif() or any(k in image.info for k in ('exif', 'xmp', 'comment', 'XML:com.adobe.xmp')):
                    issues.append(rel + ': image metadata')
                if path.parent.name == 'mockups' and image.size not in ((1448, 1072), (1072, 1448)):
                    issues.append(rel + ': invalid display dimensions')
    if issues:
        raise ValueError('\n'.join(issues))
    return [{'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'bytes': p.stat().st_size} for p in files()]


if __name__ == '__main__':
    manifest = check()
    print(json.dumps({'ok': True, 'files': len(manifest), 'bytes': sum(f['bytes'] for f in manifest)}, indent=2))
