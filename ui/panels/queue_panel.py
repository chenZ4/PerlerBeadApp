# ui/panels/queue_panel.py - 批量队列面板
import os
import tkinter as tk
from tkinter import ttk

QUEUE_FORMATS = ["PNG", "PDF(A4适应)", "PDF(1:1实物)"]


class QueuePanel:
    """批量队列：格式选择、入队/开始/取消、列表、进度条、状态"""

    def __init__(self, parent, title="📋 批量队列",
                 on_enqueue=None, on_remove=None, on_clear=None,
                 on_start=None, on_cancel=None):
        from ui.widgets import section_title
        section_title(parent, title)

        frame_format = ttk.Frame(parent)
        frame_format.pack(fill=tk.X, pady=5)
        ttk.Label(frame_format, text="导出格式:").pack(side=tk.LEFT)
        self.queue_format_var = tk.StringVar(value="PNG")
        self.combo_queue_format = ttk.Combobox(
            frame_format, textvariable=self.queue_format_var,
            values=QUEUE_FORMATS, state="readonly", width=13)
        self.combo_queue_format.pack(side=tk.LEFT, padx=10)

        frame_btn = ttk.Frame(parent)
        frame_btn.pack(fill=tk.X, pady=5)
        ttk.Button(frame_btn, text="➕ 加入队列", command=on_enqueue,
                   width=10).pack(side=tk.LEFT, padx=2)
        self.btn_queue_start = ttk.Button(frame_btn, text="▶ 开始批量",
                                          command=on_start, width=10,
                                          style="Accent.TButton")
        self.btn_queue_start.pack(side=tk.LEFT, padx=2)
        self.btn_queue_cancel = ttk.Button(frame_btn, text="⏹ 取消",
                                           command=on_cancel, width=8,
                                           state=tk.DISABLED)
        self.btn_queue_cancel.pack(side=tk.LEFT, padx=2)

        self.queue_tree = ttk.Treeview(parent, columns=("thumb", "info"),
                                       show="tree", height=5)
        self.queue_tree.heading("#0", text="图片")
        self.queue_tree.column("#0", width=140, anchor=tk.W)
        self.queue_tree.heading("thumb", text="")
        self.queue_tree.column("thumb", width=54, anchor=tk.CENTER, stretch=False)
        self.queue_tree.heading("info", text="设置")
        self.queue_tree.column("info", width=130, anchor=tk.W)
        self.queue_tree.pack(fill=tk.X, pady=5)

        frame_action = ttk.Frame(parent)
        frame_action.pack(fill=tk.X, pady=5)
        ttk.Button(frame_action, text="移除选中", command=on_remove,
                   width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_action, text="清空", command=on_clear,
                   width=10).pack(side=tk.LEFT, padx=2)

        self.progress = ttk.Progressbar(parent, maximum=100, value=0)
        self.progress.pack(fill=tk.X, pady=5)
        self.lbl_queue_status = ttk.Label(parent, text="队列为空", foreground="gray")
        self.lbl_queue_status.pack(anchor=tk.W)

        self._thumb_cache = {}
        self._thumb_max = 200

    def _make_thumb(self, path):
        if path in self._thumb_cache:
            return self._thumb_cache[path]
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((48, 48))
            photo = ImageTk.PhotoImage(img)
            img.close()
        except Exception:
            return None
        self._thumb_cache[path] = photo
        while len(self._thumb_cache) > self._thumb_max:
            oldest = next(iter(self._thumb_cache))
            self._thumb_cache.pop(oldest, None)
        return photo

    def refresh(self, items):
        """items: list[QueueItem]"""
        self.queue_tree.delete(*self.queue_tree.get_children())
        for item in items:
            thumb = self._make_thumb(item.image_path)
            info = f"[{item.fmt}] {item.params.grid_w}x{item.params.grid_h}"
            self.queue_tree.insert("", tk.END, text=os.path.basename(item.image_path),
                                   values=(thumb, info))

    def selection_index(self):
        sel = self.queue_tree.selection()
        return self.queue_tree.index(sel[0]) if sel else None

    def set_progress(self, value, maximum=None):
        if maximum is not None:
            self.progress.config(maximum=maximum)
        self.progress.config(value=value)

    def set_status(self, text, foreground="black"):
        self.lbl_queue_status.config(text=text, foreground=foreground)
