# ui/panels/preview_panel.py - 实时预览面板（渲染/缩放/拖动）
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ui.fonts import is_mac, ui_font

MAX_RENDER_DIM = 8192


class PreviewPanel:
    """右侧预览：画布 + 缩放条 + 成品切换 + 状态栏。

    图片渲染完全内聚：调用方通过 set_image() 更新图源，面板负责降采样/缩放/平移。
    """

    def __init__(self, parent, title="🖼️ 实时预览",
                 on_zoom_change=None, on_fit_toggle=None):
        self.frame = ttk.LabelFrame(parent, text=title, padding=15)

        self.canvas_frame = ttk.Frame(self.frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=tk.YES, pady=10)
        self.canvas_frame.bind("<Configure>", self._on_resize)

        self.preview_canvas = tk.Canvas(self.canvas_frame, background="#F3F3F3",
                                        highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=tk.YES)
        self.preview_canvas.bind("<MouseWheel>", self._on_wheel)
        self.preview_canvas.bind("<ButtonPress-1>", self._on_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_release)
        self.preview_canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas_frame.bind("<MouseWheel>", self._on_wheel)

        self.scale_frame = ttk.Frame(self.frame)
        self.scale_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.scale_frame, text="预览缩放:").pack(side=tk.LEFT)
        self.fit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.scale_frame, text="适应窗口", variable=self.fit_var,
                        command=self._toggle_fit).pack(side=tk.LEFT)
        self.zoom_var = tk.IntVar(value=100)
        self.scale_zoom = ttk.Scale(self.scale_frame, from_=25, to=400,
                                    variable=self.zoom_var, orient=tk.HORIZONTAL,
                                    command=self._on_zoom_cmd)
        self.scale_zoom.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES, padx=10)
        self.lbl_zoom_val = ttk.Label(self.scale_frame, text="适应窗口", width=8)
        self.lbl_zoom_val.pack(side=tk.LEFT)
        self.finished_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.scale_frame, text="成品效果", variable=self.finished_var,
                        command=self._schedule_render).pack(side=tk.LEFT, padx=(12, 0))

        self.lbl_status = ttk.Label(self.frame, text="✅ 就绪", style="Status.OK.TLabel")
        self.lbl_status.pack(pady=10)

        self._processed = None
        self._finished = None
        self.photo_ref = None
        self._drag_start = None
        self._img_item = None
        self._img_w = 0
        self._img_h = 0
        self._ox = 0
        self._oy = 0
        self._render_timer = None
        self._show_placeholder()

    # ---------- 布局 ----------
    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def bind_canvas_frame(self, seq, handler):
        self.canvas_frame.bind(seq, handler)

    # ---------- 图片源 ----------
    def set_images(self, processed, finished=None):
        """更新图源（PIL Image 引用，调用方负责旧图释放）"""
        self._processed = processed
        self._finished = finished
        self._schedule_render(0)

    def clear_images(self):
        """清空图源引用（换图/撤销时在旧图 close 前调用，防渲染已关闭对象）"""
        self._processed = None
        self._finished = None
        self.cancel_timer()
        self._show_placeholder()

    @property
    def processed_image(self):
        return self._processed

    @property
    def finished_image(self):
        return self._finished

    def _current_image(self):
        if self.finished_var.get() and self._finished is not None:
            return self._finished
        return self._processed

    # ---------- 渲染 ----------
    def _schedule_render(self, delay=60):
        if self._render_timer:
            try:
                self.frame.after_cancel(self._render_timer)
            except tk.TclError:
                pass
            self._render_timer = None
        self._render_timer = self.frame.after(delay, self._render)

    def _render(self):
        self._render_timer = None
        img = self._current_image()
        if img is None:
            self._show_placeholder()
            return
        aw = self.canvas_frame.winfo_width()
        ah = self.canvas_frame.winfo_height()

        try:
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

            if nw > MAX_RENDER_DIM or nh > MAX_RENDER_DIM:
                s = min(MAX_RENDER_DIM / nw, MAX_RENDER_DIM / nh)
                nw = max(1, int(nw * s))
                nh = max(1, int(nh * s))

            display = img.resize((nw, nh), Image.NEAREST)
            self._set_photo(display)
        except (ValueError, OSError):
            self._show_placeholder()

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
        self._center()

    def _center(self):
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

    def _show_placeholder(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        self._img_item = None
        canvas.create_text(12, 12, anchor=tk.NW, text="请选择图片并生成预览",
                           fill="#888888", font=ui_font(11))

    # ---------- 交互 ----------
    def _on_zoom_cmd(self, val):
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

    def zoom_by(self, delta_pct):
        """键盘 +/- 缩放"""
        if self._processed is None:
            return
        if self.fit_var.get():
            # 从当前实际显示比例起算，避免跳变
            img = self._current_image()
            try:
                aw = self.canvas_frame.winfo_width()
                ah = self.canvas_frame.winfo_height()
                current = int(min(aw / img.width, ah / img.height) * 100)
            except (ValueError, OSError, ZeroDivisionError):
                current = 100
            self.fit_var.set(False)
            self.zoom_var.set(max(25, min(400, current)))
        new_zoom = max(25, min(400, self.zoom_var.get() + delta_pct))
        self.zoom_var.set(new_zoom)
        self.lbl_zoom_val.config(text=f"{new_zoom}%")
        self._schedule_render(40)

    def _on_wheel(self, event):
        if self._processed is None:
            return
        if is_mac():
            step = event.delta
        else:
            step = event.delta / 120
        if step == 0:
            return
        self.zoom_by(int(step * 10))

    def _on_resize(self, _event=None):
        if self.fit_var.get() and self._processed is not None:
            self._schedule_render(100)

    def _on_press(self, event):
        if self._img_item is None:
            return
        self._drag_start = (event.x, event.y, self._ox, self._oy)

    def _on_drag(self, event):
        if self._drag_start is None or self._img_item is None:
            return
        sx, sy, ox0, oy0 = self._drag_start
        ox, oy = self._clamp_offset(ox0 + (event.x - sx), oy0 + (event.y - sy))
        self._ox, self._oy = ox, oy
        self.preview_canvas.coords(self._img_item, ox, oy)

    def _on_release(self, _event):
        self._drag_start = None

    def _on_double_click(self, _event):
        if self._img_item is None:
            return
        self._center()

    def force_render(self):
        self._render()

    def cancel_timer(self):
        if self._render_timer:
            self.frame.after_cancel(self._render_timer)
            self._render_timer = None
