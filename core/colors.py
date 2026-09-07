# core/colors.py - 色卡数据（data/palettes/*.json 动态加载）
import json
import os

import numpy as np

from .models import hex_to_rgb_safe  # noqa: F401  (re-export for effects)

# 感知加权 RGB（人眼敏感度）：R 0.299 / G 0.587 / B 0.114
# 保留给旧调用方（UI 兼容层）；色卡匹配已升级为 CIELAB 距离（感知均匀，
# 修复饱和色映错色相/渐变区噪点，见 closest_indices）
RGB_WEIGHTS = (0.299, 0.587, 0.114)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALETTE_DIR = os.path.join(BASE_DIR, "data", "palettes")

# CIELAB 常量（D65 白点）
_SRGB_TO_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                         [0.2126729, 0.7151522, 0.0721750],
                         [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
_LAB_MIN = np.array([0.0, -128.0, -128.0], dtype=np.float32)
_LAB_MAX = np.array([100.0, 127.0, 127.0], dtype=np.float32)


def _srgb_to_linear(c):
    """sRGB 伽马 → 线性 RGB（c: 0..1）"""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(arr):
    """RGB(0..255, ...,3) → CIELAB（D65），向量化任意形状"""
    c = np.asarray(arr, dtype=np.float32) / 255.0
    lin = _srgb_to_linear(np.clip(c, 0.0, 1.0))
    xyz = lin @ _SRGB_TO_XYZ.T / _WHITE_D65
    delta = 6 / 29
    f = np.where(xyz > delta ** 3,
                 np.cbrt(xyz),
                 xyz / (3 * delta * delta) + 4 / 29)
    lab = np.empty_like(f)
    lab[..., 0] = 116 * f[..., 1] - 16
    lab[..., 1] = 500 * (f[..., 0] - f[..., 1])
    lab[..., 2] = 200 * (f[..., 1] - f[..., 2])
    return lab

# 兜底色卡（数据目录缺失/全部损坏时）
_FALLBACK = {
    "display": "基础 8 色",
    "internal": "basic",
    "colors": [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0),
               (0, 0, 255), (255, 255, 0), (128, 128, 128), (255, 165, 0)],
    "names": ["黑", "白", "红", "绿", "蓝", "黄", "灰", "橙"],
    "codes": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],
}

_PALETTE_CACHE = {}
PALETTE_OPTIONS = []


def weighted_distance(rgb1, rgb2):
    """感知加权 RGB 距离平方（R 0.299 / G 0.587 / B 0.114）"""
    wr, wg, wb = RGB_WEIGHTS
    return ((rgb1[0] - rgb2[0]) ** 2 * wr
            + (rgb1[1] - rgb2[1]) ** 2 * wg
            + (rgb1[2] - rgb2[2]) ** 2 * wb)


def rgb_to_hex(rgb):
    return '#{:02X}{:02X}{:02X}'.format(*rgb)


def _validate(data):
    """校验色卡数据完整性"""
    if not isinstance(data, dict):
        return False
    colors = data.get("colors")
    names = data.get("names")
    codes = data.get("codes")
    if not (isinstance(colors, list) and isinstance(names, list)
            and isinstance(codes, list)):
        return False
    if not (len(colors) == len(names) == len(codes)):
        return False
    if not colors:
        return False
    for rgb in colors:
        if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3):
            return False
        if any(not (isinstance(v, int) and 0 <= v <= 255) for v in rgb):
            return False
    if len(set(codes)) != len(codes):
        return False
    for code in codes:
        if not isinstance(code, str) or not code.strip():
            return False
    for name in names:
        if not isinstance(name, str):
            return False
    return True


