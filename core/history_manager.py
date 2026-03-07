# core/history_manager.py
import json
import os
from datetime import datetime

HISTORY_FILE = "history.json"


class HistoryManager:
    def __init__(self):
        self.history = []
        self.load_history()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                self._migrate_history()
            except:
                self.history = []
        else:
            self.history = []

    def _migrate_history(self):
        updated = False
        for record in self.history:
            if 'palette' not in record:
                record['palette'] = "佩勒 24 色"
                updated = True
            if 'output_size' not in record:
                record['output_size'] = 1500
                updated = True
            if 'show_grid' not in record:
                record['show_grid'] = True
                updated = True
            if 'grid_color' not in record:
                record['grid_color'] = "#C8C8C8"
                updated = True
            if 'save_path' not in record:
                record['save_path'] = ""
                updated = True

        if updated:
            self.save_history()

    def save_history(self):
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def add_record(self, image_path, save_path, width, height, ratio_mode, canvas_size,
                   show_grid, grid_color, palette_name):
        record = {
            "image_path": image_path,
            "save_path": save_path,
            "width": width,
            "height": height,
            "ratio": ratio_mode,
            "output_size": canvas_size,
            "show_grid": show_grid,
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