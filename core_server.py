# core_server.py - 常驻引擎服务（stdio JSON 行协议）
# SwiftUI 前端通过子进程与引擎通信：
#   请求:  {"id": 1, "op": "generate", "params": {...}}
#   响应:  {"id": 1, "ok": true, ...}
#   事件:  {"id": 1, "event": "progress", "progress": 0.5}
# 取消:  {"id": 1, "op": "cancel"}（读线程即时处理，可中断进行中的生成）
import json
import os
import queue
import sys
import threading
import time

import numpy as np

from core.colors import PALETTE_OPTIONS, _PALETTE_CACHE, get_palette
from core.effects import list_effects
from core.history_manager import HistoryManager
from core.processor import ImageProcessor, OUTPUT_DIR
from core.settings import load_queue, load_settings, save_queue, save_settings
from core.version import APP_VERSION

PROGRESS_THROTTLE = 0.02  # 每 2% 发一次进度事件


def tempfile_dir():
    import tempfile
    return tempfile.gettempdir()


class CoreServer:
    def __init__(self):
        self.processor = ImageProcessor()
        self.history = HistoryManager()
        self.settings = load_settings()
        self._cancelled = set()
        self._last_progress = {}
        self._out_lock = threading.Lock()

    # ---------- 分发 ----------
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
            return {"ok": True, **self._generate(rid, params)}
        if op == "export_png":
            return {"ok": True, **self._export_png(params)}
        if op == "export_bom":
            return {"ok": True, **self._export_bom(params)}
        if op == "export_pdf":
            return {"ok": True, **self._export_pdf(params)}
        if op == "palettes":
            return {"ok": True, "palettes": [
                {"display": d, "internal": i, "count": len(get_palette(i).colors)}
                for d, i in PALETTE_OPTIONS]}
        if op == "palette_colors":
            palette = get_palette(params.get("internal", "mard_221"))
            return {"ok": True, "codes": palette.codes, "names": palette.names,
                    "colors": palette.colors, "hex": palette.hex_codes}
        if op == "my_colors_get":
            from core.my_colors import load_my_colors
            data = load_my_colors()
            return {"ok": True, "my_colors": data}
        if op == "my_colors_save":
            from core.my_colors import save_my_colors
            save_my_colors(params.get("colors") or [],
                           params.get("names"), params.get("codes"))
            _PALETTE_CACHE.pop("my_colors", None)
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
            tpl = load_template(params.get("template_id", ""))
            if tpl is None:
                return {"ok": False, "error": "模板不存在"}
            img = template_to_image(tpl)
            if img is None:
                return {"ok": False, "error": "模板数据无效"}
            path = os.path.join(tempfile_dir(), f"tpl_{params.get('template_id')}.png")
            img.save(path)
            return {"ok": True, "image_path": path, "width": img.width,
                    "height": img.height}
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
        self._cancelled.discard(rid)
        self._last_progress[rid] = 0

        image_path = params["image_path"]
        grid_w = params.get("grid_w", 50)
        grid_h = params.get("grid_h", 50)
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
            show_finished=params.get("show_finished", True),
            effects=params.get("effects"),
            show_grid=params.get("show_grid", True),
            grid_color=tuple(params.get("grid_color", (200, 200, 200))),
            palette_name=params.get("palette", "mard_221"),
            show_color_legend=params.get("show_color_legend", True),
            show_row_col_labels=params.get("show_row_col_labels", True),
            save=False, cancel_callback=cb)

        cancelled = rid in self._cancelled
        self._cancelled.discard(rid)
        if result is None:
            if cancelled:
                return {"cancelled": True}
            return {"error": "生成失败"}

        base = f"perler_{int(time.time())}_{rid}.png"
        chart_path = os.path.join(OUTPUT_DIR, base)
        result.chart.save(chart_path)
        return {
            "chart_path": chart_path,
            "chart_size": list(result.chart.size),
            "finished_size": list(result.finished.size) if result.finished else None,
            "color_stats": result.color_stats,
            "total_beads": result.total_beads,
            "grid_w": result.grid_w,
            "grid_h": result.grid_h,
            "cell_size": result.cell_size,
            "palette": params.get("palette", "mard_221"),
        }

    # ---------- 导出 ----------
    def _export_png(self, params):
        from PIL import Image
        src = params["source_path"]
        out = params["save_path"]
        img = Image.open(src)
        if params.get("transparent"):
            rgba = img.convert("RGBA")
            arr = np.asarray(rgba).astype(np.int32).copy()
            dist = np.abs(arr[..., :3] - 255).sum(-1)
            arr[..., 3][dist <= 12] = 0
            img = Image.fromarray(arr.astype(np.uint8), "RGBA")
        img.save(out)
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
            self.history.add_record(
                r.get("image_path", ""), r.get("save_path", ""),
                r.get("width", 0), r.get("height", 0),
                r.get("ratio", "按原图比例（宽为基准）"),
                r.get("cell_px", 60), r.get("show_grid", True),
                r.get("grid_color", "#C8C8C8"), r.get("palette", "MARD 221 色"),
                r.get("show_labels", True))
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
            rid = req.get("id")
            if req.get("op") == "cancel":
                server._cancelled.add(rid)
                writer({"id": rid, "ok": True, "cancelled": True})
            else:
                work_queue.put(req)

    def worker():
        while True:
            req = work_queue.get()
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
