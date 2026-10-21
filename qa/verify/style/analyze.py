#!/usr/bin/env python3
"""T17 引擎输出（图纸/成品/PDF）风格与可读性独立分析。
在 conda pindou 环境运行（numpy + Pillow）。OCR 用同目录 Swift/Vision 工具 ./ocr。

用法: conda run -n pindou python qa/verify/style/analyze.py --tag after
输出: qa/verify/evidence/style/analysis_<tag>.json + stdout markdown 摘要
"""
import argparse
import json
import os
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OCR = os.path.join(HERE, "ocr")

TOK_LIGHT = {
    "paper": (244, 237, 225), "paperDeep": (235, 225, 210), "paperMat": (251, 246, 236),
    "ink": (42, 33, 24), "inkSoft": (77, 63, 48), "inkMuted": (123, 106, 85),
    "hairline": (213, 196, 172), "hairlineStrong": (183, 164, 136),
    "accent": (138, 90, 51), "accentSoft": (239, 224, 204),
}
TOK_DARK = {
    "paper": (23, 18, 13), "paperDeep": (30, 24, 17), "paperMat": (38, 30, 21),
    "ink": (240, 231, 216), "inkSoft": (201, 185, 159), "inkMuted": (160, 142, 116),
    "hairline": (58, 47, 35), "hairlineStrong": (82, 66, 47),
    "accent": (201, 155, 99), "accentSoft": (51, 38, 26),
}
OLD_BLUE = [(0, 120, 215), (120, 190, 255)]


def load(path):
    im = Image.open(path).convert("RGB")
    return np.asarray(im)


def patch_median(arr, x, y, size=24):
    h, w, _ = arr.shape
    x0 = max(0, min(w - size, x)); y0 = max(0, min(h - size, y))
    p = arr[y0:y0 + size, x0:x0 + size].reshape(-1, 3)
    return tuple(int(v) for v in np.median(p, axis=0))


def dist(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1])) + abs(int(a[2]) - int(b[2]))


def count_near(arr, rgb, tol=10):
    d = np.abs(arr.astype(np.int32) - np.array(rgb, dtype=np.int32)).sum(axis=2)
    return int((d <= tol).sum())


def count_old_blue(arr):
    total = 0
    for rgb in OLD_BLUE:
        d = np.abs(arr.astype(np.int32) - np.array(rgb, dtype=np.int32)).sum(axis=2)
        total += int((d <= 24).sum())
    # 广义蓝色（hue 190-235, sat>0.55, val>0.25）
    f = arr.astype(np.float32) / 255.0
    mx = f.max(axis=2); mn = f.min(axis=2)
    dlt = mx - mn
    sat = np.where(mx > 1e-6, dlt / np.maximum(mx, 1e-6), 0)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    hue = np.zeros_like(mx)
    mask = dlt > 1e-6
    with np.errstate(divide="ignore", invalid="ignore"):
        hr = ((g - b) / np.where(dlt == 0, 1, dlt)) % 6
        hg = (b - r) / np.where(dlt == 0, 1, dlt) + 2
        hb = (r - g) / np.where(dlt == 0, 1, dlt) + 4
    hue = np.where(mx == r, hr, np.where(mx == g, hg, hb)) * 60
    blue_mask = mask & (hue >= 190) & (hue <= 240) & (sat > 0.55) & (mx > 0.25)
    return total, int(blue_mask.sum())


def luminance(rgb):
    def ch(v):
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def region_stats(arr, box):
    x, y, w, h = [int(v) for v in box]
    H, W, _ = arr.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + max(1, w)), min(H, y + max(1, h))
    if x1 <= x0 or y1 <= y0:
        return None
    crop = arr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    lum = (0.2126 * crop[:, 0] + 0.7152 * crop[:, 1] + 0.0722 * crop[:, 2]) / 255.0
    order = np.argsort(lum)
    p05 = crop[order[int(len(order) * 0.05)]]
    p95 = crop[order[int(len(order) * 0.95)]]
    return {
        "contrast_p95_p05": float(round(float(contrast(tuple(p95), tuple(p05))), 2)),
        "lum_p05": round(float(lum[order[int(len(order) * 0.05)]]), 3),
        "lum_p95": round(float(lum[order[int(len(order) * 0.95)]]), 3),
        "dark_ratio": round(float((lum < 0.25).mean()), 3),
        "light_ratio": round(float((lum > 0.75).mean()), 3),
    }


