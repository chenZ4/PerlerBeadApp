# core/history_manager.py
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LEGACY_HISTORY_FILE = "history.json"


class HistoryManager:
    def __init__(self):
        self.history = []
        self.load_history()

    def load_history(self):
        if os.path.exists(LEGACY_HISTORY_FILE) and not os.path.exists(HISTORY_FILE):
            try:
                with open(LEGACY_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except:
                self.history = []
            self._migrate_history()
            self.save_history()
            return

        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except:
                self.history = []
        else:
            self.history = []
        self._migrate_history()

    def _migrate_history(self):
        updated = False
        for record in self.history:
            if not isinstance(record, dict):
                continue
            if 'palette' not in record:
                record['palette'] = "佩勒 24 色"
                updated = True
            if 'output_size' not in record:
                record['output_size'] = 1500
                updated = True
            elif isinstance(record['output_size'], (int, float)) and record['output_size'] > 200:
                # 旧语义：总画布像素 -> 反推每格像素
                w = record.get('width') or 50
                h = record.get('height') or 50
                cell = round(record['output_size'] / max(1, max(w, h)))
                record['output_size'] = max(16, min(160, cell))
                updated = True
            if 'show_grid' not in record:
                record['show_grid'] = True
                updated = True
            if 'show_labels' not in record:
                record['show_labels'] = True
                updated = True
            if record.get('ratio') == "原始比例":
                record['ratio'] = "按原图比例（宽为基准）"
                updated = True
            if 'grid_color' not in record:
                record['grid_color'] = "#C8C8C8"
                updated = True
            elif not isinstance(record['grid_color'], str):
                rgb = record['grid_color']
                if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                    record['grid_color'] = '#{:02X}{:02X}{:02X}'.format(
                        int(rgb[0]), int(rgb[1]), int(rgb[2]))
                    updated = True
                else:
                    record['grid_color'] = "#C8C8C8"
                    updated = True
            if 'save_path' not in record:
                record['save_path'] = ""
                updated = True
            elif record['save_path'] and not os.path.isabs(record['save_path']):
                record['save_path'] = os.path.normpath(
                    os.path.join(BASE_DIR, record['save_path'].replace('\\', '/')))
                updated = True

        if updated:
            self.save_history()

    def save_history(self):
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass

    def add_record(self, image_path, save_path, width, height, ratio_mode, canvas_size,
                   show_grid, grid_color, palette_name, show_labels=True):
        record = {
            "image_path": image_path,
            "save_path": save_path,
            "width": width,
            "height": height,
            "ratio": ratio_mode,
            "output_size": canvas_size,
            "show_grid": show_grid,
            "show_labels": show_labels,
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
