# core/my_colors.py - 用户自定义调色板（My Colors）
import json
import os

from .colors import _validate
from .models import atomic_write_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MY_COLORS_FILE = os.path.join(BASE_DIR, "my_colors.json")


def _build_palette(data):
    palette = {
        "display": "我的颜色",
        "internal": "my_colors",
        "colors": data.get("colors", []),
        "names": data.get("names", []),
        "codes": data.get("codes", []),
    }
    return palette if _validate(palette) else None


def load_my_colors():
    """返回色卡结构 dict（display/internal/colors/names/codes）或 None"""
    try:
        with open(MY_COLORS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return _build_palette(data)


def save_my_colors(colors, names=None, codes=None):
    """colors: [[r,g,b],...]；names/codes 可选；非法数据拒绝写入返回 False"""
    names = names if names is not None else []
    codes = codes if codes is not None else []
    try:
        data = {"colors": [list(c) for c in colors],
                "names": list(names), "codes": list(codes)}
    except TypeError:
        return False
    if _build_palette(data) is None:
        return False
    atomic_write_json(MY_COLORS_FILE, data, indent=1)
    return True


def clear_my_colors():
    if os.path.exists(MY_COLORS_FILE):
        os.remove(MY_COLORS_FILE)
