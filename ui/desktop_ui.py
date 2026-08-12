# ui/desktop_ui.py

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from core.colors import PALETTE_OPTIONS, get_palette
from core.history_manager import HistoryManager
from core.processor import ImageProcessor, OUTPUT_DIR
from core.settings import load_queue, load_settings, save_queue, save_settings
from core.version import APP_NAME, APP_VERSION
from ui.fonts import is_mac, ui_font
from ui.theme import ACCENT, apply_theme

DEFAULT_GRID_COLOR = "#C8C8C8"
DEFAULT_GRID_RGB = (200, 200, 200)
MAX_RENDER_DIM = 8192
MAX_GRID_SIZE = 500
BIG_GRID_WARN = 40000
RATIO_ORIGINAL = "按原图比例（宽为基准）"
RATIO_FIT_BOX = "等比完整（适应框内）"
# 固定比例：网格尺寸必须精确，不允许引擎按源图比例重算
RATIO_FIXED = ["1:1 (正方形)", "4:3", "3:4", "16:9", "9:16"]
RATIOS = [RATIO_ORIGINAL, RATIO_FIT_BOX] + RATIO_FIXED + ["自定义"]

PALETTE_MAP = {display: internal for display, internal in PALETTE_OPTIONS}


class DesktopUI:
    def __init__(self, root):
        self.root = root
        self.root.title("拼豆图纸")
        apply_theme(root)
        self.settings = load_settings()

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        win_w = self.settings.get('window_w') or 0
        win_h = self.settings.get('window_h') or 0
        if win_w > 600 and win_h > 400:
            win_w = min(win_w, max(800, self.screen_width - 60))
            win_h = min(win_h, max(600, self.screen_height - 60))
            self.root.geometry(f"{win_w}x{win_h}")
        else:
            window_w = int(self.screen_width * 0.85)
            window_h = int(self.screen_height * 0.85)
            self.root.geometry(f"{window_w}x{window_h}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.processor = ImageProcessor()
        self.history_mgr = HistoryManager()

        self.original_image = None
        self.processed_image = None
        self.finished_image = None
        self.photo_ref = None
        self.selected_file = None
        self.current_save_path = None
        self.color_stats = {}
        self.total_beads = 0
        self.last_cell_size = 0

        # 性能优化
        self.preview_timer = None
        self.render_timer = None
        self.is_processing = False
        self.previous_states = []
        self.max_undo_steps = 10
        self.is_calculating = False

        # 色卡窗口
        self.color_chart_window = None

        # 批量队列
        self.queue_items = load_queue()
        self._queue_cancel = False
        self._queue_thumbs = []
        self._thumb_cache = {}

        # 处理中变更补生成
        self._pending_regenerate = False
        self._modal_active = False
        self._closing = False

        self.setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._setup_dnd()

    def setup_ui(self):
        # === 主容器 ===
        main_container = ttk.Frame(self.root, padding=15)
        main_container.pack(fill=tk.BOTH, expand=tk.YES)

        # === 左侧面板 ===
        left_panel = ttk.LabelFrame(main_container, text="⚙️ 设置面板", padding=15)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.configure(width=350)
        left_panel.pack_propagate(False)

        # 可滚动区域
        canvas = tk.Canvas(left_panel, width=320, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._settings_canvas = canvas
        canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # ===== 1. 图片选择 =====
        self._create_section_title("📁 图片源")

        self.btn_select = ttk.Button(self.scrollable_frame, text="选择图片", command=self.select_image)
        self.btn_select.pack(fill=tk.X, pady=5)

        self.lbl_file = ttk.Label(self.scrollable_frame, text="未选择图片", foreground="gray", wraplength=300)
        self.lbl_file.pack(fill=tk.X, pady=5)

        # ===== 2. 网格设置 =====
        self._create_section_title("📐 网格设置")

        ttk.Label(self.scrollable_frame, text="画布比例:").pack(anchor=tk.W)
        self.ratio_var = tk.StringVar(value=self.settings.get('ratio', RATIO_ORIGINAL))
        self.combo_ratio = ttk.Combobox(self.scrollable_frame, textvariable=self.ratio_var, values=RATIOS,
                                        state="readonly")
        self.combo_ratio.pack(fill=tk.X, pady=5)
        self.combo_ratio.bind("<<ComboboxSelected>>", self._on_ratio_change)

        frame_wh = ttk.Frame(self.scrollable_frame)
        frame_wh.pack(fill=tk.X, pady=10)

        ttk.Label(frame_wh, text="宽 (颗):").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.entry_w = ttk.Entry(frame_wh, width=8)
        self.entry_w.insert(0, "50")
        self.entry_w.grid(row=0, column=1, padx=5)
        self.entry_w.bind("<Return>", self._on_enter_press)
        self.entry_w.bind("<FocusOut>", lambda e: self._on_dimension_change('w'))

        ttk.Label(frame_wh, text="高 (颗):").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.entry_h = ttk.Entry(frame_wh, width=8)
        self.entry_h.insert(0, "50")
        self.entry_h.grid(row=0, column=3, padx=5)
        self.entry_h.bind("<Return>", self._on_enter_press)
        self.entry_h.bind("<FocusOut>", lambda e: self._on_dimension_change('h'))

        self.lbl_cm_hint = ttk.Label(self.scrollable_frame, text="", foreground="gray")
        self.lbl_cm_hint.pack(anchor=tk.W, pady=(0, 5))
        self._update_cm_hint()

        # ===== 3. 色卡选择 =====
        self._create_section_title("🎨 色卡选择")

        ttk.Label(self.scrollable_frame, text="色卡方案:").pack(anchor=tk.W)
        self.palette_var = tk.StringVar(value=self.settings.get('palette', 'MARD 221 色'))
        self.combo_palette = ttk.Combobox(self.scrollable_frame, textvariable=self.palette_var,
                                          values=[name for name, _ in PALETTE_OPTIONS], state="readonly")
        self.combo_palette.pack(fill=tk.X, pady=5)
        self.combo_palette.bind("<<ComboboxSelected>>", self._on_setting_change)

        self.lbl_palette_info = ttk.Label(self.scrollable_frame, text="", foreground=ACCENT)
        self.lbl_palette_info.pack(anchor=tk.W, pady=5)
        self._update_palette_info()

        # ===== 4. 画布设置 =====
        self._create_section_title("🖼️ 画布设置")

        frame_cell = ttk.Frame(self.scrollable_frame)
        frame_cell.pack(fill=tk.X, pady=5)
        ttk.Label(frame_cell, text="每格像素:").pack(side=tk.LEFT)
        self.cell_px_var = tk.StringVar(value=str(self.settings.get('cell_px', '60')))
        self.combo_cell_px = ttk.Combobox(frame_cell, textvariable=self.cell_px_var,
                                          values=["32", "40", "48", "60", "80", "96"],
                                          width=8)
        self.combo_cell_px.pack(side=tk.LEFT, padx=10)
        self.combo_cell_px.bind("<<ComboboxSelected>>", self._on_setting_change)
        self.combo_cell_px.bind("<Return>", self._on_setting_change)
        ttk.Label(self.scrollable_frame, text="输出尺寸 = 格子数 × 每格像素，默认 60 清晰度",
                  foreground="gray").pack(anchor=tk.W)

        self.show_labels_var = tk.BooleanVar(value=bool(self.settings.get('show_labels', True)))
        self.chk_labels = ttk.Checkbutton(self.scrollable_frame, text="显示行列标号",
                                          variable=self.show_labels_var,
                                          command=self._on_setting_change)
        self.chk_labels.pack(anchor=tk.W, pady=5)

        self.show_grid_var = tk.BooleanVar(value=bool(self.settings.get('show_grid', True)))
        self.chk_grid = ttk.Checkbutton(self.scrollable_frame, text="显示网格线", variable=self.show_grid_var,
                                        command=self._on_setting_change)
        self.chk_grid.pack(anchor=tk.W, pady=5)

        self.show_legend_var = tk.BooleanVar(value=bool(self.settings.get('show_legend', True)))
        self.chk_legend = ttk.Checkbutton(self.scrollable_frame, text="显示颜色图例", variable=self.show_legend_var,
                                          command=self._on_setting_change)
        self.chk_legend.pack(anchor=tk.W, pady=5)

        frame_grid_color = ttk.Frame(self.scrollable_frame)
        frame_grid_color.pack(fill=tk.X, pady=5)
        ttk.Label(frame_grid_color, text="网格颜色:").pack(side=tk.LEFT)
        self.grid_color_var = tk.StringVar(value=self.settings.get('grid_color', DEFAULT_GRID_COLOR))
        self.entry_grid_color = ttk.Entry(frame_grid_color, textvariable=self.grid_color_var, width=12)
        self.entry_grid_color.pack(side=tk.LEFT, padx=10)
        self.entry_grid_color.bind("<KeyRelease>", lambda e: self._trigger_preview())
        self.entry_grid_color.bind("<FocusOut>", self._on_setting_change)

        # ===== 5. 操作按钮 =====
        self._create_section_title("🔧 操作")

        frame_buttons = ttk.Frame(self.scrollable_frame)
        frame_buttons.pack(fill=tk.X, pady=10)

        self.btn_undo = ttk.Button(frame_buttons, text="↩️ 撤销", command=self.undo, width=8)
        self.btn_undo.pack(side=tk.LEFT, padx=5)
        self.btn_undo.config(state=tk.DISABLED)

        self.btn_generate = ttk.Button(frame_buttons, text="🔄 生成",
                                       command=lambda: self.generate_preview(confirm_big=True), width=8)
        self.btn_generate.pack(side=tk.LEFT, padx=5)

        self.btn_save = ttk.Button(self.scrollable_frame, text="💾 保存并加入历史",
                                   command=self.save_to_history)
        self.btn_save.pack(fill=tk.X, pady=5)

        self.btn_export_png = ttk.Button(self.scrollable_frame, text="🖼️ 导出 PNG...", command=self.export_png)
        self.btn_export_png.pack(fill=tk.X, pady=5)

        self.btn_export_pdf = ttk.Button(self.scrollable_frame, text="📄 导出 PDF...", command=self.export_pdf)
        self.btn_export_pdf.pack(fill=tk.X, pady=5)

        self.btn_color_chart = ttk.Button(self.scrollable_frame, text="🎨 查看色卡", command=self.open_color_chart)
        self.btn_color_chart.pack(fill=tk.X, pady=5)

        # ===== 6. 批量队列 =====
        self._create_section_title("📋 批量队列")

        frame_queue_format = ttk.Frame(self.scrollable_frame)
        frame_queue_format.pack(fill=tk.X, pady=5)
        ttk.Label(frame_queue_format, text="导出格式:").pack(side=tk.LEFT)
        self.queue_format_var = tk.StringVar(value="PNG")
        self.combo_queue_format = ttk.Combobox(frame_queue_format, textvariable=self.queue_format_var,
                                               values=["PNG", "PDF(A4适应)", "PDF(1:1实物)"],
                                               state="readonly", width=13)
        self.combo_queue_format.pack(side=tk.LEFT, padx=10)

        frame_queue_btn = ttk.Frame(self.scrollable_frame)
        frame_queue_btn.pack(fill=tk.X, pady=5)
        ttk.Button(frame_queue_btn, text="➕ 加入队列", command=self.enqueue_item, width=10).pack(side=tk.LEFT, padx=2)
        self.btn_queue_start = ttk.Button(frame_queue_btn, text="▶ 开始批量", command=self.process_queue, width=10,
                                          style="Accent.TButton")
        self.btn_queue_start.pack(side=tk.LEFT, padx=2)
        self.btn_queue_cancel = ttk.Button(frame_queue_btn, text="⏹ 取消", command=self._cancel_queue, width=8,
                                           state=tk.DISABLED)
        self.btn_queue_cancel.pack(side=tk.LEFT, padx=2)

        self.queue_tree = ttk.Treeview(self.scrollable_frame, columns=("thumb", "info"),
                                       show="tree", height=5)
        self.queue_tree.heading("#0", text="图片")
        self.queue_tree.column("#0", width=140, anchor=tk.W)
        self.queue_tree.heading("thumb", text="")
        self.queue_tree.column("thumb", width=54, anchor=tk.CENTER, stretch=False)
        self.queue_tree.heading("info", text="设置")
        self.queue_tree.column("info", width=130, anchor=tk.W)
        self.queue_tree.pack(fill=tk.X, pady=5)

        frame_queue_action = ttk.Frame(self.scrollable_frame)
        frame_queue_action.pack(fill=tk.X, pady=5)
        ttk.Button(frame_queue_action, text="移除选中", command=self.remove_selected_queue, width=10).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(frame_queue_action, text="清空", command=self.clear_queue, width=10).pack(side=tk.LEFT, padx=2)

        self.progress = ttk.Progressbar(self.scrollable_frame, maximum=100, value=0)
        self.progress.pack(fill=tk.X, pady=5)
        self.lbl_queue_status = ttk.Label(self.scrollable_frame, text="队列为空", foreground="gray")
        self.lbl_queue_status.pack(anchor=tk.W)

        # ===== 7. 颜色统计 =====
        self._create_section_title("📊 颜色统计")
        self.lbl_color_stats = ttk.Label(self.scrollable_frame, text="生成后显示", foreground="gray", wraplength=300)
        self.lbl_color_stats.pack(fill=tk.X, pady=5)

        # ===== 8. 历史记录 =====
        self._create_section_title("📜 历史记录")

        frame_hist_btn = ttk.Frame(self.scrollable_frame)
        frame_hist_btn.pack(fill=tk.X, pady=5)
        ttk.Button(frame_hist_btn, text="刷新", command=self.refresh_history_list, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_hist_btn, text="清除", command=self.clear_history, width=6).pack(side=tk.LEFT, padx=2)

        self.list_history = tk.Listbox(self.scrollable_frame, height=6)
        self.list_history.pack(fill=tk.X, pady=5)
        self.list_history.bind("<<ListboxSelect>>", self.load_history_item)
        self.refresh_history_list()

        frame_hist_action = ttk.Frame(self.scrollable_frame)
        frame_hist_action.pack(fill=tk.X, pady=5)
        ttk.Button(frame_hist_action, text="加载", command=self.load_selected_history, width=8).pack(side=tk.LEFT,
                                                                                                     padx=2)
        ttk.Button(frame_hist_action, text="删除", command=self.delete_selected_history, width=8).pack(side=tk.LEFT,
                                                                                                       padx=2)

        # === 右侧预览面板 ===
        right_panel = ttk.LabelFrame(main_container, text="🖼️ 实时预览", padding=15)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=tk.YES)

        self.canvas_frame = ttk.Frame(right_panel)
        self.canvas_frame.pack(fill=tk.BOTH, expand=tk.YES, pady=10)
        self.canvas_frame.bind("<Configure>", self._on_preview_resize)

        self.preview_canvas = tk.Canvas(self.canvas_frame, background="#F3F3F3", highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=tk.YES)
        self.preview_canvas.bind("<MouseWheel>", self._on_preview_wheel)
        self.preview_canvas.bind("<ButtonPress-1>", self._on_preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_preview_release)
        self.preview_canvas.bind("<Double-Button-1>", self._on_preview_double_click)
        self.canvas_frame.bind("<MouseWheel>", self._on_preview_wheel)
        self._drag_start = None
        self._img_item = None
        self._img_w = 0
        self._img_h = 0
        self._ox = 0
        self._oy = 0
        self._show_preview_placeholder()

        self.scale_frame = ttk.Frame(right_panel)
        self.scale_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.scale_frame, text="预览缩放:").pack(side=tk.LEFT)
        self.fit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.scale_frame, text="适应窗口", variable=self.fit_var,
                        command=self._toggle_fit).pack(side=tk.LEFT)
        self.zoom_var = tk.IntVar(value=100)
        self.scale_zoom = ttk.Scale(self.scale_frame, from_=25, to=400, variable=self.zoom_var,
                                    orient=tk.HORIZONTAL, command=self.update_zoom)
        self.scale_zoom.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES, padx=10)
        self.lbl_zoom_val = ttk.Label(self.scale_frame, text="适应窗口", width=8)
        self.lbl_zoom_val.pack(side=tk.LEFT)
        self.finished_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.scale_frame, text="成品效果", variable=self.finished_var,
                        command=lambda: self._schedule_render(40)).pack(side=tk.LEFT, padx=(12, 0))

        self.lbl_status = ttk.Label(right_panel, text="✅ 就绪", style="Status.OK.TLabel")
        self.lbl_status.pack(pady=10)

    def _setup_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="选择图片...", command=self.select_image)
        file_menu.add_separator()
        file_menu.add_command(label="保存并加入历史...", command=self.save_to_history)
        file_menu.add_command(label="导出 PNG...", command=self.export_png)
        file_menu.add_command(label="导出 PDF...", command=self.export_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        if is_mac():
            apple = tk.Menu(menubar, name="apple")
            apple.add_command(label=f"关于 {APP_NAME}", command=self._show_about)
            apple.add_separator()
            apple.add_command(label=f"退出 {APP_NAME}", command=self._on_close)
            menubar.add_cascade(menu=apple)

        self.root.config(menu=menubar)

    def _on_close(self):
        self._closing = True
        self._persist_settings()
        self.root.destroy()

    def _persist_settings(self):
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w > 600 and h > 400:
                self.settings['window_w'] = w
                self.settings['window_h'] = h
            self.settings.update({
                'ratio': self.ratio_var.get(),
                'palette': self.palette_var.get(),
                'cell_px': self.cell_px_var.get(),
                'show_grid': self.show_grid_var.get(),
                'show_labels': self.show_labels_var.get(),
                'show_legend': self.show_legend_var.get(),
                'grid_color': self.grid_color_var.get(),
            })
            save_settings(self.settings)
        except Exception:
            pass

    def _update_cm_hint(self):
        try:
            w = int(self.entry_w.get())
            h = int(self.entry_h.get())
            if w < 1 or h < 1:
                raise ValueError
            self.lbl_cm_hint.config(
                text=f"成品约 {w * 0.5:.0f} × {h * 0.5:.0f} cm（每颗 5mm）")
        except Exception:
            self.lbl_cm_hint.config(text="")

    def _guarded(self, handler):
        """模态窗口激活时屏蔽快捷键"""
        def wrapped(event=None):
            if self._modal_active:
                return
            handler()
        return wrapped

    def _setup_shortcuts(self):
        actions = {
            'o': self.select_image,
            's': self.save_to_history,
            'p': self.export_pdf,
            'e': self.export_png,
            'equal': lambda: self._zoom_by(10),
            'minus': lambda: self._zoom_by(-10),
        }

        for mod in ("Command", "Control"):
            for key, handler in actions.items():
                self.root.bind_all(f"<{mod}-{key}>", self._guarded(handler))

    def _zoom_by(self, delta_pct):
        if not self.processed_image:
            return
        if self.fit_var.get():
            self.fit_var.set(False)
        new_zoom = max(25, min(400, self.zoom_var.get() + delta_pct))
        self.zoom_var.set(new_zoom)
        self.lbl_zoom_val.config(text=f"{new_zoom}%")
        self._schedule_render(40)

    def _show_about(self):
        messagebox.showinfo("关于", f"{APP_NAME} v{APP_VERSION}\n\n支持 Mac / Windows\n批量队列、PNG / PDF 导出")

    def _show_in_folder(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            elif os.name == "nt":
                subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

    def _center_toplevel(self, win):
        win.update_idletasks()
        width = win.winfo_reqwidth()
        height = win.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.focus_set()

    def _show_result_dialog(self, title, text, path=None):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        self._modal_active = True

        ttk.Label(win, text=text, wraplength=520, justify=tk.LEFT).pack(padx=24, pady=(18, 8))

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=12)

        def close():
            self._modal_active = False
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

        if path:
            ttk.Button(btn_frame, text="📂 在文件夹中显示", style="Accent.TButton",
                       command=lambda: (self._show_in_folder(path), close())).pack(
                side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="关闭", command=close).pack(side=tk.LEFT, padx=6)

        self._center_toplevel(win)
        self.root.wait_window(win)
        self._modal_active = False
        if self._closing:
            return

    def _create_section_title(self, text):
        ttk.Label(self.scrollable_frame, text=text, style="Section.TLabel").pack(anchor=tk.W, pady=(15, 8))
        ttk.Separator(self.scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))

    def _on_mousewheel(self, event):
        if not str(event.widget).startswith(str(self._settings_canvas)):
            return
        if is_mac():
            step = int(-event.delta)
        else:
            step = int(-(event.delta / 120))
        self._settings_canvas.yview_scroll(step, "units")

    # ---------- 撤销 ----------
    def _save_current_state(self):
        state = {
            'ratio': self.ratio_var.get(), 'width': self.entry_w.get(), 'height': self.entry_h.get(),
            'palette': self.palette_var.get(), 'cell_px': self.cell_px_var.get(),
            'show_grid': self.show_grid_var.get(), 'show_labels': self.show_labels_var.get(),
            'show_legend': self.show_legend_var.get(),
            'grid_color': self.grid_color_var.get(), 'selected_file': self.selected_file,
        }
        self.previous_states.append(state)
        if len(self.previous_states) > self.max_undo_steps:
            self.previous_states.pop(0)
        self.btn_undo.config(state=tk.NORMAL if len(self.previous_states) > 0 else tk.DISABLED)

    def undo(self):
        if not self.previous_states:
            return
        state = self.previous_states.pop()
        self.ratio_var.set(state['ratio'])
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, state['width'])
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, state['height'])
        self.palette_var.set(state['palette'])
        self.cell_px_var.set(state['cell_px'])
        self.show_grid_var.set(state['show_grid'])
        self.show_labels_var.set(state['show_labels'])
        self.show_legend_var.set(state['show_legend'])
        self.grid_color_var.set(state['grid_color'])
        if state['selected_file']:
            self.selected_file = state['selected_file']
            self.lbl_file.config(text=os.path.basename(state['selected_file']), foreground="black")
        self._update_palette_info()
        self._update_cm_hint()
        self.btn_undo.config(state=tk.NORMAL if len(self.previous_states) > 0 else tk.DISABLED)
        self.generate_preview()
        self.lbl_status.config(text="↩️ 已撤销", style="Status.Warn.TLabel")

    # ---------- 色卡窗口 ----------
    def open_color_chart(self):
        if self.color_chart_window is None or not self.color_chart_window.window.winfo_exists():
            from ui.color_chart_ui import ColorChartWindow
            self.color_chart_window = ColorChartWindow(self.root, palette_name=self._current_palette())
            self.color_chart_window.window.bind("<Destroy>", self._on_color_chart_destroy)
        else:
            self.color_chart_window.window.focus_force()
            self.color_chart_window.window.lift()

    def _on_color_chart_destroy(self, event):
        if self.color_chart_window is not None and event.widget is self.color_chart_window.window:
            self.color_chart_window = None

    # ---------- 尺寸联动 ----------
    def _on_enter_press(self, event):
        self._save_current_state()
        widget = event.widget
        if widget == self.entry_w:
            self._calculate_dimension('w')
        elif widget == self.entry_h:
            self._calculate_dimension('h')
        self._update_cm_hint()
        self._trigger_preview()

    def _on_ratio_change(self, event=None):
        self._save_current_state()
        self._calculate_dimension('w')
        self._trigger_preview()

    def _on_setting_change(self, event=None):
        self._save_current_state()
        self._update_cm_hint()
        self._trigger_preview()

    def _on_dimension_change(self, source):
        if self.is_calculating:
            return
        self._save_current_state()
        self._calculate_dimension(source)
        self._trigger_preview()

    def _calculate_dimension(self, source):
        if self.is_calculating:
            return
        self.is_calculating = True
        try:
            w_str = self.entry_w.get().strip()
            h_str = self.entry_h.get().strip()
            w = int(w_str) if w_str else 50
            h = int(h_str) if h_str else 50
        except (TypeError, ValueError):
            self.is_calculating = False
            return

        ratio = self.ratio_var.get()
        if ratio == "1:1 (正方形)":
            if source == 'w':
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(w))
            else:
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(h))
        elif ratio == "4:3":
            if source == 'w':
                new_h = max(1, round(w * 3 / 4))
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(new_h))
            else:
                new_w = max(1, round(h * 4 / 3))
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(new_w))
        elif ratio == "3:4":
            if source == 'w':
                new_h = max(1, round(w * 4 / 3))
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(new_h))
            else:
                new_w = max(1, round(h * 3 / 4))
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(new_w))
        elif ratio == "16:9":
            if source == 'w':
                new_h = max(1, round(w * 9 / 16))
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(new_h))
            else:
                new_w = max(1, round(h * 16 / 9))
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(new_w))
        elif ratio == "9:16":
            if source == 'w':
                new_h = max(1, round(w * 16 / 9))
                self.entry_h.delete(0, tk.END)
                self.entry_h.insert(0, str(new_h))
            else:
                new_w = max(1, round(h * 9 / 16))
                self.entry_w.delete(0, tk.END)
                self.entry_w.insert(0, str(new_w))
        self.is_calculating = False

    def _update_palette_info(self):
        internal = self._display_to_internal(self.palette_var.get())
        palette = get_palette(internal)
        self.lbl_palette_info.config(text=f"✓ 共 {len(palette.colors)} 种颜色")

    def _display_to_internal(self, display_name):
        return PALETTE_MAP.get(display_name, "mard_221")

    def _current_palette(self):
        return self._display_to_internal(self.palette_var.get())

    def _read_params(self):
        def _num(text, default, lo, hi):
            try:
                v = int(str(text).strip())
            except (TypeError, ValueError):
                v = default
            return max(lo, min(hi, v))

        w = _num(self.entry_w.get(), 50, 1, MAX_GRID_SIZE)
        h = _num(self.entry_h.get(), 50, 1, MAX_GRID_SIZE)
        cell_px = _num(self.cell_px_var.get(), 60, 16, 160)
        show_grid = self.show_grid_var.get()
        show_labels = self.show_labels_var.get()
        show_legend = self.show_legend_var.get()
        try:
            grid_color = self.hex_to_rgb(self.grid_color_var.get())
        except ValueError:
            self.lbl_status.config(text="⚠️ 网格颜色无效，已用灰色", style="Status.Warn.TLabel")
            grid_color = DEFAULT_GRID_RGB
        return w, h, cell_px, show_grid, show_labels, show_legend, grid_color

    def _trigger_preview(self):
        if self.is_processing:
            self._pending_regenerate = True
            return
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(800, self.generate_preview)

    def _setup_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            return
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')):
                self._load_image_file(f)
                break

    def _load_image_file(self, file_path):
        try:
            img = Image.open(file_path)
            img.load()
        except Exception:
            messagebox.showerror("错误", "无法打开该图片文件")
            return
        self._save_current_state()
        self._replace_original_image(img)
        self.selected_file = file_path
        self.lbl_file.config(text=os.path.basename(file_path), foreground="black")
        orig_w, orig_h = img.size
        suggested_w = min(max(30, orig_w // 20), 80)
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(suggested_w))
        self._calculate_dimension('w')
        self._update_cm_hint()
        self.generate_preview()

    def select_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp *.webp *.gif")])
        if not file_path:
            return
        self._load_image_file(file_path)

    def _generate_chart(self, show_finished=True, cancel_callback=None):
        """按当前参数生成图纸，返回 GenerateResult 或 None"""
        w, h, cell_px, show_grid, show_labels, show_legend, grid_color = self._read_params()
        return self.processor.process_image(
            self.selected_file, w, h, cell_size=cell_px,
            show_grid=show_grid, grid_color=grid_color,
            palette_name=self._current_palette(), show_color_legend=show_legend,
            show_row_col_labels=show_labels, show_finished=show_finished,
            fit_box=(self.ratio_var.get() == RATIO_FIT_BOX),
            exact_grid=(self.ratio_var.get() in RATIO_FIXED),
            save=False, cancel_callback=cancel_callback)

    def _apply_result(self, result):
        """把生成结果应用到界面状态与预览"""
        self._replace_processed_image(result.chart, result.finished)
        self.last_cell_size = result.cell_size
        self.current_save_path = result.save_path
        self.color_stats = result.color_stats
        self.total_beads = result.total_beads
        self._render_preview()
        self._update_color_stats_display(result.total_beads, result.grid_w, result.grid_h)

    def generate_preview(self, confirm_big=False):
        if self.is_processing:
            return
        if not self.selected_file:
            self.lbl_status.config(text="⚠️ 请先选择图片！", style="Status.Warn.TLabel")
            return

        if confirm_big:
            w, h = self._grid_dims()
            if w * h > BIG_GRID_WARN:
                if not messagebox.askyesno(
                        "大图纸确认",
                        f"网格 {w}×{h} = {w * h} 颗豆子，生成可能需要较长时间。\n\n继续吗？"):
                    return

        self.is_processing = True
        self._pending_regenerate = False
        self.lbl_status.config(text="⏳ 正在处理...", style="Status.Busy.TLabel")
        self.root.update_idletasks()

        try:
            result = self._generate_chart()
            if result is not None:
                self._apply_result(result)
                self.lbl_status.config(
                    text=f"✅ 完成！{result.chart.width}x{result.chart.height} | 网格：{result.grid_w}x{result.grid_h}",
                    style="Status.OK.TLabel")
            else:
                self.lbl_status.config(text="❌ 处理失败", style="Status.Err.TLabel")
        finally:
            self.is_processing = False
            if self._pending_regenerate and self.selected_file:
                self._pending_regenerate = False
                self.preview_timer = self.root.after(50, self.generate_preview)

    def save_to_history(self):
        if self.is_processing:
            return
        if not self.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        w, h = self._grid_dims()
        default_name = f"perler_{w}x{h}_{self._current_palette()}.png"
        save_path = filedialog.asksaveasfilename(
            title="保存拼豆图纸",
            defaultextension=".png",
            initialdir=OUTPUT_DIR,
            initialfile=default_name,
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.lbl_status.config(text="⏳ 正在生成...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            result.chart.save(save_path)
            self._apply_result(result)
            w, h, cell_px, show_grid, _, _, grid_color = self._read_params()
            self.history_mgr.add_record(self.selected_file, save_path, w, h,
                                        self.ratio_var.get(), cell_px,
                                        show_grid, grid_color, self.palette_var.get(),
                                        self.show_labels_var.get())
            self.refresh_history_list()

            file_size = os.path.getsize(save_path) / 1024
            self._show_result_dialog(
                "保存成功",
                f"图片已保存至：\n{save_path}\n\n"
                f"尺寸：{result.chart.width}x{result.chart.height} 像素\n"
                f"文件大小：{file_size:.1f} KB\n使用色卡：{self.palette_var.get()}\n"
                f"总耗材：{result.total_beads} 颗豆子",
                save_path)
            if self._closing:
                return
            self.lbl_status.config(text="💾 已保存到历史记录", style="Status.OK.TLabel")
        finally:
            self.is_processing = False

    def export_png(self):
        if self.is_processing:
            return
        if not self.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        w, h = self._grid_dims()
        default_name = f"perler_{w}x{h}_{self._current_palette()}.png"
        save_path = filedialog.asksaveasfilename(
            title="导出 PNG",
            defaultextension=".png",
            initialdir=OUTPUT_DIR,
            initialfile=default_name,
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.lbl_status.config(text="⏳ 正在导出 PNG...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            result.chart.save(save_path)
            self._apply_result(result)
            file_size = os.path.getsize(save_path) / 1024
            self.lbl_status.config(text=f"🖼️ PNG 已导出：{os.path.basename(save_path)}",
                                   style="Status.OK.TLabel")
            self._show_result_dialog(
                "导出成功",
                f"PNG 已导出至：\n{save_path}\n\n"
                f"尺寸：{result.chart.width}x{result.chart.height} 像素\n"
                f"文件大小：{file_size:.1f} KB",
                save_path)
            if self._closing:
                return
        finally:
            self.is_processing = False

    def export_pdf(self):
        if self.is_processing:
            return
        if not self.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        mode = self._ask_pdf_mode()
        if mode is None:
            return

        w, h = self._grid_dims()
        default_name = f"perler_{w}x{h}_{self._current_palette()}.pdf"
        save_path = filedialog.asksaveasfilename(
            title="导出 PDF",
            defaultextension=".pdf",
            initialdir=OUTPUT_DIR,
            initialfile=default_name,
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.lbl_status.config(text="⏳ 正在导出 PDF...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            self.processor.export_pdf(result.chart, save_path, mode, result.cell_size)
            self._apply_result(result)
            file_size = os.path.getsize(save_path) / 1024
            self.lbl_status.config(text=f"📄 PDF 已导出：{os.path.basename(save_path)}",
                                   style="Status.OK.TLabel")
            self._show_result_dialog(
                "导出成功",
                f"PDF 已导出至：\n{save_path}\n\n文件大小：{file_size:.1f} KB\n"
                f"总耗材：{result.total_beads} 颗豆子",
                save_path)
            if self._closing:
                return
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            self.lbl_status.config(text=f"❌ 导出失败：{e}", style="Status.Err.TLabel")
        finally:
            self.is_processing = False

    def _grid_dims(self):
        params = self._read_params()
        return params[0], params[1]

    def _ask_pdf_mode(self):
        win = tk.Toplevel(self.root)
        win.title("PDF 导出模式")
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()
        self._modal_active = True

        result = {"mode": None}

        ttk.Label(win, text="选择 PDF 导出模式：", font=ui_font(11, bold=True)).pack(
            anchor=tk.W, padx=20, pady=(15, 5))
        var = tk.StringVar(value="a4")
        ttk.Radiobutton(win, text="适应 A4 单页（整图缩放到一页）", value="a4", variable=var).pack(
            anchor=tk.W, padx=25, pady=5)
        ttk.Radiobutton(win, text="1:1 实物大小多页（5mm/颗，自动切块拼接）", value="1x1", variable=var).pack(
            anchor=tk.W, padx=25, pady=5)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=15)

        def close(mode):
            result["mode"] = mode
            self._modal_active = False
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()

        ttk.Button(btn_frame, text="确定", command=lambda: close(var.get()),
                   style="Accent.TButton", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: close(None), width=10).pack(side=tk.LEFT, padx=5)

        self._center_toplevel(win)
        self.root.wait_window(win)
        self._modal_active = False
        if self._closing:
            return None
        return result["mode"]

    # ---------- 预览缩放 ----------
    def update_zoom(self, val):
        pct = int(float(val))
        self.lbl_zoom_val.config(text=f"{pct}%")
        if not self.fit_var.get():
            self._schedule_render(40)

    def _toggle_fit(self):
        if self.fit_var.get():
            self.lbl_zoom_val.config(text="适应窗口")
        else:
            self.lbl_zoom_val.config(text=f"{self.zoom_var.get()}%")
        self._schedule_render(40)

    def _on_preview_wheel(self, event):
        if not self.processed_image:
            return
        if is_mac():
            step = event.delta
        else:
            step = event.delta / 120
        if step == 0:
            return
        self._zoom_by(int(step * 10))

    def _on_preview_resize(self, event):
        if self.fit_var.get() and self.processed_image:
            self._schedule_render(100)

    def _schedule_render(self, delay=60):
        if self.render_timer:
            self.root.after_cancel(self.render_timer)
        self.render_timer = self.root.after(delay, self._render_preview)

    def _render_preview(self):
        if not self.processed_image:
            return
        if self.finished_var.get() and self.finished_image is not None:
            img = self.finished_image
        else:
            img = self.processed_image
        area = self.canvas_frame
        aw = area.winfo_width()
        ah = area.winfo_height()

        if aw > 10 and ah > 10:
            if self.fit_var.get():
                scale = min(aw / img.width, ah / img.height)
                nw = max(1, int(img.width * scale))
                nh = max(1, int(img.height * scale))
            else:
                pct = self.zoom_var.get() / 100.0
                nw = max(1, int(img.width * pct))
                nh = max(1, int(img.height * pct))
        else:
            nw, nh = img.width, img.height

        max_dim = MAX_RENDER_DIM
        if nw > max_dim or nh > max_dim:
            s = min(max_dim / nw, max_dim / nh)
            nw = max(1, int(nw * s))
            nh = max(1, int(nh * s))

        display = img.resize((nw, nh), Image.NEAREST)
        self._set_photo(display)

    def _set_photo(self, img):
        old = self.photo_ref
        self.photo_ref = ImageTk.PhotoImage(img)
        try:
            old.blank()
        except Exception:
            pass
        canvas = self.preview_canvas
        canvas.delete("all")
        self._drag_start = None
        self._img_w = img.width
        self._img_h = img.height
        self._img_item = canvas.create_image(0, 0, image=self.photo_ref, anchor=tk.NW)
        self._center_preview()

    def _center_preview(self):
        if self._img_item is None:
            return
        canvas = self.preview_canvas
        cw = max(1, canvas.winfo_width())
        ch = max(1, canvas.winfo_height())
        self._ox = max(0, (cw - self._img_w) // 2)
        self._oy = max(0, (ch - self._img_h) // 2)
        canvas.coords(self._img_item, self._ox, self._oy)

    def _clamp_offset(self, ox, oy):
        canvas = self.preview_canvas
        cw = max(1, canvas.winfo_width())
        ch = max(1, canvas.winfo_height())
        if self._img_w <= cw:
            ox = (cw - self._img_w) // 2
        else:
            ox = max(cw - self._img_w, min(0, ox))
        if self._img_h <= ch:
            oy = (ch - self._img_h) // 2
        else:
            oy = max(ch - self._img_h, min(0, oy))
        return ox, oy

    def _on_preview_press(self, event):
        if self._img_item is None:
            return
        self._drag_start = (event.x, event.y, self._ox, self._oy)

    def _on_preview_drag(self, event):
        if self._drag_start is None or self._img_item is None:
            return
        sx, sy, ox0, oy0 = self._drag_start
        ox, oy = self._clamp_offset(ox0 + (event.x - sx), oy0 + (event.y - sy))
        self._ox, self._oy = ox, oy
        self.preview_canvas.coords(self._img_item, ox, oy)

    def _on_preview_release(self, event):
        self._drag_start = None

    def _on_preview_double_click(self, event):
        if self._img_item is None:
            return
        self._center_preview()

    def _show_preview_placeholder(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        self._img_item = None
        canvas.create_text(12, 12, anchor=tk.NW, text="请选择图片并生成预览",
                           fill="#888888", font=ui_font(11))

    # ---------- 图片资源管理（防内存泄漏） ----------
    def _replace_original_image(self, new_img):
        old = self.original_image
        self.original_image = new_img
        if old is not None and old is not new_img:
            try:
                old.close()
            except Exception:
                pass

    def _replace_processed_image(self, new_img, new_finished=None):
        old = self.processed_image
        old_f = self.finished_image
        self.processed_image = new_img
        self.finished_image = new_finished
        if old is not None and old is not new_img:
            try:
                old.close()
            except Exception:
                pass
        if old_f is not None and old_f is not new_finished:
            try:
                old_f.close()
            except Exception:
                pass

    # ---------- 颜色统计 ----------
    def _update_color_stats_display(self, total_beads=0, grid_w=0, grid_h=0):
        if not self.color_stats:
            self.lbl_color_stats.config(text="生成后显示", foreground="gray")
            return
        text = ""
        sorted_stats = sorted(self.color_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        for code, info in sorted_stats[:10]:
            text += f"● {info['code']} {info['name']}: {info['count']}颗\n"
        if len(self.color_stats) > 10:
            text += f"... 共 {len(self.color_stats)} 种颜色\n"
        text += f"\n总计：{total_beads} 颗豆子 | 网格：{grid_w}×{grid_h}"
        self.lbl_color_stats.config(text=text, foreground="black")

    def hex_to_rgb(self, hex_color):
        text = str(hex_color).strip().lstrip('#')
        if len(text) != 6:
            raise ValueError(f"无效颜色值：{hex_color}")
        try:
            r = int(text[0:2], 16)
            g = int(text[2:4], 16)
            b = int(text[4:6], 16)
        except ValueError:
            raise ValueError(f"无效颜色值：{hex_color}")
        return (r, g, b)

    def _hex_to_rgb_safe(self, hex_color):
        try:
            return self.hex_to_rgb(hex_color)
        except ValueError:
            return DEFAULT_GRID_RGB

    # ---------- 批量队列 ----------
    def enqueue_item(self):
        if not self.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return
        w, h, cell_px, show_grid, show_labels, show_legend, grid_color = self._read_params()
        item = {
            'image_path': self.selected_file,
            'width': w, 'height': h,
            'ratio': self.ratio_var.get(),
            'cell_px': cell_px,
            'show_grid': show_grid, 'show_labels': show_labels, 'show_legend': show_legend,
            'grid_color': self.grid_color_var.get(),
            'palette': self.palette_var.get(),
            'format': self.queue_format_var.get(),
        }
        self.queue_items.append(item)
        save_queue(self.queue_items)
        self.refresh_queue_list()
        self.lbl_queue_status.config(text=f"队列共 {len(self.queue_items)} 项", foreground="black")

    def _make_thumb(self, path):
        if path in self._thumb_cache:
            return self._thumb_cache[path]
        try:
            img = Image.open(path)
            img.thumbnail((48, 48))
            photo = ImageTk.PhotoImage(img)
            img.close()
            self._thumb_cache[path] = photo
            return photo
        except Exception:
            return None

    def refresh_queue_list(self):
        self.queue_tree.delete(*self.queue_tree.get_children())
        self._queue_thumbs = []
        for item in self.queue_items:
            thumb = self._make_thumb(item['image_path'])
            self._queue_thumbs.append(thumb)
            info = f"[{item['format']}] {item['width']}x{item['height']}"
            self.queue_tree.insert("", tk.END, text=os.path.basename(item['image_path']),
                                   values=(thumb, info))

    def remove_selected_queue(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要移除的队列项")
            return
        index = self.queue_tree.index(sel[0])
        self.queue_items.pop(index)
        save_queue(self.queue_items)
        self.refresh_queue_list()
        self.lbl_queue_status.config(text=f"队列共 {len(self.queue_items)} 项", foreground="black")

    def clear_queue(self):
        if not self.queue_items:
            return
        self.queue_items.clear()
        save_queue(self.queue_items)
        self.refresh_queue_list()
        self.progress.config(value=0)
        self.lbl_queue_status.config(text="队列为空", foreground="gray")

    def _cancel_queue(self):
        self._queue_cancel = True

    def _unique_path(self, directory, base, ext):
        path = os.path.join(directory, f"{base}.{ext}")
        i = 2
        while os.path.exists(path):
            path = os.path.join(directory, f"{base}_{i}.{ext}")
            i += 1
        return path

    def process_queue(self):
        if self.is_processing:
            return
        if not self.queue_items:
            messagebox.showwarning("提示", "队列为空，请先加入项目")
            return

        out_dir = filedialog.askdirectory(title="选择批量导出目录", initialdir=OUTPUT_DIR)
        if not out_dir:
            return

        self.is_processing = True
        self._queue_cancel = False
        self.btn_queue_start.config(state=tk.DISABLED)
        self.btn_queue_cancel.config(state=tk.NORMAL)
        items = list(self.queue_items)
        total = len(items)
        success = []
        failed = []
        cancelled = 0
        self.progress.config(maximum=total, value=0)
        self.lbl_queue_status.config(text="⏳ 开始批量处理...", style="Status.Busy.TLabel")
        self.root.update()

        try:
            for idx, item in enumerate(items):
                if self._queue_cancel:
                    cancelled = total - idx
                    break
                fmt = item['format']
                if fmt == "PDF(A4适应)":
                    mode = "a4"
                    ext = "pdf"
                    mode_tag = "_a4"
                elif fmt == "PDF(1:1实物)":
                    mode = "1x1"
                    ext = "pdf"
                    mode_tag = "_1x1"
                else:
                    mode = None
                    ext = "png"
                    mode_tag = ""

                palette_internal = self._display_to_internal(item['palette'])
                grid_color = self._hex_to_rgb_safe(item['grid_color'])
                try:
                    cell_px = int(item.get('cell_px') or item.get('canvas_size') or 60)
                    grid_w = int(item.get('width') or 50)
                    grid_h = int(item.get('height') or 50)
                except (TypeError, ValueError):
                    cell_px, grid_w, grid_h = 60, 50, 50
                src_name = os.path.splitext(os.path.basename(item['image_path']))[0]
                base = f"perler_{src_name}_{grid_w}x{grid_h}_{palette_internal}{mode_tag}"
                out_path = self._unique_path(out_dir, base, ext)
                img = None
                try:
                    result = self.processor.process_image(
                        item['image_path'], grid_w, grid_h,
                        cell_size=cell_px,
                        show_grid=item.get('show_grid', True),
                        grid_color=grid_color, palette_name=palette_internal,
                        show_color_legend=item.get('show_legend', True),
                        show_row_col_labels=item.get('show_labels', True),
                        fit_box=(item.get('ratio') == RATIO_FIT_BOX),
                        exact_grid=(item.get('ratio') in RATIO_FIXED),
                        save=False, cancel_callback=lambda: self._queue_cancel)
                    if result is None:
                        if self._queue_cancel:
                            cancelled = total - idx
                            break
                        raise RuntimeError("生成失败")
                    if self._queue_cancel:
                        cancelled = total - idx
                        break
                    img = result.chart
                    if mode:
                        self.processor.export_pdf(img, out_path, mode, result.cell_size)
                    else:
                        img.save(out_path)
                    success.append(out_path)
                    self.history_mgr.add_record(item['image_path'], out_path,
                                                grid_w, grid_h,
                                                item.get('ratio', RATIO_ORIGINAL),
                                                cell_px,
                                                item.get('show_grid', True),
                                                item.get('grid_color', DEFAULT_GRID_COLOR),
                                                item.get('palette', 'MARD 221 色'),
                                                item.get('show_labels', True))
                except Exception as e:
                    failed.append((os.path.basename(item['image_path']), str(e)))
                finally:
                    if img is not None:
                        try:
                            img.close()
                        except Exception:
                            pass
                self.progress.config(value=idx + 1)
                self.lbl_queue_status.config(
                    text=f"⏳ 处理中 {idx + 1}/{total}：{os.path.basename(out_path)}", style="Status.Busy.TLabel")
                self.root.update()
        finally:
            self.refresh_history_list()
            self.progress.config(value=min(idx + 1, total) if cancelled else total)
            self.btn_queue_start.config(state=tk.NORMAL)
            self.btn_queue_cancel.config(state=tk.DISABLED)
            self.is_processing = False
            self._queue_cancel = False

        if cancelled:
            self.lbl_queue_status.config(
                text=f"⏹ 已取消：成功 {len(success)}，失败 {len(failed)}，剩余 {cancelled}",
                style="Status.Warn.TLabel")
            msg = f"批量处理已取消\n\n✅ 成功 {len(success)} 项\n❌ 失败 {len(failed)} 项\n⏹ 剩余 {cancelled} 项未处理"
            if failed:
                msg += "\n\n失败明细：\n" + "\n".join(f"{name}: {err}" for name, err in failed)
            messagebox.showwarning("批量已取消", msg)
        elif failed:
            self.lbl_queue_status.config(
                text=f"⚠️ 完成：成功 {len(success)}，失败 {len(failed)}", style="Status.Warn.TLabel")
            msg = f"批量处理完成\n\n✅ 成功 {len(success)} 项：\n" + "\n".join(success)
            msg += "\n\n❌ 失败 " + str(len(failed)) + " 项：\n" + "\n".join(
                f"{name}: {err}" for name, err in failed)
            messagebox.showwarning("批量完成（有失败）", msg)
        else:
            self.lbl_queue_status.config(
                text=f"✅ 批量完成：成功 {len(success)} 项", style="Status.OK.TLabel")
            messagebox.showinfo("批量完成", f"全部 {len(success)} 项导出成功：\n{out_dir}")

    # ---------- 历史记录 ----------
    def refresh_history_list(self):
        self.list_history.delete(0, tk.END)
        for i, record in enumerate(self.history_mgr.get_list()):
            text = f"[{i}] {record.get('time', '?')} - {record.get('width', '?')}x{record.get('height', '?')} ({record.get('palette', '?')})"
            self.list_history.insert(tk.END, text)

    def load_history_item(self, event):
        self.load_selected_history()

    def load_selected_history(self):
        selection = self.list_history.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一条历史记录")
            return
        index = selection[0]
        record = self.history_mgr.get_record(index)
        if not record:
            return
        if not os.path.exists(record.get('image_path', '')):
            messagebox.showerror("错误", "原图片已不存在")
            return

        self._save_current_state()
        self.selected_file = record['image_path']
        self.lbl_file.config(text=os.path.basename(record['image_path']), foreground="black")
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(record['width']))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(record['height']))
        self.ratio_var.set(record.get('ratio', RATIO_ORIGINAL))
        self.cell_px_var.set(str(record.get('output_size', 60)))
        self.show_grid_var.set(record.get('show_grid', True))
        self.show_labels_var.set(record.get('show_labels', True))
        grid_color = record.get('grid_color', DEFAULT_GRID_COLOR)
        if isinstance(grid_color, str) and grid_color.startswith('#'):
            self.grid_color_var.set(grid_color)
        self.palette_var.set(record.get('palette', 'MARD 221 色'))
        self._update_palette_info()
        try:
            img = Image.open(record['image_path'])
            img.load()
            self._replace_original_image(img)
        except Exception:
            self._replace_original_image(None)
        self.lbl_status.config(text=f"📋 已加载历史 [{index}]，自动生成预览...", style="Status.Busy.TLabel")
        self.generate_preview()

    def delete_selected_history(self):
        selection = self.list_history.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一条历史记录")
            return
        index = selection[0]
        if messagebox.askyesno("确认", "确定要删除这条历史记录吗？"):
            self.history_mgr.delete_record(index)
            self.refresh_history_list()
            self.lbl_status.config(text="🗑️ 已删除历史记录", style="Status.Warn.TLabel")

    def clear_history(self):
        if messagebox.askyesno("确认", "确定要清除所有历史记录吗？\n此操作不可恢复！"):
            self.history_mgr.clear_history()
            self.refresh_history_list()
            self.lbl_status.config(text="🗑️ 历史记录已清空", style="Status.Warn.TLabel")
