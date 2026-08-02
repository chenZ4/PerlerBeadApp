import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image
from core.colors import get_palette, PALETTE_OPTIONS
from ui.fonts import is_mac, ui_font, mono_font


class ColorChartWindow:
    """色卡预览窗口 - 已修复自动刷新卡顿问题"""

    def __init__(self, parent, palette_name="mard_221"):
        self.parent = parent
        self.palette_name = palette_name
        self.window = tk.Toplevel(parent)
        self.window.title("🎨 拼豆色卡预览")
        self.window.geometry("1400x900")
        self.window.minsize(1300, 750)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self.palette = get_palette(palette_name)
        self.filtered_colors = []
        self.current_filter = ""
        self.group_expanded = {}

        # 卡片尺寸
        self.card_width = 160
        self.card_height = 170
        self.color_preview_height = 75

        # 🔧 关键修复：添加加载标志，防止重复加载
        self._is_loading = False
        self._load_completed = False
        self._last_cols = 0
        self._search_timer = None

        self._setup_ui()
        self._load_colors()
        self._load_completed = True
        self._last_cols = self._calculate_cols()

    def _on_close(self):
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()

    def _get_palette_display_name(self):
        for display, internal in PALETTE_OPTIONS:
            if internal == self.palette_name:
                return display
        return self.palette_name

    def _setup_ui(self):
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=tk.YES)

        self._create_header(main_frame)
        self._create_scrollable_area(main_frame)
        self._create_footer(main_frame)

    def _create_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 15))

        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)

        ttk.Label(title_frame, text=f"🎨 {self._get_palette_display_name()}",
                  font=ui_font(16, bold=True), foreground="#0078D4").pack(anchor=tk.W)

        self.lbl_stats = ttk.Label(title_frame, text="", font=ui_font(10), foreground="#666")
        self.lbl_stats.pack(anchor=tk.W, pady=(5, 0))

        # 色卡切换
        palette_frame = ttk.Frame(header)
        palette_frame.pack(side=tk.LEFT, padx=(30, 0))
        ttk.Label(palette_frame, text="色卡:", font=ui_font(10)).pack(side=tk.LEFT)
        self.palette_combo = ttk.Combobox(palette_frame, values=[n for n, _ in PALETTE_OPTIONS],
                                          state="readonly", width=15)
        self.palette_combo.set(self._get_palette_display_name())
        self.palette_combo.pack(side=tk.LEFT, padx=5)
        self.palette_combo.bind("<<ComboboxSelected>>", self._on_palette_change)

        # 搜索框
        control_frame = ttk.Frame(header)
        control_frame.pack(side=tk.RIGHT)

        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=25)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self._on_search)
        ttk.Button(search_frame, text="✕", width=3, command=self._clear_search).pack(side=tk.LEFT)

        # 操作按钮
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side=tk.LEFT, padx=(15, 0))
        ttk.Button(btn_frame, text="💾 导出 CSV", command=self._export_csv).pack(side=tk.LEFT, padx=3)

    def _create_scrollable_area(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=tk.YES)

        self.canvas = tk.Canvas(container, highlightthickness=0, bg="#F5F5F5")
        v_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)

        self.scroll_frame = ttk.Frame(self.canvas)
        # 🔧 关键修复：只监听 scroll_frame 的 Configure，不监听 window
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self._canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.configure(yscrollcommand=v_scroll.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 🔧 关键修复：只绑定 canvas 的滚轮，不用 bind_all
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def _on_mousewheel(self, event):
        if is_mac():
            step = int(-event.delta)
        else:
            step = int(-(event.delta / 120))
        self.canvas.yview_scroll(step, "units")

    def _on_canvas_resize(self, event=None):
        try:
            self.canvas.itemconfigure(self._canvas_window, width=event.width)
        except tk.TclError:
            return
        if self._load_completed and not self._is_loading:
            cols = self._calculate_cols()
            if cols != self._last_cols:
                self._last_cols = cols
                self._load_colors(self.current_filter)

    def _create_footer(self, parent):
        footer = ttk.Frame(parent)
        footer.pack(fill=tk.X, pady=(15, 0))

        self.status_label = ttk.Label(footer, text=f"✓ 已加载 {len(self.palette.colors)} 种颜色",
                                      font=ui_font(9), foreground="#666")
        self.status_label.pack(side=tk.LEFT)

    def _load_colors(self, filter_text=""):
        # 🔧 关键修复：防止重复加载
        if self._is_loading:
            return
        self._is_loading = True

        try:
            for widget in self.scroll_frame.winfo_children():
                widget.destroy()

            colors_data = []
            for i, (rgb, name, code) in enumerate(zip(self.palette.colors, self.palette.names, self.palette.codes)):
                hex_val = self.palette.hex_codes[i]
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
                               if ft in c['code'].lower() or ft in c['name'].lower() or ft in c['hex'].lower()]

            self.filtered_colors = colors_data
            self._update_stats(len(colors_data))

            groups = {}
            for c in colors_data:
                groups.setdefault(c['group'], []).append(c)

            if not groups:
                ttk.Label(self.scroll_frame, text="😕 未找到匹配的颜色",
                          font=ui_font(12), foreground="#999").pack(pady=50)
                return

            for group in sorted(groups.keys()):
                self._render_group(group, groups[group])
        finally:
            self._is_loading = False

    def _render_group(self, group_name, colors):
        header = ttk.Frame(self.scroll_frame, padding=(0, 15, 0, 5))
        header.pack(fill=tk.X)

        toggle_btn = ttk.Label(header, text="▼" if self.group_expanded.get(group_name, True) else "▶",
                               font=ui_font(11), cursor="hand2", foreground="#0078D4")
        toggle_btn.pack(side=tk.LEFT)
        toggle_btn.bind("<Button-1>", lambda e: self._toggle_group(group_name))

        ttk.Label(header, text=f"【{group_name}组】{len(colors)}色",
                  font=ui_font(12, bold=True), foreground="#333").pack(side=tk.LEFT, padx=5)

        if not self.group_expanded.get(group_name, True):
            return

        grid_frame = ttk.Frame(self.scroll_frame)
        grid_frame.pack(fill=tk.X, pady=5)

        cols = self._calculate_cols()

        for i, color in enumerate(colors):
            row, col = divmod(i, cols)
            if col == 0:
                row_frame = ttk.Frame(grid_frame)
                row_frame.pack(fill=tk.X)
            self._create_color_card(row_frame, color)

    def _create_color_card(self, parent, color_info):
        """创建单个色卡卡片"""
        card = tk.Frame(parent, width=self.card_width, height=self.card_height,
                        bg="#FFFFFF", relief="raised", borderwidth=1)
        card.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=tk.YES)
        card.pack_propagate(False)

        color_box = tk.Canvas(card, width=self.card_width - 20, height=self.color_preview_height,
                              bg=color_info['hex'], highlightthickness=2,
                              highlightbackground="#E0E0E0", cursor="hand2")
        color_box.pack(pady=(8, 5))

        def on_click(event, info=color_info):
            self._copy_to_clipboard(info)

        color_box.bind("<Button-1>", on_click)

        info_frame = tk.Frame(card, bg="#FFFFFF")
        info_frame.pack(fill=tk.BOTH, expand=tk.YES)

        top_row = tk.Frame(info_frame, bg="#FFFFFF")
        top_row.pack(fill=tk.X)

        code_label = tk.Label(top_row, text=color_info['code'],
                              font=mono_font(12, bold=True), fg="#333", bg="#FFFFFF", anchor=tk.W, width=5)
        code_label.pack(side=tk.LEFT)

        name = color_info['name'] if color_info['name'] else '—'
        name_label = tk.Label(top_row, text=name, font=ui_font(10),
                              fg="#666", bg="#FFFFFF", anchor=tk.W, wraplength=self.card_width - 60)
        name_label.pack(side=tk.LEFT, padx=(5, 0))

        rgb_text = f"RGB({color_info['rgb'][0]}, {color_info['rgb'][1]}, {color_info['rgb'][2]})"
        rgb_label = tk.Label(info_frame, text=rgb_text, font=mono_font(10),
                             fg="#0078D4", bg="#FFFFFF", anchor=tk.W)
        rgb_label.pack(fill=tk.X, pady=(3, 0))

        hex_label = tk.Label(info_frame, text=color_info['hex'].lower(),
                             font=mono_font(9), fg="#999", bg="#FFFFFF", anchor=tk.W)
        hex_label.pack(fill=tk.X, pady=(1, 0))

        def on_enter(e):
            card.configure(relief="solid", borderwidth=2, bg="#E8F4FD")
            info_frame.configure(bg="#E8F4FD")
            top_row.configure(bg="#E8F4FD")
            code_label.configure(bg="#E8F4FD")
            name_label.configure(bg="#E8F4FD")
            rgb_label.configure(bg="#E8F4FD")
            hex_label.configure(bg="#E8F4FD")

        def on_leave(e):
            card.configure(relief="raised", borderwidth=1, bg="#FFFFFF")
            info_frame.configure(bg="#FFFFFF")
            top_row.configure(bg="#FFFFFF")
            code_label.configure(bg="#FFFFFF")
            name_label.configure(bg="#FFFFFF")
            rgb_label.configure(bg="#FFFFFF")
            hex_label.configure(bg="#FFFFFF")

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    def _calculate_cols(self):
        try:
            width = self.scroll_frame.winfo_width()
            if width < 200:
                width = self.canvas.winfo_width()
            if width < 200:
                return 7
            cols = width // (self.card_width + 10)
            return max(6, min(cols, 9))
        except:
            return 7

    def _toggle_group(self, group_name):
        self.group_expanded[group_name] = not self.group_expanded.get(group_name, True)
        self._load_colors(self.current_filter)

    def _on_search(self, event=None):
        if self._search_timer:
            self.window.after_cancel(self._search_timer)
        self._search_timer = self.window.after(250, self._do_search)

    def _do_search(self):
        self.current_filter = self.search_var.get().strip()
        self._load_colors(self.current_filter)

    def _clear_search(self):
        self.search_var.set("")
        self.current_filter = ""
        if self._search_timer:
            self.window.after_cancel(self._search_timer)
        self._load_colors()

    def _on_palette_change(self, event=None):
        display_name = self.palette_combo.get()
        for display, internal in PALETTE_OPTIONS:
            if display == display_name:
                self.palette = get_palette(internal)
                self.palette_name = internal
                self.group_expanded = {}
                self._load_colors()
                self.window.title(f"🎨 {display_name}")
                break

    def _update_stats(self, count):
        total = len(self.palette.colors)
        self.lbl_stats.config(text=f"显示 {count}/{total} 色")
        self.status_label.config(text=f"✓ 显示 {count}/{total} 种颜色")

    def _copy_to_clipboard(self, color_info):
        name_text = color_info['name'] if color_info['name'] else ''
        text = f"{color_info['code']} {name_text} | RGB{color_info['rgb']} | {color_info['hex'].lower()}"
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.status_label.config(text=f"✓ 已复制：{color_info['code']}", foreground="#28a745")
            self.window.after(2000, lambda: self.status_label.config(
                text=f"✓ 显示 {len(self.filtered_colors)}/{len(self.palette.colors)} 种颜色", foreground="#666"))
        except Exception as e:
            messagebox.showerror("错误", f"复制失败：{e}")

    def _export_csv(self):
        from tkinter import filedialog
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        save_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV 文件", "*.csv")],
                                                 title="导出颜色数据")
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8-sig') as f:
                    f.write("色号，颜色名称，R,G,B,HEX\n")
                    for c in self.filtered_colors:
                        r, g, b = c['rgb']
                        f.write(f"{c['code']},{c['name']},{r},{g},{b},{c['hex'].lower()}\n")
                messagebox.showinfo("✓ 导出成功", f"已保存至:\n{save_path}")
            except Exception as e:
                messagebox.showerror("❌ 导出失败", str(e))
        try:
            if self.window.winfo_exists():
                self.window.grab_set()
        except tk.TclError:
            pass