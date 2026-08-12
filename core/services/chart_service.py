# core/services/chart_service.py - 单图生成/保存/导出服务
from typing import Optional

from core.colors import display_to_internal
from core.models import GenerateParams


class ChartService:
    """把「参数快照 → 图纸/导出文件」的业务逻辑从 UI 中剥离。

    不依赖任何 Tk 组件，可在无界面环境下单测。
    """

    def __init__(self, processor):
        self.processor = processor

    def generate(self, image_path: str, params: GenerateParams,
                 show_finished: bool = True, cancel_callback=None):
        """按参数生成图纸，返回 GenerateResult；失败/取消返回 None"""
        params = params.clamp()
        return self.processor.process_image(
            image_path, params.grid_w, params.grid_h, cell_size=params.cell_px,
            show_grid=params.show_grid, grid_color=params.grid_rgb,
            palette_name=display_to_internal(params.palette),
            show_color_legend=params.show_legend,
            show_row_col_labels=params.show_labels, show_finished=show_finished,
            fit_box=params.fit_box, exact_grid=params.exact_grid,
            save=False, cancel_callback=cancel_callback)

    @staticmethod
    def save_chart(result, save_path: str) -> str:
        result.chart.save(save_path)
        return save_path

    def export_pdf(self, chart, save_path: str, mode: str, cell_size: Optional[int]):
        """导出 PDF：a4=适应单页 / 1x1=实物多页拼接"""
        return self.processor.export_pdf(chart, save_path, mode, cell_size)
