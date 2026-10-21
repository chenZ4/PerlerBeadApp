# core/effects/filters2.py - 滤镜特效 v2
import numpy as np
from PIL import Image, ImageEnhance

from ..colors import hex_to_rgb_safe, rgb_to_lab
from .base import EffectSpec, lab_to_rgb, preserve_alpha, warn
from .registry import register


def _cel_shade(img, params, ctx):
    """赛璐璐：边缘保留平滑 + Lab 空间聚类平涂（保留色相与形体）。

    旧实现 RGB 逐通道 floor 分桶：255→192 全图压暗、通道独立取整造成色相
    漂移（扁平卡通实测色相中位漂移 158°、白底变灰）。新实现：
      1) cv2.stylization 边缘保留平滑（无 cv2 时退化为 Lab L* 分桶）；
      2) 在 Lab 空间 k-means（k = 2*levels）聚成平涂色块；
      3) 直接输出 RGB，随后的色卡映射照常进行。
    """
    levels = int(params.get("levels", 4))
    levels = max(2, min(levels, 16))
    src = img.convert("RGB")
    w, h = src.size
    try:
        import cv2
        # 大图先降采样（stylization 在 2048px 会到秒级），结果再 NEAREST 放大
        scale = min(1.0, 1024.0 / max(w, h))
        work = src
        if scale < 1.0:
            work = src.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                              Image.BOX)
        arr = np.asarray(work, dtype=np.uint8)
        # bilateralFilter（而非 stylization）：后者在随机噪声/抖动图上会塌成
        # 近黑色（QA 实测 127→0.1），bilateral 保持均值且边缘保留、稳定可复现
        smooth = cv2.bilateralFilter(arr, 9, 75, 75)
        lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB)
        flat = lab.reshape(-1, 3).astype(np.float32)
        k = max(2, min(2 * levels, 16))
        sample = flat
        if flat.shape[0] > 60000:
            pos = np.linspace(0, flat.shape[0] - 1, 60000).astype(np.int64)
            sample = flat[pos]
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, _, centers = cv2.kmeans(sample, k, None, criteria, 3,
                                   cv2.KMEANS_PP_CENTERS)
        centers = centers.astype(np.float32)
        out_lab = np.empty_like(flat)
        for start in range(0, flat.shape[0], 32768):
            chunk = flat[start:start + 32768]
            d = ((chunk[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
            out_lab[start:start + len(chunk)] = centers[d.argmin(-1)]
        out_lab = np.clip(out_lab, 0, 255).astype(np.uint8).reshape(lab.shape)
        out_rgb = cv2.cvtColor(out_lab, cv2.COLOR_LAB2RGB)
        out_img = Image.fromarray(out_rgb, "RGB")
        if scale < 1.0:
            out_img = out_img.resize((w, h), Image.NEAREST)
        return preserve_alpha(img, out_img)
    except ImportError:
        pass
    # fallback：CIE Lab 只对 L* 分桶（保留 a*/b*，端点对齐不压暗）
    lab = rgb_to_lab(np.asarray(src, dtype=np.float32))
    step = 100.0 / (levels - 1)
    quant = lab.copy()
    quant[..., 0] = np.clip(np.round(lab[..., 0] / step) * step, 0, 100)
    out_img = Image.fromarray(lab_to_rgb(quant), "RGB")
    return preserve_alpha(img, out_img)


register(EffectSpec(
    id="cel_shade",
    name="赛璐璐色阶",
    category="preprocess",
    params={"levels": {"type": "int", "default": 4, "min": 2, "max": 16}},
    description="边缘保留平滑 + Lab 聚类平涂（保留色相/形体/透明背景）",
), _cel_shade)


def _neon(img, params, ctx):
    """霓虹：暗底 + 高饱和（保留 alpha）。"""
    sat = float(params.get("saturation", 1.5))
    dark = float(params.get("darkness", 0.9))
    out = img.convert("RGB")
    # 先降亮再拉饱和：旧顺序（先饱和后压暗）会把饱和增益抵消
    if abs(dark - 1.0) > 0.01:
        out = ImageEnhance.Brightness(out).enhance(dark)
    if abs(sat - 1.0) > 0.01:
        out = ImageEnhance.Color(out).enhance(sat)
    return preserve_alpha(img, out)


register(EffectSpec(
    id="neon",
    name="霓虹",
    category="preprocess",
    params={
        "saturation": {"type": "float", "default": 1.5, "min": 1.0, "max": 2.5},
        "darkness": {"type": "float", "default": 0.9, "min": 0.4, "max": 1.0},
    },
    description="压暗 + 高饱和荧光感（配合深色底图纸效果最佳）",
), _neon)


def _duotone(img, params, ctx):
    """双色调：灰度映射到双色渐变，复古海报感（保留 alpha）。"""
    c1 = hex_to_rgb_safe(params.get("color1"), (30, 30, 30))
    c2 = hex_to_rgb_safe(params.get("color2"), (240, 240, 240))
    arr = np.asarray(img.convert("RGB").convert("L"), dtype=np.float32) / 255.0
    t = arr[..., None]
    out = (np.asarray(c1, dtype=np.float32) * (1 - t)
           + np.asarray(c2, dtype=np.float32) * t)
    out_img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    return preserve_alpha(img, out_img)


register(EffectSpec(
    id="duotone",
    name="双色调",
    category="preprocess",
    params={
        "color1": {"type": "color", "default": "#1E1E1E"},
        "color2": {"type": "color", "default": "#F0F0F0"},
    },
    description="灰度双色渐变，复古海报感（保持透明背景）",
), _duotone)


def _bg_remove(img, params, ctx):
    """背景去除：边界连通背景 → 透明（透明格 = 空格，无珠）。

    T1 实测旧实现按全图色距删除：白色主体删除率 100%、白色高光被误删。
    新实现：
      - color="auto" 时取四条边像素中位色作为背景色；
      - 只在「与目标色相近 且 与图像边界连通」的区域内删除（连通域约束），
        内部同色主体保留；
      - 目标色未出现在图像边界时不删除并给出 warning（避免误删主体）。
    """
    tol = int(params.get("tolerance", 30))
    tol = max(0, min(tol, 255))
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).astype(np.int32).copy()
    h, w = arr.shape[:2]
    color_param = params.get("color", "#FFFFFF")
    if isinstance(color_param, str) and color_param.strip().lower() == "auto":
        border = np.concatenate([arr[0, :, :3], arr[-1, :, :3],
                                 arr[:, 0, :3], arr[:, -1, :3]], axis=0)
        target = np.median(border, axis=0).astype(np.int32)
    else:
        target = np.asarray(hex_to_rgb_safe(color_param, (255, 255, 255)),
                            dtype=np.int32)
    dist = np.abs(arr[..., :3] - target).sum(-1)
    similar = dist <= tol * 3
    remove = np.zeros_like(similar)
    if similar.any():
        try:
            import cv2
            _, labels = cv2.connectedComponents(similar.astype(np.uint8),
                                                connectivity=4)
            border_labels = set(np.unique(labels[0, :]).tolist())
            border_labels.update(np.unique(labels[-1, :]).tolist())
            border_labels.update(np.unique(labels[:, 0]).tolist())
            border_labels.update(np.unique(labels[:, -1]).tolist())
            border_labels.discard(0)
            if border_labels:
                remove = np.isin(labels, list(border_labels))
            else:
                warn(ctx, "bg_remove: 目标色未出现在图像边界，已跳过（避免误删内部白色主体）")
        except ImportError:
            # 无 OpenCV：退化为全图色键，并明确告知可能误删主体
            remove = similar
            warn(ctx, "bg_remove: OpenCV 不可用，退化为全图色键（可能误删内部同色主体）")
    alpha = arr[..., 3].copy()
    alpha[remove] = 0
    arr[..., 3] = alpha
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


register(EffectSpec(
    id="bg_remove",
    name="背景去除",
    category="preprocess",
    params={
        "color": {"type": "color", "default": "#FFFFFF"},
        "tolerance": {"type": "int", "default": 30, "min": 0, "max": 120},
    },
    description="从图像边界泛洪去除背景色；color=auto 取角落色；内部同色主体保留",
), _bg_remove)
