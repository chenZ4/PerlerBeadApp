# ui/desktop_ui.py - 修正导入路径
import os
import sys
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QSize
from PySide6.QtGui import QPixmap, QImage, QFont, QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QSplitter, QPushButton, QComboBox, QLineEdit,
    QSpinBox, QCheckBox, QLabel, QProgressBar, QScrollArea,
    QFrame, QListWidget, QListWidgetItem, QMessageBox,
    QStatusBar, QColorDialog, QGridLayout
)

# 🔧 修正导入路径 - 从 core 导入
from core.processor import ImageProcessor
from core.history_manager import HistoryManager
from core.colors import PALETTE_OPTIONS, get_palette
# ==================== 主题样式表 ====================

LIGHT_THEME = """
/* 浅色主题 */
QMainWindow {
    background-color: #FFFFFF;
    color: #000000;
}
QFrame {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
}
QLabel {
    color: #000000;
}
QPushButton {
    background-color: #0078D4;
    color: white;
    padding: 8px 16px;
    border-radius: 4px;
    border: none;
}
QPushButton:hover {
    background-color: #0063B1;
}
QPushButton:disabled {
    background-color: #CCCCCC;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 6px;
    color: #000000;
}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {
    border: 1px solid #0078D4;
}
QCheckBox {
    color: #000000;
}
QProgressBar {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    background-color: #F0F0F0;
}
QProgressBar::chunk {
    background-color: #0078D4;
    border-radius: 4px;
}
QScrollArea {
    background-color: #FFFFFF;
    border: none;
}
QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #CCCCCC;
    border-radius: 4px;
}
QListWidget::item {
    padding: 8px;
}
QListWidget::item:selected {
    background-color: #0078D4;
    color: white;
}
QStatusBar {
    background-color: #F5F5F5;
    color: #000000;
}
"""

