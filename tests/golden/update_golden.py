# tests/golden/update_golden.py - 有意改动输出后更新 golden 基准
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PIL import Image

from core.processor import ImageProcessor

GOLDEN_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    src = os.path.join(GOLDEN_DIR, "source.png")
    if not os.path.exists(src):
        random.seed(42)
        img = Image.new("RGB", (160, 120))
        px = img.load()
        for y in range(120):
            for x in range(160):
                px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        img.save(src)

    proc = ImageProcessor()
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


if __name__ == "__main__":
    main()
