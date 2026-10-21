# core/models.py - 领域模型（纯 Python，无 UI / Tk / PIL 依赖，可独立单测）
"""拼豆工具的核心领域模型。

约定：
- 所有比例、尺寸、网格参数均以本模块常量为准（ui/core 共用）。
- 生成参数用 GenerateParams 快照，不再散落在界面控件里。
- 颜色换算、输入钳制、比例联动为纯函数，便于单测。
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json
import math
import os

# ---------- 常量 ----------
RATIO_ORIGINAL = "按原图比例（宽为基准）"
RATIO_FIT_BOX = "等比完整（适应框内）"
# 固定比例：网格尺寸必须精确，不允许引擎按源图比例重算
RATIO_FIXED = ("1:1 (正方形)", "4:3", "3:4", "16:9", "9:16")
RATIO_CUSTOM = "自定义"
RATIOS = [RATIO_ORIGINAL, RATIO_FIT_BOX] + list(RATIO_FIXED) + [RATIO_CUSTOM]

# ---------- Editorial 视觉 tokens（T15；与 qa/ui/theme/README.md / DesignSystem.swift 同源）----------
# 引擎输出（图纸 PNG / 成品 / PDF）与 App UI 共用同一套「暖纸底 + 深咖墨 + 干邑黄铜」色值。
PAPER = (244, 237, 225)             # #F4EDE1 暖羊皮纸底
PAPER_DEEP = (235, 225, 210)        # #EBE1D2 图版衬纸/分区底
PAPER_MAT = (251, 246, 236)         # #FBF6EC 卡片/奶油
INK = (42, 33, 24)                  # #2A2118 深咖墨
INK_SOFT = (77, 63, 48)             # #4D3F30 次级文字
INK_MUTED = (114, 97, 74)           # #72614A 说明/图注
HAIRLINE = (213, 196, 172)          # #D5C4AC 发丝线（默认网格线）
HAIRLINE_SOFT = (230, 217, 197)     # #E6D9C5 浅分隔
HAIRLINE_STRONG = (183, 164, 136)   # #B7A488 外铜框/裁切角线
ACCENT = (138, 90, 51)              # #8A5A33 干邑/黄铜（唯一强调色）
ACCENT_SOFT = (239, 224, 204)       # #EFE0CC 强调底
# 暗色 editorial（dark_chart 图纸）
DARK_BG = (23, 18, 13)              # #17120D espresso 底
DARK_PANEL = (30, 24, 17)           # #1E1811 面板
DARK_INK = (240, 231, 216)          # #F0E7D8 奶油色主文字
DARK_INK_SOFT = (201, 185, 159)     # #C9B99F 次级
DARK_HAIRLINE = (58, 47, 35)        # #3A2F23 暗发丝线
DARK_ACCENT = (201, 155, 99)        # #C99B63 暗色黄铜

# 默认网格线：暖发丝线（旧值 #C8C8C8 冷灰，T15 统一到 editorial tokens；
# 历史记录中已存的旧色仍按字符串原样兼容）
DEFAULT_GRID_COLOR = "#D5C4AC"
DEFAULT_GRID_RGB = HAIRLINE
DEFAULT_GRID = 50
MAX_GRID_SIZE = 500
BIG_GRID_WARN = 40000
MIN_CELL_PX = 16
MAX_CELL_PX = 160
DEFAULT_CELL_PX = 60
DEFAULT_PALETTE = "MARD 221 色"


# ---------- 纯函数 ----------
def atomic_write_json(path, data, indent=2):
    """临时文件 + os.replace 原子写 JSON，防进程中断留下半截文件"""
    tmp = f"{path}.tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    except (IOError, OSError):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def hex_to_rgb(hex_color):
    """#RRGGBB → (r, g, b)；非法输入抛 ValueError"""
    text = str(hex_color).strip().lstrip('#')
    if len(text) != 6:
        raise ValueError(f"无效颜色值：{hex_color}")
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
    except ValueError:
        raise ValueError(f"无效颜色值：{hex_color}")
    return (r, g, b)


