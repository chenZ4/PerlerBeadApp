#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa/effects/style/make_style_evidence.py — T15 editorial 输出证据生成（可复跑）

生成：29×29 / 60×60 / 100×100 / cell16 小图 / dark_chart / finished /
A4 PDF 首页 / BOM 页 / 1:1 首页（PDF 用 pdftoppm 渲染 PNG）+ 校验数据 JSON。
复跑：
  cd <repo>
  PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python \
      qa/effects/style/make_style_evidence.py
"""
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
QA = os.path.dirname(HERE)                 # qa/effects
ROOT = os.path.dirname(os.path.dirname(QA))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.models import (ACCENT, DARK_ACCENT, DARK_BG, DARK_INK,  # noqa: E402
                         HAIRLINE_STRONG, INK, PAPER, PAPER_DEEP)
from core.processor import (FOOTER_HEIGHT, LABEL_MARGIN, LEGEND_ROW_H,  # noqa: E402
                            SIDE_MARGIN, ImageProcessor)

INPUTS = os.path.join(QA, "inputs")
OUT = HERE
CAT = os.path.join(INPUTS, "cartoon_cat.png")
EAGLE = os.path.join(INPUTS, "photo_eagle.png")
TRANS = os.path.join(INPUTS, "transparent_icon.png")
PROC = ImageProcessor()
KW = dict(cell_size=None, show_finished=True, save=False)
checks = {}


def counts(img):
    arr = np.asarray(img.convert("RGB")).reshape(-1, 3)
    uniq, cnt = np.unique(arr, axis=0, return_counts=True)
    return {tuple(int(v) for v in u): int(c) for u, c in zip(uniq, cnt)}


def save_chart(name, res):
    p = os.path.join(OUT, name)
    res.chart.save(p)
    return p


def main():
    print("[1/3] 生成 PNG 证据 ...")
    cases = [
        ("chart_29x29_cell60.png", CAT, 29, 29, 60, None),
        ("chart_60x60_cell20.png", EAGLE, 60, 60, 20, None),
        ("chart_100x100_cell16.png", EAGLE, 100, 100, 16, None),
        ("chart_cell16_small.png", CAT, 60, 60, 16, None),
        ("chart_dark_chart_29x29.png", CAT, 29, 29, 60,
         [{"id": "dark_chart", "params": {}}]),
    ]
    for name, src, gw, gh, cell, effects in cases:
        r = PROC.process_image(src, gw, gh, cell_size=cell, show_finished=True,
                               save=False, effects=effects)
        p = save_chart(name, r)
        a = r.chart.convert("RGB")
        w, h = a.size
        cc = counts(a)
        checks[name] = {
            "size": [w, h], "grid": [r.grid_w, r.grid_h],
            "cell_size": r.cell_size, "beads": r.total_beads,
            "colors": len(r.color_stats),
            "bg_top_right": list(a.getpixel((w - 3, 3))),
            "bg_bottom": list(a.getpixel((w // 2, h - 3))),
            "old_blue_px": cc.get((0, 120, 215), 0) + cc.get((120, 190, 255), 0),
            "paper_px": cc.get(PAPER, 0),
            "ink_px": cc.get(INK, 0),
            "accent_px": cc.get(ACCENT, 0),
            "hairline_strong_px": cc.get(HAIRLINE_STRONG, 0),
            "paper_deep_px": cc.get(PAPER_DEEP, 0),
            "legend_cols": PROC._legend_columns(r.color_stats)[0],
            "dark_ink_px": cc.get(DARK_INK, 0),
            "dark_accent_px": cc.get(DARK_ACCENT, 0),
            "file_bytes": os.path.getsize(p),
        }
        print("   ", name, checks[name]["size"], "bg", checks[name]["bg_top_right"])

    # tofu 复验 crop：图例最后两行（数量+颗）与页脚元数据（约/cm/颗）
    _r29 = PROC.process_image(CAT, 29, 29, cell_size=60, show_finished=True,
                              save=False)
    _a29 = _r29.chart.convert("RGB")
    _w29, _h29 = _a29.size
    _legend_bottom = _h29 - FOOTER_HEIGHT
    _a29.crop((0, _legend_bottom - 2 * LEGEND_ROW_H, _w29,
               _legend_bottom)).save(os.path.join(OUT, "tofu_check_legend.png"))
    _a29.crop((0, _h29 - FOOTER_HEIGHT, _w29, _h29)).save(
        os.path.join(OUT, "tofu_check_footer.png"))
    _r29.chart.close()
    _r29.finished.close()

    # finished：60×60 照片（全覆盖，无背景暴露）+ 透明素材（露出纸底）
    r = PROC.process_image(EAGLE, 60, 60, cell_size=20, show_finished=True, save=False)
    fp = os.path.join(OUT, "finished_60x60_cell20.png")
    r.finished.save(fp)
    checks["finished_60x60_cell20.png"] = {
        "size": list(r.finished.size), "file_bytes": os.path.getsize(fp),
    }
    rt = PROC.process_image(TRANS, 60, 60, cell_size=16, show_finished=True, save=False)
    tp = os.path.join(OUT, "finished_transparent_paper_bg.png")
    rt.finished.save(tp)
    fa = rt.finished.convert("RGB")
    holes = sum(1 for px in fa.getdata() if px == PAPER)
    checks["finished_transparent_paper_bg.png"] = {
        "size": list(rt.finished.size), "paper_hole_px": holes,
        "corner_top_right": list(fa.getpixel((fa.size[0] - 1, 1))),
        "file_bytes": os.path.getsize(tp),
    }
    for im in (r.chart, r.finished, rt.chart, rt.finished):
        im.close()

    print("[2/3] 生成 PDF 并渲染页面 PNG ...")
    r = PROC.process_image(EAGLE, 60, 60, cell_size=20, show_finished=False, save=False)
    a4 = os.path.join(OUT, "pdf_a4_chart.pdf")
    PROC.export_pdf(r.chart, a4, "a4", r.cell_size)
    bom = os.path.join(OUT, "pdf_bom.pdf")
    PROC.export_pdf(r.chart, bom, "a4", r.cell_size, bom=r.color_stats)
    one = os.path.join(OUT, "pdf_1x1.pdf")
    PROC.export_pdf(r.chart, one, "1x1", r.cell_size)
    def save_page_jpg(img, name):
        out = img.convert("RGB")
        if max(out.size) > 1600:
            r = 1600.0 / max(out.size)
            out = out.resize((max(1, int(out.size[0] * r)),
                              max(1, int(out.size[1] * r))), Image.LANCZOS)
        out.save(os.path.join(OUT, name), quality=85)

    page = PROC._export_pdf_a4_page(r.chart)
    save_page_jpg(page, "pdf_a4_page_render.jpg")
    bom_pages = PROC._pdf_bom_pages(r.color_stats)
    save_page_jpg(bom_pages[0], "pdf_bom_page1_render.jpg")
    save_page_jpg(bom_pages[-1], "pdf_bom_last_page_render.jpg")
    checks["pdf_a4_page_render.jpg"] = {
        "size": list(page.size), "bg": list(page.getpixel((5, 5))),
        "old_blue": (0, 120, 215) in counts(page),
    }
    checks["pdf_bom_page1_render.jpg"] = {
        "size": list(bom_pages[0].size), "bg": list(bom_pages[0].getpixel((5, 5))),
        "pages": len(bom_pages),
        "old_blue": (0, 120, 215) in counts(bom_pages[0]),
    }
    for f in (a4, bom, one):
        subprocess.run(["pdftoppm", "-png", "-r", "96", "-f", "1", "-singlefile",
                        f, f[:-4] + "_page1"], check=True)
        png = f[:-4] + "_page1.png"
        jpg = f[:-4] + "_page1.jpg"
        Image.open(png).convert("RGB").save(jpg, quality=88)
        os.remove(png)
    print("    pdf renders ok")

    print("[3/3] 写 checks.json ...")
    checks["_tokens"] = {
        "paper": list(PAPER), "ink": list(INK), "accent": list(ACCENT),
        "dark_bg": list(DARK_BG),
    }
    with open(os.path.join(OUT, "checks.json"), "w", encoding="utf-8") as f:
        json.dump(checks, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in checks.items()
                      if k.startswith("chart_") or k.startswith("finished")
                      or k.startswith("pdf_")}, ensure_ascii=False, indent=1)[:4000])
    r.chart.close()


if __name__ == "__main__":
    main()
