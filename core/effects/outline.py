# core/effects/outline.py - 描边特效
import numpy as np
from PIL import Image

from ..colors import hex_to_rgb_safe, rgb_to_lab
from .base import EffectSpec, warn
from .registry import register


def _outline_index(palette, color):
    """把描边色 hex 转为色卡最近索引（CIELAB 感知距离）"""
    rgb = hex_to_rgb_safe(color, (26, 26, 26))
    target = rgb_to_lab(np.array([[rgb]], dtype=np.float32))[0]
    d = palette.lab - target
    return int(np.argmin((d * d).sum(-1)))


# ---------------------------------------------------------------------------
# 邻接描边（grid 阶段）
# ---------------------------------------------------------------------------
def _apply_outline(idx, params, ctx):
    """在索引矩阵上描边：只描「感知色差足够大」的相邻格。

    T1 实测旧实现（相邻索引不同即描）在照片上把 65.9% 的珠子变成描边色
    （全图黑网）。新实现：
      - 相邻格 CIELAB ΔE 需 > max(min_delta_e, 相邻色差分位 percentile)；
        照片只保留强轮廓，平涂卡通仍保留清晰外轮廓/色块边界；
      - 去孤立描边点；width 膨胀；outline_outer 可选（默认关）；
      - 透明空格参与边界判断（保持「描边填充空格」的既有语义）。
    """
    palette = ctx.palette if ctx is not None else None
    if palette is None:
        return idx
    h, w = idx.shape
    if h < 2 or w < 2:
        return idx
    outline_idx = _outline_index(palette, params.get("color", "#1A1A1A"))
    width = max(1, min(int(params.get("width", 1)), 3))
    outer = bool(params.get("outline_outer", False))
    min_delta_e = max(0.0, float(params.get("min_delta_e", 30.0)))
    percentile = max(50.0, min(float(params.get("percentile", 95.0)), 99.5))

    pal_lab = np.asarray(palette.lab, dtype=np.float32)
    safe = np.clip(idx, 0, len(pal_lab) - 1)
    cell_lab = pal_lab[safe]
    empty = idx < 0

    def pair_delta(a, b, ea, eb):
        """相邻对 ΔE：两空格=0，一空格=999（透明边界视为强边界，保持旧语义）"""
        d = np.sqrt(((a - b) ** 2).sum(-1))
        both = ea & eb
        one = ea ^ eb
        return np.where(both, 0.0, np.where(one, 999.0, d))

    # 竖直相邻（下-上）与水平相邻（右-左）
    d_v = pair_delta(cell_lab[1:, :], cell_lab[:-1, :], empty[1:, :], empty[:-1, :])
    d_h = pair_delta(cell_lab[:, 1:], cell_lab[:, :-1], empty[:, 1:], empty[:, :-1])

    finite = np.concatenate([d_v[(d_v < 998)].ravel(), d_h[(d_h < 998)].ravel()])
    if finite.size:
        thr = max(min_delta_e, float(np.percentile(finite, percentile)))
    else:
        thr = min_delta_e
    mask = np.zeros((h, w), dtype=bool)
    strong_v = d_v > thr
    strong_h = d_h > thr
    mask[1:, :] |= strong_v
    mask[:-1, :] |= strong_v
    mask[:, 1:] |= strong_h
    mask[:, :-1] |= strong_h

    # 去孤立描边点（保留外轮廓）
    if mask.any():
        nb = np.zeros_like(mask, dtype=np.int16)
        nb[1:, :] += mask[:-1, :]
        nb[:-1, :] += mask[1:, :]
        nb[:, 1:] += mask[:, :-1]
        nb[:, :-1] += mask[:, 1:]
        mask &= nb > 0
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
        # 默认不描外轮廓：细节丰富的图上「所有相邻异色对 + 外圈」会形成全图黑网
        "outline_outer": {"type": "bool", "default": False},
        # 新增：只描感知色差足够大的相邻格（照片去黑网、平涂保留轮廓）
        "min_delta_e": {"type": "float", "default": 30.0, "min": 0.0, "max": 60.0},
        "percentile": {"type": "float", "default": 95.0, "min": 50.0, "max": 99.5},
    },
    description="像素邻接描边：只描感知色差大的相邻格，按分位自适应（照片不再全图黑网）",
), _apply_outline)


# ---------------------------------------------------------------------------
# 线稿描边（preprocess + grid 两阶段）
# ---------------------------------------------------------------------------
def _outline_edge_image(img, params, ctx):
    """线稿风：保存原图快照，网格阶段做网格尺度边缘检测。"""
    if ctx is not None:
        try:
            # 超大图先降采样，控制内存（网格阶段还会 BOX 缩到网格尺寸）
            work = img
            if max(img.size) > 2048:
                r = 2048.0 / max(img.size)
                work = img.resize((max(1, int(img.width * r)),
                                   max(1, int(img.height * r))), Image.BOX)
            ctx.cache["edge_src"] = work.copy()
        except Exception:  # noqa: BLE001
            pass
    return img


