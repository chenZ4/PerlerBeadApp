# ui/panels/settings_panel.py - 设置面板（图片源/网格/色卡/画布）
import tkinter as tk
from tkinter import ttk

from core.colors import PALETTE_OPTIONS
from core.models import (
    DEFAULT_CELL_PX,
    DEFAULT_GRID,
    DEFAULT_GRID_COLOR,
    DEFAULT_PALETTE,
    RATIOS,
    GenerateParams,
    cm_hint,
    link_dimensions,
    parse_cell_px,
    parse_grid_h,
    parse_grid_w,
)
from ui.theme import ACCENT

CELL_PX_OPTIONS = ["32", "40", "48", "60", "80", "96"]
_PALETTE_DISPLAYS = [d for d, _ in PALETTE_OPTIONS]


class SettingsPanel:
    """左侧设置面板：图片源 + 网格 + 色卡 + 画布。

    面板只负责 widget 与字段联动（link_from），参数快照经 current_params() 输出。
    """

    def __init__(self, parent, settings,
                 on_select_image=None, on_dimension_change=None,
                 on_ratio_change=None, on_setting_change=None,
                 on_open_color_chart=None):
        from ui.widgets import section_title

        self._on_dimension_change = on_dimension_change
        self._on_ratio_cb = lambda: None
        self._setting_cb = lambda save=True: None
        self._is_calculating = False
        self._aspect = 1.0   # 源图宽高比，选图后由控制器更新

        # ===== 1. 图片源 =====
        section_title(parent, "📁 图片源")
        self.btn_select = ttk.Button(parent, text="选择图片",
                                     command=on_select_image)
        self.btn_select.pack(fill=tk.X, pady=5)
        self.lbl_file = ttk.Label(parent, text="未选择图片",
                                  foreground="gray", wraplength=300)
        self.lbl_file.pack(fill=tk.X, pady=5)

        # ===== 2. 网格设置 =====
        section_title(parent, "📐 网格设置")

        ttk.Label(parent, text="画布比例:").pack(anchor=tk.W)
        self.ratio_var = tk.StringVar(value=settings.get('ratio', RATIOS[0]))
        self.combo_ratio = ttk.Combobox(parent, textvariable=self.ratio_var,
                                        values=RATIOS, state="readonly")
        self.combo_ratio.pack(fill=tk.X, pady=5)
        self.combo_ratio.bind("<<ComboboxSelected>>", self._on_ratio_picked)

        frame_wh = ttk.Frame(parent)
        frame_wh.pack(fill=tk.X, pady=10)

        ttk.Label(frame_wh, text="宽 (颗):").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.entry_w = ttk.Entry(frame_wh, width=8)
        self.entry_w.insert(0, str(DEFAULT_GRID))
        self.entry_w.grid(row=0, column=1, padx=5)
        self.entry_w.bind("<Return>", lambda e: self._on_enter('w'))
        self.entry_w.bind("<FocusOut>", lambda e: self._notify_dimension('w'))
        self.entry_w.bind("<KeyRelease>", lambda e: self._on_key_release('w'))

        ttk.Label(frame_wh, text="高 (颗):").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.entry_h = ttk.Entry(frame_wh, width=8)
        self.entry_h.insert(0, str(DEFAULT_GRID))
        self.entry_h.grid(row=0, column=3, padx=5)
        self.entry_h.bind("<Return>", lambda e: self._on_enter('h'))
        self.entry_h.bind("<FocusOut>", lambda e: self._notify_dimension('h'))
        self.entry_h.bind("<KeyRelease>", lambda e: self._on_key_release('h'))

        self.lbl_cm_hint = ttk.Label(parent, text="", foreground="gray")
        self.lbl_cm_hint.pack(anchor=tk.W, pady=(0, 5))

        # ===== 3. 色卡选择 =====
        section_title(parent, "🎨 色卡选择")
        ttk.Label(parent, text="色卡方案:").pack(anchor=tk.W)
        self.palette_var = tk.StringVar(value=settings.get('palette', DEFAULT_PALETTE))
        self.combo_palette = ttk.Combobox(
            parent, textvariable=self.palette_var,
            values=[name for name, _ in PALETTE_OPTIONS], state="readonly")
        self.combo_palette.pack(fill=tk.X, pady=5)
        self.combo_palette.bind("<<ComboboxSelected>>", self._on_setting_picked)
        self.lbl_palette_info = ttk.Label(parent, text="", foreground=ACCENT)
        self.lbl_palette_info.pack(anchor=tk.W, pady=5)
        ttk.Button(parent, text="🎨 查看色卡",
                   command=on_open_color_chart).pack(fill=tk.X, pady=5)

        # ===== 4. 画布设置 =====
        section_title(parent, "🖼️ 画布设置")
        frame_cell = ttk.Frame(parent)
        frame_cell.pack(fill=tk.X, pady=5)
        ttk.Label(frame_cell, text="每格像素:").pack(side=tk.LEFT)
        self.cell_px_var = tk.StringVar(
            value=settings.get('cell_px', str(DEFAULT_CELL_PX)))
        self.combo_cell_px = ttk.Combobox(frame_cell, textvariable=self.cell_px_var,
                                          values=CELL_PX_OPTIONS, width=8)
        self.combo_cell_px.pack(side=tk.LEFT, padx=10)
        self.combo_cell_px.bind("<<ComboboxSelected>>", self._on_setting_picked)
        self.combo_cell_px.bind("<Return>", self._on_setting_picked)
        ttk.Label(parent, text="输出尺寸 = 格子数 × 每格像素，默认 60 清晰度",
                  foreground="gray").pack(anchor=tk.W)

        self.show_labels_var = tk.BooleanVar(value=bool(settings.get('show_labels', True)))
        ttk.Checkbutton(parent, text="显示行列标号", variable=self.show_labels_var,
                        command=self._on_setting_picked).pack(anchor=tk.W, pady=5)
        self.show_grid_var = tk.BooleanVar(value=bool(settings.get('show_grid', True)))
        ttk.Checkbutton(parent, text="显示网格线", variable=self.show_grid_var,
                        command=self._on_setting_picked).pack(anchor=tk.W, pady=5)
        self.show_legend_var = tk.BooleanVar(value=bool(settings.get('show_legend', True)))
        ttk.Checkbutton(parent, text="显示颜色图例", variable=self.show_legend_var,
                        command=self._on_setting_picked).pack(anchor=tk.W, pady=5)

        frame_color = ttk.Frame(parent)
        frame_color.pack(fill=tk.X, pady=5)
        ttk.Label(frame_color, text="网格颜色:").pack(side=tk.LEFT)
        self.grid_color_var = tk.StringVar(value=settings.get('grid_color', DEFAULT_GRID_COLOR))
        self.entry_grid_color = ttk.Entry(frame_color, textvariable=self.grid_color_var, width=12)
        self.entry_grid_color.pack(side=tk.LEFT, padx=10)
        self.entry_grid_color.bind("<KeyRelease>", lambda e: self._notify_setting(save=False))
        self.entry_grid_color.bind("<FocusOut>", self._on_setting_picked)

    # ---------- 事件转发 ----------
    def _on_ratio_picked(self, _event=None):
        self.link_from('w')
        self._on_ratio_cb()

    def set_on_ratio_change(self, cb):
        self._on_ratio_cb = cb

    def _on_setting_picked(self, _event=None):
        self._notify_setting(save=True)

    def _notify_setting(self, save=True):
        self._setting_cb(save)

    def set_on_setting_change(self, cb):
        self._setting_cb = cb

    def _notify_dimension(self, source):
        if self._on_dimension_change:
            self._on_dimension_change(source)

    def _on_enter(self, source):
        self._notify_dimension(source)

    # ---------- 字段联动 ----------
    def set_aspect(self, aspect):
        """源图像素宽高比（iw/ih），由控制器在选图/加载历史时更新；无图 1.0（1:1 兜底）"""
        self._aspect = aspect if aspect and aspect > 0 else 1.0

    def _on_key_release(self, source):
        """输入实时联动（对齐 Swift 版）：另一侧为合法整数才联动，且不回写正在编辑的框"""
        if self._is_calculating:
            return
        try:
            w = int(self.entry_w.get().strip())
            h = int(self.entry_h.get().strip())
        except (TypeError, ValueError):
            return
        nw, nh = link_dimensions(source, parse_grid_w(str(w)), parse_grid_h(str(h)),
                                 self.ratio_var.get(), aspect=self._aspect)
        self._is_calculating = True
        try:
            if source == 'w' and nh != h:
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(nh))
            elif source == 'h' and nw != w:
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(nw))
        finally:
            self._is_calculating = False
        self.update_cm_hint()

    def link_from(self, source):
        """按比例联动另一维度（失焦/回车/切比例时；固定比例按比例、原始比例按源图比）"""
        if self._is_calculating:
            return
        self._is_calculating = True
        try:
            w = parse_grid_w(self.entry_w.get())
            h = parse_grid_h(self.entry_h.get())
            w, h = link_dimensions(source, w, h, self.ratio_var.get(),
                                   aspect=self._aspect)
            self.set_grid(w, h)
        finally:
            self._is_calculating = False

    def set_grid(self, w, h):
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(w))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(h))

    def update_cm_hint(self):
        try:
            w = int(self.entry_w.get().strip())
            h = int(self.entry_h.get().strip())
            if w < 1 or h < 1:
                raise ValueError
            self.lbl_cm_hint.config(text=cm_hint(w, h))
        except (TypeError, ValueError):
            self.lbl_cm_hint.config(text="")

    def update_palette_info(self):
        from core.colors import display_to_internal, get_palette
        palette = get_palette(display_to_internal(self.palette_var.get()))
        self.lbl_palette_info.config(text=f"✓ 共 {len(palette.colors)} 种颜色")

    # ---------- 参数快照 ----------
    def current_params(self) -> GenerateParams:
        return GenerateParams(
            grid_w=parse_grid_w(self.entry_w.get()),
            grid_h=parse_grid_h(self.entry_h.get()),
            cell_px=parse_cell_px(self.cell_px_var.get()),
            ratio=self.ratio_var.get(), palette=self.palette_var.get(),
            show_grid=self.show_grid_var.get(), show_labels=self.show_labels_var.get(),
            show_legend=self.show_legend_var.get(), grid_color=self.grid_color_var.get(),
        )

    def apply_params(self, params: GenerateParams):
        """把参数快照写回控件（撤销/历史/模板加载用）"""
        self.set_grid(params.grid_w, params.grid_h)
        self.ratio_var.set(params.ratio)
        self.cell_px_var.set(str(params.cell_px))
        self.show_grid_var.set(params.show_grid)
        self.show_labels_var.set(params.show_labels)
        self.show_legend_var.set(params.show_legend)
        self.grid_color_var.set(params.grid_color)
        if params.palette in _PALETTE_DISPLAYS:
            self.palette_var.set(params.palette)
        self.update_palette_info()
        self.update_cm_hint()
