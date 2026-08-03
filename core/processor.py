# core/processor.py
import math
import os
import sys
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .colors import get_palette

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

MAX_CANVAS = 12000
LABEL_MARGIN = 35
FONT_MIN_CELL = 12
MAX_FONT_SIZE = 18
LEGEND_ROW_GAP = 70
LEGEND_TOP_GAP = 30
LEGEND_BOTTOM_GAP = 20
FOOTER_HEIGHT = 130
GRID_WHITE = (255, 255, 255)
GRID_DEFAULT = (200, 200, 200)
BEAD_MM = 5.0
A4_MM = (210, 297)
FINISHED_MAX_DIM = 4096


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


class ImageProcessor:
    def __init__(self):
        self.output_dir = OUTPUT_DIR
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self._font_cache = {}

    def _get_font(self, size, bold=False):
        """获取缓存的字体对象 - 按平台选择中文字体"""
        cache_key = f"{size}_{bold}"
        if cache_key not in self._font_cache:
            self._font_cache[cache_key] = self._load_font(size, bold)
        return self._font_cache[cache_key]

    def _load_font(self, size, bold):
        candidates = self._font_candidates(bold)
        for font_name in candidates:
            try:
                return ImageFont.truetype(font_name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _font_candidates(self, bold):
        if sys.platform == "darwin":
            base = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            ]
        elif sys.platform == "win32":
            base = ["msyhbd.ttc" if bold else "msyh.ttc",
                    "msyh.ttf", "simhei.ttf", "simsun.ttc", "arial.ttf"]
        else:
            base = ["Noto Sans CJK SC", "NotoSansCJK-Regular.ttc",
                    "wqy-microhei.ttc", "DejaVuSans.ttf"]
        return base

    def process_image(self, image_path, grid_w, grid_h, canvas_size=1500,
                      cell_size=None, max_canvas=MAX_CANVAS,
                      fit_box=False, show_finished=False,
                      effects=None, grid_overrides=None,
                      show_grid=True, grid_color=GRID_DEFAULT, grid_width=1,
                      palette_name="mard_221", show_color_legend=True,
                      show_row_col_labels=True, save=True,
                      cancel_callback=None) -> Optional[GenerateResult]:
        """生成专业拼豆图纸 - 带行列标号和页脚统计

        cell_size: 每格像素（与格子数解耦）；不传时用 canvas_size // 最大格子（旧逻辑）
        max_canvas: 输出总边长上限保护
        fit_box: True 时按请求框等比完整放入（取小），False 时按较宽一侧为基准
        show_finished: True 时额外渲染一张纯色成品效果图（预览用，4096px 上限降采样）
        effects: [{"id": ..., "params": {...}}] 特效链（全部默认关闭）
        grid_overrides: {(y, x): code} 手动编辑覆盖（映射后应用）
        cancel_callback: 每行检测的取消回调，返回 True 则中止
        返回: GenerateResult；失败/取消返回 None
        """
        try:
            grid_w = max(1, int(grid_w))
            grid_h = max(1, int(grid_h))
            with Image.open(image_path) as opened:
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

            # 1. 保持原始比例下采样
            scale = min(grid_w / orig_w, grid_h / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            if fit_box:
                final_grid_w = new_w
                final_grid_h = new_h
            elif grid_w >= grid_h:
                final_grid_w = grid_w
                final_grid_h = max(1, int(grid_w * orig_h / orig_w))
            else:
                final_grid_h = grid_h
                final_grid_w = max(1, int(grid_h * orig_w / orig_h))

            small_img = img.resize((final_grid_w, final_grid_h), resample=Image.NEAREST)

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
                    strength = dither_params.get("strength", 1.0)
                    try:
                        strength = float(strength)
                    except (TypeError, ValueError):
                        strength = 1.0
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
                code_to_idx = {c: i for i, c in enumerate(palette.codes)}
                for (y, x), code in grid_overrides.items():
                    if not (0 <= y < final_grid_h and 0 <= x < final_grid_w):
                        continue
                    ci = code_to_idx.get(str(code).strip())
                    if ci is None:
                        continue
                    grid_colors[y][x] = palette.colors[ci]
                    grid_codes[y][x] = palette.codes[ci].strip()
                    grid_idx[y][x] = ci
                color_stats = {}
                for y in range(final_grid_h):
                    for x in range(final_grid_w):
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
                color_stats = {}
                for y in range(final_grid_h):
                    for x in range(final_grid_w):
                        code = grid_codes[y][x]
                        if code is None:
                            continue
                        rgb = grid_colors[y][x]
                        ci = grid_idx[y][x]
                        if code not in color_stats:
                            color_stats[code] = {
                                "rgb": rgb,
                                "name": palette.names[ci].strip(),
                                "code": code, "count": 0, "index": ci,
                            }
                        color_stats[code]["count"] += 1

            # 4. 计算画布尺寸（每格像素与格子数解耦）
            if cell_size and cell_size > 0:
                cell_size = int(cell_size)
                cap = max(1, max_canvas // max(final_grid_w, final_grid_h, 1))
                cell_size = min(cell_size, cap)
            else:
                cell_size = max(1, canvas_size // max(final_grid_w, final_grid_h, 1))
            draw_width = cell_size * final_grid_w
            draw_height = cell_size * final_grid_h

            # 5. 计算布局区域
            label_margin = LABEL_MARGIN if show_row_col_labels else 0

            legend_rows = 0
            legend_height = 0
            if show_color_legend and color_stats:
                colors_per_row = min(10, len(color_stats))
                legend_rows = (len(color_stats) + colors_per_row - 1) // colors_per_row
                legend_height = LEGEND_TOP_GAP + legend_rows * LEGEND_ROW_GAP + LEGEND_BOTTOM_GAP + FOOTER_HEIGHT

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

                    color = grid_colors[y][x]
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
                        font_size = max(6, min(cell_size // 3, MAX_FONT_SIZE))
                        font = self._get_font(font_size)

                        bbox = draw.textbbox((0, 0), code, font=font)
                        text_w = bbox[2] - bbox[0]
                        text_h = bbox[3] - bbox[1]
                        text_x = x1 + (cell_size - text_w) // 2
                        text_y = y1 + (cell_size - text_h) // 2

                        brightness = sum(color) / 3
                        if render_opts.get("dark"):
                            text_color = (0, 0, 0) if brightness > 200 else (255, 255, 255)
                        else:
                            text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                        draw.text((text_x, text_y), code, fill=text_color, font=font)

            # 10. 绘制颜色图例 + 页脚
            if show_color_legend and color_stats:
                self._draw_legend_footer(draw, final_grid_w, final_grid_h,
                                         cell_size, total_width, total_height,
                                         color_stats, total_beads,
                                         label_margin, legend_rows,
                                         dark=render_opts.get("dark", False))

            # 11. 保存
            save_path = ""
            if save:
                filename = f"perler_{final_grid_w}x{final_grid_h}_{palette_name}.png"
                save_path = os.path.join(self.output_dir, filename)
                final_img.save(save_path, quality=95)

            return GenerateResult(
                save_path=save_path, chart=final_img, finished=finished_img,
                color_stats=color_stats, total_beads=total_beads,
                grid_w=final_grid_w, grid_h=final_grid_h, cell_size=cell_size)

        except Exception as e:
            print(f"[错误] 处理失败：{e}")
            import traceback
            traceback.print_exc()
            return None

    def _draw_legend_footer(self, draw, grid_w, grid_h, cell_size,
                            total_width, total_height, color_stats, total_beads,
                            label_margin, legend_rows, dark=False):
        legend_y = label_margin * 2 + grid_h * cell_size + LEGEND_TOP_GAP
        color_items = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)

        text_main = (235, 235, 235) if dark else (0, 0, 0)
        text_sub = (170, 170, 170) if dark else (100, 100, 100)
        text_name = (200, 200, 200) if dark else (50, 50, 50)
        line_color = (70, 70, 70) if dark else (220, 220, 220)
        title_color = (120, 190, 255) if dark else (0, 120, 215)
        info_color = (160, 160, 160) if dark else (120, 120, 120)
        block_outline = (120, 120, 120) if dark else (200, 200, 200)

        usable_width = total_width - 40
        colors_per_row = min(10, len(color_items))
        item_width = usable_width // colors_per_row

        for i, (code, info) in enumerate(color_items):
            row = i // colors_per_row
            col = i % colors_per_row

            item_x = 20 + col * item_width
            item_y = legend_y + row * LEGEND_ROW_GAP

            block_size = min(45, item_width - 15)
            block_x = item_x + (item_width - block_size) // 2

            draw.rounded_rectangle(
                [block_x, item_y, block_x + block_size, item_y + block_size],
                radius=5, fill=info['rgb'], outline=block_outline, width=1
            )

            font_small = self._get_font(11)
            font_normal = self._get_font(13)

            text_x = block_x + block_size + 8
            draw.text((text_x, item_y + 5), f"{code}", fill=text_main, font=font_small)
            draw.text((text_x, item_y + 22), f"{info['count']}颗", fill=text_sub, font=font_small)
            draw.text((text_x, item_y + 40), f"{info['name']}", fill=text_name, font=font_normal)

        # 底部耗材量页脚
        footer_y = legend_y + legend_rows * LEGEND_ROW_GAP + LEGEND_BOTTOM_GAP

        draw.line([(100, footer_y), (total_width - 100, footer_y)], fill=line_color, width=2)

        font_title = self._get_font(24, bold=True)
        font_count = self._get_font(36, bold=True)
        font_unit = self._get_font(18)

        title_text = "本次拼豆所需耗材总量"
        count_text = str(total_beads)
        unit_text = "颗豆子"

        title_w = draw.textlength(title_text, font=font_title)
        count_w = draw.textlength(count_text, font=font_count)
        unit_w = draw.textlength(unit_text, font=font_unit)

        total_text_w = count_w + unit_w + 10
        start_text_x = (total_width - total_text_w) // 2

        title_x = (total_width - title_w) // 2
        draw.text((title_x, footer_y + 10), title_text, fill=title_color, font=font_title)

        draw.text((start_text_x, footer_y + 50), count_text, fill=text_main, font=font_count)
        draw.text((start_text_x + count_w + 8, footer_y + 60), unit_text, fill=text_sub, font=font_unit)

        info_text = f"网格尺寸：{grid_w} × {grid_h} 颗  |  画布：{total_width} × {total_height} px"
        info_font = self._get_font(14)
        info_w = draw.textlength(info_text, font=info_font)
        info_x = (total_width - info_w) // 2
        draw.text((info_x, footer_y + 100), info_text, fill=info_color, font=info_font)

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
            pages = self._pdf_bom_pages(bom) + pages

        dpi = 300
        pages[0].save(save_path, "PDF", resolution=dpi,
                      save_all=True, append_images=pages[1:])
        return save_path

    @staticmethod
    def _a4_page_size(dpi):
        return int(A4_MM[0] / 25.4 * dpi), int(A4_MM[1] / 25.4 * dpi)

    def _export_pdf_a4_page(self, pil_img):
        dpi = 300
        page_w, page_h = self._a4_page_size(dpi)
        margin = int(10 / 25.4 * dpi)
        avail_w = page_w - margin * 2
        avail_h = page_h - margin * 2

        scale = min(avail_w / pil_img.width, avail_h / pil_img.height)
        new_w = max(1, int(pil_img.width * scale))
        new_h = max(1, int(pil_img.height * scale))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        page = Image.new("RGB", (page_w, page_h), GRID_WHITE)
        page.paste(resized, ((page_w - new_w) // 2, (page_h - new_h) // 2))
        return page

    def _pdf_bom_pages(self, color_stats):
        """材料清单页（300dpi A4）：色块 + 色号 + 名称 + 数量 + 占比"""
        dpi = 300
        page_w, page_h = self._a4_page_size(dpi)
        margin = int(12 / 25.4 * dpi)
        rows = sorted(color_stats.items(), key=lambda x: -x[1]['count'])
        total = sum(v['count'] for v in color_stats.values()) or 1

        pages = []
        row_h = int(15 / 25.4 * dpi)
        title_h = int(14 / 25.4 * dpi)
        per_page = (page_h - margin * 2 - title_h) // row_h

        font_title = self._get_font(64, bold=True)
        font_row = self._get_font(44)
        font_small = self._get_font(36)

        for start in range(0, len(rows), per_page):
            page = Image.new("RGB", (page_w, page_h), GRID_WHITE)
            draw = ImageDraw.Draw(page)
            draw.text((margin, margin), "材料清单", fill=(0, 120, 215), font=font_title)

            block = int(11 / 25.4 * dpi)
            y = margin + title_h
            for code, info in rows[start:start + per_page]:
                rgb = tuple(info['rgb'])
                draw.rounded_rectangle(
                    [margin, y, margin + block, y + block],
                    radius=12, fill=rgb, outline=(200, 200, 200), width=2)
                draw.text((margin + block + int(20 / 25.4 * dpi), y + 4),
                          f"{code}  {info['name']}", fill=(0, 0, 0), font=font_row)
                pct = info['count'] / total * 100
                draw.text((margin + block + int(20 / 25.4 * dpi), y + block - int(55 / 25.4 * dpi)),
                          f"{info['count']} 颗  ({pct:.1f}%)", fill=(100, 100, 100), font=font_small)
                y += row_h
            pages.append(page)
        return pages

    def _export_pdf_1x1_pages(self, pil_img, cell_size_px):
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

        pages = []
        for r in range(rows):
            for c in range(cols):
                page = Image.new("RGB", (page_w, page_h), GRID_WHITE)
                crop_w = avail_w + (overlap if c < cols - 1 else 0)
                crop_h = avail_h + (overlap if r < rows - 1 else 0)
                x0 = c * avail_w
                y0 = r * avail_h
                x1 = min(x0 + crop_w, resized.width)
                y1 = min(y0 + crop_h, resized.height)
                tile = resized.crop((x0, y0, x1, y1))
                page.paste(tile, (margin, margin))

                draw = ImageDraw.Draw(page)
                line_color = (210, 210, 210)
                draw.rectangle([margin, margin, margin + avail_w, margin + avail_h],
                               outline=line_color, width=2)

                pageno = f"{r * cols + c + 1}/{total_pages}"
                font = self._get_font(36)
                bbox = draw.textbbox((0, 0), pageno, font=font)
                draw.text((page_w - bbox[2] - margin, page_h - bbox[3] - margin // 2),
                          pageno, fill=(150, 150, 150), font=font)
                pages.append(page)
        return pages

    def _draw_row_col_labels(self, draw, grid_w, grid_h, start_x, start_y, cell_size,
                             label_margin, dark=False):
        """绘制行列标号（四边统一逻辑）"""
        font_label = self._get_font(14, bold=True)
        font_small = self._get_font(11)

        if dark:
            label_bg = (50, 50, 52)
            label_border = (75, 75, 78)
            text_strong = (120, 190, 255)
            text_normal = (185, 185, 185)
            corner = (0, 90, 160)
        else:
            label_bg = (240, 248, 255)
            label_border = (200, 210, 220)
            text_strong = (0, 100, 200)
            text_normal = (80, 80, 80)
            corner = (0, 120, 215)

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
                else:
                    text_color = text_normal
                    font = font_small

                bbox = draw.textbbox((0, 0), str(num), font=font)
                if side in ("top", "bottom"):
                    text_x = rect[0] + (cell_size - (bbox[2] - bbox[0])) // 2
                    text_y = rect[1] + 8
                else:
                    text_x = rect[0] + 8
                    text_y = rect[1] + (cell_size - (bbox[3] - bbox[1])) // 2
                draw.text((text_x, text_y), str(num), fill=text_color, font=font)

        # 左上角装饰
        draw.rectangle([0, 0, label_margin, label_margin], fill=corner)
