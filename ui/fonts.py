# ui/fonts.py - 跨平台字体选择（macOS / Windows）
import sys


def is_mac():
    return sys.platform == "darwin"


def ui_font(size, bold=False):
    family = "PingFang SC" if is_mac() else "Microsoft YaHei"
    return (family, size, "bold" if bold else "normal")


def mono_font(size, bold=False):
    family = "Menlo" if is_mac() else "Consolas"
    return (family, size, "bold" if bold else "normal")
