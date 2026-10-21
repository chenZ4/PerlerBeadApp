#!/usr/bin/env python3
"""T7 设计验证探针：验证「monkeypatch 路径 + 子进程 bootstrap」确实把测试写入隔离到 temp。

不修改任何 tests/ 或产品源码；只读导入 core 模块并做隔离写入。
运行：conda run --no-capture-output -n pindou python qa/gates/probes/isolation_design_probe.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TMP = tempfile.mkdtemp(prefix="perler_iso_probe_")
OUT = os.path.join(TMP, "output")
os.makedirs(OUT, exist_ok=True)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (" " + str(detail) if not ok else ""))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_snapshot(rel):
    base = os.path.join(ROOT, rel)
    if not os.path.isdir(base):
        return {"__missing__": True}
    out = {}
    for cur, dirs, files in os.walk(base):
        for name in sorted(files):
            full = os.path.join(cur, name)
            out[os.path.relpath(full, base)] = sha(full)
    return out


def repo_snapshot():
    snap = {}
    for name in ("history.json", "queue_state.json", "app_settings.json", "my_colors.json"):
        p = os.path.join(ROOT, name)
        snap["root:" + name] = sha(p) if os.path.isfile(p) else "<missing>"
    for d in ("track", "output", "data"):
        snap["dir:" + d] = tree_snapshot(d)
    return snap


def diff(before, after):
    out = []
    for k in sorted(set(before) | set(after)):
        if before.get(k) != after.get(k):
            out.append(k)
    return out


before = repo_snapshot()
print("== 0. baseline temp:", TMP)

# ---------- 1) 进程内 monkeypatch ----------
print("== 1. 进程内路径注入（monkeypatch core 模块 + SettingsStore 默认参数） ==")
sys.path.insert(0, ROOT)
import core.processor as cp          # noqa: E402
import core.settings as cs           # noqa: E402
import core.history_manager as chm   # noqa: E402
import core.my_colors as cm          # noqa: E402

cp.OUTPUT_DIR = OUT
chm.HISTORY_FILE = os.path.join(TMP, "history.json")
chm.LEGACY_HISTORY_FILE = os.path.join(TMP, "legacy_history.json")
cm.MY_COLORS_FILE = os.path.join(TMP, "my_colors.json")
cs.SETTINGS_FILE = os.path.join(TMP, "app_settings.json")
cs.QUEUE_FILE = os.path.join(TMP, "queue_state.json")
cs.SettingsStore.__init__.__defaults__ = (cs.SETTINGS_FILE, cs.QUEUE_FILE)

from PIL import Image                       # noqa: E402
from core.processor import ImageProcessor   # noqa: E402
from core.settings import load_settings, save_settings, save_queue, load_queue  # noqa: E402
from core.history_manager import HistoryManager  # noqa: E402
from core.my_colors import save_my_colors, clear_my_colors  # noqa: E402

src = os.path.join(TMP, "src.png")
Image.new("RGB", (40, 40), (200, 30, 30)).save(src)
r = ImageProcessor().process_image(src, 10, 10, cell_size=20, save=True)
check("ImageProcessor(save=True) 落盘到 temp 输出", r.save_path.startswith(OUT), r.save_path)
check("temp 输出文件存在", os.path.isfile(r.save_path))
r.chart.close()

save_settings({"cell_px": "55", "palette": "MARD 221 色"})
check("save_settings 写 temp app_settings.json", os.path.isfile(cs.SETTINGS_FILE))
check("load_settings 读回 temp 值", load_settings().get("cell_px") == "55", load_settings().get("cell_px"))
save_queue([])
check("save_queue 写 temp queue_state.json", os.path.isfile(cs.QUEUE_FILE))
check("load_queue 读 temp 空队列", load_queue() == [])

hm = HistoryManager()
hm.add_record(src, os.path.join(TMP, "out.png"), 10, 10, "原始比例", 1500, True,
              "#C8C8C8", "MARD 221 色", True)
check("HistoryManager 写 temp history.json", os.path.isfile(chm.HISTORY_FILE))

save_my_colors([[255, 0, 0]], ["红"], ["X1"])
check("save_my_colors 写 temp my_colors.json", os.path.isfile(cm.MY_COLORS_FILE))
clear_my_colors()

# ---------- 2) 子进程 bootstrap ----------
print("== 2. 子进程隔离 bootstrap（真实 core_server.serve） ==")
bootstrap = os.path.join(TMP, "engine_bootstrap.py")
with open(bootstrap, "w", encoding="utf-8") as f:
    f.write(
        "import os, sys\n"
        "ROOT = %r\nTMP = %r\n"
        "sys.path.insert(0, ROOT)\n"
        "import core.processor as p, core.settings as s, core.history_manager as h, core.my_colors as m\n"
        "p.OUTPUT_DIR = os.path.join(TMP, 'output'); os.makedirs(p.OUTPUT_DIR, exist_ok=True)\n"
        "h.HISTORY_FILE = os.path.join(TMP, 'history.json')\n"
        "h.LEGACY_HISTORY_FILE = os.path.join(TMP, 'legacy_history.json')\n"
        "m.MY_COLORS_FILE = os.path.join(TMP, 'my_colors.json')\n"
        "s.SETTINGS_FILE = os.path.join(TMP, 'app_settings.json')\n"
        "s.QUEUE_FILE = os.path.join(TMP, 'queue_state.json')\n"
        "s.SettingsStore.__init__.__defaults__ = (s.SETTINGS_FILE, s.QUEUE_FILE)\n"
        "import core_server as cs\n"
        "cs.OUTPUT_DIR = p.OUTPUT_DIR\n"
        "cs.TRACK_DIR = os.path.join(TMP, 'track')\n"
        "cs.serve()\n"
        % (ROOT, TMP))

proc = subprocess.Popen([sys.executable, bootstrap],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def req(rid, op, params=None):
    proc.stdin.write(json.dumps({"id": rid, "op": op, "params": params or {}}) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("engine 无响应")
        msg = json.loads(line)
        if msg.get("id") == rid and "event" not in msg:
            return msg


try:
    check("bootstrap 引擎 ping", req(1, "ping").get("ok") is True)
    g = req(2, "generate", {"image_path": src, "grid_w": 10, "grid_h": 10, "cell_size": 20})
    check("bootstrap 引擎 generate ok", g.get("ok") is True, str(g.get("error")))
    check("chart_path 在 temp output", str(g.get("chart_path", "")).startswith(OUT), g.get("chart_path"))
    check("temp output 中确有产物", os.path.isdir(OUT) and len(os.listdir(OUT)) >= 1)
    req(3, "track_save", {"key": "iso_probe", "cells": ["1:1"]})
    check("track 写入 temp track/", os.path.isfile(os.path.join(TMP, "track", "iso_probe.json")))
    req(4, "settings_set", {"settings": {"cell_px": "66"}})
    check("settings_set 写 temp app_settings.json", os.path.isfile(cs.SETTINGS_FILE))
    req(5, "my_colors_save", {"colors": [[1, 2, 3]], "names": ["probe"], "codes": ["P1"]})
    check("my_colors 写入 temp", os.path.isfile(cm.MY_COLORS_FILE))
finally:
    try:
        proc.stdin.close()
        proc.wait(timeout=8)
    except Exception:
        proc.kill()

# ---------- 3) 仓库未被触碰 ----------
print("== 3. 仓库用户数据前后对照 ==")
after = repo_snapshot()
changed = diff(before, after)
check("仓库根 track/ 与用户 .json 及 data/ 无任何变化", not changed, changed)
check("仓库 output/ 无变化（本探针不写仓库 output）", before["dir:output"] == after["dir:output"])

print()
failed = [x for x in RESULTS if not x[1]]
print("结果: %d/%d PASS" % (len(RESULTS) - len(failed), len(RESULTS)))
sys.exit(1 if failed else 0)
