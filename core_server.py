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
import tempfile
import threading
import time

from core.colors import PALETTE_OPTIONS, get_palette
from core.effects import list_effects
from core.history_manager import HistoryManager
from core.processor import ImageProcessor, OUTPUT_DIR
from core.settings import load_queue, load_settings, save_queue, save_settings
from core.version import APP_VERSION

PROGRESS_THROTTLE = 0.02  # 每 2% 发一次进度事件


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

        def cb(y, total):
            self._emit_progress(rid, y, total)
            return self._cancel_check(rid)

        result = self.processor.process_image(
            params["image_path"],
            grid_w=params.get("grid_w", 50),
            grid_h=params.get("grid_h", 50),
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
        src = params["source_path"]
        out = params["save_path"]
        from PIL import Image
        img = Image.open(src)
        img.save(out)
        img.close()
        return {"save_path": out}

    def _export_pdf(self, params):
        from PIL import Image
        img = Image.open(params["source_path"])
        try:
            self.processor.export_pdf(img, params["save_path"],
                                      params.get("mode", "a4"),
                                      params.get("cell_size"))
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
