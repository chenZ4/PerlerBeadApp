# ui/desktop_ui.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from core.processor import ImageProcessor
from core.history_manager import HistoryManager
from core.colors import PALETTE_OPTIONS, get_palette
import os


class DesktopUI:
    def __init__(self, root):
        self.root = root
        self.root.title("拼豆图纸生成器")

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        window_w = int(self.screen_width * 0.85)
        window_h = int(self.screen_height * 0.85)
        self.root.geometry(f"{window_w}x{window_h}")

        self.processor = ImageProcessor()
        self.history_mgr = HistoryManager()

        self.original_image = None
        self.processed_image = None
        self.photo_ref = None
        self.selected_file = None
        self.current_save_path = None
        self.color_stats = {}
        self.total_beads = 0

        # 性能优化
        self.preview_timer = None
        self.is_processing = False
        self.previous_states = []
        self.max_undo_steps = 10
        self.is_calculating = False

        # 色卡窗口
        self.color_chart_window = None

        self.setup_ui()

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
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # ===== 1. 图片选择 =====
        self._create_section_title("📁 图片源")

        self.btn_select = ttk.Button(self.scrollable_frame, text="选择图片", command=self.select_image)
        self.btn_select.pack(fill=tk.X, pady=5)

        self.lbl_file = ttk.Label(self.scrollable_frame, text="未选择图片", foreground="gray", wraplength=300)
        self.lbl_file.pack(fill=tk.X, pady=5)

        # ===== 2. 网格设置 =====
        self._create_section_title("📐 网格设置")

        ttk.Label(self.scrollable_frame, text="画布比例:").pack(anchor=tk.W)
        self.ratio_var = tk.StringVar(value="原始比例")
        ratios = ["原始比例", "1:1 (正方形)", "4:3", "3:4", "16:9", "9:16", "自定义"]
        self.combo_ratio = ttk.Combobox(self.scrollable_frame, textvariable=self.ratio_var, values=ratios,
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

        # ===== 3. 色卡选择 =====
        self._create_section_title("🎨 色卡选择")

        ttk.Label(self.scrollable_frame, text="色卡方案:").pack(anchor=tk.W)
        self.palette_var = tk.StringVar(value="MARD 221 色")
        self.combo_palette = ttk.Combobox(self.scrollable_frame, textvariable=self.palette_var,
                                          values=[name for name, _ in PALETTE_OPTIONS], state="readonly")
        self.combo_palette.pack(fill=tk.X, pady=5)
        self.combo_palette.bind("<<ComboboxSelected>>", lambda e: self._trigger_preview())

        self.lbl_palette_info = ttk.Label(self.scrollable_frame, text="", foreground="blue")
        self.lbl_palette_info.pack(anchor=tk.W, pady=5)
        self._update_palette_info()

        # ===== 4. 画布设置 =====
        self._create_section_title("🖼️ 画布设置")

        ttk.Label(self.scrollable_frame, text="画布尺寸 (像素):").pack(anchor=tk.W)
        self.canvas_size_var = tk.StringVar(value="1500")
        self.combo_canvas_size = ttk.Combobox(self.scrollable_frame, textvariable=self.canvas_size_var,
                                              values=["1000", "1500", "2000", "2500", "3000"], state="readonly")
        self.combo_canvas_size.pack(fill=tk.X, pady=5)
        self.combo_canvas_size.bind("<<ComboboxSelected>>", lambda e: self._trigger_preview())

        self.show_grid_var = tk.BooleanVar(value=True)
        self.chk_grid = ttk.Checkbutton(self.scrollable_frame, text="显示网格线", variable=self.show_grid_var,
                                        command=lambda: self._trigger_preview())
        self.chk_grid.pack(anchor=tk.W, pady=5)

        self.show_legend_var = tk.BooleanVar(value=True)
        self.chk_legend = ttk.Checkbutton(self.scrollable_frame, text="显示颜色图例", variable=self.show_legend_var,
                                          command=lambda: self._trigger_preview())
        self.chk_legend.pack(anchor=tk.W, pady=5)

        frame_grid_color = ttk.Frame(self.scrollable_frame)
        frame_grid_color.pack(fill=tk.X, pady=5)
        ttk.Label(frame_grid_color, text="网格颜色:").pack(side=tk.LEFT)
        self.grid_color_var = tk.StringVar(value="#C8C8C8")
        self.entry_grid_color = ttk.Entry(frame_grid_color, textvariable=self.grid_color_var, width=12)
        self.entry_grid_color.pack(side=tk.LEFT, padx=10)
        self.entry_grid_color.bind("<KeyRelease>", lambda e: self._trigger_preview())

        # ===== 5. 操作按钮 =====
        self._create_section_title("🔧 操作")

        frame_buttons = ttk.Frame(self.scrollable_frame)
        frame_buttons.pack(fill=tk.X, pady=10)

        self.btn_undo = ttk.Button(frame_buttons, text="↩️ 撤销", command=self.undo, width=8)
        self.btn_undo.pack(side=tk.LEFT, padx=5)
        self.btn_undo.config(state=tk.DISABLED)

        self.btn_generate = ttk.Button(frame_buttons, text="🔄 生成", command=self.generate_preview, width=8)
        self.btn_generate.pack(side=tk.LEFT, padx=5)

        self.btn_save = ttk.Button(self.scrollable_frame, text="💾 保存并添加到历史", command=self.save_to_history)
        self.btn_save.pack(fill=tk.X, pady=15)

        # 色卡预览按钮
        self.btn_color_chart = ttk.Button(self.scrollable_frame, text="🎨 查看色卡", command=self.open_color_chart)
        self.btn_color_chart.pack(fill=tk.X, pady=5)

        # ===== 6. 颜色统计 =====
        self._create_section_title("📊 颜色统计")
        self.lbl_color_stats = ttk.Label(self.scrollable_frame, text="生成后显示", foreground="gray", wraplength=300)
        self.lbl_color_stats.pack(fill=tk.X, pady=5)

        # ===== 7. 历史记录 =====
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

        self.lbl_preview = ttk.Label(self.canvas_frame, anchor=tk.CENTER, background="#F3F3F3",
                                     text="请选择图片并生成预览")
        self.lbl_preview.pack(fill=tk.BOTH, expand=tk.YES)

        scale_frame = ttk.Frame(right_panel)
        scale_frame.pack(fill=tk.X, pady=10)

        ttk.Label(scale_frame, text="预览缩放:").pack(side=tk.LEFT)
        self.zoom_var = tk.IntVar(value=300)
        self.scale_zoom = ttk.Scale(scale_frame, from_=100, to=800, variable=self.zoom_var,
                                    orient=tk.HORIZONTAL, command=self.update_zoom)
        self.scale_zoom.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES, padx=10)
        self.lbl_zoom_val = ttk.Label(scale_frame, text="300px", width=8)
        self.lbl_zoom_val.pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(right_panel, text="✅ 就绪", foreground="green")
        self.lbl_status.pack(pady=10)

    def _create_section_title(self, text):
        ttk.Label(self.scrollable_frame, text=text, font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 8))
        ttk.Separator(self.scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))

    def _save_current_state(self):
        state = {
            'ratio': self.ratio_var.get(), 'width': self.entry_w.get(), 'height': self.entry_h.get(),
            'palette': self.palette_var.get(), 'canvas_size': self.canvas_size_var.get(),
            'show_grid': self.show_grid_var.get(), 'show_legend': self.show_legend_var.get(),
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
        self.canvas_size_var.set(state['canvas_size'])
        self.show_grid_var.set(state['show_grid'])
        self.show_legend_var.set(state['show_legend'])
        self.grid_color_var.set(state['grid_color'])
        if state['selected_file']:
            self.selected_file = state['selected_file']
            self.lbl_file.config(text=state['selected_file'].split("/")[-1], foreground="black")
        self._update_palette_info()
        self.btn_undo.config(state=tk.NORMAL if len(self.previous_states) > 0 else tk.DISABLED)
        self.generate_preview()
        self.lbl_status.config(text="↩️ 已撤销", foreground="orange")

    def open_color_chart(self):
        """打开色卡预览窗口"""
        if self.color_chart_window is None or not self.color_chart_window.window.winfo_exists():
            from ui.color_chart_ui import ColorChartWindow
            current_palette = self.palette_var.get()
            palette_internal = "mard_221"
            for display, internal in PALETTE_OPTIONS:
                if display == current_palette:
                    palette_internal = internal
                    break
            self.color_chart_window = ColorChartWindow(self.root, palette_name=palette_internal)
        else:
            self.color_chart_window.window.focus_force()
            self.color_chart_window.window.lift()
    def _on_enter_press(self, event):
        self._save_current_state()
        widget = event.widget
        if widget == self.entry_w:
            self._calculate_dimension('w')
        elif widget == self.entry_h:
            self._calculate_dimension('h')
        self.generate_preview()

    def _on_ratio_change(self, event=None):
        self._save_current_state()
        self._calculate_dimension('w')
        self._trigger_preview()

    def _on_dimension_change(self, source):
        if self.is_calculating:
            return
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
        except:
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
        palette_name = self.palette_var.get()
        for display_name, internal_name in PALETTE_OPTIONS:
            if display_name == palette_name:
                palette = get_palette(internal_name)
                self.lbl_palette_info.config(text=f"✓ 共 {len(palette.colors)} 种颜色")
                break

    def _trigger_preview(self):
        if self.is_processing:
            return
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(800, self.generate_preview)

    def select_image(self):
        self._save_current_state()
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.png *.jpeg")])
        if file_path:
            self.selected_file = file_path
            self.lbl_file.config(text=file_path.split("/")[-1], foreground="black")
            try:
                self.original_image = Image.open(file_path)
                if self.original_image:
                    orig_w, orig_h = self.original_image.size
                    suggested_w = min(max(30, orig_w // 20), 80)
                    self.entry_w.delete(0, tk.END)
                    self.entry_w.insert(0, str(suggested_w))
                    self._calculate_dimension('w')
                    self.generate_preview()
            except:
                self.original_image = None

    def generate_preview(self):
        if self.is_processing:
            return

        if not self.selected_file:
            self.lbl_status.config(text="⚠️ 请先选择图片！", foreground="orange")
            return

        self.is_processing = True

        try:
            w = int(self.entry_w.get()) if self.entry_w.get() else 50
            h = int(self.entry_h.get()) if self.entry_h.get() else 50
            canvas_size = int(self.canvas_size_var.get())
            show_grid = self.show_grid_var.get()
            show_legend = self.show_legend_var.get()
            grid_color = self.hex_to_rgb(self.grid_color_var.get())

            palette_internal = "mard_221"
            for display_name, internal_name in PALETTE_OPTIONS:
                if display_name == self.palette_var.get():
                    palette_internal = internal_name
                    break
        except Exception as e:
            self.lbl_status.config(text=f"❌ 参数错误：{e}", foreground="red")
            self.is_processing = False
            return

        self.lbl_status.config(text="⏳ 正在处理...", foreground="blue")
        self.root.update()

        result = self.processor.process_image(
            self.selected_file, w, h, canvas_size=canvas_size,
            show_grid=show_grid, grid_color=grid_color,
            palette_name=palette_internal, show_color_legend=show_legend
        )

        save_path, img_obj, color_stats, total_beads, grid_w, grid_h = result

        if img_obj:
            self.processed_image = img_obj
            self.current_save_path = save_path
            self.color_stats = color_stats
            self.total_beads = total_beads
            self.update_preview_display(img_obj)
            self._update_color_stats_display(total_beads, grid_w, grid_h)
            self.lbl_status.config(text=f"✅ 完成！{img_obj.width}x{img_obj.height} | 网格：{grid_w}x{grid_h}",
                                   foreground="green")
        else:
            self.lbl_status.config(text="❌ 处理失败", foreground="red")

        self.is_processing = False

    def save_to_history(self):
        if not self.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        try:
            w = int(self.entry_w.get()) if self.entry_w.get() else 50
            h = int(self.entry_h.get()) if self.entry_h.get() else 50
            canvas_size = int(self.canvas_size_var.get())
            show_grid = self.show_grid_var.get()
            show_legend = self.show_legend_var.get()
            grid_color = self.hex_to_rgb(self.grid_color_var.get())

            palette_internal = "mard_221"
            for display_name, internal_name in PALETTE_OPTIONS:
                if display_name == self.palette_var.get():
                    palette_internal = internal_name
                    break
        except Exception as e:
            messagebox.showerror("错误", f"参数错误：{e}")
            return

        self.lbl_status.config(text="⏳ 正在保存...", foreground="blue")
        self.root.update()

        result = self.processor.process_image(
            self.selected_file, w, h, canvas_size=canvas_size,
            show_grid=show_grid, grid_color=grid_color,
            palette_name=palette_internal, show_color_legend=show_legend
        )

        save_path, img_obj, color_stats, total_beads, grid_w, grid_h = result

        if not img_obj:
            messagebox.showerror("错误", "生成失败")
            return

        self.processed_image = img_obj
        self.current_save_path = save_path
        self.color_stats = color_stats
        self.total_beads = total_beads
        self.update_preview_display(img_obj)
        self._update_color_stats_display(total_beads, grid_w, grid_h)

        self.history_mgr.add_record(self.selected_file, save_path, w, h,
                                    self.ratio_var.get(), canvas_size,
                                    show_grid, grid_color, self.palette_var.get())
        self.refresh_history_list()

        file_size = os.path.getsize(save_path) / 1024
        messagebox.showinfo("保存成功",
                            f"图片已保存至：\n{save_path}\n\n尺寸：{img_obj.width}x{img_obj.height} 像素\n"
                            f"文件大小：{file_size:.1f} KB\n使用色卡：{self.palette_var.get()}\n"
                            f"总耗材：{total_beads} 颗豆子")

        self.lbl_status.config(text="💾 已保存到历史记录", foreground="green")

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
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def update_zoom(self, val):
        size = int(float(val))
        self.lbl_zoom_val.config(text=f"{size}px")
        if self.processed_image:
            display_img = self.processed_image.resize((size, size), resample=Image.NEAREST)
            self.update_preview_display(display_img)

    def update_preview_display(self, img):
        max_display = min(self.screen_width // 2, 800)
        if img.width > max_display:
            ratio = max_display / img.width
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), resample=Image.NEAREST)
        self.photo_ref = ImageTk.PhotoImage(img)
        self.lbl_preview.config(image=self.photo_ref, text="")

    def refresh_history_list(self):
        self.list_history.delete(0, tk.END)
        for i, record in enumerate(self.history_mgr.get_list()):
            text = f"[{i}] {record['time']} - {record['width']}x{record['height']} ({record['palette']})"
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
        if not os.path.exists(record['image_path']):
            messagebox.showerror("错误", f"原图片已不存在")
            return

        self._save_current_state()
        self.selected_file = record['image_path']
        self.lbl_file.config(text=os.path.basename(record['image_path']), foreground="black")
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(record['width']))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(record['height']))
        self.ratio_var.set(record.get('ratio', '原始比例'))
        self.canvas_size_var.set(str(record.get('output_size', 1500)))
        self.show_grid_var.set(record.get('show_grid', True))
        self.grid_color_var.set(record.get('grid_color', '#C8C8C8'))
        self.palette_var.set(record.get('palette', 'MARD 221 色'))
        self._update_palette_info()
        try:
            self.original_image = Image.open(record['image_path'])
        except:
            self.original_image = None
        self.lbl_status.config(text=f"📋 已加载历史 [{index}]，自动生成预览...", foreground="blue")
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
            self.lbl_status.config(text="🗑️ 已删除历史记录", foreground="orange")

    def clear_history(self):
        if messagebox.askyesno("确认", "确定要清除所有历史记录吗？\n此操作不可恢复！"):
            self.history_mgr.clear_history()
            self.refresh_history_list()
            self.lbl_status.config(text="🗑️ 历史记录已清空", foreground="orange")