# core/settings.py - 应用偏好持久化
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(BASE_DIR, "app_settings.json")

DEFAULTS = {
    "palette": "MARD 221 色",
    "cell_px": "60",
    "show_grid": True,
    "show_labels": True,
    "show_legend": True,
    "grid_color": "#C8C8C8",
    "ratio": "按原图比例（宽为基准）",
    "window_w": 0,
    "window_h": 0,
}


def load_settings():
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            settings.update(data)
    except Exception:
        pass
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


QUEUE_FILE = os.path.join(BASE_DIR, "queue_state.json")


def load_queue():
    try:
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [i for i in data if isinstance(i, dict)]
    except Exception:
        pass
    return []


def save_queue(items):
    try:
        with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
