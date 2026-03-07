# ui/color_chart_ui.py - 完整优化版
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw
from core.colors import get_palette, PALETTE_OPTIONS
import os


class ColorChartWindow:
    """专业色卡预览窗口 - 优化显示布局"""

    def __init__(self, parent, palette_name="mard_221"):
        self.parent = parent
        self.palette_name = palette_name
        self.window = tk.Toplevel(parent)
        self.window.title("🎨 拼豆色卡预览")
        self.window.geometry("1400x900")  # 增大默认窗口
        self.window.minsize(1300, 750)  # 设置最小尺寸
        self.window.transient(parent)
        self.window.grab_set()

        # 状态变量
        self.palette = get_palette(palette_name)
        self.filtered_colors = []
        self.current_filter = ""
        self.group_expanded = {}

        # 卡片尺寸 (确保内容完整显示)
        self.card_width = 160
        self.card_height = 170
        self.color_preview_height = 75

        self._setup_styles()
        self._setup_ui()
        self._load_colors()

    def _get_palette_display_name(self):
        """获取色卡显示名称"""
        for display, internal in PALETTE_OPTIONS:
            if internal == self.palette_name:
                return display
        return self.palette_name

    def _setup_styles(self):
        """配置 ttk 样式"""
        style = ttk.Style()
        style.configure("ColorCard.TFrame", background="#FFFFFF", relief="solid", borderwidth=1)
        style.configure("GroupHeader.TLabel", font=("Microsoft YaHei", 13, "bold"), foreground="#0078D4")
        style.configure("StatCard.TFrame", background="#F8F9FA", relief="solid", borderwidth=1)
        style.configure("Code.TLabel", font=("Consolas", 12, "bold"), foreground="#333")
        style.configure("Name.TLabel", font=("Microsoft YaHei", 10), foreground="#666")
        style.configure("RGB.TLabel", font=("Consolas", 10), foreground="#0078D4")
        style.configure("HEX.TLabel", font=("Consolas", 9), foreground="#999")

    def _setup_ui(self):
        """构建界面"""
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=tk.YES)

        # === 顶部栏：标题 + 搜索 + 工具 ===
        self._create_header(main_frame)

        # === 中部：可滚动色卡区域 ===
        self._create_scrollable_area(main_frame)

        # === 底部：状态栏 ===
        self._create_footer(main_frame)

    def _create_header(self, parent):
        """创建顶部控制栏"""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 15))

        # 左侧：标题 + 统计
        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)

        ttk.Label(title_frame, text=f"🎨 {self._get_palette_display_name()}",
                  font=("Microsoft YaHei", 16, "bold"), foreground="#0078D4").pack(anchor=tk.W)

        self.lbl_stats = ttk.Label(title_frame, text="", font=("Microsoft YaHei", 10), foreground="#666")
        self.lbl_stats.pack(anchor=tk.W, pady=(5, 0))

        # 中间：色卡切换
        palette_frame = ttk.Frame(header)
        palette_frame.pack(side=tk.LEFT, padx=(30, 0))
        ttk.Label(palette_frame, text="色卡:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.palette_combo = ttk.Combobox(palette_frame, values=[n for n, _ in PALETTE_OPTIONS],
                                          state="readonly", width=15)
        self.palette_combo.set(self._get_palette_display_name())
        self.palette_combo.pack(side=tk.LEFT, padx=5)
        self.palette_combo.bind("<<ComboboxSelected>>", self._on_palette_change)

        # 右侧：搜索 + 操作
        control_frame = ttk.Frame(header)
        control_frame.pack(side=tk.RIGHT)

        # 搜索框
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
        ttk.Button(btn_frame, text="🖼️ 导出图片", command=self._export_image).pack(side=tk.LEFT, padx=3)

    def _create_scrollable_area(self, parent):
        """创建可滚动的主内容区"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=tk.YES)

        self.canvas = tk.Canvas(container, highlightthickness=0, bg="#F5F5F5")
        v_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.canvas.xview)

        self.scroll_frame = ttk.Frame(self.canvas)
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        # 鼠标滚轮
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        # 窗口大小改变时重新计算列数
        self.window.bind("<Configure>", self._on_window_resize)

    def _create_footer(self, parent):
        """创建底部状态栏"""
        footer = ttk.Frame(parent)
        footer.pack(fill=tk.X, pady=(15, 0))

        self.status_label = ttk.Label(footer, text=f"✓ 已加载 {len(self.palette.colors)} 种颜色",
                                      font=("Microsoft YaHei", 9), foreground="#666")
        self.status_label.pack(side=tk.LEFT)

        ttk.Label(footer, text="💡 点击色块可复制信息 | 双击查看大图", font=("Microsoft YaHei", 9),
                  foreground="#999").pack(side=tk.RIGHT)

    def _load_colors(self, filter_text=""):
        """加载并渲染色卡"""
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        colors_data = []
        for i, (rgb, name, code) in enumerate(zip(self.palette.colors, self.palette.names, self.palette.codes)):
            hex_val = self.palette.hex_codes[i] if hasattr(self.palette, 'hex_codes') else '#000000'
            colors_data.append({
                'code': code.strip(),
                'name': name.strip() if name.strip() else '',
                'rgb': rgb,
                'hex': hex_val,
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
                      font=("Microsoft YaHei", 12), foreground="#999").pack(pady=50)
            return

        for group in sorted(groups.keys()):
            self._render_group(group, groups[group])

    def _render_group(self, group_name, colors):
        """渲染一个颜色分组"""
        header = ttk.Frame(self.scroll_frame, padding=(0, 15, 0, 5))
        header.pack(fill=tk.X)

        toggle_btn = ttk.Label(header, text="▼" if self.group_expanded.get(group_name, True) else "▶",
                               font=("Microsoft YaHei", 11), cursor="hand2", foreground="#0078D4")
        toggle_btn.pack(side=tk.LEFT)
        toggle_btn.bind("<Button-1>", lambda e: self._toggle_group(group_name))

        ttk.Label(header, text=f"【{group_name}组】{len(colors)}色",
                  font=("Microsoft YaHei", 12, "bold"), foreground="#333").pack(side=tk.LEFT, padx=5)

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
        """创建单个色卡卡片 - 优化布局"""
        card = ttk.Frame(parent, width=self.card_width, height=self.card_height,
                         style="ColorCard.TFrame", relief="raised", borderwidth=1)
        card.pack(side=tk.LEFT, padx=5, pady=5)
        card.pack_propagate(False)

        # === 颜色预览区 (占卡片 50% 高度) ===
        color_box = tk.Canvas(card, width=self.card_width - 20, height=self.color_preview_height,
                              bg=color_info['hex'], highlightthickness=2,
                              highlightbackground="#E0E0E0", cursor="hand2")
        color_box.pack(pady=(8, 5))

        def on_click(event, info=color_info):
            self._copy_to_clipboard(info)

        def on_double_click(event, info=color_info):
            self._show_color_detail(info)

        color_box.bind("<Button-1>", on_click)
        color_box.bind("<Double-Button-1>", on_double_click)

        # === 信息区 (占卡片 50% 高度) ===
        info_frame = ttk.Frame(card, padding=(6, 0))
        info_frame.pack(fill=tk.BOTH, expand=tk.YES)

        # 【第一行】色号 + 中文名 并列显示
        top_row = ttk.Frame(info_frame)
        top_row.pack(fill=tk.X)

        # 色号 (左侧，加粗)
        code_label = ttk.Label(top_row, text=color_info['code'],
                               style="Code.TLabel", anchor=tk.W, width=5)
        code_label.pack(side=tk.LEFT)

        # 中文名 (右侧，可能为空)
        name = color_info['name'] if color_info['name'] else '—'
        name_label = ttk.Label(top_row, text=name, style="Name.TLabel",
                               anchor=tk.W, wraplength=self.card_width - 60)
        name_label.pack(side=tk.LEFT, padx=(5, 0))

        # 【第二行】RGB 值
        rgb_text = f"RGB({color_info['rgb'][0]}, {color_info['rgb'][1]}, {color_info['rgb'][2]})"
        rgb_label = ttk.Label(info_frame, text=rgb_text, style="RGB.TLabel", anchor=tk.W)
        rgb_label.pack(fill=tk.X, pady=(3, 0))

        # 【第三行】HEX 值
        hex_label = ttk.Label(info_frame, text=color_info['hex'].lower(),
                              style="HEX.TLabel", anchor=tk.W)
        hex_label.pack(fill=tk.X, pady=(1, 0))

        # 悬停效果
        def on_enter(e):
            card.configure(relief="solid", borderwidth=2, background="#E8F4FD")

        def on_leave(e):
            card.configure(relief="raised", borderwidth=1, background="#FFFFFF")

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    def _calculate_cols(self):
        """根据窗口宽度计算每行列数"""
        try:
            width = self.window.winfo_width()
            if width < 1300:
                return 6
            elif width < 1500:
                return 7
            elif width < 1700:
                return 8
            else:
                return 9
        except:
            return 7

    def _on_window_resize(self, event=None):
        """窗口大小改变时重新渲染"""
        if event and event.widget == self.window:
            # 避免频繁重绘
            if hasattr(self, '_resize_timer'):
                self.window.after_cancel(self._resize_timer)
            self._resize_timer = self.window.after(300, self._reload_colors)

    def _reload_colors(self):
        """重新加载颜色"""
        self._load_colors(self.current_filter)

    def _toggle_group(self, group_name):
        """折叠/展开分组"""
        self.group_expanded[group_name] = not self.group_expanded.get(group_name, True)
        self._load_colors(self.current_filter)

    def _on_search(self, event=None):
        """搜索回调"""
        self.current_filter = self.search_var.get().strip()
        self._load_colors(self.current_filter)

    def _clear_search(self):
        """清除搜索"""
        self.search_var.set("")
        self.current_filter = ""
        self._load_colors()

    def _on_palette_change(self, event=None):
        """切换色卡方案"""
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
        """更新统计显示"""
        total = len(self.palette.colors)
        self.lbl_stats.config(text=f"显示 {count}/{total} 色")
        self.status_label.config(text=f"✓ 显示 {count}/{total} 种颜色")

    def _copy_to_clipboard(self, color_info):
        """复制色卡信息到剪贴板"""
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

    def _show_color_detail(self, color_info):
        """显示颜色详细信息弹窗"""
        detail_window = tk.Toplevel(self.window)
        detail_window.title(f"颜色详情 - {color_info['code']}")
        detail_window.geometry("450x350")
        detail_window.transient(self.window)
        detail_window.resizable(True, True)  # 允许拉伸

        frame = ttk.Frame(detail_window, padding=25)
        frame.pack(fill=tk.BOTH, expand=tk.YES)

        # 大色块
        color_canvas = tk.Canvas(frame, width=350, height=180, bg=color_info['hex'],
                                 highlightthickness=3, highlightbackground="#DDD")
        color_canvas.pack(pady=10)

        # 详细信息
        name_text = color_info['name'] if color_info['name'] else '无'
        info_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
色号：{color_info['code']}
名称：{name_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RGB: ({color_info['rgb'][0]}, {color_info['rgb'][1]}, {color_info['rgb'][2]})
HEX: {color_info['hex'].lower()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        ttk.Label(frame, text=info_text, font=("Consolas", 11),
                  justify=tk.LEFT, anchor=tk.W, lineheight=1.5).pack(pady=15)

        ttk.Button(frame, text="关闭", command=detail_window.destroy, width=15).pack(pady=10)

    def _export_csv(self):
        """导出为 CSV 文件"""
        from tkinter import filedialog
        save_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV 文件", "*.csv")],
                                                 title="导出颜色数据")
        if not save_path:
            return
        try:
            with open(save_path, 'w', encoding='utf-8-sig') as f:
                f.write("色号，颜色名称，R,G,B,HEX\n")
                for c in self.filtered_colors:
                    r, g, b = c['rgb']
                    f.write(f"{c['code']},{c['name']},{r},{g},{b},{c['hex'].lower()}\n")
            messagebox.showinfo("✓ 导出成功", f"已保存至:\n{save_path}")
        except Exception as e:
            messagebox.showerror("❌ 导出失败", str(e))

    def _export_image(self):
        """导出为图片"""
        from tkinter import filedialog
        save_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG 图片", "*.png")],
                                                 title="导出色卡图片")
        if not save_path:
            return
        try:
            cols = 8
            rows = (len(self.filtered_colors) + cols - 1) // cols
            cell_w, cell_h = 140, 130
            padding = 40
            img_w = cols * cell_w + padding * 2
            img_h = rows * cell_h + padding * 2 + 60

            img = Image.new('RGB', (img_w, img_h), '#FFFFFF')
            draw = ImageDraw.Draw(img)

            try:
                font_title = ImageFont.truetype("msyh.ttc", 18)
                font_code = ImageFont.truetype("consola.ttf", 13)
                font_name = ImageFont.truetype("msyh.ttc", 11)
                font_rgb = ImageFont.truetype("consola.ttf", 10)
            except:
                font_title = ImageFont.load_default()
                font_code = ImageFont.load_default()
                font_name = ImageFont.load_default()
                font_rgb = ImageFont.load_default()

            draw.text((padding, 15), f"{self._get_palette_display_name()} - {len(self.filtered_colors)}色",
                      fill='#333', font=font_title)

            for i, c in enumerate(self.filtered_colors):
                row, col = divmod(i, cols)
                x = padding + col * cell_w + 5
                y = 50 + row * cell_h + 5
                draw.rectangle([x, y, x + 120, y + 70], fill=c['rgb'], outline='#DDD', width=2)

                # 第一行：色号 + 名称
                name_txt = c['name'] if c['name'] else '—'
                draw.text((x + 5, y + 75), f"{c['code']}  {name_txt}", fill='#333', font=font_code)

                # 第二行：RGB
                rgb_txt = f"RGB{c['rgb']}"
                draw.text((x + 5, y + 95), rgb_txt, fill='#0078D4', font=font_rgb)

                # 第三行：HEX
                draw.text((x + 5, y + 110), c['hex'].lower(), fill='#999', font=font_rgb)

            img.save(save_path, quality=95)
            messagebox.showinfo("✓ 导出成功", f"已保存至:\n{save_path}")
        except Exception as e:
            messagebox.showerror("❌ 导出失败", str(e))