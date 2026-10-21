#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证：网格级线稿/描边提取 —— 现状 FIND_EDGES vs DoG/XDoG+hysteresis+细化。

只读 qa/lead/inputs/eagle.png；只写 qa/research/artifacts/。
运行：conda run -n pindou python qa/research/verify_lineart.py
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SRC = os.path.join(ROOT, "qa/lead/inputs/eagle.png")
OUT = os.path.join(ROOT, "qa/research/artifacts")
os.makedirs(OUT, exist_ok=True)
GRID = 64
PAPER = (250, 247, 240)
INK = (26, 26, 26)


def to_mask(a):
    return (a > 127).astype(np.uint8)


def nb_count(mask):
    k = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], np.uint8)
    return cv2.filter2D(mask.astype(np.uint8), -1, k, borderType=cv2.BORDER_CONSTANT)


def comps(mask):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    sizes = stats[1:, cv2.CC_STAT_AREA] if n > 1 else np.array([])
    return n - 1, sizes


def metrics(name, mask):
    mask = mask.astype(bool)
    total = mask.size
    cov = mask.sum()
    ncomp, sizes = comps(mask)
    isolated = int((mask & (nb_count(mask) == 0)).sum())
    largest = int(sizes.max()) if sizes.size else 0
    return {
        "method": name,
        "coverage_cells": int(cov),
        "coverage_pct": round(100.0 * cov / total, 2),
        "components": int(ncomp),
        "largest_component": largest,
        "largest_share_of_mask": round(largest / max(1, cov), 3),
        "isolated_cells": isolated,
        "isolated_share_of_mask": round(isolated / max(1, cov), 3),
        "mean_component_size": round(float(cov / max(1, ncomp)), 2),
    }


def hyst(abs_resp, hi_pct, lo_pct, iters=3):
    hi = np.percentile(abs_resp, hi_pct)
    lo = np.percentile(abs_resp, lo_pct)
    seed = (abs_resp >= hi).astype(np.uint8)
    lowm = (abs_resp >= lo).astype(np.uint8)
    grown = seed.copy()
    for _ in range(iters):
        grown = cv2.dilate(grown, np.ones((3, 3), np.uint8)) & lowm
    return grown.astype(bool), float(hi), float(lo)


def despeckle(mask, min_nb=1, min_comp=2):
    m = mask.astype(np.uint8)
    m[nb_count(m) < min_nb] = 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_comp:
            out[lab == i] = 1
    return out.astype(bool)


def zhang_suen(mask, max_iter=30):
    """Zhang-Suen 细化（numpy 向量化，64x64 足够快）"""
    img = mask.astype(np.uint8).copy()

    def neighbours(im):
        P2 = np.roll(im, -1, 0); P3 = np.roll(np.roll(im, -1, 0), -1, 1)
        P4 = np.roll(im, -1, 1); P5 = np.roll(np.roll(im, 1, 0), -1, 1)
        P6 = np.roll(im, 1, 0); P7 = np.roll(np.roll(im, 1, 0), 1, 1)
        P8 = np.roll(im, 1, 1); P9 = np.roll(np.roll(im, -1, 0), 1, 1)
        return P2, P3, P4, P5, P6, P7, P8, P9

    for _ in range(max_iter):
        changed = False
        for step in (0, 1):
            P2, P3, P4, P5, P6, P7, P8, P9 = neighbours(img)
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                cond = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & \
                       (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                cond = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & \
                       (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            if cond.any():
                img[cond] = 0
                changed = True
        if not changed:
            break
    return img.astype(bool)


def contrast_aware_downscale(img, grid):
    """PixelOE contrast_based_downscale 的 numpy 复刻（仅 L 通道选 min/max/median）"""
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    h, w = L.shape
    ph, pw = h // grid, w // grid
    blocks = L[: ph * grid, : pw * grid].reshape(grid, ph, grid, pw).transpose(0, 2, 1, 3).reshape(grid, grid, ph * pw)
    med = np.median(blocks, axis=-1)
    mean = blocks.mean(axis=-1)
    mx = blocks.max(axis=-1)
    mn = blocks.min(axis=-1)
    out = med.copy()
    mini_loc = (med < mean) & ((mx - med) > (med - mn))
    maxi_loc = (med > mean) & ((mx - med) < (med - mn))
    out[mini_loc] = mn[mini_loc]
    out[maxi_loc] = mx[maxi_loc]
    return np.clip(out / 255.0, 0.0, 1.0)


def render_panel(arr, scale=6):
    """arr: (64,64) float 0..1 或 RGB uint8"""
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)) if arr.ndim == 2 else Image.fromarray(arr)
    return im.resize((GRID * scale, GRID * scale), Image.NEAREST)


