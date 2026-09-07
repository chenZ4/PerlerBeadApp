# core/effects/presets.py - 限色数与风格色板预设
import numpy as np

from ..colors import rgb_to_lab
from .base import EffectSpec
from .registry import register

# 社区风格色板（RGB，任意色卡中取最近色）
PRESETS = {
    "pastel": {
        "name": "马卡龙可爱",
        "colors": [(248, 187, 208), (156, 175, 136), (255, 243, 176),
                   (215, 196, 232), (255, 253, 245), (168, 216, 234)],
    },
    "preppy": {
        "name": "Preppy/Y2K",
        "colors": [(255, 105, 180), (123, 216, 123), (255, 253, 245),
                   (255, 165, 0), (255, 215, 0)],
    },
    "halloween": {
        "name": "万圣节",
        "colors": [(255, 127, 0), (26, 26, 26), (255, 255, 255),
                   (75, 0, 130), (191, 255, 0)],
    },
    "christmas": {
        "name": "圣诞",
        "colors": [(27, 94, 32), (211, 47, 47), (255, 255, 255),
                   (255, 215, 0), (109, 76, 65)],
    },
    "cottagecore": {
        "name": "Cottagecore",
        "colors": [(156, 175, 136), (196, 115, 93), (197, 165, 60),
                   (201, 138, 138), (245, 239, 224), (122, 122, 82)],
    },
}


def _max_colors(idx, params, ctx):
    palette = ctx.palette
    if palette is None:
        return idx
    limit = int(params.get("max", 12))
    limit = max(1, min(limit, len(palette.colors)))
    flat = idx.reshape(-1)
    out = np.empty_like(flat)
    empty = flat < 0
    out[empty] = -1
    valid = flat[~empty]
    if valid.size == 0:
        return out.reshape(idx.shape)
    counts = np.bincount(valid, minlength=len(palette.colors))
    top = np.argsort(counts)[::-1][:limit]
    top_lab = palette.lab[top]
    outside = ~np.isin(valid, top)
    if outside.any():
        # 被淘汰的色 → Lab 感知距离最近的保留色
        src_lab = palette.lab[valid[outside]]
        d = ((src_lab[:, None, :] - top_lab[None, :, :]) ** 2).sum(-1)
        valid[outside] = top[d.argmin(-1)]
    out[~empty] = valid
    return out.reshape(idx.shape)


register(EffectSpec(
    id="max_colors",
    name="限色数",
    category="grid",
    params={"max": {"type": "int", "default": 12, "min": 2, "max": 50}},
    description="把颜色限制到使用最多的 N 种（简化色板）",
), _max_colors)


def _preset(idx, params, ctx):
    palette = ctx.palette
    if palette is None:
        return idx
    preset_name = params.get("preset", "pastel")
    preset = PRESETS.get(preset_name)
    if not preset:
        return idx
    target_lab = rgb_to_lab(np.asarray(preset["colors"], dtype=np.float32))
    pal_lab = palette.lab
    # 预设色 → 色卡最近索引（CIELAB 感知距离）
    d = ((target_lab[:, None, :] - pal_lab[None, :, :]) ** 2).sum(-1)
    subset = d.argmin(-1)  # 每个预设色的色卡索引（可能有重复）
    subset = list(dict.fromkeys(int(i) for i in subset))
    # 每个色卡色 → 最近预设色
    d2 = ((pal_lab[:, None, :] - target_lab[None, :, :]) ** 2).sum(-1)
    map_to_preset = d2.argmin(-1)  # 色卡索引 → 预设索引
    subset_idx = np.asarray(subset, dtype=np.int32)
    flat = idx.reshape(-1)
    out = np.empty_like(flat)
    empty = flat < 0
    out[empty] = -1
    for i in np.nonzero(~empty)[0]:
        out[i] = subset_idx[map_to_preset[flat[i]]]
    return out.reshape(idx.shape)


register(EffectSpec(
    id="preset",
    name="风格色板",
    category="grid",
    params={"preset": {"type": "choice", "default": "pastel",
                       "options": list(PRESETS.keys())}},
    description="一键使用社区流行风格色板（马卡龙/Preppy/万圣节/圣诞/Cottagecore）",
), _preset)
