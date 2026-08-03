# core/effects/registry.py - 特效注册表与管线执行
from .base import EffectSpec

_EFFECTS = {}


def register(spec: EffectSpec, handler):
    """注册特效：spec 定义元数据与参数 schema，handler 为阶段处理函数"""
    _EFFECTS[spec.id] = (spec, handler)


def list_effects():
    """返回 {id: spec}，供协议层/UI 展示"""
    return {eid: spec for eid, (spec, _) in _EFFECTS.items()}


def get_spec(effect_id):
    item = _EFFECTS.get(effect_id)
    return item[0] if item else None


def _coerce_params(params, schema):
    """按 schema 约束参数（类型/范围/默认值）"""
    out = {}
    for name, meta in schema.items():
        value = params.get(name, meta.get("default"))
        try:
            if meta.get("type") == "int":
                value = int(value)
                if "min" in meta:
                    value = max(meta["min"], value)
                if "max" in meta:
                    value = min(meta["max"], value)
            elif meta.get("type") == "float":
                value = float(value)
                if "min" in meta:
                    value = max(meta["min"], value)
                if "max" in meta:
                    value = min(meta["max"], value)
            elif meta.get("type") == "bool":
                value = bool(value)
            elif meta.get("type") == "color":
                value = str(value)
            elif meta.get("type") == "choice":
                if meta.get("options") and value not in meta["options"]:
                    value = meta.get("default")
        except (TypeError, ValueError):
            value = meta.get("default")
        out[name] = value
    return out


def apply_phase(effects, phase, target, ctx=None):
    """按阶段顺序应用特效。

    effects: [{"id": ..., "params": {...}}, ...]
    phase: geometric / preprocess / grid / chart
    target: 该阶段的输入对象（图/网格矩阵/渲染参数字典）
    ctx: EffectContext（grid 阶段需要）
    返回处理后的 target。
    """
    if not effects:
        return target
    for e in effects:
        item = _EFFECTS.get(e.get("id"))
        if not item:
            continue
        spec, handler = item
        if spec.category != phase:
            continue
        params = _coerce_params(e.get("params") or {}, spec.params)
        target = handler(target, params, ctx)
    return target
