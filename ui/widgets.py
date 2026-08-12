# ui/widgets.py - 通用小组件
from tkinter import ttk


def section_title(parent, text):
    """面板分区标题 + 分隔线"""
    ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", pady=(15, 8))
    ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=(0, 10))
