# core/history_manager.py
import json
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LEGACY_HISTORY_FILE = os.path.join(os.getcwd(), "history.json")

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _as_int(value, default):
    """宽松整数转换：非法类型/值回退 default"""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class HistoryManager:
    def __init__(self, file_path=None):
        self.file_path = file_path or HISTORY_FILE
        self.history = []
        self.load_history()

    def load_history(self):
        history_file = self.file_path
        legacy = (os.path.abspath(LEGACY_HISTORY_FILE)
                  if os.path.exists(LEGACY_HISTORY_FILE) else None)
        if legacy and legacy != os.path.abspath(history_file) \
                and not os.path.exists(history_file):
            try:
                with open(legacy, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.history = data if isinstance(data, list) else []
            except (IOError, OSError, ValueError):
                self.history = []
            self._migrate_history()
            self.save_history()
            return

        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.history = data if isinstance(data, list) else []
            except (IOError, OSError, ValueError):
                self.history = []
        else:
            self.history = []
        self._migrate_history()

    def _migrate_history(self):
        updated = False
        cleaned = []
        for record in self.history:
            if not isinstance(record, dict):
                updated = True
                continue
            if 'palette' not in record:
                record['palette'] = "佩勒 24 色"
                updated = True
            if 'image_path' not in record:
                record['image_path'] = ""
                updated = True
            elif not isinstance(record['image_path'], str):
                record['image_path'] = ""
                updated = True
            if 'output_size' not in record:
                record['output_size'] = 1500
                updated = True
            else:
                os_val = _as_int(record['output_size'], 0)
                if not isinstance(record['output_size'], (int, float)) \
                        and not isinstance(record['output_size'], bool):
                    record['output_size'] = os_val
                    updated = True
                if os_val > 200:
                    # 旧语义：总画布像素 -> 反推每格像素
                    w = _as_int(record.get('width'), 50) or 50
                    h = _as_int(record.get('height'), 50) or 50
                    cell = round(os_val / max(1, max(w, h)))
                    record['output_size'] = max(16, min(160, cell))
                    updated = True
            for key in ('width', 'height'):
                if key in record and not isinstance(record[key], (int, float)):
                    record[key] = _as_int(record[key], 50)
                    updated = True
            if 'show_grid' not in record:
                record['show_grid'] = True
                updated = True
            if 'show_labels' not in record:
                record['show_labels'] = True
                updated = True
            if 'show_legend' not in record:
                record['show_legend'] = True
                updated = True
            if record.get('ratio') == "原始比例":
                record['ratio'] = "按原图比例（宽为基准）"
                updated = True
            if 'grid_color' not in record:
                record['grid_color'] = "#C8C8C8"
                updated = True
            elif not isinstance(record['grid_color'], str) \
                    or not _HEX_RE.match(record['grid_color']):
                rgb = record['grid_color']
                if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                    try:
                        record['grid_color'] = '#{:02X}{:02X}{:02X}'.format(
                            int(rgb[0]), int(rgb[1]), int(rgb[2]))
                        updated = True
                    except (TypeError, ValueError):
                        record['grid_color'] = "#C8C8C8"
                        updated = True
                else:
                    record['grid_color'] = "#C8C8C8"
                    updated = True
            if 'save_path' not in record:
                record['save_path'] = ""
                updated = True
            elif isinstance(record['save_path'], str) and record['save_path'] \
                    and not os.path.isabs(record['save_path']):
                record['save_path'] = os.path.normpath(
                    os.path.join(BASE_DIR, record['save_path'].replace('\\', '/')))
                updated = True
            elif not isinstance(record['save_path'], str):
                record['save_path'] = ""
                updated = True
            cleaned.append(record)
        if updated:
            self.history = cleaned
            self.save_history()

    def save_history(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def add_record(self, image_path, save_path, width, height, ratio_mode, canvas_size,
                   show_grid, grid_color, palette_name, show_labels=True, show_legend=True):
        record = {
            "image_path": image_path,
            "save_path": save_path,
            "width": width,
            "height": height,
            "ratio": ratio_mode,
            "output_size": canvas_size,
            "show_grid": show_grid,
            "show_labels": show_labels,
            "show_legend": show_legend,
            "grid_color": grid_color,
            "palette": palette_name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.history.insert(0, record)
        if len(self.history) > 50:
            self.history = self.history[:50]
        self.save_history()

    def get_list(self):
        return self.history

    def get_record(self, index):
        if 0 <= index < len(self.history):
            return self.history[index]
        return None

    def clear_history(self):
        self.history = []
        self.save_history()

    def delete_record(self, index):
        if 0 <= index < len(self.history):
            self.history.pop(index)
            self.save_history()
