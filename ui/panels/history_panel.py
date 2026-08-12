# ui/panels/history_panel.py - 历史记录面板
import tkinter as tk
from tkinter import messagebox, ttk


class HistoryPanel:
    """历史记录：列表 + 刷新/清除/加载/删除"""

    def __init__(self, parent, title="📜 历史记录",
                 on_load=None, on_delete=None, on_clear=None, on_refresh=None):
        from ui.widgets import section_title
        section_title(parent, title)

        frame_btn = ttk.Frame(parent)
        frame_btn.pack(fill=tk.X, pady=5)
        ttk.Button(frame_btn, text="刷新",
                   command=on_refresh if on_refresh else self.refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_btn, text="清除",
                   command=on_clear).pack(side=tk.LEFT, padx=2)

        self.list_history = tk.Listbox(parent, height=6)
        self.list_history.pack(fill=tk.X, pady=5)
        self.list_history.bind("<<ListboxSelect>>", self._on_select)

        frame_action = ttk.Frame(parent)
        frame_action.pack(fill=tk.X, pady=5)
        ttk.Button(frame_action, text="加载",
                   command=on_load).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_action, text="删除",
                   command=on_delete).pack(side=tk.LEFT, padx=2)

        self._records = []
        self._on_select_cb = on_load

    def _on_select(self, _event=None):
        if self._on_select_cb:
            self._on_select_cb()

    def refresh(self, records=None):
        if records is not None:
            self._records = records
        self.list_history.delete(0, tk.END)
        for i, record in enumerate(self._records):
            text = (f"[{i}] {record.get('time', '?')} - "
                    f"{record.get('width', '?')}x{record.get('height', '?')} "
                    f"({record.get('palette', '?')})")
            self.list_history.insert(tk.END, text)

    def selection_index(self):
        selection = self.list_history.curselection()
        return selection[0] if selection else None
