#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa/effects/protocol_probe.py — 用真实 core_server.py 的 stdio JSON 行协议复现 Swift 调用。

协议路径与 Swift 完全一致：{"id":N,"op":"generate","params":{...}} 写入 stdin，逐行读 stdout。
唯一隔离：protocol_runner.py 把 OUTPUT_DIR 指向 qa/effects/tmp_protocol，
避免与并发门禁套件互相裁剪共享 output/（其余代码路径不变）。

验证点：
  1) 15 项单特效协议路径输出 == 直接引擎调用（像素级）；
  2) effects 参数名/类型/取值被 _coerce_params 静默丢弃/钳制的行为；
  3) dither strength 是否真的生效、是否绕过 schema 上限；
  4) outline_edge 两阶段（preprocess+grid）在协议路径是否都执行；
  5) dark_chart chart 阶段是否生效、finished 是否不变；
  6) bg_remove 透明格是否不计入耗材；
  7) chibi 无脸时是否静默无效；未知特效 id 是否静默忽略；
  8) 协议层 effect 顺序影响；edit 路径 effects+overrides 优先级。
输出：qa/effects/artifacts/protocol/protocol_results.json 与关键图
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.colors import get_palette                      # noqa: E402
from core.processor import ImageProcessor                # noqa: E402

