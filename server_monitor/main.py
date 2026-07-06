"""ServerMonitor-GUI 应用入口"""

import sys
import os
import logging

# 确保项目根目录在 Python 路径中（由 run_monitor.py 或 python -m 处理）
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_stylesheet() -> str:
    """加载全局样式表"""
    qss_path = os.path.join(
        os.path.dirname(__file__), "assets", "styles", "dark.qss"
    )
    try:
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting ServerMonitor-GUI...")

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    # 高 DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("ServerMonitor-GUI")

    # 加载样式
    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    from server_monitor.ui.main_window import MainWindow
    window = MainWindow()

    # 登录验证
    if not window.start():
        sys.exit(0)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
