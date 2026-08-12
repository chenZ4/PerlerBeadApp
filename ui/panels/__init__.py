# ui/panels/__init__.py
"""面板组件：每个面板只负责自己的 widget 构建与交互，通过回调与控制器通信"""
from .history_panel import HistoryPanel
from .preview_panel import PreviewPanel
from .queue_panel import QueuePanel
from .settings_panel import SettingsPanel
from .stats_panel import StatsPanel

__all__ = ["HistoryPanel", "PreviewPanel", "QueuePanel", "SettingsPanel", "StatsPanel"]
