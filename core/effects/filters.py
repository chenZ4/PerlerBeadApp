# core/effects/filters.py - 滤镜与图纸风格特效
from PIL import Image, ImageEnhance

from .base import EffectSpec
from .registry import register


def _grayscale(img, params, ctx):
    contrast = float(params.get("contrast", 1.0))
    out = img.convert("L").convert("RGB")
    if abs(contrast - 1.0) > 0.01:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    return out


register(EffectSpec(
    id="grayscale",
    name="黑白/灰度",
    category="preprocess",
    params={"contrast": {"type": "float", "default": 1.0, "min": 0.5, "max": 2.0}},
    description="灰度出图，可调对比度",
), _grayscale)


def _adjust(img, params, ctx):
    out = img
    b = float(params.get("brightness", 1.0))
    c = float(params.get("contrast", 1.0))
    s = float(params.get("saturation", 1.0))
    if abs(b - 1.0) > 0.01:
        out = ImageEnhance.Brightness(out).enhance(b)
    if abs(c - 1.0) > 0.01:
        out = ImageEnhance.Contrast(out).enhance(c)
    if abs(s - 1.0) > 0.01:
        out = ImageEnhance.Color(out).enhance(s)
    return out


register(EffectSpec(
    id="adjust",
    name="亮度/对比度/饱和度",
    category="preprocess",
    params={
        "brightness": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.5},
        "contrast": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.5},
        "saturation": {"type": "float", "default": 1.0, "min": 0.0, "max": 2.0},
    },
    description="像素化前调整亮度、对比度、饱和度",
), _adjust)


def _dither_marker(img, params, ctx):
    """抖动为 processor 特判特效，此处仅占位标记（真实匹配在映射阶段）"""
    return img


register(EffectSpec(
    id="dither",
    name="抖动过渡",
    category="preprocess",
    params={"strength": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.5}},
    description="Floyd-Steinberg 误差扩散，渐变过渡更柔和",
), _dither_marker)


def _hex_rgb(value, default):
    text = str(value).strip().lstrip('#')
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    return default


def _dark_chart(opts, params, ctx):
    opts["dark"] = True
    opts["background"] = _hex_rgb(params.get("background"), (30, 30, 30))
    opts["grid_color"] = _hex_rgb(params.get("grid_color"), (90, 90, 90))
    return opts


register(EffectSpec(
    id="dark_chart",
    name="深色底图纸",
    category="chart",
    params={
        "background": {"type": "color", "default": "#1E1E1E"},
        "grid_color": {"type": "color", "default": "#5A5A5A"},
    },
    description="深色底浅字图纸，护眼/省墨",
), _dark_chart)
