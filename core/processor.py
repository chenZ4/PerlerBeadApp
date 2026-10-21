# core/processor.py
import math
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .colors import PALETTE_OPTIONS, get_palette
from .models import (
    ACCENT, ACCENT_SOFT, DARK_ACCENT, DARK_BG, DARK_HAIRLINE, DARK_INK,
    DARK_INK_SOFT, DARK_PANEL, HAIRLINE, HAIRLINE_SOFT, HAIRLINE_STRONG, INK,
    INK_MUTED, INK_SOFT, MAX_GRID_SIZE, PAPER, PAPER_DEEP, PAPER_MAT,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

MAX_CANVAS = 12000
LABEL_MARGIN = 35
FONT_MIN_CELL = 12
MAX_FONT_SIZE = 18
# ---------- Editorial 版式（T15）----------
LEGEND_COLUMNS = 5          # 图例列数（4~5 列编辑式版面，名称/数量不重叠）
LEGEND_TOP_GAP = 34
LEGEND_TITLE_H = 70
LEGEND_ROW_H = 48
LEGEND_COL_GAP = 16
LEGEND_BOTTOM_GAP = 16
FOOTER_HEIGHT = 214         # PLATE 标题 + Didot 大数字 + 元数据行
SIDE_MARGIN = 40
GRID_WHITE = PAPER           # 兼容旧常量名：纸底（原纯白）
GRID_DEFAULT = HAIRLINE      # 默认网格线：暖发丝线（原冷灰 200,200,200）
BEAD_MM = 5.0
A4_MM = (210, 297)
FINISHED_MAX_DIM = 4096


def _round_half_up(x):
    """半上舍入（对齐 Swift .rounded() 与产品语义；Python 内建 round 是银行家舍入）"""
    return math.floor(x + 0.5)


@dataclass
class GenerateResult:
    save_path: str
    chart: Image.Image
    finished: Optional[Image.Image]
    color_stats: dict
    total_beads: int
    grid_w: int
    grid_h: int
    cell_size: int
    # 非致命提示（协议层回传 warnings；UI 状态栏可见）
    warnings: list = field(default_factory=list)


class ImageProcessor:
    def __init__(self):
        self.output_dir = OUTPUT_DIR
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self._font_cache = {}

    # ------------------------------------------------------------------
    # T15 editorial：主题 tokens / 字体 / 版式小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _theme(dark=False):
        """图纸配色（亮/暗 editorial），与 App DesignSystem Tok 同源。"""
        if dark:
            return {
                "bg": DARK_BG, "panel": DARK_PANEL, "ink": DARK_INK,
                "ink_soft": DARK_INK_SOFT, "ink_muted": DARK_INK_SOFT,
                "hairline": DARK_HAIRLINE, "hairline_strong": DARK_ACCENT,
                "accent": DARK_ACCENT, "accent_soft": (51, 38, 26),
                "paper_mat": PAPER_MAT,
            }
        return {
            "bg": PAPER, "panel": PAPER_DEEP, "ink": INK, "ink_soft": INK_SOFT,
            "ink_muted": INK_MUTED, "hairline": HAIRLINE,
            "hairline_strong": HAIRLINE_STRONG, "accent": ACCENT,
            "accent_soft": ACCENT_SOFT, "paper_mat": PAPER_MAT,
        }

    @staticmethod
    def _relative_luminance(rgb):
        def f(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])

    @classmethod
    def _cell_text_color(cls, rgb):
        """色号文字选与珠子 WCAG 对比度更高的墨色（浅珠 ink / 深珠 paperMat）。"""
        def ratio(a, b):
            la, lb = sorted((cls._relative_luminance(a),
                             cls._relative_luminance(b)), reverse=True)
            return (la + 0.05) / (lb + 0.05)
        return INK if ratio(INK, rgb) >= ratio(PAPER_MAT, rgb) else PAPER_MAT

    @staticmethod
    def _legend_columns(color_stats):
        """图例列数/行数（4~5 列，随色数自适应）。"""
        n = len(color_stats) if color_stats else 0
        if n <= 0:
            return 0, 0
        cols = max(1, min(LEGEND_COLUMNS, n))
        return cols, (n + cols - 1) // cols

    @staticmethod
    def _palette_display(palette_name):
        for display, internal in PALETTE_OPTIONS:
            if internal == palette_name:
                return display
        return palette_name or ""

    @staticmethod
    def _thousands(n):
        try:
            return f"{int(n):,}"
        except (TypeError, ValueError):
            return str(n)

    _CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

    @classmethod
    def _text_runs(cls, text):
        """把中文/非中文拆段：[(segment, is_cjk)]；CJK 必须用含中文字形的字体。"""
        return [(m.group(0), bool(cls._CJK_RE.fullmatch(m.group(0))))
                for m in re.finditer(r"[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+",
                                     str(text))]

    def _draw_mixed_text(self, draw, x, y, text, latin_font, cjk_font, fill,
                         align="left", box_width=None):
        """CJK 感知混排：数字/ASCII 用 mono，中文用 body（PIL 不做字体回退）。

        y 为基线（anchor='ls'）；align='center' 时按 box_width 居中；
        返回总宽度。用于图例数量「颗」、页脚元数据「约…颗」等混排文本。
        """
        runs = self._text_runs(text)
        fonts = [cjk_font if is_cjk else latin_font for _, is_cjk in runs]
        widths = [draw.textlength(run, font=f)
                  for (run, _), f in zip(runs, fonts)]
        total = sum(widths)
        if align == "center" and box_width:
            x = (box_width - total) // 2
        for (run, _), f, w in zip(runs, fonts, widths):
            draw.text((x, y), run, font=f, fill=fill, anchor="ls")
            x += w
        return total

    @staticmethod
    def _physical_size(grid_w, grid_h):
        """按 5mm/颗 换算实物尺寸（cm），整数省略小数点。"""
        def one(v):
            cm = v * BEAD_MM / 10.0
            return f"{cm:.0f}" if abs(cm - round(cm)) < 1e-6 else f"{cm:.1f}"
        return one(grid_w), one(grid_h)

    @staticmethod
    def _double_rule(draw, x0, x1, y, theme):
        """双发丝线：外 hairlineStrong 2px + 内 hairline 1px。"""
        draw.line([(x0, y), (x1, y)], fill=theme["hairline_strong"], width=2)
        draw.line([(x0, y + 6), (x1, y + 6)], fill=theme["hairline"], width=1)

    @staticmethod
    def _fleuron(draw, cx, cy, size=5, color=ACCENT):
        """菱形 fleuron（accent 描边）。"""
        draw.polygon([(cx, cy - size), (cx + size, cy),
                      (cx, cy + size), (cx - size, cy)],
                     outline=color, width=1)

    def _get_font(self, size, bold=False, role="body"):
        """获取缓存字体对象。role: body(PingFang) / serif(Songti) /
        display(Didot/Georgia 数字) / mono(Menlo)。"""
        cache_key = f"{role}_{size}_{bold}"
        if cache_key not in self._font_cache:
            self._font_cache[cache_key] = self._load_font(size, bold, role)
        return self._font_cache[cache_key]

    def _load_font(self, size, bold=False, role="body"):
        for font_name in self._font_candidates(bold, role):
            try:
                return ImageFont.truetype(font_name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _font_candidates(self, bold=False, role="body"):
        """按平台返回字体回退链（T15：宋体展示字 Songti / Didot / Georgia）。

        mac：PingFang 正文、Songti 衬线、Didot/Georgia 数字展示、Menlo 等宽；
        win：msyh 正文、simsun 衬线、Georgia 数字、consola 等宽；
        其它：Noto Sans/Serif CJK、DejaVu。全部有回退，无新依赖。
        """
        if sys.platform == "darwin":
            body = ["/System/Library/Fonts/PingFang.ttc",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc",
                    "/System/Library/Fonts/STHeiti Medium.ttc",
                    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]
            serif = ["/System/Library/Fonts/Supplemental/Songti.ttc",
                     "/System/Library/Fonts/STHeiti Medium.ttc",
                     "/System/Library/Fonts/PingFang.ttc"]
            display = ["/System/Library/Fonts/Supplemental/Didot.ttc",
                       "/System/Library/Fonts/Supplemental/Georgia.ttf",
                       "/System/Library/Fonts/Supplemental/Baskerville.ttc",
                       "/System/Library/Fonts/Supplemental/Songti.ttc"]
            mono = ["/System/Library/Fonts/Menlo.ttc",
                    "/System/Library/Fonts/SFNSMono.ttf",
                    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]
        elif sys.platform == "win32":
            body = ["msyhbd.ttc" if bold else "msyh.ttc", "msyh.ttf",
                    "simhei.ttf", "arial.ttf"]
            serif = ["simsun.ttc", "msyh.ttc", "simhei.ttf"]
            display = ["georgia.ttf", "times.ttf", "msyh.ttc"]
            mono = ["consola.ttf", "cour.ttf", "msyh.ttc"]
        else:
            body = ["Noto Sans CJK SC", "NotoSansCJK-Regular.ttc",
                    "wqy-microhei.ttc", "DejaVuSans.ttf"]
            serif = ["Noto Serif CJK SC", "NotoSerifCJK-Regular.ttc",
                     "DejaVuSerif.ttf", "DejaVuSans.ttf"]
            display = ["DejaVuSerif.ttf", "DejaVuSans.ttf"]
            mono = ["DejaVuSansMono.ttf", "DejaVuSans.ttf"]
        return {"body": body, "serif": serif, "display": display,
                "mono": mono}.get(role, body)

    def process_image(self, image_path, grid_w, grid_h, canvas_size=1500,
                      cell_size=None, max_canvas=MAX_CANVAS,
                      fit_box=False, exact_grid=False, show_finished=False,
                      effects=None, grid_overrides=None,
                      show_grid=True, grid_color=GRID_DEFAULT, grid_width=1,
                      palette_name="mard_221", show_color_legend=True,
                      show_row_col_labels=True, save=True,
                      cancel_callback=None) -> Optional[GenerateResult]:
        """生成专业拼豆图纸 - 带行列标号和页脚统计

        cell_size: 每格像素（与格子数解耦）；不传时用 canvas_size // 最大格子（旧逻辑）
        max_canvas: 输出总边长上限保护
        fit_box: True 时按请求框等比完整放入（取小），False 时按较宽一侧为基准
        exact_grid: True 时强制精确网格（不按源图比例调整，忽略 fit_box）
        show_finished: True 时额外渲染一张纯色成品效果图（预览用，4096px 上限降采样）
        effects: [{"id": ..., "params": {...}}] 特效链（全部默认关闭）
        grid_overrides: {(y, x): code} 手动编辑覆盖（映射后应用）
        cancel_callback: 每行检测的取消回调，返回 True 则中止
        返回: GenerateResult；失败/取消返回 None
        """
        try:
            grid_w = max(1, min(int(grid_w), MAX_GRID_SIZE))
            grid_h = max(1, min(int(grid_h), MAX_GRID_SIZE))
            with Image.open(image_path) as opened:
                # 带 alpha 的源图必须保留透明通道（透明格 = 空格，无珠）；
                # 提前 convert("RGB") 会让下方 alpha_mask 成为死代码
                if opened.mode in ("RGBA", "LA", "PA") or "transparency" in opened.info:
                    img = opened.convert("RGBA")
                else:
                    img = opened.convert("RGB")
            orig_w, orig_h = img.size

            # 0. 特效：几何变形 + 预处理（作用于原图）
            ctx = None
            if effects:
                from core.effects import EffectContext, apply_phase, has_effect
                ctx = EffectContext(palette=None, grid_w=0, grid_h=0,
                                    cell_size=0, engine=self)
                img = apply_phase(effects, "geometric", img, ctx)
                img = apply_phase(effects, "preprocess", img, ctx)
                orig_w, orig_h = img.size

            # 1. 最终网格：WYSIWYG 路由（UI 实时联动的配对必须原样生效）
            # 候选 = 宽基准 / 高基准（保持源图比例，半上舍入对齐 UI 的 rounded()）
            cand_w = (grid_w, max(1, _round_half_up(grid_w * orig_h / orig_w)))
            cand_h = (max(1, _round_half_up(grid_h * orig_w / orig_h)), grid_h)
            if exact_grid:
                final_grid_w = max(1, grid_w)
                final_grid_h = max(1, grid_h)
            elif fit_box:
                if cand_w[0] == grid_w and cand_w[1] == grid_h:
                    final_grid_w, final_grid_h = cand_w
                elif cand_h[0] == grid_w and cand_h[1] == grid_h:
                    final_grid_w, final_grid_h = cand_h
                else:
                    # 模糊请求（非联动对）：回退等比完整放入框内语义
                    scale = min(grid_w / orig_w, grid_h / orig_h)
                    final_grid_w = max(1, _round_half_up(orig_w * scale))
                    final_grid_h = max(1, _round_half_up(orig_h * scale))
            elif cand_w == (grid_w, grid_h):
                final_grid_w, final_grid_h = cand_w
            elif cand_h == (grid_w, grid_h):
                final_grid_w, final_grid_h = cand_h
            else:
                # 模糊请求（非联动对）：保持文档语义「按原图比例（宽为基准）」
                final_grid_w, final_grid_h = cand_w

            # 几何特效（chibi/crop）可能改变画幅 → 告知调用方网格被改写
            if effects and ctx is not None and (
                    has_effect(effects, "chibi") or has_effect(effects, "crop")):
                if (final_grid_w, final_grid_h) != (grid_w, grid_h):
                    ctx.warnings.append(
                        f"几何特效改变画幅：网格 {grid_w}×{grid_h} → "
                        f"{final_grid_w}×{final_grid_h}")

            # BOX（面积平均）下采样：NEAREST 单像素采样在照片上噪声大
            small_img = img.resize((final_grid_w, final_grid_h), resample=Image.BOX)

            # 2. 加载色卡
            palette = get_palette(palette_name)

            # 3. 颜色映射 + 统计（支持 RGBA：透明像素为空格，无珠）
            grid_codes = [[None] * final_grid_w for _ in range(final_grid_h)]
            grid_colors = [[None] * final_grid_w for _ in range(final_grid_h)]
            grid_idx = [[-1] * final_grid_w for _ in range(final_grid_h)]
            color_stats = {}

            alpha_mask = None
            map_img = small_img
            if small_img.mode == "RGBA":
                import numpy as _np
                alpha_mask = (_np.asarray(small_img)[..., 3] >= 128)
                map_img = small_img.convert("RGB")

            try:
                import numpy as np  # noqa: F401
                if effects and has_effect(effects, "dither"):
                    dither_params = {}
                    for _e in effects:
                        if _e.get("id") == "dither":
                            dither_params = _e.get("params") or {}
                    # 复用注册表 schema 钳制（旧实现直接读原始值，strength=5 会绕
                    # 过 schema max=1.5 把图抖成噪点）
                    from core.effects.registry import coerce_params as _coerce
                    _coerced, _changed = _coerce("dither", dither_params)
                    strength = _coerced.get("strength", 1.0)
                    if _changed and ctx is not None:
                        ctx.warnings.append(
                            f"抖动 strength 已按参数范围钳制到 {strength}（0~1.5）")
                    index_map = palette.closest_indices_dithered(map_img, strength)
                else:
                    index_map = palette.closest_indices(map_img)
            except ImportError:
                index_map = None

            for y in range(final_grid_h):
                if cancel_callback:
                    try:
                        cancelled = cancel_callback(y, final_grid_h)
                    except TypeError:
                        cancelled = cancel_callback()
                    if cancelled:
                        return None
                for x in range(final_grid_w):
                    if alpha_mask is not None and not alpha_mask[y, x]:
                        continue
                    if index_map is not None:
                        closest_idx = int(index_map[y, x])
                        closest_rgb = palette.colors[closest_idx]
                        closest_name = palette.names[closest_idx].strip()
                        closest_code = palette.codes[closest_idx].strip()
                    else:
                        r, g, b = map_img.getpixel((x, y))
                        closest_rgb, closest_name, closest_code, closest_idx = \
                            palette.find_closest_color(r, g, b)
                    grid_colors[y][x] = closest_rgb
                    grid_codes[y][x] = closest_code
                    grid_idx[y][x] = closest_idx

                    if closest_code not in color_stats:
                        color_stats[closest_code] = {
                            "rgb": closest_rgb, "name": closest_name,
                            "code": closest_code, "count": 0, "index": closest_idx
                        }
                    color_stats[closest_code]["count"] += 1

            total_beads = sum(info['count'] for info in color_stats.values())

            # 3.4 手动编辑覆盖（grid_overrides: {(y,x): code}）
            if grid_overrides:
                color_stats = self._apply_grid_overrides(
                    grid_overrides, palette, grid_colors, grid_codes, grid_idx)
                total_beads = sum(info['count'] for info in color_stats.values())

            # 3.5 特效：网格阶段（作用于映射后的 grid 索引矩阵）
            if effects:
                from core.effects import apply_phase
                if ctx is None:
                    from core.effects import EffectContext
                    ctx = EffectContext(palette=palette, grid_w=final_grid_w,
                                        grid_h=final_grid_h, cell_size=0, engine=self)
                else:
                    ctx.palette = palette
                    ctx.grid_w = final_grid_w
                    ctx.grid_h = final_grid_h
                import numpy as np
                idx_mat = np.asarray(grid_idx, dtype=np.int32)
                idx_mat = apply_phase(effects, "grid", idx_mat, ctx)
                for y in range(final_grid_h):
                    for x in range(final_grid_w):
                        ci = int(idx_mat[y, x])
                        if ci == -1:
                            continue
                        if 0 <= ci < len(palette.colors):
                            grid_colors[y][x] = palette.colors[ci]
                            grid_codes[y][x] = palette.codes[ci].strip()
                            grid_idx[y][x] = ci
                # grid 特效可能改色 → 重建颜色统计（空格不计入）
                color_stats = self._rebuild_stats(palette, grid_colors, grid_codes, grid_idx)
                # 手动编辑优先：特效后重新应用 overrides（编辑格不被描边/限色覆盖）
                if grid_overrides:
                    color_stats = self._apply_grid_overrides(
                        grid_overrides, palette, grid_colors, grid_codes, grid_idx)
                total_beads = sum(info['count'] for info in color_stats.values())

            # 4. 计算画布尺寸（每格像素与格子数解耦）
            if cell_size is not None:
                try:
                    cell_size = int(cell_size)
                except (TypeError, ValueError):
                    cell_size = 0
            if cell_size and cell_size > 0:
                cell_size = int(cell_size)
                cap = max(1, max_canvas // max(final_grid_w, final_grid_h, 1))
                cell_size = min(cell_size, cap)
            else:
                cell_size = max(1, canvas_size // max(final_grid_w, final_grid_h, 1))
            draw_width = cell_size * final_grid_w
            draw_height = cell_size * final_grid_h

            # 5. 计算布局区域（T15：图例 4~5 列 + 编辑式页脚，高度自适应）
            label_margin = LABEL_MARGIN if show_row_col_labels else 0

            legend_rows = 0
            legend_height = 0
            if show_color_legend and color_stats:
                _cols, legend_rows = self._legend_columns(color_stats)
                legend_height = (LEGEND_TOP_GAP + LEGEND_TITLE_H
                                 + legend_rows * LEGEND_ROW_H
                                 + LEGEND_BOTTOM_GAP + FOOTER_HEIGHT)

            total_width = max(draw_width + label_margin * 2, 1000)
            total_height = label_margin * 2 + draw_height + legend_height

            # 6. 创建画布（特效 chart 阶段可修改渲染参数）
            render_opts = {
                "background": GRID_WHITE,
                "grid_color": grid_color,
                "show_grid": show_grid,
                "dark": False,
            }
            if effects:
                from core.effects import apply_phase
                render_opts = apply_phase(effects, "chart", render_opts, ctx) or render_opts
            final_img = Image.new('RGB', (total_width, total_height), render_opts["background"])
            draw = ImageDraw.Draw(final_img)

            # 7. 计算网格起始位置
            start_x = label_margin + (total_width - label_margin * 2 - draw_width) // 2
            start_y = label_margin

            # 8. 绘制行列标号
            if show_row_col_labels:
                self._draw_row_col_labels(draw, final_grid_w, final_grid_h,
                                          start_x, start_y, cell_size,
                                          label_margin,
                                          dark=render_opts.get("dark", False))

            # 9. 绘制网格和颜色（成品图为预览降采样版，纯色块缩放无损）
            finished_img = None
            finished_draw = None
            finished_cell = cell_size
            if show_finished:
                finished_scale = min(1.0, FINISHED_MAX_DIM / draw_width,
                                     FINISHED_MAX_DIM / draw_height)
                finished_cell = max(1, int(cell_size * finished_scale))
                finished_img = Image.new(
                    'RGB', (finished_cell * final_grid_w, finished_cell * final_grid_h), GRID_WHITE)
                finished_draw = ImageDraw.Draw(finished_img)

            for y in range(final_grid_h):
                if cancel_callback:
                    try:
                        cancelled = cancel_callback(y, final_grid_h)
                    except TypeError:
                        cancelled = cancel_callback()
                    if cancelled:
                        return None
                for x in range(final_grid_w):
                    color = grid_colors[y][x]
                    if color is None:
                        continue
                    x1 = start_x + x * cell_size
                    y1 = start_y + y * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size

                    draw.rectangle([x1, y1, x2, y2], fill=color)

                    if finished_draw is not None:
                        finished_draw.rectangle(
                            [x * finished_cell, y * finished_cell,
                             (x + 1) * finished_cell, (y + 1) * finished_cell],
                            fill=color)

                    if show_grid:
                        draw.rectangle([x1, y1, x2, y2], outline=render_opts["grid_color"], width=grid_width)

                    if cell_size >= FONT_MIN_CELL:
                        code = grid_codes[y][x]
                        font_size = max(7, min(int(round(cell_size * 0.34)), MAX_FONT_SIZE))
                        font = self._get_font(font_size, role="mono")

                        bbox = draw.textbbox((0, 0), code, font=font)
                        text_w = bbox[2] - bbox[0]
                        text_h = bbox[3] - bbox[1]
                        text_x = x1 + (cell_size - text_w) // 2
                        text_y = y1 + (cell_size - text_h) // 2

                        # T15：浅珠 ink / 深珠 paperMat，按 WCAG 对比度取更高者
                        text_color = self._cell_text_color(color)
                        draw.text((text_x, text_y), code, fill=text_color, font=font)

            # 10. 绘制颜色图例 + 页脚
            if show_color_legend and color_stats:
                self._draw_legend_footer(draw, final_grid_w, final_grid_h,
                                         cell_size, total_width, total_height,
                                         color_stats, total_beads,
                                         label_margin, legend_rows,
                                         dark=render_opts.get("dark", False),
                                         palette_name=palette_name)

            # 11. 保存
            save_path = ""
            if save:
                filename = f"perler_{final_grid_w}x{final_grid_h}_{palette_name}.png"
                save_path = os.path.join(self.output_dir, filename)
                final_img.save(save_path, quality=95)

            return GenerateResult(
                save_path=save_path, chart=final_img, finished=finished_img,
                color_stats=color_stats, total_beads=total_beads,
                grid_w=final_grid_w, grid_h=final_grid_h, cell_size=cell_size,
                warnings=list(ctx.warnings) if ctx is not None else [])

        except Exception as e:
            # 走 stderr：stdout 是 core_server 的 JSON 行协议通道，绝不能污染
            print(f"[错误] 处理失败：{e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _rebuild_stats(palette, grid_colors, grid_codes, grid_idx):
        color_stats = {}
        for y in range(len(grid_codes)):
            for x in range(len(grid_codes[y])):
                code = grid_codes[y][x]
                if code is None:
                    continue
                ci = grid_idx[y][x]
                if code not in color_stats:
                    color_stats[code] = {
                        "rgb": grid_colors[y][x],
                        "name": palette.names[ci].strip(),
                        "code": code, "count": 0, "index": ci,
                    }
                color_stats[code]["count"] += 1
        return color_stats

    def _apply_grid_overrides(self, grid_overrides, palette,
                              grid_colors, grid_codes, grid_idx):
        """应用手动编辑覆盖并重建统计（编辑优先于特效）"""
        code_to_idx = {c: i for i, c in enumerate(palette.codes)}
        for (y, x), code in grid_overrides.items():
            if not (0 <= y < len(grid_codes) and 0 <= x < len(grid_codes[y])):
                continue
            ci = code_to_idx.get(str(code).strip())
            if ci is None:
                continue
            grid_colors[y][x] = palette.colors[ci]
            grid_codes[y][x] = palette.codes[ci].strip()
            grid_idx[y][x] = ci
        return self._rebuild_stats(palette, grid_colors, grid_codes, grid_idx)

    def _draw_legend_footer(self, draw, grid_w, grid_h, cell_size,
                            total_width, total_height, color_stats, total_beads,
                            label_margin, legend_rows, dark=False,
                            palette_name=""):
        """T15 编辑式图例 + PLATE 页脚（MATERIALS 标题/双线/方形色块/发丝线）。"""
        theme = self._theme(dark)
        color_items = sorted(color_stats.items(), key=lambda x: x[1]['count'],
                             reverse=True)
        cols = max(1, min(LEGEND_COLUMNS, len(color_items)))
        usable = total_width - 2 * SIDE_MARGIN
        item_w = usable // max(1, cols)
        legend_y = label_margin * 2 + grid_h * cell_size + LEGEND_TOP_GAP

        font_serif = self._get_font(22, role="serif")
        font_caption = self._get_font(11, role="mono")
        font_code = self._get_font(13, bold=True, role="mono")
        font_name = self._get_font(12, role="body")
        font_count = self._get_font(11, role="mono")
        font_count_zh = self._get_font(11, role="body")

        # 分区标题：MATERIALS · 耗材清单（serif）+ 右侧 PLATE 01 · BOM
        draw.text((SIDE_MARGIN, legend_y), "MATERIALS", font=font_serif,
                  fill=theme["ink"], stroke_width=1, stroke_fill=theme["ink"])
        w_m = draw.textlength("MATERIALS", font=font_serif)
        draw.text((SIDE_MARGIN + w_m + 8, legend_y + 3), "· 耗材清单",
                  font=font_serif, fill=theme["ink_soft"])
        right = "PLATE 01 · BOM"
        w_right = draw.textlength(right, font=font_caption)
        draw.text((total_width - SIDE_MARGIN - w_right, legend_y + 8), right,
                  font=font_caption, fill=theme["ink_muted"])

        # 双发丝线 + 中央菱形 fleuron
        rule_y = legend_y + LEGEND_TITLE_H - 26
        self._double_rule(draw, SIDE_MARGIN, total_width - SIDE_MARGIN, rule_y, theme)
        self._fleuron(draw, total_width // 2, rule_y + 3, 5, theme["accent"])

        items_y = legend_y + LEGEND_TITLE_H
        for i, (code, info) in enumerate(color_items):
            row, col = divmod(i, cols)
            item_x = SIDE_MARGIN + col * item_w
            item_y = items_y + row * LEGEND_ROW_H
            sw = 24
            draw.rectangle([item_x, item_y + 2, item_x + sw, item_y + 2 + sw],
                           fill=tuple(info["rgb"]),
                           outline=theme["hairline_strong"], width=1)
            text_x = item_x + sw + 10
            draw.text((text_x, item_y + 1), str(code), font=font_code,
                      fill=theme["ink"])
            # 数字用 mono、「颗」用 body：Menlo 无 CJK 字形，整串会 tofu
            cnt_text = self._thousands(info["count"])
            unit_text = " 颗"
            w_num = draw.textlength(cnt_text, font=font_count)
            w_unit = draw.textlength(unit_text, font=font_count_zh)
            cnt_x = item_x + item_w - 12 - w_num - w_unit
            draw.text((cnt_x, item_y + 15), cnt_text, font=font_count,
                      fill=theme["ink_muted"], anchor="ls")
            draw.text((cnt_x + w_num, item_y + 15), unit_text,
                      font=font_count_zh, fill=theme["ink_muted"], anchor="ls")
            draw.text((text_x, item_y + 23), str(info.get("name", "")),
                      font=font_name, fill=theme["ink_soft"])
            draw.line([(item_x, item_y + LEGEND_ROW_H - 8),
                       (item_x + item_w - 14, item_y + LEGEND_ROW_H - 8)],
                      fill=theme["hairline"], width=1)

        # ---------------- PLATE 页脚 ----------------
        footer_y = (legend_y + LEGEND_TITLE_H + legend_rows * LEGEND_ROW_H
                    + LEGEND_BOTTOM_GAP)
        self._double_rule(draw, SIDE_MARGIN, total_width - SIDE_MARGIN,
                          footer_y, theme)

        font_plate = self._get_font(21, role="serif")
        font_unit = self._get_font(14, role="serif")
        font_meta = self._get_font(11, role="mono")
        font_meta_zh = self._get_font(11, role="body")
        font_num = self._get_font(58, role="display")

        # PLATE 01 · 拼豆图纸（serif，双行居中标）
        t1 = "PLATE 01"
        t2 = " · 拼豆图纸"
        w1 = draw.textlength(t1, font=font_plate)
        w2 = draw.textlength(t2, font=font_plate)
        tx = (total_width - w1 - w2) // 2
        draw.text((tx, footer_y + 14), t1, font=font_plate,
                  fill=theme["accent"], stroke_width=1, stroke_fill=theme["accent"])
        draw.text((tx + w1, footer_y + 14), t2, font=font_plate,
                  fill=theme["ink"])

        # Didot/Georgia 大数字 + 小号「颗」
        num_text = self._thousands(total_beads)
        unit_text = "颗"
        wn = draw.textlength(num_text, font=font_num)
        wu = draw.textlength(unit_text, font=font_unit)
        x = (total_width - wn - wu - 10) // 2
        line_y = footer_y + 52
        draw.text((x, line_y), num_text, font=font_num, fill=theme["ink"])
        draw.text((x + wn + 8, line_y + 34), unit_text, font=font_unit,
                  fill=theme["ink_muted"])

        # 元数据行：GRID · BEADS · 色卡 · 实物尺寸 · 珠径
        pname = self._palette_display(palette_name).replace(" 色", "") or "MARD 221"
        wcm, hcm = self._physical_size(grid_w, grid_h)
        meta = (f"GRID {grid_w}×{grid_h}  ·  BEADS {self._thousands(total_beads)}"
                f"  ·  COLORS {len(color_items)}  ·  {pname}"
                f"  ·  约 {wcm}×{hcm} cm  ·  5mm/颗")
        def _meta_width(f_mono, f_zh):
            return sum(draw.textlength(run, font=(f_zh if is_cjk else f_mono))
                       for run, is_cjk in self._text_runs(meta))

        wm = _meta_width(font_meta, font_meta_zh)
        if wm > usable:
            font_meta = self._get_font(9, role="mono")
            font_meta_zh = self._get_font(9, role="body")
            wm = _meta_width(font_meta, font_meta_zh)
        self._draw_mixed_text(draw, 0, footer_y + FOOTER_HEIGHT - 33, meta,
                              font_meta, font_meta_zh, theme["ink_muted"],
                              align="center", box_width=total_width)


    def export_pdf(self, pil_img, save_path, mode="a4", cell_size_px=None,
                   bom=None, bw=False):
        """导出 PDF：a4=适应A4单页, 1x1=1:1实物大小(BEAD_MM/颗)多页拼接

        bom: 材料清单 color_stats（可选，追加材料页在最前）
        bw: 黑白打印模式（灰度增强，色号文字更清晰）
        """
        if bw:
            from PIL import ImageEnhance
            pil_img = pil_img.convert("L").convert("RGB")
            pil_img = ImageEnhance.Contrast(pil_img).enhance(1.4)

        if mode == "1x1":
            pages = self._export_pdf_1x1_pages(pil_img, cell_size_px)
        else:
            pages = [self._export_pdf_a4_page(pil_img)]

        if bom:
            pages = self._pdf_bom_pages(bom, bw=bw) + pages

        dpi = 300
        pages[0].save(save_path, "PDF", resolution=dpi,
                      save_all=True, append_images=pages[1:])
        return save_path

    @staticmethod
    def _a4_page_size(dpi):
        return int(A4_MM[0] / 25.4 * dpi), int(A4_MM[1] / 25.4 * dpi)

    def _export_pdf_a4_page(self, pil_img):
        """A4 单页：暖纸底 + 双框/裁切角线 + PLATE caption（页数/尺寸语义不变）。"""
        dpi = 300
        page_w, page_h = self._a4_page_size(dpi)
        margin = int(12 / 25.4 * dpi)
        cap_h = int(14 / 25.4 * dpi)
        avail_w = page_w - margin * 2
        avail_h = page_h - margin * 2 - cap_h

        scale = min(avail_w / pil_img.width, avail_h / pil_img.height)
        new_w = max(1, int(pil_img.width * scale))
        new_h = max(1, int(pil_img.height * scale))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        page = Image.new("RGB", (page_w, page_h), PAPER)
        draw = ImageDraw.Draw(page)
        x0 = (page_w - new_w) // 2
        y0 = margin
        page.paste(resized, (x0, y0))
        # 外铜框 + 内发丝线（editorial plate 装帧）
        draw.rectangle([x0 - 8, y0 - 8, x0 + new_w + 8, y0 + new_h + 8],
                       outline=HAIRLINE_STRONG, width=2)
        draw.rectangle([x0 - 3, y0 - 3, x0 + new_w + 3, y0 + new_h + 3],
                       outline=HAIRLINE, width=1)
        # 图表内部已有完整 PLATE 页脚 → PDF 页只保留细边框 + 页码（不重复页脚）
        font_pno = self._get_font(int(5 / 25.4 * dpi), role="mono")
        pno = "01 / 01"
        wp = draw.textlength(pno, font=font_pno)
        draw.text((page_w - margin - wp,
                   page_h - margin + int(3 / 25.4 * dpi)), pno,
                  font=font_pno, fill=INK_MUTED)
        return page

    def _pdf_bom_pages(self, color_stats, bw=False):
        """BOM 材料页（300dpi A4，editorial）：serif 标题 + 双线 + 表头 +
        方形色块 + 数量/占比右对齐 + 合计；页面尺寸/分页语义不变。"""
        dpi = 300
        page_w, page_h = self._a4_page_size(dpi)
        margin = int(14 / 25.4 * dpi)
        rows = sorted(color_stats.items(), key=lambda x: -x[1]['count'])
        total = sum(v['count'] for v in color_stats.values()) or 1
        n_colors = len(rows)

        row_h = int(13 / 25.4 * dpi)
        head_h = int(56 / 25.4 * dpi)
        col_head_h = int(16 / 25.4 * dpi)
        foot_h = int(26 / 25.4 * dpi)
        per_page = max(1, (page_h - margin * 2 - head_h - col_head_h - foot_h)
                       // row_h)
        total_pages = max(1, math.ceil(len(rows) / per_page)) if rows else 1

        px = lambda mm: int(mm / 25.4 * dpi)  # noqa: E731
        font_brand = self._get_font(px(8.5), role="mono")
        font_title = self._get_font(px(17), role="serif")
        font_sub = self._get_font(px(8.5), role="serif")
        font_col = self._get_font(px(7), role="mono")
        font_code = self._get_font(px(9), role="mono")
        font_name = self._get_font(px(9), role="body")
        font_qty = self._get_font(px(9), role="mono")
        font_pct = self._get_font(px(7.5), role="mono")
        font_foot = self._get_font(px(8.5), role="serif")
        sw = px(8)
        code_x = margin + px(30)
        name_x = code_x + px(22)
        qty_right = page_w - margin - px(30)
        pct_right = page_w - margin
        theme = self._theme(False)

        pages = []
        for pi in range(total_pages):
            chunk = rows[pi * per_page:(pi + 1) * per_page]
            page = Image.new("RGB", (page_w, page_h), PAPER)
            d = ImageDraw.Draw(page)
            # 报头：第一行品牌 micro caps，第二行 serif 大标题（避免重叠）
            brand = "PERLER BEAD ATELIER · PLATE 01 · BOM"
            wb = d.textlength(brand, font=font_brand)
            d.text((page_w - margin - wb, margin), brand,
                   font=font_brand, fill=INK_MUTED)
            title_y = margin + px(13)
            d.text((margin, title_y), "MATERIALS", font=font_title, fill=INK,
                   stroke_width=2, stroke_fill=INK)
            w1 = d.textlength("MATERIALS", font=font_title)
            d.text((margin + w1 + px(5), title_y + px(4)), "· 耗材清单",
                   font=font_sub, fill=INK_SOFT)
            rule_y = margin + head_h - px(14)
            self._double_rule(d, margin, page_w - margin, rule_y, theme)
            self._fleuron(d, page_w // 2, rule_y + 3, px(2.2), ACCENT)

            # 列头
            hy = margin + head_h
            for label, x in (("SWATCH", margin), ("CODE", code_x),
                             ("NAME", name_x)):
                d.text((x, hy), label, font=font_col, fill=INK_MUTED)
            qw = d.textlength("QTY", font=font_col)
            d.text((qty_right - qw, hy), "QTY", font=font_col, fill=INK_MUTED)
            pw = d.textlength("SHARE", font=font_col)
            d.text((pct_right - pw, hy), "SHARE", font=font_col, fill=INK_MUTED)
            d.line([(margin, hy + px(7)), (page_w - margin, hy + px(7))],
                   fill=HAIRLINE, width=1)

            y = hy + col_head_h
            for code, info in chunk:
                rgb = tuple(info['rgb'])
                if bw:
                    g = int(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])
                    rgb = (g, g, g)
                d.rectangle([margin, y + px(1), margin + sw, y + px(1) + sw],
                            fill=rgb, outline=HAIRLINE_STRONG, width=1)
                d.text((code_x, y), str(code), font=font_code, fill=INK)
                d.text((name_x, y), str(info.get('name', '')), font=font_name,
                       fill=INK_SOFT)
                qt = self._thousands(info['count'])
                qw2 = d.textlength(qt, font=font_qty)
                d.text((qty_right - qw2, y), qt, font=font_qty, fill=INK)
                pt = f"{info['count'] / total * 100:.1f}%"
                pw2 = d.textlength(pt, font=font_pct)
                d.text((pct_right - pw2, y + px(1.2)), pt, font=font_pct,
                       fill=INK_MUTED)
                d.line([(margin, y + row_h - px(2)),
                        (page_w - margin, y + row_h - px(2))],
                       fill=HAIRLINE_SOFT, width=1)
                y += row_h

            # 页脚：合计（最后一页）+ 页码
            fy = page_h - margin - foot_h
            self._double_rule(d, margin, page_w - margin, fy, theme)
            if pi == total_pages - 1:
                foot = (f"TOTAL · {self._thousands(total)} 颗 · "
                        f"{n_colors} 色")
                wf = d.textlength(foot, font=font_foot)
                d.text(((page_w - wf) // 2, fy + px(9)), foot,
                       font=font_foot, fill=INK)
            pno = f"MATERIALS · {pi + 1:02d} / {total_pages:02d}"
            d.text((margin, page_h - margin + px(2)), pno,
                   font=font_brand, fill=INK_MUTED)
            pages.append(page)
        return pages

    def _export_pdf_1x1_pages(self, pil_img, cell_size_px):
        """1:1 实物大小多页：纸底 + 发丝框 + 裁切角线 + serif 页码（语义不变）。"""
        if not cell_size_px or cell_size_px <= 0:
            raise ValueError("缺少网格单元尺寸，无法按 1:1 实物大小导出")
        dpi = 300
        px_per_mm = dpi / 25.4
        scale = (BEAD_MM * px_per_mm) / cell_size_px

        new_w = max(1, int(round(pil_img.width * scale)))
        new_h = max(1, int(round(pil_img.height * scale)))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        page_w, page_h = self._a4_page_size(dpi)
        margin = int(8 * px_per_mm)
        overlap = int(8 * px_per_mm)
        avail_w = page_w - margin * 2
        avail_h = page_h - margin * 2

        cols = math.ceil(resized.width / avail_w)
        rows = math.ceil(resized.height / avail_h)
        total_pages = rows * cols
        theme = self._theme(False)
        font_cap = self._get_font(int(8 / 25.4 * dpi), role="mono")
        font_plate = self._get_font(int(8.5 / 25.4 * dpi), role="serif")

        pages = []
        for r in range(rows):
            for c in range(cols):
                page = Image.new("RGB", (page_w, page_h), PAPER)
                crop_w = avail_w + (overlap if c < cols - 1 else 0)
                crop_h = avail_h + (overlap if r < rows - 1 else 0)
                x0 = c * avail_w
                y0 = r * avail_h
                x1 = min(x0 + crop_w, resized.width)
                y1 = min(y0 + crop_h, resized.height)
                tile = resized.crop((x0, y0, x1, y1))
                page.paste(tile, (margin, margin))

                draw = ImageDraw.Draw(page)
                # 外铜框 + 内发丝线
                draw.rectangle([margin - 6, margin - 6,
                                margin + avail_w + 6, margin + avail_h + 6],
                               outline=HAIRLINE_STRONG, width=2)
                draw.rectangle([margin - 2, margin - 2,
                                margin + avail_w + 2, margin + avail_h + 2],
                               outline=HAIRLINE, width=1)
                # 四角裁切角线
                tick = int(5 * px_per_mm)
                for (ax, ay, sx, sy) in (
                        (margin, margin, 1, 1),
                        (margin + avail_w, margin, -1, 1),
                        (margin, margin + avail_h, 1, -1),
                        (margin + avail_w, margin + avail_h, -1, -1)):
                    draw.line([(ax, ay), (ax + sx * tick, ay)],
                              fill=HAIRLINE_STRONG, width=1)
                    draw.line([(ax, ay), (ax, ay + sy * tick)],
                              fill=HAIRLINE_STRONG, width=1)

                pageno = f"{r * cols + c + 1:02d} / {total_pages:02d}"
                bbox = draw.textbbox((0, 0), pageno, font=font_cap)
                draw.text((page_w - (bbox[2] - bbox[0]) - margin,
                           page_h - margin + int(2 / 25.4 * dpi)), pageno,
                          font=font_cap, fill=INK_MUTED)
                plate = "PLATE 01 · 1:1 实物大小 · 5mm/颗"
                draw.text((margin, page_h - margin + int(2 / 25.4 * dpi)),
                          plate, font=font_plate, fill=INK_MUTED)
                pages.append(page)
        return pages

    def _draw_row_col_labels(self, draw, grid_w, grid_h, start_x, start_y, cell_size,
                             label_margin, dark=False):
        """行列标号（四边统一）：paperDeep 底 + hairline 边 + ink 数字，每 5 个 accent。"""
        theme = self._theme(dark)
        label_bg = theme["panel"]
        label_border = theme["hairline"]
        text_normal = theme["ink"]
        text_strong = theme["accent"]
        font_small = self._get_font(10, role="mono")
        font_label = self._get_font(11, role="mono")

        for side in ("top", "bottom", "left", "right"):
            n = grid_w if side in ("top", "bottom") else grid_h
            for i in range(n):
                if side in ("top", "bottom"):
                    x1 = start_x + i * cell_size
                    x2 = x1 + cell_size
                    y1 = 0 if side == "top" else start_y + grid_h * cell_size
                    y2 = y1 + label_margin
                    rect = [x1, y1, x2, y2]
                else:
                    y1 = start_y + i * cell_size
                    y2 = y1 + cell_size
                    x1 = 0 if side == "left" else start_x + grid_w * cell_size
                    x2 = x1 + label_margin
                    rect = [x1, y1, x2, y2]

                draw.rectangle(rect, fill=label_bg, outline=label_border)

                num = i + 1
                if num % 5 == 0:
                    text_color = text_strong
                    font = font_label
                    stroke = 1
                else:
                    text_color = text_normal
                    font = font_small
                    stroke = 0

                bbox = draw.textbbox((0, 0), str(num), font=font)
                if side in ("top", "bottom"):
                    text_x = rect[0] + (cell_size - (bbox[2] - bbox[0])) // 2
                    text_y = rect[1] + 8
                else:
                    text_x = rect[0] + 8
                    text_y = rect[1] + (cell_size - (bbox[3] - bbox[1])) // 2
                draw.text((text_x, text_y), str(num), fill=text_color,
                          font=font, stroke_width=stroke, stroke_fill=text_color)

        # 左上角块：espresso 底 + 奶油色双框/菱形装饰
        draw.rectangle([0, 0, label_margin, label_margin], fill=INK)
        inset = max(4, label_margin // 7)
        draw.rectangle([inset, inset, label_margin - inset, label_margin - inset],
                       outline=PAPER_MAT, width=1)
        self._fleuron(draw, label_margin // 2, label_margin // 2,
                      max(3, label_margin // 10), PAPER_MAT)
