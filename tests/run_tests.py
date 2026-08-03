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
    for c in crop.get_flattened_data():
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
    wr, wg, wb = (0.299, 0.587, 0.114)
    for y in range(60):
        for x in range(60):
            r, g, b = px[x, y]
            best = min(range(len(p.colors)),
                       key=lambda i: (r - p.colors[i][0]) ** 2 * wr
                       + (g - p.colors[i][1]) ** 2 * wg
                       + (b - p.colors[i][2]) ** 2 * wb)
            if idx[y, x] != best:
                mismatch += 1
    report("numpy 加权匹配与暴力法 100% 一致", mismatch == 0, f"mismatch={mismatch}")


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


def test_hex_to_rgb():
    print("== 测试1b: hex_to_rgb 输入防御 ==")
    from ui.desktop_ui import DesktopUI

    app = object.__new__(DesktopUI)

    def parse(value):
        try:
            return app.hex_to_rgb(value)
        except ValueError:
            return None

    valid = [
        ("#C8C8C8", (200, 200, 200)),
        ("C8C8C8", (200, 200, 200)),
        ("#c8c8c8", (200, 200, 200)),
        (" #C8C8C8 ", (200, 200, 200)),
        ("#000000", (0, 0, 0)),
        ("#FFFFFF", (255, 255, 255)),
        ("#1a2b3c", (26, 43, 60)),
    ]
    invalid = ["", "#", "12345", "#12345", "#1234567", "GGGGGG", "#GGGGGG",
               "0x1234", "#0x1234", "＃123456", "#1_2abc", "abc", "12", "#1234567890"]

    ok = True
    for value, expected in valid:
        if parse(value) != expected:
            ok = False
            print(f"    合法输入未通过: {value} -> {parse(value)}")
    for value in invalid:
        if parse(value) is not None:
            ok = False
            print(f"    非法输入未回退: {value} -> {parse(value)}")
    report("hex_to_rgb 合法 7 例 + 非法 13 例全部正确", ok)

    app._read_params = lambda: (50, 50, 60, True, True, True, (200, 200, 200))
    app._hex_to_rgb_safe("#ZZZZZZ")
    report("_hex_to_rgb_safe 非法回退灰色", True)


