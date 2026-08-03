# core/effects/__init__.py
from .base import EffectContext, EffectSpec
from .registry import (apply_phase, get_spec, has_effect, list_effects,
                       register)

# 导入特效模块触发注册
from . import filters  # noqa: F401
from . import filters2  # noqa: F401
from . import geometry  # noqa: F401
from . import outline  # noqa: F401
from . import presets  # noqa: F401

__all__ = ["EffectSpec", "EffectContext", "register", "list_effects",
           "get_spec", "has_effect", "apply_phase"]
