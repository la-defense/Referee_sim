"""GUI 启动入口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RoboMaster 裁判系统模拟器")
    app.setOrganizationName("MC-02")
    window = MainWindow()
    window.show()
    return app.exec()
