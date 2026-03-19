# ui/win_ui/main_window.py - 完整特性融合版 (包含局部裁剪、描边、批量处理、修复传参报错)
import os
import sys
import io
from pathlib import Path
from typing import Optional, List
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QImage, QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QSplitter, QPushButton, QComboBox, QLineEdit,
    QSpinBox, QCheckBox, QLabel, QProgressBar, QScrollArea,
    QFrame, QListWidget, QListWidgetItem, QMessageBox,
    QColorDialog, QGridLayout, QProgressDialog
)
from PIL import Image
from core.processor import ImageProcessor
from core.history_manager import HistoryManager
from core.colors import PALETTE_OPTIONS, get_palette

# ==================== 主题样式表 (保持极简风) ====================
LIGHT_THEME = """
QMainWindow { background-color: #FFFFFF; color: #000000; }
QFrame { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 8px; }
QLabel { color: #000000; }
QPushButton { background-color: #0078D4; color: white; padding: 8px 16px; border-radius: 4px; border: none; }
QPushButton:hover { background-color: #0063B1; }
QPushButton:disabled { background-color: #CCCCCC; }
QComboBox, QSpinBox, QLineEdit { background-color: #FFFFFF; border: 1px solid #CCCCCC; border-radius: 4px; padding: 6px; color: #000000; }
QProgressBar { border: 1px solid #CCCCCC; border-radius: 4px; background-color: #F0F0F0; text-align: center; }
QProgressBar::chunk { background-color: #0078D4; }
QListWidget { background-color: #FFFFFF; border: 1px solid #CCCCCC; border-radius: 4px; }
QListWidget::item:selected { background-color: #0078D4; color: white; }
"""

DARK_THEME = """
QMainWindow { background-color: #202020; color: #FFFFFF; }
QFrame { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 8px; }
QLabel { color: #FFFFFF; }
QPushButton { background-color: #0078D4; color: white; padding: 8px 16px; border-radius: 4px; border: none; }
QPushButton:hover { background-color: #1A8BE0; }
QPushButton:disabled { background-color: #555555; }
QComboBox, QSpinBox, QLineEdit { background-color: #3D3D3D; border: 1px solid #555555; border-radius: 4px; padding: 6px; color: #FFFFFF; }
QProgressBar { border: 1px solid #555555; border-radius: 4px; background-color: #3D3D3D; text-align: center; }
QProgressBar::chunk { background-color: #0078D4; }
QListWidget { background-color: #2D2D2D; border: 1px solid #404040; border-radius: 4px; }
QListWidget::item:selected { background-color: #0078D4; color: white; }
"""


# ==================== 后台处理线程 ====================
class ProcessingWorker(QObject):
    """单图预览与处理工作线程"""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, processor: ImageProcessor, params: dict):
        super().__init__()
        self.processor = processor
        self.params = params

    def run(self):
        try:
            result = self.processor.process_image(**self.params)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BatchWorker(QObject):
    """批量处理工作线程，支持生成器进度反馈"""
    progress = Signal(int, int, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, processor: ImageProcessor, image_paths: List[str], params: dict):
        super().__init__()
        self.processor = processor
        self.image_paths = image_paths
        self.params = params

    def run(self):
        try:
            results = []
            generator = self.processor.process_batch(self.image_paths, **self.params)
            for step in generator:
                # 跨线程投递进度信号
                self.progress.emit(step['current'], step['total'], step['latest_result']['path'])
                results.append(step['latest_result'])
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


