# core/processor.py - 完整修改版
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from .colors import get_palette

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


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
            except:
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
                      cell_size=None, max_canvas=12000,
                      fit_box=False, show_finished=False,
                      show_grid=True, grid_color=(200, 200, 200), grid_width=1,
                      palette_name="mard_221", show_color_legend=True,
                      show_row_col_labels=True, save=True,
                      cancel_callback=None):
        """生成专业拼豆图纸 - 带行列标号和页脚统计

        cell_size: 每格像素（与格子数解耦）；不传时用 canvas_size // 最大格子（旧逻辑）
        max_canvas: 输出总边长上限保护
        fit_box: True 时按请求框等比完整放入（取小），False 时按较宽一侧为基准
        show_finished: True 时额外渲染一张纯色成品效果图（无网格/文字/图例）
        cancel_callback: 每行检测的取消回调，返回 True 则中止
        返回: (save_path, 图纸图, 成品图或None, stats, total, gw, gh, cell)
        """
        try:
            img = Image.open(image_path).convert("RGB")
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

            # 3. 颜色映射 + 统计
            grid_codes = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]
            grid_colors = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]
            color_stats = {}

            try:
                import numpy as np  # noqa: F401
                index_map = palette.closest_indices(small_img)
            except ImportError:
                index_map = None

            for y in range(final_grid_h):
                if cancel_callback and cancel_callback():
                    return None, None, None, {}, 0, 0, 0, 0
                for x in range(final_grid_w):
                    if index_map is not None:
                        closest_idx = int(index_map[y, x])
                        closest_rgb = palette.colors[closest_idx]
                        closest_name = palette.names[closest_idx].strip()
                        closest_code = palette.codes[closest_idx].strip()
                    else:
                        r, g, b = small_img.getpixel((x, y))
                        closest_rgb, closest_name, closest_code, closest_idx = \
                            palette.find_closest_color(r, g, b)
                    grid_colors[y][x] = closest_rgb
                    grid_codes[y][x] = closest_code

                    if closest_code not in color_stats:
                        color_stats[closest_code] = {
                            "rgb": closest_rgb, "name": closest_name,
                            "code": closest_code, "count": 0, "index": closest_idx
                        }
                    color_stats[closest_code]["count"] += 1

            total_beads = sum(info['count'] for info in color_stats.values())

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
            label_margin = 35 if show_row_col_labels else 0

            legend_rows = 0
            legend_height = 0
            footer_height = 0
            if show_color_legend and color_stats:
                colors_per_row = min(10, len(color_stats))
                legend_rows = (len(color_stats) + colors_per_row - 1) // colors_per_row
                footer_height = 130
                legend_height = 30 + legend_rows * 70 + 20 + footer_height

            total_width = max(draw_width + label_margin * 2, 1000)
            total_height = label_margin * 2 + draw_height + legend_height

            # 6. 创建画布
            final_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
            draw = ImageDraw.Draw(final_img)

            # 7. 计算网格起始位置
            start_x = label_margin + (total_width - label_margin * 2 - draw_width) // 2
            start_y = label_margin

            # 8. 绘制行列标号
            if show_row_col_labels:
                self._draw_row_col_labels(draw, final_grid_w, final_grid_h,
                                          start_x, start_y, cell_size,
                                          total_width, total_height, label_margin)

            # 9. 绘制网格和颜色（可选同时绘制成品效果图）
            finished_img = None
            if show_finished:
                finished_img = Image.new('RGB', (draw_width, draw_height), (255, 255, 255))
            finished_draw = ImageDraw.Draw(finished_img) if finished_img else None

            for y in range(final_grid_h):
                if cancel_callback and cancel_callback():
                    return None, None, None, {}, 0, 0, 0, 0
                for x in range(final_grid_w):
                    x1 = start_x + x * cell_size
                    y1 = start_y + y * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size

                    color = grid_colors[y][x]
                    draw.rectangle([x1, y1, x2, y2], fill=color)

                    if finished_draw is not None:
                        finished_draw.rectangle(
                            [x * cell_size, y * cell_size,
                             (x + 1) * cell_size, (y + 1) * cell_size],
                            fill=color)

                    if show_grid:
                        draw.rectangle([x1, y1, x2, y2], outline=grid_color, width=grid_width)

                    if cell_size >= 12:
                        code = grid_codes[y][x]
                        font_size = max(6, min(cell_size // 3, 18))
                        font = self._get_font(font_size)

                        bbox = draw.textbbox((0, 0), code, font=font)
                        text_w = bbox[2] - bbox[0]
                        text_h = bbox[3] - bbox[1]
                        text_x = x1 + (cell_size - text_w) // 2
                        text_y = y1 + (cell_size - text_h) // 2

                        brightness = sum(color) / 3
                        text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                        draw.text((text_x, text_y), code, fill=text_color, font=font)

            # 10. 绘制颜色图例 + 页脚
            if show_color_legend and color_stats:
                legend_y = label_margin * 2 + draw_height + 30
                color_items = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)

                usable_width = total_width - 40
                colors_per_row = min(10, len(color_items))
                item_width = usable_width // colors_per_row

                for i, (code, info) in enumerate(color_items):
                    row = i // colors_per_row
                    col = i % colors_per_row

                    item_x = 20 + col * item_width
                    item_y = legend_y + row * 70

                    block_size = min(45, item_width - 15)
                    block_x = item_x + (item_width - block_size) // 2

                    draw.rounded_rectangle(
                        [block_x, item_y, block_x + block_size, item_y + block_size],
                        radius=5, fill=info['rgb'], outline=(200, 200, 200), width=1
                    )

                    font_small = self._get_font(11)
                    font_normal = self._get_font(13)

                    text_x = block_x + block_size + 8
                    draw.text((text_x, item_y + 5), f"{code}", fill=(0, 0, 0), font=font_small)
                    draw.text((text_x, item_y + 22), f"{info['count']}颗", fill=(100, 100, 100), font=font_small)
                    draw.text((text_x, item_y + 40), f"{info['name']}", fill=(50, 50, 50), font=font_normal)

                # 底部耗材量页脚
                footer_y = legend_y + legend_rows * 70 + 20

                draw.line([(100, footer_y), (total_width - 100, footer_y)], fill=(220, 220, 220), width=2)

                font_title = self._get_font(24, bold=True)
                font_count = self._get_font(36, bold=True)
                font_unit = self._get_font(18)

                title_text = "本次拼豆所需耗材总量"
                count_text = str(total_beads)
                unit_text = "颗豆子"

                title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
                title_w = title_bbox[2] - title_bbox[0]

                count_bbox = draw.textbbox((0, 0), count_text, font=font_count)
                count_w = count_bbox[2] - count_bbox[0]

                unit_bbox = draw.textbbox((0, 0), unit_text, font=font_unit)
                unit_w = unit_bbox[2] - unit_bbox[0]

                total_text_w = count_w + unit_w + 10
                start_text_x = (total_width - total_text_w) // 2

                title_x = (total_width - title_w) // 2
                draw.text((title_x, footer_y + 10), title_text, fill=(0, 120, 215), font=font_title)

                draw.text((start_text_x, footer_y + 50), count_text, fill=(0, 0, 0), font=font_count)
                draw.text((start_text_x + count_w + 8, footer_y + 60), unit_text, fill=(100, 100, 100), font=font_unit)

                info_text = f"网格尺寸：{final_grid_w} × {final_grid_h} 颗  |  画布：{total_width} × {total_height} px"
                info_font = self._get_font(14)
                info_bbox = draw.textbbox((0, 0), info_text, font=info_font)
                info_w = info_bbox[2] - info_bbox[0]
                info_x = (total_width - info_w) // 2
                draw.text((info_x, footer_y + 100), info_text, fill=(120, 120, 120), font=info_font)

            # 11. 保存
            save_path = ""
            if save:
                filename = f"perler_{final_grid_w}x{final_grid_h}_{palette_name}.png"
                save_path = os.path.join(self.output_dir, filename)
                final_img.save(save_path, quality=95)

            return save_path, final_img, finished_img, color_stats, total_beads, final_grid_w, final_grid_h, cell_size

        except Exception as e:
            print(f"[错误] 处理失败：{e}")
            import traceback
            traceback.print_exc()
            return None, None, None, {}, 0, 0, 0, 0

    def export_pdf(self, pil_img, save_path, mode="a4", cell_size_px=None):
        """导出 PDF：a4=适应A4单页, 1x1=1:1实物大小(5mm/颗)多页拼接"""
        if mode == "1x1":
            return self._export_pdf_1x1(pil_img, save_path, cell_size_px)
        return self._export_pdf_a4(pil_img, save_path)

    def _export_pdf_a4(self, pil_img, save_path):
        dpi = 150
        page_w = int(210 / 25.4 * dpi)
        page_h = int(297 / 25.4 * dpi)
        margin = int(10 / 25.4 * dpi)
        avail_w = page_w - margin * 2
        avail_h = page_h - margin * 2

        scale = min(avail_w / pil_img.width, avail_h / pil_img.height)
        new_w = max(1, int(pil_img.width * scale))
        new_h = max(1, int(pil_img.height * scale))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        page = Image.new("RGB", (page_w, page_h), (255, 255, 255))
        page.paste(resized, ((page_w - new_w) // 2, (page_h - new_h) // 2))
        page.save(save_path, "PDF", resolution=dpi)
        return save_path

    def _export_pdf_1x1(self, pil_img, save_path, cell_size_px):
        if not cell_size_px or cell_size_px <= 0:
            raise ValueError("缺少网格单元尺寸，无法按 1:1 实物大小导出")
        bead_mm = 5.0
        dpi = 300
        px_per_mm = dpi / 25.4
        scale = (bead_mm * px_per_mm) / cell_size_px

        new_w = max(1, int(round(pil_img.width * scale)))
        new_h = max(1, int(round(pil_img.height * scale)))
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)

        page_w = int(210 * px_per_mm)
        page_h = int(297 * px_per_mm)
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
                page = Image.new("RGB", (page_w, page_h), (255, 255, 255))
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

        pages[0].save(save_path, "PDF", resolution=dpi, save_all=True, append_images=pages[1:])
        return save_path

    def _draw_row_col_labels(self, draw, grid_w, grid_h, start_x, start_y, cell_size,
                             total_width, total_height, label_margin):
        """🔧 绘制行列标号"""
        font_label = self._get_font(14, bold=True)
        font_small = self._get_font(11)

        # 背景色
        label_bg = (240, 248, 255)  # 淡蓝色背景
        label_border = (200, 210, 220)

        # === 顶部列号 ===
        for col in range(grid_w):
            x1 = start_x + col * cell_size
            x2 = x1 + cell_size

            # 背景
            draw.rectangle([x1, 0, x2, label_margin], fill=label_bg, outline=label_border)

            # 数字（每 5 格加粗显示）
            num = col + 1
            if num % 5 == 0:
                text_color = (0, 100, 200)
                font = font_label
            else:
                text_color = (80, 80, 80)
                font = font_small

            bbox = draw.textbbox((0, 0), str(num), font=font)
            text_w = bbox[2] - bbox[0]
            text_x = x1 + (cell_size - text_w) // 2
            draw.text((text_x, 8), str(num), fill=text_color, font=font)

        # === 底部列号 ===
        bottom_start = start_y + grid_h * cell_size
        for col in range(grid_w):
            x1 = start_x + col * cell_size
            x2 = x1 + cell_size

            draw.rectangle([x1, bottom_start, x2, bottom_start + label_margin],
                           fill=label_bg, outline=label_border)

            num = col + 1
            if num % 5 == 0:
                text_color = (0, 100, 200)
                font = font_label
            else:
                text_color = (80, 80, 80)
                font = font_small

            bbox = draw.textbbox((0, 0), str(num), font=font)
            text_w = bbox[2] - bbox[0]
            text_x = x1 + (cell_size - text_w) // 2
            draw.text((text_x, bottom_start + 8), str(num), fill=text_color, font=font)

        # === 左侧行号 ===
        for row in range(grid_h):
            y1 = start_y + row * cell_size
            y2 = y1 + cell_size

            draw.rectangle([0, y1, label_margin, y2], fill=label_bg, outline=label_border)

            num = row + 1
            if num % 5 == 0:
                text_color = (0, 100, 200)
                font = font_label
            else:
                text_color = (80, 80, 80)
                font = font_small

            bbox = draw.textbbox((0, 0), str(num), font=font)
            text_h = bbox[3] - bbox[1]
            text_y = y1 + (cell_size - text_h) // 2
            draw.text((8, text_y), str(num), fill=text_color, font=font)

        # === 右侧行号 ===
        right_start = start_x + grid_w * cell_size
        for row in range(grid_h):
            y1 = start_y + row * cell_size
            y2 = y1 + cell_size

            draw.rectangle([right_start, y1, right_start + label_margin, y2],
                           fill=label_bg, outline=label_border)

            num = row + 1
            if num % 5 == 0:
                text_color = (0, 100, 200)
                font = font_label
            else:
                text_color = (80, 80, 80)
                font = font_small

            bbox = draw.textbbox((0, 0), str(num), font=font)
            text_h = bbox[3] - bbox[1]
            text_y = y1 + (cell_size - text_h) // 2
            draw.text((right_start + 8, text_y), str(num), fill=text_color, font=font)

        # === 左上角装饰 ===
        draw.rectangle([0, 0, label_margin, label_margin], fill=(0, 120, 215))