def overlay(base_rgb, mask, scale=6, alpha=0.85):
    im = Image.fromarray(base_rgb).resize((GRID * scale, GRID * scale), Image.NEAREST).convert("RGB")
    line = Image.new("RGB", im.size, INK)
    im = Image.blend(im, line, alpha) if False else im
    px = im.load()
    m = np.asarray(Image.fromarray(mask.astype(np.uint8)).resize(im.size, Image.NEAREST)) > 0
    mimg = Image.fromarray(mask.astype(np.uint8) * 255).resize(im.size, Image.NEAREST)
    im.paste(INK, (0, 0), mimg.point(lambda v: 255 if v > 0 else 0))
    return im


def main():
    img = Image.open(SRC).convert("RGB")
    base = img.resize((GRID, GRID), Image.BOX)
    base_rgb = np.asarray(base)
    base_l = np.asarray(base.convert("L"), dtype=np.float32) / 255.0
    contrast_l = contrast_aware_downscale(img, GRID)
    L = contrast_l  # 对比度感知下采样作为 DoG 输入

    # ---- A. 现状：PIL FIND_EDGES 全分辨率 -> 阈值 -> NEAREST 下采样 ----
    gray_full = img.convert("L")
    edges = gray_full.filter(ImageFilter.FIND_EDGES)
    earr = np.asarray(edges, dtype=np.uint8)
    current_mask = np.asarray(Image.fromarray((earr > 40).astype(np.uint8) * 255).resize((GRID, GRID), Image.NEAREST)) > 127

    # ---- B. 现状：邻接描边（在色卡索引矩阵上做相邻异色检测）----
    from core.colors import get_palette, rgb_to_lab
    palette = get_palette("mard_221")
    lab = rgb_to_lab(np.asarray(base, dtype=np.float32))
    flat = lab.reshape(-1, 3)
    d = ((flat[:, None, :] - palette.lab[None, :, :]) ** 2).sum(-1)
    idx = d.argmin(-1).reshape(GRID, GRID)
    diff = np.zeros((GRID, GRID), dtype=bool)
    diff[1:, :] |= idx[1:, :] != idx[:-1, :]
    diff[:-1, :] |= idx[1:, :] != idx[:-1, :]
    diff[:, 1:] |= idx[:, 1:] != idx[:, :-1]
    diff[:, :-1] |= idx[:, 1:] != idx[:, :-1]
    cell_mask = diff

    # ---- C. DoG 在网格分辨率：sigma1=0.8 sigma2=1.6，abs 响应 + hysteresis + 去孤点 + 细化 ----
    g1 = cv2.GaussianBlur(L, (0, 0), 0.8)
    g2 = cv2.GaussianBlur(L, (0, 0), 1.6)
    dog = np.abs(g1 - g2)
    dog_raw, dog_hi, dog_lo = hyst(dog, 92, 80, iters=3)
    dog_clean = despeckle(dog_raw)
    dog_final = despeckle(zhang_suen(dog_clean), min_nb=0, min_comp=2)

    # ---- D. DoG 在全分辨率（512）→ 覆盖率下采样（替代 NEAREST 抽点）----
    L_full = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    fg1 = cv2.GaussianBlur(L_full, (0, 0), 1.2)
    fg2 = cv2.GaussianBlur(L_full, (0, 0), 2.4)
    fdog = np.abs(fg1 - fg2)
    fmask, f_hi, f_lo = hyst(fdog, 95, 85, iters=4)
    # 覆盖率下采样：每格 8x8 中多少比例是边缘
    fh, fw = L_full.shape
    ph, pw = fh // GRID, fw // GRID
    cover = fmask[: ph * GRID, : pw * GRID].reshape(GRID, ph, GRID, pw).transpose(0, 2, 1, 3).mean(axis=(2, 3))
    dog_fullres_cov_raw = cover >= 0.22
    dog_fullres_cov = despeckle(dog_fullres_cov_raw, min_nb=0, min_comp=2)

    # ---- E. XDoG 全分辨率 → 覆盖率下采样（tau/eps/phi 用 Winnemoller 推荐值）----
    tau, eps, phi = 0.98, 0.10, 200.0
    xd = fg1 - tau * fg2
    soft = np.where(xd >= eps, 1.0, 1.0 + np.tanh(phi * (xd - eps)))
    soft = (soft - soft.min()) / max(1e-9, soft.max() - soft.min())
    xline = soft < 0.5  # 归一化后软阈值，得到相对边缘掩码
    xcover = xline[: ph * GRID, : pw * GRID].reshape(GRID, ph, GRID, pw).transpose(0, 2, 1, 3).mean(axis=(2, 3))
    xdog_fullres_raw = xcover >= 0.12
    xdog_fullres = despeckle(xdog_fullres_raw, min_nb=0, min_comp=2)

    # ---- F. 邻接描边的可控版本：色卡索引相邻 ΔE2000 门限（替代「异色即描边」）----
    from core.colors import get_palette, rgb_to_lab

    def ciede2000(l1, l2):
        """标量 CIEDE2000（Sharma 2005 实现注记）"""
        L1, a1, b1 = float(l1[0]), float(l1[1]), float(l1[2])
        L2, a2, b2 = float(l2[0]), float(l2[1]), float(l2[2])
        C1 = np.hypot(a1, b1); C2 = np.hypot(a2, b2)
        Cm = (C1 + C2) / 2.0
        G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
        a1p, a2p = (1 + G) * a1, (1 + G) * a2
        C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
        h1p = np.degrees(np.arctan2(b1, a1p)) % 360
        h2p = np.degrees(np.arctan2(b2, a2p)) % 360
        dLp = L2 - L1
        dCp = C2p - C1p
        if C1p * C2p == 0:
            dhp = 0.0
        else:
            dhp = h2p - h1p
            if dhp > 180: dhp -= 360
            elif dhp < -180: dhp += 360
        dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2)
        Lpm = (L1 + L2) / 2.0
        Cpm = (C1p + C2p) / 2.0
        if C1p * C2p == 0:
            hpm = h1p + h2p
        elif abs(h1p - h2p) <= 180:
            hpm = (h1p + h2p) / 2.0
        elif h1p + h2p < 360:
            hpm = (h1p + h2p + 360) / 2.0
        else:
            hpm = (h1p + h2p - 360) / 2.0
        T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
             + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
        dtheta = 30 * np.exp(-(((hpm - 275) / 25.0) ** 2))
        RC = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
        SL = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
        SC = 1 + 0.045 * Cpm
        SH = 1 + 0.015 * Cpm * T
        RT = -np.sin(np.radians(2 * dtheta)) * RC
        return float(np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH)))

    de_map = np.zeros((GRID, GRID), dtype=np.float32)
    pal_lab = palette.lab
    de_cache = {}
    for y in range(GRID):
        for x in range(GRID):
            best = 0.0
            for dy, dx in ((0, 1), (1, 0)):
                ny, nx = y + dy, x + dx
                if ny >= GRID or nx >= GRID:
                    continue
                a, b = int(idx[y, x]), int(idx[ny, nx])
                key = (a, b) if a <= b else (b, a)
                val = de_cache.get(key)
                if val is None:
                    val = ciede2000(pal_lab[a], pal_lab[b])
                    de_cache[key] = val
                if val > best:
                    best = val
            de_map[y, x] = best
    gate = np.percentile(de_map, 88)
    gated = de_map >= gate
    gated = despeckle(gated, min_nb=1, min_comp=2)

    results = [
        metrics("current_FIND_EDGES_threshold40", current_mask),
        metrics("current_neighbor_diff_outline", cell_mask),
        metrics("dog_grid_hysteresis", dog_raw),
        metrics("dog_grid_despeckle_thin", dog_final),
        metrics("dog_fullres_strict_covdown", dog_fullres_cov),
        metrics("xdog_fullres_covdown_12pct", xdog_fullres),
        metrics("neighbor_diff_deltaE_gate_p88", gated),
    ]

    # ---- 拼图 ----
    scale = 5
    def chart_preview(mask):
        bead = Image.new("RGB", (GRID * scale, GRID * scale), PAPER)
        bd = ImageDraw.Draw(bead)
        for y in range(GRID):
            for x in range(GRID):
                bd.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1],
                             fill=tuple(int(v) for v in base_rgb[y, x]))
        mimg = Image.fromarray(mask.astype(np.uint8) * 255).resize(bead.size, Image.NEAREST)
        bead.paste(INK, (0, 0), mimg.point(lambda v: 255 if v > 0 else 0))
        return bead

    panels = [
        ("source 64x64 (BOX)", Image.fromarray(base_rgb).resize((GRID * scale, GRID * scale), Image.NEAREST)),
        ("CURRENT FIND_EDGES t=40 (%.1f%%)" % results[0]["coverage_pct"], overlay(base_rgb, current_mask, scale)),
        ("CURRENT neighbor-diff (%.1f%%)" % results[1]["coverage_pct"], overlay(base_rgb, cell_mask, scale)),
        ("DoG@64 + hyst + thin (%.1f%%)" % results[3]["coverage_pct"], overlay(base_rgb, dog_final, scale)),
        ("DoG@512 strict + cov-down (%.1f%%)" % results[4]["coverage_pct"], overlay(base_rgb, dog_fullres_cov, scale)),
        ("neighbor-diff + dE2000 gate p88 (%.1f%%)" % results[6]["coverage_pct"], overlay(base_rgb, gated, scale)),
        ("PROPOSED line-art: DoG@64 + thin", chart_preview(dog_final)),
        ("PROPOSED outline: dE2000-gated", chart_preview(gated)),
    ]

    W = GRID * scale
    pad, label_h = 8, 22
    cols = 4
    rows = 2
    sheet = Image.new("RGB", (cols * (W + pad) + pad, rows * (W + pad + label_h) + pad), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(panels):
        col, row = i % cols, i // cols
        x = pad + col * (W + pad)
        y = pad + row * (W + pad + label_h)
        sheet.paste(im, (x, y + label_h))
        d.text((x, y + 4), label, fill=(20, 20, 20))
    sheet.save(os.path.join(OUT, "lineart_compare.png"))

    payload = {"grid": GRID, "source": "qa/lead/inputs/eagle.png", "results": results,
               "dog_thresholds": {"hi": round(dog_hi, 5), "lo": round(dog_lo, 5)},
               "params": {"dog_sigma": [0.8, 1.6], "xdog_tau_eps_phi": [tau, eps, phi]}}
    with open(os.path.join(OUT, "lineart_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("artifacts:", os.path.join(OUT, "lineart_compare.png"))


if __name__ == "__main__":
    main()