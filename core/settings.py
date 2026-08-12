# core/settings.py - 应用偏好与队列持久化（SettingsStore 类 + 兼容旧函数）
import json
import os

from .models import (
    DEFAULT_CELL_PX,
    DEFAULT_GRID_COLOR,
    RATIO_ORIGINAL,
    QueueItem,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(BASE_DIR, "app_settings.json")
QUEUE_FILE = os.path.join(BASE_DIR, "queue_state.json")

DEFAULTS = {
    "palette": "MARD 221 色",
    "cell_px": str(DEFAULT_CELL_PX),
    "show_grid": True,
    "show_labels": True,
    "show_legend": True,
    "grid_color": DEFAULT_GRID_COLOR,
    "ratio": RATIO_ORIGINAL,
    "window_w": 0,
    "window_h": 0,
}


class SettingsStore:
    """应用偏好 + 批量队列的持久化封装。

    读取异常时回退默认值并保证不崩溃；所有写入吞掉 IO 异常（非关键路径）。
    """

    def __init__(self, settings_file=SETTINGS_FILE, queue_file=QUEUE_FILE):
        self.settings_file = settings_file
        self.queue_file = queue_file

    # ---------- 偏好 ----------
    def load_settings(self):
        settings = dict(DEFAULTS)
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
        except (IOError, OSError, ValueError):
            pass
        return settings

    def save_settings(self, settings):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def update_settings(self, **kwargs):
        settings = self.load_settings()
        settings.update(kwargs)
        self.save_settings(settings)
        return settings

    # ---------- 批量队列 ----------
    def load_queue(self):
        """读取队列并迁移为 QueueItem 列表（兼容旧裸 dict 文件）"""
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (IOError, OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [QueueItem.from_legacy(i) for i in data if isinstance(i, dict)]

    def save_queue(self, items):
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump([i.to_dict() if isinstance(i, QueueItem) else i
                           for i in items], f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass


# ---------- 兼容旧函数（返回默认实例结果，行为与原模块级函数一致） ----------
def load_settings():
    return SettingsStore().load_settings()


def save_settings(settings):
    SettingsStore().save_settings(settings)


def load_queue():
    """兼容旧 API：返回可 JSON 序列化的 dict 列表（core_server 协议用）"""
    return [i.to_dict() for i in SettingsStore().load_queue()]


def save_queue(items):
    SettingsStore().save_queue(items)