def _outline_edge_grid(idx, params, ctx):
    """网格尺度线稿：对比度感知下采样 → L 通道 DoG + 滞后阈值 + 去孤点。

    旧实现全分辨率 FIND_EDGES 后 NEAREST 缩到网格 → 孤立噪点（T1 实测变更格
    仅 13.4% 有 ≥2 邻居，卡通 0%）。新实现先在网格尺度求边缘并用弱边连接、
    去小连通域，得到连续线条；透明边界也纳入边缘。
    """
    palette = ctx.palette if ctx is not None else None
    if palette is None:
        return idx
    src = None
    if ctx is not None:
        src = ctx.cache.get("edge_src")
    if src is None:
        warn(ctx, "线稿描边：缺少预处理快照，已跳过")
        return idx
    h, w = idx.shape
    outline_idx = _outline_index(palette, params.get("color", "#1A1A1A"))
    width = max(1, min(int(params.get("width", 1)), 3))
    strength = float(params.get("strength", 0.8))
    strength = max(0.0, min(strength, 1.0))

    small = src.convert("RGB").resize((w, h), Image.BOX)
    L = np.asarray(small.convert("L"), dtype=np.float32)
    alpha = None
    if src.mode in ("RGBA", "LA", "PA"):
        alpha = np.asarray(src.convert("RGBA").getchannel("A").resize((w, h), Image.BOX),
                           dtype=np.float32)

    try:
        import cv2
        g1 = cv2.GaussianBlur(L, (0, 0), 0.8)
        g2 = cv2.GaussianBlur(L, (0, 0), 1.6)
        dog = np.abs(g1 - g2)
        peak = float(dog.max())
        if peak <= 1e-6:
            return idx
        dog = dog / peak
        alpha_edge = np.zeros((h, w), dtype=bool)
        if alpha is not None:
            ax = np.abs(np.diff(alpha, axis=1)) > 0.15
            ay = np.abs(np.diff(alpha, axis=0)) > 0.15
            alpha_edge[:, 1:] |= ax
            alpha_edge[:, :-1] |= ax
            alpha_edge[1:, :] |= ay
            alpha_edge[:-1, :] |= ay
        hi_pct = 88.0 + strength * 8.0
        lo_pct = hi_pct - 12.0
        hi = float(np.percentile(dog, hi_pct))
        lo = float(np.percentile(dog, lo_pct))
        strong = dog >= hi
        weak = dog >= lo
        kernel = np.ones((3, 3), np.uint8)
        grow = strong.astype(np.uint8)
        for _ in range(3):
            grow = cv2.dilate(grow, kernel)
        mask = ((grow > 0) & weak) | strong
        # 去小连通域：面积 <2 且不含强边的块移除
        num, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8), connectivity=8)
        keep = np.zeros_like(mask)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] >= 2 or strong[labels == i].any():
                keep[labels == i] = True
        mask = keep | alpha_edge
        if width > 1:
            mask = cv2.dilate(mask.astype(np.uint8), kernel,
                              iterations=width - 1).astype(bool)
        mask &= idx >= 0          # 透明格不产生珠子
        out = idx.copy()
        out[mask] = outline_idx
        return out
    except ImportError:
        pass
    # fallback：网格 L 梯度 + 分位阈值（无 cv2）
    gx = np.zeros((h, w), np.float32)
    gy = np.zeros((h, w), np.float32)
    gx[:, :-1] = np.abs(np.diff(L, axis=1))
    gy[:-1, :] = np.abs(np.diff(L, axis=0))
    mag = gx + gy
    if mag.max() <= 1e-6:
        return idx
    thr = float(np.percentile(mag, 86.0 + strength * 8.0))
    mask = mag >= thr
    mask &= idx >= 0
    out = idx.copy()
    out[mask] = outline_idx
    return out


register(EffectSpec(
    id="outline_edge",
    name="线稿描边",
    category="preprocess",
    params={
        # strength 0~1：线稿强度（映射到网格尺度 DoG 分位阈值，越高线越少越干净）
        "strength": {"type": "float", "default": 0.8, "min": 0.0, "max": 1.0},
        # 兼容旧参数：threshold 保留但新算法不再使用绝对阈值
        "threshold": {"type": "int", "default": 40, "min": 10, "max": 250},
        "color": {"type": "color", "default": "#1A1A1A"},
        "width": {"type": "int", "default": 1, "min": 1, "max": 3},
    },
    description="网格尺度线稿：DoG + 滞后阈值 + 去孤点，线条连续、少噪点",
), {"preprocess": _outline_edge_image, "grid": _outline_edge_grid})