DARK_THEME = """
/* 深色主题 */
QMainWindow {
    background-color: #202020;
    color: #FFFFFF;
}
QFrame {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 8px;
}
QLabel {
    color: #FFFFFF;
}
QPushButton {
    background-color: #0078D4;
    color: white;
    padding: 8px 16px;
    border-radius: 4px;
    border: none;
}
QPushButton:hover {
    background-color: #1A8BE0;
}
QPushButton:disabled {
    background-color: #555555;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #3D3D3D;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px;
    color: #FFFFFF;
}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {
    border: 1px solid #0078D4;
}
QCheckBox {
    color: #FFFFFF;
}
QProgressBar {
    border: 1px solid #555555;
    border-radius: 4px;
    background-color: #3D3D3D;
}
QProgressBar::chunk {
    background-color: #0078D4;
    border-radius: 4px;
}
QScrollArea {
    background-color: #2D2D2D;
    border: none;
}
QListWidget {
    background-color: #2D2D2D;
    border: 1px solid #404040;
    border-radius: 4px;
}
QListWidget::item {
    padding: 8px;
    color: #FFFFFF;
}
QListWidget::item:selected {
    background-color: #0078D4;
    color: white;
}
QStatusBar {
    background-color: #2D2D2D;
    color: #FFFFFF;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

    def run(self):
        try:
            result = self.processor.process_image(
                image_path=self.params['image_path'],
                grid_w=self.params['grid_w'],
                grid_h=self.params['grid_h'],
                canvas_size=self.params['canvas_size'],
                show_grid=self.params['show_grid'],
                grid_color=self.params['grid_color'],
                palette_name=self.params['palette_name'],
                show_color_legend=self.params['show_legend'],
                show_row_col_labels=self.params['show_labels']
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ColorChartDialog(QMainWindow):
    """色卡预览窗口 - 横向排列"""

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

        # 顶部工具栏
        toolbar = QHBoxLayout()

        # 标题
        title = QLabel(f"🎨 {self._get_palette_display_name()}")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078D4")
        toolbar.addWidget(title)

        # 统计
        self.lbl_stats = QLabel("共 0 种颜色")
        self.lbl_stats.setStyleSheet("color: #666")
        toolbar.addWidget(self.lbl_stats)

        toolbar.addStretch()

        # 色卡选择
        toolbar.addWidget(QLabel("色卡:"))
        self.combo_palette = QComboBox()
        self.combo_palette.addItems([name for name, _ in PALETTE_OPTIONS])
        self.combo_palette.setCurrentText(self._get_palette_display_name())
        self.combo_palette.currentTextChanged.connect(self._on_palette_change)
        toolbar.addWidget(self.combo_palette)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索颜色名称或色号...")
        self.search_input.setFixedWidth(250)
        self.search_input.textChanged.connect(self._filter_colors)
        toolbar.addWidget(self.search_input)

        layout.addLayout(toolbar)

        # 颜色卡片区域 - 使用滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.colors_container = QWidget()
        # 🔧 使用 QGridLayout 实现横向排列
        self.colors_layout = QGridLayout(self.colors_container)
        self.colors_layout.setSpacing(10)
        self.colors_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll.setWidget(self.colors_container)
        layout.addWidget(self.scroll, 1)

        # 底部按钮
        btn_frame = QHBoxLayout()
        btn_export = QPushButton("💾 导出 CSV")
        btn_export.clicked.connect(self._export_csv)
        btn_frame.addWidget(btn_export)
        btn_frame.addStretch()
        layout.addLayout(btn_frame)

    def _get_palette_display_name(self):
        for display, internal in PALETTE_OPTIONS:
            if internal == self.palette_name:
                return display
        return self.palette_name

    def _load_colors(self, filter_text=""):
        # 清理现有卡片
        while self.colors_layout.count():
            item = self.colors_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        colors_data = []
        for i, (rgb, name, code) in enumerate(zip(
                self.palette.colors,
                self.palette.names,
                self.palette.codes
        )):
            hex_val = '#{:02X}{:02X}{:02X}'.format(*rgb)
            colors_data.append({
                'code': code.strip(),
                'name': name.strip() if name.strip() else '',
                'rgb': rgb,
                'hex': hex_val.lower(),
                'group': code.strip()[0]
            })

        if filter_text:
            ft = filter_text.lower()
            colors_data = [c for c in colors_data
                           if ft in c['code'].lower() or ft in c['name'].lower()]

        self.filtered_colors = colors_data
        self.lbl_stats.setText(f"显示 {len(colors_data)}/{len(self.palette.colors)} 种颜色")

        # 🔧 横向排列：每行显示 10 个颜色卡片
        cols = 10
        row = 0
        col = 0

        for color in colors_data:
            card = self._create_color_card(color)
            self.colors_layout.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _create_color_card(self, color_info):
        card = QFrame()
        card.setFixedSize(130, 150)

        # 根据主题设置样式
        if self.is_dark_theme:
            card.setStyleSheet("""
                QFrame {
                    background-color: #3D3D3D;
                    border: 1px solid #555555;
                    border-radius: 8px;
                }
                QFrame:hover {
                    border: 2px solid #0078D4;
                    background-color: #4D4D4D;
                }
            """)
        else:
            card.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                }
                QFrame:hover {
                    border: 2px solid #0078D4;
                    background-color: #E8F4FD;
                }
            """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        # 颜色预览
        color_label = QLabel()
        color_label.setFixedSize(100, 50)
        color_label.setStyleSheet(f"""
            background-color: {color_info['hex']};
            border-radius: 5px;
            border: 1px solid #ccc;
        """)
        color_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(color_label)

        # 色号
        code_label = QLabel(color_info['code'])
        code_label.setStyleSheet("font-weight: bold; font-size: 13px")
        code_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(code_label)

        # 名称
        name_label = QLabel(color_info['name'] or '—')
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #666; font-size: 11px")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        # RGB
        rgb_label = QLabel(f"RGB{color_info['rgb']}")
        rgb_label.setStyleSheet("color: #0078D4; font-size: 10px")
        rgb_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(rgb_label)

        return card

    def _filter_colors(self, text):
        self._load_colors(text)

    def _on_palette_change(self, text):
        for display, internal in PALETTE_OPTIONS:
            if display == text:
                self.palette_name = internal
                self.palette = get_palette(internal)
                self._load_colors()
                self.setWindowTitle(f"🎨 {text}")
                break

    def _export_csv(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "", "CSV 文件 (*.csv)"
        )
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


