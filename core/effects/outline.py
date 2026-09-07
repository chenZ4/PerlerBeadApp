# core/effects/outline.py - 描边特效
import numpy as np
from PIL import Image, ImageFilter

from ..colors import hex_to_rgb_safe, rgb_to_lab
from .base import EffectSpec
from .registry import register


def _outline_index(palette, color):
    """把描边色 hex 转为色卡最近索引（CIELAB 感知距离）"""
    rgb = hex_to_rgb_safe(color, (26, 26, 26))
    target = rgb_to_lab(np.array([[rgb]], dtype=np.float32))[0]
    d = palette.lab - target
    return int(np.argmin((d * d).sum(-1)))


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
        # 默认不描外轮廓：细节丰富的图上「所有相邻异色对 + 外圈」会形成
        # 全图黑网（实测 58% 像素被改写），外轮廓交给用户按需开启
        "outline_outer": {"type": "bool", "default": False},
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
        # 100 时渐变/柔和边缘几乎全部漏检（实测仅 0.9% 像素生效），降低到 40
        "threshold": {"type": "int", "default": 40, "min": 10, "max": 250},
        "color": {"type": "color", "default": "#1A1A1A"},
        "width": {"type": "int", "default": 1, "min": 1, "max": 3},
    },
    description="线稿风描边：检测原图边缘轮廓并描边",
), {"preprocess": _outline_edge_image, "grid": _outline_edge_grid})
