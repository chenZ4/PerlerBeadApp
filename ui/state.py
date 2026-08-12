# ui/state.py - 应用状态中枢（模型 + 撤销栈 + 变更通知）
from typing import Callable, List, Optional

from core.models import GenerateParams, UndoSnapshot


class AppState:
    """Tk 版应用的运行时状态。

    - 参数快照（GenerateParams）为唯一事实来源，面板通过 apply_params/current_params 同步
    - 图片与结果集中管理（负责旧图 close，防内存泄漏）
    - 撤销栈为结构化 UndoSnapshot
    - 通过 emit() 通知控制器（事件名：'params' / 'result' / 'image'）
    """

    def __init__(self, store, initial_params: GenerateParams):
        self.store = store
        self.params = initial_params
        self.settings = store.load_settings()

        self.selected_file: Optional[str] = None
        self.original_image = None
        self.processed_image = None
        self.finished_image = None
        self.color_stats = {}
        self.total_beads = 0
        self.last_cell_size = 0

        self.previous_states: List[UndoSnapshot] = []
        self.max_undo_steps = 10

        self._listeners: List[Callable[[str], None]] = []

    # ---------- 观察者 ----------
    def on_change(self, fn):
        self._listeners.append(fn)

    def emit(self, event: str):
        for fn in self._listeners:
            fn(event)

    # ---------- 参数 ----------
    def set_params(self, params: GenerateParams):
        self.params = params
        self.emit('params')

    # ---------- 撤销 ----------
    def save_state(self):
        self.previous_states.append(
            UndoSnapshot(params=self.params, selected_file=self.selected_file))
        if len(self.previous_states) > self.max_undo_steps:
            self.previous_states.pop(0)

    def can_undo(self) -> bool:
        return bool(self.previous_states)

    def undo(self) -> Optional[UndoSnapshot]:
        if not self.previous_states:
            return None
        snapshot = self.previous_states.pop()
        self.params = snapshot.params
        if snapshot.selected_file:
            self.selected_file = snapshot.selected_file
        return snapshot

    # ---------- 图片资源 ----------
    def replace_original_image(self, new_img):
        old = self.original_image
        self.original_image = new_img
        if old is not None and old is not new_img:
            try:
                old.close()
            except Exception:
                pass
        self.emit('image')

    def replace_processed_image(self, new_img, new_finished=None):
        old = self.processed_image
        old_f = self.finished_image
        self.processed_image = new_img
        self.finished_image = new_finished
        if old is not None and old is not new_img:
            try:
                old.close()
            except Exception:
                pass
        if old_f is not None and old_f is not new_finished:
            try:
                old_f.close()
            except Exception:
                pass

    def apply_result(self, result):
        """把生成结果应用到状态（不负责渲染）"""
        self.replace_processed_image(result.chart, result.finished)
        self.last_cell_size = result.cell_size
        self.color_stats = result.color_stats
        self.total_beads = result.total_beads

    def reset_result(self):
        """换图/清空时重置结果与编辑状态"""
        self.replace_processed_image(None, None)
        self.color_stats = {}
        self.total_beads = 0
        self.last_cell_size = 0

    # ---------- 持久化 ----------
    def persist_settings(self, window_w=0, window_h=0):
        settings = dict(self.settings)
        if window_w > 600 and window_h > 400:
            settings['window_w'] = window_w
            settings['window_h'] = window_h
        p = self.params
        settings.update({
            'ratio': p.ratio,
            'palette': p.palette,
            'cell_px': str(p.cell_px),
            'show_grid': p.show_grid,
            'show_labels': p.show_labels,
            'show_legend': p.show_legend,
            'grid_color': p.grid_color,
        })
        self.store.save_settings(settings)
        self.settings = settings