def run_ocr(paths):
    out = {}
    if not os.path.exists(OCR):
        return out
    chunks = [paths[i:i + 12] for i in range(0, len(paths), 12)]
    for chunk in chunks:
        try:
            raw = subprocess.check_output([OCR] + chunk, cwd=HERE)
            for item in json.loads(raw.decode("utf-8")):
                if "texts" in item:
                    item["_path"] = item["file"]
                out[os.path.abspath(item["file"])] = item
        except Exception as e:
            print("OCR failed:", e)
    return out


def crop_temp(arr, box, name):
    x, y, w, h = [int(v) for v in box]
    H, W, _ = arr.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=name + "_")
    Image.fromarray(arr[y0:y1, x0:x1]).save(tmp.name)
    return tmp.name, (x0, y0)


def ocr_scaled(arr, max_dim=2048, name="scaled"):
    h, w, _ = arr.shape
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        im = Image.fromarray(arr).resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=name + "_")
        im.save(tmp.name)
        return tmp.name, scale
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=name + "_")
    Image.fromarray(arr).save(tmp.name)
    return tmp.name, 1.0


def texts_bounds(item, offset=(0, 0), scale=1.0):
    res = []
    for t in item.get("texts", []):
        W, H = item.get("width", 1), item.get("height", 1)
        x = t["x"] * W / max(scale, 1e-6) + offset[0]
        y = t["y"] * H / max(scale, 1e-6) + offset[1]
        w = t["w"] * W / max(scale, 1e-6)
        h = t["h"] * H / max(scale, 1e-6)
        res.append({"text": t["text"], "conf": t["conf"], "box": (x, y, w, h)})
    return res


def overlap_pairs(items):
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i]["box"], items[j]["box"]
            ax, ay, aw, ah = a; bx, by, bw, bh = b
            ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
            iy = max(0, min(ay + ah, by + bh) - max(ay, by))
            inter = ix * iy
            if inter <= 0:
                continue
            ratio = inter / max(1.0, min(aw * ah, bw * bh))
            if ratio > 0.30:
                pairs.append({"a": items[i]["text"], "b": items[j]["text"],
                              "overlap_ratio": round(ratio, 2)})
    return pairs


def cell_center_rgb(arr, box):
    x, y, w, h = box
    cx, cy = int(x + w / 2), int(y + h / 2)
    H, W, _ = arr.shape
    cx = max(0, min(W - 1, cx)); cy = max(0, min(H - 1, cy))
    patch = arr[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3].reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))


