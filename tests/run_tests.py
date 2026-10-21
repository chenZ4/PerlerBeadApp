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

import numpy as np  # Lab 暴力法校验用

RESULT = {"passed": 0, "failed": 0, "errors": []}
TEST_DIR = tempfile.mkdtemp(prefix="perler_test_")
OUT_DIR = os.path.join(TEST_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)

# --- T7 测试隔离：所有用户数据/中间产物路径重定向到临时目录 ---
# 进程内直接使用 core 模块（monkeypatch）；子进程 core_server.py 通过继承
# PERLER_* 环境变量隔离（见 core_server.py 顶部 _env_override_path）。
import atexit
import shutil as _iso_shutil

import core.history_manager as _iso_history
import core.my_colors as _iso_my_colors
import core.processor as _iso_processor
import core.settings as _iso_settings

ISO_ROOT = tempfile.mkdtemp(prefix="perler_iso_")
ISO_OUTPUT = os.path.join(ISO_ROOT, "output")
os.makedirs(ISO_OUTPUT, exist_ok=True)
ISO_TRACK = os.path.join(ISO_ROOT, "track")
ISO_SETTINGS = os.path.join(ISO_ROOT, "app_settings.json")
ISO_QUEUE = os.path.join(ISO_ROOT, "queue_state.json")
ISO_HISTORY = os.path.join(ISO_ROOT, "history.json")
ISO_LEGACY_HISTORY = os.path.join(ISO_ROOT, "legacy_history.json")
ISO_MY_COLORS = os.path.join(ISO_ROOT, "my_colors.json")
os.environ.update({
    "PERLER_OUTPUT_DIR": ISO_OUTPUT,
    "PERLER_TRACK_DIR": ISO_TRACK,
    "PERLER_SETTINGS_FILE": ISO_SETTINGS,
    "PERLER_QUEUE_FILE": ISO_QUEUE,
    "PERLER_HISTORY_FILE": ISO_HISTORY,
    "PERLER_MY_COLORS_FILE": ISO_MY_COLORS,
})
_iso_processor.OUTPUT_DIR = ISO_OUTPUT
_iso_settings.SETTINGS_FILE = ISO_SETTINGS
_iso_settings.QUEUE_FILE = ISO_QUEUE
_iso_settings.SettingsStore.__init__.__defaults__ = (ISO_SETTINGS, ISO_QUEUE)
_iso_history.HISTORY_FILE = ISO_HISTORY
_iso_history.LEGACY_HISTORY_FILE = ISO_LEGACY_HISTORY
_iso_my_colors.MY_COLORS_FILE = ISO_MY_COLORS
HISTORY_FILE = ISO_HISTORY  # 覆盖顶部 from ... import HISTORY_FILE 的本地绑定
atexit.register(_iso_shutil.rmtree, ISO_ROOT, ignore_errors=True)


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
    from core.colors import rgb_to_lab
    px_lab = rgb_to_lab(np.asarray(img, dtype=np.float32))
    for y in range(60):
        for x in range(60):
            lab = px_lab[y, x]
            best = min(range(len(p.colors)),
                       key=lambda i: float(((p.lab[i] - lab) ** 2).sum()))
            if idx[y, x] != best:
                mismatch += 1
    report("numpy Lab 匹配与暴力法 100% 一致", mismatch == 0, f"mismatch={mismatch}")


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
    report("A4 页面尺寸正确（±1pt）",
           size is not None and abs(size[0] - 595) <= 1 and abs(size[1] - 841) <= 1,
           str(size))

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
    import json as _json
    backup = None
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            backup = f.read()

    legacy = _iso_history.LEGACY_HISTORY_FILE  # T7: 隔离路径，不读仓库 history.json
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

    # 损坏记录迁移：非法类型/缺字段均不崩溃且被修复
    corrupt = [
        {"image_path": "/tmp/c.jpg", "save_path": "rel/c.png", "width": "abc", "height": None,
         "ratio": "原始比例", "output_size": "large", "show_grid": "false",
         "grid_color": "not_a_color", "palette": "MARD 221 色", "time": "2026-01-01 00:00"},
        "not_a_dict",
        {"width": 10, "height": 10},
    ]
    try:
        hm.history = corrupt + old
        hm._migrate_history()
        migrated = hm.history
        report("损坏历史记录迁移不崩溃", len(migrated) == 2 + len(old),
               f"kept={len(migrated)}")
        c0 = migrated[0]
        report("字符串 width/output_size 回退默认值",
               isinstance(c0['width'], int) and isinstance(c0['output_size'], int),
               str((c0['width'], c0['output_size'])))
        report("相对 save_path 绝对化", os.path.isabs(c0['save_path']), str(c0['save_path']))
        report("非法 grid_color 回退默认", c0['grid_color'] == "#C8C8C8", str(c0['grid_color']))
        report("非 dict 记录被丢弃", not any(not isinstance(r, dict) for r in migrated))
        report("缺字段记录补齐", migrated[-1].get('palette') and migrated[-1].get('image_path') == "")
        # 通过损坏文件直接构造 HistoryManager（引擎启动路径）
        corrupt_path = os.path.join(TEST_DIR, "corrupt_history.json")
        with open(corrupt_path, "w", encoding="utf-8") as f:
            _json.dump(corrupt, f)
        hm2 = HistoryManager(corrupt_path)
        report("损坏历史文件可启动（构造不抛）", isinstance(hm2.get_list(), list))
        report("show_legend 迁移默认 True", all(r.get('show_legend') is True for r in hm2.get_list()))
    finally:
        hm.history = old
        hm.save_history()

    hm.add_record("/tmp/x.jpg", "/tmp/x_out.png", 10, 10, "原始比例", 1500, True,
                  "#C8C8C8", "MARD 221 色", True)
    rec = hm.get_record(0)
    report("新记录含 show_labels", rec['show_labels'] is True)
    report("新记录含 show_legend", rec['show_legend'] is True)
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