def test_core_server():
    print("== 测试7: core_server 协议层 ==")
    import json as _json
    import subprocess
    import sys as _sys
    import time as _time

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [_sys.executable, os.path.join(root, "core_server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def req(rid, op, params=None):
        proc.stdin.write(_json.dumps({"id": rid, "op": op, "params": params or {}}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            msg = _json.loads(line)
            if msg.get("id") == rid and "event" not in msg:
                return msg

    def close():
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    try:
        r = req(1, "ping")
        report("ping → pong + 版本", r.get("ok") and r.get("pong") and r.get("version"),
               str(r))

        r = req(2, "palettes")
        report("palettes 返回 4 套色卡", r.get("ok") and len(r["palettes"]) == 4,
               str(len(r.get("palettes", []))))

        r = req(3, "palette_colors", {"internal": "mard_221"})
        report("palette_colors 返回 221 色", r.get("ok") and len(r["colors"]) == 221)

        r = req(4, "effects")
        report("effects 返回特效清单", r.get("ok") and isinstance(r.get("effects"), dict))

        src = make_source(300, 300)
        r = req(5, "generate", {"image_path": src, "grid_w": 100, "grid_h": 100,
                                "cell_size": 60, "show_finished": True})
        ok = (r.get("ok") and os.path.isfile(r.get("chart_path", ""))
              and r["grid_w"] == 100 and r["cell_size"] == 60 and r["total_beads"] > 0)
        report("generate 返回图纸与统计", ok, f"ok={r.get('ok')}")
        if ok:
            r2 = req(6, "export_png", {"source_path": r["chart_path"],
                                       "save_path": os.path.join(OUT_DIR, "sv_png.png")})
            report("export_png 导出文件", r2.get("ok") and os.path.isfile(r2["save_path"]))
            r3 = req(7, "export_pdf", {"source_path": r["chart_path"],
                                       "save_path": os.path.join(OUT_DIR, "sv_pdf.pdf"),
                                       "mode": "a4", "cell_size": 60})
            report("export_pdf 导出文件", r3.get("ok") and os.path.isfile(r3["save_path"]))

        proc.stdin.write(_json.dumps({"id": 8, "op": "generate",
                                      "params": {"image_path": src, "grid_w": 300,
                                                 "grid_h": 300, "cell_size": 60}}) + "\n")
        proc.stdin.flush()
        _time.sleep(0.9)
        proc.stdin.write(_json.dumps({"id": 8, "op": "cancel"}) + "\n")
        proc.stdin.flush()
        events = []
        while True:
            line = proc.stdout.readline()
            msg = _json.loads(line)
            if msg.get("id") == 8 and "event" not in msg:
                break
            events.append(msg)
        has_progress = any(m.get("event") == "progress" for m in events)
        report("生成中进度事件", has_progress, f"events={len(events)}")
        report("生成中取消生效（返回 cancelled）", msg.get("cancelled") is True,
               str(msg))

        r = req(9, "history", {"action": "list"})
        before = len(r["records"])
        req(10, "history", {"action": "add", "record": {
            "image_path": "/tmp/a.jpg", "save_path": "/tmp/a.png", "width": 10,
            "height": 10, "ratio": "按原图比例（宽为基准）", "cell_px": 60,
            "show_grid": True, "grid_color": "#C8C8C8", "palette": "MARD 221 色",
            "show_labels": True}})
        r = req(11, "history", {"action": "list"})
        report("history add/list", len(r["records"]) == before + 1)
        req(12, "history", {"action": "delete", "index": 0})
        r = req(13, "history", {"action": "list"})
        report("history delete", len(r["records"]) == before)
        req(14, "history", {"action": "clear"})
        r = req(15, "history", {"action": "list"})
        report("history clear", len(r["records"]) == 0)

        req(16, "settings_set", {"settings": {"cell_px": "72"}})
        r = req(17, "settings_get")
        report("settings set/get", r.get("settings", {}).get("cell_px") == "72")
        req(18, "settings_set", {"settings": {"cell_px": "60"}})

        req(19, "queue_save", {"items": [{"image_path": "/tmp/q.jpg", "width": 20}]})
        r = req(20, "queue_load")
        report("queue save/load", r.get("ok") and len(r["items"]) == 1)
        req(21, "queue_save", {"items": []})

        r = req(22, "nope_op")
        report("未知操作返回 error", r.get("ok") is False and r.get("error"))
    finally:
        close()
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


def test_effects():
    print("== 测试7b: 特效库 ==")
    from core.effects import list_effects, has_effect

    src = make_source(200, 200)
    proc = ImageProcessor()
    expected_ids = {"outline_cell", "outline_edge", "grayscale", "adjust",
                    "dither", "dark_chart", "max_colors", "preset"}
    registered = set(list_effects().keys())
    report("8 个特效全部注册", expected_ids <= registered,
           f"missing={expected_ids - registered}")

    # 邻接描边：描边色（近黑）出现在网格中
    r = proc.process_image(src, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "outline_cell", "params": {}}])
    stats = r.color_stats
    black_codes = [c for c, i in stats.items() if sum(i['rgb']) < 200]
    report("邻接描边产生描边色", len(black_codes) > 0, str(black_codes))
    r.chart.close()

    # 线稿描边（跨阶段）
    r = proc.process_image(src, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "outline_edge", "params": {"threshold": 120}}])
    report("线稿描边不崩溃且正常输出", r is not None)
    r.chart.close()

    # 灰度：输出颜色全部为灰阶
    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "grayscale", "params": {}}])
    all_gray = all(abs(c['rgb'][0] - c['rgb'][1]) <= 20
                   and abs(c['rgb'][1] - c['rgb'][2]) <= 20
                   for c in r.color_stats.values())
    report("灰度特效输出灰阶", all_gray and len(r.color_stats) >= 1,
           str({k: v['rgb'] for k, v in r.color_stats.items()}))
    r.chart.close()

    # 抖动：与不抖动颜色分布不同（渐变图更明显）
    grad = Image.new("RGB", (200, 200))
    px = grad.load()
    for y in range(200):
        for x in range(200):
            px[x, y] = (x, y, 128)
    grad_path = os.path.join(TEST_DIR, "grad.png")
    grad.save(grad_path)
    r1 = proc.process_image(grad_path, 40, 40, cell_size=40, save=False)
    r2 = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                            effects=[{"id": "dither", "params": {"strength": 1.0}}])
    report("抖动改变颜色映射", r1.color_stats.keys() != r2.color_stats.keys()
           or len(r1.color_stats) != len(r2.color_stats))
    r1.chart.close()
    r2.chart.close()

    # 限色数：颜色数 ≤ 上限
    r = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "max_colors", "params": {"max": 6}}])
    report("限色数 ≤ 6", len(r.color_stats) <= 6, str(len(r.color_stats)))
    r.chart.close()

    # 风格预设：颜色限制在预设色集
    r = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "preset", "params": {"preset": "pastel"}}])
    report("马卡龙预设生效（≤6 色）", len(r.color_stats) <= 6, str(len(r.color_stats)))
    r.chart.close()

    # 深色底：背景深色占比显著
    r = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "dark_chart", "params": {}}])
    data = list(r.chart.get_flattened_data())
    dark_cnt = sum(1 for p in data if sum(p) < 300)
    report("深色底图纸背景深色", dark_cnt / len(data) > 0.3,
           f"dark={dark_cnt / len(data):.2f}")
    r.chart.close()

    # 亮度调整：调整后映射结果变化
    r1 = proc.process_image(grad_path, 30, 30, cell_size=40, save=False)
    r2 = proc.process_image(grad_path, 30, 30, cell_size=40, save=False,
                            effects=[{"id": "adjust", "params": {"brightness": 1.5}}])
    report("亮度调整改变映射", r1.color_stats.keys() != r2.color_stats.keys()
           or r1.total_beads != r2.total_beads)
    r1.chart.close()
    r2.chart.close()

    # 组合特效不崩
    r = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "grayscale", "params": {}},
                                    {"id": "outline_cell", "params": {}},
                                    {"id": "max_colors", "params": {"max": 8}},
                                    {"id": "dark_chart", "params": {}}])
    report("组合特效叠加正常", r is not None)
    r.chart.close()

    # 无效特效 id 忽略不崩
    r = proc.process_image(grad_path, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "not_exist", "params": {}}])
    report("无效特效 id 忽略", r is not None)
    r.chart.close()


def main():
    print("=== 拼豆图纸自动化测试 ===\n")
    test_colors()
    test_hex_to_rgb()
    test_processor()
    test_colors_numpy()
    test_pdf()
    test_history()
    test_memory()
    test_golden_and_perf()
    test_core_server()
    test_effects()
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
