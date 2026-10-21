#!/usr/bin/env python3
"""T3 测试有效性探针：run_tests.py 的特效断言能否区分"真实特效"与"no-op(原样返回)"？

复刻 tests/run_tests.py::test_effects (L743-919) 的输入 fixture 与断言谓词，
分别用"真实特效输出"和"无特效基线输出"代入断言：
  - assertion_pass_on_real   : 现有门禁用真实特效跑时的通过情况（应全 True，与 230/230 一致）
  - assertion_pass_if_noop   : 若 handler 被替换为 return img / return idx（no-op），断言是否仍通过
  - vacuous                  : True 表示该断言对"特效是否真的发生"零区分力 —— 代码绿但效果可为空
  - effect_changed_pct       : 真实特效相对无特效基线的图纸像素改变比例（可见度参考）

全部 save=False + 临时目录，不写共享 output/。
运行：conda run -n pindou python qa/gates/probes/test_discrimination_probe.py
"""
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from core.processor import ImageProcessor  # noqa: E402

TMP = tempfile.mkdtemp(prefix="perler_gate_disc_")
PROC = ImageProcessor()


def _save(name, img):
    p = os.path.join(TMP, name)
    img.save(p)
    return p


def _arr(r):
    return np.asarray(r.chart.convert("RGB"))


def _close(r):
    try:
        r.chart.close()
    except Exception:
        pass
    fin = getattr(r, "finished", None)
    if fin is not None:
        try:
            fin.close()
        except Exception:
            pass


def _gen(path, grid, cell, effects=None):
    return PROC.process_image(path, grid, grid, cell_size=cell, save=False,
                              effects=effects or [])


# ---- 复刻 run_tests 的 fixture ----
solid = _save("src_solid_red.png", Image.new("RGB", (200, 200), (255, 0, 0)))

grad_img = Image.new("RGB", (200, 200))
_px = grad_img.load()
for _y in range(200):
    for _x in range(200):
        _px[_x, _y] = (_x, _y, 128)
grad = _save("grad.png", grad_img)

flat = _save("flat.png", Image.new("RGB", (60, 60), (30, 120, 220)))

wb_img = Image.new("RGB", (200, 200), (255, 255, 255))
_wpx = wb_img.load()
for _y in range(40, 160):
    for _x in range(40, 160):
        _wpx[_x, _y] = (255, 0, 0)
wb = _save("wb.png", wb_img)

FIXTURES = {
    # name: (path, grid, cell)
    "solid40": (solid, 40, 40),
    "solid30": (solid, 30, 40),
    "grad40": (grad, 40, 40),
    "grad30": (grad, 30, 40),
    "flat12": (flat, 12, 20),
    "wb40": (wb, 40, 40),
}

BASE = {}
for key, (path, grid, cell) in FIXTURES.items():
    r = _gen(path, grid, cell)
    BASE[key] = {"arr": _arr(r), "stats": dict(r.color_stats),
                 "total": r.total_beads, "not_none": r is not None}
    _close(r)


def _diff_pct(a, b):
    if a.shape != b.shape:
        return 1.0
    return float((a != b).any(axis=2).mean())


def run_case(effect, fixture, params, assertion, predicate, compare_to_baseline=False):
    """返回结果行。predicate(real_result_or_none) -> bool"""
    path, grid, cell = FIXTURES[fixture]
    base = BASE[fixture]
    effects = [{"id": effect, "params": params}]
    r_real = _gen(path, grid, cell, effects)
    arr = _arr(r_real)
    changed = _diff_pct(arr, base["arr"])
    pass_real = bool(predicate(r_real, base))
    if compare_to_baseline:
        pass_noop = bool(predicate(None, base, use_baseline=True))   # 对比型断言：no-op 时两边相同
    else:
        pass_noop = bool(predicate(r_real, base, use_baseline=True)) \
            if predicate.__code__.co_argcount >= 3 else bool(predicate(None, base))
    _close(r_real)
    return {
        "effect": effect,
        "fixture": fixture,
        "params": params,
        "assertion": assertion,
        "pass_on_real": pass_real,
        "pass_if_noop": pass_noop,
        "vacuous": bool(pass_noop),
        "effect_changed_pct": round(changed * 100, 2),
    }


def pred_not_none(r, base, use_baseline=False):
    if use_baseline:
        return base["not_none"]
    return r is not None