# ==================== 色卡预览窗口 (折叠保持原样) ====================
class ColorChartDialog(QMainWindow):
    def __init__(self, parent=None, palette_name="mard_221", is_dark_theme=False):
        super().__init__(parent)
        self.setWindowTitle("🎨 拼豆色卡预览")
        self.resize(1400, 900)
        self.setWindowFlags(Qt.Window)
        self.palette_name = palette_name
        self.palette = get_palette(palette_name)
        self.filtered_colors = []
        self.is_dark_theme = is_dark_theme
        self._init_ui()
        self._load_colors()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        toolbar = QHBoxLayout()
        title = QLabel(f"🎨 {self._get_palette_display_name()}")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078D4")
        toolbar.addWidget(title)
        self.lbl_stats = QLabel("共 0 种颜色")
        self.lbl_stats.setStyleSheet("color: #666")
        toolbar.addWidget(self.lbl_stats)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("色卡："))
        self.combo_palette = QComboBox()
        self.combo_palette.addItems([name for name, _ in PALETTE_OPTIONS])
        self.combo_palette.setCurrentText(self._get_palette_display_name())
        self.combo_palette.currentTextChanged.connect(self._on_palette_change)
        toolbar.addWidget(self.combo_palette)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索颜色名称或色号...")
        self.search_input.setFixedWidth(250)
        self.search_input.textChanged.connect(self._filter_colors)
        toolbar.addWidget(self.search_input)
        layout.addLayout(toolbar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.colors_container = QWidget()
        self.colors_layout = QGridLayout(self.colors_container)
        self.colors_layout.setSpacing(10)
        self.colors_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.colors_container)
        layout.addWidget(self.scroll, 1)
        btn_frame = QHBoxLayout()
        btn_export = QPushButton("💾 导出 CSV")
        btn_export.clicked.connect(self._export_csv)
        btn_frame.addWidget(btn_export)
        btn_frame.addStretch()
        layout.addLayout(btn_frame)

    def _get_palette_display_name(self):
        for display, internal in PALETTE_OPTIONS:
            if internal == self.palette_name: return display
        return self.palette_name

    def _load_colors(self, filter_text=""):
        while self.colors_layout.count():
            item = self.colors_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        colors_data = []
        for i, (rgb, name, code) in enumerate(zip(self.palette.colors, self.palette.names, self.palette.codes)):
            hex_val = '#{:02X}{:02X}{:02X}'.format(*rgb)
            colors_data.append({'code': code.strip(), 'name': name.strip() if name.strip() else '', 'rgb': rgb,
                                'hex': hex_val.lower()})
        if filter_text:
            ft = filter_text.lower()
            colors_data = [c for c in colors_data if ft in c['code'].lower() or ft in c['name'].lower()]
        self.filtered_colors = colors_data
        self.lbl_stats.setText(f"显示 {len(colors_data)}/{len(self.palette.colors)} 种颜色")
        cols, row, col = 10, 0, 0
        for color in colors_data:
            card = self._create_color_card(color)
            self.colors_layout.addWidget(card, row, col)
            col += 1
            if col >= cols: col, row = 0, row + 1

    def _create_color_card(self, color_info):
        card = QFrame()
        card.setFixedSize(130, 150)
        card.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #ddd; border-radius: 8px; } QFrame:hover { border: 2px solid #0078D4; background-color: #E8F4FD; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        color_label = QLabel()
        color_label.setFixedSize(100, 50)
        color_label.setStyleSheet(f"background-color: {color_info['hex']}; border-radius: 5px; border: 1px solid #ccc;")
        layout.addWidget(color_label)
        code_label = QLabel(color_info['code'])
        code_label.setStyleSheet("font-weight: bold; font-size: 13px")
        code_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(code_label)
        name_label = QLabel(color_info['name'] or '—')
        name_label.setStyleSheet("color: #666; font-size: 11px")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        return card

    def _filter_colors(self, text):
        self._load_colors(text)

    def _on_palette_change(self, text):
        for display, internal in PALETTE_OPTIONS:
            if display == text:
                self.palette_name = internal
                self.palette = get_palette(internal)
                self._load_colors()
                break

    def _export_csv(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "", "CSV 文件 (*.csv)")
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8-sig') as f:
                    f.write("色号，颜色名称，R,G,B,HEX\n")
                    for c in self.filtered_colors:
                        r, g, b = c['rgb']
                        f.write(f"{c['code']},{c['name']},{r},{g},{b},{c['hex']}\n")
                QMessageBox.information(self, "成功", f"已保存至:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败：{e}")