def hex_to_rgb_safe(hex_color, default=DEFAULT_GRID_RGB):
    try:
        return hex_to_rgb(hex_color)
    except ValueError:
        return default


def parse_int(text, default, lo, hi):
    """文本 → 钳制后的整数；非法输入回退 default"""
    try:
        v = int(str(text).strip())
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def parse_grid_w(text):
    return parse_int(text, DEFAULT_GRID, 1, MAX_GRID_SIZE)


def parse_grid_h(text):
    return parse_int(text, DEFAULT_GRID, 1, MAX_GRID_SIZE)


def parse_cell_px(text):
    return parse_int(text, DEFAULT_CELL_PX, MIN_CELL_PX, MAX_CELL_PX)


def as_bool(value, default=True):
    """宽松布尔转换：bool / 'true'/'false'/'1'/'0' → bool，其他回退 default"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off"):
            return False
    return default


def _round_half_up(x):
    """半上舍入（对齐 Swift .rounded() 与引擎；Python 内建 round 是银行家舍入，
    x.5 时会向下导致与 UI 显示差 1）"""
    return math.floor(x + 0.5)


def link_dimensions(source, w, h, ratio, aspect=None):
    """按编辑来源联动另一维度（Tk 与 Swift 行为对齐）。

    source: 'w' 表示宽被编辑，'h' 表示高被编辑
    aspect: 源图像素宽高比（iw/ih）；原始比例/等比完整下传入则按源图比例联动
            （与 Swift 版实时联动一致），None 时这两种模式不联动
    返回 (w, h) 联动后的整数对；非可联动比例原样返回
    """
    if ratio == RATIO_FIT_BOX or ratio == RATIO_ORIGINAL:
        if not aspect or aspect <= 0:
            return w, h
        if source == 'w':
            return w, max(1, _round_half_up(w / aspect))
        return max(1, _round_half_up(h * aspect)), h
    if ratio not in RATIO_FIXED:
        return w, h
    if ratio == "1:1 (正方形)":
        return (w, w) if source == 'w' else (h, h)
    if ratio == "4:3":
        return (w, max(1, _round_half_up(w * 3 / 4))) if source == 'w' else (max(1, _round_half_up(h * 4 / 3)), h)
    if ratio == "3:4":
        return (w, max(1, _round_half_up(w * 4 / 3))) if source == 'w' else (max(1, _round_half_up(h * 3 / 4)), h)
    if ratio == "16:9":
        return (w, max(1, _round_half_up(w * 9 / 16))) if source == 'w' else (max(1, _round_half_up(h * 16 / 9)), h)
    if ratio == "9:16":
        return (w, max(1, _round_half_up(w * 16 / 9))) if source == 'w' else (max(1, _round_half_up(h * 9 / 16)), h)
    return w, h


def cm_hint(w, h, bead_mm=5.0):
    """成品物理尺寸提示文本（每颗默认 5mm）"""
    return f"成品约 {w * bead_mm / 10:.0f} × {h * bead_mm / 10:.0f} cm（每颗 {bead_mm:.0f}mm）"


# ---------- 数据类 ----------
@dataclass
class GenerateParams:
    """一次生成的完整参数快照。

    grid_w / grid_h 为「请求值」；最终网格由引擎按比例模式决定：
    - RATIO_ORIGINAL：以较宽一侧为基准，另一侧按源图比例
    - RATIO_FIT_BOX：等比完整放入请求框内
    - RATIO_FIXED：精确网格（exact_grid）
    """
    grid_w: int = DEFAULT_GRID
    grid_h: int = DEFAULT_GRID
    cell_px: int = DEFAULT_CELL_PX
    ratio: str = RATIO_ORIGINAL
    palette: str = DEFAULT_PALETTE          # 展示名（display_to_internal 转 internal）
    show_grid: bool = True
    show_labels: bool = True
    show_legend: bool = True
    grid_color: str = DEFAULT_GRID_COLOR

    @property
    def exact_grid(self) -> bool:
        return self.ratio in RATIO_FIXED

    @property
    def fit_box(self) -> bool:
        return self.ratio == RATIO_FIT_BOX

    @property
    def grid_rgb(self):
        return hex_to_rgb_safe(self.grid_color)

    def linked(self, source: str) -> "GenerateParams":
        """返回按 source（'w'/'h'）联动后的新参数副本（固定比例生效）"""
        w, h = link_dimensions(source, self.grid_w, self.grid_h, self.ratio)
        return GenerateParams(
            grid_w=w, grid_h=h, cell_px=self.cell_px, ratio=self.ratio,
            palette=self.palette, show_grid=self.show_grid,
            show_labels=self.show_labels, show_legend=self.show_legend,
            grid_color=self.grid_color)

    def clamp(self) -> "GenerateParams":
        return GenerateParams(
            grid_w=max(1, min(self.grid_w, MAX_GRID_SIZE)),
            grid_h=max(1, min(self.grid_h, MAX_GRID_SIZE)),
            cell_px=max(MIN_CELL_PX, min(self.cell_px, MAX_CELL_PX)),
            ratio=self.ratio, palette=self.palette, show_grid=self.show_grid,
            show_labels=self.show_labels, show_legend=self.show_legend,
            grid_color=self.grid_color)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GenerateParams":
        raw_cell_px = d.get("cell_px", d.get("output_size", d.get("canvas_size", DEFAULT_CELL_PX)))
        raw_w = d.get("width", d.get("grid_w", DEFAULT_GRID))
        raw_h = d.get("height", d.get("grid_h", DEFAULT_GRID))
        return cls(
            grid_w=parse_grid_w(raw_w),
            grid_h=parse_grid_h(raw_h),
            cell_px=parse_cell_px(raw_cell_px),
            ratio=str(d.get("ratio", RATIO_ORIGINAL)),
            palette=str(d.get("palette", DEFAULT_PALETTE)),
            show_grid=as_bool(d.get("show_grid", True)),
            show_labels=as_bool(d.get("show_labels", True)),
            show_legend=as_bool(d.get("show_legend", True)),
            grid_color=str(d.get("grid_color", DEFAULT_GRID_COLOR)),
        )


@dataclass
class QueueItem:
    """批量队列项（可持久化；兼容旧 dict 字段名）"""
    image_path: str
    params: GenerateParams = field(default_factory=GenerateParams)
    fmt: str = "PNG"                        # PNG / PDF(A4适应) / PDF(1:1实物)

    @classmethod
    def from_legacy(cls, item: Dict[str, Any]) -> "QueueItem":
        params = GenerateParams.from_dict(item)
        return cls(
            image_path=str(item.get("image_path", "")),
            params=params,
            fmt=str(item.get("format", item.get("fmt", "PNG"))),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = self.params.to_dict()
        d["image_path"] = self.image_path
        d["format"] = self.fmt
        # 保留旧字段名兼容历史持久化文件
        d["width"] = d.pop("grid_w")
        d["height"] = d.pop("grid_h")
        return d

    @property
    def export_mode(self) -> Optional[str]:
        """PDF 模式：'a4' / '1x1'；PNG 返回 None"""
        if self.fmt == "PDF(A4适应)":
            return "a4"
        if self.fmt == "PDF(1:1实物)":
            return "1x1"
        return None

    @property
    def ext(self) -> str:
        return "pdf" if self.export_mode else "png"


@dataclass
class UndoSnapshot:
    """撤销栈快照（结构化，替代裸 dict）"""
    params: GenerateParams
    selected_file: Optional[str] = None


@dataclass
class BatchResult:
    """批量处理结果汇总"""
    success: List[str] = field(default_factory=list)
    failed: List[Any] = field(default_factory=list)   # [(文件名, 错误信息), ...]
    cancelled_remaining: int = 0

    @property
    def cancelled(self) -> bool:
        return self.cancelled_remaining > 0
