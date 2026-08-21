# tests/golden/update_golden.py - 有意改动输出后更新 golden 基准
# 用法：
#   python tests/golden/update_golden.py            # 更新单配置 golden.json
#   python tests/golden/update_golden.py --matrix   # 同时更新多配置 golden_matrix.json
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PIL import Image

from core.processor import ImageProcessor

GOLDEN_DIR = os.path.dirname(os.path.abspath(__file__))

# 多配置矩阵：锁定 比例模式 × 特效 × 色卡 的输出行为。
# 只字节哈希「逐元素运算」路径（broadcast/argmin，跨平台位稳定）；
# dither 走 BLAS matvec，跨平台可能有位差异 → 不入哈希矩阵，
# 由 run_tests 的结构断言覆盖（总量/色域/与无抖动映射不同）。
MATRIX = [
    {"name": "base_50x50", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "mard_221"},
    {"name": "exact_40x40", "grid_w": 40, "grid_h": 40, "cell_size": 60,
     "palette": "mard_221", "exact_grid": True},
    {"name": "fitbox_30x30", "grid_w": 30, "grid_h": 30, "cell_size": 60,
     "palette": "mard_221", "fit_box": True},
    {"name": "grayscale", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "mard_221",
     "effects": [{"id": "grayscale", "params": {}}]},
    {"name": "max_colors_6", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "mard_221",
     "effects": [{"id": "max_colors", "params": {"max": 6}}]},
    {"name": "outline_cell", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "mard_221",
     "effects": [{"id": "outline_cell", "params": {}}]},
    {"name": "dark_chart", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "mard_221",
     "effects": [{"id": "dark_chart", "params": {}}]},
    {"name": "basic_palette", "grid_w": 50, "grid_h": 50, "cell_size": 60,
     "palette": "basic"},
]


def ensure_source():
    src = os.path.join(GOLDEN_DIR, "source.png")
    if not os.path.exists(src):
        random.seed(42)
        img = Image.new("RGB", (160, 120))
        px = img.load()
        for y in range(120):
            for x in range(160):
                px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        img.save(src)
    return src


def update_single(proc, src):
    r = proc.process_image(src, 50, 50, cell_size=60, show_finished=True, save=False)
    h = hashlib.sha256(r.finished.tobytes()).hexdigest()
    meta = {
        "source": "source.png",
        "source_seed": 42,
        "grid_w": 50, "grid_h": 50, "cell_size": 60,
        "palette": "mard_221",
        "finished_sha256": h,
        "finished_size": list(r.finished.size),
        "note": "纯色成品图（无字体），跨平台稳定；改动输出后运行 update_golden.py 更新",
    }
    with open(os.path.join(GOLDEN_DIR, "golden.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    r.chart.close()
    r.finished.close()
    print(f"golden 已更新: {h}")


def update_matrix(proc, src):
    entries = []
    for cfg in MATRIX:
        r = proc.process_image(
            src, cfg["grid_w"], cfg["grid_h"], cell_size=cfg["cell_size"],
            palette_name=cfg["palette"], effects=cfg.get("effects"),
            exact_grid=cfg.get("exact_grid", False),
            fit_box=cfg.get("fit_box", False),
            show_finished=True, save=False)
        h = hashlib.sha256(r.finished.tobytes()).hexdigest()
        entries.append({
            "name": cfg["name"],
            "config": {k: v for k, v in cfg.items() if k != "name"},
            "finished_sha256": h,
            "finished_size": list(r.finished.size),
        })
        print(f"  matrix[{cfg['name']}]: {h[:12]}…")
        r.chart.close()
        r.finished.close()
    with open(os.path.join(GOLDEN_DIR, "golden_matrix.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "source.png", "entries": entries},
                  f, ensure_ascii=False, indent=2)
    print(f"golden_matrix 已更新: {len(entries)} 配置")


def main():
    matrix = "--matrix" in sys.argv
    src = ensure_source()
    proc = ImageProcessor()
    update_single(proc, src)
    if matrix:
        update_matrix(proc, src)


if __name__ == "__main__":
    main()
