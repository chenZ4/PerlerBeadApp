# ui/desktop_ui.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from core.processor import ImageProcessor
from core.history_manager import HistoryManager
from core.colors import PALETTE_OPTIONS, get_palette
import copy
import os


class DesktopUI:
    def __init__(self, root):
        self.root = root
        self.root.title("拼豆图纸生成器 Pro")

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

        self.preview_timer = None
        self.previous_states = []
        self.max_undo_steps = 10

        # 防止循环触发
        self.is_calculating = False

        self.setup_ui()

    def setup_ui(self):
        # --- 左侧控制面板 ---
        left_frame = ttk.Frame(self.root, padding="10", width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        left_frame.pack_propagate(False)

        canvas = tk.Canvas(left_frame, width=330)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # ===== 1. 图片选择 =====
        self._create_section_title("1. 图片源")
        self.btn_select = ttk.Button(self.scrollable_frame, text="📁 选择图片", command=self.select_image)
        self.btn_select.pack(fill=tk.X, pady=5)
        self.lbl_file = ttk.Label(self.scrollable_frame, text="未选择", foreground="gray", wraplength=300)
        self.lbl_file.pack(anchor=tk.W)

        # ===== 2. 网格设置 =====
        self._create_section_title("2. 网格设置")

        ttk.Label(self.scrollable_frame, text="画布比例:").pack(anchor=tk.W)
        self.ratio_var = tk.StringVar(value="原始比例")
        ratios = ["原始比例", "1:1 (正方形)", "4:3", "3:4", "16:9", "9:16", "自定义"]
        self.combo_ratio = ttk.Combobox(self.scrollable_frame, textvariable=self.ratio_var, values=ratios,
                                        state="readonly")
        self.combo_ratio.pack(fill=tk.X, pady=2)
        self.combo_ratio.bind("<<ComboboxSelected>>", self._on_ratio_change)

        frame_wh = ttk.Frame(self.scrollable_frame)
        frame_wh.pack(fill=tk.X, pady=5)

        ttk.Label(frame_wh, text="宽 (颗):").grid(row=0, column=0, padx=2)
        self.entry_w = ttk.Entry(frame_wh, width=6)
        self.entry_w.insert(0, "50")
        self.entry_w.grid(row=0, column=1, padx=2)
        # 绑定回车键 - 立即计算并生成
        self.entry_w.bind("<Return>", self._on_enter_press)
        # 绑定失去焦点 - 计算并预览
        self.entry_w.bind("<FocusOut>", lambda e: self._on_dimension_change('w'))

        ttk.Label(frame_wh, text="高 (颗):").grid(row=0, column=2, padx=2)
        self.entry_h = ttk.Entry(frame_wh, width=6)
        self.entry_h.insert(0, "50")
        self.entry_h.grid(row=0, column=3, padx=2)
        # 绑定回车键 - 立即计算并生成
        self.entry_h.bind("<Return>", self._on_enter_press)
        # 绑定失去焦点 - 计算并预览
        self.entry_h.bind("<FocusOut>", lambda e: self._on_dimension_change('h'))

        # ===== 3. 色卡选择 =====
        self._create_section_title("3. 色卡选择")

        ttk.Label(self.scrollable_frame, text="色卡方案:").pack(anchor=tk.W)
        self.palette_var = tk.StringVar(value="MARD 221 色")
        self.combo_palette = ttk.Combobox(self.scrollable_frame, textvariable=self.palette_var,
                                          values=[name for name, _ in PALETTE_OPTIONS], state="readonly")
        self.combo_palette.pack(fill=tk.X, pady=2)
        self.combo_palette.bind("<<ComboboxSelected>>", lambda e: self._trigger_preview())

        self.lbl_palette_info = ttk.Label(self.scrollable_frame, text="", foreground="blue", font=("Arial", 9))
        self.lbl_palette_info.pack(anchor=tk.W, pady=2)
        self._update_palette_info()

        # ===== 4. 画布设置 =====
        self._create_section_title("4. 画布设置")

        ttk.Label(self.scrollable_frame, text="画布尺寸 (像素):").pack(anchor=tk.W)
        self.canvas_size_var = tk.StringVar(value="1500")
        self.combo_canvas_size = ttk.Combobox(self.scrollable_frame, textvariable=self.canvas_size_var,
                                              values=["1000", "1500", "2000", "2500", "3000"],
                                              state="readonly")
        self.combo_canvas_size.pack(fill=tk.X, pady=2)
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
        frame_grid_color.pack(fill=tk.X, pady=2)
        ttk.Label(frame_grid_color, text="网格颜色:").pack(side=tk.LEFT)
        self.grid_color_var = tk.StringVar(value="#C8C8C8")
        self.entry_grid_color = ttk.Entry(frame_grid_color, textvariable=self.grid_color_var, width=10)
        self.entry_grid_color.pack(side=tk.LEFT, padx=5)
        self.entry_grid_color.bind("<KeyRelease>", lambda e: self._trigger_preview())

        # ===== 5. 操作按钮 =====
        self._create_section_title("5. 操作")

        frame_buttons = ttk.Frame(self.scrollable_frame)
        frame_buttons.pack(fill=tk.X, pady=5)

        self.btn_undo = ttk.Button(frame_buttons, text="↩️ 上一步", command=self.undo, width=10)
        self.btn_undo.pack(side=tk.LEFT, padx=2)
        self.btn_undo.config(state=tk.DISABLED)

        self.btn_generate = ttk.Button(frame_buttons, text="🔄 生成预览", command=self.generate_preview)
        self.btn_generate.pack(side=tk.LEFT, padx=2)

        self.btn_save = ttk.Button(self.scrollable_frame, text="💾 保存并添加到历史", command=self.save_to_history)
        self.btn_save.pack(fill=tk.X, pady=10)

        # ===== 6. 颜色统计 =====
        self._create_section_title("6. 颜色统计")
        self.lbl_color_stats = ttk.Label(self.scrollable_frame, text="生成后显示", foreground="gray",
                                         wraplength=300, justify=tk.LEFT)
        self.lbl_color_stats.pack(anchor=tk.W, pady=5)

        # ===== 7. 历史记录 =====
        self._create_section_title("7. 历史记录")

        frame_hist_btn = ttk.Frame(self.scrollable_frame)
        frame_hist_btn.pack(fill=tk.X, pady=2)
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

        # --- 右侧预览面板 ---
        right_frame = ttk.Frame(self.root, padding="10", relief=tk.SUNKEN, borderwidth=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_frame, text="🖼️ 实时预览", font=("Arial", 14, "bold")).pack()

        self.canvas_frame = ttk.Frame(right_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.lbl_preview = ttk.Label(self.canvas_frame, anchor=tk.CENTER, background="#eee")
        self.lbl_preview.pack(fill=tk.BOTH, expand=True)

        scale_frame = ttk.Frame(right_frame)
        scale_frame.pack(fill=tk.X, pady=5)
        ttk.Label(scale_frame, text="预览缩放:").pack(side=tk.LEFT)
        self.zoom_var = tk.IntVar(value=300)
        self.scale_zoom = ttk.Scale(scale_frame, from_=100, to=800, variable=self.zoom_var, orient=tk.HORIZONTAL,
                                    command=self.update_zoom)
        self.scale_zoom.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.lbl_zoom_val = ttk.Label(scale_frame, text="300px", width=6)
        self.lbl_zoom_val.pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(right_frame, text="✅ 就绪", foreground="green", font=("Arial", 10))
        self.lbl_status.pack()

    def _create_section_title(self, text):
        ttk.Label(self.scrollable_frame, text=text, font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(10, 5))

    def _save_current_state(self):
        state = {
            'ratio': self.ratio_var.get(),
            'width': self.entry_w.get(),
            'height': self.entry_h.get(),
            'palette': self.palette_var.get(),
            'canvas_size': self.canvas_size_var.get(),
            'show_grid': self.show_grid_var.get(),
            'show_legend': self.show_legend_var.get(),
            'grid_color': self.grid_color_var.get(),
            'selected_file': self.selected_file,
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

        self.lbl_status.config(text="↩️ 已撤销到上一步", foreground="orange")

    def _on_enter_press(self, event):
        """按回车键时立即计算另一边并生成预览"""
        self._save_current_state()

        # 判断是哪个输入框触发的
        widget = event.widget
        if widget == self.entry_w:
            self._calculate_dimension('w')
        elif widget == self.entry_h:
            self._calculate_dimension('h')

        # 直接生成，不防抖
        self.generate_preview()

    def _on_ratio_change(self, event=None):
        """比例改变时重新计算"""
        self._save_current_state()
        self._calculate_dimension('w')
        self._trigger_preview()

    def _on_dimension_change(self, source):
        """宽高变化时自动计算另一边"""
        if self.is_calculating:
            return
        self._calculate_dimension(source)
        self._trigger_preview()

    def _calculate_dimension(self, source):
        """核心计算函数 - 根据比例计算另一边"""
        if self.is_calculating:
            return

        self.is_calculating = True

        try:
            w_str = self.entry_w.get().strip()
            h_str = self.entry_h.get().strip()

            # 如果为空，使用默认值
            w = int(w_str) if w_str else 50
            h = int(h_str) if h_str else 50
        except:
            self.is_calculating = False
            return

        ratio = self.ratio_var.get()

        # 根据比例计算
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

        # 原始比例和自定义不自动计算

        self.is_calculating = False

    def _on_palette_change(self, event):
        self._save_current_state()
        self._update_palette_info()
        self._trigger_preview()

    def _update_palette_info(self):
        palette_name = self.palette_var.get()
        for display_name, internal_name in PALETTE_OPTIONS:
            if display_name == palette_name:
                palette = get_palette(internal_name)
                self.lbl_palette_info.config(text=f"共 {len(palette.colors)} 种颜色")
                break

    def _trigger_preview(self):
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(500, self.generate_preview)

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
        if not self.selected_file:
            self.lbl_status.config(text="⚠️ 请先选择图片！", foreground="orange")
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
            self.lbl_status.config(text=f"❌ 参数错误：{e}", foreground="red")
            return

        self.lbl_status.config(text="⏳ 正在处理...", foreground="blue")
        self.root.update()

        save_path, img_obj, color_stats = self.processor.process_image(
            self.selected_file, w, h,
            canvas_size=canvas_size,
            show_grid=show_grid,
            grid_color=grid_color,
            palette_name=palette_internal,
            show_color_legend=show_legend
        )

        if img_obj:
            self.processed_image = img_obj
            self.current_save_path = save_path
            self.color_stats = color_stats
            self.update_preview_display(img_obj)
            self._update_color_stats_display()

            self.lbl_status.config(text=f"✅ 预览完成！{img_obj.width}x{img_obj.height} | 网格：{w}x{h}",
                                   foreground="green")
        else:
            self.lbl_status.config(text="❌ 处理失败", foreground="red")

    def save_to_history(self):
        """保存并添加到历史记录（每次点击都重新生成）"""
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

        # 重新生成图片
        save_path, img_obj, color_stats = self.processor.process_image(
            self.selected_file, w, h,
            canvas_size=canvas_size,
            show_grid=show_grid,
            grid_color=grid_color,
            palette_name=palette_internal,
            show_color_legend=show_legend
        )

        if not img_obj:
            messagebox.showerror("错误", "生成失败")
            return

        self.processed_image = img_obj
        self.current_save_path = save_path
        self.color_stats = color_stats
        self.update_preview_display(img_obj)
        self._update_color_stats_display()

        # 添加到历史记录
        self.history_mgr.add_record(
            self.selected_file,
            save_path,
            w, h,
            self.ratio_var.get(),
            canvas_size,
            show_grid,
            grid_color,
            self.palette_var.get()
        )

        self.refresh_history_list()

        file_size = os.path.getsize(save_path) / 1024
        messagebox.showinfo("保存成功",
                            f"图片已保存至：\n{save_path}\n\n"
                            f"尺寸：{img_obj.width}x{img_obj.height} 像素\n"
                            f"文件大小：{file_size:.1f} KB\n"
                            f"使用色卡：{self.palette_var.get()}\n"
                            f"已添加到历史记录")

        self.lbl_status.config(text="💾 已保存到历史记录", foreground="green")

    def _update_color_stats_display(self):
        if not self.color_stats:
            self.lbl_color_stats.config(text="生成后显示", foreground="gray")
            return

        text = ""
        total = 0
        sorted_stats = sorted(self.color_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        for code, info in sorted_stats[:10]:
            text += f"● {info['code']} {info['name']}: {info['count']}颗\n"
            total += info['count']

        if len(self.color_stats) > 10:
            text += f"... 共 {len(self.color_stats)} 种颜色\n"
        text += f"总计：{total} 颗豆子"

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
        self.lbl_file.config(text=os.path.basename(record['image_path']), foreground="blue")

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
        if messagebox.askyesno("确认", "确定要清除所有历史记录吗？"):
            self.history_mgr.clear_history()
            self.refresh_history_list()
            self.lbl_status.config(text="🗑️ 历史记录已清空", foreground="orange")