def load_palettes():
    """扫描 data/palettes/*.json 构建色卡列表；损坏文件跳过并警告"""
    global PALETTE_OPTIONS
    options = []
    if os.path.isdir(PALETTE_DIR):
        for filename in sorted(os.listdir(PALETTE_DIR)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(PALETTE_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (IOError, OSError, ValueError) as e:
                print(f"[警告] 色卡文件无法解析: {filename}: {e}")
                continue
            if not _validate(data):
                print(f"[警告] 色卡数据无效，已跳过: {filename}")
                continue
            internal = data.get("internal") or filename[:-5]
            display = data.get("display") or internal
            options.append((display, internal))
            _PALETTE_CACHE[internal] = data
    if not options:
        print("[警告] 未找到可用色卡数据，使用内置兜底色卡")
        options = [(_FALLBACK["display"], _FALLBACK["internal"])]
        _PALETTE_CACHE[_FALLBACK["internal"]] = _FALLBACK
    PALETTE_OPTIONS = options


class ColorPalette:
    def __init__(self, palette_name="basic"):
        data = _PALETTE_CACHE.get(palette_name)
        if data is None:
            data = _FALLBACK
        self.palette_name = data.get("internal", palette_name)
        self.colors = [tuple(c) for c in data["colors"]]
        self.names = list(data["names"])
        self.codes = list(data["codes"])
        self._hex_codes = [self._rgb_to_hex(rgb) for rgb in self.colors]
        # 色卡 Lab 预计算（感知色距匹配用）
        self._lab = rgb_to_lab(np.asarray(self.colors, dtype=np.float32))

    @property
    def lab(self):
        """色卡 CIELAB 数组 (K,3)"""
        return self._lab

    def _rgb_to_hex(self, rgb):
        """RGB 转 HEX"""
        return rgb_to_hex(rgb)

    @property
    def hex_codes(self):
        """HEX 颜色码列表（预计算缓存）"""
        return self._hex_codes

    def closest_indices(self, pil_img):
        """CIELAB 感知色距最近色匹配，返回 (H,W) 色卡索引数组"""
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        lab = rgb_to_lab(np.asarray(pil_img, dtype=np.float32))
        h, w_, _ = lab.shape
        flat = lab.reshape(-1, 3)
        out = np.empty(flat.shape[0], dtype=np.int32)
        step = 8192
        pal = self._lab
        for start in range(0, flat.shape[0], step):
            chunk = flat[start:start + step]
            diff = chunk[:, None, :] - pal[None, :, :]
            out[start:start + chunk.shape[0]] = (diff * diff).sum(-1).argmin(-1)
        return out.reshape(h, w_)

    def closest_indices_dithered(self, pil_img, strength=1.0):
        """Floyd-Steinberg 误差扩散匹配（CIELAB 空间）：渐变更柔和，返回 (H,W) 索引矩阵

        误差在 Lab 空间累加并 clamp 到合法域，防止极端参数下漂移；
        渐变区噪点与饱和色映错色相由感知均匀的 Lab 距离修复。
        """
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        arr = rgb_to_lab(np.asarray(pil_img, dtype=np.float32))
        arr = arr.copy()
        h, w_, _ = arr.shape
        out = np.empty((h, w_), dtype=np.int32)
        pal = self._lab
        scale = float(strength)
        for y in range(h):
            row = arr[y]
            for x in range(w_):
                px = row[x]
                np.clip(px, _LAB_MIN, _LAB_MAX, out=px)
                d = pal - px
                idx = int(np.argmin((d * d).sum(-1)))
                out[y, x] = idx
                err = (px - pal[idx]) * scale
                if x + 1 < w_:
                    row[x + 1] += err * (7 / 16)
                if y + 1 < h:
                    nxt = arr[y + 1]
                    if x > 0:
                        nxt[x - 1] += err * (3 / 16)
                    nxt[x] += err * (5 / 16)
                    if x + 1 < w_:
                        nxt[x + 1] += err * (1 / 16)
        return out

    def find_closest_color(self, r, g, b):
        """找到色卡中最接近的颜色（CIELAB 距离，备用路径）"""
        lab = rgb_to_lab(np.array([[(r, g, b)]], dtype=np.float32))[0]
        d = self._lab - lab
        closest_index = int(np.argmin((d * d).sum(-1)))

        return (self.colors[closest_index],
                self.names[closest_index],
                self.codes[closest_index],
                closest_index)

    def get_color_info(self, index):
        """获取单个颜色的完整信息"""
        if 0 <= index < len(self.colors):
            return {
                'code': self.codes[index].strip(),
                'name': self.names[index].strip(),
                'rgb': self.colors[index],
                'hex': self.hex_codes[index]
            }
        return None


def get_palette(palette_name):
    if palette_name == "my_colors":
        from .my_colors import load_my_colors
        data = load_my_colors()
        if data:
            _PALETTE_CACHE["my_colors"] = data
        elif "my_colors" in _PALETTE_CACHE:
            _PALETTE_CACHE.pop("my_colors", None)
    return ColorPalette(palette_name)


def display_to_internal(display_name, default="mard_221"):
    """色卡展示名 → internal 名（未知名称回退 mard_221）"""
    for display, internal in PALETTE_OPTIONS:
        if display == display_name:
            return internal
    return default


load_palettes()
