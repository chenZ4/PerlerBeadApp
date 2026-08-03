# core/effects/geometry.py - 几何变形特效
import numpy as np
from PIL import Image

from .base import EffectSpec
from .registry import register


def _chibi(img, params, ctx):
    """大头（chibi）：人脸检测 → 头部放大、身体压缩"""
    try:
        import cv2
    except ImportError:
        return img
    try:
        gray = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        min_size = max(24, min(img.width, img.height) // 8)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_size, min_size))
        if len(faces) == 0:
            return img
        fx, fy, fw, fh = faces[0]
    except Exception:
        return img

    head_ratio = float(params.get("head_ratio", 1.4))
    body_shrink = float(params.get("body_shrink", 0.75))

    hx = fx
    hy = max(0, fy - int(fh * 0.8))
    hw = fw
    hh = min(img.height - hy, int(fh * 1.8))

    head = img.crop((hx, hy, hx + hw, hy + hh))
    head = head.resize((max(1, int(hw * head_ratio)),
                        max(1, int(hh * head_ratio))), Image.LANCZOS)

    body_top = hy + hh
    if body_top >= img.height:
        return img
    body = img.crop((0, body_top, img.width, img.height))
    body = body.resize((img.width, max(1, int(body.height * body_shrink))), Image.LANCZOS)

    out = Image.new("RGB", (img.width, head.height + body.height), (255, 255, 255))
    out.paste(head, ((img.width - head.width) // 2, 0))
    out.paste(body, (0, head.height))
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
    description="检测人脸后放大头部、压缩身体，产生 Q 版大头效果",
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
        return img
    return img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


register(EffectSpec(
    id="crop",
    name="裁剪",
    category="geometric",
    params={
        "x0": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
        "y0": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
        "x1": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0},
        "y1": {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0},
    },
    description="按区域百分比裁剪（0~1 相对坐标）",
), _crop)
