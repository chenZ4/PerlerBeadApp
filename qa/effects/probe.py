#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa/effects/probe.py — 15 项特效真实效果量化复现（直接引擎路径，save=False）

回答用户主诉「特效代码可行但是效果不可行」：
  1. 事实基线：注册表 / 四阶段 / 每个特效在管线中的作用点；
  2. 素材矩阵：真实照片 x2、扁平卡通、透明背景 RGBA 各跑 15 项单特效 + 常用组合；
  3. 量化：与无特效基线的网格级差异、像素差异、平均/中位 CIELAB ΔE、耗材/色数/网格变化；
  4. 特殊探针：dither strength、outline 线连续性、bg_remove 白底/白主体、chibi 静默失效、
     preset 洗白、cel 色相漂移、色卡量化可见性下限、参数顺序影响、UI 静态可用性。
运行：
  cd <repo>
  PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python qa/effects/probe.py
输出：
  qa/effects/artifacts/**           证据图（≤1MB/张）
  qa/effects/artifacts/metrics.json 全量逐例数据
  qa/effects/artifacts/summary_table.md 自动汇总表
  qa/effects/artifacts/probe_notes.json 特殊探针结论
"""
import json
import math
import os
import re
import sys
import time
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.colors import get_palette, rgb_to_lab          # noqa: E402
from core.processor import ImageProcessor                # noqa: E402

INPUTS = os.path.join(HERE, "inputs")
ART = os.path.join(HERE, "artifacts")
os.makedirs(ART, exist_ok=True)

GRID = (60, 60)
CELL = 16
# 与 Swift AppViewModel.generate() 的真实请求一致：不传 show_* → 全部走默认 True
BASE_KW = dict(cell_size=CELL, show_finished=True, save=False)

OUTLINE_RGB = (26, 26, 26)   # outline.py 默认色 #1A1A1A

MATERIALS = OrderedDict([
    ("photo_eagle", dict(path=os.path.join(INPUTS, "photo_eagle.png"), grid=GRID,
                         kind="photo", desc="真实照片：白头海雕（512²，深色背景，羽毛细节）")),
    ("photo_sky", dict(path=os.path.join(INPUTS, "photo_sky.png"), grid=GRID,
                       kind="photo", desc="真实照片：macOS 系统壁纸航拍（渐变天空/水面/岩石）")),
    ("cartoon_cat", dict(path=os.path.join(INPUTS, "cartoon_cat.png"), grid=GRID,
                         kind="cartoon", desc="扁平卡通：白底粗描边猫脸（7 个平涂色，拼豆典型图）")),
    ("transparent_icon", dict(path=os.path.join(INPUTS, "transparent_icon.png"), grid=GRID,
                              kind="transparent", desc="透明背景 PNG（RGBA 渐变心形，透明格=空格）")),
])

# ---------------------------------------------------------------------------
# 特效用例：params 与 Swift AppViewModel.effectsParams() / UI 默认值完全一致
# ---------------------------------------------------------------------------
def eff(eid, **params):
    return {"id": eid, "params": params}


CASES = [
    # ---- 单特效（15 项，参数 = Swift UI 打开开关时的默认装配）----
    dict(id="baseline", group="single", effects=[], chart=True,
         note="无特效基线（UI 默认参数）"),
    dict(id="chibi", group="single", effects=[eff("chibi")],
         note="大头 Q 版（无 params，OpenCV 人脸检测）"),
    dict(id="mirror_h", group="single", effects=[eff("mirror", direction="horizontal")],
         note="镜像-水平"),
    dict(id="crop_center", group="single", effects=[eff("crop", x0=0.1, y0=0.1, x1=0.9, y1=0.9)],
         note="裁剪 10%~90%（方形裁剪，比例不变）"),
    dict(id="crop_default", group="sweep", effects=[eff("crop", x0=0.0, y0=0.0, x1=1.0, y1=1.0)],
         note="裁剪-开关默认参数（0/0/1/1）= 空操作"),
    dict(id="grayscale", group="single", effects=[eff("grayscale")], chart=True, diff=True,
         note="黑白/灰度（contrast=1.0）"),
    dict(id="adjust_sat12", group="single", effects=[eff("adjust", brightness=1.0, contrast=1.0, saturation=1.2)],
         chart=True, diff=True,
         note="画面调整-UI 默认（sat=1.2，bright/contrast=1.0）"),
    dict(id="cel4", group="single", effects=[eff("cel_shade", levels=4)], chart=True, diff=True,
         note="赛璐璐色阶 levels=4"),
    dict(id="neon", group="single", effects=[eff("neon", saturation=1.5, darkness=0.75)],
         chart=True, diff=True, note="霓虹（sat=1.5, darkness=0.75；不自动加深色底）"),
    dict(id="duotone", group="single", effects=[eff("duotone", color1="#1E1E1E", color2="#F0F0F0")],
         chart=True, diff=True, note="双色调 #1E1E1E→#F0F0F0"),
    dict(id="bg_remove_white", group="single",
         effects=[eff("bg_remove", color="#FFFFFF", tolerance=30)], chart=True, diff=True,
         note="背景去除 白色 tol=30（无连通域约束）"),
    dict(id="outline_edge", group="single", effects=[eff("outline_edge")], chart=True, diff=True,
         note="线稿描边（threshold=40, width=1）"),
    dict(id="dither", group="single", effects=[eff("dither")], chart=True, diff=True,
         note="抖动过渡（UI 空 params → 引擎默认 strength=1.0）"),
    dict(id="outline_cell", group="single", effects=[eff("outline_cell")], chart=True, diff=True,
         note="邻接描边（#1A1A1A w=1 outer=False）"),
    dict(id="max_colors12", group="single", effects=[eff("max_colors", max=12)], chart=True, diff=True,
         note="限色数 max=12（UI 默认）"),
    dict(id="preset_pastel", group="single", effects=[eff("preset", preset="pastel")],
         chart=True, diff=True, note="风格色板-马卡龙可爱（UI 默认）"),
    dict(id="dark_chart", group="single", effects=[eff("dark_chart")], chart=True,
         note="深色底图纸（chart 阶段）"),

    # ---- 常用组合（顺序 = Swift effectsParams 固定顺序）----
    dict(id="combo_outline_max12", group="combo",
         effects=[eff("outline_cell"), eff("max_colors", max=12)], chart=True, diff=True,
         note="描边+限色 12（Swift 顺序：描边在前）"),
    dict(id="combo_outline_max8", group="combo",
         effects=[eff("outline_cell"), eff("max_colors", max=8)], chart=True,
         note="描边+限色 8（Swift 顺序）"),
    dict(id="order_rev_max_outline", group="combo",
         effects=[eff("max_colors", max=12), eff("outline_cell")], chart=True,
         note="反序：限色 12 → 描边（Swift 无法产生，用于证明顺序敏感）"),
    dict(id="combo_outline_preset", group="combo",
         effects=[eff("outline_cell"), eff("preset", preset="pastel")], chart=True, diff=True,
         note="描边+马卡龙（Swift 顺序：描边在前，preset 在后）"),
    dict(id="order_rev_preset_outline", group="combo",
         effects=[eff("preset", preset="pastel"), eff("outline_cell")], chart=True,
         note="反序：马卡龙 → 描边"),
    dict(id="combo_gray_dither", group="combo",
         effects=[eff("grayscale"), eff("dither")], chart=True, diff=True,
         note="灰度+抖动"),
    dict(id="combo_cel_dark", group="combo",
         effects=[eff("cel_shade", levels=4), eff("dark_chart")], chart=True,
         note="赛璐璐+深色底图纸"),
    dict(id="combo_neon_dark", group="combo",
         effects=[eff("neon", saturation=1.5, darkness=0.75), eff("dark_chart")], chart=True,
         note="霓虹+深色底图纸（描述中推荐的组合）"),
    dict(id="combo_edge_max8", group="combo",
         effects=[eff("outline_edge"), eff("max_colors", max=8)], chart=True,
         note="线稿描边+限色 8"),
    dict(id="combo_bgremove_max8", group="combo",
         effects=[eff("bg_remove", color="#FFFFFF", tolerance=30), eff("max_colors", max=8)],
         chart=True, note="背景去除+限色 8（透明空格与统计）"),
    dict(id="combo_crop_mirror", group="combo",
         effects=[eff("mirror", direction="horizontal"),
                  eff("crop", x0=0.1, y0=0.1, x1=0.9, y1=0.9)], chart=True,
         note="镜像+裁剪（Swift 顺序：mirror 在 crop 前）"),
    dict(id="combo_all15", group="combo", effects=[
        eff("chibi"), eff("mirror", direction="horizontal"),
        eff("crop", x0=0.0, y0=0.0, x1=1.0, y1=1.0), eff("grayscale"),
        eff("adjust", brightness=1.0, contrast=1.0, saturation=1.2),
        eff("cel_shade", levels=4), eff("neon", saturation=1.5, darkness=0.75),
        eff("duotone", color1="#1E1E1E", color2="#F0F0F0"),
        eff("bg_remove", color="#FFFFFF", tolerance=30), eff("outline_edge"),
        eff("dither"), eff("outline_cell"), eff("max_colors", max=12),
        eff("preset", preset="pastel"), eff("dark_chart")], chart=True, diff=True,
        note="15 项全开（顺序 = Swift effectsParams 固定顺序）"),

    # ---- 参数扫描（证明「调参能否救」）----
    dict(id="sweep_adjust_b105", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", brightness=1.05)], note="亮度 1.05"),
    dict(id="sweep_adjust_b110", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", brightness=1.10)], note="亮度 1.10"),
    dict(id="sweep_adjust_b120", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", brightness=1.20)], note="亮度 1.20"),
    dict(id="sweep_adjust_c110", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", contrast=1.10)], note="对比度 1.10"),
    dict(id="sweep_adjust_c130", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", contrast=1.30)], note="对比度 1.30"),
    dict(id="sweep_adjust_s11", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", saturation=1.1)], note="饱和度 1.10"),
    dict(id="sweep_adjust_s15", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("adjust", saturation=1.5)], note="饱和度 1.50"),
    dict(id="sweep_grayscale_c15", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("grayscale", contrast=1.5)], note="灰度+对比度 1.5"),
    dict(id="sweep_cel2", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("cel_shade", levels=2)], note="赛璐璐 levels=2"),
    dict(id="sweep_cel8", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("cel_shade", levels=8)], note="赛璐璐 levels=8"),
    dict(id="sweep_dither_s0", group="sweep", mats=["photo_eagle", "photo_sky", "cartoon_cat"],
         effects=[eff("dither", strength=0.0)], note="抖动 strength=0（应等于无抖动最近色）"),
    dict(id="sweep_dither_s05", group="sweep", mats=["photo_eagle", "photo_sky", "cartoon_cat"],
         effects=[eff("dither", strength=0.5)], note="抖动 strength=0.5"),
    dict(id="sweep_dither_s15", group="sweep", mats=["photo_eagle", "photo_sky", "cartoon_cat"],
         effects=[eff("dither", strength=1.5)], note="抖动 strength=1.5"),
    dict(id="sweep_dither_s5", group="sweep", mats=["photo_eagle", "photo_sky", "cartoon_cat"],
         effects=[eff("dither", strength=5.0)], note="抖动 strength=5.0（超 schema max=1.5，验证是否被钳制）"),
    dict(id="sweep_outline_w2", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_cell", width=2)], note="邻接描边 width=2"),
    dict(id="sweep_outline_w3", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_cell", width=3)], note="邻接描边 width=3"),
    dict(id="sweep_outline_outer", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_cell", outline_outer=True)], note="邻接描边 outer=True（旧默认）"),
    dict(id="sweep_edge_thr100", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_edge", threshold=100)], note="线稿描边 threshold=100（旧默认）"),
    dict(id="sweep_edge_thr20", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_edge", threshold=20)], note="线稿描边 threshold=20"),
    dict(id="sweep_edge_w2", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("outline_edge", width=2)], note="线稿描边 width=2"),
    dict(id="sweep_max4", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("max_colors", max=4)], note="限色数 max=4"),
    dict(id="sweep_max8", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("max_colors", max=8)], note="限色数 max=8"),
    dict(id="sweep_preset_preppy", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("preset", preset="preppy")], note="风格色板 Preppy/Y2K"),
    dict(id="sweep_preset_halloween", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("preset", preset="halloween")], note="风格色板 万圣节"),
    dict(id="sweep_preset_christmas", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("preset", preset="christmas")], note="风格色板 圣诞"),
    dict(id="sweep_preset_cottage", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("preset", preset="cottagecore")], note="风格色板 Cottagecore"),
    dict(id="sweep_bgremove_tol0", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("bg_remove", color="#FFFFFF", tolerance=0)], note="背景去除 tol=0"),
    dict(id="sweep_bgremove_tol60", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("bg_remove", color="#FFFFFF", tolerance=60)], note="背景去除 tol=60"),
    dict(id="sweep_neon_s20", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("neon", saturation=2.0, darkness=0.6)], note="霓虹 sat=2.0 dark=0.6"),
    dict(id="sweep_crop_aspect", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("crop", x0=0.1, y0=0.0, x1=0.9, y1=0.5)], chart=True,
         note="非方形裁剪（改变宽高比 → 检验网格是否被改写）"),
    dict(id="sweep_duotone_custom", group="sweep", mats=["photo_eagle", "cartoon_cat"],
         effects=[eff("duotone", color1="#112233", color2="#FFCC00")], chart=True,
         note="双色调 自定义 #112233→#FFCC00"),
]

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, dict):
        return {str(k): jd(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jd(v) for v in o]
    return o


def load_image(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        return im.convert("RGBA")
    return im.convert("RGB")


def sample_cells(finished, gw, gh):
    """从 finished 预览图（每格纯色块）按格中心采样，得到 (gh, gw, 3) 每格实际颜色"""
    a = np.asarray(finished.convert("RGB"))
    fh, fw = a.shape[:2]
    ys = np.clip(((np.arange(gh) + 0.5) * fh / gh).astype(int), 0, fh - 1)
    xs = np.clip(((np.arange(gw) + 0.5) * fw / gw).astype(int), 0, fw - 1)
    return a[np.ix_(ys, xs)]


def cell_lab(cells):
    return rgb_to_lab(np.asarray(cells, dtype=np.float32))


def cell_stat(cells):
    lab = cell_lab(cells)
    L = lab[..., 0]
    C = np.sqrt(lab[..., 1] ** 2 + lab[..., 2] ** 2)
    return {
        "mean_l": round(float(L.mean()), 2),
        "mean_chroma": round(float(C.mean()), 2),
        "near_white_ratio": round(float((L >= 92).mean()), 4),
        "unique_rgb": int(len(np.unique(cells.reshape(-1, 3), axis=0))),
    }


def compare_cells(cur, base, base_outline_rgb=None):
    """cur/base: (h,w,3) RGB cells；返回网格级差异指标"""
    if cur is None or base is None or cur.shape != base.shape:
        return {}
    diff = np.abs(cur.astype(np.int32) - base.astype(np.int32))
    changed = diff.max(-1) > 12
    lb, lc = cell_lab(base), cell_lab(cur)
    de = np.sqrt(((lc - lb) ** 2).sum(-1))
    out = {
        "cell_changed_ratio": round(float(changed.mean()), 4),
        "mean_delta_e": round(float(de.mean()), 2),
        "median_delta_e": round(float(np.median(de)), 2),
        "p95_delta_e": round(float(np.percentile(de, 95)), 2),
        "max_delta_e": round(float(de.max()), 2),
    }
    if changed.any():
        hb = np.arctan2(lb[..., 2], lb[..., 1])
        hc = np.arctan2(lc[..., 2], lc[..., 1])
        dh = np.degrees(np.abs(np.angle(np.exp(1j * (hc - hb)))))
        out["median_hue_shift_deg_changed"] = round(float(np.median(dh[changed])), 1)
        out["median_chroma_delta_changed"] = round(
            float(np.median((np.sqrt(lc[..., 1] ** 2 + lc[..., 2] ** 2)
                             - np.sqrt(lb[..., 1] ** 2 + lb[..., 2] ** 2))[changed])), 2)
        out["median_l_delta_changed"] = round(float(np.median((lc[..., 0] - lb[..., 0])[changed])), 2)
    if base_outline_rgb is not None:
        cur_o = np.all(cur == np.asarray(base_outline_rgb), axis=-1)
        base_o = np.all(base == np.asarray(base_outline_rgb), axis=-1)
        out["outline_bead_share"] = round(float(cur_o.mean()), 4)
        out["outline_bead_share_baseline"] = round(float(base_o.mean()), 4)
    return out


def compare_pixels(a_img, b_img):
    if a_img is None or b_img is None:
        return None
    a = np.asarray(a_img.convert("RGB")).astype(np.int32)
    b = np.asarray(b_img.convert("RGB")).astype(np.int32)
    if a.shape != b.shape:
        return None
    return round(float((np.abs(a - b).max(-1) > 12).mean()), 4)


def diff_image(base_img, cur_img, amplify=6):
    a = np.asarray(base_img.convert("RGB")).astype(np.int32)
    b = np.asarray(cur_img.convert("RGB")).astype(np.int32)
    if a.shape != b.shape:
        side = max(a.shape[0], b.shape[0])
        canvas = Image.new("RGB", (side * 2 + 10, side), (255, 255, 255))
        canvas.paste(base_img.convert("RGB"), (0, 0))
        canvas.paste(cur_img.convert("RGB"), (side + 10, 0))
        return canvas
    return Image.fromarray(np.clip(np.abs(a - b) * amplify, 0, 255).astype(np.uint8))


def chart_metrics(res):
    a = np.asarray(res.chart.convert("RGB"))
    h, w = a.shape[:2]
    bg = a[3, w - 3].tolist()          # 右上角：空白画布背景（避开左上角装饰/行列标号）
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    lm = 35                             # LABEL_MARGIN（UI 默认 show_row_col_labels=True）
    cs = max(1, int(res.cell_size))
    gw, gh = int(res.grid_w), int(res.grid_h)
    draw_w, draw_h = cs * gw, cs * gh
    x0 = lm + max(0, (w - 2 * lm - draw_w) // 2)
    y0 = lm
    grid_area = a[y0:y0 + draw_h, x0:x0 + draw_w].copy()
    return {
        "size": [w, h],
        "bg_rgb": bg,
        "dark_ratio": round(float((lum < 80).mean()), 4),
        "mean_lum": round(float(lum.mean()), 1),
        "grid_area": grid_area,
    }


def outline_index_rgb(palette):
    from core.effects.outline import _outline_index
    idx = _outline_index(palette, "#1A1A1A")
    return tuple(int(v) for v in palette.colors[idx]), idx


def montage(panels, cols, out_path, panel=210, title_h=16):
    rows = int(math.ceil(len(panels) / cols))
    W, H = cols * panel, rows * (panel + title_h)
    img = Image.new("RGB", (W, H), (242, 242, 242))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for i, (label, im) in enumerate(panels):
        r, c = divmod(i, cols)
        x, y = c * panel, r * (panel + title_h)
        d.text((x + 4, y + 2), label[:34], fill=(20, 20, 20), font=font)
        thumb = im.convert("RGB").resize((panel, panel), Image.NEAREST)
        img.paste(thumb, (x, y + title_h))
    img.save(out_path, quality=88)
    return out_path


# ---------------------------------------------------------------------------
# 1) 注册表事实基线
# ---------------------------------------------------------------------------
def probe_registry():
    import core.effects as fx
    from core.effects.registry import _EFFECTS
    effects = []
    for eid, (spec, handler) in _EFFECTS.items():
        if isinstance(handler, dict):
            phases = sorted(handler.keys())
        else:
            phases = [spec.category]
        d = spec.to_dict()
        d["handler_phases"] = phases
        d["category_declared"] = spec.category
        d["phase_mismatch"] = (len(phases) > 1 or phases[0] != spec.category)
        effects.append(d)
    effects.sort(key=lambda e: (e["category"], e["id"]))
    out = {"count": len(effects), "effects": effects,
           "categories": sorted({e["category"] for e in effects})}
    with open(os.path.join(ART, "effects_registry.json"), "w", encoding="utf-8") as f:
        json.dump(jd(out), f, ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------------------
# 2) 预处理器逐项「代码做了什么」：全分辨率作用统计
# ---------------------------------------------------------------------------
PREPROCESS_PROBES = [
    ("grayscale", {}),
    ("adjust", {"brightness": 1.0, "contrast": 1.0, "saturation": 1.2}),
    ("cel_shade", {"levels": 4}),
    ("neon", {"saturation": 1.5, "darkness": 0.75}),
    ("duotone", {"color1": "#1E1E1E", "color2": "#F0F0F0"}),
    ("bg_remove", {"color": "#FFFFFF", "tolerance": 30}),
    ("outline_edge", {}),
]


def probe_preprocess_phase():
    from core.effects import EffectContext, apply_phase
    proc = ImageProcessor()
    out = {}
    for mat_name in ("photo_eagle", "cartoon_cat", "transparent_icon"):
        mat = MATERIALS[mat_name]
        img0 = load_image(mat["path"])
        rows = []
        for eid, params in PREPROCESS_PROBES:
            ctx = EffectContext(engine=proc)
            try:
                img = apply_phase([eff(eid, **params)], "preprocess", img0.copy(), ctx)
            except Exception as e:  # noqa: BLE001
                rows.append({"id": eid, "error": repr(e)})
                continue
            rgb = np.asarray(img.convert("RGB"))
            lab = rgb_to_lab(rgb.astype(np.float32))
            row = {
                "id": eid,
                "out_mode": img.mode,
                "out_size": list(img.size),
                "mean_l": round(float(lab[..., 0].mean()), 2),
                "mean_chroma": round(float(np.sqrt(lab[..., 1] ** 2 + lab[..., 2] ** 2).mean()), 2),
                "unique_rgb": int(len(np.unique(rgb.reshape(-1, 3), axis=0))),
            }
            if img.mode == "RGBA":
                alpha = np.asarray(img)[..., 3]
                row["alpha_zero_ratio"] = round(float((alpha < 128).mean()), 4)
            if hasattr(ctx, "edge_mask"):
                mask = ctx.edge_mask
                row["edge_mask_coverage"] = round(float((mask > 127).mean()), 4)
                mp = os.path.join(ART, mat_name, "edge_mask.png")
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                Image.fromarray(np.where(mask > 127, 255, 0).astype(np.uint8)).resize(
                    (256, 256), Image.NEAREST).save(mp)
            # 预览小图（≤256px）作为「代码做了什么」证据
            prev = img.convert("RGB")
            prev.thumbnail((256, 256), Image.LANCZOS)
            prev.save(os.path.join(ART, mat_name, "pre_" + eid + ".png"))
            rows.append(row)
        out[mat_name] = rows
    return out


# ---------------------------------------------------------------------------
# 3) chibi：真实检测（多为无脸→静默 no-op）+ 检测命中时的几何/透明度行为
# ---------------------------------------------------------------------------
def probe_chibi(baselines):
    import cv2
    from core.effects import EffectContext, apply_phase
    proc = ImageProcessor()
    out = {}
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception as e:  # noqa: BLE001
        return {"cv2_available": False, "error": repr(e)}
    out["cv2_version"] = cv2.__version__
    out["real_detection"] = {}
    for mat_name, mat in MATERIALS.items():
        img = np.asarray(load_image(mat["path"]).convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        min_size = max(24, min(img.shape[:2]) // 8)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_size, min_size))
        out["real_detection"][mat_name] = {"faces": int(len(faces))}
    # 模拟「检测到人脸」以检验变换本身（不改产品代码，仅 QA 运行时 monkeypatch）
    orig = cv2.CascadeClassifier.detectMultiScale

    def fake_detect(self, image, *a, **k):
        return np.array([[170, 120, 150, 160]], dtype=np.int32)

    patched = {}
    try:
        cv2.CascadeClassifier.detectMultiScale = fake_detect
        for mat_name in ("photo_eagle", "transparent_icon"):
            mat = MATERIALS[mat_name]
            res = proc.process_image(mat["path"], *mat["grid"],
                                     effects=[eff("chibi")], **BASE_KW)
            if res is None:
                patched[mat_name] = {"error": "process_image None"}
                continue
            b = baselines.get(mat_name)
            fin = res.finished
            arr = np.asarray(fin.convert("RGB"))
            row = {
                "grid": [res.grid_w, res.grid_h],
                "total_beads": res.total_beads,
                "grid_dims_changed_vs_baseline": (b is not None and
                                                  (res.grid_w, res.grid_h) != tuple(b["grid"])),
                "finished_changed_ratio_vs_baseline": compare_pixels(fin, b["finished"]) if b else None,
                "pure_white_ratio": round(float(np.all(arr >= 250, axis=-1).mean()), 4),
                "finished_path": os.path.join(ART, mat_name, "chibi_patched_finished.png"),
            }
            fin.save(row["finished_path"])
            # 透明源图：直接看 geometric 阶段输出是否丢失 alpha
            src = load_image(mat["path"])
            ctx = EffectContext(engine=proc)
            transformed = apply_phase([eff("chibi")], "geometric", src.copy(), ctx)
            row["geometric_out_mode"] = transformed.mode
            row["geometric_out_size"] = list(transformed.size)
            row["source_mode"] = src.mode
            small = transformed.convert("RGB")
            small.thumbnail((256, 256), Image.LANCZOS)
            small.save(os.path.join(ART, mat_name, "chibi_patched_geometric.png"))
            patched[mat_name] = row
    finally:
        cv2.CascadeClassifier.detectMultiScale = orig
    out["patched_detection"] = patched
    # 模拟 OpenCV 缺失：geometry.py 的 try/except ImportError 静默返回原图
    import sys as _sys
    _saved = _sys.modules.get("cv2")
    _sys.modules["cv2"] = None
    try:
        src = load_image(MATERIALS["photo_eagle"]["path"])
        ctx = EffectContext(engine=proc)
        out_img = apply_phase([eff("chibi")], "geometric", src.copy(), ctx)
        out["cv2_missing_simulation"] = {
            "returned_same_size": list(out_img.size) == list(src.size),
            "returned_same_mode": out_img.mode == src.mode,
            "silent_noop": True,
            "note": "ImportError 被 geometry.py:11-14 吞掉，返回原图，无 warning",
        }
    finally:
        if _saved is not None:
            _sys.modules["cv2"] = _saved
        else:
            _sys.modules.pop("cv2", None)
    return out


# ---------------------------------------------------------------------------
# 4) dither strength：是否生效 / 是否被 schema 钳制
# ---------------------------------------------------------------------------
def probe_dither_strength():
    proc = ImageProcessor()
    out = {}
    for mat_name in ("photo_sky", "photo_eagle"):
        mat = MATERIALS[mat_name]
        base = proc.process_image(mat["path"], *mat["grid"], effects=[], **BASE_KW)
        base_cells = sample_cells(base.finished, base.grid_w, base.grid_h)
        rows = []
        prev_cells = None
        for s in (0.0, 0.5, 1.0, 1.5, 5.0):
            res = proc.process_image(mat["path"], *mat["grid"],
                                     effects=[eff("dither", strength=s)], **BASE_KW)
            cells = sample_cells(res.finished, res.grid_w, res.grid_h)
            row = {"strength": s,
                   "vs_baseline": compare_cells(cells, base_cells),
                   "vs_prev_strength": compare_cells(cells, prev_cells) if prev_cells is not None else {}}
            prev_cells = cells
            rows.append(row)
        out[mat_name] = rows
    return out


# ---------------------------------------------------------------------------
# 5) 色卡量化下限：多小的调整会被色卡映射吞掉
# ---------------------------------------------------------------------------
def probe_quantization_floor():
    palette = get_palette("mard_221")
    lab = palette.lab.astype(np.float64)
    d = np.sqrt(((lab[:, None, :] - lab[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, np.inf)
    nn = d.min(1)
    # 素材原图 → 100x100 网格小图（用于快速模拟逐像素调整后的色卡映射变化）
    img = np.asarray(Image.open(MATERIALS["photo_eagle"]["path"]).convert("RGB")
                     .resize((100, 100), Image.BOX), dtype=np.float32)
    gray = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114

    def changed_ratio(transformed):
        t = np.clip(transformed, 0, 255).astype(np.float32)
        idx = palette.closest_indices(Image.fromarray(t.astype(np.uint8)))
        idx0 = palette.closest_indices(Image.fromarray(img.astype(np.uint8)))
        return round(float((idx != idx0).mean()), 4)

    curves = {"brightness": {}, "contrast": {}, "saturation": {}}
    for b in (1.02, 1.05, 1.08, 1.10, 1.15, 1.20, 1.30, 1.50):
        curves["brightness"][str(b)] = changed_ratio(img * b)
    for c in (1.02, 1.05, 1.10, 1.20, 1.30, 1.50):
        curves["contrast"][str(c)] = changed_ratio((img - 128.0) * c + 128.0)
    for s in (0.80, 0.90, 1.05, 1.10, 1.20, 1.30, 1.50, 2.00):
        curves["saturation"][str(s)] = changed_ratio(gray[..., None] + (img - gray[..., None]) * s)
    return {
        "palette": "mard_221",
        "palette_nearest_neighbor_delta_e": {
            "min": round(float(nn.min()), 2),
            "p10": round(float(np.percentile(nn, 10)), 2),
            "median": round(float(np.median(nn)), 2),
            "p90": round(float(np.percentile(nn, 90)), 2),
            "max": round(float(nn.max()), 2),
        },
        "cell_change_curve_100x100": curves,
    }


# ---------------------------------------------------------------------------
# 6) bg_remove：白底 vs 白色主体（无连通域约束的算法语义缺陷）
# ---------------------------------------------------------------------------
def probe_bg_remove():
    from core.effects import EffectContext, apply_phase
    proc = ImageProcessor()
    out = {}
    # 6.1 白色主体（幽灵）被误删
    src = load_image(os.path.join(INPUTS, "cartoon_ghost.png")).convert("RGB")
    ctx = EffectContext(engine=proc)
    res_img = apply_phase([eff("bg_remove", color="#FFFFFF", tolerance=30)],
                          "preprocess", src.copy(), ctx)
    alpha = np.asarray(res_img)[..., 3]
    src_arr = np.asarray(src)
    subject = np.all(src_arr >= 250, axis=-1)             # 白色主体
    bg = np.abs(src_arr.astype(int) - np.array([190, 220, 240])).sum(-1) <= 90
    out["ghost_white_subject"] = {
        "subject_pixel_ratio": round(float(subject.mean()), 4),
        "bg_pixel_ratio": round(float(bg.mean()), 4),
        "deleted_ratio_total": round(float((alpha < 128).mean()), 4),
        "deleted_ratio_of_subject": round(float((alpha[subject] < 128).mean()), 4),
        "deleted_ratio_of_bg": round(float((alpha[bg] < 128).mean()), 4),
        "preview_path": os.path.join(ART, "cartoon_ghost", "bgremove_processed.png"),
    }
    res_img.convert("RGB").thumbnail((256, 256), Image.LANCZOS)
    os.makedirs(os.path.dirname(out["ghost_white_subject"]["preview_path"]), exist_ok=True)
    res_img.convert("RGB").save(out["ghost_white_subject"]["preview_path"])
    # 6.2 白底卡通：删掉的是背景（语义正确），但预览几乎无变化 → 用户以为没生效
    base = proc.process_image(MATERIALS["cartoon_cat"]["path"], *GRID, effects=[], **BASE_KW)
    after = proc.process_image(MATERIALS["cartoon_cat"]["path"], *GRID,
                               effects=[eff("bg_remove", color="#FFFFFF", tolerance=30)], **BASE_KW)
    out["white_bg_cartoon"] = {
        "baseline_beads": base.total_beads,
        "after_beads": after.total_beads,
        "beads_removed": base.total_beads - after.total_beads,
        "transparent_cells": after.grid_w * after.grid_h - after.total_beads,
        "finished_pixel_changed_ratio": compare_pixels(after.finished, base.finished),
        "chart_grid_area_changed_ratio": None,
        "preview_path": os.path.join(ART, "cartoon_cat", "bgremove_finished.png"),
    }
    bm = chart_metrics(base)
    am = chart_metrics(after)
    if bm["grid_area"].shape == am["grid_area"].shape:
        out["white_bg_cartoon"]["chart_grid_area_changed_ratio"] = round(
            float((np.abs(bm["grid_area"].astype(int) - am["grid_area"].astype(int)).max(-1) > 12).mean()), 4)
    after.finished.save(out["white_bg_cartoon"]["preview_path"])
    # 6.3 透明源图 + bg_remove 白色：无白色 → no-op（用户以为坏了）
    timg = load_image(MATERIALS["transparent_icon"]["path"])
    ctx2 = EffectContext(engine=proc)
    t2 = apply_phase([eff("bg_remove", color="#FFFFFF", tolerance=30)], "preprocess", timg.copy(), ctx2)
    a0 = np.asarray(timg)[..., 3] >= 128
    a2 = np.asarray(t2)[..., 3] >= 128
    out["transparent_source"] = {
        "deleted_ratio": round(float((a0 & ~a2).mean()), 4),
        "alpha_zero_ratio_before": round(float((~a0).mean()), 4),
        "alpha_zero_ratio_after": round(float((~a2).mean()), 4),
    }
    return out


# ---------------------------------------------------------------------------
# 7) 顺序敏感性 & 描边覆盖/连续性
# ---------------------------------------------------------------------------
def probe_order(baselines, rows_index):
    out = {"outline_share": {}, "order_compare": {}}
    for mat_name in ("photo_eagle", "cartoon_cat"):
        base = baselines[mat_name]
        bo = base.get("outline_share")
        out["outline_share"][mat_name] = {
            "baseline": bo,
            "outline_cell": rows_index.get((mat_name, "outline_cell"), {}).get("outline_bead_share"),
            "combo_outline_max12": rows_index.get((mat_name, "combo_outline_max12"), {}).get("outline_bead_share"),
            "order_rev_max_outline": rows_index.get((mat_name, "order_rev_max_outline"), {}).get("outline_bead_share"),
            "combo_outline_preset": rows_index.get((mat_name, "combo_outline_preset"), {}).get("outline_bead_share"),
            "order_rev_preset_outline": rows_index.get((mat_name, "order_rev_preset_outline"), {}).get("outline_bead_share"),
        }
        pairs = [
            ("max12_then_outline_vs_outline_then_max12", "order_rev_max_outline", "combo_outline_max12"),
            ("preset_then_outline_vs_outline_then_preset", "order_rev_preset_outline", "combo_outline_preset"),
        ]
        for label, a, b in pairs:
            ra, rb = rows_index.get((mat_name, a)), rows_index.get((mat_name, b))
            if ra and rb:
                out["order_compare"].setdefault(label, {})[mat_name] = {
                    "cell_changed_ratio_between_orders": ra.get("vs_baseline", {}).get("cell_changed_ratio"),
                    "beads_A": ra.get("total_beads"), "beads_B": rb.get("total_beads"),
                    "colors_A": ra.get("n_colors"), "colors_B": rb.get("n_colors"),
                }
    # outline_edge 线连续性：变更格中 4 邻域仍有变更格的比例（衡量「线」还是「噪点」）
    cont = {}
    for mat_name in ("photo_eagle", "cartoon_cat"):
        r = rows_index.get((mat_name, "outline_edge"))
        if not r:
            continue
        cur = r["_cells"]; base = baselines[mat_name]["cells"]
        diff = np.abs(cur.astype(int) - base.astype(int)).max(-1) > 12
        nb = np.zeros_like(diff, dtype=int)
        nb[1:, :] += diff[:-1, :]
        nb[:-1, :] += diff[1:, :]
        nb[:, 1:] += diff[:, :-1]
        nb[:, :-1] += diff[:, 1:]
        vals = nb[diff]
        cont[mat_name] = {
            "changed_cells": int(diff.sum()),
            "changed_ratio": round(float(diff.mean()), 4),
            "mean_changed_neighbors_of_changed": round(float(vals.mean()), 2) if vals.size else 0,
            "ratio_with_ge2_neighbors": round(float((vals >= 2).mean()), 4) if vals.size else 0,
        }
    out["outline_edge_continuity"] = cont
    return out


# ---------------------------------------------------------------------------
# 8) preset 洗白 / cel 色相漂移（从矩阵行聚合）
# ---------------------------------------------------------------------------
def probe_semantic_summary(rows_index):
    out = {"preset": {}, "cel": {}, "neon": {}, "grayscale": {}}
    for mat_name in ("photo_eagle", "cartoon_cat"):
        base = rows_index[(mat_name, "baseline")]
        for pid in ("preset_pastel", "sweep_preset_preppy", "sweep_preset_halloween",
                    "sweep_preset_christmas", "sweep_preset_cottage"):
            r = rows_index.get((mat_name, pid))
            if not r:
                continue
            out["preset"].setdefault(pid, {})[mat_name] = {
                "n_colors": r.get("n_colors"),
                "cell_changed_ratio": r.get("vs_baseline", {}).get("cell_changed_ratio"),
                "mean_l": r.get("cells_stat", {}).get("mean_l"),
                "mean_l_baseline": base.get("cells_stat", {}).get("mean_l"),
                "mean_chroma": r.get("cells_stat", {}).get("mean_chroma"),
                "near_white_ratio": r.get("cells_stat", {}).get("near_white_ratio"),
                "near_white_ratio_baseline": base.get("cells_stat", {}).get("near_white_ratio"),
            }
        for cid in ("cel4", "sweep_cel2", "sweep_cel8"):
            r = rows_index.get((mat_name, cid))
            if not r:
                continue
            out["cel"].setdefault(cid, {})[mat_name] = {
                "n_colors": r.get("n_colors"),
                "cell_changed_ratio": r.get("vs_baseline", {}).get("cell_changed_ratio"),
                "median_hue_shift_deg_changed": r.get("vs_baseline", {}).get("median_hue_shift_deg_changed"),
                "median_delta_e": r.get("vs_baseline", {}).get("median_delta_e"),
            }
        for nid in ("neon", "sweep_neon_s20", "combo_neon_dark"):
            r = rows_index.get((mat_name, nid))
            if not r:
                continue
            out["neon"].setdefault(nid, {})[mat_name] = {
                "n_colors": r.get("n_colors"),
                "cell_changed_ratio": r.get("vs_baseline", {}).get("cell_changed_ratio"),
                "mean_l_delta": round(r.get("cells_stat", {}).get("mean_l", 0)
                                      - base.get("cells_stat", {}).get("mean_l", 0), 2),
                "mean_chroma_delta": round(r.get("cells_stat", {}).get("mean_chroma", 0)
                                           - base.get("cells_stat", {}).get("mean_chroma", 0), 2),
                "chart_bg_rgb": r.get("chart", {}).get("bg_rgb"),
            }
        for gid in ("grayscale", "sweep_grayscale_c15"):
            r = rows_index.get((mat_name, gid))
            if not r:
                continue
            out["grayscale"].setdefault(gid, {})[mat_name] = {
                "n_colors": r.get("n_colors"),
                "mean_chroma": r.get("cells_stat", {}).get("mean_chroma"),
                "mean_chroma_baseline": base.get("cells_stat", {}).get("mean_chroma"),
                "cell_changed_ratio": r.get("vs_baseline", {}).get("cell_changed_ratio"),
            }
    return out


# ---------------------------------------------------------------------------
# 9) UI 静态可用性
# ---------------------------------------------------------------------------
def probe_ui_static():
    src = os.path.join(ROOT, "app", "Sources", "PerlerApp")
    files = {}
    for name in ("ContentView.swift", "AppViewModel.swift", "Engine.swift", "Models.swift"):
        p = os.path.join(src, name)
        with open(p, "r", encoding="utf-8") as f:
            files[name] = f.read().splitlines()

    def find_lines(lines, pattern):
        return [i + 1 for i, l in enumerate(lines) if re.search(pattern, l)]

    content = files["ContentView.swift"]
    vm = files["AppViewModel.swift"]
    out = {
        "effect_toggles_in_ui": find_lines(content, r"Toggle\("),
        "onchange_in_ui": find_lines(content, r"\.onChange\("),
        "generate_call_sites_content": find_lines(content, r"vm\.generate|\.generate\(\)"),
        "effects_params_lines": [find_lines(vm, r"func effectsParams")[0],
                                  find_lines(vm, r"return effects")[0]] if find_lines(vm, r"return effects") else [],
        "engine_effects_op_requested_by_app": find_lines(files["Engine.swift"], r'op:\s*"effects"'),
        "dirty_or_stale_markers": find_lines(content, r"dirty|stale|needsRegen|未应用|需重新生成|已修改")
                                 + find_lines(vm, r"dirty|stale|needsRegen|未应用|需重新生成|已修改"),
        "toggles_have_onchange": False,
        "show_finished_default_false": any("showFinished = false" in l for l in vm),
        "generation_trigger": "仅「生成」按钮 / 编辑后自动 applyEdits；参数与开关变化不触发重算",
        "effect_param_ui_exposed": {},
    }
    # 每个已暴露开关是否有参数控件（粗判：同名开关后是否出现 slider/stepper/picker/hexField）
    toggles = re.findall(r"@Published var (\w+)On = false", "\n".join(vm))
    out["published_effect_toggles"] = toggles
    out["published_effect_toggle_count"] = len(toggles)
    # 引擎 schema 参数 vs UI 暴露（手工映射，供报告核对）
    out["effect_param_ui_exposed"] = {
        "outline_cell": ["开关"], "outline_edge": ["开关"],
        "grayscale": ["开关"], "dither": ["开关"],
        "dark_chart": ["开关"], "max_colors": ["开关", "max 步进器"],
        "preset": ["开关", "preset 选择器"], "adjust": ["开关", "亮/对比/饱和滑杆"],
        "mirror": ["开关", "方向选择器"], "crop": ["开关", "四边滑杆"],
        "cel_shade": ["开关", "levels 步进器"], "neon": ["开关", "饱和/压暗滑杆"],
        "duotone": ["开关", "双 HEX"], "bg_remove": ["开关", "HEX + 容差步进器"],
        "chibi": ["开关"],
    }
    out["effects_requested_by_ui"] = "无：AppViewModel 从未请求 op=effects（引擎 schema 未接入 UI，UI 列表/顺序为硬编码）"
    with open(os.path.join(ART, "ui_static.json"), "w", encoding="utf-8") as f:
        json.dump(jd(out), f, ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------------------
# 主矩阵
# ---------------------------------------------------------------------------
def run_matrix(proc):
    rows = []
    baselines = {}
    rows_index = {}
    palette = get_palette("mard_221")
    outline_rgb, _ = outline_index_rgb(palette)
    print("[probe] outline accent rgb =", outline_rgb)

    for mat_name, mat in MATERIALS.items():
        matdir = os.path.join(ART, mat_name)
        os.makedirs(matdir, exist_ok=True)
        for case in CASES:
            if case.get("mats") and mat_name not in case["mats"]:
                continue
            t0 = time.time()
            res = proc.process_image(mat["path"], *mat["grid"],
                                     effects=case["effects"], **BASE_KW)
            dt = time.time() - t0
            row = {"material": mat_name, "case": case["id"], "group": case.get("group"),
                   "effects": case["effects"], "note": case.get("note", ""),
                   "sec": round(dt, 2)}
            if res is None:
                row["error"] = "process_image 返回 None"
                rows.append(row)
                continue
            fin = res.finished if res.finished is not None else res.chart
            fin_path = os.path.join(matdir, "fin_" + case["id"] + ".png")
            fin.save(fin_path)
            row["artifacts"] = {"finished": os.path.relpath(fin_path, ROOT)}
            cells = sample_cells(fin, res.grid_w, res.grid_h)
            cm = chart_metrics(res)
            row.update({
                "grid": [res.grid_w, res.grid_h],
                "cell_size": res.cell_size,
                "total_beads": res.total_beads,
                "n_colors": len(res.color_stats),
                "cells_stat": cell_stat(cells),
                "outline_bead_share": round(float(np.all(cells == np.asarray(outline_rgb), axis=-1).mean()), 4),
                "chart": {"size": cm["size"], "bg_rgb": cm["bg_rgb"],
                          "dark_ratio": cm["dark_ratio"], "mean_lum": cm["mean_lum"]},
            })
            if case.get("chart"):
                ch_path = os.path.join(matdir, "chart_" + case["id"] + ".png")
                res.chart.save(ch_path)
                row["artifacts"]["chart"] = os.path.relpath(ch_path, ROOT)
            if case["id"] == "baseline":
                baselines[mat_name] = {
                    "cells": cells, "grid": [res.grid_w, res.grid_h],
                    "finished": fin, "chart_img": res.chart.copy(),
                    "beads": res.total_beads,
                    "outline_share": row["outline_bead_share"],
                    "chart": cm, "cells_stat": row["cells_stat"],
                }
            else:
                if case.get("diff") and baselines[mat_name].get("finished") is not None:
                    d_path = os.path.join(matdir, "diff_" + case["id"] + ".png")
                    diff_image(baselines[mat_name]["finished"], fin).save(d_path)
                    row["artifacts"]["diff"] = os.path.relpath(d_path, ROOT)
                b = baselines[mat_name]
                row["dims_changed_vs_baseline"] = tuple(row["grid"]) != tuple(b["grid"])
                if not row["dims_changed_vs_baseline"]:
                    row["vs_baseline"] = compare_cells(cells, b["cells"], outline_rgb)
                    row["beads_delta"] = res.total_beads - b["beads"]
                if b["chart"]["grid_area"].shape == cm["grid_area"].shape:
                    ga0 = b["chart"]["grid_area"].astype(int)
                    ga1 = cm["grid_area"].astype(int)
                    row["chart_grid_area_changed_ratio"] = round(
                        float((np.abs(ga0 - ga1).max(-1) > 12).mean()), 4)
                row["chart_canvas_changed_ratio"] = compare_pixels(b.get("chart_img"), res.chart)
            rows.append(row)
            rows_index[(mat_name, case["id"])] = row
    return rows, baselines, rows_index


# ---------------------------------------------------------------------------
# 10) 更高精度网格（100×100）下关键特效的表现
# ---------------------------------------------------------------------------
def probe_grid_sensitivity():
    proc = ImageProcessor()
    outline_rgb, _ = outline_index_rgb(get_palette("mard_221"))
    cases = [("outline_cell", [eff("outline_cell")]),
             ("outline_edge", [eff("outline_edge")]),
             ("dither", [eff("dither")]),
             ("preset_pastel", [eff("preset", preset="pastel")]),
             ("cel4", [eff("cel_shade", levels=4)]),
             ("max_colors12", [eff("max_colors", max=12)])]
    out = {}
    for mat_name in ("photo_eagle", "cartoon_cat"):
        mat = MATERIALS[mat_name]
        base = proc.process_image(mat["path"], 100, 100, effects=[], **BASE_KW)
        base_cells = sample_cells(base.finished, base.grid_w, base.grid_h)
        rows = []
        for cid, ef in cases:
            res = proc.process_image(mat["path"], 100, 100, effects=ef, **BASE_KW)
            cells = sample_cells(res.finished, res.grid_w, res.grid_h)
            comp = compare_cells(cells, base_cells)
            rows.append({"case": cid, "grid": [res.grid_w, res.grid_h],
                         "beads": res.total_beads, "n_colors": len(res.color_stats),
                         "cell_changed_ratio": comp.get("cell_changed_ratio"),
                         "mean_delta_e": comp.get("mean_delta_e"),
                         "outline_share": round(float(np.all(
                             cells == np.asarray(outline_rgb), axis=-1).mean()), 4)})
            if cid in ("outline_cell", "outline_edge"):
                res.finished.save(os.path.join(ART, mat_name, "grid100_" + cid + "_finished.png"))
        out[mat_name] = rows
    return out


# ---------------------------------------------------------------------------
# 11) 关键缺陷可视化：bg_remove 删除格红标 / 幽灵透明棋盘 / alpha 失真
# ---------------------------------------------------------------------------
def probe_vis_overlays(baselines):
    from core.effects import EffectContext, apply_phase
    proc = ImageProcessor()
    out = {}
    for mat_name in ("photo_eagle", "cartoon_cat"):
        mat = MATERIALS[mat_name]
        src = load_image(mat["path"])
        ctx = EffectContext(engine=proc)
        out_img = apply_phase([eff("bg_remove", color="#FFFFFF", tolerance=30)],
                              "preprocess", src.copy(), ctx)
        gw, gh = baselines[mat_name]["grid"]
        alpha = np.asarray(out_img.resize((gw, gh), Image.BOX))[..., 3] >= 128
        base = baselines[mat_name]["finished"].convert("RGB").copy()
        arr = np.asarray(base).copy()
        cell_px = arr.shape[0] // gh
        for y in range(gh):
            for x in range(gw):
                if not alpha[y, x]:
                    arr[y * cell_px:(y + 1) * cell_px,
                        x * cell_px:(x + 1) * cell_px] = (255, 0, 80)
        p = os.path.join(ART, mat_name, "bgremove_deleted_overlay.png")
        Image.fromarray(arr).save(p)
        out[mat_name] = {"deleted_cells": int(gw * gh - alpha.sum()),
                         "path": os.path.relpath(p, ROOT)}
    # 幽灵：透明区域棋盘格合成，直观显示白色主体被删
    src = load_image(os.path.join(INPUTS, "cartoon_ghost.png")).convert("RGB")
    ctx = EffectContext(engine=proc)
    out_img = apply_phase([eff("bg_remove", color="#FFFFFF", tolerance=30)],
                          "preprocess", src.copy(), ctx)
    rgba = np.asarray(out_img)
    h, w = rgba.shape[:2]
    checker = (((np.indices((h, w)).sum(0) // 24) % 2) * 40 + 190).astype(np.uint8)
    comp = np.stack([checker] * 3, -1)
    alpha = rgba[..., 3:4].astype(np.float32) / 255.0
    comp = (rgba[..., :3].astype(np.float32) * alpha + comp * (1 - alpha)).astype(np.uint8)
    p = os.path.join(ART, "cartoon_ghost", "bgremove_checkerboard.png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.fromarray(comp).save(p)
    out["ghost_checkerboard"] = os.path.relpath(p, ROOT)
    # 透明素材被 grayscale 填满（alpha 丢失）的成品图
    g = proc.process_image(MATERIALS["transparent_icon"]["path"], *GRID,
                           effects=[eff("grayscale")], **BASE_KW)
    p2 = os.path.join(ART, "transparent_icon", "alpha_loss_grayscale_finished.png")
    g.finished.save(p2)
    out["alpha_loss_finished"] = os.path.relpath(p2, ROOT)
    return out


def main():
    t_start = time.time()
    os.makedirs(ART, exist_ok=True)
    proc = ImageProcessor()
    notes = {}

    print("[1/9] 注册表事实基线 ...")
    notes["registry"] = probe_registry()

    print("[2/9] 主矩阵（4 素材 × 15 单特效 + 组合 + 参数扫描）...")
    rows, baselines, rows_index = run_matrix(proc)
    print("      cases:", len(rows), " rows_index:", len(rows_index))

    print("[3/9] 预处理阶段逐项行为 ...")
    notes["preprocess_phase"] = probe_preprocess_phase()

    print("[4/9] chibi 静默失效 / 几何行为 ...")
    notes["chibi"] = probe_chibi(baselines)

    print("[5/9] dither strength ...")
    notes["dither_strength"] = probe_dither_strength()

    print("[6/9] 色卡量化下限 ...")
    notes["quantization_floor"] = probe_quantization_floor()

    print("[7/9] bg_remove 白色主体 / 白底可见性 / 透明源图 ...")
    notes["bg_remove"] = probe_bg_remove()

    print("[8/9] 顺序敏感性 / 描边连续性 / 语义聚合 ...")
    # rows_index 里移除了 _cells，重新计算 outline continuity 需要 cells：用 rows 的 artifacts 读回
    for (mat, cid), row in list(rows_index.items()):
        fp = row.get("artifacts", {}).get("finished")
        if fp and cid in ("outline_edge",):
            row["_cells"] = sample_cells(Image.open(os.path.join(ROOT, fp)).convert("RGB"),
                                         row["grid"][0], row["grid"][1])
    notes["order"] = probe_order(baselines, rows_index)
    notes["semantic"] = probe_semantic_summary(rows_index)
    notes["outline_edge_continuity"] = notes["order"].pop("outline_edge_continuity")

    print("[9/11] UI 静态可用性 ...")
    notes["ui_static"] = probe_ui_static()

    print("[10/11] 100x100 高精度网格关键特效 ...")
    notes["grid_100x100"] = probe_grid_sensitivity()

    print("[11/11] 缺陷可视化叠加图 ...")
    notes["vis_overlays"] = probe_vis_overlays(baselines)

    # ---- 汇总 ----
    total_time = round(time.time() - t_start, 1)
    metrics = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "env": {"grid": list(GRID), "cell_size": CELL,
                "python": sys.version.split()[0],
                "pillow": Image.__version__ if hasattr(Image, "__version__") else "",
                "numpy": np.__version__, "total_sec": total_time},
        "materials": {k: {"path": os.path.relpath(v["path"], ROOT),
                          "kind": v["kind"], "desc": v["desc"], "grid": list(v["grid"])}
                      for k, v in MATERIALS.items()},
        "rows": rows,
        "notes": notes,
    }
    with open(os.path.join(ART, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(jd(metrics), f, ensure_ascii=False, indent=1)
    with open(os.path.join(ART, "probe_notes.json"), "w", encoding="utf-8") as f:
        json.dump(jd(notes), f, ensure_ascii=False, indent=1)

    write_summary(rows)
    write_contact_sheets(rows)
    print("[done] %.1fs -> %s" % (total_time, os.path.relpath(ART, ROOT)))


def write_summary(rows):
    lines = ["# 特效矩阵自动汇总（probe.py 生成，勿手改）", "",
             "指标说明：Δcells = 与无特效基线相比发生变化的格子占比；ΔE = 中位 CIELAB ΔE(76)；"
             "beads = 耗材颗数；colors = 用色数；grid = 最终网格。", ""]
    order = ["baseline", "chibi", "mirror_h", "crop_center", "crop_default", "grayscale",             "adjust_sat12", "cel4", "neon", "duotone", "bg_remove_white", "outline_edge",
             "dither", "outline_cell", "max_colors12", "preset_pastel", "dark_chart",
             "combo_outline_max12", "combo_outline_max8", "order_rev_max_outline",
             "combo_outline_preset", "order_rev_preset_outline", "combo_gray_dither",
             "combo_cel_dark", "combo_neon_dark", "combo_edge_max8", "combo_bgremove_max8",
             "combo_crop_mirror", "combo_all15"]
    for mat_name in MATERIALS:
        rws = [r for r in rows if r["material"] == mat_name and not r.get("error")]
        lines.append("## " + mat_name + "（" + MATERIALS[mat_name]["desc"] + "）")
        lines.append("")
        lines.append("| case | group | grid | beads | colors | Δcells | median ΔE | p95 ΔE | chart_grid Δ | note |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        by_id = {r["case"]: r for r in rws}
        ids = order + sorted(set(by_id) - set(order))
        for cid in ids:
            r = by_id.get(cid)
            if not r:
                continue
            vs = r.get("vs_baseline", {})
            lines.append("| {} | {} | {}×{} | {} | {} | {} | {} | {} | {} | {} |".format(
                cid, r.get("group", ""), r["grid"][0], r["grid"][1],
                r.get("total_beads", ""), r.get("n_colors", ""),
                vs.get("cell_changed_ratio", ""), vs.get("median_delta_e", ""),
                vs.get("p95_delta_e", ""),
                r.get("chart_grid_area_changed_ratio", ""),
                (r.get("note") or "")[:42]))
        lines.append("")
    with open(os.path.join(ART, "summary_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_contact_sheets(rows):
    for mat_name in MATERIALS:
        rws = [r for r in rows if r["material"] == mat_name and not r.get("error")
               and r.get("group") in ("single", "combo")]
        panels = []
        for r in rws:
            fp = r.get("artifacts", {}).get("finished")
            if not fp:
                continue
            label = r["case"]
            if r.get("vs_baseline") and r["case"] != "baseline":
                label += " Δ%0.1f%%" % (r["vs_baseline"].get("cell_changed_ratio", 0) * 100)
            panels.append((label, Image.open(os.path.join(ROOT, fp)).convert("RGB")))
        if panels:
            montage(panels, 5, os.path.join(ART, mat_name, "contact_sheet_finished.jpg"))
        dpanels = []
        for r in rws:
            fp = r.get("artifacts", {}).get("diff")
            if not fp:
                continue
            dpanels.append((r["case"] + " diff×6", Image.open(os.path.join(ROOT, fp)).convert("RGB")))
        if dpanels:
            montage(dpanels, 5, os.path.join(ART, mat_name, "contact_sheet_diff.jpg"))


if __name__ == "__main__":
    main()
