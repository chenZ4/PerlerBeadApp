# config.py - 全局配置
import os
from pathlib import Path

# 版本信息
VERSION = "1.0.0"
APP_NAME = "🎨 拼豆图纸生成器"

# 路径配置
BASE_DIR = Path(__file__).parent
RESOURCES_DIR = BASE_DIR / "resources"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_FILE = BASE_DIR / "history.json"
SETTINGS_FILE = RESOURCES_DIR / "config.json"

# 确保目录存在
for directory in [RESOURCES_DIR, OUTPUT_DIR, RESOURCES_DIR / "fonts", RESOURCES_DIR / "icons"]:
    directory.mkdir(exist_ok=True)

# 默认设置
DEFAULT_SETTINGS = {
    "theme": "light",  # light / dark
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

# 支持的平台
SUPPORTED_PLATFORMS = ["windows", "android", "web"]