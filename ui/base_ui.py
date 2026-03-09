# ui/base_ui.py - UI 基类（定义标准接口）
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseUI(ABC):
    """UI 基类 - 定义所有平台 UI 的标准接口"""

    def __init__(self):
        self.processor = None
        self.history_manager = None
        self.settings_manager = None

    @abstractmethod
    def initialize(self):
        """初始化 UI"""
        pass

    @abstractmethod
    def show(self):
        """显示窗口"""
        pass

    @abstractmethod
    def hide(self):
        """隐藏窗口"""
        pass

    @abstractmethod
    def close(self):
        """关闭窗口"""
        pass

    @abstractmethod
    def update_preview(self, image_data: Any):
        """更新预览"""
        pass

    @abstractmethod
    def update_status(self, message: str):
        """更新状态"""
        pass

    @abstractmethod
    def show_error(self, title: str, message: str):
        """显示错误"""
        pass

    @abstractmethod
    def show_success(self, title: str, message: str):
        """显示成功"""
        pass

    def set_processor(self, processor):
        """设置处理器"""
        self.processor = processor

    def set_history_manager(self, manager):
        """设置历史管理器"""
        self.history_manager = manager

    def set_settings_manager(self, manager):
        """设置设置管理器"""
        self.settings_manager = manager

    def get_current_settings(self) -> Dict[str, Any]:
        """获取当前设置"""
        if self.settings_manager:
            return self.settings_manager.settings
        return {}