def pred_cel_colored(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return bool(stats) and any(
        sum(i["rgb"]) > 60 and max(i["rgb"]) - min(i["rgb"]) > 30
        for i in stats.values())


def pred_stats_nonempty(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return len(stats) > 0


def pred_outline_default_one_color(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return len(stats) == 1


def pred_outline_outer_two_colors(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return len(stats) == 2


def pred_black_present(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return any(sum(i["rgb"]) < 200 for i in stats.values())


def pred_gray_only(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return bool(stats) and all(abs(i["rgb"][0] - i["rgb"][1]) <= 20 and
                               abs(i["rgb"][1] - i["rgb"][2]) <= 20
                               for i in stats.values())


def pred_dither_diff(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return stats != base["stats"] or len(stats) != len(base["stats"])


def pred_le6(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    return len(stats) <= 6


def pred_dark_frac(r, base, use_baseline=False):
    if use_baseline:
        data = list(base["arr"].reshape(-1, 3))
    else:
        data = list(_arr(r).reshape(-1, 3))
    dark = sum(1 for p in data if int(p[0]) + int(p[1]) + int(p[2]) < 300)
    return dark / len(data) > 0.3


def pred_adjust_diff(r, base, use_baseline=False):
    stats = base["stats"] if use_baseline else r.color_stats
    total = base["total"] if use_baseline else r.total_beads
    return stats != base["stats"] or total != base["total"]


def pred_bg_less(r, base, use_baseline=False):
    total = base["total"] if use_baseline else r.total_beads
    return total < base["total"]


CASES = [
    ("outline_cell", "solid40", {"outline_outer": True},
     "r.color_stats 中存在近黑描边色", pred_black_present, False),
    ("outline_cell", "flat12", {},
     "默认参数纯色图仍 1 色（不描外轮廓）", pred_outline_default_one_color, False),
    ("outline_cell", "flat12", {"outline_outer": True},
     "显式外轮廓纯色图 2 色", pred_outline_outer_two_colors, False),
    ("outline_edge", "solid40", {"threshold": 120},
     "r is not None（仅不崩溃）", pred_not_none, False),
    ("grayscale", "solid30", {},
     "输出颜色全部为灰阶", pred_gray_only, False),
    ("dither", "grad40", {"strength": 1.0},
     "颜色映射与无抖动不同", pred_dither_diff, True),
    ("max_colors", "grad40", {"max": 6},
     "颜色数 <= 6", pred_le6, False),
    ("preset", "grad40", {"preset": "pastel"},
     "马卡龙预设 <= 6 色", pred_le6, False),
    ("dark_chart", "grad40", {},
     "深色像素占比 > 30%", pred_dark_frac, False),
    ("adjust", "grad30", {"brightness": 1.5},
     "映射结果与默认不同", pred_adjust_diff, True),
    ("cel_shade", "solid30", {"levels": 4},
     "输出存在彩色像素（保留色相）", pred_cel_colored, False),
    ("neon", "solid30", {},
     "r is not None（仅不崩溃）", pred_not_none, False),
    ("duotone", "solid30", {},
     "r is not None 且 color_stats 非空", pred_stats_nonempty, False),
    ("mirror", "solid30", {"direction": "horizontal"},
     "r is not None（仅不崩溃）", pred_not_none, False),
    ("crop", "solid30", {"x1": 0.5, "y1": 0.5},
     "r is not None（仅不崩溃）", pred_not_none, False),
    ("bg_remove", "wb40", {"color": "#FFFFFF"},
     "耗材数少于不去背景", pred_bg_less, False),
    ("chibi", "solid30", {},
     "r is not None（无人脸原样输出）", pred_not_none, False),
]

rows = []
for effect, fixture, params, assertion, predicate, cmp_base in CASES:
    rows.append(run_case(effect, fixture, params, assertion, predicate, cmp_base))

print("=" * 100)
print("T3 探针：run_tests.py::test_effects 断言区分力（fixtures 完全复刻门禁用例）")
print("=" * 100)
hdr = f"{'effect':<13} {'fixture':<9} {'real':<5} {'noop':<5} {'vacuous':<8} {'changed%':<9} assertion"
print(hdr)
print("-" * 100)
for row in rows:
    print(f"{row['effect']:<13} {row['fixture']:<9} "
          f"{str(row['pass_on_real']):<5} {str(row['pass_if_noop']):<5} "
          f"{str(row['vacuous']):<8} {row['effect_changed_pct']:<9} {row['assertion']}")

vacuous_effects = sorted({r["effect"] for r in rows if r["vacuous"]})
all_effects = sorted({r["effect"] for r in rows})
fully_vacuous = [e for e in all_effects
                 if all(r["vacuous"] for r in rows if r["effect"] == e)]
print("-" * 100)
print("完全可被 no-op 骗过的特效（其全部断言在 no-op 下仍通过）:",
      fully_vacuous)
print("至少一条断言可被 no-op 骗过的特效:", vacuous_effects)
print()
print("JSON:", json.dumps(rows, ensure_ascii=False))