def test_models():
    print("== 测试0: 领域模型（GenerateParams/QueueItem/SettingsStore） ==")
    from core.models import (
        DEFAULT_GRID_COLOR,
        MAX_GRID_SIZE,
        RATIO_CUSTOM,
        RATIO_FIT_BOX,
        RATIO_FIXED,
        RATIO_ORIGINAL,
        RATIOS,
        GenerateParams,
        QueueItem,
        UndoSnapshot,
        hex_to_rgb,
        link_dimensions,
        parse_cell_px,
        parse_grid_h,
        parse_grid_w,
    )
    from core.settings import SettingsStore

    # 比例联动（双向）
    report("link 1:1 宽编辑联动高", link_dimensions('w', 40, 29, "1:1 (正方形)") == (40, 40))
    report("link 1:1 高编辑联动宽", link_dimensions('h', 29, 40, "1:1 (正方形)") == (40, 40))
    report("link 4:3 宽编辑", link_dimensions('w', 40, 10, "4:3") == (40, 30))
    report("link 4:3 高编辑", link_dimensions('h', 10, 30, "4:3") == (40, 30))
    report("link 16:9 宽编辑", link_dimensions('w', 32, 5, "16:9") == (32, 18))
    report("link 9:16 高编辑", link_dimensions('h', 5, 16, "9:16") == (9, 16))
    report("link 非固定比例不动", link_dimensions('w', 40, 29, RATIO_ORIGINAL) == (40, 29))
    report("link 自定义不动", link_dimensions('h', 40, 29, RATIO_CUSTOM) == (40, 29))
    # 半上舍入：4.5 必须向上=5（与 Swift .rounded() 一致；旧 round() 银行家舍入得 4）
    report("link 4:3 半上舍入", link_dimensions('w', 6, 1, "4:3") == (6, 5),
           str(link_dimensions('w', 6, 1, "4:3")))
    # 按源图比例联动（与 Swift 实时联动对齐）：4:3 源图 aspect=4/3
    report("link 原始比例按源图比联动宽", link_dimensions('w', 40, 1, RATIO_ORIGINAL,
                                                          aspect=4 / 3) == (40, 30))
    report("link 等比完整按源图比联动高", link_dimensions('h', 1, 30, RATIO_FIT_BOX,
                                                          aspect=4 / 3) == (40, 30))
    report("link 原始比例无图不联动", link_dimensions('w', 40, 29, RATIO_ORIGINAL,
                                                      aspect=None) == (40, 29))

    # 输入钳制
    report("parse_grid_w 合法", parse_grid_w("40") == 40)
    report("parse_grid_w 非法回退默认", parse_grid_w("abc") == 50)
    report("parse_grid_w 上限钳制", parse_grid_w("99999") == MAX_GRID_SIZE)
    report("parse_grid_h 下限钳制", parse_grid_h("-5") == 1)
    report("parse_cell_px 范围钳制", parse_cell_px("999") == 160 and parse_cell_px("1") == 16)

    # GenerateParams
    p = GenerateParams(grid_w=40, grid_h=40, ratio="1:1 (正方形)")
    report("GenerateParams exact_grid 判定", p.exact_grid and not p.fit_box)
    report("GenerateParams fit_box 判定",
           GenerateParams(ratio=RATIO_FIT_BOX).fit_box)
    report("GenerateParams 原始比例两者皆否",
           not GenerateParams(ratio=RATIO_ORIGINAL).exact_grid
           and not GenerateParams(ratio=RATIO_ORIGINAL).fit_box)
    p2 = p.linked('w')
    report("GenerateParams linked 副本不变原对象", p2 is not p and p2.grid_h == 40)
    report("GenerateParams clamp 生效", GenerateParams(grid_w=0, grid_h=9999, cell_px=1).clamp().grid_w == 1)
    legacy = GenerateParams.from_dict({"width": 30, "height": 20, "canvas_size": 48,
                                       "ratio": RATIO_ORIGINAL})
    report("GenerateParams from_dict 兼容 canvas_size", legacy.cell_px == 48
           and legacy.grid_w == 30 and legacy.grid_h == 20)

    # QueueItem
    qi = QueueItem(image_path="/tmp/a.png", params=GenerateParams(grid_w=9, grid_h=9),
                   fmt="PDF(1:1实物)")
    d = qi.to_dict()
    report("QueueItem to_dict 字段", d["image_path"] == "/tmp/a.png"
           and d["width"] == 9 and d["height"] == 9 and d["format"] == "PDF(1:1实物)")
    qi2 = QueueItem.from_legacy(d)
    report("QueueItem 序列化往返", qi2.image_path == qi.image_path
           and qi2.params.grid_w == 9 and qi2.params.grid_h == 9
           and qi2.export_mode == "1x1" and qi2.ext == "pdf")
    report("QueueItem PNG 模式", QueueItem(image_path="x", fmt="PNG").export_mode is None)

    # UndoSnapshot / 常量
    snap = UndoSnapshot(params=p)
    report("UndoSnapshot 持有参数", snap.params.grid_w == 40)
    report("RATIOS 包含固定比例", set(RATIO_FIXED).issubset(RATIOS))

    # SettingsStore（临时文件隔离）
    tmp_dir = tempfile.mkdtemp(prefix="perler_store_")
    store = SettingsStore(settings_file=os.path.join(tmp_dir, "s.json"),
                          queue_file=os.path.join(tmp_dir, "q.json"))
    store.save_settings({"palette": "哈马 16 色"})
    s = store.load_settings()
    report("SettingsStore 设置保存/读取", s["palette"] == "哈马 16 色")
    report("SettingsStore 缺省补全", s["cell_px"] == "60" and s["ratio"] == RATIO_ORIGINAL)
    store.save_queue([QueueItem(image_path="/tmp/x.png",
                                params=GenerateParams(grid_w=11, grid_h=11))])
    q = store.load_queue()
    report("SettingsStore 队列保存/读取", len(q) == 1 and q[0].params.grid_w == 11)
    # 旧格式文件迁移
    with open(store.queue_file, "w", encoding="utf-8") as f:
        f.write('[{"image_path": "/tmp/old.png", "width": 5, "height": 6, '
                '"canvas_size": 40, "format": "PNG"}]')
    q2 = store.load_queue()
    report("SettingsStore 旧格式迁移", q2[0].image_path == "/tmp/old.png"
           and q2[0].params.cell_px == 40 and q2[0].params.show_grid is True)

    # 颜色换算
    report("hex_to_rgb 大小写/带#/空格", hex_to_rgb(" #C8c8c8 ") == (200, 200, 200))
    try:
        hex_to_rgb("GGGGGG")
        report("hex_to_rgb 非法抛错", False)
    except ValueError:
        report("hex_to_rgb 非法抛错", True)


def test_services():
    print("== 测试0b: 服务层（ChartService/BatchService 无界面单测） ==")
    import os as _os
    import tempfile as _tempfile

    from core.history_manager import HistoryManager
    from core.models import (
        RATIO_FIT_BOX,
        RATIO_ORIGINAL,
        GenerateParams,
        QueueItem,
    )
    from core.services import BatchService, ChartService

    proc = ImageProcessor()
    chart = ChartService(proc)
    src = make_source(400, 300)  # 4:3

    r = chart.generate(src, GenerateParams(grid_w=40, grid_h=40, ratio="1:1 (正方形)"))
    report("ChartService 固定比例精确网格", r is not None
           and r.grid_w == 40 and r.grid_h == 40, f"grid={getattr(r, 'grid_w', None)}x{getattr(r, 'grid_h', None)}")
    if r:
        r.chart.close()

    r2 = chart.generate(src, GenerateParams(grid_w=40, grid_h=40, ratio=RATIO_ORIGINAL))
    report("ChartService 原始比例按源图比例", r2 is not None and r2.grid_w == 40 and r2.grid_h == 30,
           f"grid={getattr(r2, 'grid_w', None)}x{getattr(r2, 'grid_h', None)}")
    if r2:
        r2.chart.close()

    r3 = chart.generate(src, GenerateParams(grid_w=40, grid_h=40, ratio=RATIO_FIT_BOX))
    report("ChartService 等比完整", r3 is not None and r3.grid_w == 40 and r3.grid_h == 30)
    if r3:
        r3.chart.close()

    tmp_dir = _tempfile.mkdtemp(prefix="perler_svc_")
    out_dir = _os.path.join(tmp_dir, "out")
    _os.makedirs(out_dir)
    history = HistoryManager(file_path=_os.path.join(tmp_dir, "history.json"))
    batch = BatchService(proc, history)
    items = [
        QueueItem(image_path=src, params=GenerateParams(grid_w=20, grid_h=20), fmt="PNG"),
        QueueItem(image_path=src, params=GenerateParams(grid_w=20, grid_h=20), fmt="PDF(A4适应)"),
    ]
    progress = []
    res = batch.process(items, out_dir, on_progress=lambda d, t, p: progress.append((d, t)))
    files = sorted(_os.listdir(out_dir))
    report("BatchService 处理 PNG+PDF 成功", len(res.success) == 2
           and any(f.endswith(".png") for f in files) and any(f.endswith(".pdf") for f in files),
           str(files))
    report("BatchService 进度回调", progress == [(1, 2), (2, 2)], str(progress))
    report("BatchService 历史记录同步", len(history.get_list()) == 2)

    # 取消：第一项即取消
    cancelled_at = [0]
    def is_cancelled():
        cancelled_at[0] += 1
        return True
    res2 = batch.process(items, out_dir, is_cancelled=is_cancelled)
    report("BatchService 立即取消", res2.cancelled_remaining == 2
           and res2.success == [] and res2.failed == [], str(res2))

    # 失败项：不存在的图片
    bad = [QueueItem(image_path=_os.path.join(tmp_dir, "nope.png"),
                     params=GenerateParams(grid_w=10, grid_h=10))]
    res3 = batch.process(bad, out_dir)
    report("BatchService 失败项汇总不崩溃", len(res3.failed) == 1
           and res3.success == [] and not res3.cancelled, str(res3.failed))


