# ui/theme.py - 跨平台界面主题
import tkinter as tk
from tkinter import ttk

from ui.fonts import is_mac, ui_font

ACCENT = "#0078D4"
BG = "#F5F6F7"
FG = "#333333"


def apply_theme(root):
    style = ttk.Style(root)
    try:
        if is_mac():
            style.theme_use("aqua")
        else:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
    except tk.TclError:
        pass

    style.configure(".", font=ui_font(10))

    style.configure("Section.TLabel", font=ui_font(11, bold=True))
    style.configure("Status.OK.TLabel", foreground="#1a7f37")
    style.configure("Status.Busy.TLabel", foreground=ACCENT)
    style.configure("Status.Warn.TLabel", foreground="#d97706")
    style.configure("Status.Err.TLabel", foreground="#d1242f")
    style.configure("Accent.TButton", foreground="white")

    if is_mac():
        return

    root.configure(background=BG)
    style.configure("TFrame", background=BG)
    style.configure("TLabelframe", background=BG, bordercolor="#D1D5DB", relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=FG, font=ui_font(11, bold=True))
    style.configure("TButton", padding=(12, 6), font=ui_font(10))
    style.map("TButton",
              background=[("pressed", "#C8CFD6"), ("active", "#E4E9EE")],
              foreground=[("disabled", "#9CA3AF")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white")
    style.map("Accent.TButton",
              background=[("pressed", "#005A9E"), ("active", "#1A86D9")],
              foreground=[("disabled", "#F0F4F8")])
    style.configure("TCheckbutton", background=BG, font=ui_font(10))
    style.configure("TRadiobutton", background=BG, font=ui_font(10))
    style.configure("TCombobox", padding=4, font=ui_font(10))
    style.configure("TEntry", padding=4, font=ui_font(10))
    style.configure("TScale", background=BG, troughcolor="#D1D5DB", bordercolor="#D1D5DB")
    style.configure("Horizontal.TScale", background=BG)
    style.configure("TProgressbar", background=ACCENT, troughcolor="#E5E7EB", borderwidth=0)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#E5E7EB", borderwidth=0)
    style.configure("TSeparator", background="#D1D5DB")