class DesktopUI(QMainWindow):
    """主界面 - 纯 PySide6 版本"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎨 拼豆图纸生成器")
        self.resize(1400, 900)

        # 主题状态
        self.is_dark_theme = False

        # 核心组件
        self.processor = ImageProcessor()
        self.history_mgr = HistoryManager()
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ProcessingWorker] = None

        # 状态
        self.selected_file: Optional[str] = None
        self.current_image: Optional[QImage] = None
        self.color_stats = {}
        self.total_beads = 0
        self.preview_timer: Optional[QTimer] = None
        self.is_processing = False

        # 色卡窗口
        self.color_chart_window: Optional[ColorChartDialog] = None

        self._init_ui()
        self._init_status_bar()
        self._apply_theme()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # === 顶部工具栏 ===
        toolbar = QHBoxLayout()

        title = QLabel("🎨 拼豆图纸生成器")
        title.setStyleSheet("font-size: 18px; font-weight: bold")
        toolbar.addWidget(title)

        toolbar.addStretch()

        # 🔧 主题切换按钮
        self.btn_theme = QPushButton("🌙 深色模式")
        self.btn_theme.setFixedWidth(120)
        self.btn_theme.clicked.connect(self._toggle_theme)
        toolbar.addWidget(self.btn_theme)

        main_layout.addLayout(toolbar)

        # 使用 Splitter 分隔左右
        splitter = QSplitter(Qt.Horizontal)

        # 左侧设置面板
        left_panel = self._create_setting_panel()
        splitter.addWidget(left_panel)

        # 右侧预览面板
        right_panel = self._create_preview_panel()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

    def _create_setting_panel(self) -> QWidget:
        """创建设置面板"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        panel.setMinimumWidth(350)
        panel.setMaximumWidth(400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 标题
        title = QLabel("⚙️ 设置面板")
        title.setStyleSheet("font-size: 16px; font-weight: bold")
        layout.addWidget(title)

        # 1. 图片选择
        self._add_section_title(layout, "📁 图片源")
        self.btn_select = QPushButton("选择图片")
        self.btn_select.clicked.connect(self._select_image)
        layout.addWidget(self.btn_select)

        self.lbl_file = QLabel("未选择图片")
        self.lbl_file.setStyleSheet("color: gray")
        layout.addWidget(self.lbl_file)

        # 2. 网格设置
        self._add_section_title(layout, "📐 网格设置")

        layout.addWidget(QLabel("画布比例:"))
        self.combo_ratio = QComboBox()
        self.combo_ratio.addItems([
            "原始比例", "1:1 (正方形)", "4:3", "3:4", "16:9", "9:16"
        ])
        self.combo_ratio.currentTextChanged.connect(self._on_ratio_change)
        layout.addWidget(self.combo_ratio)

        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("宽 (颗):"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(10, 200)
        self.spin_w.setValue(50)
        self.spin_w.valueChanged.connect(self._trigger_preview)
        grid_layout.addWidget(self.spin_w)

        grid_layout.addWidget(QLabel("高 (颗):"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(10, 200)
        self.spin_h.setValue(50)
        self.spin_h.valueChanged.connect(self._trigger_preview)
        grid_layout.addWidget(self.spin_h)

        layout.addLayout(grid_layout)

        # 3. 色卡选择
        self._add_section_title(layout, "🎨 色卡选择")

        self.combo_palette = QComboBox()
        self.combo_palette.addItems([name for name, _ in PALETTE_OPTIONS])
        self.combo_palette.setCurrentText("MARD 221 色")
        self.combo_palette.currentTextChanged.connect(self._trigger_preview)
        layout.addWidget(self.combo_palette)

        self.btn_color_chart = QPushButton("🎨 查看色卡")
        self.btn_color_chart.clicked.connect(self._open_color_chart)
        layout.addWidget(self.btn_color_chart)

        # 4. 画布设置
        self._add_section_title(layout, "🖼️ 画布设置")

        self.combo_canvas = QComboBox()
        self.combo_canvas.addItems(["1000", "1500", "2000", "2500", "3000"])
        self.combo_canvas.setCurrentText("1500")
        self.combo_canvas.currentTextChanged.connect(self._trigger_preview)
        layout.addWidget(self.combo_canvas)

        self.chk_labels = QCheckBox("显示行列标号")
        self.chk_labels.setChecked(True)
        self.chk_labels.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_labels)

        self.chk_grid = QCheckBox("显示网格线")
        self.chk_grid.setChecked(True)
        self.chk_grid.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_grid)

        self.chk_legend = QCheckBox("显示颜色图例")
        self.chk_legend.setChecked(True)
        self.chk_legend.stateChanged.connect(self._trigger_preview)
        layout.addWidget(self.chk_legend)

        # 网格颜色
        grid_color_layout = QHBoxLayout()
        grid_color_layout.addWidget(QLabel("网格颜色:"))
        self.btn_grid_color = QPushButton("#C8C8C8")
        self.btn_grid_color.setFixedWidth(100)
        self.btn_grid_color.clicked.connect(self._select_grid_color)
        grid_color_layout.addWidget(self.btn_grid_color)
        layout.addLayout(grid_color_layout)

        layout.addStretch()

        # 操作按钮
        self.btn_generate = QPushButton("🔄 生成预览")
        self.btn_generate.clicked.connect(self._generate_preview)
        layout.addWidget(self.btn_generate)

        self.btn_save = QPushButton("💾 保存图片")
        self.btn_save.clicked.connect(self._save_image)
        layout.addWidget(self.btn_save)

        # 颜色统计
        self._add_section_title(layout, "📊 颜色统计")
        self.lbl_stats = QLabel("生成后显示")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setStyleSheet("color: gray")
        layout.addWidget(self.lbl_stats)

        # 历史记录
        self._add_section_title(layout, "📜 历史记录")
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(150)
        self.history_list.itemClicked.connect(self._load_history_item)
        layout.addWidget(self.history_list)

        hist_btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_history)
        hist_btn_layout.addWidget(btn_refresh)

        btn_clear = QPushButton("清除")
        btn_clear.clicked.connect(self._clear_history)
        hist_btn_layout.addWidget(btn_clear)

        btn_load = QPushButton("加载")
        btn_load.clicked.connect(self._load_selected_history)
        hist_btn_layout.addWidget(btn_load)

        layout.addLayout(hist_btn_layout)

        self._refresh_history()

        return panel

    def _create_preview_panel(self) -> QWidget:
        """创建预览面板"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 标题
        title = QLabel("🖼️ 实时预览")
        title.setStyleSheet("font-size: 16px; font-weight: bold")
        layout.addWidget(title)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 图片预览
        self.image_label = QLabel("请选择图片并生成预览")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("""
            background-color: #F3F3F3;
            border: 1px solid #ddd;
            border-radius: 8px;
            min-height: 400px;
        """)
        layout.addWidget(self.image_label, 1)

        # 缩放控制
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("预览缩放:"))
        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(100, 800)
        self.spin_zoom.setValue(300)
        self.spin_zoom.setSuffix("px")
        self.spin_zoom.valueChanged.connect(self._update_zoom)
        zoom_layout.addWidget(self.spin_zoom)
        zoom_layout.addStretch()
        layout.addLayout(zoom_layout)

        # 状态
        self.lbl_status = QLabel("✅ 就绪")
        self.lbl_status.setStyleSheet("color: green; font-weight: bold")
        layout.addWidget(self.lbl_status)

        return panel

    def _add_section_title(self, layout, text):
        """添加分区标题"""
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; margin-top: 10px")
        layout.addWidget(label)

    def _init_status_bar(self):
        """初始化状态栏"""
        self.statusBar().showMessage("就绪")

    # ==================== 主题切换功能 ====================

    def _toggle_theme(self):
        """切换主题"""
        self.is_dark_theme = not self.is_dark_theme
        self._apply_theme()

    def _apply_theme(self):
        """应用主题"""
        if self.is_dark_theme:
            self.setStyleSheet(DARK_THEME)
            self.btn_theme.setText("☀️ 浅色模式")
        else:
            self.setStyleSheet(LIGHT_THEME)
            self.btn_theme.setText("🌙 深色模式")

        # 更新色卡窗口主题
        if self.color_chart_window:
            self.color_chart_window.is_dark_theme = self.is_dark_theme
            self.color_chart_window._load_colors()

    # ==================== 功能方法 ====================

    def _select_image(self):
        """选择图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Image Files (*.jpg *.png *.jpeg *.bmp)"
        )
        if file_path:
            self.selected_file = file_path
            self.lbl_file.setText(Path(file_path).name)
            self.lbl_file.setStyleSheet("color: black")

            from PIL import Image
            try:
                with Image.open(file_path) as img:
                    w, h = img.size
                    suggested = min(max(30, w // 20), 80)
                    self.spin_w.setValue(suggested)
                    self._calculate_dimension('w')
            except:
                pass

            self._trigger_preview()

    def _calculate_dimension(self, source: str):
        """计算尺寸"""
        w = self.spin_w.value()
        h = self.spin_h.value()
        ratio = self.combo_ratio.currentText()

        if ratio == "1:1 (正方形)":
            if source == 'w':
                self.spin_h.setValue(w)
            else:
                self.spin_w.setValue(h)
        elif ratio == "4:3":
            if source == 'w':
                self.spin_h.setValue(max(1, round(w * 3 / 4)))
            else:
                self.spin_w.setValue(max(1, round(h * 4 / 3)))
        elif ratio == "16:9":
            if source == 'w':
                self.spin_h.setValue(max(1, round(w * 9 / 16)))
            else:
                self.spin_w.setValue(max(1, round(h * 16 / 9)))

    def _on_ratio_change(self):
        """比例变化"""
        self._calculate_dimension('w')
        self._trigger_preview()

    def _trigger_preview(self):
        """触发预览（防抖）"""
        if self.preview_timer:
            self.preview_timer.stop()

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._generate_preview)
        self.preview_timer.start(500)

    def _generate_preview(self):
        """生成预览（后台线程）"""
        if self.is_processing:
            return

        if not self.selected_file:
            QMessageBox.warning(self, "提示", "请先选择图片！")
            return

        self.is_processing = True
        self.btn_generate.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("⏳ 正在处理...")
        self.lbl_status.setStyleSheet("color: blue")

        params = {
            'image_path': self.selected_file,
            'grid_w': self.spin_w.value(),
            'grid_h': self.spin_h.value(),
            'canvas_size': int(self.combo_canvas.currentText()),
            'show_grid': self.chk_grid.isChecked(),
            'grid_color': self._hex_to_rgb(self.btn_grid_color.text()),
            'palette_name': self._get_palette_internal(),
            'show_legend': self.chk_legend.isChecked(),
            'show_labels': self.chk_labels.isChecked()
        }

        self.worker_thread = QThread(self)
        self.worker = ProcessingWorker(self.processor, params)
        self.worker.moveToThread(self.worker_thread)

        self.worker.finished.connect(self._on_processing_finished)
        self.worker.error.connect(self._on_processing_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.started.connect(self.worker.run)

        self.worker_thread.start()

    def _on_processing_finished(self, result):
        """处理完成"""
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.is_processing = False

        save_path, img_obj, color_stats, total_beads, grid_w, grid_h = result

        if img_obj:
            img_obj = img_obj.convert('RGB')
            data = img_obj.tobytes()
            qimage = QImage(
                data, img_obj.width, img_obj.height,
                img_obj.width * 3, QImage.Format_RGB888
            )
            self.current_image = qimage
            self.color_stats = color_stats
            self.total_beads = total_beads

            self._update_preview_display()
            self._update_stats_display(total_beads, grid_w, grid_h)

            self.lbl_status.setText(f"✅ 完成！网格：{grid_w}×{grid_h}")
            self.lbl_status.setStyleSheet("color: green")
            self.statusBar().showMessage(f"生成完成！共 {total_beads} 颗豆子", 3000)
        else:
            self.lbl_status.setText("❌ 处理失败")
            self.lbl_status.setStyleSheet("color: red")

    def _on_processing_error(self, error_msg):
        """处理错误"""
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.is_processing = False
        self.lbl_status.setText("❌ 处理失败")
        self.lbl_status.setStyleSheet("color: red")
        QMessageBox.critical(self, "错误", error_msg)

    def _update_preview_display(self):
        """更新预览显示"""
        if self.current_image:
            zoom_size = self.spin_zoom.value()
            scaled = self.current_image.scaled(
                zoom_size, zoom_size,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_label.setPixmap(QPixmap.fromImage(scaled))
            self.image_label.setText("")

    def _update_zoom(self):
        """更新缩放"""
        self._update_preview_display()

    def _update_stats_display(self, total_beads, grid_w, grid_h):
        """更新统计显示"""
        if not self.color_stats:
            return

        text = "📊 颜色统计:\n"
        sorted_stats = sorted(
            self.color_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:10]

        for code, info in sorted_stats:
            text += f"● {info['code']} {info['name']}: {info['count']}颗\n"

        if len(self.color_stats) > 10:
            text += f"... 共 {len(self.color_stats)} 种颜色\n"

        text += f"\n总计：{total_beads} 颗豆子 | 网格：{grid_w}×{grid_h}"
        self.lbl_stats.setText(text)
        self.lbl_stats.setStyleSheet("color: black")

    def _save_image(self):
        """保存图片"""
        if not self.current_image:
            QMessageBox.warning(self, "提示", "请先生成预览！")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "perler_pattern.png", "PNG Files (*.png)"
        )
        if save_path:
            self.current_image.save(save_path)
            QMessageBox.information(self, "成功", f"已保存至：{save_path}")

    def _select_grid_color(self):
        """选择网格颜色"""
        color = QColor(self.btn_grid_color.text())
        dialog = QColorDialog(color, self)
        if dialog.exec():
            new_color = dialog.selectedColor()
            self.btn_grid_color.setText(new_color.name())
            self._trigger_preview()

    def _open_color_chart(self):
        """打开色卡预览"""
        palette_name = self._get_palette_internal()

        if self.color_chart_window is None:
            # 🔧 传递当前主题状态
            self.color_chart_window = ColorChartDialog(
                self,
                palette_name,
                is_dark_theme=self.is_dark_theme
            )

        self.color_chart_window.show()
        self.color_chart_window.activateWindow()
        self.color_chart_window.raise_()

    def _get_palette_internal(self) -> str:
        """获取色卡内部名称"""
        display_name = self.combo_palette.currentText()
        for display, internal in PALETTE_OPTIONS:
            if display == display_name:
                return internal
        return "mard_221"

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """HEX 转 RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def _refresh_history(self):
        """刷新历史"""
        self.history_list.clear()
        for i, record in enumerate(self.history_mgr.get_list()):
            text = f"[{i}] {record['time']} - {record['width']}x{record['height']} ({record['palette']})"
            item = QListWidgetItem(text)
            self.history_list.addItem(item)

    def _clear_history(self):
        """清除历史"""
        reply = QMessageBox.question(
            self, "确认", "确定要清除所有历史记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.history_mgr.clear_history()
            self._refresh_history()
            self.statusBar().showMessage("历史记录已清空", 3000)

    def _load_selected_history(self):
        """加载选中历史"""
        current = self.history_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, "提示", "请先选择一条历史记录")
            return

        record = self.history_mgr.get_record(current)
        if not record:
            return

        if not os.path.exists(record['image_path']):
            QMessageBox.error(self, "错误", "原图片已不存在")
            return

        self.selected_file = record['image_path']
        self.lbl_file.setText(os.path.basename(record['image_path']))
        self.lbl_file.setStyleSheet("color: black")

        self.spin_w.setValue(record['width'])
        self.spin_h.setValue(record['height'])
        self.combo_ratio.setCurrentText(record.get('ratio', '原始比例'))
        self.combo_canvas.setCurrentText(str(record.get('output_size', 1500)))
        self.chk_grid.setChecked(record.get('show_grid', True))
        self.btn_grid_color.setText(record.get('grid_color', '#C8C8C8'))
        self.combo_palette.setCurrentText(record.get('palette', 'MARD 221 色'))

        self.statusBar().showMessage(f"已加载历史 [{current}]，自动生成预览...", 3000)
        self._trigger_preview()

    def _load_history_item(self, item):
        """加载历史项"""
        self._load_selected_history()


# ==================== 启动入口 ====================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = DesktopUI()
    window.show()

    sys.exit(app.exec())
#1234