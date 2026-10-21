#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证：赛璐璐平涂、色卡感知距离、背景去除的可行替代实现。

只读 qa/lead/inputs/eagle.png（另建合成图）；只写 qa/research/artifacts/。
运行：conda run -n pindou python qa/research/verify_color_bg.py
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SRC = os.path.join(ROOT, "qa/lead/inputs/eagle.png")
OUT = os.path.join(ROOT, "qa/research/artifacts")
os.makedirs(OUT, exist_ok=True)
GRID = 64

from core.colors import get_palette, rgb_to_lab  # noqa: E402

PALETTE = get_palette("mard_221")
PAL_LAB = PALETTE.lab.astype(np.float64)
PAL_RGB = np.asarray(PALETTE.colors, dtype=np.uint8)


def lab_ciede2000(lab1, lab2):
    """向量化 CIEDE2000。lab1:(N,3) lab2:(K,3) -> (N,K)。Sharma 2005。"""
    L1, a1, b1 = (lab1[:, 0:1], lab1[:, 1:2], lab1[:, 2:3])
    L2, a2, b2 = (lab2[None, :, 0], lab2[None, :, 1], lab2[None, :, 2])
    C1 = np.hypot(a1, b1); C2 = np.hypot(a2, b2)
    Cm = (C1 + C2) / 2.0
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    zero_c = (C1p * C2p) == 0
    dhp = np.where(zero_c, 0.0, dhp)
    dHp = 2 * np.sqrt(np.maximum(C1p * C2p, 0)) * np.sin(np.radians(dhp) / 2)
    Lpm = (L1 + L2) / 2.0
    Cpm = (C1p + C2p) / 2.0
    hsum = h1p + h2p
    hpm = np.where(zero_c, hsum,
                   np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
                            np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-(((hpm - 275) / 25.0) ** 2))
    RC = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
    SL = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    SC = 1 + 0.045 * Cpm
    SH = 1 + 0.015 * Cpm * T
    RT = -np.sin(np.radians(2 * dtheta)) * RC
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))


def de2000_pairs(lab1, lab2):
    """逐元素 CIEDE2000（lab1/lab2 同形状 (N,3)）。"""
    L1, a1, b1 = lab1[:, 0], lab1[:, 1], lab1[:, 2]
    L2, a2, b2 = lab2[:, 0], lab2[:, 1], lab2[:, 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2.0
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    zero_c = (C1p * C2p) == 0
    dhp = np.where(zero_c, 0.0, dhp)
    dHp = 2 * np.sqrt(np.maximum(C1p * C2p, 0)) * np.sin(np.radians(dhp) / 2)
    Lpm, Cpm = (L1 + L2) / 2.0, (C1p + C2p) / 2.0
    hsum = h1p + h2p
    hpm = np.where(zero_c, hsum, np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
                                          np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-(((hpm - 275) / 25.0) ** 2))
    RC = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
    SL = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    SC = 1 + 0.045 * Cpm
    SH = 1 + 0.015 * Cpm * T
    RT = -np.sin(np.radians(2 * dtheta)) * RC
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


def srgb_to_oklab(arr):
    """RGB 0..255 -> Oklab（Ottosson 2020 公式）"""
    c = np.asarray(arr, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * lin[..., 0] + 0.5363325363 * lin[..., 1] + 0.0514459929 * lin[..., 2]
    m = 0.2119034982 * lin[..., 0] + 0.6806995451 * lin[..., 1] + 0.1073969566 * lin[..., 2]
    s = 0.0883024619 * lin[..., 0] + 0.2817188376 * lin[..., 1] + 0.6299787005 * lin[..., 2]
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    ], axis=-1)


def map_palette(rgb_img, metric="cie76"):
    rgb = np.asarray(rgb_img, dtype=np.float64)
    flat_lab = rgb_to_lab(rgb.astype(np.float32)).reshape(-1, 3).astype(np.float64)
    if metric == "cie76":
        d = ((flat_lab[:, None, :] - PAL_LAB[None, :, :]) ** 2).sum(-1)
    elif metric == "ciede2000":
        d = lab_ciede2000(flat_lab, PAL_LAB)
    elif metric == "oklab":
        ok = srgb_to_oklab(rgb).reshape(-1, 3)
        pal_ok = srgb_to_oklab(PAL_RGB)
        d = ((ok[:, None, :] - pal_ok[None, :, :]) ** 2).sum(-1)
    else:
        raise ValueError(metric)
    return d.argmin(-1).reshape(rgb.shape[:2])


