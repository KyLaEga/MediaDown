#!/usr/bin/env python3
"""
Universal Media Downloader
Современная версия с графическим интерфейсом на PySide6
"""

import sys
import os

# Добавить путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    """Главная функция"""
    # Создать приложение Qt
    app = QApplication(sys.argv)
    
    # Создать и показать главное окно
    window = MainWindow()
    window.show()
    
    # Запустить цикл обработки событий
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
