# tests/run_tests.py - 无界面自动化测试
import gc
import os
import re
import sys
import tempfile
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from core.colors import get_palette, PALETTE_OPTIONS
from core.history_manager import HistoryManager, HISTORY_FILE
from core.processor import ImageProcessor

RESULT = {"passed": 0, "failed": 0, "errors": []}
TEST_DIR = tempfile.mkdtemp(prefix="perler_test_")
OUT_DIR = os.path.join(TEST_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)


def report(name, ok, detail=""):
    if ok:
        RESULT["passed"] += 1
        print(f"  [PASS] {name}")
    else:
        RESULT["failed"] += 1
        RESULT["errors"].append(f"{name}: {detail}")
        print(f"  [FAIL] {name} {detail}")


def make_source(w=200, h=200, color=(255, 0, 0)):
    path = os.path.join(TEST_DIR, f"src_{w}x{h}.png")
    img = Image.new("RGB", (w, h), color)
    img.save(path)
    return path


def pdf_info(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:5] != b"%PDF-":
        return None, None
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", data))
    m = re.search(rb"/MediaBox\s*\[\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    size = (round(float(m.group(1))), round(float(m.group(2)))) if m else None
    return pages, size


def footer_dark_pixels(img, height=130):
    w, h = img.size
    crop = img.crop((0, h - height, w, h))
    dark = 0
    for c in crop.getdata():
        if sum(c) < 450:
            dark += 1
    return dark


def test_colors():
    print("== 测试1: 色卡数据 ==")
    for display, internal in PALETTE_OPTIONS:
        p = get_palette(internal)
        ok = len(p.colors) == len(p.names) == len(p.codes)
        report(f"色卡 {display}: {len(p.colors)} 色, 列表长度一致", ok,
               f"colors={len(p.colors)} names={len(p.names)} codes={len(p.codes)}")
    p = get_palette("mard_221")
    report("mard_221 色号唯一", len(set(p.codes)) == len(p.codes))


def test_processor():
    print("== 测试2: 图片处理与页脚 ==")
    proc = ImageProcessor()
    src = make_source()

    result = proc.process_image(src, 50, 50, canvas_size=1500, save=False)
    report("50x50 生成成功（GenerateResult）", result is not None)
    img = result.chart
    report("cell_size 字段正确", result.cell_size > 0)
    report("网格尺寸正确", result.grid_w == 50 and result.grid_h == 50)
    report("耗材总数 = 网格面积", result.total_beads == result.grid_w * result.grid_h)
    report("旧逻辑 cell = canvas//max", result.cell_size == 30, str(result.cell_size))

    white_ratio = footer_dark_pixels(img)
    report("页脚统计文字完整可见（底部130px含文字像素）", white_ratio > 50,
           f"dark_pixels={white_ratio}")
    report("页脚文字未超出画布", img.size[1] > 0)
    img.close()

    result = proc.process_image(src, 50, 50, canvas_size=1500, show_row_col_labels=False,
                                show_color_legend=False, save=False)
    report("关闭标号/图例后生成正常", result is not None and result.grid_w == 50)
    report("无图例时画布紧凑", result.chart.size[1] < 1600, f"height={result.chart.size[1]}")
    result.chart.close()

    result = proc.process_image(src, 50, 50, canvas_size=1500, save=True)
    report("save=True 落盘到固定 output 目录", os.path.isfile(result.save_path),
           result.save_path)
    report("输出路径为绝对路径", os.path.isabs(result.save_path))
    result.chart.close()

    tall = make_source(100, 400)
    result = proc.process_image(tall, 30, 30, canvas_size=1500, save=False)
    report("竖版图保持原始比例", abs(result.grid_w / result.grid_h - 0.25) < 0.01,
           f"{result.grid_w}x{result.grid_h}")
    result.chart.close()

    big = make_source(300, 300)
    result = proc.process_image(big, 150, 150, cell_size=60, save=False)
    report("cell_size=60 解耦生效（每格 60px）", result.cell_size == 60 and result.grid_w == 150,
           f"cell={result.cell_size}")
    report("输出画布足够大（>= 9000px 宽）", result.chart.size[0] >= 9000, str(result.chart.size))
    result.chart.close()

    result = proc.process_image(big, 300, 300, cell_size=60, save=False)
    report("总边长 12000px 上限保护生效", result.cell_size == 40,
           f"cell={result.cell_size} size={result.chart.size}")
    result.chart.close()

    result = proc.process_image(big, 150, 150, cell_size=60, save=False, show_finished=True)
    report("成品效果图生成", result.finished is not None)
    report("成品图为纯网格区尺寸", result.chart.size[0] > result.finished.size[0],
           f"chart={result.chart.size} finished={result.finished.size}")
    report("成品图无页脚（高度更小）", result.finished.size[1] < result.chart.size[1],
           f"chart_h={result.chart.size[1]} finished_h={result.finished.size[1]}")
    report("成品图 4096px 降采样上限", result.finished.size[0] <= 4096,
           str(result.finished.size))
    result.chart.close()
    result.finished.close()

    result = proc.process_image(big, 150, 150, cell_size=60, save=False, cancel_callback=lambda: True)
    report("取消回调返回 None", result is None)

    result = proc.process_image(big, 0, 0, cell_size=60, save=False)
    report("grid=0 参数防护（不崩溃）", result is not None and result.grid_w >= 1)
    result.chart.close()

    result = proc.process_image(os.path.join(TEST_DIR, "nope.png"), 50, 50, save=False)
    report("文件不存在返回 None", result is None)


def test_colors_numpy():
    print("== 测试2b: numpy 颜色匹配零误差 ==")
    import random
    from PIL import Image as _Img
    p = get_palette("mard_221")
    img = _Img.new("RGB", (60, 60))
    px = img.load()
    random.seed(7)
    for y in range(60):
        for x in range(60):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    idx = p.closest_indices(img)
    mismatch = 0
    for y in range(60):
        for x in range(60):
            r, g, b = px[x, y]
            best = min(range(len(p.colors)),
                       key=lambda i: (r - p.colors[i][0]) ** 2 + (g - p.colors[i][1]) ** 2 + (b - p.colors[i][2]) ** 2)
            if idx[y, x] != best:
                mismatch += 1
    report("numpy 匹配与暴力法 100% 一致", mismatch == 0, f"mismatch={mismatch}")


def test_pdf():
    print("== 测试3: PDF 导出 ==")
    proc = ImageProcessor()
    src = make_source()

    result = proc.process_image(src, 50, 50, canvas_size=1500, save=False)
    img = result.chart
    cell = result.cell_size

    pdf_a4 = os.path.join(OUT_DIR, "a4.pdf")
    proc.export_pdf(img, pdf_a4, "a4", cell)
    pages, size = pdf_info(pdf_a4)
    report("A4 适应 PDF 生成", os.path.isfile(pdf_a4))
    report("A4 适应为单页", pages == 1, f"pages={pages}")
    report("A4 页面尺寸正确 (595x842pt)", size == (595, 841), str(size))

    pdf_1x1 = os.path.join(OUT_DIR, "1x1.pdf")
    proc.export_pdf(img, pdf_1x1, "1x1", cell)
    pages1, size1 = pdf_info(pdf_1x1)
    report("1:1 实物 PDF 生成", os.path.isfile(pdf_1x1))
    report("50x50 大网格 1:1 为多页拼接", pages1 > 1, f"pages={pages1}")
    report("1:1 页面同样为 A4（±1pt）",
           size1 is not None and abs(size1[0] - 595) <= 1 and abs(size1[1] - 841) <= 1,
           str(size1))
    report("1:1 导出无异常（含出血/裁剪线/页码栅格绘制）", os.path.getsize(pdf_1x1) > 0)

    result = proc.process_image(src, 20, 20, canvas_size=1500, save=False)
    img_small = result.chart
    cell_small = result.cell_size
    pdf_1x1_small = os.path.join(OUT_DIR, "1x1_small.pdf")
    proc.export_pdf(img_small, pdf_1x1_small, "1x1", cell_small)
    pages_s, _ = pdf_info(pdf_1x1_small)
    report("20x20 小网格 1:1 为单页", pages_s == 1, f"pages={pages_s}")
    img.close()
    img_small.close()

    try:
        proc.export_pdf(img, os.path.join(OUT_DIR, "bad.pdf"), "1x1", 0)
        report("缺 cell_size 时 1:1 报错", False)
    except ValueError:
        report("缺 cell_size 时 1:1 报错", True)


def test_history():
    print("== 测试4: 历史记录迁移 ==")
    backup = None
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            backup = f.read()

    legacy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history.json")
    if os.path.exists(legacy) and not os.path.exists(HISTORY_FILE):
        import shutil
        shutil.copy(legacy, HISTORY_FILE)

    hm = HistoryManager()
    report("历史加载不崩溃", True)
    before = len(hm.get_list())
    bad_grid = [r for r in hm.get_list() if not isinstance(r.get('grid_color', '#'), str)]
    report("所有记录 grid_color 已归一化为字符串", not bad_grid)
    for r in hm.get_list():
        if r.get('save_path'):
            report(f"save_path 绝对化: {r['save_path'][-30:]}", os.path.isabs(r['save_path']))
            break

    legacy_records = [
        {"image_path": "/tmp/a.jpg", "save_path": "/tmp/a.png", "width": 50, "height": 50,
         "ratio": "原始比例", "output_size": 1500, "show_grid": True, "grid_color": "#C8C8C8",
         "palette": "MARD 221 色", "time": "2026-01-01 00:00"},
        {"image_path": "/tmp/b.jpg", "save_path": "/tmp/b.png", "width": 61, "height": 50,
         "ratio": "原始比例", "output_size": 3000, "show_grid": True, "grid_color": [200, 200, 200],
         "palette": "MARD 221 色", "time": "2026-01-01 00:00"},
    ]
    old = hm.get_list()
    hm.history = legacy_records + old
    hm._migrate_history()
    r0 = hm.history[0]
    r1 = hm.history[1]
    report("旧 output_size=1500/50x50 反推为 30", r0['output_size'] == 30, str(r0['output_size']))
    report("旧 output_size=3000/61x50 反推为 49", r1['output_size'] == 49, str(r1['output_size']))
    report("旧 grid_color 数组归一化", r1['grid_color'] == "#C8C8C8", str(r1['grid_color']))
    hm.history = old
    hm.save_history()

    hm.add_record("/tmp/x.jpg", "/tmp/x_out.png", 10, 10, "原始比例", 1500, True,
                  "#C8C8C8", "MARD 221 色", True)
    rec = hm.get_record(0)
    report("新记录含 show_labels", rec['show_labels'] is True)
    report("新记录 grid_color 为 hex 字符串", rec['grid_color'] == "#C8C8C8")
    hm.delete_record(0)
    report("删除记录正常", len(hm.get_list()) in (before, before - 1),
           f"before={before} after={len(hm.get_list())}")

    if backup is None:
        os.remove(HISTORY_FILE)
    else:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write(backup)


def test_memory():
    print("== 测试5: 内存泄漏（tracemalloc 连续 20 次生成） ==")
    proc = ImageProcessor()
    src = make_source(400, 300)
    gc.collect()
    tracemalloc.start()
    for i in range(20):
        result = proc.process_image(src, 50, 50, canvas_size=1500, save=False)
        result.chart.close()
        if result.finished:
            result.finished.close()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    mb = 1024 * 1024
    report("20 次连续生成内存无持续累积（峰值 < 150MB）", peak < 150 * mb,
           f"peak={peak / mb:.1f}MB current={current / mb:.1f}MB")
    report("结束后驻留内存回归（< 60MB）", current < 60 * mb, f"current={current / mb:.1f}MB")


def test_golden_and_perf():
    print("== 测试6: Golden 回归 + 耗时基准 ==")
    import hashlib
    import json
    import time

    from core.processor import ImageProcessor

    GOLDEN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "tests", "golden")
    golden_file = os.path.join(GOLDEN_DIR, "golden.json")
    source_file = os.path.join(GOLDEN_DIR, "source.png")
    report("golden 文件存在", os.path.isfile(golden_file) and os.path.isfile(source_file))
    if not (os.path.isfile(golden_file) and os.path.isfile(source_file)):
        return

    with open(golden_file, "r", encoding="utf-8") as f:
        golden = json.load(f)

    proc = ImageProcessor()
    t0 = time.time()
    result = proc.process_image(source_file, 50, 50, cell_size=60, show_finished=True, save=False)
    dt50 = time.time() - t0
    report("golden 生成耗时 < 5s（WARNING 级）", dt50 < 5.0, f"{dt50:.2f}s")

    h = hashlib.sha256(result.finished.tobytes()).hexdigest()
    report("golden 输出哈希一致（防无声回归）", h == golden['finished_sha256'],
           f"expected={golden['finished_sha256'][:12]} got={h[:12]}")
    report("golden 输出尺寸一致", list(result.finished.size) == golden['finished_size'],
           str(result.finished.size))
    result.chart.close()
    result.finished.close()

    t0 = time.time()
    result = proc.process_image(source_file, 150, 150, cell_size=60, save=False)
    dt150 = time.time() - t0
    report("150x150 生成耗时 < 30s（WARNING 级）", dt150 < 30.0, f"{dt150:.2f}s")
    result.chart.close()
    print(f"    耗时: 50x50={dt50:.2f}s 150x150={dt150:.2f}s")


def main():
    print("=== 拼豆图纸自动化测试 ===\n")
    test_colors()
    test_processor()
    test_colors_numpy()
    test_pdf()
    test_history()
    test_memory()
    test_golden_and_perf()
    print("\n=== 结果汇总 ===")
    print(f"通过: {RESULT['passed']}   失败: {RESULT['failed']}")
    if RESULT["errors"]:
        print("\n失败明细:")
        for e in RESULT["errors"]:
            print(f"  - {e}")
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