def analyze_chart(case, ocr_texts, legend_texts, tok, dark=False):
    path = case["chart_path"]
    arr = load(path)
    h, w, _ = arr.shape
    res = {"case": case["name"], "path": path, "size": [w, h],
           "grid": [case["grid"], case["grid"]], "cell": case["cell"],
           "total_beads": case["total_beads"], "color_count": case["color_count"],
           "palette": case["palette"], "dark": dark}
    corners = [patch_median(arr, 2, 2), patch_median(arr, w - 27, 2),
               patch_median(arr, 2, h - 27), patch_median(arr, w - 27, h - 27)]
    res["corners"] = [list(c) for c in corners]
    espresso = (42, 33, 24)
    bg_tok = tok["paper"]
    res["corner_tl_espresso"] = dist(corners[0], espresso) <= 3
    res["corner_other3_bg_delta"] = max(dist(c, bg_tok) for c in corners[1:])
    res["corner_other3_bg_ok"] = res["corner_other3_bg_delta"] <= 2
    res["has_old_blue_exact"], res["has_old_blue_broad"] = count_old_blue(arr)
    # 旧蓝只在「chrome 区」（边缘标号/页脚/图例文字区）计数，避免色卡内合法蓝色珠干扰
    band = np.zeros_like(arr)
    bh = int(h * 0.10); bw = int(w * 0.10)
    band[:bh, :, :] = 1; band[:, :bw, :] = 1
    band[max(0, h - int(h * 0.16)):, :, :] = 1
    band[int(h * 0.50):int(h * 0.86), :, :] = 1
    blue_band = 0
    for rgb in OLD_BLUE:
        d = np.abs(band.astype(np.int32) * arr.astype(np.int32)
                   - np.array(rgb, dtype=np.int32)).sum(axis=2)
        blue_band += int(((d <= 24) & (band[..., 0] == 1)).sum())
    res["old_blue_chrome_px"] = blue_band
    res["accent_px"] = count_near(arr, tok["accent"], 12)
    res["ink_px"] = count_near(arr, tok["ink"], 12)
    res["paperDeep_px"] = count_near(arr, tok["paperDeep"], 8)
    res["paperMat_px"] = count_near(arr, tok["paperMat"], 8)
    # 四边条带（页脚/图例/标号区）颜色
    bottom = arr[max(0, h - int(h * 0.12)):, :, :]
    res["footer_accent_ratio"] = round(float((np.abs(
        bottom.astype(np.int32) - np.array(tok["accent"], dtype=np.int32)).sum(axis=2) <= 18).mean()), 4)
    res["footer_bg"] = patch_median(arr, w // 2, h - 8, 16)
    left_band = arr[:, :max(8, int(w * 0.03))].reshape(-1, 3)
    top_band = arr[:max(8, int(h * 0.03)), :, :].reshape(-1, 3)
    def ratio(arr2, rgb, tol=8):
        return round(float(np.mean(np.abs(
            arr2.astype(np.int32) - np.array(rgb, dtype=np.int32)).sum(axis=1) <= tol)), 4)
    res["left_label_band"] = {"paperDeep": ratio(left_band, tok["paperDeep"]),
                              "ink": ratio(left_band, tok["ink"]),
                              "accent": ratio(left_band, tok["accent"]),
                              "old_blue": ratio(left_band, OLD_BLUE[0], 24)}
    res["top_label_band"] = {"paperDeep": ratio(top_band, tok["paperDeep"]),
                             "ink": ratio(top_band, tok["ink"]),
                             "accent": ratio(top_band, tok["accent"]),
                             "old_blue": ratio(top_band, OLD_BLUE[0], 24)}
    # 左上角块（espresso 底 + 奶油装饰）
    corner_block = arr[2:max(8, int(h * 0.03)), 2:max(8, int(w * 0.03))].reshape(-1, 3)
    res["corner_block"] = {"espresso_like": ratio(corner_block, tok["ink"]),
                           "cream_like": ratio(corner_block, tok["paper"])}
    # OCR 文本（由 main 预裁剪并 OCR 后传入）
    all_texts = ocr_texts
    texts = [t["text"] for t in all_texts]
    joined = " ".join(texts)
    res["ocr_texts"] = texts[:200]
    res["ocr_count"] = len(texts)
    # 信息完整性（token 检查）
    beads_expected = str(case.get("total_beads", "")).replace(",", "")
    beads_variants = [beads_expected, "{:,}".format(int(beads_expected)) if beads_expected.isdigit() else ""]
    up = joined.upper()
    checks = {
        "grid_dims": bool(re.search(r"(\d{2,4})\s*[×xX]\s*(\d{2,4})", joined)),
        "total_beads": any(v and v in joined for v in beads_variants)
                       or bool(re.search(r"[\d,]{3,}\s*(颗|顆)", joined)),
        "mard221": ("MARD" in up) and ("221" in joined),
        "plate": ("PLATE" in up) or ("拼豆图纸" in joined),
        "materials": ("MATER" in up) or ("耗材" in joined) or ("托材" in joined),
        "physical_size": ("CM" in up) or ("毫米" in joined) or ("MM" in up),
        "grid_label": ("GRID" in up) or ("网格" in joined),
        "beads_label": ("BEADS" in up) or ("颗豆" in joined) or ("颗" in joined),
    }
    res["info_checks"] = checks
    res["info_pass"] = all(checks.values())
    # 文本对比度（取 OCR 框区域 p95/p05 近似）
    contrasts = []
    for t in all_texts:
        if len(t["text"].strip()) < 2:
            continue
        st = region_stats(arr, t["box"])
        if st:
            contrasts.append({"text": t["text"][:16], "contrast": st["contrast_p95_p05"]})
    vals = [c["contrast"] for c in contrasts]
    res["text_contrast_median"] = round(float(np.median(vals)), 2) if vals else None
    res["text_contrast_min"] = round(float(np.min(vals)), 2) if vals else None
    res["text_contrast_n"] = len(vals)
    # 单元格色号文字对比度（浅色珠用 ink、深色珠用 paperMat 的目标产物）
    code_contrasts = []
    for t in all_texts:
        if re.fullmatch(r"[A-Z]{1,3}\d{1,3}", t["text"].strip()):
            st = region_stats(arr, t["box"])
            if st:
                code_contrasts.append(st["contrast_p95_p05"])
    res["cell_code_contrast_median"] = round(float(np.median(code_contrasts)), 2) if code_contrasts else None
    res["cell_code_contrast_min"] = round(float(np.min(code_contrasts)), 2) if code_contrasts else None
    res["cell_code_contrast_n"] = len(code_contrasts)
    res["cell_code_contrast_below_4_5"] = int(sum(1 for v in code_contrasts if v < 4.5))
    res["cell_code_contrast_below_3"] = int(sum(1 for v in code_contrasts if v < 3.0))
    worst = []
    for t in all_texts:
        if re.fullmatch(r"[A-Z]{1,3}\d{1,3}", t["text"].strip()):
            st = region_stats(arr, t["box"])
            if st:
                worst.append({"text": t["text"], "contrast": st["contrast_p95_p05"],
                              "box": [round(v, 1) for v in t["box"]],
                              "cell_center_rgb": [int(v) for v in cell_center_rgb(arr, t["box"])]})
    worst.sort(key=lambda x: x["contrast"])
    res["cell_code_worst10"] = worst[:10]
    # 图例区文字重叠（只用图例裁剪区自身的 OCR，避免重复框造成假阳性）
    res["ocr_overlaps"] = overlap_pairs(legend_texts)[:12]
    # 可读性：色号文本数量/高度
    codes = [t for t in all_texts if re.fullmatch(r"[A-Z]{1,3}\d{1,3}", t["text"].strip())]
    res["color_code_texts"] = len(codes)
    res["color_code_median_h_px"] = round(float(np.median([t["box"][3] for t in codes])), 1) if codes else None
    return res


def analyze_finished(case, tok, dark=False):
    if not case.get("finished_path"):
        return None
    arr = load(case["finished_path"])
    h, w, _ = arr.shape
    corners = [patch_median(arr, 2, 2), patch_median(arr, w - 27, 2),
               patch_median(arr, 2, h - 27), patch_median(arr, w - 27, h - 27)]
    return {"case": case["name"], "path": case["finished_path"], "size": [w, h],
            "corners": [list(c) for c in corners],
            "corner_paper_delta": min(dist(c, tok["paper"]) for c in corners),
            "corner_expect": list(tok["paper"]),
            "old_blue_exact": int(sum(
                int((np.abs(arr.astype(np.int32) - np.array(b, dtype=np.int32)).sum(axis=2) <= 24).sum())
                for b in OLD_BLUE))}


def analyze_pdf(pdf_path, tok, ocr_full, workdir, tag):
    info = {"path": pdf_path}
    try:
        out = subprocess.check_output(["pdfinfo", pdf_path], text=True)
        for line in out.splitlines():
            if line.startswith("Pages:"):
                info["pages"] = int(line.split(":")[1].strip())
            if line.startswith("Page size:"):
                m = re.search(r"([\d.]+) x ([\d.]+)", line)
                if m:
                    info["page_size_pt"] = [float(m.group(1)), float(m.group(2))]
    except Exception as e:
        info["pdfinfo_error"] = str(e)
    prefix = os.path.join(workdir, "pdf_" + tag)
    try:
        subprocess.check_call(["pdftoppm", "-r", "110", "-png", pdf_path, prefix],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        info["pdftoppm_error"] = str(e)
        return info
    pages = sorted([p for p in os.listdir(workdir) if p.startswith("pdf_" + tag) and p.endswith(".png")])
    page_reports = []
    for idx, name in enumerate(pages):
        arr = load(os.path.join(workdir, name))
        h, w, _ = arr.shape
        corners = [patch_median(arr, 3, 3), patch_median(arr, w - 28, 3),
                   patch_median(arr, 3, h - 28), patch_median(arr, w - 28, h - 28)]
        path = os.path.join(workdir, name)
        item = ocr_full.get(os.path.abspath(path))
        texts = [t["text"] for t in texts_bounds(item, (0, 0), 1.0)] if item else []
        page_reports.append({
            "index": idx + 1, "size_px": [w, h],
            "corners": [list(c) for c in corners],
            "corner_paper_delta": min(dist(c, tok["paper"]) for c in corners),
            "paper_ratio": round(float(np.mean(np.abs(
                arr.astype(np.int32) - np.array(tok["paper"], dtype=np.int32)).sum(axis=2) <= 8)), 4),
            "ocr_texts": texts[:40],
            "old_blue_chrome_px": sum(
                int((np.abs(arr.astype(np.int32) - np.array(b, dtype=np.int32)).sum(axis=2) <= 24).sum())
                for b in OLD_BLUE),
            "is_bom": any(("材料清单" in t) or ("色号" in t and "数量" in " ".join(texts))
                          or ("BOM" in t.upper() and "MATERIAL" in " ".join(texts).upper())
                          for t in texts),
            "is_chart_page": any(("PLATE" in t.upper()) or ("拼豆图纸" in t) for t in texts),
        })
    info["pages_raster"] = page_reports
    return info


CORE_TOKEN_MAP = {
    "PAPER": ("paper", "light"), "PAPER_DEEP": ("paperDeep", "light"),
    "PAPER_MAT": ("paperMat", "light"), "INK": ("ink", "light"),
    "INK_SOFT": ("inkSoft", "light"), "INK_MUTED": ("inkMuted", "light"),
    "HAIRLINE": ("hairline", "light"), "HAIRLINE_SOFT": ("hairlineSoft", "light"),
    "HAIRLINE_STRONG": ("hairlineStrong", "light"),
    "ACCENT": ("accent", "light"), "ACCENT_SOFT": ("accentSoft", "light"),
    "DARK_BG": ("paper", "dark"), "DARK_PANEL": ("paperDeep", "dark"),
    "DARK_INK": ("ink", "dark"), "DARK_INK_SOFT": ("inkSoft", "dark"),
    "DARK_HAIRLINE": ("hairline", "dark"), "DARK_ACCENT": ("accent", "dark"),
}


def parse_design_tokens():
    path = os.path.join(ROOT, "app/Sources/PerlerApp/DesignSystem.swift")
    raw = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(
            r"static\s+let\s+(\w+)\s*=\s*Color\.dynamic\(\s*light:\s*0x([0-9A-Fa-f]{6})\s*,"
            r"\s*dark:\s*0x([0-9A-Fa-f]{6})", raw):
        name = m.group(1)
        light = tuple(int(m.group(2)[i:i + 2], 16) for i in (0, 2, 4))
        dark = tuple(int(m.group(3)[i:i + 2], 16) for i in (0, 2, 4))
        out[name] = {"light": light, "dark": dark}
    return out


def token_source_compare():
    """解析 core/models.py 的 editorial tokens，与 Swift DesignSystem tokens 逐项比对（±2 RGB）。"""
    swift = parse_design_tokens()
    rows = []
    parsed = {}
    path = os.path.join(ROOT, "core/models.py")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8").read().splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)\s*=\s*(?:HAIRLINE|\()\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\)?",
                         line.strip())
            if not m:
                m2 = re.match(r"^([A-Z][A-Z0-9_]*)\s*=\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", line.strip())
                if not m2:
                    continue
                m = m2
            name = m.group(1)
            if name not in CORE_TOKEN_MAP:
                continue
            rgb = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
            swift_name, mode = CORE_TOKEN_MAP[name]
            if swift_name not in swift:
                rows.append({"core": name, "core_rgb": list(rgb), "swift": swift_name,
                             "mode": mode, "swift_rgb": None, "delta": None, "pass": False,
                             "note": "Swift token missing"})
                continue
            expected = swift[swift_name][mode]
            delta = dist(rgb, expected)
            parsed[name] = rgb
            rows.append({"core": name, "core_rgb": list(rgb), "swift": swift_name,
                         "mode": mode, "swift_rgb": list(expected),
                         "delta": delta, "pass": delta <= 2})
    return {"rows": rows, "parsed": {k: list(v) for k, v in parsed.items()},
            "swift_tokens": {k: {"light": list(v["light"]), "dark": list(v["dark"])}
                             for k, v in swift.items()},
            "pass": all(r["pass"] for r in rows) if rows else False,
            "fail_count": sum(1 for r in rows if not r["pass"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="after")
    ap.add_argument("--out", default=os.path.join(ROOT, "qa/verify/evidence/style"))
    ap.add_argument("--skip-pdf", action="store_true")
    args = ap.parse_args()
    base = os.path.join(args.out, args.tag)
    manifest = json.load(open(os.path.join(base, "manifest.json"), encoding="utf-8"))
    work = tempfile.mkdtemp(prefix="t17_pdf_")

    # 1) 每张图预裁剪：缩图（≤2048）+ 页脚 + 图例；一次批量 OCR
    crop_paths = []
    plan = {}   # case_name -> [(kind, path, scale, offset)]
    for c in manifest["cases"]:
        arr = load(c["chart_path"])
        h, w, _ = arr.shape
        lst = []
        sp, scale = ocr_scaled(arr, 2048, c["name"])
        crop_paths.append(sp); lst.append(("scaled", sp, scale, (0, 0)))
        fc, foff = crop_temp(arr, (0, int(h * 0.86), w, int(h * 0.14)), "footer")
        crop_paths.append(fc); lst.append(("footer", fc, 1.0, foff))
        lc, loff = crop_temp(arr, (0, int(h * 0.50), w, int(h * 0.36)), "legend")
        crop_paths.append(lc); lst.append(("legend", lc, 1.0, loff))
        plan[c["name"]] = lst
        if c.get("finished_path"):
            fa = load(c["finished_path"])
            fsp, fscale = ocr_scaled(fa, 2048, c["name"] + "_fin")
            crop_paths.append(fsp)
    ocr_map = run_ocr(crop_paths)
    texts_by_case = {}
    legend_by_case = {}
    for name, lst in plan.items():
        all_t = []
        leg_t = []
        for kind, path, scale, off in lst:
            item = ocr_map.get(os.path.abspath(path))
            if not item:
                continue
            got = texts_bounds(item, off, scale)
            if kind == "legend":
                leg_t.extend(got)
            if kind != "legend" or True:
                all_t.extend(got)
        texts_by_case[name] = all_t
        legend_by_case[name] = leg_t

    # 2) 图表/成品分析
    reports = {"tag": args.tag, "manifest": manifest, "charts": [], "finished": [],
               "pdfs": {}, "token_compare": token_source_compare()}
    for c in manifest["cases"]:
        dark = "dark" in c["name"]
        tok = TOK_DARK if dark else TOK_LIGHT
        rep = analyze_chart(c, texts_by_case.get(c["name"], []), legend_by_case.get(c["name"], []), tok, dark)
        reports["charts"].append(rep)
        fin = analyze_finished(c, TOK_LIGHT, dark)
        if fin:
            reports["finished"].append(fin)

    # 3) PDF：转图 + 逐页 OCR/分析
    if not args.skip_pdf:
        pdf_raster_paths = []
        for name, p in manifest.get("pdfs", {}).items():
            prefix = os.path.join(work, "pdf_" + name)
            try:
                subprocess.check_call(["pdftoppm", "-r", "110", "-png", p["path"], prefix],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        for f in sorted(os.listdir(work)):
            if f.endswith(".png"):
                pdf_raster_paths.append(os.path.join(work, f))
        ocr_map.update(run_ocr(pdf_raster_paths))
        for name, p in manifest.get("pdfs", {}).items():
            reports["pdfs"][name] = analyze_pdf(p["path"], TOK_LIGHT, ocr_map, work, name)

    out_path = os.path.join(args.out, "analysis_%s.json" % args.tag)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print("=== charts ===")
    for r in reports["charts"]:
        print("%-24s size=%s corner=%s blue(chrome,broad)=(%d,%d) accent=%d ink=%d paperDeep=%d footerAccent=%.4f info=%s contrast_med=%s n=%d codes=%d overlaps=%d" % (
            r["case"], r["size"], r["corners"][0], r["old_blue_chrome_px"], r["has_old_blue_broad"],
            r["accent_px"], r["ink_px"], r["paperDeep_px"], r["footer_accent_ratio"],
            r["info_pass"], r["text_contrast_median"], r["text_contrast_n"], r["color_code_texts"],
            len(r["ocr_overlaps"])))
        print("    info:", r["info_checks"], "contrast_min:", r["text_contrast_min"])
    print("=== finished ===")
    for r in reports["finished"]:
        print("%-24s size=%s corner_paper_delta=%s blue=%d" % (
            r["case"], r["size"], r["corner_paper_delta"], r["old_blue_exact"]))
    print("=== pdfs ===")
    for name, r in reports["pdfs"].items():
        print(name, "pages=", r.get("pages"), "size_pt=", r.get("page_size_pt"),
              "raster_pages=", len(r.get("pages_raster", [])),
              "corner_delta=", [p["corner_paper_delta"] for p in r.get("pages_raster", [])],
              "bom_pages=", [p["index"] for p in r.get("pages_raster", []) if p["is_bom"]])
    tc = reports["token_compare"]
    print("=== token source compare: rows=%d fail=%d pass=%s" % (len(tc["rows"]), tc["fail_count"], tc["pass"]))
    print("analysis ->", out_path)


if __name__ == "__main__":
    main()
