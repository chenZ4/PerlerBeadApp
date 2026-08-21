# core_server.py - 常驻引擎服务（stdio JSON 行协议）
# SwiftUI 前端通过子进程与引擎通信：
#   请求:  {"id": 1, "op": "generate", "params": {...}}
#   响应:  {"id": 1, "ok": true, ...}
#   事件:  {"id": 1, "event": "progress", "progress": 0.5}
# 取消:  {"id": 1, "op": "cancel"}（读线程即时处理，可中断进行中的生成）
import json
import os
import queue
import re
import sys
import threading
import time

import numpy as np

from core.colors import PALETTE_OPTIONS, _PALETTE_CACHE, get_palette
from core.effects import list_effects
from core.history_manager import HistoryManager
from core.models import MAX_GRID_SIZE
from core.processor import ImageProcessor, OUTPUT_DIR
from core.settings import load_queue, load_settings, save_queue, save_settings
from core.version import APP_VERSION

PROGRESS_THROTTLE = 0.02  # 每 2% 发一次进度事件

_TRACK_KEY_RE = re.compile(r"^[\w-]{1,64}$")

_DISPLAY_TO_INTERNAL = {d: i for d, i in PALETTE_OPTIONS}


def _resolve_palette(name):
    """显示名或 internal 名统一解析为 internal 名（防任何客户端传错）"""
    if name in _DISPLAY_TO_INTERNAL:
        return _DISPLAY_TO_INTERNAL[name]
    if name in {i for _, i in PALETTE_OPTIONS}:
        return name
    if name in ("my_colors", "我的颜色"):
        from core.my_colors import load_my_colors
        if load_my_colors() is not None:
            return "my_colors"
    return "mard_221"


def tempfile_dir():
    import tempfile
    return tempfile.gettempdir()


TRACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "track")

# output/ 保留的最新产物文件数（generate/edit 中间产物会无限累积，需裁剪）
MAX_OUTPUT_FILES = 50
_OUTPUT_PREFIXES = ("perler_", "finished_")


def prune_output(keep: int = MAX_OUTPUT_FILES):
    """按 mtime 只保留最新 keep 个本工具产物，防止 output/ 无限增长。

    仅清理 OUTPUT_DIR 下以 perler_/finished_ 开头的中间产物，
    用户显式导出到其他位置的文件不受影响。
    """
    try:
        entries = []
        for name in os.listdir(OUTPUT_DIR):
            if not name.startswith(_OUTPUT_PREFIXES):
                continue
            path = os.path.join(OUTPUT_DIR, name)
            try:
                entries.append((os.path.getmtime(path), path))
            except OSError:
                continue
        entries.sort(reverse=True)
        for _, path in entries[keep:]:
            try:
                os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def track_dir():
    os.makedirs(TRACK_DIR, exist_ok=True)
    return TRACK_DIR


