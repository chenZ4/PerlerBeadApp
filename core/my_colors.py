# core/my_colors.py - 用户自定义调色板（My Colors）
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MY_COLORS_FILE = os.path.join(BASE_DIR, "my_colors.json")


def load_my_colors():
    """返回色卡结构 dict（display/internal/colors/names/codes）或 None"""
    try:
        with open(MY_COLORS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    colors = data.get("colors")
    if not isinstance(colors, list) or not colors:
        return None
    return {
        "display": "我的颜色",
        "internal": "my_colors",
        "colors": colors,
        "names": data.get("names", []),
        "codes": data.get("codes", []),
    }


def save_my_colors(colors, names=None, codes=None):
    """colors: [[r,g,b],...]；names/codes 可选"""
    names = names if names is not None else []
    codes = codes if codes is not None else []
    data = {"colors": [list(c) for c in colors],
            "names": list(names), "codes": list(codes)}
    with open(MY_COLORS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return True


def clear_my_colors():
    if os.path.exists(MY_COLORS_FILE):
        os.remove(MY_COLORS_FILE)
