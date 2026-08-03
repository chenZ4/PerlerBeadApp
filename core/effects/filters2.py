# core/effects/filters2.py - 滤镜特效 v2
import numpy as np
from PIL import Image, ImageEnhance

from .base import EffectSpec
from .registry import register


def _hex_rgb(value, default):
    text = str(value).strip().lstrip('#')
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    return default


def _cel_shade(img, params, ctx):
    """赛璐璐：亮度分桶色阶化，漫画风"""
    levels = int(params.get("levels", 4))
    levels = max(2, min(levels, 16))
    arr = np.asarray(img.convert("L"), dtype=np.float32)
    bucket = np.floor(arr / (256.0 / levels)) * (256.0 / levels)
    out = np.clip(bucket, 0, 255).astype(np.uint8)
    return Image.fromarray(np.repeat(out[:, :, None], 3, axis=2))


register(EffectSpec(
    id="cel_shade",
    name="赛璐璐色阶",
    category="preprocess",
    params={"levels": {"type": "int", "default": 4, "min": 2, "max": 16}},
    description="亮度分桶色阶化，漫画赛璐璐风格",
), _cel_shade)


def _neon(img, params, ctx):
    """霓虹：暗底 + 高饱和荧光感"""
    sat = float(params.get("saturation", 1.5))
    dark = float(params.get("darkness", 0.75))
    out = ImageEnhance.Color(img).enhance(sat)
    out = ImageEnhance.Brightness(out).enhance(dark)
    return out


register(EffectSpec(
    id="neon",
    name="霓虹",
    category="preprocess",
    params={
        "saturation": {"type": "float", "default": 1.5, "min": 1.0, "max": 2.5},
        "darkness": {"type": "float", "default": 0.75, "min": 0.4, "max": 1.0},
    },
    description="深色底 + 高饱和荧光感（配合深色底图纸效果最佳）",
), _neon)


def _duotone(img, params, ctx):
    """双色调：灰度映射到双色渐变，复古海报感"""
    c1 = _hex_rgb(params.get("color1"), (30, 30, 30))
    c2 = _hex_rgb(params.get("color2"), (240, 240, 240))
    arr = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    t = arr[..., None]
    out = (np.asarray(c1, dtype=np.float32) * (1 - t)
           + np.asarray(c2, dtype=np.float32) * t)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


register(EffectSpec(
    id="duotone",
    name="双色调",
    category="preprocess",
    params={
        "color1": {"type": "color", "default": "#1E1E1E"},
        "color2": {"type": "color", "default": "#F0F0F0"},
    },
    description="灰度双色渐变，复古海报感",
), _duotone)


def _bg_remove(img, params, ctx):
    """背景去除：匹配背景色 → 透明（透明格 = 空格，无珠）"""
    target = _hex_rgb(params.get("color", "#FFFFFF"), (255, 255, 255))
    tol = int(params.get("tolerance", 30))
    tol = max(0, min(tol, 255))
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).astype(np.int32).copy()
    dist = np.abs(arr[..., :3] - np.asarray(target, dtype=np.int32)).sum(-1)
    arr[..., 3][dist <= tol * 3] = 0
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


register(EffectSpec(
    id="bg_remove",
    name="背景去除",
    category="preprocess",
    params={
        "color": {"type": "color", "default": "#FFFFFF"},
        "tolerance": {"type": "int", "default": 30, "min": 0, "max": 120},
    },
    description="一键去除背景色（透明格 = 空格，无珠）",
), _bg_remove)
