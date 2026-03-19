# core/processor.py
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .colors import get_palette
from .pdf_exporter import PDFExporter


class ImageProcessor:
    def __init__(self):
        self.output_dir = "output"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self._font_cache = {}
        self.pdf_exporter = PDFExporter()

    def _get_font(self, size, bold=False):
        """获取缓存的字体对象 - 带 fallback 机制"""
        cache_key = f"{size}_{bold}"
        if cache_key not in self._font_cache:
            font_obj = None
            try:
                font_name = "msyh.ttc" if bold else "msyh.ttf"
                font_obj = ImageFont.truetype(font_name, size)
            except Exception:
                try:
                    font_name = "simhei.ttf" if bold else "simsun.ttc"
                    font_obj = ImageFont.truetype(font_name, size)
                except Exception:
                    font_obj = ImageFont.load_default()

            self._font_cache[cache_key] = font_obj
        return self._font_cache[cache_key]

    def process_batch(self, image_paths, grid_w, grid_h, **kwargs):
        """
        批量处理图像序列引擎 (Batch Processing Generator)
        利用 Python 生成器 (Generator) 机制返回进度，防止主线程 UI 卡死
        """
        total = len(image_paths)
        results = []
        for idx, path in enumerate(image_paths):
            try:
                # 依次调用核心处理管线
                res = self.process_image(image_path=path, grid_w=grid_w, grid_h=grid_h, **kwargs)
                results.append({"path": path, "status": "success", "data": res})
            except Exception as e:
                results.append({"path": path, "status": "error", "message": str(e)})

            # 向上层 UI yield 进度与当前结果
            yield {"current": idx + 1, "total": total, "latest_result": results[-1]}

    def process_image(self, image_path, grid_w, grid_h, canvas_size=1500,
                      show_grid=True, grid_color=(200, 200, 200), grid_width=1,
                      palette_name="mard_221", show_color_legend=True,
                      show_row_col_labels=True, crop_box=None, outline_black=False):
        """
        生成专业拼豆图纸 - 新增局部框选、透明度解析与边缘黑化矩阵运算

        Args:
            crop_box: tuple (left, top, right, bottom) 局部裁剪框坐标
            outline_black: bool 是否对主体进行边缘黑化处理
        """
        try:
            # 强制转换为 RGBA 以确保兼容透明度通道运算
            img = Image.open(image_path).convert("RGBA")

            # 特性 1：局部裁剪 (Local Cropping)
            if crop_box is not None:
                img = img.crop(crop_box)

            orig_w, orig_h = img.size

            # 保持原始比例下采样
            scale = min(grid_w / orig_w, grid_h / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            if grid_w >= grid_h:
                final_grid_w = grid_w
                final_grid_h = max(1, int(grid_w * orig_h / orig_w))
            else:
                final_grid_h = grid_h
                final_grid_w = max(1, int(grid_h * orig_w / orig_h))

            # NEAREST 保证像素艺术的锐利度，不产生插值过渡色
            small_img = img.resize((final_grid_w, final_grid_h), resample=Image.NEAREST)

            # --- 特性 2：透明通道解析与边缘黑化 (Alpha Channel & Outline) ---
            # 零开销内存视图转换：PIL -> NumPy Tensor (H, W, 4)
            img_tensor = np.array(small_img)

            # 提取 Alpha 通道生成二值化掩膜 (阈值设为 128)
            alpha_channel = img_tensor[:, :, 3]
            mask = (alpha_channel > 128).astype(np.uint8)

            if outline_black:
                # 构造 3x3 十字交叉核 (Cross Kernel)
                # 使用十字核而非全 1 矩阵，是为了避免在斜向对角线产生过度粗糙的边缘
                kernel = np.array([
                    [0, 1, 0],
                    [1, 1, 1],
                    [0, 1, 0]
                ], dtype=np.uint8)

                # 数学形态学操作：内部腐蚀
                eroded_mask = cv2.erode(mask, kernel, iterations=1)

                # 异或操作 (XOR) 提取完美单像素边缘
                edge_mask = mask ^ eroded_mask

                # 内存连续性赋值：将边缘区域直接覆写为纯黑 (R=0, G=0, B=0, A=255)
                img_tensor[edge_mask == 1] = [0, 0, 0, 255]

            palette = get_palette(palette_name)

            # 颜色映射与统计初始化
            color_stats = {}
            grid_codes = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]
            grid_colors = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]

            # O(W*H) 密集运算区
            for y in range(final_grid_h):
                for x in range(final_grid_w):
                    # 如果该像素处于透明区域 (mask == 0)，直接跳过匹配，极大幅度降低欧氏距离计算开销
                    if mask[y, x] == 0:
                        continue

                    r, g, b, _ = img_tensor[y, x]
                    closest_rgb, closest_name, closest_code, closest_idx = palette.find_closest_color(r, g, b)
                    grid_colors[y][x] = closest_rgb
                    grid_codes[y][x] = closest_code

                    if closest_code not in color_stats:
                        color_stats[closest_code] = {
                            "rgb": closest_rgb, "name": closest_name,
                            "code": closest_code, "count": 0, "index": closest_idx
                        }
                    color_stats[closest_code]["count"] += 1

            total_beads = sum(info['count'] for info in color_stats.values())

            # 计算画布与布局参数
            base_cell_size = max(20, canvas_size // max(final_grid_w, final_grid_h))
            cell_size = base_cell_size
            draw_width = cell_size * final_grid_w
            draw_height = cell_size * final_grid_h

            label_margin = max(40, int(cell_size * 0.6)) if show_row_col_labels else 0

            legend_height = 0
            if show_color_legend and color_stats:
                colors_per_row = 10
                legend_rows = (len(color_stats) + colors_per_row - 1) // colors_per_row
                legend_height = legend_rows * 70 + 80

            total_width = max(draw_width + label_margin * 2, 1000)
            total_height = draw_height + label_margin * 2 + legend_height

            final_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
            draw = ImageDraw.Draw(final_img)

            start_x = label_margin + (total_width - label_margin * 2 - draw_width) // 2
            start_y = label_margin

            if show_row_col_labels:
                self._draw_row_col_labels(draw, final_grid_w, final_grid_h,
                                          start_x, start_y, cell_size,
                                          total_width, total_height, label_margin)

            # 绘制网格
            for y in range(final_grid_h):
                for x in range(final_grid_w):
                    x1 = start_x + x * cell_size
                    y1 = start_y + y * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size

                    color = grid_colors[y][x]

                    if color is not None:
                        # 绘制实体豆子
                        draw.rectangle([x1, y1, x2, y2], fill=color)

                        if show_grid:
                            draw.rectangle([x1, y1, x2, y2], outline=grid_color, width=grid_width)

                        if cell_size >= 12:
                            code = grid_codes[y][x]
                            font_size = max(8, min(int(cell_size * 0.35), 20))
                            font = self._get_font(font_size)

                            bbox = draw.textbbox((0, 0), code, font=font)
                            text_w = bbox[2] - bbox[0]
                            text_h = bbox[3] - bbox[1]
                            text_x = x1 + (cell_size - text_w) // 2
                            text_y = y1 + (cell_size - text_h) // 2

                            brightness = sum(color) / 3
                            text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                            draw.text((text_x, text_y), code, fill=text_color, font=font)
                    else:
                        # 对于透明/裁剪剔除的空白区域，只绘制空网格线，不消耗豆子
                        if show_grid:
                            draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255), outline=grid_color, width=grid_width)

            # 绘制颜色图例与统计区
            if show_color_legend and color_stats:
                legend_y = draw_height + label_margin * 2 + 30
                color_items = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)

                usable_width = total_width - 40
                colors_per_row = min(10, len(color_items))
                item_width = usable_width // colors_per_row

                for i, (code, info) in enumerate(color_items):
                    row = i // colors_per_row
                    col = i % colors_per_row

                    item_x = 20 + col * item_width
                    item_y = legend_y + row * 70

                    block_size = min(50, max(40, item_width - 20))
                    block_x = item_x + (item_width - block_size) // 2

                    draw.rounded_rectangle(
                        [block_x, item_y, block_x + block_size, item_y + block_size],
                        radius=5, fill=info['rgb'], outline=(200, 200, 200), width=2
                    )

                    font_small = self._get_font(12)
                    font_normal = self._get_font(15)

                    text_x = block_x + block_size + 10
                    draw.text((text_x, item_y + 5), f"{code}", fill=(0, 0, 0), font=font_small)
                    draw.text((text_x, item_y + 24), f"{info['count']}颗", fill=(100, 100, 100), font=font_small)
                    draw.text((text_x, item_y + 42), f"{info['name']}", fill=(50, 50, 50), font=font_normal)

                footer_y = legend_y + legend_rows * 70 + 20
                draw.line([(100, footer_y), (total_width - 100, footer_y)], fill=(220, 220, 220), width=2)

                font_title = self._get_font(28, bold=True)
                font_count = self._get_font(42, bold=True)
                font_unit = self._get_font(20)

                title_text = "本次拼豆所需耗材总量"
                count_text = str(total_beads)
                unit_text = "颗豆子"

                title_w = draw.textbbox((0, 0), title_text, font=font_title)[2]
                count_w = draw.textbbox((0, 0), count_text, font=font_count)[2]
                unit_w = draw.textbbox((0, 0), unit_text, font=font_unit)[2]

                total_text_w = count_w + unit_w + 10
                start_text_x = (total_width - total_text_w) // 2
                title_x = (total_width - title_w) // 2

                draw.text((title_x, footer_y + 10), title_text, fill=(0, 120, 215), font=font_title)
                draw.text((start_text_x, footer_y + 50), count_text, fill=(0, 0, 0), font=font_count)
                draw.text((start_text_x + count_w + 8, footer_y + 60), unit_text, fill=(100, 100, 100), font=font_unit)

                info_text = f"网格尺寸：{final_grid_w} × {final_grid_h} 颗  |  画布：{total_width} × {total_height} px"
                info_font = self._get_font(16)
                info_w = draw.textbbox((0, 0), info_text, font=info_font)[2]
                info_x = (total_width - info_w) // 2
                draw.text((info_x, footer_y + 100), info_text, fill=(120, 120, 120), font=info_font)

            filename = f"perler_{final_grid_w}x{final_grid_h}_{palette_name}.png"
            save_path = os.path.join(self.output_dir, filename)
            final_img.save(save_path, quality=100, dpi=(300, 300))

            return save_path, final_img, color_stats, total_beads, final_grid_w, final_grid_h

        except Exception as e:
            print(f"[错误] 图像引擎处理崩溃：{e}")
            import traceback
            traceback.print_exc()
            return None, None, {}, 0, 0, 0

    def _draw_row_col_labels(self, draw, grid_w, grid_h, start_x, start_y, cell_size,
                             total_width, total_height, label_margin):
        """绘制行列标号 (逻辑保持不变)"""
        font_label = self._get_font(14, bold=True)
        font_small = self._get_font(11)

        label_bg = (240, 248, 255)
        label_border = (200, 210, 220)

        for col in range(grid_w):
            x1 = start_x + col * cell_size
            x2 = x1 + cell_size
            draw.rectangle([x1, 0, x2, label_margin], fill=label_bg, outline=label_border)
            num = col + 1
            if num % 5 == 0:
                text_color, font = (0, 100, 200), font_label
            else:
                text_color, font = (80, 80, 80), font_small
            text_w = draw.textbbox((0, 0), str(num), font=font)[2]
            draw.text((x1 + (cell_size - text_w) // 2, 8), str(num), fill=text_color, font=font)

        bottom_start = start_y + grid_h * cell_size
        for col in range(grid_w):
            x1 = start_x + col * cell_size
            x2 = x1 + cell_size
            draw.rectangle([x1, bottom_start, x2, bottom_start + label_margin], fill=label_bg, outline=label_border)
            num = col + 1
            if num % 5 == 0:
                text_color, font = (0, 100, 200), font_label
            else:
                text_color, font = (80, 80, 80), font_small
            text_w = draw.textbbox((0, 0), str(num), font=font)[2]
            draw.text((x1 + (cell_size - text_w) // 2, bottom_start + 8), str(num), fill=text_color, font=font)

        for row in range(grid_h):
            y1 = start_y + row * cell_size
            y2 = y1 + cell_size
            draw.rectangle([0, y1, label_margin, y2], fill=label_bg, outline=label_border)
            num = row + 1
            if num % 5 == 0:
                text_color, font = (0, 100, 200), font_label
            else:
                text_color, font = (80, 80, 80), font_small
            text_h = draw.textbbox((0, 0), str(num), font=font)[3]
            draw.text((8, y1 + (cell_size - text_h) // 2), str(num), fill=text_color, font=font)

        right_start = start_x + grid_w * cell_size
        for row in range(grid_h):
            y1 = start_y + row * cell_size
            y2 = y1 + cell_size
            draw.rectangle([right_start, y1, right_start + label_margin, y2], fill=label_bg, outline=label_border)
            num = row + 1
            if num % 5 == 0:
                text_color, font = (0, 100, 200), font_label
            else:
                text_color, font = (80, 80, 80), font_small
            text_h = draw.textbbox((0, 0), str(num), font=font)[3]
            draw.text((right_start + 8, y1 + (cell_size - text_h) // 2), str(num), fill=text_color, font=font)

        draw.rectangle([0, 0, label_margin, label_margin], fill=(0, 120, 215))

    def export_to_pdf(self, pattern_image, color_stats, grid_w, grid_h,
                      total_beads, palette_name, filename=None):
        if filename is None:
            filename = f"perler_{grid_w}x{grid_h}_{palette_name}.pdf"
        save_path = os.path.join(self.output_dir, filename)
        success = self.pdf_exporter.export(
            output_path=save_path, pattern_image=pattern_image,
            color_stats=color_stats, grid_w=grid_w, grid_h=grid_h,
            total_beads=total_beads, palette_name=palette_name
        )
        return save_path if success else None

    def export_color_list_pdf(self, color_stats, total_beads, palette_name, filename=None):
        if filename is None:
            filename = f"color_list_{palette_name}.pdf"
        save_path = os.path.join(self.output_dir, filename)
        success = self.pdf_exporter.export_color_list_only(
            output_path=save_path, color_stats=color_stats,
            total_beads=total_beads, palette_name=palette_name
        )
        return save_path if success else None