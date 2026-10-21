# core/effects/presets.py - 限色数与风格色板预设
import numpy as np

from ..colors import rgb_to_lab
from .base import EffectSpec, lab_to_rgb, warn
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
    palette = ctx.palette if ctx is not None else None
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
    """风格色板：保亮度结构的「秩映射」——禁止整图洗白。

    旧实现：每个色卡色 → 最近预设色的最近色卡色。预设色多偏浅，照片被整体
    映射到近白（T1 实测 L +40、近白珠 6%→28%）。
    新实现：
      1) 统计图像实际使用的色卡色，按使用次数等分到 K 组（K = 预设色数）；
      2) 每组按明度排序对应一个预设色锚点（暗组→暗锚点）；
      3) 目标色 = 锚点色相/彩度 + 该组平均明度（CIELAB L），再映射到最近色卡色。
    → 输出用色 ≤ 预设色数、明度分布接近原图、风格色相来自预设。
    """
    palette = ctx.palette if ctx is not None else None
    if palette is None:
        return idx
    preset_name = params.get("preset", "pastel")
    preset = PRESETS.get(preset_name)
    if not preset:
        warn(ctx, f"风格色板：未知预设 {preset_name}，回退马卡龙")
        preset = PRESETS["pastel"]
    flat = idx.reshape(-1)
    out = np.full_like(flat, -1)
    empty = flat < 0
    valid_vals = flat[~empty]
    if valid_vals.size == 0:
        return out.reshape(idx.shape)
    counts = np.bincount(valid_vals, minlength=len(palette.colors))
    used = np.nonzero(counts > 0)[0]
    if used.size <= 1:
        # 单色图：无需风格化
        out[~empty] = valid_vals
        return out.reshape(idx.shape)

    preset_lab = rgb_to_lab(np.asarray(preset["colors"], dtype=np.float32))  # (K,3)
    k = max(2, len(preset_lab))
    used_counts = counts[used].astype(np.float64)
    used_lab = np.asarray(palette.lab[used], dtype=np.float64)
    # 1) 等频（按使用次数）分组：每组占比接近 1/k
    order = np.argsort(used_lab[:, 0])
    used_sorted = used[order]
    counts_sorted = used_counts[order]
    cum = np.cumsum(counts_sorted)
    total = cum[-1]
    # 每组的累计次数边界
    boundaries = np.searchsorted(cum, total * np.arange(1, k) / k, side="right")
    groups = np.split(np.arange(used.size), boundaries)
    # 2) 预设锚点按明度排序，暗组→暗锚点
    anchor_order = np.argsort(preset_lab[:, 0])
    anchors = preset_lab[anchor_order]
    # 3) 每组映射到一个输出色卡色
    lut = np.full(len(palette.colors), -1, dtype=np.int32)
    for gi, g in enumerate(groups):
        if g.size == 0:
            continue
        anchor_idx = int(round(gi * (len(anchors) - 1) / max(1, k - 1)))
        anchor = anchors[anchor_idx]
        mean_l = float(np.average(used_lab[order][g][:, 0], weights=counts_sorted[g]))
        target_lab = np.array([np.clip(mean_l, 12.0, 95.0), anchor[1], anchor[2]],
                              dtype=np.float32)
        target_rgb = lab_to_rgb(target_lab[None, :])[0]
        target_lab2 = rgb_to_lab(target_rgb[None, :].astype(np.float32))[0]
        d = ((np.asarray(palette.lab) - target_lab2) ** 2).sum(-1)
        out_idx = int(np.argmin(d))
        lut[used_sorted[g]] = out_idx
    # 未映射到的使用色（极端情况）回退到按明度最近的组色
    missing = np.nonzero(lut[used] < 0)[0]
    if missing.size:
        mapped_used = used[lut[used] >= 0]
        mapped_lut = lut[mapped_used]
        for mi in missing:
            raw = used[mi]
            lab = np.asarray(palette.lab[raw])
            best = int(np.argmin(((np.asarray(palette.lab[mapped_used]) - lab) ** 2).sum(-1)))
            lut[raw] = int(mapped_lut[best])
    out[~empty] = lut[valid_vals]
    return out.reshape(idx.shape)


register(EffectSpec(
    id="preset",
    name="风格色板",
    category="grid",
    params={"preset": {"type": "choice", "default": "pastel",
                       "options": list(PRESETS.keys())}},
    description="风格色板：按明度秩映射到预设色（保亮度结构，用色 ≤ 预设色数）",
), _preset)
