# core/processor.py - 完整修改版
from PIL import Image, ImageDraw, ImageFont
from .colors import get_palette
import os


class ImageProcessor:
    def __init__(self):
        self.output_dir = "output"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self._font_cache = {}

    def _get_font(self, size, bold=False):
        """获取缓存的字体对象 - 使用微软雅黑"""
        cache_key = f"{size}_{bold}"
        if cache_key not in self._font_cache:
            try:
                font_name = "msyh.ttc" if bold else "msyh.ttf"
                self._font_cache[cache_key] = ImageFont.truetype(font_name, size)
            except:
                try:
                    font_name = "simhei.ttf" if bold else "simsun.ttc"
                    self._font_cache[cache_key] = ImageFont.truetype(font_name, size)
                except:
                    self._font_cache[cache_key] = ImageFont.load_default()
        return self._font_cache[cache_key]

    def process_image(self, image_path, grid_w, grid_h, canvas_size=1500,
                      show_grid=True, grid_color=(200, 200, 200), grid_width=1,
                      palette_name="mard_221", show_color_legend=True,
                      show_row_col_labels=True):  # 🔧 新增参数
        """生成专业拼豆图纸 - 带行列标号"""
        try:
            img = Image.open(image_path).convert("RGB")
            orig_w, orig_h = img.size

            # 1. 保持原始比例下采样
            scale = min(grid_w / orig_w, grid_h / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            if grid_w >= grid_h:
                final_grid_w = grid_w
                final_grid_h = max(1, int(grid_w * orig_h / orig_w))
            else:
                final_grid_h = grid_h
                final_grid_w = max(1, int(grid_h * orig_w / orig_h))

            small_img = img.resize((final_grid_w, final_grid_h), resample=Image.NEAREST)

            # 2. 加载色卡
            palette = get_palette(palette_name)

            # 3. 颜色映射 + 统计
            pixels = small_img.load()
            color_stats = {}
            grid_codes = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]
            grid_colors = [[None for _ in range(final_grid_w)] for _ in range(final_grid_h)]

            for y in range(final_grid_h):
                for x in range(final_grid_w):
                    r, g, b = pixels[x, y]
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

            # 4. 计算画布尺寸
            cell_size = canvas_size // max(final_grid_w, final_grid_h)
            draw_width = cell_size * final_grid_w
            draw_height = cell_size * final_grid_h

            # 🔧 5. 计算行列标号区域大小
            label_margin = 0
            if show_row_col_labels:
                # 预留标号空间：顶部 + 左侧 + 底部 + 右侧
                label_margin = 35  # 每边预留 35px

            # 6. 计算图例区域
            legend_height = 0
            if show_color_legend and color_stats:
                colors_per_row = 10
                legend_rows = (len(color_stats) + colors_per_row - 1) // colors_per_row
                legend_height = legend_rows * 70 + 80

            # 🔧 7. 总画布尺寸（包含标号边距）
            total_width = max(draw_width + label_margin * 2, 1000)
            total_height = draw_height + label_margin * 2 + legend_height

            # 8. 创建画布
            final_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
            draw = ImageDraw.Draw(final_img)

            # 🔧 9. 计算网格起始位置（留出标号空间）
            start_x = label_margin + (total_width - label_margin * 2 - draw_width) // 2
            start_y = label_margin

            # 🔧 10. 绘制行列标号
            if show_row_col_labels:
                self._draw_row_col_labels(draw, final_grid_w, final_grid_h,
                                          start_x, start_y, cell_size,
                                          total_width, total_height, label_margin)

            # 11. 绘制网格和颜色
            for y in range(final_grid_h):
                for x in range(final_grid_w):
                    x1 = start_x + x * cell_size
                    y1 = start_y + y * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size

                    color = grid_colors[y][x]
                    draw.rectangle([x1, y1, x2, y2], fill=color)

                    if show_grid:
                        draw.rectangle([x1, y1, x2, y2], outline=grid_color, width=grid_width)

                    # 显示色号字母
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

            # 12. 绘制颜色图例
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

                # 底部耗材量显示
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

            # 13. 保存
            filename = f"perler_{final_grid_w}x{final_grid_h}_{palette_name}.png"
            save_path = os.path.join(self.output_dir, filename)
            final_img.save(save_path, quality=95)

            return save_path, final_img, color_stats, total_beads, final_grid_w, final_grid_h

        except Exception as e:
            print(f"[错误] 处理失败：{e}")
            import traceback
            traceback.print_exc()
            return None, None, {}, 0, 0, 0

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