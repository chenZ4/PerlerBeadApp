# core/services/batch_service.py - 批量队列处理服务
import os
from typing import Callable, List, Optional

from core.colors import display_to_internal
from core.models import BatchResult, QueueItem


class BatchService:
    """批量队列处理：进度/取消/结果汇总，UI 无关。

    回调约定：
    - is_cancelled(): 返回 True 时尽快中止
    - on_progress(idx_done, total, out_path): 每项完成后的进度回调
    - unique_path_fn(directory, base, ext): 输出文件名防覆盖策略
    """

    def __init__(self, processor, history_mgr, unique_path_fn=None):
        self.processor = processor
        self.history_mgr = history_mgr
        self._unique_path = unique_path_fn or self._default_unique_path
        self._cancelled: Callable[[], bool] = lambda: False

    @staticmethod
    def _default_unique_path(directory: str, base: str, ext: str) -> str:
        path = os.path.join(directory, f"{base}.{ext}")
        i = 2
        while os.path.exists(path):
            path = os.path.join(directory, f"{base}_{i}.{ext}")
            i += 1
        return path

    def _build_output(self, out_dir: str, item: QueueItem):
        """生成一个 QueueItem 的导出文件名"""
        src_name = os.path.splitext(os.path.basename(item.image_path))[0]
        p = item.params
        base = f"perler_{src_name}_{p.grid_w}x{p.grid_h}_{display_to_internal(p.palette)}"
        if item.export_mode:
            base += f"_{item.export_mode}"
        return self._unique_path(out_dir, base, item.ext)

    def _process_one(self, out_dir: str, item: QueueItem):
        """处理单个队列项，返回导出路径；取消时返回 None"""
        params = item.params.clamp()
        out_path = self._build_output(out_dir, item)
        result = self.processor.process_image(
            item.image_path, params.grid_w, params.grid_h,
            cell_size=params.cell_px,
            show_grid=params.show_grid,
            grid_color=params.grid_rgb,
            palette_name=display_to_internal(params.palette),
            show_color_legend=params.show_legend,
            show_row_col_labels=params.show_labels,
            fit_box=params.fit_box, exact_grid=params.exact_grid,
            save=False, cancel_callback=lambda: self._cancelled())
        if result is None:
            if self._cancelled():
                return None
            raise RuntimeError("生成失败")
        if self._cancelled():
            return None
        img = result.chart
        try:
            if item.export_mode:
                self.processor.export_pdf(img, out_path, item.export_mode, result.cell_size)
            else:
                img.save(out_path)
        finally:
            img.close()
        self.history_mgr.add_record(
            item.image_path, out_path,
            params.grid_w, params.grid_h, params.ratio,
            params.cell_px, params.show_grid,
            params.grid_color, params.palette,
            params.show_labels, params.show_legend)
        return out_path

    def process(self, items: List[QueueItem], out_dir: str,
                on_progress: Optional[Callable[[int, int, str], None]] = None,
                is_cancelled: Optional[Callable[[], bool]] = None) -> BatchResult:
        """同步处理队列（Tk 单线程事件循环下由调用方保证 UI 刷新）"""
        self._cancelled = is_cancelled or (lambda: False)
        total = len(items)
        result = BatchResult()
        try:
            for idx, item in enumerate(items):
                if self._cancelled():
                    result.cancelled_remaining = total - idx
                    break
                out_path = None
                try:
                    out_path = self._process_one(out_dir, item)
                    if out_path is None:  # 处理中被取消
                        result.cancelled_remaining = total - idx
                        break
                    result.success.append(out_path)
                except Exception as e:
                    result.failed.append((os.path.basename(item.image_path), str(e)))
                if on_progress:
                    try:
                        on_progress(idx + 1, total, out_path or "")
                    except Exception:
                        pass
        finally:
            self._cancelled = lambda: False
        return result
