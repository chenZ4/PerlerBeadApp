# core/effects/outline.py - 描边特效
import numpy as np
from PIL import Image, ImageFilter

from ..colors import weighted_distance, hex_to_rgb_safe
from .base import EffectSpec
from .registry import register


def _outline_index(palette, color):
    """把描边色 hex 转为色卡最近索引（加权距离）"""
    target = hex_to_rgb_safe(color, (26, 26, 26))
    best = 0
    best_d = float('inf')
    for i, c in enumerate(palette.colors):
        d = weighted_distance(target, c)
        if d < best_d:
            best_d = d
            best = i
    return best


def _apply_outline(idx, params, ctx):
    """在索引矩阵上描边：相邻异色格（及可选外轮廓）替换为描边索引"""
    palette = ctx.palette
    if palette is None:
        return idx
    h, w = idx.shape
    outline_idx = _outline_index(palette, params.get("color", "#1A1A1A"))
    width = int(params.get("width", 1))
    outer = bool(params.get("outline_outer", True))

    mask = np.zeros((h, w), dtype=bool)
    if h > 1 and w > 1:
        mask[1:, :] |= idx[1:, :] != idx[:-1, :]
        mask[:-1, :] |= idx[1:, :] != idx[:-1, :]
        mask[:, 1:] |= idx[:, 1:] != idx[:, :-1]
        mask[:, :-1] |= idx[:, 1:] != idx[:, :-1]
    if outer:
        mask[0, :] = True
        mask[-1, :] = True
        mask[:, 0] = True
        mask[:, -1] = True
    if width > 1 and mask.any():
        for _ in range(width - 1):
            dilated = mask.copy()
            dilated[1:, :] |= mask[:-1, :]
            dilated[:-1, :] |= mask[1:, :]
            dilated[:, 1:] |= mask[:, :-1]
            dilated[:, :-1] |= mask[:, 1:]
            mask = dilated
    out = idx.copy()
    out[mask] = outline_idx
    return out


register(EffectSpec(
    id="outline_cell",
    name="邻接描边",
    category="grid",
    params={
        "color": {"type": "color", "default": "#1A1A1A"},
        "width": {"type": "int", "default": 1, "min": 1, "max": 3},
        "outline_outer": {"type": "bool", "default": True},
    },
    description="像素邻接描边：相邻不同色格子之间画描边线",
), _apply_outline)


def _outline_edge_image(img, params, ctx):
    """线稿风：原图边缘检测，结果存到 ctx 供 grid 阶段使用"""
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = edges.point(lambda v: 255 if v > int(params.get("threshold", 100)) else 0)
    ctx.edge_mask = np.asarray(edges, dtype=np.uint8)
    return img


def _outline_edge_grid(idx, params, ctx):
    palette = ctx.palette
    if palette is None:
        return idx
    edge = getattr(ctx, "edge_mask", None)
    if edge is None:
        return idx
    h, w = idx.shape
    small = np.asarray(
        Image.fromarray(edge).resize((w, h), Image.NEAREST), dtype=np.uint8)
    outline_idx = _outline_index(palette, params.get("color", "#1A1A1A"))
    width = int(params.get("width", 1))
    mask = small > 127
    if width > 1 and mask.any():
        for _ in range(width - 1):
            dilated = mask.copy()
            dilated[1:, :] |= mask[:-1, :]
            dilated[:-1, :] |= mask[1:, :]
            dilated[:, 1:] |= mask[:, :-1]
            dilated[:, :-1] |= mask[:, 1:]
            mask = dilated
    out = idx.copy()
    out[mask] = outline_idx
    return out


register(EffectSpec(
    id="outline_edge",
    name="线稿描边",
    category="preprocess",
    params={
        "threshold": {"type": "int", "default": 100, "min": 10, "max": 250},
        "color": {"type": "color", "default": "#1A1A1A"},
        "width": {"type": "int", "default": 1, "min": 1, "max": 3},
    },
    description="线稿风描边：检测原图边缘轮廓并描边",
), {"preprocess": _outline_edge_image, "grid": _outline_edge_grid})
