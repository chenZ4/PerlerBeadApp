# core/effects/base.py - 特效规格与上下文
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np


@dataclass
class EffectSpec:
    id: str
    name: str
    category: str          # geometric / preprocess / grid / chart
    params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    requires_opencv: bool = False
    description: str = ""

    def param_schema(self):
        """供 UI/协议层使用的参数 schema"""
        return self.params

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "params": self.params,
            "requires_opencv": self.requires_opencv,
            "description": self.description,
        }


@dataclass
class EffectContext:
    palette: Any = None
    grid_w: int = 0
    grid_h: int = 0
    cell_size: int = 0
    engine: Any = None
    # 特效执行过程中的非致命提示（协议层回传 warnings；UI 状态栏可见）
    warnings: List[str] = field(default_factory=list)
    # 阶段间缓存（如 outline_edge 的原图副本、已应用特效 id 列表）
    cache: Dict[str, Any] = field(default_factory=dict)


def warn(ctx, message):
    """向上下文追加 warning（去重，避免同一条重复刷屏）"""
    if ctx is None:
        return
    try:
        if message not in ctx.warnings:
            ctx.warnings.append(message)
    except Exception:  # noqa: BLE001 - 上下文可能是旧对象/测试替身
        pass


def preserve_alpha(src, out):
    """保持 src 的透明度：把 src 的 alpha 通道还给处理后的 RGB 图像。

    RGBA/LA 输入经 convert("L") / convert("RGB") 会丢 alpha（T1 实测：透明格
    从 918 颗变成 3600 颗实心珠）。所有 preprocess 特效输出都必须经过这里。
    """
    if src.mode not in ("RGBA", "LA", "PA"):
        if out.mode != "RGB":
            return out.convert("RGB")
        return out
    alpha = src.convert("RGBA").getchannel("A")
    rgb = out.convert("RGB") if out.mode != "RGB" else out
    rgb = rgb.copy()
    rgb.putalpha(alpha)
    return rgb


# ---------------------------------------------------------------------------
# CIELAB → sRGB（标准 D65 逆变换；Lab 空间做色阶/风格迁移时回写用）
# ---------------------------------------------------------------------------
def lab_to_rgb(arr):
    """CIELAB(...,3) → RGB(0..255, ...,3) uint8"""
    lab = np.asarray(arr, dtype=np.float32)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0

    def finv(t):
        delta = 6.0 / 29.0
        return np.where(t > delta, t ** 3, 3 * delta * delta * (t - 4.0 / 29.0))

    x = finv(fx) * 0.95047
    y = finv(fy)
    z = finv(fz) * 1.08883
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def gamma(c):
        return np.where(c <= 0.0031308, 12.92 * c,
                        1.055 * np.power(np.maximum(c, 0.0), 1.0 / 2.4) - 0.055)

    rgb = np.stack([gamma(r), gamma(g), gamma(b)], axis=-1)
    return np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
