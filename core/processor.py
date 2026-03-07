# core/processor.py

from PIL import Image, ImageDraw, ImageFont
from .colors import get_palette
import os


class ImageProcessor:
    def __init__(self):
        self.output_dir = "output"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def process_image(self, image_path, grid_w, grid_h, canvas_size=1500,
                      show_grid=True, grid_color=(200, 200, 200), grid_width=1,
                      palette_name="perler_24", show_color_legend=True):
        """
        生成专业拼豆图纸
        :param canvas_size: 画布大小（正方形，不含图例）
        :param grid_w: 横向豆子数量
        :param grid_h: 纵向豆子数量
        :return: (save_path, pil_image_object, color_stats)
        """
        try:
            img = Image.open(image_path).convert("RGB")

            # 1. 下采样到网格大小
            small_img = img.resize((grid_w, grid_h), resample=Image.NEAREST)

            # 2. 加载色卡
            palette = get_palette(palette_name)

            # 3. 颜色映射 + 统计
            pixels = small_img.load()
            color_stats = {}
            grid_codes = [[None for _ in range(grid_w)] for _ in range(grid_h)]
            grid_colors = [[None for _ in range(grid_w)] for _ in range(grid_h)]

            for y in range(grid_h):
                for x in range(grid_w):
                    r, g, b = pixels[x, y]
                    closest_rgb, closest_name, closest_code, closest_idx = palette.find_closest_color(r, g, b)
                    grid_colors[y][x] = closest_rgb
                    grid_codes[y][x] = closest_code

                    if closest_code not in color_stats:
                        color_stats[closest_code] = {
                            "rgb": closest_rgb,
                            "name": closest_name,
                            "code": closest_code,
                            "count": 0,
                            "index": closest_idx
                        }
                    color_stats[closest_code]["count"] += 1

            # 4. 计算画布尺寸
            # 主画布区域
            main_canvas_size = canvas_size
            cell_size = main_canvas_size // max(grid_w, grid_h)

            # 实际绘图区域
            draw_width = cell_size * grid_w
            draw_height = cell_size * grid_h

            # 图例区域高度（如果需要）
            legend_height = 0
            if show_color_legend and color_stats:
                # 每行显示 8 个颜色，每个颜色块约 100px 高
                colors_per_row = 8
                legend_rows = (len(color_stats) + colors_per_row - 1) // colors_per_row
                legend_height = legend_rows * 80 + 40

            # 总画布高度
            total_height = draw_height + legend_height
            total_width = max(draw_width, 800)  # 至少 800px 宽

            # 5. 创建画布
            final_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
            draw = ImageDraw.Draw(final_img)

            # 6. 绘制网格和颜色
            start_x = (total_width - draw_width) // 2  # 居中
            start_y = 0

            for y in range(grid_h):
                for x in range(grid_w):
                    # 格子坐标
                    x1 = start_x + x * cell_size
                    y1 = start_y + y * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size

                    # 填充颜色
                    color = grid_colors[y][x]
                    draw.rectangle([x1, y1, x2, y2], fill=color)

                    # 绘制网格线
                    if show_grid:
                        draw.rectangle([x1, y1, x2, y2], outline=grid_color, width=grid_width)

                    # 绘制色号字母（如果格子够大）
                    if cell_size >= 15:  # 格子太小就不显示文字
                        code = grid_codes[y][x]
                        # 根据格子大小调整字体
                        font_size = max(8, min(cell_size // 3, 20))
                        try:
                            # 尝试加载中文字体
                            font = ImageFont.truetype("simhei.ttf", font_size)
                        except:
                            try:
                                font = ImageFont.truetype("arial.ttf", font_size)
                            except:
                                font = ImageFont.load_default()

                        # 计算文字位置（居中）
                        bbox = draw.textbbox((0, 0), code, font=font)
                        text_w = bbox[2] - bbox[0]
                        text_h = bbox[3] - bbox[1]
                        text_x = x1 + (cell_size - text_w) // 2
                        text_y = y1 + (cell_size - text_h) // 2

                        # 根据背景颜色选择文字颜色（深色背景用白色，浅色用黑色）
                        brightness = sum(color) / 3
                        text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)

                        draw.text((text_x, text_y), code, fill=text_color, font=font)

            # 7. 绘制颜色图例
            if show_color_legend and color_stats:
                legend_y = draw_height + 20
                colors_per_row = 8
                color_items = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)

                for i, (code, info) in enumerate(color_items):
                    row = i // colors_per_row
                    col = i % colors_per_row

                    item_x = 20 + col * 100
                    item_y = legend_y + row * 80

                    # 颜色块
                    draw.rectangle([item_x, item_y, item_x + 40, item_y + 40], fill=info['rgb'])
                    draw.rectangle([item_x, item_y, item_x + 40, item_y + 40], outline=(0, 0, 0), width=1)

                    # 色号
                    try:
                        font = ImageFont.truetype("simhei.ttf", 12)
                    except:
                        font = ImageFont.load_default()

                    draw.text((item_x + 45, item_y + 5), f"{code} ({info['count']})", fill=(0, 0, 0), font=font)
                    draw.text((item_x + 45, item_y + 20), f"{info['name']}", fill=(100, 100, 100), font=font)

            # 8. 保存
            filename = f"perler_{grid_w}x{grid_h}_{palette_name}.png"
            save_path = os.path.join(self.output_dir, filename)
            final_img.save(save_path)

            return save_path, final_img, color_stats

        except Exception as e:
            print(f"[错误] 处理失败：{e}")
            import traceback
            traceback.print_exc()
            return None, None, {}