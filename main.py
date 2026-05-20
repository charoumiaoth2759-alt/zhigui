# -*- coding: utf-8 -*-
"""应用入口"""
import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("智柜")
    app.setApplicationVersion("V2026")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