# ==================== 主界面 ====================
class DesktopUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎨 拼豆图纸生成器")
        self.resize(1400, 900)

        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()

        self.is_dark_theme = False
        self.processor = ImageProcessor()
        self.history_mgr = HistoryManager()

        # 线程句柄管理
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ProcessingWorker] = None
        self.batch_thread: Optional[QThread] = None
        self.batch_worker: Optional[BatchWorker] = None

        self.selected_files: List[str] = []  # 改为支持多文件序列
        self.current_image: Optional[QImage] = None
        self.color_stats = {}
        self.total_beads = 0
        self.is_processing = False
        self.color_chart_window: Optional[ColorChartDialog] = None

        # 输入防抖机制
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._generate_preview)

        self._init_ui()
        self._init_status_bar()
        self._apply_theme()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        toolbar = QHBoxLayout()
        title = QLabel("🎨 拼豆图纸生成器 Pro")
        title.setStyleSheet("font-size: 18px; font-weight: bold")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.btn_theme = QPushButton("🌙 深色模式")
        self.btn_theme.setFixedWidth(120)
        self.btn_theme.clicked.connect(self._toggle_theme)
        toolbar.addWidget(self.btn_theme)
        main_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        scroll_panel = QScrollArea()
        scroll_panel.setWidgetResizable(True)
        scroll_panel.setWidget(self._create_setting_panel())

        splitter.addWidget(scroll_panel)
        splitter.addWidget(self._create_preview_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)  # 给予预览区更大权重
        main_layout.addWidget(splitter)

    def _create_setting_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        self._add_section_title(layout, "📁 图片源 (支持多选批量)")
        self.btn_select = QPushButton("选择图片...")
        self.btn_select.clicked.connect(self._select_image)
        layout.addWidget(self.btn_select)

        self.lbl_file = QLabel("未选择图片")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("color: gray")
        layout.addWidget(self.lbl_file)

        # ✂️ 新增：局部裁剪面板
        self._add_section_title(layout, "✂️ 局部裁剪 (像素)")
        crop_layout1 = QHBoxLayout()
        self.spin_crop_x = QSpinBox();
        self.spin_crop_x.setRange(0, 9999)
        self.spin_crop_y = QSpinBox();
        self.spin_crop_y.setRange(0, 9999)
        crop_layout1.addWidget(QLabel("X:"))
        crop_layout1.addWidget(self.spin_crop_x)
        crop_layout1.addWidget(QLabel("Y:"))
        crop_layout1.addWidget(self.spin_crop_y)
        layout.addLayout(crop_layout1)

        crop_layout2 = QHBoxLayout()
        self.spin_crop_w = QSpinBox();
        self.spin_crop_w.setRange(0, 9999)
        self.spin_crop_h = QSpinBox();
        self.spin_crop_h.setRange(0, 9999)
        self.spin_crop_w.setToolTip("输入 0 表示不裁剪该维度")
        self.spin_crop_h.setToolTip("输入 0 表示不裁剪该维度")
        crop_layout2.addWidget(QLabel("宽:"))
        crop_layout2.addWidget(self.spin_crop_w)
        crop_layout2.addWidget(QLabel("高:"))
        crop_layout2.addWidget(self.spin_crop_h)
        layout.addLayout(crop_layout2)

        self.spin_crop_x.valueChanged.connect(self._trigger_preview)
        self.spin_crop_y.valueChanged.connect(self._trigger_preview)
        self.spin_crop_w.valueChanged.connect(self._trigger_preview)
        self.spin_crop_h.valueChanged.connect(self._trigger_preview)

        self._add_section_title(layout, "📐 网格设置")
        layout.addWidget(QLabel("画布比例："))
        self.combo_ratio = QComboBox()
        self.combo_ratio.addItems(["原始比例", "1:1 (正方形)", "4:3", "3:4", "16:9", "9:16"])
        self.combo_ratio.currentTextChanged.connect(self._on_ratio_change)
        layout.addWidget(self.combo_ratio)

        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("宽 (颗): "))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(10, 500)
        self.spin_w.setValue(50)
        self.spin_w.valueChanged.connect(self._trigger_preview)
        grid_layout.addWidget(self.spin_w)

        grid_layout.addWidget(QLabel("高 (颗): "))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(10, 500)
        self.spin_h.setValue(50)
        self.spin_h.valueChanged.connect(self._trigger_preview)
        grid_layout.addWidget(self.spin_h)
        layout.addLayout(grid_layout)

        self._add_section_title(layout, "🎨 色卡选择")
        self.combo_palette = QComboBox()
        self.combo_palette.addItems([name for name, _ in PALETTE_OPTIONS])
        self.combo_palette.setCurrentText("MARD 221 色")
        self.combo_palette.currentTextChanged.connect(self._trigger_preview)
        layout.addWidget(self.combo_palette)

        self.btn_color_chart = QPushButton("🎨 查看色卡手册")
        self.btn_color_chart.clicked.connect(self._open_color_chart)
        layout.addWidget(self.btn_color_chart)

        self._add_section_title(layout, "🖼️ 高级视觉设置")
        self.combo_canvas = QComboBox()
        self.combo_canvas.addItems(["1000", "1500", "2000", "3000", "4000"])
        self.combo_canvas.setCurrentText("1500")
        self.combo_canvas.currentTextChanged.connect(self._trigger_preview)
        layout.addWidget(self.combo_canvas)

        # 🖌️ 新增：边缘黑化特性
        self.chk_outline = QCheckBox("识别主体边缘黑化 (仅限透明背景图)")
        self.chk_outline.setChecked(False)
        self.chk_outline.setStyleSheet("color: #0078D4; font-weight: bold;")
        self.chk_outline.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_outline)

        self.chk_labels = QCheckBox("生成行列标号")
        self.chk_labels.setChecked(True)
        self.chk_labels.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_labels)

        self.chk_grid = QCheckBox("显示网格线")
        self.chk_grid.setChecked(True)
        self.chk_grid.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_grid)

        grid_color_layout = QHBoxLayout()
        grid_color_layout.addWidget(QLabel("网格颜色："))
        self.btn_grid_color = QPushButton("#C8C8C8")
        self.btn_grid_color.setFixedWidth(100)
        self.btn_grid_color.clicked.connect(self._select_grid_color)
        grid_color_layout.addWidget(self.btn_grid_color)
        layout.addLayout(grid_color_layout)

        layout.addStretch()

        # 生成与批量处理控制区
        btn_action_layout = QHBoxLayout()
        self.btn_generate = QPushButton("🔄 生成预览")
        self.btn_generate.clicked.connect(self._generate_preview)
        btn_action_layout.addWidget(self.btn_generate)

        self.btn_batch = QPushButton("🚀 批量处理")
        self.btn_batch.setStyleSheet("background-color: #28a745;")
        self.btn_batch.clicked.connect(self._run_batch)
        btn_action_layout.addWidget(self.btn_batch)
        layout.addLayout(btn_action_layout)

        export_layout = QHBoxLayout()
        self.btn_save_png = QPushButton("💾 保存 PNG")
        self.btn_save_png.clicked.connect(self._save_image)
        export_layout.addWidget(self.btn_save_png)

        self.btn_save_pdf = QPushButton("📄 导出 PDF")
        self.btn_save_pdf.clicked.connect(self._export_pdf)
        export_layout.addWidget(self.btn_save_pdf)
        layout.addLayout(export_layout)

        self._add_section_title(layout, "📊 颜色统计")
        self.lbl_stats = QLabel("生成后显示")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setStyleSheet("color: gray")
        layout.addWidget(self.lbl_stats)

        return panel

    def _create_preview_panel(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("🖼️ 实时预览 (支持滚轮缩放)")
        title.setStyleSheet("font-size: 16px; font-weight: bold")
        layout.addWidget(title)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.image_label = QLabel("请选择图片并生成预览")
        self.image_label.setAlignment(Qt.AlignCenter)

        if self.screen_width >= 2560:
            min_size, default_zoom = 600, 900
        elif self.screen_width >= 1920:
            min_size, default_zoom = 500, 600
        else:
            min_size, default_zoom = 400, 400

        self.image_label.setMinimumSize(min_size, min_size)
        self.image_label.setStyleSheet(
            "background-color: #000000; border: 1px solid #333; border-radius: 8px; color: #FFFFFF;")

        # 将 image_label 包装入 ScrollArea 支持超大图片漫游
        self.img_scroll = QScrollArea()
        self.img_scroll.setWidgetResizable(True)
        self.img_scroll.setWidget(self.image_label)
        layout.addWidget(self.img_scroll, 1)

        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("预览缩放："))
        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(100, 5000)
        self.spin_zoom.setValue(default_zoom)
        self.spin_zoom.setSuffix("px")
        self.spin_zoom.valueChanged.connect(self._update_zoom)
        zoom_layout.addWidget(self.spin_zoom)

        btn_auto_fit = QPushButton("📐 窗口自适应")
        btn_auto_fit.setFixedWidth(100)
        btn_auto_fit.clicked.connect(self._auto_fit_zoom)
        zoom_layout.addWidget(btn_auto_fit)
        zoom_layout.addStretch()
        layout.addLayout(zoom_layout)

        self.lbl_status = QLabel("✅ 就绪")
        self.lbl_status.setStyleSheet("color: green; font-weight: bold")
        layout.addWidget(self.lbl_status)

        return panel

    def _add_section_title(self, layout, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; margin-top: 10px")
        layout.addWidget(label)

    def _init_status_bar(self):
        self.statusBar().showMessage("就绪")

    def _toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self._apply_theme()

    def _apply_theme(self):
        if self.is_dark_theme:
            self.setStyleSheet(DARK_THEME)
            self.btn_theme.setText("☀️ 浅色模式")
        else:
            self.setStyleSheet(LIGHT_THEME)
            self.btn_theme.setText("🌙 深色模式")
        if self.color_chart_window:
            self.color_chart_window.is_dark_theme = self.is_dark_theme
            self.color_chart_window._load_colors()

    def _select_image(self):
        # 支持多文件序列选择
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片序列", "", "Image Files (*.png *.jpg *.jpeg *.bmp)")
        if files:
            self.selected_files = files
            if len(files) == 1:
                self.lbl_file.setText(Path(files[0]).name)
            else:
                self.lbl_file.setText(f"已选中 {len(files)} 张图片，可点击批量处理。")
            self.lbl_file.setStyleSheet("color: black")

            # 预读取第一张图片计算尺寸
            try:
                with Image.open(files[0]) as img:
                    w, h = img.size
                    self.spin_w.setValue(min(max(30, w // 20), 100))
                    self._calculate_dimension('w')
            except:
                pass
            self._trigger_preview()

    def _calculate_dimension(self, source: str):
        w, h = self.spin_w.value(), self.spin_h.value()
        ratio = self.combo_ratio.currentText()
        if ratio == "1:1 (正方形)":
            self.spin_h.setValue(w) if source == 'w' else self.spin_w.setValue(h)
        elif ratio == "4:3":
            self.spin_h.setValue(max(1, round(w * 3 / 4))) if source == 'w' else self.spin_w.setValue(
                max(1, round(h * 4 / 3)))
        elif ratio == "16:9":
            self.spin_h.setValue(max(1, round(w * 9 / 16))) if source == 'w' else self.spin_w.setValue(
                max(1, round(h * 16 / 9)))

    def _on_ratio_change(self):
        self._calculate_dimension('w')
        self._trigger_preview()

    def _trigger_preview(self):
        self.preview_timer.start(500)

    def _build_processor_params(self, single_file: str) -> dict:
        """封装并验证传递给底层引擎的字典参数"""
        cx, cy = self.spin_crop_x.value(), self.spin_crop_y.value()
        cw, ch = self.spin_crop_w.value(), self.spin_crop_h.value()

        crop_box = None
        if cw > 0 and ch > 0:
            crop_box = (cx, cy, cx + cw, cy + ch)

        return {
            'image_path': single_file,
            'grid_w': self.spin_w.value(),
            'grid_h': self.spin_h.value(),
            'canvas_size': int(self.combo_canvas.currentText()),
            'show_grid': self.chk_grid.isChecked(),
            'grid_color': self._hex_to_rgb(self.btn_grid_color.text()),
            'palette_name': self._get_palette_internal(),
            # 🔧 关键修复：修正错位的 kwargs Key，使其与 processor.py 对齐
            'show_color_legend': True,
            'show_row_col_labels': self.chk_labels.isChecked(),
            'crop_box': crop_box,
            'outline_black': self.chk_outline.isChecked()
        }

    def _generate_preview(self):
        if self.is_processing or not self.selected_files: return
        self.is_processing = True
        self.btn_generate.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)  # 忙碌动画
        self.lbl_status.setText("⏳ 渲染中...")
        self.lbl_status.setStyleSheet("color: blue")

        # 预览默认取列表里的第一张图
        params = self._build_processor_params(self.selected_files[0])

        self.worker_thread = QThread(self)
        self.worker = ProcessingWorker(self.processor, params)
        self.worker.moveToThread(self.worker_thread)
        self.worker.finished.connect(self._on_processing_finished)
        self.worker.error.connect(self._on_processing_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _run_batch(self):
        """拉起批量处理状态机，阻断主窗体交互"""
        if not self.selected_files or len(self.selected_files) < 2:
            QMessageBox.warning(self, "提示", "请选择至少 2 张图片组成序列进行批量处理！")
            return

        params = self._build_processor_params("")  # 占位，内部会重写 image_path
        params.pop('image_path', None)
        # 建立模态进度对话框
        self.progress_dlg = QProgressDialog("启动批量引擎...", "取消", 0, len(self.selected_files), self)
        self.progress_dlg.setWindowTitle("批量处理中")
        self.progress_dlg.setWindowModality(Qt.WindowModal)
        self.progress_dlg.setMinimumDuration(0)
        self.progress_dlg.setValue(0)

        self.batch_thread = QThread(self)
        self.batch_worker = BatchWorker(self.processor, self.selected_files, params)
        self.batch_worker.moveToThread(self.batch_thread)

        # 信号绑定
        self.batch_worker.progress.connect(self._on_batch_progress)
        self.batch_worker.finished.connect(self._on_batch_finished)
        self.batch_worker.error.connect(self._on_processing_error)
        self.progress_dlg.canceled.connect(self.batch_thread.quit)  # 允许打断

        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_thread.start()

    def _on_batch_progress(self, current: int, total: int, last_file: str):
        self.progress_dlg.setLabelText(f"正在处理 [{current}/{total}]:\n{os.path.basename(last_file)}")
        self.progress_dlg.setValue(current)

    def _on_batch_finished(self, results):
        self.batch_thread.quit()
        success_count = sum(1 for r in results if r.get('status') == 'success')
        QMessageBox.information(self, "批量完成",
                                f"队列执行完毕！\n成功: {success_count} \n失败: {len(results) - success_count}\n文件保存在 output 目录。")
        self._generate_preview()  # 刷新当前预览

    def _on_processing_finished(self, result):
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.is_processing = False

        save_path, img_obj, color_stats, total_beads, grid_w, grid_h = result
        if img_obj:
            img_obj = img_obj.convert('RGB')
            qimage = QImage(img_obj.tobytes(), img_obj.width, img_obj.height, img_obj.width * 3, QImage.Format_RGB888)
            self.current_image = qimage
            self.color_stats = color_stats
            self.total_beads = total_beads

            self._auto_fit_zoom()
            self._update_stats_display(total_beads, grid_w, grid_h)

            self.lbl_status.setText(f"✅ 完成！网格：{grid_w}×{grid_h}")
            self.lbl_status.setStyleSheet("color: green")
            self.statusBar().showMessage(f"渲染成功，共提取 {total_beads} 颗特征豆", 3000)
        else:
            self.lbl_status.setText("❌ 处理失败")
            self.lbl_status.setStyleSheet("color: red")

    def _on_processing_error(self, error_msg):
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.is_processing = False
        self.lbl_status.setText("❌ 引擎崩溃")
        self.lbl_status.setStyleSheet("color: red")
        QMessageBox.critical(self, "底层错误", error_msg)

    def _update_preview_display(self):
        if self.current_image:
            zoom_size = self.spin_zoom.value()
            scaled = self.current_image.scaled(zoom_size, zoom_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(QPixmap.fromImage(scaled))
            self.image_label.setText("")
        else:
            self.image_label.setText("未生成矩阵")

    def _update_zoom(self):
        self._update_preview_display()

    def _auto_fit_zoom(self):
        if not self.current_image: return
        # 留出滚动条呼吸空间
        preview_width = self.img_scroll.width() - 40
        preview_height = self.img_scroll.height() - 40
        max_zoom = 2000 if self.screen_width >= 2560 else 1500

        scale = min(preview_width / self.current_image.width(), preview_height / self.current_image.height(), 1.0)
        new_size = int(max(self.current_image.width(), self.current_image.height()) * scale)
        self.spin_zoom.setValue(max(300, min(new_size, max_zoom)))

    def _update_stats_display(self, total_beads, grid_w, grid_h):
        if not self.color_stats: return
        text = "📊 耗材流统计:\n"
        sorted_stats = sorted(self.color_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        for code, info in sorted_stats: text += f"● {info['code']} {info['name']}: {info['count']}颗\n"
        if len(self.color_stats) > 10: text += f"... 共 {len(self.color_stats)} 种\n"
        text += f"\n总计：{total_beads} 颗 | 规格：{grid_w}×{grid_h}"
        self.lbl_stats.setText(text)
        self.lbl_stats.setStyleSheet("color: black")

    def _save_image(self):
        if not self.current_image: return QMessageBox.warning(self, "提示", "缓冲矩阵为空！")
        save_path, _ = QFileDialog.getSaveFileName(self, "保存光栅图", "perler_pattern.png", "PNG Files (*.png)")
        if save_path:
            self.current_image.save(save_path)
            QMessageBox.information(self, "成功", f"落盘完成：{save_path}")

    def _export_pdf(self):
        if not self.current_image or not hasattr(self, 'color_stats'):
            return QMessageBox.warning(self, "提示", "请先在内存中生成预览图纸！")

        buffer = QBuffer()
        buffer.open(QIODevice.ReadWrite)
        try:
            self.current_image.save(buffer, "PNG")
            pil_image = Image.open(io.BytesIO(buffer.data().data())).convert('RGB')
        finally:
            buffer.close()

        save_path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", "perler_vector.pdf", "PDF Files (*.pdf)")
        if save_path:
            try:
                pdf_path = self.processor.export_to_pdf(
                    pattern_image=pil_image, color_stats=self.color_stats,
                    grid_w=self.spin_w.value(), grid_h=self.spin_h.value(),
                    total_beads=self.total_beads, palette_name=self._get_palette_internal(),
                    filename=save_path
                )
                if pdf_path:
                    QMessageBox.information(self, "成功", f"矢量流已写入:\n{pdf_path}")
                else:
                    QMessageBox.critical(self, "错误", "ReportLab 引擎执行失败")
            except Exception as e:
                QMessageBox.critical(self, "异常抛出", str(e))

    def _select_grid_color(self):
        dialog = QColorDialog(QColor(self.btn_grid_color.text()), self)
        if dialog.exec():
            self.btn_grid_color.setText(dialog.selectedColor().name())
            self._trigger_preview()

    def _open_color_chart(self):
        if self.color_chart_window is None:
            self.color_chart_window = ColorChartDialog(self, self._get_palette_internal(),
                                                       is_dark_theme=self.is_dark_theme)
        self.color_chart_window.show()
        self.color_chart_window.raise_()

    def _get_palette_internal(self) -> str:
        for display, internal in PALETTE_OPTIONS:
            if display == self.combo_palette.currentText(): return internal
        return "mard_221"

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        return tuple(int(hex_color.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))