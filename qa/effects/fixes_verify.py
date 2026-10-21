#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa/effects/fixes_verify.py — T5 修复前后对比量化（可复跑）

对 T1 定位的核心缺陷逐项验证修复效果，输出：
  qa/effects/fixes/metrics_after.json
  qa/effects/fixes/{effect}_before_after.jpg
  qa/effects/fixes/*.png（关键 before/after 成品图）
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.colors import get_palette, rgb_to_lab
from core.effects import EffectContext, apply_phase
from core.effects.outline import _outline_index
from core.processor import ImageProcessor

INPUTS = os.path.join(HERE, "inputs")
ART = os.path.join(HERE, "artifacts")
FIX = os.path.join(HERE, "fixes")
os.makedirs(FIX, exist_ok=True)
GRID = (60, 60)
CELL = 16
KW = dict(cell_size=CELL, show_finished=True, save=False)
PAL = get_palette("mard_221")
OUTLINE_RGB = tuple(int(v) for v in PAL.colors[_outline_index(PAL, "#1A1A1A")])

MATS = {
    "photo_eagle": os.path.join(INPUTS, "photo_eagle.png"),
    "photo_sky": os.path.join(INPUTS, "photo_sky.png"),
    "cartoon_cat": os.path.join(INPUTS, "cartoon_cat.png"),
    "transparent_icon": os.path.join(INPUTS, "transparent_icon.png"),
}


def sample_cells(finished, gw, gh):
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
    return {"mean_l": round(float(L.mean()), 2),
            "mean_chroma": round(float(C.mean()), 2),
            "near_white_ratio": round(float((L >= 92).mean()), 4),
            "n_colors": int(len(np.unique(cells.reshape(-1, 3), axis=0)))}


def run(mat, effects, grid=GRID):
    proc = ImageProcessor()
    return proc.process_image(MATS[mat], grid[0], grid[1], effects=effects, **KW)


def outline_share(cells):
    return round(float(np.all(cells == np.asarray(OUTLINE_RGB), axis=-1).mean()), 4)


def continuity(fin_after_cells, fin_base_cells):
    diff = np.abs(fin_after_cells.astype(int) - fin_base_cells.astype(int)).max(-1) > 12
    nb = np.zeros_like(diff, dtype=int)
    nb[1:, :] += diff[:-1, :]
    nb[:-1, :] += diff[1:, :]
    nb[:, 1:] += diff[:, :-1]
    nb[:, :-1] += diff[:, 1:]
    vals = nb[diff]
    return {"changed": int(diff.sum()), "changed_ratio": round(float(diff.mean()), 4),
            "mean_neighbors": round(float(vals.mean()), 2) if vals.size else 0,
            "ratio_ge2": round(float((vals >= 2).mean()), 4) if vals.size else 0}


def label_panel(img, text, px=240):
    img = img.convert("RGB").resize((px, px), Image.NEAREST)
    canvas = Image.new("RGB", (px, px + 18), (245, 245, 245))
    canvas.paste(img, (0, 18))
    d = ImageDraw.Draw(canvas)
    d.text((3, 2), text[:38], fill=(0, 0, 0), font=ImageFont.load_default())
    return canvas


def sheet(items, path, cols=2, px=240):
    panels = [label_panel(img, txt, px) for txt, img in items]
    rows = int(math.ceil(len(panels) / cols))
    w, h = cols * px, rows * (px + 18)
    out = Image.new("RGB", (w, h), (255, 255, 255))
    for i, p in enumerate(panels):
        out.paste(p, ((i % cols) * px, (i // cols) * (px + 18)))
    out.save(path, quality=90)
    return path


def main():
    metrics = {}
    proc = ImageProcessor()

    # ---------- 1) outline_cell 去黑网 ----------
    rows = {}
    sheet_items = []
    for mat in ("photo_eagle", "photo_sky", "cartoon_cat"):
        base = run(mat, [])
        after = run(mat, [{"id": "outline_cell", "params": {}}])
        bcell = sample_cells(base.finished, base.grid_w, base.grid_h)
        acell = sample_cells(after.finished, after.grid_w, after.grid_h)
        rows[mat] = {"outline_share_after": outline_share(acell),
                     "outline_share_baseline": outline_share(bcell),
                     "mean_l_after": cell_stat(acell)["mean_l"],
                     "mean_l_baseline": cell_stat(bcell)["mean_l"],
                     "n_colors": len(after.color_stats),
                     "warnings": after.warnings}
        before_img = os.path.join(ART, mat, "fin_outline_cell.png")
        if os.path.exists(before_img):
            sheet_items.append((f"{mat} BEFORE", Image.open(before_img)))
        sheet_items.append((f"{mat} AFTER", after.finished))
        after.finished.save(os.path.join(FIX, f"outline_cell_{mat}_after.png"))
    metrics["outline_cell"] = rows
    sheet(sheet_items, os.path.join(FIX, "outline_cell_before_after.jpg"), cols=2)

    # ---------- 2) outline_edge 网格尺度 ----------
    rows = {}
    sheet_items = []
    for mat in ("photo_eagle", "cartoon_cat"):
        base = run(mat, [])
        after = run(mat, [{"id": "outline_edge", "params": {}}])
        bcell = sample_cells(base.finished, base.grid_w, base.grid_h)
        acell = sample_cells(after.finished, after.grid_w, after.grid_h)
        c = continuity(acell, bcell)
        c["outline_share"] = outline_share(acell)
        c["warnings"] = after.warnings
        rows[mat] = c
        before_img = os.path.join(ART, mat, "fin_outline_edge.png")
        if os.path.exists(before_img):
            sheet_items.append((f"{mat} BEFORE", Image.open(before_img)))
        sheet_items.append((f"{mat} AFTER", after.finished))
        after.finished.save(os.path.join(FIX, f"outline_edge_{mat}_after.png"))
    metrics["outline_edge"] = rows
    sheet(sheet_items, os.path.join(FIX, "outline_edge_before_after.jpg"), cols=2)

    # ---------- 3) cel_shade ----------
    rows = {}
    sheet_items = []
    for mat in ("photo_eagle", "photo_sky", "cartoon_cat"):
        base = run(mat, [])
        after = run(mat, [{"id": "cel_shade", "params": {"levels": 4}}])
        bcell = sample_cells(base.finished, base.grid_w, base.grid_h)
        acell = sample_cells(after.finished, after.grid_w, after.grid_h)
        lb, la = cell_lab(bcell), cell_lab(acell)
        de = np.sqrt(((la - lb) ** 2).sum(-1))
        changed = de > 10
        hb = np.arctan2(lb[..., 2], lb[..., 1])
        ha = np.arctan2(la[..., 2], la[..., 1])
        dh = np.degrees(np.abs(np.angle(np.exp(1j * (ha - hb)))))
        rows[mat] = {
            "mean_l_after": cell_stat(acell)["mean_l"],
            "mean_l_baseline": cell_stat(bcell)["mean_l"],
            "n_colors": len(after.color_stats),
            "n_colors_baseline": len(base.color_stats),
            "changed_ratio_de10": round(float(changed.mean()), 4),
            "median_hue_shift_changed": round(float(np.median(dh[changed])), 1) if changed.any() else 0.0,
            "warnings": after.warnings,
        }
        before_img = os.path.join(ART, mat, "fin_cel4.png")
        if os.path.exists(before_img):
            sheet_items.append((f"{mat} BEFORE", Image.open(before_img)))
        sheet_items.append((f"{mat} AFTER", after.finished))
        after.finished.save(os.path.join(FIX, f"cel_shade_{mat}_after.png"))
    metrics["cel_shade"] = rows
    sheet(sheet_items, os.path.join(FIX, "cel_shade_before_after.jpg"), cols=2)

    # ---------- 4) preset ----------
    rows = {}
    sheet_items = []
    for mat in ("photo_eagle", "photo_sky", "cartoon_cat"):
        base = run(mat, [])
        after = run(mat, [{"id": "preset", "params": {"preset": "pastel"}}])
        bcell = sample_cells(base.finished, base.grid_w, base.grid_h)
        acell = sample_cells(after.finished, after.grid_w, after.grid_h)
        rows[mat] = {
            "n_colors": len(after.color_stats),
            "mean_l_baseline": cell_stat(bcell)["mean_l"],
            "mean_l_after": cell_stat(acell)["mean_l"],
            "near_white_baseline": cell_stat(bcell)["near_white_ratio"],
            "near_white_after": cell_stat(acell)["near_white_ratio"],
            "warnings": after.warnings,
        }
        before_img = os.path.join(ART, mat, "fin_preset_pastel.png")
        if os.path.exists(before_img):
            sheet_items.append((f"{mat} BEFORE", Image.open(before_img)))
        sheet_items.append((f"{mat} AFTER", after.finished))
        after.finished.save(os.path.join(FIX, f"preset_{mat}_after.png"))
    metrics["preset"] = rows
    sheet(sheet_items, os.path.join(FIX, "preset_before_after.jpg"), cols=2)

    # ---------- 5) bg_remove：白色主体保留 / 白底删除 ----------
    rows = {}
    ghost = Image.open(os.path.join(INPUTS, "cartoon_ghost.png")).convert("RGB")
    ctx = EffectContext(engine=proc)
    out = apply_phase([{"id": "bg_remove", "params": {"color": "#FFFFFF"}}], "preprocess", ghost.copy(), ctx)
    alpha = np.asarray(out)[..., 3]
    src = np.asarray(ghost)
    subject = np.all(src >= 250, axis=-1)
    bg = np.abs(src.astype(int) - np.array([190, 220, 240])).sum(-1) <= 90
    rows["ghost"] = {"deleted_subject_ratio": round(float((alpha[subject] < 128).mean()), 4),
                     "deleted_bg_ratio": round(float((alpha[bg] < 128).mean()), 4),
                     "warnings": ctx.warnings}
    checker = (((np.indices(alpha.shape).sum(0) // 24) % 2) * 40 + 190).astype(np.uint8)
    comp = np.stack([checker] * 3, -1)
    a = (alpha[..., None].astype(np.float32) / 255.0)
    comp = (np.asarray(out)[..., :3].astype(np.float32) * a + comp * (1 - a)).astype(np.uint8)
    Image.fromarray(comp).save(os.path.join(FIX, "bg_remove_ghost_after_checker.png"))
    before_checker = os.path.join(ART, "cartoon_ghost", "bgremove_checkerboard.png")
    sheet([("ghost BEFORE (white body deleted)", Image.open(before_checker)),
           ("ghost AFTER (white body kept)", Image.fromarray(comp))],
          os.path.join(FIX, "bg_remove_before_after.jpg"), cols=2)
    cat = run("cartoon_cat", [{"id": "bg_remove", "params": {"color": "#FFFFFF"}}])
    rows["cartoon_white_bg"] = {"beads": cat.total_beads,
                                "transparent_cells": cat.grid_w * cat.grid_h - cat.total_beads,
                                "warnings": cat.warnings}
    # auto 角落取色
    cat_auto = run("cartoon_cat", [{"id": "bg_remove", "params": {"color": "auto"}}])
    rows["cartoon_auto"] = {"beads": cat_auto.total_beads, "warnings": cat_auto.warnings}
    metrics["bg_remove"] = rows

    # ---------- 6) alpha 保持 ----------
    rows = {}
    for eid, params in (("grayscale", {}), ("cel_shade", {"levels": 4}),
                        ("duotone", {}), ("adjust", {"saturation": 1.2})):
        r = run("transparent_icon", [{"id": eid, "params": params}])
        rows[eid] = {"beads": r.total_beads, "warnings": r.warnings}
    metrics["transparent_alpha"] = {"baseline_beads": 918, "rows": rows}

    # ---------- 7) chibi 静默失效修复 ----------
    r = run("photo_eagle", [{"id": "chibi", "params": {}}])
    metrics["chibi"] = {"grid": [r.grid_w, r.grid_h], "warnings": r.warnings,
                        "beads": r.total_beads}

    # ---------- 8) dither 钳制 ----------
    r15 = run("photo_sky", [{"id": "dither", "params": {"strength": 1.5}}])
    r5 = run("photo_sky", [{"id": "dither", "params": {"strength": 5.0}}])
    c15 = sample_cells(r15.finished, r15.grid_w, r15.grid_h)
    c5 = sample_cells(r5.finished, r5.grid_w, r5.grid_h)
    metrics["dither_clamp"] = {
        "identical_after_clamp": bool(np.array_equal(c15, c5)),
        "warnings": r5.warnings,
        "n_colors_s15": len(r15.color_stats), "n_colors_s5": len(r5.color_stats)}

    with open(os.path.join(FIX, "metrics_after.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
