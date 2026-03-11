"""
PDF 导出模块
使用 reportlab 生成专业拼豆图纸 PDF
"""
from pathlib import Path
from typing import Dict
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from PIL import Image
import os

class PDFExporter:
    """PDF 导出器"""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._register_chinese_fonts()  # ✅ 注册中文字体
        self._setup_custom_styles()

    def _register_chinese_fonts(self):
        """✅ 注册中文字体以支持中文显示"""
        font_paths = [
            ('SimHei', 'simhei.ttf'),
            ('SimSun', 'simsun.ttc'),
            ('MicrosoftYaHei', 'msyh.ttc'),
            ('MicrosoftYaHei-Bold', 'msyhbd.ttc'),
        ]

        for font_name, font_file in font_paths:
            try:
                # 尝试在系统字体目录中查找
                if os.name == 'nt':  # Windows
                    font_path = os.path.join(os.environ['WINDIR'], 'Fonts', font_file)
                else:  # Linux/Mac
                    font_path = font_file

                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    print(f"✅ 已注册字体：{font_name}")
            except Exception as e:
                print(f"⚠️ 字体注册失败 {font_name}: {e}")

    def _setup_custom_styles(self):
        """设置自定义样式"""
        # ✅ 使用支持中文的字体
        chinese_font = 'SimHei' if 'SimHei' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'

        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            fontName=chinese_font,
            textColor=colors.HexColor('#0078D4'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName=chinese_font,
            textColor=colors.HexColor('#333333'),
            spaceAfter=6
        ))

    def export(self, output_path: str, pattern_image: Image.Image,
               color_stats: Dict, grid_w: int, grid_h: int,
               total_beads: int, palette_name: str) -> bool:
        """导出 PDF 图纸"""
        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=landscape(A4),
                rightMargin=2 * cm,
                leftMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm
            )

            elements = []

            # 1. 标题
            title = Paragraph(f"🎨 拼豆图纸 - {palette_name}", self.styles['CustomTitle'])
            elements.append(title)
            elements.append(Spacer(1, 0.3 * inch))

            # 2. 基本信息
            info_text = f"""
            <b>网格尺寸:</b> {grid_w} × {grid_h} 颗 <br/>
            <b>总豆子数:</b> {total_beads} 颗 <br/>
            <b>色卡:</b> {palette_name} <br/>
            <b>颜色种类:</b> {len(color_stats)} 种
            """
            info = Paragraph(info_text, self.styles['CustomNormal'])
            elements.append(info)
            elements.append(Spacer(1, 0.5 * inch))

            # 3. 图案图片
            img_buffer = BytesIO()
            pattern_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            max_width = 11 * inch
            max_height = 5 * inch
            img_ratio = pattern_image.width / pattern_image.height

            if pattern_image.width > pattern_image.height:
                draw_width = max_width
                draw_height = max_width / img_ratio
            else:
                draw_height = max_height
                draw_width = max_height * img_ratio

            rl_image = RLImage(img_buffer, width=draw_width, height=draw_height)
            elements.append(rl_image)
            elements.append(Spacer(1, 0.5 * inch))

            # 4. 颜色清单表格
            elements.append(Paragraph("📋 颜色清单", self.styles['Heading2']))
            elements.append(Spacer(1, 0.2 * inch))

            table_data = [['色号', '颜色名称', 'RGB', '数量', '占比']]

            sorted_stats = sorted(
                color_stats.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )

            for code, info in sorted_stats:
                r, g, b = info['rgb']
                rgb_text = f"{r},{g},{b}"
                percentage = f"{info['count'] / total_beads * 100:.1f}%"
                color_block = f"■ {code}"

                table_data.append([
                    color_block,
                    info['name'],
                    rgb_text,
                    str(info['count']),
                    percentage
                ])

            table = Table(table_data, colWidths=[1.2 * inch, 2 * inch, 1.5 * inch, 1 * inch, 1 * inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078D4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F5')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAFA')]),
            ]))

            elements.append(table)
            elements.append(Spacer(1, 0.5 * inch))

            # 5. 页脚
            from datetime import datetime
            footer_text = f"""
            <para alignment="center">
            <font size="8" color="#999999">
            生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} <br/>
            本图纸由拼豆图纸生成器自动生成
            </font>
            </para>
            """
            elements.append(Paragraph(footer_text, self.styles['Normal']))

            doc.build(elements)
            return True

        except Exception as e:
            print(f"PDF 导出失败：{e}")
            import traceback
            traceback.print_exc()
            return False

    def export_color_list_only(self, output_path: str, color_stats: Dict,
                               total_beads: int, palette_name: str) -> bool:
        """仅导出颜色清单"""
        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2 * cm,
                leftMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm
            )

            elements = []

            title = Paragraph(f"📋 颜色清单 - {palette_name}", self.styles['CustomTitle'])
            elements.append(title)
            elements.append(Spacer(1, 0.3 * inch))

            info_text = f"""
            <b>总豆子数:</b> {total_beads} 颗 <br/>
            <b>颜色种类:</b> {len(color_stats)} 种
            """
            info = Paragraph(info_text, self.styles['CustomNormal'])
            elements.append(info)
            elements.append(Spacer(1, 0.5 * inch))

            table_data = [['色号', '颜色名称', 'RGB', 'HEX', '数量', '占比']]

            sorted_stats = sorted(
                color_stats.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )

            for code, info in sorted_stats:
                r, g, b = info['rgb']
                hex_val = f"#{r:02X}{g:02X}{b:02X}"
                percentage = f"{info['count'] / total_beads * 100:.1f}%"

                table_data.append([
                    code,
                    info['name'],
                    f"{r},{g},{b}",
                    hex_val,
                    str(info['count']),
                    percentage
                ])

            table = Table(table_data, colWidths=[0.8 * inch, 1.5 * inch, 1.2 * inch, 1 * inch, 0.8 * inch, 0.8 * inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078D4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
            ]))

            elements.append(table)
            doc.build(elements)
            return True

        except Exception as e:
            print(f"PDF 导出失败：{e}")
            return False