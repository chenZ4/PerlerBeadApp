# ui/app_controller.py - 应用控制器（组合根：装配面板/状态/服务并路由事件）
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from core.history_manager import HistoryManager
from core.models import (
    BIG_GRID_WARN,
    DEFAULT_CELL_PX,
    DEFAULT_GRID_COLOR,
    DEFAULT_PALETTE,
    RATIO_ORIGINAL,
    BatchResult,
    GenerateParams,
    QueueItem,
)
from core.processor import ImageProcessor, OUTPUT_DIR
from core.services import BatchService, ChartService
from core.settings import SettingsStore
from core.version import APP_NAME, APP_VERSION
from ui.fonts import is_mac, ui_font
from ui.panels import HistoryPanel, PreviewPanel, QueuePanel, SettingsPanel, StatsPanel
from ui.state import AppState
from ui.theme import apply_theme


def _params_from_settings(settings):
    """设置 dict → GenerateParams（启动时初始化）"""
    return GenerateParams(
        ratio=settings.get('ratio', RATIO_ORIGINAL),
        palette=settings.get('palette', DEFAULT_PALETTE),
        cell_px=int(settings.get('cell_px', str(DEFAULT_CELL_PX)) or DEFAULT_CELL_PX),
        show_grid=bool(settings.get('show_grid', True)),
        show_labels=bool(settings.get('show_labels', True)),
        show_legend=bool(settings.get('show_legend', True)),
        grid_color=settings.get('grid_color', DEFAULT_GRID_COLOR),
    )


