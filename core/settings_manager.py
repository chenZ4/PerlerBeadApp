# core/settings_manager.py - 用户设置管理
import json
import os
from pathlib import Path
from config import SETTINGS_FILE, DEFAULT_SETTINGS


class SettingsManager:
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.settings_file = SETTINGS_FILE
        self.load_settings()

    def load_settings(self):
        """加载用户设置"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"加载设置失败：{e}")

    def save_settings(self):
        """保存用户设置"""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存设置失败：{e}")

    def get(self, key, default=None):
        """获取设置值"""
        return self.settings.get(key, default or DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        """设置值并保存"""
        self.settings[key] = value
        self.save_settings()

    def reset_to_default(self):
        """重置为默认设置"""
        self.settings = DEFAULT_SETTINGS.copy()
        self.save_settings()