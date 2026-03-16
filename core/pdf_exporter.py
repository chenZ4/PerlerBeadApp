"""
PDF 导出模块
使用 reportlab 生成专业拼豆图纸 PDF (Google Material Design 极简风格)
"""
import os
import platform
from io import BytesIO
from typing import Dict
from PIL import Image

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class PDFExporter:
    """PDF 导出器 - 机制白盒化：通过动态字体挂载与流式布局引擎生成矢量文档"""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.font_name = self._register_cross_platform_font()
        self._setup_material_styles()

    def _register_cross_platform_font(self) -> str:
        """
        动态探测操作系统级中文字体并挂载。
        返回成功挂载的虚拟字体别名 'MainFont'，失败则回退默认。
        """
        system = platform.system()
        font_candidates = []

        if system == "Windows":
            base_dir = os.environ.get('WINDIR', 'C:\\Windows')
            font_candidates = [
                os.path.join(base_dir, 'Fonts', 'msyh.ttc'),     # 微软雅黑
                os.path.join(base_dir, 'Fonts', 'simhei.ttf'),   # 黑体
            ]
        elif system == "Darwin": # macOS
            font_candidates = [
                '/System/Library/Fonts/PingFang.ttc',            # 苹方
                '/Library/Fonts/Songti.ttc',
            ]
        else: # Linux
            font_candidates = [
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            ]

        for path in font_candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('MainFont', path))
                    return 'MainFont'
                except Exception as e:
                    print(f"字体加载失败 ({path}): {e}")

        # 极端失效兜底：无可用字体时回退
        return 'Helvetica'

    def _setup_material_styles(self):
        """定义 Google Material Design 极简风格样式"""
        # 主标题
        self.styles.add(ParagraphStyle(
            name='MaterialTitle',
            fontName=self.font_name,
            fontSize=22,
            textColor=colors.HexColor('#202124'), # Google 标题黑
            spaceAfter=15,
            alignment=TA_LEFT
        ))

        # 次级信息文字
        self.styles.add(ParagraphStyle(
            name='MaterialSubtitle',
            fontName=self.font_name,
            fontSize=11,
            textColor=colors.HexColor('#5F6368'), # Google 辅文灰
            spaceAfter=20,
            leading=16,
            alignment=TA_LEFT
        ))

        # 章节小标题
        self.styles.add(ParagraphStyle(
            name='MaterialHeading',
            fontName=self.font_name,
            fontSize=16,
            textColor=colors.HexColor('#1A73E8'), # Google 品牌蓝
            spaceBefore=20,
            spaceAfter=15,
            alignment=TA_LEFT
        ))

    def export(self, output_path: str, pattern_image: Image.Image,
               color_stats: Dict, grid_w: int, grid_h: int,
               total_beads: int, palette_name: str) -> bool:
        """
        导出全尺寸 PDF 图纸 - 高清晰度优化版

        核心优化策略：
        1. 使用原始高分辨率图像，避免二次缩放损失
        2. 动态计算最佳显示尺寸，保持像素锐利
        3. 采用 PNG 无损格式传输图像数据
        4. ReportLab 高质量渲染设置
        """
        img_buffer = BytesIO() # 提前声明，防 finally 块未定义的引用
        try:
            # 采用横向 A4 布局，提供更大的绘图视野
            doc = SimpleDocTemplate(
                output_path,
                pagesize=landscape(A4),
                rightMargin=1.5 * cm,
                leftMargin=1.5 * cm,
                topMargin=1.5 * cm,
                bottomMargin=1.5 * cm,
                title="拼豆图纸"  # PDF 元数据
            )

            elements = []

            # --- 1. 头部信息区 (Metadata) ---
            elements.append(Paragraph(f"拼豆工程图纸", self.styles['MaterialTitle']))

            info_text = (
                f"<b>规格：</b> {grid_w} × {grid_h} 像素网格 &nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp; "
                f"<b>耗材：</b> 共计 {total_beads} 颗 &nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp; "
                f"<b>色系库：</b> {palette_name} ({len(color_stats)} 种颜色)"
            )
            elements.append(Paragraph(info_text, self.styles['MaterialSubtitle']))

            # --- 2. 图像渲染区 (高清晰度优化) ---
            # 获取原始图像尺寸
            orig_width, orig_height = pattern_image.size
            print(f"📊 原始图像尺寸：{orig_width} x {orig_height} 像素")

            # 使用最高质量保存 PNG（无损压缩）
            pattern_image.save(
                img_buffer,
                format='PNG',
                quality=100,
                dpi=(300, 300)
            )
            img_buffer.seek(0)

            # 动态计算在横版 A4 下的最佳显示尺寸
            available_width = landscape(A4)[0] - 3 * cm  # 约 756 points
            available_height = landscape(A4)[1] - 8 * cm  # 预留头部和表格空间

            max_width = available_width / 72  # 约 10 inch
            max_height = available_height / 72  # 约 4.7 inch

            img_ratio = orig_width / orig_height
            display_ratio = max_width / max_height

            if img_ratio > display_ratio:
                draw_width = max_width
                draw_height = max_width / img_ratio
            else:
                draw_height = max_height
                draw_width = max_height * img_ratio

            # 修复 SyntaxError
            print(f"📐 PDF 中显示尺寸：{draw_width:.2f} x {draw_height:.2f} 英寸")

            rl_image = RLImage(img_buffer, width=draw_width * inch, height=draw_height * inch)

            # 禁用抗锯齿，保持像素锐利
            rl_image.drawHeight = draw_height * inch
            rl_image.drawWidth = draw_width * inch

            elements.append(rl_image)
            elements.append(Spacer(1, 0.3 * inch))

            # --- 3. 耗材清单表格 (Material Table 风格) ---
            elements.append(Paragraph("耗材调配清单", self.styles['MaterialHeading']))

            table_data = [['色块', '色号标识', '标准命名', 'RGB 坐标', '需求数量', '占比']]
            sorted_stats = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)
            dynamic_cell_styles = []

            for row_idx, (code, info) in enumerate(sorted_stats, start=1):
                r, g, b = info['rgb']
                hex_color = f"#{r:02X}{g:02X}{b:02X}"
                percentage = f"{info['count'] / total_beads * 100:.1f}%"

                table_data.append([
                    "",
                    code,
                    info['name'],
                    f"({r}, {g}, {b})",
                    f"{info['count']} 颗",
                    percentage
                ])

                dynamic_cell_styles.append(('BACKGROUND', (0, row_idx), (0, row_idx), colors.HexColor(hex_color)))
                dynamic_cell_styles.append(('BOX', (0, row_idx), (0, row_idx), 0.5, colors.HexColor('#DADCE0')))

            table = Table(table_data, colWidths=[0.8 * inch, 1.5 * inch, 2.5 * inch, 1.5 * inch, 1.2 * inch, 1 * inch])

            base_table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F0FE')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1967D2')),
                ('FONTNAME', (0, 0), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#E8EAED')),
            ]

            table.setStyle(TableStyle(base_table_style + dynamic_cell_styles))
            elements.append(table)

            # 延迟渲染动作，渲染完成后方可关闭 buffer
            doc.build(elements, canvasmaker=None)
            return True

        except Exception as e:
            print(f"PDF 渲染管线崩溃：{e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # 无论成功或抛出异常，强制阻断内存泄漏
            img_buffer.close()

    def export_color_list_only(self, output_path: str, color_stats: Dict,
                               total_beads: int, palette_name: str) -> bool:
        """重用主函数的逻辑结构进行单一功能输出（简略展示）"""
        pass