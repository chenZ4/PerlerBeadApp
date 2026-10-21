# core/effects/geometry.py - 几何变形特效
import numpy as np
from PIL import Image

from .base import EffectSpec, warn
from .registry import register


def _chibi(img, params, ctx):
    """大头（chibi）：人脸检测 → 头部局部放大（保持画布尺寸与透明背景）。

    旧实现裁剪头部/身体后新建 RGB 白底画布：命中时画布尺寸 512×512→512×571、
    40% 白色填充珠、透明背景丢失；无脸/无 OpenCV 时完全静默。
    新实现：原地放大头部并贴回原画布，尺寸/alpha 不变；失败时写 warning。
    """
    try:
        import cv2
    except ImportError:
        warn(ctx, "大头(Q版)：需要 OpenCV，已跳过")
        return img
    try:
        gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        min_size = max(24, min(img.width, img.height) // 8)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_size, min_size))
    except Exception:  # noqa: BLE001 - 检测环境异常不应中断整条管线
        warn(ctx, "大头(Q版)：人脸检测失败，已跳过")
        return img
    if len(faces) == 0:
        warn(ctx, "大头(Q版)：未检测到人脸，已跳过（正面人像效果最佳）")
        return img

    head_ratio = float(params.get("head_ratio", 1.4))
    head_ratio = max(1.0, min(head_ratio, 2.0))
    fx, fy, fw, fh = [int(v) for v in faces[0]]
    cx = fx + fw // 2
    cy = fy + int(fh * 0.42)
    hw = max(4, int(fw * 1.35))
    hh = max(4, int(fh * 1.55))
    x0 = max(0, cx - hw // 2)
    y0 = max(0, cy - hh // 2)
    x1 = min(img.width, cx + hw // 2)
    y1 = min(img.height, cy + hh // 2)
    if x1 <= x0 or y1 <= y0:
        warn(ctx, "大头(Q版)：人脸区域越界，已跳过")
        return img
    head = img.crop((x0, y0, x1, y1))
    nw = max(1, int(head.width * head_ratio))
    nh = max(1, int(head.height * head_ratio))
    big = head.resize((nw, nh), Image.LANCZOS)
    px = cx - nw // 2
    py = cy - nh // 2
    src_x = max(0, -px)
    src_y = max(0, -py)
    dst_x = max(0, px)
    dst_y = max(0, py)
    paste_w = min(nw - src_x, img.width - dst_x)
    paste_h = min(nh - src_y, img.height - dst_y)
    if paste_w <= 0 or paste_h <= 0:
        warn(ctx, "大头(Q版)：放大区域越界，已跳过")
        return img
    piece = big.crop((src_x, src_y, src_x + paste_w, src_y + paste_h))
    out = img.copy()
    if out.mode in ("RGBA", "LA", "PA"):
        if out.mode != "RGBA":
            out = out.convert("RGBA")
        patch = piece.convert("RGBA")
        out.paste(patch, (dst_x, dst_y), patch.getchannel("A"))
        return out
    out.paste(piece, (dst_x, dst_y))
    return out


register(EffectSpec(
    id="chibi",
    name="大头（Q版）",
    category="geometric",
    params={
        "head_ratio": {"type": "float", "default": 1.4, "min": 1.0, "max": 2.0},
        "body_shrink": {"type": "float", "default": 0.75, "min": 0.4, "max": 1.0},
    },
    requires_opencv=True,
    description="检测人脸后原地放大头部（保持画布尺寸/透明背景；无脸时给出 warning）",
), _chibi)


def _mirror(img, params, ctx):
    direction = params.get("direction", "horizontal")
    if direction == "vertical":
        return img.transpose(Image.FLIP_TOP_BOTTOM)
    return img.transpose(Image.FLIP_LEFT_RIGHT)


register(EffectSpec(
    id="mirror",
    name="镜像",
    category="geometric",
    params={"direction": {"type": "choice", "default": "horizontal",
                          "options": ["horizontal", "vertical"]}},
    description="水平或垂直翻转图像",
), _mirror)


def _crop(img, params, ctx):
    w, h = img.size
    x0 = max(0.0, min(1.0, float(params.get("x0", 0.0))))
    y0 = max(0.0, min(1.0, float(params.get("y0", 0.0))))
    x1 = max(0.0, min(1.0, float(params.get("x1", 1.0))))
    y1 = max(0.0, min(1.0, float(params.get("y1", 1.0))))
    if x1 <= x0 or y1 <= y0:
        warn(ctx, "裁剪：参数无效（右/下边界需大于左/上），已跳过")
        return img
    if x0 <= 1e-6 and y0 <= 1e-6 and x1 >= 1 - 1e-6 and y1 >= 1 - 1e-6:
        warn(ctx, "裁剪：当前区域为整图（无裁剪），可拖动四边滑杆调整")
        return img
    return img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


register(EffectSpec(
    id="crop",
    name="裁剪",
    category="geometric",
    params={
        "x0": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0},
        "y0": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0},
        "x1": {"type": "float", "default": 0.9, "min": 0.0, "max": 1.0},
        "y1": {"type": "float", "default": 0.9, "min": 0.0, "max": 1.0},
    },
    description="按区域百分比裁剪（0~1 相对坐标；默认内缩 10%）",
), _crop)
