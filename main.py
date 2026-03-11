# main.py - 修正版
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from config import APP_NAME, VERSION
from core.utils import setup_logging


def main():
    # 启用高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 设置应用信息
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    # 初始化日志
    logger = setup_logging()
    logger.info(f"启动 {APP_NAME} v{VERSION}")

    # 🔧 修改：从 win_ui.main_window 导入 DesktopUI
    from ui.win_ui.main_window import DesktopUI
    window = DesktopUI()
    window.show()

    logger.info("界面初始化完成")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()