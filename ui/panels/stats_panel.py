# ui/panels/stats_panel.py - 颜色统计面板
from tkinter import ttk


class StatsPanel:
    """颜色统计展示：前 10 色 + 总计/网格信息"""

    def __init__(self, parent, title="📊 颜色统计"):
        from ui.widgets import section_title
        section_title(parent, title)
        self.lbl_color_stats = ttk.Label(parent, text="生成后显示",
                                         foreground="gray", wraplength=300)
        self.lbl_color_stats.pack(fill="x", pady=5)

    def update(self, color_stats=None, total_beads=0, grid_w=0, grid_h=0):
        if not color_stats:
            self.lbl_color_stats.config(text="生成后显示", foreground="gray")
            return
        text = ""
        sorted_stats = sorted(color_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        for code, info in sorted_stats[:10]:
            text += f"● {info['code']} {info['name']}: {info['count']}颗\n"
        if len(color_stats) > 10:
            text += f"... 共 {len(color_stats)} 种颜色\n"
        text += f"\n总计：{total_beads} 颗豆子 | 网格：{grid_w}×{grid_h}"
        self.lbl_color_stats.config(text=text, foreground="black")
