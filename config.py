# config.py - 确保包含这些内容
import os
from pathlib import Path

VERSION = "0.0.1"
APP_NAME = "🎨 拼豆图纸生成器"

BASE_DIR = Path(__file__).parent
CORE_DIR = BASE_DIR / "core"
UI_DIR = BASE_DIR / "ui"
RESOURCES_DIR = BASE_DIR / "resources"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_FILE = BASE_DIR / "history.json"
SETTINGS_FILE = RESOURCES_DIR / "config.json"

# 确保目录存在
for directory in [RESOURCES_DIR, OUTPUT_DIR]:
    directory.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "theme": "light",
    "default_palette": "mard_221",
    "default_canvas_size": 1500,
    "default_grid_w": 50,
    "default_grid_h": 50,
    "show_grid": True,
    "grid_color": "#C8C8C8",
    "show_labels": True,
    "show_legend": True,
    "max_history_records": 50,
    "language": "zh-CN"
}


def get_platform() -> str:
    import platform
    import sys

    if hasattr(sys, 'getandroidapilevel'):
        return "android"

    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "android":
        return "android"
    else:
        return "windows"