def render(idx, scale=5, cell_border=False):
    rgb = PAL_RGB[idx]
    im = Image.fromarray(rgb).resize((GRID * scale, GRID * scale), Image.NEAREST)
    return im


def speckle_ratio(idx):
    """每格颜色与 3x3 邻域众数不同的比例（越低越干净）"""
    h, w = idx.shape
    padded = np.pad(idx, 1, mode="edge")
    diff = 0
    for y in range(h):
        for x in range(w):
            block = padded[y:y + 3, x:x + 3].ravel()
            vals, counts = np.unique(block, return_counts=True)
            if vals[counts.argmax()] != idx[y, x]:
                diff += 1
    return diff / (h * w)


def banding_ratio(idx, lab_grid, thresh=10.0):
    """所选珠子与块均值色之间的 CIEDE2000：越大越「怪色块/失真」"""
    chosen = PAL_LAB[idx.reshape(-1)]
    d = de2000_pairs(chosen, lab_grid.reshape(-1, 3))
    return float((d > thresh).mean()), float(np.median(d))


def block_mean_rgb(img):
    return np.asarray(img.resize((GRID, GRID), Image.BOX))


def contrast_aware_downscale(img, grid=GRID):
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    h, w = L.shape
    ph, pw = h // grid, w // grid
    blocks = L[: ph * grid, : pw * grid].reshape(grid, ph, grid, pw).transpose(0, 2, 1, 3).reshape(grid, grid, ph * pw)
    med, mean = np.median(blocks, -1), blocks.mean(-1)
    mx, mn = blocks.max(-1), blocks.min(-1)
    out = med.copy()
    mini = (med < mean) & ((mx - med) > (med - mn))
    maxi = (med > mean) & ((mx - med) < (med - mn))
    out[mini] = mn[mini]; out[maxi] = mx[maxi]
    lab2 = cv2.resize(lab, (grid, grid), interpolation=cv2.INTER_NEAREST)
    lab2[..., 0] = out
    rgb = cv2.cvtColor(lab2.astype(np.uint8), cv2.COLOR_LAB2RGB)
    return Image.fromarray(rgb)