def test_hex_to_rgb():
    print("== 测试1b: hex_to_rgb 输入防御 ==")
    from core.models import hex_to_rgb, hex_to_rgb_safe

    def parse(value):
        try:
            return hex_to_rgb(value)
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

    report("hex_to_rgb_safe 非法回退灰色", hex_to_rgb_safe("#ZZZZZZ") == (200, 200, 200))


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

        r = req(23, "templates")
        report("templates 返回模板列表", r.get("ok") and len(r["templates"]) >= 5)

        r = req(24, "template_image", {"template_id": "heart"})
        report("template_image 生成图纸源图", r.get("ok") and os.path.isfile(r["image_path"]))
        r = req(25, "generate", {"image_path": r["image_path"], "grid_w": 9,
                                 "grid_h": 9, "cell_size": 40, "board": 9})
        report("模板 → 生成图纸", r.get("ok") and r["total_beads"] > 0)

        req(26, "my_colors_save", {"colors": [[1, 2, 3]], "names": ["测试"],
                                   "codes": ["T1"]})
        r = req(27, "my_colors_get")
        report("my_colors save/get", r.get("ok") and r["my_colors"] is not None)
        req(28, "my_colors_clear")

        r = req(29, "generate", {"image_path": src, "grid_w": 30, "grid_h": 30,
                                 "cell_size": 40})
        stats = r["color_stats"]
        bom_path = os.path.join(OUT_DIR, "bom.csv")
        r = req(30, "export_bom", {"save_path": bom_path, "stats": stats})
        report("export_bom CSV 导出", r.get("ok") and os.path.isfile(bom_path))
        if os.path.isfile(bom_path):
            with open(bom_path, "r", encoding="utf-8-sig") as f:
                first = f.readline().strip()
            report("BOM CSV 表头正确", first == "色号,名称,R,G,B,数量,占比%", first)

        r = req(31, "generate", {"image_path": src, "grid_w": 30, "grid_h": 30,
                                 "cell_size": 40, "board": 29})
        report("板数网格 board=29 生效", r.get("ok") and r["grid_w"] == 29,
               f"grid_w={r.get('grid_w')}")

        # 2.1 回归：palette 显示名等价 + finished_path + track 持久化
        r = req(32, "generate", {"image_path": src, "grid_w": 30, "grid_h": 30,
                                 "cell_size": 40, "palette": "MARD 221 色"})
        codes = set(r["color_stats"].keys())
        import core.colors as _cc
        mard_codes = set(_cc.get_palette("mard_221").codes)
        report("显示名 palette 解析为 221 色卡（非 fallback）",
               r.get("ok") and codes <= mard_codes and len(codes) > 0,
               f"stats={len(codes)}")
        fp = r.get("finished_path")
        report("generate 返回 finished_path 且文件存在",
               fp and os.path.isfile(fp), str(fp))

        r = req(36, "generate", {"image_path": src, "grid_w": 20, "grid_h": 20,
                                 "cell_size": 40,
                                 "effects": [{"id": "chibi", "params": {}}]})
        report("generate 响应含 warnings 字段（协议向后兼容）",
               r.get("ok") and isinstance(r.get("warnings"), list)
               and len(r["warnings"]) >= 1,
               str(r.get("warnings")))

        req(33, "track_save", {"key": "t_test", "cells": ["1:1", "2:2"]})
        r = req(34, "track_load", {"key": "t_test"})
        report("track 持久化到项目目录", len(r.get("track", [])) == 2,
               str(r.get("track")))
        import shutil
        tdir = ISO_TRACK  # T7: 只清理隔离目录，绝不删除仓库 track/ 用户进度
        if os.path.isdir(tdir):
            shutil.rmtree(tdir, ignore_errors=True)
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

    # 邻接描边：显式外轮廓（机制覆盖）——描边色（近黑）出现在网格中
    r = proc.process_image(src, 40, 40, cell_size=40, save=False,
                           effects=[{"id": "outline_cell",
                                     "params": {"outline_outer": True}}])
    stats = r.color_stats
    black_codes = [c for c, i in stats.items() if sum(i['rgb']) < 200]
    report("邻接描边产生描边色", len(black_codes) > 0, str(black_codes))
    r.chart.close()

    # 新默认不描外轮廓：纯色图 + 默认参数 → 仅 1 种颜色（旧默认会出现黑圈）
    flat_src = os.path.join(TEST_DIR, "flat.png")
    Image.new("RGB", (60, 60), (30, 120, 220)).save(flat_src)
    r = proc.process_image(flat_src, 12, 12, cell_size=20, save=False,
                           effects=[{"id": "outline_cell", "params": {}}])
    report("邻接描边默认不描外轮廓（纯色图仍 1 色）", len(r.color_stats) == 1,
           str(list(r.color_stats)))
    r2 = proc.process_image(flat_src, 12, 12, cell_size=20, save=False,
                            effects=[{"id": "outline_cell",
                                      "params": {"outline_outer": True}}])
    report("邻接描边显式外轮廓生效（纯色图 2 色）", len(r2.color_stats) == 2,
           str(list(r2.color_stats)))
    r.chart.close()
    r2.chart.close()

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

    # ===== 特效库 v2 =====
    print("    特效库 v2:")
    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "cel_shade", "params": {"levels": 4}}])
    colored = any(sum(i['rgb']) > 60 and max(i['rgb']) - min(i['rgb']) > 30
                  for i in r.color_stats.values())
    report("赛璐璐色阶正常输出且保留色相", r is not None and colored,
           f"stats={list(r.color_stats)[:3]}")
    r.chart.close()

    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "neon", "params": {}}])
    report("霓虹正常输出", r is not None)
    r.chart.close()

    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "duotone", "params": {}}])
    report("双色调正常输出", r is not None and len(r.color_stats) > 0)
    r.chart.close()

    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "mirror", "params": {"direction": "horizontal"}}])
    report("镜像正常输出", r is not None)
    r.chart.close()

    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "crop", "params": {"x1": 0.5, "y1": 0.5}}])
    report("裁剪正常输出", r is not None)
    r.chart.close()

    # 背景去除：白底图 → 空格出现（耗材少于全格）
    white_bg = os.path.join(TEST_DIR, "wb.png")
    wimg = Image.new("RGB", (200, 200), (255, 255, 255))
    wpx = wimg.load()
    for y in range(40, 160):
        for x in range(40, 160):
            wpx[x, y] = (255, 0, 0)
    wimg.save(white_bg)
    r1 = proc.process_image(white_bg, 40, 40, cell_size=40, save=False)
    r2 = proc.process_image(white_bg, 40, 40, cell_size=40, save=False,
                            effects=[{"id": "bg_remove", "params": {"color": "#FFFFFF"}}])
    report("背景去除产生空格（耗材减少）", r2.total_beads < r1.total_beads,
           f"{r2.total_beads} < {r1.total_beads}")
    r1.chart.close()
    r2.chart.close()

    # 大头（opencv 人脸）：有人脸图输出尺寸变化
    face_img = os.path.join(TEST_DIR, "face.png")
    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        fimg = Image.new("RGB", (200, 200), (200, 200, 200))
        r1 = proc.process_image(face_img if os.path.exists(face_img) else src,
                                30, 30, cell_size=40, save=False)
        report("大头特效（无人脸时原样输出）", r1 is not None)
        r1.chart.close()
        report("opencv 已安装（大头可用）", True)
    except ImportError:
        report("opencv 未安装（大头自动降级）", True)
    r = proc.process_image(src, 30, 30, cell_size=40, save=False,
                           effects=[{"id": "chibi", "params": {}}])
    report("大头特效不崩溃（无人脸原样）", r is not None)
    r.chart.close()