class CoreServer:
    def __init__(self):
        self.processor = ImageProcessor()
        self.history = HistoryManager()
        self.settings = load_settings()
        self._cancelled = set()
        self._last_progress = {}
        self._out_lock = threading.Lock()

    # ---------- 分发 ----------
    @staticmethod
    def _wrap(sub):
        """error/cancelled 子结果不带 ok:True（防止客户端把错误当成功解码）"""
        if isinstance(sub, dict) and ("error" in sub or "cancelled" in sub):
            return sub
        return {"ok": True, **sub}

    def handle(self, req):
        op = req.get("op")
        rid = req.get("id")
        params = req.get("params") or {}

        if op == "ping":
            return {"ok": True, "pong": True, "version": APP_VERSION}
        if op == "cancel":
            self._cancelled.add(rid)
            return {"ok": True, "cancelled": True}
        if op == "generate":
            return self._wrap(self._generate(rid, params))
        if op == "edit":
            return self._wrap(self._edit(rid, params))
        if op == "track_load":
            return {"ok": True, "key": str(params.get("key", "")),
                    "track": self._track_load(params)}
        if op == "track_save":
            self._track_save(params)
            return {"ok": True}
        if op == "export_png":
            return {"ok": True, **self._export_png(params)}
        if op == "export_bom":
            return {"ok": True, **self._export_bom(params)}
        if op == "export_pdf":
            return {"ok": True, **self._export_pdf(params)}
        if op == "palettes":
            return {"ok": True, "palettes": [
                {"display": d, "internal": i, "count": len(get_palette(i).colors)}
                for d, i in sorted(PALETTE_OPTIONS,
                                   key=lambda x: 0 if x[1] == "mard_221" else 1)]}
        if op == "palette_colors":
            palette = get_palette(_resolve_palette(params.get("internal", "mard_221")))
            return {"ok": True, "codes": palette.codes, "names": palette.names,
                    "colors": palette.colors, "hex": palette.hex_codes}
        if op == "my_colors_get":
            from core.my_colors import load_my_colors
            data = load_my_colors()
            return {"ok": True, "my_colors": data}
        if op == "my_colors_save":
            from core.my_colors import save_my_colors
            ok = save_my_colors(params.get("colors") or [],
                                params.get("names"), params.get("codes"))
            _PALETTE_CACHE.pop("my_colors", None)
            if not ok:
                return {"ok": False, "error": "色卡数据无效"}
            return {"ok": True}
        if op == "my_colors_clear":
            from core.my_colors import clear_my_colors
            clear_my_colors()
            _PALETTE_CACHE.pop("my_colors", None)
            return {"ok": True}
        if op == "effects":
            return {"ok": True, "effects": list_effects()}
        if op == "settings_get":
            return {"ok": True, "settings": load_settings()}
        if op == "settings_set":
            self.settings.update(params.get("settings") or {})
            save_settings(self.settings)
            return {"ok": True}
        if op == "history":
            return {"ok": True, **self._history(params)}
        if op == "queue_load":
            return {"ok": True, "items": load_queue()}
        if op == "queue_save":
            save_queue(params.get("items") or [])
            return {"ok": True}
        if op == "templates":
            from core.templates import list_templates
            return {"ok": True, "templates": list_templates()}
        if op == "template_image":
            from core.templates import load_template, template_to_image
            tid = params.get("template_id", "")
            tpl = load_template(tid)
            if tpl is None:
                return {"ok": False, "error": "模板不存在"}
            img = template_to_image(tpl)
            if img is None:
                return {"ok": False, "error": "模板数据无效"}
            path = os.path.join(tempfile_dir(), f"tpl_{tid}.png")
            img_w, img_h = img.width, img.height
            try:
                img.save(path)
            finally:
                img.close()
            return {"ok": True, "image_path": path, "width": img_w,
                    "height": img_h}
        raise ValueError(f"未知操作: {op}")

    # ---------- 生成 ----------
    def _emit_progress(self, rid, y, total):
        if total <= 0:
            return
        p = y / total
        if p - self._last_progress.get(rid, 0) >= PROGRESS_THROTTLE or y == total - 1:
            self._last_progress[rid] = p
            self._emit({"id": rid, "event": "progress", "progress": round(p, 3)})

    def _emit(self, msg):
        try:
            line = json.dumps(msg, ensure_ascii=False)
        except TypeError:
            line = json.dumps({"id": msg.get("id"), "ok": False,
                               "error": "响应包含不可序列化对象"})
        with self._out_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _cancel_check(self, rid):
        return rid in self._cancelled

    def _generate(self, rid, params):
        # 取消可能在请求排队期间到达：开头即检查，不能 discard（否则取消失效）
        if rid in self._cancelled:
            self._cancelled.discard(rid)
            return {"cancelled": True}
        self._last_progress[rid] = 0

        image_path = params["image_path"]
        try:
            grid_w = max(1, min(int(params.get("grid_w", 50)), MAX_GRID_SIZE))
            grid_h = max(1, min(int(params.get("grid_h", 50)), MAX_GRID_SIZE))
        except (TypeError, ValueError):
            return {"error": "网格参数无效"}
        # 板数网格：按 29/58/87 板自动适配比例
        board = params.get("board")
        if board:
            from PIL import Image as _Img
            with _Img.open(image_path) as im:
                iw, ih = im.size
            board = int(board)
            grid_w = board
            grid_h = max(1, round(board * ih / iw))

        def cb(y, total):
            self._emit_progress(rid, y, total)
            return self._cancel_check(rid)

        result = self.processor.process_image(
            image_path,
            grid_w=grid_w,
            grid_h=grid_h,
            cell_size=params.get("cell_size"),
            fit_box=params.get("fit_box", False),
            exact_grid=params.get("exact_grid", False),
            show_finished=params.get("show_finished", True),
            effects=params.get("effects"),
            show_grid=params.get("show_grid", True),
            grid_color=tuple(params.get("grid_color", (200, 200, 200))),
            palette_name=_resolve_palette(params.get("palette", "mard_221")),
            show_color_legend=params.get("show_color_legend", True),
            show_row_col_labels=params.get("show_row_col_labels", True),
            save=False, cancel_callback=cb)

        cancelled = rid in self._cancelled
        self._cancelled.discard(rid)
        self._last_progress.pop(rid, None)
        if result is None:
            if cancelled:
                return {"cancelled": True}
            return {"error": "生成失败"}

        base = f"perler_{int(time.time())}_{rid}.png"
        chart_path = os.path.join(OUTPUT_DIR, base)
        chart_size = list(result.chart.size)
        try:
            result.chart.save(chart_path)
        finally:
            result.chart.close()
        finished_path = None
        finished_size = None
        if result.finished is not None:
            finished_path = os.path.join(OUTPUT_DIR, f"finished_{int(time.time())}_{rid}.png")
            finished_size = list(result.finished.size)
            try:
                result.finished.save(finished_path)
            finally:
                result.finished.close()
        prune_output()
        return {
            "chart_path": chart_path,
            "chart_size": chart_size,
            "finished_path": finished_path,
            "finished_size": finished_size,
            "color_stats": result.color_stats,
            "total_beads": result.total_beads,
            "grid_w": result.grid_w,
            "grid_h": result.grid_h,
            "cell_size": result.cell_size,
            "palette": params.get("palette", "mard_221"),
        }

    def _edit(self, rid, params):
        """手动编辑：重生成 + 应用格子覆盖，返回更新后的图纸"""
        if rid in self._cancelled:
            self._cancelled.discard(rid)
            return {"cancelled": True}
        self._last_progress[rid] = 0
        image_path = params["image_path"]
        try:
            grid_w = max(1, min(int(params.get("grid_w", 50)), MAX_GRID_SIZE))
            grid_h = max(1, min(int(params.get("grid_h", 50)), MAX_GRID_SIZE))
        except (TypeError, ValueError):
            return {"error": "网格参数无效"}
        board = params.get("board")
        if board:
            from PIL import Image as _Img
            with _Img.open(image_path) as im:
                iw, ih = im.size
            grid_w = int(board)
            grid_h = max(1, round(int(board) * ih / iw))
        overrides = {}
        for item in params.get("overrides") or []:
            if not isinstance(item, dict):
                continue
            try:
                x = int(item.get("x", -1))
                y = int(item.get("y", -1))
            except (TypeError, ValueError):
                continue
            code = item.get("code")
            if x >= 0 and y >= 0 and code:
                overrides[(y, x)] = code

        def cb(y, total):
            self._emit_progress(rid, y, total)
            return self._cancel_check(rid)

        result = self.processor.process_image(
            image_path, grid_w=grid_w, grid_h=grid_h,
            cell_size=params.get("cell_size"),
            fit_box=params.get("fit_box", False),
            exact_grid=params.get("exact_grid", False),
            show_finished=True,
            effects=params.get("effects"),
            grid_overrides=overrides,
            show_grid=params.get("show_grid", True),
            grid_color=tuple(params.get("grid_color", (200, 200, 200))),
            palette_name=_resolve_palette(params.get("palette", "mard_221")),
            show_color_legend=params.get("show_color_legend", True),
            show_row_col_labels=params.get("show_row_col_labels", True),
            save=False, cancel_callback=cb)
        cancelled = rid in self._cancelled
        self._cancelled.discard(rid)
        self._last_progress.pop(rid, None)
        if result is None:
            if cancelled:
                return {"cancelled": True}
            return {"error": "编辑失败"}
        base = f"perler_edit_{int(time.time())}_{rid}.png"
        chart_path = os.path.join(OUTPUT_DIR, base)
        chart_size = list(result.chart.size)
        try:
            result.chart.save(chart_path)
        finally:
            result.chart.close()
        finished_path = None
        if result.finished is not None:
            finished_path = os.path.join(OUTPUT_DIR, f"finished_edit_{int(time.time())}_{rid}.png")
            try:
                result.finished.save(finished_path)
            finally:
                result.finished.close()
        prune_output()
        return {
            "chart_path": chart_path,
            "chart_size": chart_size,
            "finished_path": finished_path,
            "color_stats": result.color_stats,
            "total_beads": result.total_beads,
            "grid_w": result.grid_w,
            "grid_h": result.grid_h,
            "cell_size": result.cell_size,
        }

    def _track_load(self, params):
        key = str(params.get("key", ""))
        if not _TRACK_KEY_RE.match(key):
            return []
        path = os.path.join(track_dir(), f"{key}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (IOError, OSError, ValueError):
            return []

    def _track_save(self, params):
        key = str(params.get("key", ""))
        cells = params.get("cells") or []
        if not _TRACK_KEY_RE.match(key):
            return
        path = os.path.join(track_dir(), f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cells, f, ensure_ascii=False)

    # ---------- 导出 ----------
    def _export_png(self, params):
        from PIL import Image
        src = params["source_path"]
        out = params["save_path"]
        img = Image.open(src)
        try:
            if params.get("transparent"):
                rgba = img.convert("RGBA")
                arr = np.asarray(rgba).astype(np.int32).copy()
                dist = np.abs(arr[..., :3] - 255).sum(-1)
                arr[..., 3][dist <= 12] = 0
                img = Image.fromarray(arr.astype(np.uint8), "RGBA")
            img.save(out)
        finally:
            img.close()
        return {"save_path": out}

    def _export_bom(self, params):
        """导出材料清单 CSV：code,name,rgb,count,percent"""
        import csv
        stats = params.get("stats") or {}
        save_path = params["save_path"]
        rows = sorted(stats.items(), key=lambda x: -x[1]["count"])
        total = sum(v["count"] for v in stats.values()) or 1
        with open(save_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["色号", "名称", "R", "G", "B", "数量", "占比%"])
            for code, info in rows:
                rgb = info.get("rgb", (0, 0, 0))
                writer.writerow([code, info.get("name", ""), rgb[0], rgb[1], rgb[2],
                                 info["count"], round(info["count"] / total * 100, 1)])
        return {"save_path": save_path}

    def _export_pdf(self, params):
        from PIL import Image
        img = Image.open(params["source_path"])
        try:
            self.processor.export_pdf(img, params["save_path"],
                                      params.get("mode", "a4"),
                                      params.get("cell_size"),
                                      bom=params.get("bom"),
                                      bw=params.get("bw", False))
        finally:
            img.close()
        return {"save_path": params["save_path"]}

    # ---------- 历史 ----------
    def _history(self, params):
        action = params.get("action", "list")
        if action == "list":
            return {"records": self.history.get_list()}
        if action == "add":
            r = params.get("record") or {}
            if not isinstance(r, dict):
                return {"ok": False, "error": "记录无效"}
            self.history.add_record(
                r.get("image_path", ""), r.get("save_path", ""),
                r.get("width", 0), r.get("height", 0),
                r.get("ratio", "按原图比例（宽为基准）"),
                r.get("cell_px", 60), r.get("show_grid", True),
                r.get("grid_color", "#C8C8C8"), r.get("palette", "MARD 221 色"),
                r.get("show_labels", True), r.get("show_legend", True))
            return {"ok": True}
        if action == "delete":
            self.history.delete_record(int(params.get("index", 0)))
            return {"ok": True}
        if action == "clear":
            self.history.clear_history()
            return {"ok": True}
        raise ValueError(f"未知历史操作: {action}")


def serve():
    server = CoreServer()
    work_queue = queue.Queue()

    def writer(msg):
        server._emit(msg)

    def reader():
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(req, dict):
                continue
            rid = req.get("id")
            if req.get("op") == "cancel":
                server._cancelled.add(rid)
                writer({"id": rid, "ok": True, "cancelled": True})
            else:
                work_queue.put(req)
        work_queue.put(None)

    def worker():
        while True:
            req = work_queue.get()
            if req is None:
                break
            rid = req.get("id")
            try:
                result = server.handle(req)
            except Exception as e:
                result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            writer({"id": rid, **result})

    threading.Thread(target=reader, daemon=True).start()
    worker()


if __name__ == "__main__":
    serve()
