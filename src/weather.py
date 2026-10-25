"""Explicit demo/live weather, location-keyed cache outside the source tree."""
import datetime
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request

from starter_runtime import DATA_DIR


def validate_weather(value):
    if not isinstance(value, dict):
        raise ValueError('天气设置必须是对象')
    result = {'mode': value.get('mode', 'demo'), 'latitude': value.get('latitude'),
              'longitude': value.get('longitude')}
    if result['mode'] not in ('demo', 'live'):
        raise ValueError('天气模式应为 demo 或 live')
    for key, limit in [('latitude', 90), ('longitude', 180)]:
        number = result[key]
        if number is None and result['mode'] == 'demo':
            continue
        if isinstance(number, bool):
            raise ValueError('天气经纬度应为数字')
        try:
            number = float(number)
        except (ValueError, TypeError):
            raise ValueError('实时天气需要填写经纬度') from None
        if not math.isfinite(number) or not -limit <= number <= limit:
            raise ValueError('天气经纬度超出范围')
        result[key] = number
    return result


def fetch_weather(settings=None, city='示例城市'):
    settings = validate_weather(settings or {})
    demo = {'city': city, 'cond': '多云 · 示例', 'temp': '22°C',
            'range': '18–26°C · 示例', 'update': '示例', 'source': 'demo'}
    if settings['mode'] == 'demo':
        return demo
    key = hashlib.sha256(json.dumps([city, settings], sort_keys=True).encode()).hexdigest()[:20]
    cache = DATA_DIR / 'weather' / (key + '.json')
    cached = None
    try:
        cached = json.loads(cache.read_text(encoding='utf-8'))
        if 0 <= time.time() - cached['ts'] < 10800:
            return cached['data']
    except (OSError, ValueError, KeyError, TypeError):
        cached = None
    query = urllib.parse.urlencode({
        'latitude': settings['latitude'], 'longitude': settings['longitude'],
        'current': 'temperature_2m,weather_code',
        'daily': 'temperature_2m_max,temperature_2m_min', 'timezone': 'auto',
        'forecast_days': 1,
    })
    try:
        request = urllib.request.Request('https://api.open-meteo.com/v1/forecast?' + query,
                                         headers={'User-Agent': 'KindleDashboardStarter/0.1'})
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
        code = result['current']['weather_code']
        if code == 0:
            condition = '晴'
        elif code in (1, 2, 3):
            condition = '多云' if code != 3 else '阴'
        elif code in (45, 48):
            condition = '雾'
        elif 71 <= code <= 77 or code in (85, 86):
            condition = '雪'
        elif code >= 95:
            condition = '雷雨'
        else:
            condition = '雨'
        data = {'city': city, 'cond': condition,
                'temp': f"{round(result['current']['temperature_2m'])}°C",
                'range': f"{round(result['daily']['temperature_2m_min'][0])}–{round(result['daily']['temperature_2m_max'][0])}°C",
                'update': datetime.datetime.now().strftime('%m-%d %H:%M'), 'source': 'Open-Meteo'}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.tmp')
            temporary.write_text(json.dumps({'ts': time.time(), 'data': data}, ensure_ascii=False), encoding='utf-8')
            temporary.replace(cache)
        except OSError:
            pass  # Display live data even when the optional cache is unwritable.
        return data
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        if cached:
            return {**cached['data'], 'cond': cached['data']['cond'] + ' · 旧缓存', 'source': 'stale'}
        return {'city': city, 'cond': '天气获取失败', 'temp': '—',
                'range': '检查网络与经纬度', 'update': '未更新', 'source': 'unavailable'}
