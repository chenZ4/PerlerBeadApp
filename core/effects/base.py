# core/effects/base.py - 特效规格与上下文
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class EffectSpec:
    id: str
    name: str
    category: str          # geometric / preprocess / grid / chart
    params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    requires_opencv: bool = False
    description: str = ""

    def param_schema(self):
        """供 UI/协议层使用的参数 schema"""
        return self.params


@dataclass
class EffectContext:
    palette: Any = None
    grid_w: int = 0
    grid_h: int = 0
    cell_size: int = 0
    engine: Any = None
