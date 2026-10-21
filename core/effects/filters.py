# core/effects/filters.py - 滤镜与图纸风格特效
from PIL import Image, ImageEnhance

from ..colors import hex_to_rgb_safe
from .base import EffectSpec, preserve_alpha
from .registry import register


def _grayscale(img, params, ctx):
    contrast = float(params.get("contrast", 1.0))
    # 先在 RGB 上处理，再还原 alpha（convert("L") 会丢透明通道）
    out = img.convert("RGB").convert("L").convert("RGB")
    if abs(contrast - 1.0) > 0.01:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    return preserve_alpha(img, out)


register(EffectSpec(
    id="grayscale",
    name="黑白/灰度",
    category="preprocess",
    params={"contrast": {"type": "float", "default": 1.0, "min": 0.5, "max": 2.0}},
    description="灰度出图，可调对比度（保持透明背景）",
), _grayscale)


def _adjust(img, params, ctx):
    out = img.convert("RGB")
    b = float(params.get("brightness", 1.0))
    c = float(params.get("contrast", 1.0))
    s = float(params.get("saturation", 1.0))
    if abs(b - 1.0) > 0.01:
        out = ImageEnhance.Brightness(out).enhance(b)
    if abs(c - 1.0) > 0.01:
        out = ImageEnhance.Contrast(out).enhance(c)
    if abs(s - 1.0) > 0.01:
        out = ImageEnhance.Color(out).enhance(s)
    return preserve_alpha(img, out)


register(EffectSpec(
    id="adjust",
    name="亮度/对比度/饱和度",
    category="preprocess",
    params={
        "brightness": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.5},
        "contrast": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.5},
        "saturation": {"type": "float", "default": 1.2, "min": 0.0, "max": 2.0},
    },
    description="像素化前调整亮度、对比度、饱和度（保持透明背景）",
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


def _dark_chart(opts, params, ctx):
    # T15：暗色 editorial（espresso 底 / 奶油墨 / 黄铜网格），不再用旧蓝灰
    opts["dark"] = True
    opts["background"] = hex_to_rgb_safe(params.get("background"), (23, 18, 13))
    opts["grid_color"] = hex_to_rgb_safe(params.get("grid_color"), (58, 47, 35))
    return opts


register(EffectSpec(
    id="dark_chart",
    name="深色底图纸",
    category="chart",
    params={
        "background": {"type": "color", "default": "#17120D"},
        "grid_color": {"type": "color", "default": "#3A2F23"},
    },
    description="深色底浅字图纸，护眼/省墨（仅影响图纸，不影响成品效果图）",
), _dark_chart)