def kmeans_quantize(img, k):
    lab = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(flat, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8).reshape(1, -1, 3)
    centers_rgb = cv2.cvtColor(centers, cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return Image.fromarray(centers_rgb[labels.ravel()].reshape(lab.shape[:2] + (3,)).astype(np.uint8))


def metrics_for(idx, name, lab_grid):
    br, med = banding_ratio(idx, lab_grid)
    return {
        "method": name,
        "unique_beads": int(len(np.unique(idx))),
        "speckle_ratio": round(speckle_ratio(idx), 4),
        "outlier_ratio_dE2000_gt10": round(br, 4),
        "median_dE2000_to_block_mean": round(med, 2),
    }


def main():
    img = Image.open(SRC).convert("RGB")
    base = img.resize((GRID, GRID), Image.BOX)
    base_lab = rgb_to_lab(np.asarray(base, dtype=np.float32))

    # ---------- 1. 赛璐璐：现状 vs 边缘保持平滑 + 对比感知下采样 + Lab k-means ----------
    levels = 4
    step = 256.0 / levels
    poster = (np.floor(np.asarray(img, dtype=np.float32) / step) * step).clip(0, 255).astype(np.uint8)
    cur_cel = Image.fromarray(poster).resize((GRID, GRID), Image.BOX)
    cur_idx = map_palette(cur_cel, "cie76")

    # cv2.stylization：OpenCV 官方非真实感渲染（edge-preserving abstraction）
    smoothed = Image.fromarray(cv2.stylization(np.asarray(img), sigma_s=60, sigma_r=0.35))
    smooth_cel = contrast_aware_downscale(smoothed, GRID)
    proposed_idx = map_palette(kmeans_quantize(smooth_cel, max(2, levels * 2)), "ciede2000")

    # ---------- 2. 色卡距离：CIE76 vs CIEDE2000 vs Oklab ----------
    idx76 = map_palette(base, "cie76")
    idx2k = map_palette(base, "ciede2000")
    idxok = map_palette(base, "oklab")
    diff76_2k = float((idx76 != idx2k).mean())
    diff76_ok = float((idx76 != idxok).mean())

    def fidelity(idx):
        chosen = PAL_LAB[idx.reshape(-1)]
        d = de2000_pairs(chosen, base_lab.reshape(-1, 3))
        return float(np.median(d))

    dist_stats = {
        "cie76_vs_ciede2000_index_diff_pct": round(100 * diff76_2k, 2),
        "cie76_vs_oklab_index_diff_pct": round(100 * diff76_ok, 2),
        "median_ciede2000_to_block_mean": {
            "cie76": round(fidelity(idx76), 2),
            "ciede2000": round(fidelity(idx2k), 2),
            "oklab": round(fidelity(idxok), 2),
        },
    }

    # ---------- 3. 背景去除：现状全局容差 vs 连通域 vs GrabCut ----------
    H = W = 320
    yy, xx = np.mgrid[0:H, 0:W]
    white = np.array([255, 255, 255], dtype=np.uint8)

    # Case A：白色主体 + 浅灰渐变背景（主体与背景直接相接）
    bg = (238 + 8 * (yy / H)).astype(np.uint8)
    synthA = np.stack([bg, bg, bg], -1)
    circle = (xx - 160) ** 2 + (yy - 150) ** 2 <= 92 ** 2
    synthA[circle] = white
    eye = ((xx - 130) ** 2 + (yy - 130) ** 2 <= 9 ** 2) | ((xx - 190) ** 2 + (yy - 130) ** 2 <= 9 ** 2)
    synthA[eye] = (60, 60, 60)
    mouth = ((xx - 160) ** 2 + (yy - 190) ** 2 <= 14 ** 2) & (yy < 190)
    synthA[mouth] = (160, 90, 90)
    subjectA = circle

    # Case B：白色背景 + 深色描边包围的白色主体内部（典型线稿/贴纸）
    synthB = np.full((H, W, 3), 255, np.uint8)
    ring = np.abs(np.hypot(xx - 160, yy - 160) - 100) <= 8
    synthB[ring] = (45, 45, 45)
    inner = np.hypot(xx - 160, yy - 160) <= 92
    synthB[inner & ~ring] = (252, 250, 246)  # 近白主体内部，不是纯白
    subjectB = inner  # 主体内部（含描边）

    def current_global(synth, tol=30):
        target = white.astype(np.int32)
        dist = np.abs(synth.astype(np.int32) - target).sum(-1)
        return dist > tol * 3

    def connected_key(synth, dE_thr):
        lab = rgb_to_lab(synth.astype(np.float32)).reshape(-1, 3)
        dE = lab_ciede2000(lab, np.array([[100.0, 0.0, 0.0]]))[:, 0].reshape(H, W)
        in_tol = (dE <= dE_thr).astype(np.uint8)
        n, cc = cv2.connectedComponents(in_tol, connectivity=8)
        border = set(cc[0, :]) | set(cc[-1, :]) | set(cc[:, 0]) | set(cc[:, -1])
        border.discard(0)
        return ~np.isin(cc, list(border))

    def grabcut(synth):
        gc_mask = np.zeros((H, W), np.uint8)
        rect = (12, 12, W - 24, H - 24)
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(cv2.cvtColor(synth, cv2.COLOR_RGB2BGR), gc_mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
        return (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD)

    def keep(alpha, subject):
        return float((alpha & subject).sum() / max(1, subject.sum()))

    def remove(alpha, subject):
        return float(((~alpha) & ~subject).sum() / max(1, (~subject).sum()))

    alphaA_cur = current_global(synthA)
    alphaA_conn = connected_key(synthA, 1.8)
    alphaA_gc = grabcut(synthA)
    alphaB_cur = current_global(synthB)
    alphaB_conn = connected_key(synthB, 1.8)

    bg_stats = {
        "case_A_white_subject_on_light_gray": {
            "current_global_tolerance30": {"subject_retention": round(keep(alphaA_cur, subjectA), 3), "bg_removal": round(remove(alphaA_cur, subjectA), 3)},
            "border_connected_dE1.8": {"subject_retention": round(keep(alphaA_conn, subjectA), 3), "bg_removal": round(remove(alphaA_conn, subjectA), 3)},
            "grabcut_rect_init": {"subject_retention": round(keep(alphaA_gc, subjectA), 3), "bg_removal": round(remove(alphaA_gc, subjectA), 3)},
        },
        "case_B_white_bg_with_enclosed_white_subject_interior": {
            "current_global_tolerance30": {"subject_retention": round(keep(alphaB_cur, subjectB), 3), "bg_removal": round(remove(alphaB_cur, subjectB), 3)},
            "border_connected_dE1.8": {"subject_retention": round(keep(alphaB_conn, subjectB), 3), "bg_removal": round(remove(alphaB_conn, subjectB), 3)},
        },
    }

    # ---------- 输出 ----------
    scale = 4
    cel_panels = [
        ("source 64 (BOX)", Image.fromarray(np.asarray(base)).resize((GRID * scale, GRID * scale), Image.NEAREST)),
        ("CURRENT cel RGB posterize4 (%.1f%% outlier)" % (100 * banding_ratio(cur_idx, base_lab)[0]),
         render(cur_idx, scale)),
        ("PROPOSED stylization+cov-down+Lab kmeans (%.1f%% outlier)" % (100 * banding_ratio(proposed_idx, base_lab)[0]),
         render(proposed_idx, scale)),
    ]
    sheet = Image.new("RGB", (sum(p.width for _, p in cel_panels) + 40, GRID * scale + 30), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    x = 10
    for label, im in cel_panels:
        sheet.paste(im, (x, 20))
        d.text((x, 4), label, fill=(20, 20, 20))
        x += im.width + 10
    sheet.save(os.path.join(OUT, "cel_compare.png"))

    m_panels = [
        ("CIE76 (current)", render(idx76, scale)),
        ("CIEDE2000", render(idx2k, scale)),
        ("Oklab", render(idxok, scale)),
        ("changed: CIE76 vs CIEDE2000 (%.1f%%)" % (100 * diff76_2k),
         Image.fromarray(np.where((idx76 != idx2k)[..., None], np.array([220, 40, 40], np.uint8),
                                  np.array([235, 235, 235], np.uint8)))),
    ]
    sheet2 = Image.new("RGB", (sum(p.width for _, p in m_panels) + 50, GRID * scale + 30), (245, 245, 245))
    d2 = ImageDraw.Draw(sheet2)
    x = 10
    for label, im in m_panels:
        sheet2.paste(im, (x, 20))
        d2.text((x, 4), label, fill=(20, 20, 20))
        x += im.width + 10
    sheet2.save(os.path.join(OUT, "palette_distance_compare.png"))

    bg_strip = cv2.cvtColor(synthA, cv2.COLOR_RGB2BGR)

    def alpha_preview(synth, alpha, title):
        im = Image.new("RGB", (W, H), (255, 255, 255))
        check = ImageDraw.Draw(im)
        for cy in range(0, H, 16):
            for cx in range(0, W, 16):
                if (cx // 16 + cy // 16) % 2 == 0:
                    check.rectangle([cx, cy, cx + 15, cy + 15], fill=(225, 225, 225))
        rgba = np.dstack([synth, (alpha * 255).astype(np.uint8)])
        im.paste(Image.fromarray(rgba, "RGBA"), (0, 0), Image.fromarray((alpha * 255).astype(np.uint8)))
        d3 = ImageDraw.Draw(im)
        d3.text((8, 8), title, fill=(20, 20, 20))
        return im

    panels = [
        (synthA, np.ones_like(subjectA), "CASE A source: white subject on light-gray bg"),
        (synthA, alphaA_cur, "CASE A current global tolerance=30: subject erased (keep %.0f%%)" % (100 * keep(alphaA_cur, subjectA))),
        (synthA, alphaA_gc, "CASE A GrabCut rect-init: keep %.0f%% subject" % (100 * keep(alphaA_gc, subjectA))),
        (synthB, np.ones_like(subjectB), "CASE B source: white bg + dark ring around near-white subject"),
        (synthB, alphaB_cur, "CASE B current global: interior punched out (keep %.0f%%)" % (100 * keep(alphaB_cur, subjectB))),
        (synthB, alphaB_conn, "CASE B border-connected dE<=1.8: interior kept (%.0f%%), bg removed" % (100 * keep(alphaB_conn, subjectB))),
    ]
    sheet3 = Image.new("RGB", (3 * (W + 10) + 10, 2 * (H + 10) + 10), (245, 245, 245))
    for i, (synth, alpha, title) in enumerate(panels):
        x = 10 + (i % 3) * (W + 10)
        y = 10 + (i // 3) * (H + 10)
        sheet3.paste(alpha_preview(synth, alpha, title), (x, y))
    sheet3.save(os.path.join(OUT, "bg_remove_compare.png"))

    payload = {
        "grid": GRID,
        "cel": {
            "current": metrics_for(cur_idx, "current_cel_posterize4_cie76", base_lab),
            "proposed": metrics_for(proposed_idx, "proposed_stylization_covdown_labkmeans_ciede2000", base_lab),
        },
        "palette_distance": dist_stats,
        "bg_remove": bg_stats,
        "params": {"abstraction": "cv2.stylization sigma_s=60 sigma_r=0.35", "kmeans_k": max(2, levels * 2), "bg_dE_threshold": 1.8},
    }
    with open(os.path.join(OUT, "color_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("artifacts: cel_compare.png / palette_distance_compare.png / bg_remove_compare.png")


if __name__ == "__main__":
    main()