class AppController:
    """拼豆图纸 Tk 版控制器。

    只做装配与事件路由：面板构建交互、状态保存数据、服务执行业务。
    """

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        apply_theme(root)

        # ---- 依赖装配 ----
        self.store = SettingsStore()
        settings = self.store.load_settings()
        self.state = AppState(self.store, _params_from_settings(settings), settings)
        self.history_mgr = HistoryManager()
        self.chart_service = ChartService(ImageProcessor())
        self.batch_service = BatchService(self.chart_service.processor, self.history_mgr)

        # ---- 运行标志 ----
        self.is_processing = False
        self.is_calculating = False
        self._pending_regenerate = False
        self._modal_active = False
        self._closing = False
        self.preview_timer = None
        self.color_chart_window = None

        self._setup_window()
        self._build_layout()
        self._setup_menu()
        self._setup_shortcuts()
        self._setup_dnd()

    # ================================================================
    # 窗口与布局
    # ================================================================
    def _setup_window(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        settings = self.state.settings
        win_w = settings.get('window_w') or 0
        win_h = settings.get('window_h') or 0
        if win_w > 600 and win_h > 400:
            win_w = min(win_w, max(800, screen_w - 60))
            win_h = min(win_h, max(600, screen_h - 60))
            self.root.geometry(f"{win_w}x{win_h}")
        else:
            self.root.geometry(f"{int(screen_w * 0.85)}x{int(screen_h * 0.85)}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        main_container = ttk.Frame(self.root, padding=15)
        main_container.pack(fill=tk.BOTH, expand=tk.YES)

        # 左侧：可滚动设置面板
        left_panel = ttk.LabelFrame(main_container, text="⚙️ 设置面板", padding=15)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.configure(width=350)
        left_panel.pack_propagate(False)

        canvas = tk.Canvas(left_panel, width=320, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._settings_canvas = canvas
        canvas.bind_all("<MouseWheel>", self._on_settings_wheel)

        # 面板装配（顺序与旧版一致）
        self.settings_panel = SettingsPanel(
            scroll_frame, self.state.settings,
            on_select_image=self.select_image,
            on_dimension_change=self._on_dimension_change,
            on_open_color_chart=self.open_color_chart)
        self.settings_panel.set_on_ratio_change(self._on_ratio_change)
        self.settings_panel.set_on_setting_change(self._on_setting_change)
        self.settings_panel.update_palette_info()
        self.settings_panel.update_cm_hint()

        self.queue_panel = QueuePanel(
            scroll_frame,
            on_enqueue=self.enqueue_item, on_remove=self.remove_selected_queue,
            on_clear=self.clear_queue, on_start=self.process_queue,
            on_cancel=self._cancel_queue)
        self.queue_items = self.store.load_queue()
        self.queue_panel.refresh(self.queue_items)

        self.stats_panel = StatsPanel(scroll_frame)
        self.history_panel = HistoryPanel(
            scroll_frame, on_load=self.load_selected_history,
            on_delete=self.delete_selected_history,
            on_clear=self.clear_history, on_refresh=self.refresh_history_list)
        self.history_panel.refresh(self.history_mgr.get_list())

        # 右侧：预览
        self.preview_panel = PreviewPanel(main_container)
        self.preview_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=tk.YES)

    # ================================================================
    # 菜单 / 快捷键 / 拖拽
    # ================================================================
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

    def _guarded(self, handler):
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
            'equal': lambda: self.preview_panel.zoom_by(10),
            'minus': lambda: self.preview_panel.zoom_by(-10),
        }
        for mod in ("Command", "Control"):
            for key, handler in actions.items():
                self.root.bind_all(f"<{mod}-{key}>", self._guarded(handler))

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

    # ================================================================
    # 设置面板事件
    # ================================================================
    def _on_settings_wheel(self, event):
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Widget):
            return
        try:
            if widget.winfo_toplevel() is not self.root:
                return
        except tk.TclError:
            return
        w = widget
        while w is not None and w is not self.root:
            if w is self._settings_canvas:
                break
            w = w.master
        else:
            return
        if is_mac():
            step = int(-event.delta)
        else:
            step = int(-(event.delta / 120))
        self._settings_canvas.yview_scroll(step, "units")

    def _on_dimension_change(self, source):
        if self.is_calculating:
            return
        if self.settings_panel.current_params() == self.state.params:
            return
        self.is_calculating = True
        try:
            self.state.save_state()
            self.settings_panel.link_from(source)
        finally:
            self.is_calculating = False
        self.settings_panel.update_cm_hint()
        self._trigger_preview()

    def _on_ratio_change(self):
        if self.settings_panel.current_params() == self.state.params:
            return
        self.state.save_state()
        self._trigger_preview()

    def _on_setting_change(self, save=True):
        changed = self.settings_panel.current_params() != self.state.params
        if not changed:
            return
        if save:
            self.state.save_state()
        self.settings_panel.update_cm_hint()
        self.settings_panel.update_palette_info()
        self._trigger_preview()

    def _trigger_preview(self):
        if self.is_processing:
            self._pending_regenerate = True
            return
        if self.preview_timer:
            try:
                self.root.after_cancel(self.preview_timer)
            except tk.TclError:
                pass
            self.preview_timer = None

        def fire():
            self.preview_timer = None
            self.generate_preview()

        self.preview_timer = self.root.after(800, fire)

    def _sync_params_from_panel(self):
        self.state.set_params(self.settings_panel.current_params())

    # ================================================================
    # 图片选择 / 加载
    # ================================================================
    def select_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp *.webp *.gif")])
        if not file_path:
            return
        self._load_image_file(file_path)

    def _load_image_file(self, file_path):
        try:
            img = Image.open(file_path)
            img.load()
        except Exception:
            messagebox.showerror("错误", "无法打开该图片文件")
            return
        self.state.save_state()
        self._sync_params_from_panel()
        self.state.replace_original_image(img)
        self.state.selected_file = file_path
        self.preview_panel.clear_images()
        self.state.reset_result()
        self.settings_panel.lbl_file.config(
            text=os.path.basename(file_path), foreground="black")
        orig_w, orig_h = img.size
        suggested_w = min(max(30, orig_w // 20), 80)
        params = self.state.params
        self.state.set_params(GenerateParams(
            grid_w=suggested_w, grid_h=params.grid_h, cell_px=params.cell_px,
            ratio=params.ratio, palette=params.palette,
            show_grid=params.show_grid, show_labels=params.show_labels,
            show_legend=params.show_legend, grid_color=params.grid_color))
        self.settings_panel.apply_params(self.state.params)
        self.settings_panel.link_from('w')
        self.settings_panel.update_cm_hint()
        self._sync_params_from_panel()
        self.generate_preview()

    # ================================================================
    # 生成 / 预览
    # ================================================================
    def _generate_chart(self):
        return self.chart_service.generate(self.state.selected_file, self.state.params)

    def generate_preview(self, confirm_big=False):
        if self.is_processing:
            return
        if not self.state.selected_file:
            self.preview_panel.lbl_status.config(
                text="⚠️ 请先选择图片！", style="Status.Warn.TLabel")
            return

        self._sync_params_from_panel()
        if confirm_big:
            w, h = self.state.params.grid_w, self.state.params.grid_h
            if w * h > BIG_GRID_WARN:
                if not messagebox.askyesno(
                        "大图纸确认",
                        f"网格 {w}×{h} = {w * h} 颗豆子，生成可能需要较长时间。\n\n继续吗？"):
                    return

        self.is_processing = True
        self._pending_regenerate = False
        self.preview_panel.lbl_status.config(text="⏳ 正在处理...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is not None:
                self._apply_result(result)
                self.preview_panel.lbl_status.config(
                    text=f"✅ 完成！{result.chart.width}x{result.chart.height} | "
                         f"网格：{result.grid_w}x{result.grid_h}",
                    style="Status.OK.TLabel")
            else:
                self.preview_panel.lbl_status.config(text="❌ 处理失败", style="Status.Err.TLabel")
        finally:
            self.is_processing = False
            if self._pending_regenerate and self.state.selected_file:
                self._pending_regenerate = False
                self.preview_timer = self.root.after(50, self.generate_preview)

    def _apply_result(self, result):
        self.state.apply_result(result)
        self.preview_panel.set_images(result.chart, result.finished)
        self.stats_panel.update(result.color_stats, result.total_beads,
                                result.grid_w, result.grid_h)

    # ================================================================
    # 保存 / 导出
    # ================================================================
    def _grid_dims(self):
        return self.state.params.grid_w, self.state.params.grid_h

    def _current_palette(self):
        from core.colors import display_to_internal
        return display_to_internal(self.state.params.palette)

    def save_to_history(self):
        if self.is_processing:
            return
        if not self.state.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        self._sync_params_from_panel()
        p = self.state.params
        default_name = f"perler_{p.grid_w}x{p.grid_h}_{self._current_palette()}.png"
        save_path = filedialog.asksaveasfilename(
            title="保存拼豆图纸", defaultextension=".png",
            initialdir=OUTPUT_DIR, initialfile=default_name,
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.preview_panel.lbl_status.config(text="⏳ 正在生成...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            self.chart_service.save_chart(result, save_path)
            self._apply_result(result)
            self.history_mgr.add_record(self.state.selected_file, save_path,
                                        result.grid_w, result.grid_h, p.ratio, p.cell_px,
                                        p.show_grid, p.grid_color, p.palette,
                                        p.show_labels, p.show_legend)
            self.refresh_history_list()

            file_size = os.path.getsize(save_path) / 1024
            self._show_result_dialog(
                "保存成功",
                f"图片已保存至：\n{save_path}\n\n"
                f"尺寸：{result.chart.width}x{result.chart.height} 像素\n"
                f"文件大小：{file_size:.1f} KB\n使用色卡：{p.palette}\n"
                f"总耗材：{result.total_beads} 颗豆子", save_path)
            if self._closing:
                return
            self.preview_panel.lbl_status.config(
                text="💾 已保存到历史记录", style="Status.OK.TLabel")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            self.preview_panel.lbl_status.config(
                text=f"❌ 保存失败：{e}", style="Status.Err.TLabel")
        finally:
            self.is_processing = False

    def export_png(self):
        if self.is_processing:
            return
        if not self.state.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        self._sync_params_from_panel()
        p = self.state.params
        default_name = f"perler_{p.grid_w}x{p.grid_h}_{self._current_palette()}.png"
        save_path = filedialog.asksaveasfilename(
            title="导出 PNG", defaultextension=".png",
            initialdir=OUTPUT_DIR, initialfile=default_name,
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.preview_panel.lbl_status.config(text="⏳ 正在导出 PNG...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            self.chart_service.save_chart(result, save_path)
            self._apply_result(result)
            file_size = os.path.getsize(save_path) / 1024
            self.preview_panel.lbl_status.config(
                text=f"🖼️ PNG 已导出：{os.path.basename(save_path)}",
                style="Status.OK.TLabel")
            self._show_result_dialog(
                "导出成功",
                f"PNG 已导出至：\n{save_path}\n\n"
                f"尺寸：{result.chart.width}x{result.chart.height} 像素\n"
                f"文件大小：{file_size:.1f} KB", save_path)
            if self._closing:
                return
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            self.preview_panel.lbl_status.config(
                text=f"❌ 导出失败：{e}", style="Status.Err.TLabel")
        finally:
            self.is_processing = False

    def export_pdf(self):
        if self.is_processing:
            return
        if not self.state.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return

        mode = self._ask_pdf_mode()
        if mode is None:
            return

        self._sync_params_from_panel()
        p = self.state.params
        default_name = f"perler_{p.grid_w}x{p.grid_h}_{self._current_palette()}.pdf"
        save_path = filedialog.asksaveasfilename(
            title="导出 PDF", defaultextension=".pdf",
            initialdir=OUTPUT_DIR, initialfile=default_name,
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        if not save_path:
            return

        self.is_processing = True
        self.preview_panel.lbl_status.config(text="⏳ 正在导出 PDF...", style="Status.Busy.TLabel")
        self.root.update_idletasks()
        try:
            result = self._generate_chart()
            if result is None:
                messagebox.showerror("错误", "生成失败")
                return
            self.chart_service.export_pdf(result.chart, save_path, mode, result.cell_size)
            self._apply_result(result)
            file_size = os.path.getsize(save_path) / 1024
            self.preview_panel.lbl_status.config(
                text=f"📄 PDF 已导出：{os.path.basename(save_path)}",
                style="Status.OK.TLabel")
            self._show_result_dialog(
                "导出成功",
                f"PDF 已导出至：\n{save_path}\n\n文件大小：{file_size:.1f} KB\n"
                f"总耗材：{result.total_beads} 颗豆子", save_path)
            if self._closing:
                return
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            self.preview_panel.lbl_status.config(
                text=f"❌ 导出失败：{e}", style="Status.Err.TLabel")
        finally:
            self.is_processing = False

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
        ttk.Radiobutton(win, text="适应 A4 单页（整图缩放到一页）", value="a4",
                        variable=var).pack(anchor=tk.W, padx=25, pady=5)
        ttk.Radiobutton(win, text="1:1 实物大小多页（5mm/颗，自动切块拼接）", value="1x1",
                        variable=var).pack(anchor=tk.W, padx=25, pady=5)

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
        ttk.Button(btn_frame, text="取消", command=lambda: close(None),
                   width=10).pack(side=tk.LEFT, padx=5)

        self._center_toplevel(win)
        self.root.wait_window(win)
        self._modal_active = False
        if self._closing:
            return None
        return result["mode"]

    # ================================================================
    # 撤销
    # ================================================================
    def undo(self):
        snapshot = self.state.undo()
        if snapshot is None:
            return
        self.settings_panel.apply_params(snapshot.params)
        if snapshot.selected_file:
            self.state.selected_file = snapshot.selected_file
            self.settings_panel.lbl_file.config(
                text=os.path.basename(snapshot.selected_file), foreground="black")
        self._sync_params_from_panel()
        self.generate_preview()
        self.preview_panel.lbl_status.config(text="↩️ 已撤销", style="Status.Warn.TLabel")

    # ================================================================
    # 批量队列
    # ================================================================
    def enqueue_item(self):
        if not self.state.selected_file:
            messagebox.showwarning("提示", "请先选择图片！")
            return
        self._sync_params_from_panel()
        item = QueueItem(image_path=self.state.selected_file,
                         params=self.state.params,
                         fmt=self.queue_panel.queue_format_var.get())
        self.queue_items.append(item)
        self.store.save_queue(self.queue_items)
        self.refresh_queue_list()
        self.queue_panel.set_status(f"队列共 {len(self.queue_items)} 项")

    def refresh_queue_list(self):
        self.queue_panel.refresh(self.queue_items)

    def remove_selected_queue(self):
        index = self.queue_panel.selection_index()
        if index is None:
            messagebox.showwarning("提示", "请先选择要移除的队列项")
            return
        self.queue_items.pop(index)
        self.store.save_queue(self.queue_items)
        self.refresh_queue_list()
        self.queue_panel.set_status(f"队列共 {len(self.queue_items)} 项")

    def clear_queue(self):
        if not self.queue_items:
            return
        self.queue_items.clear()
        self.store.save_queue(self.queue_items)
        self.refresh_queue_list()
        self.queue_panel.set_progress(0)
        self.queue_panel.set_status("队列为空", foreground="gray")

    def _cancel_queue(self):
        self._queue_cancel = True

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
        self.queue_panel.btn_queue_start.config(state=tk.DISABLED)
        self.queue_panel.btn_queue_cancel.config(state=tk.NORMAL)
        items = list(self.queue_items)
        total = len(items)
        self.queue_panel.set_progress(0, maximum=total)
        self.queue_panel.set_status("⏳ 开始批量处理...")
        self.root.update()

        def on_progress(done, _total, out_path):
            self.queue_panel.set_progress(done)
            self.queue_panel.set_status(
                f"⏳ 处理中 {done}/{total}：{os.path.basename(out_path)}")
            self.root.update()

        result = BatchResult()
        error = None
        try:
            result = self.batch_service.process(
                items, out_dir,
                on_progress=on_progress,
                is_cancelled=lambda: self._queue_cancel)
        except Exception as e:
            error = e
        finally:
            self.refresh_history_list()
            if error is None:
                self.queue_panel.set_progress(
                    min(len(result.success) + len(result.failed), total)
                    if result.cancelled else total)
            self.queue_panel.btn_queue_start.config(state=tk.NORMAL)
            self.queue_panel.btn_queue_cancel.config(state=tk.DISABLED)
            self.is_processing = False
            self._queue_cancel = False

        if error is not None:
            self.queue_panel.set_status("❌ 批量处理出错", foreground="#d1242f")
            messagebox.showerror("批量处理失败", str(error))
            return

        success = result.success
        failed = result.failed
        cancelled = result.cancelled_remaining
        if cancelled:
            self.queue_panel.set_status(
                f"⏹ 已取消：成功 {len(success)}，失败 {len(failed)}，剩余 {cancelled}",
                foreground="#b8860b")
            msg = (f"批量处理已取消\n\n✅ 成功 {len(success)} 项\n"
                   f"❌ 失败 {len(failed)} 项\n⏹ 剩余 {cancelled} 项未处理")
            if failed:
                msg += "\n\n失败明细：\n" + "\n".join(f"{name}: {err}" for name, err in failed)
            messagebox.showwarning("批量已取消", msg)
        elif failed:
            self.queue_panel.set_status(
                f"⚠️ 完成：成功 {len(success)}，失败 {len(failed)}", foreground="#b8860b")
            msg = f"批量处理完成\n\n✅ 成功 {len(success)} 项：\n" + "\n".join(success)
            msg += "\n\n❌ 失败 " + str(len(failed)) + " 项：\n" + "\n".join(
                f"{name}: {err}" for name, err in failed)
            messagebox.showwarning("批量完成（有失败）", msg)
        else:
            self.queue_panel.set_status(f"✅ 批量完成：成功 {len(success)} 项",
                                        foreground="#28a745")
            messagebox.showinfo("批量完成", f"全部 {len(success)} 项导出成功：\n{out_dir}")

    # ================================================================
    # 历史记录
    # ================================================================
    def refresh_history_list(self):
        self.history_panel.refresh(self.history_mgr.get_list())

    def load_selected_history(self):
        index = self.history_panel.selection_index()
        if index is None:
            messagebox.showwarning("提示", "请先选择一条历史记录")
            return
        record = self.history_mgr.get_record(index)
        if not record:
            return
        image_path = record.get('image_path') or ''
        if not image_path or not os.path.exists(image_path):
            messagebox.showerror("错误", "原图片已不存在")
            return

        try:
            self.state.save_state()
            self.state.selected_file = image_path
            self.settings_panel.lbl_file.config(
                text=os.path.basename(image_path), foreground="black")
            params = GenerateParams.from_dict(record)
            self.settings_panel.apply_params(params)
            self._sync_params_from_panel()
            try:
                img = Image.open(image_path)
                img.load()
                self.state.replace_original_image(img)
            except Exception:
                self.state.replace_original_image(None)
            self.preview_panel.clear_images()
            self.state.reset_result()
            self.preview_panel.lbl_status.config(
                text=f"📋 已加载历史 [{index}]，自动生成预览...", style="Status.Busy.TLabel")
            self.generate_preview()
        except Exception as e:
            self.preview_panel.lbl_status.config(
                text=f"❌ 加载历史失败：{e}", style="Status.Err.TLabel")

    def delete_selected_history(self):
        index = self.history_panel.selection_index()
        if index is None:
            messagebox.showwarning("提示", "请先选择一条历史记录")
            return
        if messagebox.askyesno("确认", "确定要删除这条历史记录吗？"):
            self.history_mgr.delete_record(index)
            self.refresh_history_list()
            self.preview_panel.lbl_status.config(
                text="🗑️ 已删除历史记录", style="Status.Warn.TLabel")

    def clear_history(self):
        if messagebox.askyesno("确认", "确定要清除所有历史记录吗？\n此操作不可恢复！"):
            self.history_mgr.clear_history()
            self.refresh_history_list()
            self.preview_panel.lbl_status.config(
                text="🗑️ 历史记录已清空", style="Status.Warn.TLabel")

    # ================================================================
    # 色卡窗口
    # ================================================================
    def open_color_chart(self):
        if self.color_chart_window is None or not self.color_chart_window.window.winfo_exists():
            from ui.color_chart_ui import ColorChartWindow
            from core.colors import display_to_internal
            try:
                self.color_chart_window = ColorChartWindow(
                    self.root, palette_name=display_to_internal(self.state.params.palette))
            except Exception as e:
                messagebox.showerror("色卡打开失败", str(e))
                return
            self.color_chart_window.window.bind("<Destroy>", self._on_color_chart_destroy)
        else:
            self.color_chart_window.window.focus_force()
            self.color_chart_window.window.lift()

    def _on_color_chart_destroy(self, event):
        if self.color_chart_window is not None and event.widget is self.color_chart_window.window:
            self.color_chart_window = None

    # ================================================================
    # 窗口辅助
    # ================================================================
    def _show_about(self):
        messagebox.showinfo(
            "关于", f"{APP_NAME} v{APP_VERSION}\n\n支持 Mac / Windows\n"
                    f"批量队列、PNG / PDF 导出")

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

    def _on_close(self):
        self._closing = True
        self._sync_params_from_panel()
        self.state.persist_settings(self.root.winfo_width(), self.root.winfo_height())
        try:
            if self.preview_timer:
                self.root.after_cancel(self.preview_timer)
                self.preview_timer = None
            self.preview_panel.cancel_timer()
            self.root.unbind_all("<MouseWheel>")
        except (tk.TclError, AttributeError):
            pass
        self.root.destroy()