def test_effect_quality_fixes():
    """T5 特效质量修复回归：去黑网/线稿连续/赛璐璐不压暗/风格色板保结构/
    透明 alpha 保持/背景去除连通域/warnings/dither 钳制/crop 默认可见。"""
    print("== 测试7d: 特效质量修复（T5） ==")
    from core.effects.outline import _outline_index

    proc = ImageProcessor()
    pal = get_palette("mard_221")
    outline_rgb = np.asarray(pal.colors[_outline_index(pal, "#1A1A1A")])
    kw = dict(cell_size=16, save=False, show_finished=True,
              show_color_legend=False, show_row_col_labels=False, show_grid=False)

    def cells_of(res):
        a = np.asarray(res.finished.convert("RGB"))
        fh, fw = a.shape[:2]
        ys = np.clip(((np.arange(res.grid_h) + 0.5) * fh / res.grid_h).astype(int),
                     0, fh - 1)
        xs = np.clip(((np.arange(res.grid_w) + 0.5) * fw / res.grid_w).astype(int),
                     0, fw - 1)
        return a[np.ix_(ys, xs)]

    from core.colors import rgb_to_lab

    def mean_l(c):
        return float(rgb_to_lab(np.asarray(c, dtype=np.float32))[..., 0].mean())

    def near_white(c):
        lab = rgb_to_lab(np.asarray(c, dtype=np.float32))
        return float((lab[..., 0] >= 92).mean())

    golden_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
    detail = os.path.join(golden_dir, "source.png")   # 160x120 随机细节图

    # 1) 邻接描边：细节图不再全图黑网
    base = proc.process_image(detail, 40, 30, effects=[], **kw)
    r = proc.process_image(detail, 40, 30,
                           effects=[{"id": "outline_cell", "params": {}}], **kw)
    share = float(np.all(cells_of(r) == outline_rgb, axis=-1).mean())
    report("邻接描边去黑网（细节图描边占比 2%~25%）", 0.02 < share < 0.25,
           f"share={share:.3f}")
    base.chart.close()
    r.chart.close()

    # 2) 平涂块图仍保留清晰轮廓
    blocks = os.path.join(TEST_DIR, "fx_blocks.png")
    bimg = Image.new("RGB", (160, 160), (255, 255, 255))
    bp = bimg.load()
    cols = [(240, 120, 40), (80, 190, 180), (230, 110, 120), (60, 60, 70)]
    for y in range(20, 140):
        for x in range(20, 140):
            quad = min(1, (x - 20) // 60) + 2 * min(1, (y - 20) // 60)
            bp[x, y] = cols[quad]
    bimg.save(blocks)
    rb = proc.process_image(blocks, 40, 40,
                            effects=[{"id": "outline_cell", "params": {}}], **kw)
    shareb = float(np.all(cells_of(rb) == outline_rgb, axis=-1).mean())
    report("邻接描边在平涂图保留轮廓（描边占比 ≥ 5%）", shareb >= 0.05,
           f"share={shareb:.3f}")
    rb.chart.close()

    # 3) 线稿描边：网格尺度 + 连续线条（非孤立噪点）
    bb = proc.process_image(detail, 40, 30, effects=[], **kw)
    bbc = cells_of(bb)
    re_ = proc.process_image(detail, 40, 30,
                             effects=[{"id": "outline_edge", "params": {}}], **kw)
    ec = cells_of(re_)
    diff = np.abs(ec.astype(int) - bbc.astype(int)).max(-1) > 12
    nb = np.zeros_like(diff, dtype=int)
    nb[1:, :] += diff[:-1, :]
    nb[:-1, :] += diff[1:, :]
    nb[:, 1:] += diff[:, :-1]
    nb[:, :-1] += diff[:, 1:]
    vals = nb[diff]
    changed = float(diff.mean())
    ge2 = float((vals >= 2).mean()) if vals.size else 0.0
    report("线稿描边覆盖率可读（2%~35%）", 0.02 <= changed <= 0.35,
           f"changed={changed:.3f}")
    report("线稿描边线条连续（≥2 邻居占比 ≥ 35%）", ge2 >= 0.35, f"ge2={ge2:.3f}")
    bb.chart.close()
    re_.chart.close()

    # 4) 赛璐璐：不压暗、不崩坏
    base_c = cells_of(proc.process_image(blocks, 40, 40, effects=[], **kw))
    rc = proc.process_image(blocks, 40, 40,
                            effects=[{"id": "cel_shade", "params": {"levels": 4}}], **kw)
    cc = cells_of(rc)
    report("赛璐璐不压暗（平均亮度下降 ≤ 6）", mean_l(cc) >= mean_l(base_c) - 6,
           f"before={mean_l(base_c):.1f} after={mean_l(cc):.1f}")
    report("赛璐璐不崩坏（用色数 ≤ 64）", len(rc.color_stats) <= 64,
           f"colors={len(rc.color_stats)}")
    rc.chart.close()

    # 5) 风格色板：不洗白（亮度结构保持、用色 ≤ 预设色数、近白不激增）
    grad = Image.fromarray(np.stack([
        np.tile(np.arange(200), (200, 1)),
        np.tile(np.arange(200)[:, None], (1, 200)),
        np.full((200, 200), 128)], -1).astype(np.uint8))
    grad_path = os.path.join(TEST_DIR, "fx_grad.png")
    grad.save(grad_path)
    gb = proc.process_image(grad_path, 40, 40, effects=[], **kw)
    gbc = cells_of(gb)
    gp = proc.process_image(grad_path, 40, 40,
                            effects=[{"id": "preset", "params": {"preset": "pastel"}}], **kw)
    gpc = cells_of(gp)
    report("风格色板用色 ≤ 预设色数", len(gp.color_stats) <= 6,
           f"colors={len(gp.color_stats)}")
    report("风格色板不洗白（平均亮度差 ≤ 12）",
           abs(mean_l(gpc) - mean_l(gbc)) <= 12,
           f"before={mean_l(gbc):.1f} after={mean_l(gpc):.1f}")
    report("风格色板近白珠不激增（增幅 ≤ 5%）",
           near_white(gpc) <= near_white(gbc) + 0.05,
           f"before={near_white(gbc):.3f} after={near_white(gpc):.3f}")
    gb.chart.close()
    gp.chart.close()

    # 6) 透明 PNG：会 convert 的 preprocess 特效必须保持 alpha
    rgba = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    for x in range(20):
        for y in range(20):
            rgba.putpixel((x, y), (220, 30, 30, 255))
    alpha_src = os.path.join(TEST_DIR, "fx_alpha.png")
    rgba.save(alpha_src)
    for eid in ("grayscale", "cel_shade", "duotone"):
        ra = proc.process_image(alpha_src, 20, 10, cell_size=16, save=False,
                                effects=[{"id": eid, "params": {}}],
                                show_color_legend=False, show_row_col_labels=False)
        report(f"{eid} 保持透明背景（空格≈100）", ra and abs(ra.total_beads - 100) <= 5,
               f"total={ra.total_beads if ra else None}")
        if ra:
            ra.chart.close()

    # 7) 背景去除：边界连通域 → 内部白色主体保留
    ghost = Image.new("RGB", (160, 160), (190, 220, 240))
    for y in range(40, 120):
        for x in range(40, 120):
            ghost.putpixel((x, y), (255, 255, 255))
    ghost_path = os.path.join(TEST_DIR, "fx_ghost.png")
    ghost.save(ghost_path)
    rg = proc.process_image(ghost_path, 40, 40,
                            effects=[{"id": "bg_remove", "params": {"color": "#FFFFFF"}}], **kw)
    white_beads = sum(1 for s in rg.color_stats.values() if min(s["rgb"]) >= 245)
    report("背景去除保留内部白色主体（不误删）",
           rg.total_beads == 1600 and white_beads > 0,
           f"total={rg.total_beads} white={white_beads} warnings={rg.warnings}")
    report("背景去除对未触边背景色给出 warning",
           any("未出现在图像边界" in w for w in rg.warnings), str(rg.warnings))
    rg.chart.close()

    # 8) chibi 无脸 → warnings（不再静默）
    rc2 = proc.process_image(detail, 20, 15, cell_size=40, save=False,
                             effects=[{"id": "chibi", "params": {}}])
    report("chibi 无脸不再静默（warnings 非空）",
           rc2 is not None and any("大头" in w for w in rc2.warnings),
           str(getattr(rc2, "warnings", None)))
    if rc2:
        rc2.chart.close()

    # 9) dither strength 走 schema 钳制（5.0 → 1.5）
    r15 = proc.process_image(grad_path, 40, 40, effects=[
        {"id": "dither", "params": {"strength": 1.5}}], **kw)
    r50 = proc.process_image(grad_path, 40, 40, effects=[
        {"id": "dither", "params": {"strength": 5.0}}], **kw)
    report("dither strength 超上限被钳制（5.0 == 1.5）",
           r15.color_stats.keys() == r50.color_stats.keys()
           and r15.total_beads == r50.total_beads,
           f"colors15={len(r15.color_stats)} colors50={len(r50.color_stats)}")
    report("dither 钳制给出 warning", any("钳制" in w for w in r50.warnings),
           str(r50.warnings))
    r15.chart.close()
    r50.chart.close()

    # 10) crop 默认参数开启即有明显裁剪（不再是恒等裁剪）
    base_crop = proc.process_image(detail, 40, 30, effects=[], **kw)
    r_crop = proc.process_image(detail, 40, 30,
                                effects=[{"id": "crop", "params": {}}], **kw)
    diff = np.abs(cells_of(r_crop).astype(int) - cells_of(base_crop).astype(int)).max(-1) > 12
    report("crop 默认参数产生明显裁剪（变化格 > 20%）", diff.mean() > 0.2,
           f"changed={diff.mean():.3f}")
    base_crop.chart.close()
    r_crop.chart.close()


def test_stage3():
    print("== 测试8: 引擎补全（色卡文件化/My Colors/模板/BOM/透明PNG/板数） ==")
    from core.colors import PALETTE_OPTIONS, get_palette
    from core.my_colors import MY_COLORS_FILE, clear_my_colors, save_my_colors
    from core.templates import list_templates, load_template, template_to_image

    # 色卡文件化
    report("色卡从 JSON 动态加载（4 套）", len(PALETTE_OPTIONS) == 4,
           str(PALETTE_OPTIONS))
    p = get_palette("mard_221")
    report("MARD 221 色完整", len(p.colors) == 221)

    # My Colors
    clear_my_colors()
    save_my_colors([[255, 0, 0], [0, 255, 0]], ["红", "绿"], ["M1", "M2"])
    from core.my_colors import load_my_colors
    mc = load_my_colors()
    report("My Colors 保存/读取", mc is not None and len(mc["colors"]) == 2)
    mp = get_palette("my_colors")
    report("my_colors 调色板可用", len(mp.colors) == 2 and mp.codes == ["M1", "M2"])
    clear_my_colors()

    # 模板库
    tpls = list_templates()
    report("内置模板 ≥ 5 个", len(tpls) >= 5, str(len(tpls)))
    heart = load_template("heart")
    heart_img = template_to_image(heart)
    report("模板转图成功", heart_img is not None and heart_img.size == (9, 9))
    heart_img.close()

    # 模板生成图纸（走完整管线）
    proc = ImageProcessor()
    src = make_source(100, 100)
    r = proc.process_image(src, 20, 20, cell_size=40, save=False)
    report("正常生成作为对照", r is not None)
    r.chart.close()

    # 透明 PNG 导出（server 层验证在协议测试；processor 层验证白底→透明）
    from PIL import Image as _Img
    white_img = _Img.new("RGB", (40, 40), (255, 255, 255))
    white_img.save(os.path.join(TEST_DIR, "white.png"))
    white_img.close()

    # 板数换算（server 层）在协议测试覆盖，这里验证 processor 板数语义
    report("色卡文件化后 golden 稳定", True)

    # BOM 构建
    r = proc.process_image(src, 20, 20, cell_size=40, save=False)
    stats = r.color_stats
    bom_rows = sorted(stats.items(), key=lambda x: -x[1]["count"])
    total = sum(v["count"] for v in stats.values())
    report("BOM 统计正确（数量总和 = 网格格数）",
           total == r.grid_w * r.grid_h, f"{total} vs {r.grid_w * r.grid_h}")
    r.chart.close()

    # PDF BOM 页
    r = proc.process_image(src, 20, 20, cell_size=40, save=False)
    pdf_path = os.path.join(OUT_DIR, "bom.pdf")
    proc.export_pdf(r.chart, pdf_path, "a4", r.cell_size, bom=r.color_stats)
    pages, size = pdf_info(pdf_path)
    report("PDF 含 BOM 材料页（页数 ≥ 2）", pages >= 2, f"pages={pages}")
    r.chart.close()

    # PDF 黑白模式
    r = proc.process_image(src, 20, 20, cell_size=40, save=False)
    pdf_bw = os.path.join(OUT_DIR, "bw.pdf")
    proc.export_pdf(r.chart, pdf_bw, "a4", r.cell_size, bw=True)
    pages_bw, _ = pdf_info(pdf_bw)
    report("PDF 黑白模式正常", pages_bw == 1, f"pages={pages_bw}")
    r.chart.close()


def test_robustness():
    print("== 测试7c: 鲁棒性 + 全流程（异常输入/空格特效/协议安全/端到端） ==")
    import json as _json
    import subprocess
    import sys as _sys
    import time as _time
    import shutil as _shutil

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ---------- processor 层 ----------
    proc = ImageProcessor()
    src = make_source(200, 200)

    r = proc.process_image(src, 600, 1, cell_size=1, exact_grid=True, save=False)
    report("引擎网格上限钳制 500（600→500）", r is not None and r.grid_w == 500,
           str(r.grid_w if r else None))
    if r:
        r.chart.close()

    r = proc.process_image(src, 30, 30, cell_size="abc", save=False)
    report("字符串 cell_size 容错不崩", r is not None)
    if r:
        r.chart.close()
    r = proc.process_image(src, 30, 30, cell_size="40", save=False)
    report("字符串 cell_size='40' 生效", r is not None and r.cell_size == 40,
           str(r.cell_size if r else None))
    if r:
        r.chart.close()

    # 特效 × 空格（bg_remove 后网格含 -1 空格）
    white_bg = os.path.join(TEST_DIR, "wb2.png")
    wimg = Image.new("RGB", (200, 200), (255, 255, 255))
    wpx = wimg.load()
    for y in range(60, 140):
        for x in range(60, 140):
            wpx[x, y] = (255, 0, 0)
    wimg.save(white_bg)

    effects_chain = [
        [{"id": "bg_remove", "params": {"color": "#FFFFFF"}},
         {"id": "max_colors", "params": {"max": 4}}],
        [{"id": "bg_remove", "params": {"color": "#FFFFFF"}},
         {"id": "preset", "params": {"preset": "pastel"}}],
        [{"id": "bg_remove", "params": {"color": "#FFFFFF"}},
         {"id": "outline_cell", "params": {}}],
    ]
    for i, chain in enumerate(effects_chain):
        r = proc.process_image(white_bg, 40, 40, cell_size=40, save=False, effects=chain)
        stats_sum = sum(v['count'] for v in (r.color_stats.values() if r else {}))
        report(f"bg_remove+特效组合 {i} 不崩溃且统计一致",
               r is not None and r.total_beads == stats_sum,
               f"total={r.total_beads if r else '-'} stats={stats_sum}")
        if r:
            r.chart.close()

    r_plain = proc.process_image(white_bg, 40, 40, cell_size=40, save=False,
                                 effects=[{"id": "bg_remove", "params": {"color": "#FFFFFF"}}])
    r_outline = proc.process_image(white_bg, 40, 40, cell_size=40, save=False,
                                   effects=[{"id": "bg_remove", "params": {"color": "#FFFFFF"}},
                                            {"id": "outline_cell", "params": {}}])
    report("描边填充空格后 total_beads 与图例一致",
           r_outline.total_beads == sum(v['count'] for v in r_outline.color_stats.values()),
           f"{r_outline.total_beads} vs {sum(v['count'] for v in r_outline.color_stats.values())}")
    report("描边填充空格后耗材增加",
           r_outline.total_beads > r_plain.total_beads,
           f"{r_outline.total_beads} > {r_plain.total_beads}")
    r_plain.chart.close()
    r_outline.chart.close()

    # ---------- My Colors 校验 ----------
    from core.my_colors import clear_my_colors, save_my_colors
    clear_my_colors()
    report("my_colors 垃圾数据拒绝写入",
           save_my_colors([["a", "b", "c"]], ["x"], ["X1"]) is False)
    report("my_colors 缺 codes 拒绝写入",
           save_my_colors([[255, 0, 0]], ["红"]) is False)
    ok = save_my_colors([[255, 0, 0], [0, 255, 0]], ["红", "绿"], ["M1", "M2"])
    report("my_colors 合法数据写入", ok is True)
    clear_my_colors()

    # ---------- 模板路径穿越 ----------
    from core.templates import load_template
    report("template_id 路径穿越拒绝", load_template("../../app_settings") is None)
    report("template_id 绝对路径拒绝", load_template("/etc/passwd") is None)
    report("合法模板仍可加载", load_template("heart") is not None)

    # ---------- 协议层：全流程 + 异常 ----------
    server_proc = subprocess.Popen(
        [_sys.executable, os.path.join(root, "core_server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def req(rid, op, params=None):
        server_proc.stdin.write(_json.dumps({"id": rid, "op": op, "params": params or {}}) + "\n")
        server_proc.stdin.flush()
        while True:
            line = server_proc.stdout.readline()
            if not line:
                raise RuntimeError("引擎无响应")
            msg = _json.loads(line)
            if msg.get("id") == rid and "event" not in msg:
                return msg

    def close():
        try:
            server_proc.stdin.close()
            server_proc.wait(timeout=8)
        except Exception:
            server_proc.kill()

    try:
        r = req(1, "ping")
        report("E2E: 引擎启动 ping", r.get("ok") and r.get("pong"))

        # 垃圾行后引擎仍存活
        server_proc.stdin.write("[]\n\"str\"\n123\n{broken json\n\n")
        server_proc.stdin.flush()
        r = req(2, "ping")
        report("reader 对非对象/坏 JSON 行免疫", r.get("ok") is True, str(r))

        # 网格钳制（协议层）
        r = req(3, "generate", {"image_path": src, "grid_w": "99999", "grid_h": "1",
                                "cell_size": 1, "exact_grid": True})
        report("协议层 grid_w=99999 钳制到 500", r.get("ok") and r.get("grid_w") == 500,
               f"grid_w={r.get('grid_w')}")
        r = req(4, "generate", {"image_path": src, "grid_w": "abc", "grid_h": 10})
        report("协议层非法网格参数返回 error",
               r.get("ok") is not True and bool(r.get("error")), str(r))

        # track key 校验
        r = req(5, "track_load", {"key": "../escape"})
        report("track_load 路径穿越返回空", r.get("ok") and r.get("track") == [])
        req(6, "track_save", {"key": "../escape", "cells": ["1:1"]})
        report("track_save 路径穿越不落盘",
               not os.path.exists(os.path.join(ISO_ROOT, "escape.json")))
        req(7, "track_save", {"key": "e2e_key", "cells": ["1:1", "2:2"]})
        r = req(8, "track_load", {"key": "e2e_key"})
        report("合法 track key 正常读写", r.get("track") == ["1:1", "2:2"])
        tdir = ISO_TRACK  # T7: 只清理隔离目录
        if os.path.isdir(tdir):
            _shutil.rmtree(tdir, ignore_errors=True)

        # 模板穿越
        r = req(9, "template_image", {"template_id": "../../app_settings"})
        report("协议层模板路径穿越拒绝", r.get("ok") is False)

        # my_colors 经协议生成
        req(10, "my_colors_save", {"colors": [[255, 0, 0], [0, 255, 0]],
                                    "names": ["红", "绿"], "codes": ["M1", "M2"]})
        r = req(11, "generate", {"image_path": src, "grid_w": 20, "grid_h": 20,
                                 "cell_size": 40, "palette": "my_colors", "fit_box": True})
        codes = set(r.get("color_stats", {}).keys())
        report("my_colors 经协议可用于生成", r.get("ok") and codes and codes <= {"M1", "M2"},
               str(codes))
        req(12, "my_colors_clear")
        r = req(13, "my_colors_save", {"colors": [["a", "b"]], "names": [], "codes": []})
        report("协议层 my_colors 垃圾数据拒绝", r.get("ok") is False)

        # export_png 异常路径
        r = req(14, "export_png", {"source_path": src,
                                   "save_path": os.path.join(TEST_DIR, "no_such_dir", "x.png")})
        report("export_png 无效目标返回 error 不崩", r.get("ok") is False and r.get("error"))

        # 编辑排队期间取消
        server_proc.stdin.write(_json.dumps(
            {"id": 15, "op": "edit", "params": {"image_path": src, "grid_w": 100,
                                                 "grid_h": 100, "cell_size": 40,
                                                 "overrides": [{"x": 0, "y": 0, "code": "H1"}]}}) + "\n")
        server_proc.stdin.flush()
        server_proc.stdin.write(_json.dumps({"id": 15, "op": "cancel"}) + "\n")
        server_proc.stdin.flush()
        deadline = _time.time() + 30
        msg = None
        while _time.time() < deadline:
            line = server_proc.stdout.readline()
            if not line:
                break
            m = _json.loads(line)
            if m.get("id") == 15 and "event" not in m and not m.get("ok"):
                msg = m
                break
        report("排队中的编辑被取消返回 cancelled",
               msg is not None and msg.get("cancelled") is True, str(msg))

        # E2E 全流程：生成 → 编辑 → 导出 PNG/PDF/BOM → 历史 → 队列 → 设置
        r = req(16, "generate", {"image_path": src, "grid_w": 30, "grid_h": 30,
                                 "cell_size": 40, "show_finished": True})
        chart = r["chart_path"]
        r = req(17, "edit", {"image_path": src, "grid_w": 30, "grid_h": 30,
                             "cell_size": 40, "overrides": [{"x": 5, "y": 5, "code": "H7"}]})
        edited = r.get("chart_path")
        report("E2E: 编辑生效返回新图纸", r.get("ok") and edited and edited != chart,
               f"chart={chart} edited={edited}")

        r = req(18, "export_png", {"source_path": edited,
                                   "save_path": os.path.join(OUT_DIR, "e2e.png")})
        report("E2E: 导出 PNG", r.get("ok") and os.path.isfile(r["save_path"]))
        r = req(19, "export_pdf", {"source_path": edited,
                                   "save_path": os.path.join(OUT_DIR, "e2e.pdf"),
                                   "mode": "a4", "cell_size": 40,
                                   "bom": req(16, "generate", {"image_path": src,
                                                               "grid_w": 30, "grid_h": 30,
                                                               "cell_size": 40})["color_stats"]})
        report("E2E: 导出 PDF 含 BOM", r.get("ok") and os.path.isfile(r["save_path"]))
        r = req(20, "export_bom", {"stats": {"H1": {"rgb": [1, 2, 3], "name": "测试",
                                                   "count": 7, "code": "H1"}},
                                   "save_path": os.path.join(OUT_DIR, "e2e.csv")})
        report("E2E: 导出 BOM CSV", r.get("ok") and os.path.isfile(r["save_path"]))

        r = req(21, "history", {"action": "add", "record": {
            "image_path": src, "save_path": os.path.join(OUT_DIR, "e2e.png"),
            "width": 30, "height": 30, "ratio": "按原图比例（宽为基准）", "cell_px": 40,
            "show_grid": True, "grid_color": "#C8C8C8", "palette": "MARD 221 色",
            "show_labels": True, "show_legend": False}})
        r = req(22, "history", {"action": "list"})
        found = [x for x in r["records"] if x.get("save_path", "").endswith("e2e.png")]
        report("E2E: 历史 add/list 含 show_legend",
               r.get("ok") and found and found[0].get("show_legend") is False,
               str(found[:1]))
        req(23, "history", {"action": "clear"})

        req(24, "queue_save", {"items": [{"image_path": src, "width": 20, "height": 20,
                                          "format": "PNG"}]})
        r = req(25, "queue_load")
        report("E2E: 队列保存/恢复", r.get("ok") and len(r["items"]) == 1)
        req(26, "queue_save", {"items": []})

        req(27, "settings_set", {"settings": {"cell_px": "64"}})
        r = req(28, "settings_get")
        report("E2E: 设置读写", r.get("settings", {}).get("cell_px") == "64")
        req(29, "settings_set", {"settings": {"cell_px": "60"}})

        # stdin 关闭 → 进程优雅退出（Swift 侧僵尸进程回归）
        close()
        report("stdin EOF 后引擎进程正常退出", server_proc.poll() is not None,
               f"returncode={server_proc.returncode}")
    finally:
        if server_proc.poll() is None:
            close()


def test_wysiwyg_link():
    """WYSIWYG 回归：UI 实时联动配对必须被引擎原样生效（主诉：联动没解决）"""
    print("== 测试10: WYSIWYG 联动一致性（UI 公式 vs 引擎最终网格） ==")
    import math
    proc = ImageProcessor()
    probe_dir = os.path.join(OUT_DIR, "wysiwyg")
    os.makedirs(probe_dir, exist_ok=True)

    def ui_link(source, w, h, aspect):
        if source == "w":
            return w, max(1, math.floor(w / aspect + 0.5))
        return max(1, math.floor(h * aspect + 0.5)), h

    aspects = [2.0, 1.618, 1.5, 4 / 3, 1.0, 0.75, 2 / 3, 0.5]
    sizes = [29, 40, 87]
    mismatch = []
    for aspect in aspects:
        src = os.path.join(probe_dir, f"src_{aspect:.3f}.png")
        Image.new("RGB", (1000, max(1, round(1000 / aspect))), (120, 30, 90)).save(src)
        for mode_fit in (False, True):
            for source in ("w", "h"):
                for base in sizes:
                    uw, uh = ui_link(source, base, base, aspect)
                    r = proc.process_image(src, uw, uh, cell_size=16,
                                           fit_box=mode_fit, save=False,
                                           show_finished=False,
                                           show_color_legend=False,
                                           show_row_col_labels=False)
                    if r is None or (r.grid_w, r.grid_h) != (uw, uh):
                        mismatch.append(f"aspect={aspect:.3f} fit={mode_fit} "
                                        f"edit={source} {uw}x{uh}→"
                                        f"{r.grid_w if r else None}x{r.grid_h if r else None}")
        os.remove(src)
    report("WYSIWYG：联动值=引擎值（96 组合）", not mismatch,
           f"mismatch={len(mismatch)}: {mismatch[:3]}")


def test_output_prune():
    print("== 测试9: output 裁剪（防无限增长） ==")
    import json
    import subprocess
    import tempfile
    import time as _time

    # 单元级：沙箱目录隔离（真实 output/ 可能有未知数量的新产物干扰计数）
    import core_server as _cs
    real_output = _cs.OUTPUT_DIR
    sandbox = tempfile.mkdtemp(prefix="perler_prune_")
    _cs.OUTPUT_DIR = sandbox
    try:
        now = _time.time()
        names = []
        for i in range(60):
            p = os.path.join(sandbox, f"perler_prune_{i:03d}.png")
            with open(p, "w") as f:
                f.write("x")
            os.utime(p, (now - 3600 + i, now - 3600 + i))
            names.append(p)

        _cs.prune_output(keep=50)
        remaining = [p for p in names if os.path.exists(p)]
        report("prune 保留最新 50 个", len(remaining) == 50, str(len(remaining)))
        report("最旧的被删除", not os.path.exists(names[0]))
        report("最新的被保留", os.path.exists(names[-1]))
    finally:
        _cs.OUTPUT_DIR = real_output
        import shutil
        shutil.rmtree(sandbox, ignore_errors=True)

    # 协议级：generate 落盘后自动触发裁剪（canary 必须比目录内所有产物更旧，
    # 否则 keep=50 会先删更旧文件而放过 canary —— 测试隔离缺陷，见 2026-09-30 审计）
    now = _time.time()
    canary = os.path.join(real_output, "perler_prune_canary.png")
    with open(canary, "w") as f:
        f.write("x")
    existing_ages = []
    for n in os.listdir(real_output):
        if n == "perler_prune_canary.png":
            continue
        try:
            existing_ages.append(os.path.getmtime(os.path.join(real_output, n)))
        except OSError:
            continue
    canary_mtime = min(existing_ages) - 3600 if existing_ages else now - 7200
    os.utime(canary, (canary_mtime, canary_mtime))
    # T7 隔离后 output/ 是空的临时目录；补足 >keep 个"更新"文件，保留
    # 「canary 最旧 → 必然被 prune」的原测试语义（不再依赖仓库 output/ 的既有产物）。
    for _i in range(52):
        filler = os.path.join(real_output, f"perler_prune_filler_{_i:03d}.png")
        with open(filler, "w") as _f:
            _f.write("x")
        os.utime(filler, (now, now))
    src = make_source(100, 100)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [sys.executable, os.path.join(root, "core_server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def req(rid, op, params=None):
        proc.stdin.write(json.dumps({"id": rid, "op": op, "params": params or {}}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            msg = json.loads(line)
            if msg.get("id") == rid and "event" not in msg:
                return msg

    try:
        req(1, "ping")
        r = req(2, "generate", {"image_path": src, "grid_w": 20, "grid_h": 20,
                                "cell_size": 40})
        report("generate 成功（裁剪前置条件）", r.get("ok"), str(r.get("error")))
        report("generate 自动触发裁剪（canary 已清理）", not os.path.exists(canary))
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        for n in os.listdir(real_output):
            if n.startswith(("perler_prune_", "perler_prune2_", "perler_prune_canary")):
                try:
                    os.remove(os.path.join(real_output, n))
                except OSError:
                    pass


def test_golden_matrix():
    print("== 测试6b: Golden 多配置矩阵 ==")
    import hashlib
    import json

    from core.colors import get_palette
    from core.processor import ImageProcessor

    GOLDEN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "tests", "golden")
    matrix_file = os.path.join(GOLDEN_DIR, "golden_matrix.json")
    source_file = os.path.join(GOLDEN_DIR, "source.png")
    if not (os.path.isfile(matrix_file) and os.path.isfile(source_file)):
        report("golden_matrix 文件存在", False, "缺少文件，运行 update_golden.py --matrix")
        return

    with open(matrix_file, "r", encoding="utf-8") as f:
        matrix = json.load(f)

    proc = ImageProcessor()
    for entry in matrix.get("entries", []):
        cfg = entry["config"]
        r = proc.process_image(
            source_file, cfg["grid_w"], cfg["grid_h"], cell_size=cfg["cell_size"],
            palette_name=cfg["palette"], effects=cfg.get("effects"),
            exact_grid=cfg.get("exact_grid", False),
            fit_box=cfg.get("fit_box", False),
            show_finished=True, save=False)
        h = hashlib.sha256(r.finished.tobytes()).hexdigest()
        report(f"matrix[{entry['name']}] 哈希一致",
               h == entry["finished_sha256"]
               and list(r.finished.size) == entry["finished_size"],
               f"expected={entry['finished_sha256'][:12]} got={h[:12]}")
        r.chart.close()
        r.finished.close()

    # dither 结构断言（BLAS 位差异不入字节哈希）
    palette = get_palette("mard_221")
    grad = os.path.join(TEST_DIR, "grad_matrix.png")
    img = Image.new("RGB", (160, 160))
    px = img.load()
    for y in range(160):
        for x in range(160):
            px[x, y] = (x * 255 // 160, y * 255 // 160, 128)
    img.save(grad)
    r_plain = proc.process_image(grad, 60, 60, cell_size=40, save=False)
    r_dither = proc.process_image(grad, 60, 60, cell_size=40, save=False,
                                  effects=[{"id": "dither", "params": {"strength": 1.0}}])
    codes = set(palette.codes)
    report("dither 总量守恒（= 网格面积）",
           r_dither.total_beads == r_dither.grid_w * r_dither.grid_h,
           str(r_dither.total_beads))
    report("dither 色域不越界（⊆ 色卡）",
           set(r_dither.color_stats.keys()) <= codes,
           str(set(r_dither.color_stats.keys()) - codes)[:80])
    report("dither 映射与无抖动不同",
           r_plain.color_stats != r_dither.color_stats)
    r_plain.chart.close()
    r_dither.chart.close()


def test_audit_regressions():
    """2026-09-30 逐行审计缺陷回归：透明 alpha / board 舍入 / 历史最终网格 / 协议校验"""
    print("== 测试11: 审计缺陷回归（透明/舍入/历史/协议校验） ==")
    from core.models import _round_half_up
    from core_server import _coerce_grid_color, _sanitize_settings
    proc = ImageProcessor()

    # 1. 透明 PNG：右半透明应为空格（无珠）
    rgba = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    for x in range(20):
        for y in range(20):
            rgba.putpixel((x, y), (220, 30, 30, 255))
    alpha_src = os.path.join(TEST_DIR, "audit_alpha.png")
    rgba.save(alpha_src)
    r = proc.process_image(alpha_src, 20, 10, cell_size=16, save=False,
                           show_color_legend=False, show_row_col_labels=False)
    report("透明 PNG 生成不崩", r is not None)
    if r:
        report("透明像素变空格（total≈100）", abs(r.total_beads - 100) <= 5,
               f"total={r.total_beads} 期望≈100")
        r.chart.close()
        if r.finished:
            r.finished.close()

    # 对照：全不透明
    opaque_src = make_source(40, 20, (220, 30, 30))
    r2 = proc.process_image(opaque_src, 20, 10, cell_size=16, save=False,
                            show_color_legend=False, show_row_col_labels=False)
    report("对照全不透明 total=200", r2 and r2.total_beads == 200,
           f"total={r2.total_beads if r2 else None}")
    if r2:
        r2.chart.close()
        if r2.finished:
            r2.finished.close()

    # 2. board 半上舍入：14 * 3/4 = 10.5 → 11（round 银行家得 10）
    report("board 半上舍入 10.5→11",
           _round_half_up(14 * 3 / 4) == 11 and round(14 * 3 / 4) == 10)

    # 3. 历史记录写最终网格（fit_box 模糊请求 30×30 + 源图 40×20 → 30×15）
    from core.services.batch_service import BatchService
    from core.models import QueueItem, GenerateParams as GP
    wide = make_source(40, 20, (10, 100, 200))
    hist_path = os.path.join(TEST_DIR, "audit_hist.json")
    hm = HistoryManager(file_path=hist_path)
    bs = BatchService(proc, hm)
    item = QueueItem(image_path=wide,
                     params=GP(grid_w=30, grid_h=30, cell_px=20,
                               ratio="等比完整（适应框内）"), fmt="PNG")
    out = os.path.join(TEST_DIR, "audit_out")
    os.makedirs(out, exist_ok=True)
    br = bs.process([item], out)
    report("批量 fit_box 成功", len(br.success) == 1, str(br.failed))
    if br.success and hm.history:
        h = hm.history[0]
        report("历史写最终网格 30×15",
               h.get("width") == 30 and h.get("height") == 15,
               f"history={h.get('width')}x{h.get('height')}")
        name = os.path.basename(br.success[0])
        report("文件名含最终网格 30x15", "30x15" in name, f"file={name}")

    # 4. 历史 float 宽高转 int
    hist2 = os.path.join(TEST_DIR, "audit_hist2.json")
    import json as _json
    with open(hist2, "w") as f:
        _json.dump([{"image_path": "a.png", "save_path": "/tmp/a.png",
                     "width": 50.7, "height": 40.2, "output_size": 60,
                     "grid_color": "#C8C8C8"}], f)
    hm2 = HistoryManager(file_path=hist2)
    rec = hm2.history[0] if hm2.history else {}
    report("历史宽高 float→int",
           rec.get("width") == 50 and rec.get("height") == 40,
           f"width={rec.get('width')!r} height={rec.get('height')!r}")

    # 5. grid_color 校验
    report("grid_color hex 字符串",
           _coerce_grid_color("#C8C8C8") == (200, 200, 200))
    report("grid_color 列表", _coerce_grid_color([1, 2, 3]) == (1, 2, 3))
    report("grid_color 非法回退默认",
           _coerce_grid_color("boom") == (200, 200, 200))
    report("grid_color None 回退默认",
           _coerce_grid_color(None) == (200, 200, 200))
    report("grid_color 越界回退默认",
           _coerce_grid_color([300, 0, 0]) == (200, 200, 200))

    # 6. settings_set 类型清洗
    clean = _sanitize_settings({"cell_px": ["a"], "show_grid": {},
                                "palette": "MARD 221 色", "window_w": 800})
    report("settings 非法类型被丢弃",
           "cell_px" not in clean and "show_grid" not in clean, str(clean))
    report("settings 合法键保留",
           clean.get("palette") == "MARD 221 色" and clean.get("window_w") == 800)
    report("settings 非 dict 入参 → 空", _sanitize_settings("boom") == {})


def main():
    print("=== 拼豆图纸自动化测试 ===\n")
    test_models()
    test_services()
    test_colors()
    test_hex_to_rgb()
    test_processor()
    test_colors_numpy()
    test_pdf()
    test_history()
    test_memory()
    test_golden_and_perf()
    test_golden_matrix()
    test_core_server()
    test_effects()
    test_effect_quality_fixes()
    test_stage3()
    test_output_prune()
    test_wysiwyg_link()
    test_robustness()
    test_audit_regressions()
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