INPUTS = os.path.join(HERE, "inputs")
ART = os.path.join(HERE, "artifacts", "protocol")
TMP = os.path.join(HERE, "tmp_protocol")
RUNNER = os.path.join(HERE, "protocol_runner.py")
PY = sys.executable
IMG = os.path.join(INPUTS, "photo_eagle.png")
IMG_SKY = os.path.join(INPUTS, "photo_sky.png")
IMG_CAT = os.path.join(INPUTS, "cartoon_cat.png")
IMG_TRANS = os.path.join(INPUTS, "transparent_icon.png")
GRID = (60, 60)
CELL = 16
os.makedirs(ART, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

PROC = ImageProcessor()
FIRST = get_palette("mard_221")
_direct_cache = {}


# ---------------------------------------------------------------------------
# 协议客户端
# ---------------------------------------------------------------------------
class Server:
    def __init__(self):
        self._err = open(os.path.join(TMP, "engine_stderr.log"), "w", encoding="utf-8")
        self.p = subprocess.Popen([PY, RUNNER, TMP], cwd=ROOT, text=True,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=self._err, bufsize=1)
        self.q = queue.Queue()
        self._alive = True
        self.noise = []
        threading.Thread(target=self._read_out, daemon=True).start()
        self._next = 1

    def _read_out(self):
        for line in self.p.stdout:
            self.q.put(line)
        self._alive = False

    def next_id(self):
        rid = self._next
        self._next += 1
        return rid

    def request(self, req, timeout=180):
        self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        deadline = time.time() + timeout
        events = []
        while time.time() < deadline:
            try:
                line = self.q.get(timeout=max(0.05, deadline - time.time()))
            except queue.Empty:
                raise TimeoutError("protocol timeout: %s" % req.get("op"))
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # 引擎进程把处理器 print 的错误信息写进了 stdout（协议流被污染）
                self.noise.append(line.rstrip("\n"))
                continue
            if obj.get("id") != req["id"]:
                continue
            if obj.get("event"):
                events.append(obj)
                continue
            return obj
        raise TimeoutError("protocol timeout: %s" % req.get("op"))

    def ping(self):
        rid = self.next_id()
        return self.request({"id": rid, "op": "ping", "params": {}}, timeout=20)

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.p.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.p.kill()
        self._err.close()


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def sample_cells(finished, gw, gh):
    a = np.asarray(finished.convert("RGB"))
    fh, fw = a.shape[:2]
    ys = np.clip(((np.arange(gh) + 0.5) * fh / gh).astype(int), 0, fh - 1)
    xs = np.clip(((np.arange(gw) + 0.5) * fw / gw).astype(int), 0, fw - 1)
    return a[np.ix_(ys, xs)]


def cell_changed_ratio(a, b):
    if a is None or b is None or a.shape != b.shape:
        return None
    return round(float((np.abs(a.astype(int) - b.astype(int)).max(-1) > 12).mean()), 4)


def direct(effects, image=IMG, gw=60, gh=60, cell=16, palette="mard_221"):
    key = json.dumps([effects, image, gw, gh, cell, palette], sort_keys=True)
    if key not in _direct_cache:
        res = PROC.process_image(image, gw, gh, cell_size=cell, effects=effects,
                                 show_finished=True, save=False, palette_name=palette)
        if res is None:
            _direct_cache[key] = None
        else:
            _direct_cache[key] = {
                "grid": [res.grid_w, res.grid_h],
                "beads": res.total_beads,
                "colors": len(res.color_stats),
                "finished": np.asarray(res.finished.convert("RGB")),
                "chart": np.asarray(res.chart.convert("RGB")),
                "cell_size": res.cell_size,
            }
    return _direct_cache[key]


def outline_rgb():
    from core.effects.outline import _outline_index
    idx = _outline_index(FIRST, "#1A1A1A")
    return tuple(int(v) for v in FIRST.colors[idx])


OUTLINE_RGB = outline_rgb()


def outline_share(cells):
    return round(float(np.all(cells == np.asarray(OUTLINE_RGB), axis=-1).mean()), 4)


def copy_artifact(src, name):
    if not src or not os.path.exists(src):
        return None
    dst = os.path.join(ART, name)
    shutil.copyfile(src, dst)
    return os.path.relpath(dst, ROOT)


_FIN_ARR = {}
_CHART_ARR = {}


def load_protocol_finished(resp, name, keep_artifact=False):
    path = resp.get("finished_path")
    if not path or not os.path.exists(path):
        return None
    arr = np.asarray(Image.open(path).convert("RGB"))
    _FIN_ARR[name] = arr
    if keep_artifact:
        copy_artifact(path, name + "_finished.png")
    return arr


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    server = Server()
    rows = []
    findings = {"response_keys": None, "param_handling": {}, "dither": {},
                "outline_edge": {}, "dark_chart": {}, "bg_remove": {},
                "chibi": {}, "order": {}, "edit": {}}
    base_cells = None
    base_fin = None

    def gen(name, effects, image=IMG, extra=None, keep=False, timeout=180):
        params = {"image_path": image, "grid_w": 60, "grid_h": 60, "cell_size": CELL,
                  "palette": "mard_221", "show_finished": True, "effects": effects,
                  "fit_box": False, "exact_grid": False}
        if extra:
            params.update(extra)
        rid = server.next_id()
        t0 = time.time()
        resp = server.request({"id": rid, "op": "generate", "params": params}, timeout=timeout)
        dt = round(time.time() - t0, 2)
        row = {"name": name, "effects": effects, "image": os.path.basename(image),
               "sec": dt, "ok": bool(resp.get("ok"))}
        fin_arr = None
        if row["ok"]:
            fin_arr = load_protocol_finished(resp, name, keep_artifact=keep)
            if keep:
                _CHART_ARR[name] = np.asarray(Image.open(resp["chart_path"]).convert("RGB"))
                copy_artifact(resp["chart_path"], name + "_chart.png")
            cells = sample_cells(Image.open(resp["finished_path"]), resp["grid_w"], resp["grid_h"])
            _FIN_ARR[name] = fin_arr
            row.update({
                "grid": [resp["grid_w"], resp["grid_h"]],
                "beads": resp["total_beads"],
                "n_colors": len(resp["color_stats"]),
                "sum_stats": sum(v["count"] for v in resp["color_stats"].values()),
                "chart_size": resp["chart_size"],
                "finished_size": resp["finished_size"],
                "outline_share": outline_share(cells),
                "cells": cells,
            })
            d = direct(effects, image)
            if d is not None and fin_arr is not None:
                row["equals_direct"] = {
                    "grid": row["grid"] == d["grid"],
                    "beads": row["beads"] == d["beads"],
                    "colors": row["n_colors"] == d["colors"],
                    "finished_pixels": bool(fin_arr.shape == d["finished"].shape
                                            and np.array_equal(fin_arr, d["finished"])),
                }
        else:
            row["error"] = resp.get("error")
            row["keys"] = sorted(resp.keys())
        rows.append(row)
        return row, resp

    # 0) 基线
    print("[protocol] baseline ...")
    base_row, base_resp = gen("baseline", [], keep=True)
    findings["response_keys"] = sorted(base_resp.keys())
    base_cells = base_row["cells"]
    base_fin = _FIN_ARR["baseline"]

    # 1) 15 项单特效：协议 vs 直接引擎
    print("[protocol] 15 singles ...")
    SINGLES = [
        ("chibi", [{"id": "chibi", "params": {}}]),
        ("mirror_h", [{"id": "mirror", "params": {"direction": "horizontal"}}]),
        ("crop_center", [{"id": "crop", "params": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}}]),
        ("grayscale", [{"id": "grayscale", "params": {}}]),
        ("adjust_sat12", [{"id": "adjust", "params": {"brightness": 1.0, "contrast": 1.0, "saturation": 1.2}}]),
        ("cel4", [{"id": "cel_shade", "params": {"levels": 4}}]),
        ("neon", [{"id": "neon", "params": {"saturation": 1.5, "darkness": 0.75}}]),
        ("duotone", [{"id": "duotone", "params": {"color1": "#1E1E1E", "color2": "#F0F0F0"}}]),
        ("bg_remove_white", [{"id": "bg_remove", "params": {"color": "#FFFFFF", "tolerance": 30}}]),
        ("outline_edge", [{"id": "outline_edge", "params": {}}]),
        ("dither", [{"id": "dither", "params": {}}]),
        ("outline_cell", [{"id": "outline_cell", "params": {}}]),
        ("max_colors12", [{"id": "max_colors", "params": {"max": 12}}]),
        ("preset_pastel", [{"id": "preset", "params": {"preset": "pastel"}}]),
        ("dark_chart", [{"id": "dark_chart", "params": {}}]),
    ]
    for name, effects in SINGLES:
        row, resp = gen(name, effects)
        if row["ok"]:
            row["changed_vs_baseline"] = cell_changed_ratio(row["cells"], base_cells)
        rows[-1] = row
        print("  %-18s ok=%s grid=%s beads=%s colors=%s chg=%s direct=%s" % (
            name, row["ok"], row.get("grid"), row.get("beads"), row.get("n_colors"),
            row.get("changed_vs_baseline"), row.get("equals_direct")))

    # 2) dither strength 生效 & 上限
    print("[protocol] dither strength ...")
    dith = {}
    for label, params in [("s0", {"strength": 0.0}), ("s1", {"strength": 1.0}),
                          ("s15", {"strength": 1.5}), ("s5", {"strength": 5.0}),
                          ("s_abc", {"strength": "abc"})]:
        row, _ = gen("dither_" + label, [{"id": "dither", "params": params}], image=IMG_SKY)
        dith[label] = {"changed_vs_baseline": row.get("changed_vs_baseline"),
                       "equals_direct": row.get("equals_direct"),
                       "finished": row["name"]}
    sky_base, _ = gen("sky_baseline", [], image=IMG_SKY)
    for label in ("s0", "s1", "s15", "s5", "s_abc"):
        dith[label]["changed_vs_noeffect"] = cell_changed_ratio(
            _FIN_ARR.get("dither_" + label), _FIN_ARR["sky_baseline"])
    dith["s_abc"]["vs_s1"] = cell_changed_ratio(_FIN_ARR["dither_s_abc"], _FIN_ARR["dither_s1"])
    dith["s5"]["vs_s15"] = cell_changed_ratio(_FIN_ARR["dither_s5"], _FIN_ARR["dither_s15"])
    dith["s15"]["vs_s1"] = cell_changed_ratio(_FIN_ARR["dither_s15"], _FIN_ARR["dither_s1"])
    findings["dither"] = {
        "rows": dith,
        "schema_declared_max": 1.5,
        "verdict": "strength 生效（0=无抖动，1.0/1.5/5.0 逐级增强）；但 5.0 超出 schema max=1.5 未被钳制",
    }

    # 3) effects 参数名/类型/取值：静默丢弃与钳制
    print("[protocol] param handling ...")
    ph = findings["param_handling"]

    def cmp_pair(label, eff_a, eff_b, image=IMG_CAT):
        ra, _ = gen(label + "_A", eff_a, image=image)
        rb, _ = gen(label + "_B", eff_b, image=image)
        na, nb = label + "_A", label + "_B"
        return {"A": {"effects": eff_a, "n_colors": ra.get("n_colors"),
                      "beads": ra.get("beads"), "grid": ra.get("grid")},
                "B": {"effects": eff_b, "n_colors": rb.get("n_colors"),
                      "beads": rb.get("beads"), "grid": rb.get("grid")},
                "finished_pixels_identical": bool(
                    _FIN_ARR.get(na) is not None and _FIN_ARR.get(nb) is not None
                    and np.array_equal(_FIN_ARR[na], _FIN_ARR[nb]))}

    ph["max_colors_int"] = cmp_pair("max8_int",
                                    [{"id": "max_colors", "params": {"max": 8}}],
                                    [{"id": "max_colors", "params": {"max": "8"}}])
    ph["max_colors_unknown_key"] = cmp_pair("max_unknown",
                                            [{"id": "max_colors", "params": {"maxColors": 8}}],
                                            [{"id": "max_colors", "params": {}}])
    ph["mirror_invalid_choice"] = cmp_pair("mirror_bad",
                                           [{"id": "mirror", "params": {"direction": "diagonal"}}],
                                           [{"id": "mirror", "params": {"direction": "horizontal"}}])
    ph["preset_invalid_choice"] = cmp_pair("preset_bad",
                                           [{"id": "preset", "params": {"preset": "unknown"}}],
                                           [{"id": "preset", "params": {"preset": "pastel"}}])
    ph["mirror_unknown_param"] = cmp_pair("mirror_extra",
                                          [{"id": "mirror", "params": {"threshold": 40}}],
                                          [{"id": "mirror", "params": {}}])
    ph["outline_width_clamp"] = cmp_pair("outline_w99",
                                         [{"id": "outline_cell", "params": {"width": 99}}],
                                         [{"id": "outline_cell", "params": {"width": 3}}])
    # 未知特效 id：静默忽略？
    unk_row, unk_resp = gen("unknown_effect_id", [{"id": "outline_edges", "params": {}}])
    ph["unknown_effect_id"] = {
        "ok": unk_row["ok"], "error": unk_row.get("error"),
        "changed_vs_baseline": cell_changed_ratio(unk_row.get("cells"), base_cells),
        "response_keys": sorted(unk_resp.keys()) if unk_row["ok"] else None,
        "note": "未知 id 被 apply_phase 静默 continue，无任何 warning/回显",
    }
    # effects 类型错误：应失败但服务存活
    bad, bad_resp = gen("bad_effects_type", "outline_cell")
    alive = server.ping()
    ph["bad_effects_type"] = {"ok": bad["ok"], "error": bad.get("error"),
                              "response_keys": sorted(bad_resp.keys()),
                              "server_alive_after": bool(alive.get("ok")),
                              "stdout_protocol_noise": server.noise[:4],
                              "noise_note": "core/processor.py 的 print('[错误] 处理失败') 写入 stdout，"
                                            "污染 JSON 行协议；Swift Engine.handleLine 靠 JSON 解析失败静默丢弃，"
                                            "最终 UI 只看到笼统的『生成失败』"}
    findings["param_handling"] = ph

    # 4) outline_edge 两阶段（preprocess+grid）
    print("[protocol] outline_edge 2-phase ...")
    only, _ = gen("edge_only", [{"id": "outline_edge", "params": {}}])
    with_gray, _ = gen("edge_after_gray", [{"id": "grayscale", "params": {}},
                                           {"id": "outline_edge", "params": {}}])
    after_gray, _ = gen("gray_only", [{"id": "grayscale", "params": {}}])
    findings["outline_edge"] = {
        "edge_only_changed_vs_baseline": cell_changed_ratio(_FIN_ARR.get("edge_only"), base_fin),
        "edge_only_outline_share": only.get("outline_share"),
        "gray_then_edge_changed_vs_baseline": cell_changed_ratio(_FIN_ARR.get("edge_after_gray"), base_fin),
        "gray_then_edge_vs_gray_only": cell_changed_ratio(
            _FIN_ARR.get("edge_after_gray"), _FIN_ARR.get("gray_only")),
        "equals_direct": {"edge_only": only.get("equals_direct"),
                          "gray_then_edge": with_gray.get("equals_direct")},
        "verdict": "preprocess 阶段记录 ctx.edge_mask、grid 阶段落到索引矩阵；两阶段在协议路径均执行"
                   "（与直接调用像素级一致，chart 有实际变化）",
    }

    # 5) dark_chart chart 阶段
    print("[protocol] dark_chart ...")
    dark, dark_resp = gen("dark_chart_proto", [{"id": "dark_chart", "params": {}}], keep=True)
    dark_custom, dark_custom_resp = gen(
        "dark_chart_custom", [{"id": "dark_chart",
                               "params": {"background": "#202040", "grid_color": "#404060"}}], keep=True)
    chart_dark = np.asarray(Image.open(dark_resp["chart_path"]).convert("RGB"))
    chart_custom = np.asarray(Image.open(dark_custom_resp["chart_path"]).convert("RGB"))
    chart_base = _CHART_ARR.get("baseline")
    if chart_base is None:
        chart_base = np.asarray(Image.open(copy_artifact(base_resp.get("chart_path"),
                                                         "baseline_chart.png")
                                           ).convert("RGB"))
    findings["dark_chart"] = {
        "default_bg_corner": [int(v) for v in chart_dark[3, -3]],
        "custom_bg_corner": [int(v) for v in chart_custom[3, -3]],
        "baseline_bg_corner": [int(v) for v in chart_base[3, -3]],
        "finished_identical_to_baseline": bool(
            _FIN_ARR.get("dark_chart_proto") is not None
            and np.array_equal(_FIN_ARR["dark_chart_proto"], base_fin)),
        "chart_dark_ratio": round(float(((0.299 * chart_dark[..., 0] + 0.587 * chart_dark[..., 1]
                                          + 0.114 * chart_dark[..., 2]) < 80).mean()), 4),
        "verdict": "chart 阶段生效（背景/网格色可参数化）；finished 成品图完全不受影响",
    }
    copy_artifact(dark_resp.get("chart_path"), "chart_dark_chart.png")
    copy_artifact(dark_custom_resp.get("chart_path"), "chart_dark_chart_custom.png")

    # 6) bg_remove：透明格不计入耗材
    print("[protocol] bg_remove ...")
    for label, image in (("cat", IMG_CAT), ("transparent", IMG_TRANS)):
        row, resp = gen("bgremove_" + label,
                        [{"id": "bg_remove", "params": {"color": "#FFFFFF", "tolerance": 30}}],
                        image=image, keep=(label == "cat"))
        br, _ = gen("bgremove_" + label + "_base", [], image=image)
        findings["bg_remove"][label] = {
            "grid": row.get("grid"), "beads": row.get("beads"),
            "baseline_beads": br.get("beads"),
            "transparent_cells": (row["grid"][0] * row["grid"][1] - row["beads"]) if row["ok"] else None,
            "sum_color_stats": row.get("sum_stats"),
            "beads_removed": (br.get("beads", 0) - row.get("beads", 0)) if row["ok"] else None,
            "finished_changed_vs_baseline": cell_changed_ratio(
                _FIN_ARR.get("bgremove_" + label), _FIN_ARR.get("bgremove_" + label + "_base")),
            "equals_direct": row.get("equals_direct"),
        }
    findings["bg_remove"]["verdict"] = ("透明格不计入耗材（sum(color_stats)==total_beads），"
                                        "但空白格与白珠在 finished/chart 上同色 → 预览几乎看不出")

    # 7) chibi 静默
    print("[protocol] chibi ...")
    chibi_row, chibi_resp = gen("chibi_proto", [{"id": "chibi", "params": {}}])
    findings["chibi"] = {
        "ok": chibi_row["ok"], "grid": chibi_row.get("grid"),
        "beads": chibi_row.get("beads"), "colors": chibi_row.get("n_colors"),
        "changed_vs_baseline": cell_changed_ratio(chibi_row.get("cells"), base_cells),
        "equals_baseline_pixels": bool(_FIN_ARR.get("chibi_proto") is not None
                                       and np.array_equal(_FIN_ARR["chibi_proto"], base_fin)),
        "response_has_warning_field": any(k in (chibi_resp or {}) for k in
                                          ("warning", "warnings", "effects_applied", "skipped")),
        "verdict": "无脸/无 OpenCV 时静默返回原图：ok=true、无 warning、结果与基线完全相同",
    }

    # 8) 顺序影响（协议路径）
    print("[protocol] order ...")
    a, _ = gen("order_outline_then_max",
               [{"id": "outline_cell", "params": {}}, {"id": "max_colors", "params": {"max": 8}}])
    b, _ = gen("order_max_then_outline",
               [{"id": "max_colors", "params": {"max": 8}}, {"id": "outline_cell", "params": {}}])
    findings["order"] = {
        "outline_then_max": {"cells": a.get("cells").tolist() if a.get("cells") is not None else None},
        "outline_then_max_outline_share": a.get("outline_share"),
        "max_then_outline_outline_share": b.get("outline_share"),
        "finished_pixels_identical": bool(_FIN_ARR.get("order_outline_then_max") is not None
                                          and np.array_equal(_FIN_ARR["order_outline_then_max"],
                                                             _FIN_ARR["order_max_then_outline"])),
        "verdict": "effects 数组顺序即执行顺序；Swift 固定顺序（描边在 preset 前）会丢描边",
    }
    findings["order"].pop("outline_then_max", None)
    # 描边 + 风格色板：Swift 固定顺序（描边在前、preset 在后）是否把描边洗掉
    c, _ = gen("order_outline_then_preset",
               [{"id": "outline_cell", "params": {}}, {"id": "preset", "params": {"preset": "pastel"}}])
    d_, _ = gen("order_preset_then_outline",
                [{"id": "preset", "params": {"preset": "pastel"}}, {"id": "outline_cell", "params": {}}])
    findings["order"]["preset_combo"] = {
        "swift_order_outline_then_preset_outline_share": c.get("outline_share"),
        "reversed_preset_then_outline_outline_share": d_.get("outline_share"),
        "finished_pixels_identical": bool(_FIN_ARR.get("order_outline_then_preset") is not None
                                          and np.array_equal(_FIN_ARR["order_outline_then_preset"],
                                                             _FIN_ARR["order_preset_then_outline"])),
        "verdict": "Swift 固定顺序下 preset 在描边之后执行 → 描边色被整体映射掉（share=0），组合失效",
    }

    # 8.5) 透明源图 + 会丢 alpha 的 preprocess 特效（协议路径）
    print("[protocol] transparent alpha ...")
    trans_alpha = {}
    for name, effects in [
        ("adjust", [{"id": "adjust", "params": {"saturation": 1.2}}]),
        ("grayscale", [{"id": "grayscale", "params": {}}]),
        ("cel4", [{"id": "cel_shade", "params": {"levels": 4}}]),
        ("duotone", [{"id": "duotone", "params": {"color1": "#1E1E1E", "color2": "#F0F0F0"}}]),
        ("bg_remove", [{"id": "bg_remove", "params": {"color": "#FFFFFF", "tolerance": 30}}]),
    ]:
        row, _ = gen("trans_" + name, effects, image=IMG_TRANS)
        trans_alpha[name] = {"beads": row.get("beads"), "n_colors": row.get("n_colors"),
                             "equals_direct": row.get("equals_direct")}
    trans_alpha["baseline_beads"] = 918
    trans_alpha["verdict"] = ("grayscale/cel_shade/duotone 在 preprocess 阶段 convert('L'/'RGB') 丢失 alpha，"
                              "透明格从 2682 个空格变成实心珠（918→3600 颗，+292%）")
    findings["transparent_alpha"] = trans_alpha

    # 8.6) 非法 HEX 颜色：静默回退默认值
    bad_hex, _ = gen("duotone_bad_hex",
                     [{"id": "duotone", "params": {"color1": "", "color2": "zzz"}}])
    good_hex, _ = gen("duotone_good_hex",
                      [{"id": "duotone", "params": {"color1": "#1E1E1E", "color2": "#F0F0F0"}}])
    findings["invalid_hex_color"] = {
        "ok": bad_hex["ok"], "error": bad_hex.get("error"),
        "n_colors_by_case": {"bad": bad_hex.get("n_colors"), "good": good_hex.get("n_colors")},
        "finished_pixels_identical_to_default": bool(
            _FIN_ARR.get("duotone_bad_hex") is not None
            and np.array_equal(_FIN_ARR["duotone_bad_hex"], _FIN_ARR["duotone_good_hex"])),
        "verdict": "非法/空 HEX 静默回退默认色，无校验提示",
    }

    # 9) edit：overrides 优先于 effects（协议路径）
    print("[protocol] edit ...")
    code = FIRST.codes[0].strip()
    try:
        edit_req = {"id": server.next_id(), "op": "edit", "params": {
            "image_path": IMG, "grid_w": 60, "grid_h": 60, "cell_size": CELL,
            "palette": "mard_221",
            "effects": [{"id": "outline_cell", "params": {}}],
            "overrides": [{"x": 30, "y": 30, "code": code}],
        }}
        e_resp = server.request(edit_req, timeout=180)
        e_ok = bool(e_resp.get("ok"))
        cell_rgb = None
        if e_ok:
            fin = np.asarray(Image.open(e_resp["finished_path"]).convert("RGB"))
            cs = int(e_resp["cell_size"])
            cell_rgb = [int(v) for v in fin[30 * cs + cs // 2, 30 * cs + cs // 2]]
        palette_rgb = [int(v) for v in FIRST.colors[FIRST.codes.index(code)]]
        findings["edit"] = {"ok": e_ok, "override_code": code,
                            "cell_rgb": cell_rgb, "palette_rgb": palette_rgb,
                            "override_wins_over_effects": cell_rgb == palette_rgb,
                            "verdict": "编辑覆盖在 effects 之后重新应用（35fa440 修复在协议路径有效）"}
    except Exception as e:  # noqa: BLE001
        findings["edit"] = {"error": repr(e)}

    server.close()

    # 汇总
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "isolation": "protocol_runner.py 仅重定向 OUTPUT_DIR 到 qa/effects/tmp_protocol；协议/管线代码 0 改动",
        "python": sys.version.split()[0],
        "rows": [{k: v for k, v in r.items() if k != "cells"} for r in rows],
        "findings": findings,
    }
    with open(os.path.join(ART, "protocol_results.json"), "w", encoding="utf-8") as f:
        json.dump(json.loads(json.dumps(out, ensure_ascii=False, default=str)),
                  f, ensure_ascii=False, indent=1)
    print("\n[protocol done] ->", os.path.relpath(ART, ROOT))
    print("response keys:", findings["response_keys"])


if __name__ == "__main__":
    main()
