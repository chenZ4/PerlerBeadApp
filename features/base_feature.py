# features/base_feature.py - 功能插件基类
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseFeature(ABC):
    """功能插件基类"""

    def __init__(self):
        self.name = "未命名功能"
        self.description = ""
        self.enabled = True

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行功能"""
        pass

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        pass

    @abstractmethod
    def set_config(self, config: Dict[str, Any]):
        """设置配置"""
        pass

    def is_available(self) -> bool:
        """检查功能是否可用"""
        return self.enabled