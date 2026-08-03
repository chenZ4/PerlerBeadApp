# core/templates.py - 内置模板库（data/templates/*.json）
import json
import os

from PIL import Image

from .colors import get_palette

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "data", "templates")


def list_templates():
    templates = []
    if not os.path.isdir(TEMPLATE_DIR):
        return templates
    for filename in sorted(os.listdir(TEMPLATE_DIR)):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(TEMPLATE_DIR, filename), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (IOError, OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("pixels"):
            templates.append({
                "id": data.get("id", filename[:-5]),
                "name": data.get("name", filename[:-5]),
                "palette": data.get("palette", "mard_221"),
                "width": data.get("width", 0),
                "height": data.get("height", 0),
            })
    return templates


def load_template(template_id):
    """返回模板 dict（含 pixels）或 None"""
    path = os.path.join(TEMPLATE_DIR, f"{template_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    if not (isinstance(data, dict) and data.get("pixels")):
        return None
    return data


def template_to_image(template):
    """模板像素（色号）→ PIL RGB 图（空格 = 白色）"""
    palette = get_palette(template.get("palette", "mard_221"))
    code_to_rgb = {c: rgb for c, rgb in zip(palette.codes, palette.colors)}
    w = template.get("width", 0)
    h = template.get("height", 0)
    pixels = template.get("pixels", [])
    if not w or not h or len(pixels) != w * h:
        return None
    img = Image.new("RGB", (w, h), (255, 255, 255))
    px = img.load()
    for y in range(h):
        for x in range(w):
            code = pixels[y * w + x]
            if code and code in code_to_rgb:
                px[x, y] = code_to_rgb[code]
    return img
