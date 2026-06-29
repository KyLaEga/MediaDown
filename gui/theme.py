import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor, QIcon, QPixmap
from PySide6.QtCore import QByteArray
from PySide6 import QtSvg  # noqa: F401

class ThemeManager:
    _THEMES_SUBDIR = os.path.join("assets", "themes")

    DARK = {
        "bg": "#1E1F22",
        "surface": "#2B2D31",
        "text": "#DBDEE1",
        "border": "#4E5058",
    }
    LIGHT = {
        "bg": "#F2F3F5",
        "surface": "#FFFFFF",
        "text": "#313338",
        "border": "#E3E5E8",
    }

    FONT_CAPTION = 11
    FONT_BASE = 13
    FONT_HEADER = 16
    FONT_H1 = 20

    # Только реально используемые в интерфейсе иконки
    ICON_GLYPHS = {
        "play": "M8 5v14l11-7z",
        "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
        "stop": "M6 6h12v12H6z",
        "download": "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
        "folder": "M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z",
        "trash": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
    }

    @classmethod
    def make_icon(cls, glyph_name: str, color: str) -> QIcon:
        path_d = cls.ICON_GLYPHS.get(glyph_name)
        if not path_d:
            return QIcon()
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'width="48" height="48"><path fill="{color}" d="{path_d}"/></svg>'
        )
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(svg.encode("utf-8")), "SVG")
        return QIcon(pixmap)

    _active = DARK

    @classmethod
    def colors(cls) -> dict:
        return cls._active

    @staticmethod
    def _resource_root() -> Path:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            if sys.platform == "darwin":
                mac_resources = exe_dir.parent / "Resources"
                if mac_resources.exists():
                    return mac_resources
            return exe_dir
        return Path(__file__).resolve().parent.parent

    @classmethod
    def _load_stylesheet(cls, theme_name: str, fallback_qss: str) -> str:
        qss_path = cls._resource_root() / cls._THEMES_SUBDIR / f"{theme_name}.qss"
        try:
            if qss_path.is_file():
                text = qss_path.read_text(encoding="utf-8")
                if text.strip():
                    return text
        except OSError:
            pass
        return fallback_qss

    @classmethod
    def _typography_qss(cls) -> str:
        return (
            f'QLabel[txt="h1"] {{ font-size: {cls.FONT_H1}px; font-weight: bold; }}'
            f'QLabel[txt="h2"] {{ font-size: {cls.FONT_HEADER}px; font-weight: bold; }}'
            f'QLabel[txt="body"] {{ font-size: {cls.FONT_BASE}px; }}'
            f'QLabel[txt="caption"] {{ font-size: {cls.FONT_CAPTION}px; }}'
        )

    @classmethod
    def apply_modern_dark(cls, app: QApplication):
        cls._active = cls.DARK
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(cls.DARK["bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(cls.DARK["text"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(cls.DARK["surface"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(cls.DARK["text"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(64, 66, 73))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(cls.DARK["text"]))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(148, 155, 164))
        app.setPalette(palette)

        qss = """
        QWidget#sidebar { background-color: #1E1F22; }
        QWidget#card { background-color: #2B2D31; border-radius: 8px; }
        QFrame#divider { max-height: 1px; min-height: 1px; background-color: #4E5058; border: none; }

        QPushButton {
            background-color: #404249; color: #DBDEE1;
            border: none; border-radius: 6px;
            padding: 6px 14px; font-weight: 500;
            min-height: 24px;
        }
        QPushButton:hover { background-color: #4E5058; }
        QPushButton:pressed { background-color: #313338; }
        QPushButton:disabled { background-color: #313338; color: #5C5E66; }

        QPushButton#primary { background-color: #23A559; color: white; font-weight: bold; }
        QPushButton#primary:hover { background-color: #1D8A4A; }
        QPushButton#danger { background-color: #DA373C; color: white; font-weight: bold; }
        QPushButton#danger:hover { background-color: #A12828; }

        QPushButton#secondary {
            background-color: transparent;
            border: 1px solid #4E5058;
            border-radius: 6px;
            padding: 6px 14px;
            color: #DBDEE1;
            min-height: 24px;
        }
        QPushButton#secondary:hover { background-color: #3F4147; border: 1px solid #5865F2; }

        QLineEdit, QPlainTextEdit {
            background-color: #1E1F22; color: #FFFFFF;
            border: 1px solid #4E5058; border-radius: 6px;
            padding: 4px 10px; selection-background-color: #5865F2;
        }
        QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #5865F2; }

        QLineEdit#spin_entry {
            border-radius: 0; border-left: none; border-right: none;
            padding: 4px;
        }
        QPushButton#spin_btn_left, QPushButton#spin_btn_right {
            background-color: #404249; border: 1px solid #4E5058; color: #DBDEE1;
            font-weight: bold; font-size: 14px; padding: 0; min-height: 24px;
        }
        QPushButton#spin_btn_left { border-top-right-radius: 0; border-bottom-right-radius: 0; border-right: none; }
        QPushButton#spin_btn_right { border-top-left-radius: 0; border-bottom-left-radius: 0; border-left: none; }
        QPushButton#spin_btn_left:hover, QPushButton#spin_btn_right:hover { background-color: #4E5058; }
        QPushButton#spin_btn_left:pressed, QPushButton#spin_btn_right:pressed { background-color: #313338; }

        QTreeWidget#tree { background-color: #2B2D31; border: none; outline: none; border-radius: 8px; padding: 5px; color: #DBDEE1; }
        QTreeWidget::item { padding: 4px; border-radius: 4px; color: #DBDEE1; }
        QTreeWidget::item:selected { background-color: #3F4147; color: white; }
        QHeaderView::section { background-color: #1E1F22; color: #949BA4; border: none; padding: 4px 8px; font-weight: bold; }

        QComboBox {
            background-color: transparent; color: #DBDEE1;
            border: 1px solid #4E5058; border-radius: 6px;
            padding: 4px 6px 4px 6px;
            combobox-popup: 0;
            outline: none;
        }
        QComboBox:hover { background-color: #3F4147; border: 1px solid #5865F2; }
        QComboBox:focus, QComboBox:on { border: 1px solid #5865F2; }
        QComboBox::drop-down {
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 20px; border: none; background: transparent;
        }
        QComboBox::down-arrow { width: 12px; height: 12px; }
        QComboBox::down-arrow:on { top: 1px; }

        QComboBox QAbstractItemView {
            background-color: #2B2D31; color: #DBDEE1;
            border: 1px solid #4E5058; border-radius: 6px;
            padding: 4px; outline: none;
            selection-background-color: #5865F2; selection-color: #FFFFFF;
        }
        QComboBox QAbstractItemView::item {
            min-height: 26px; padding: 4px 10px;
            border: none; border-radius: 4px;
        }
        QComboBox QAbstractItemView::item:hover { background-color: #3F4147; color: #FFFFFF; }
        QComboBox QAbstractItemView::item:selected { background-color: #5865F2; color: #FFFFFF; }

        QLabel { color: #DBDEE1; }
        QLabel#status { color: #949BA4; }

        QScrollBar:vertical { background: transparent; width: 14px; margin: 0px; }
        QScrollBar::handle:vertical { background: #4E5058; min-height: 20px; border-radius: 7px; border: 3px solid #2B2D31; }
        QScrollBar::handle:vertical:hover { background: #949BA4; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

        QScrollBar:horizontal { background: transparent; height: 14px; margin: 0px; }
        QScrollBar::handle:horizontal { background: #4E5058; min-width: 20px; border-radius: 7px; border: 3px solid #2B2D31; }
        QScrollBar::handle:horizontal:hover { background: #949BA4; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

        QProgressBar { border: none; background-color: #1E1F22; border-radius: 2px; text-align: center; color: transparent; }
        QProgressBar::chunk { background-color: #5865F2; border-radius: 2px; }
        """
        app.setStyleSheet(cls._load_stylesheet("dark", qss) + cls._typography_qss())

    @classmethod
    def apply_modern_light(cls, app: QApplication):
        cls._active = cls.LIGHT
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(cls.LIGHT["bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(cls.LIGHT["text"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(cls.LIGHT["surface"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(cls.LIGHT["text"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(cls.LIGHT["border"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(cls.LIGHT["text"]))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(148, 155, 164))
        app.setPalette(palette)

        qss = """
        QWidget#sidebar { background-color: #F2F3F5; }
        QWidget#card { background-color: #FFFFFF; border-radius: 8px; border: 1px solid #E3E5E8; }
        QFrame#divider { max-height: 1px; min-height: 1px; background-color: #E3E5E8; border: none; }

        QPushButton {
            background-color: #E3E5E8; color: #313338;
            border: none; border-radius: 6px;
            padding: 6px 14px; font-weight: 500;
            min-height: 24px;
        }
        QPushButton:hover { background-color: #D4D7DC; }
        QPushButton:pressed { background-color: #B5BAC1; }
        QPushButton:disabled { background-color: #E3E5E8; color: #949BA4; }

        QPushButton#primary { background-color: #23A559; color: white; font-weight: bold; }
        QPushButton#primary:hover { background-color: #1D8A4A; }
        QPushButton#danger { background-color: #DA373C; color: white; font-weight: bold; }
        QPushButton#danger:hover { background-color: #A12828; }

        QPushButton#secondary {
            background-color: transparent;
            border: 1px solid #D4D7DC;
            border-radius: 6px;
            padding: 6px 14px;
            color: #313338;
            min-height: 24px;
        }
        QPushButton#secondary:hover { background-color: #E3E5E8; border: 1px solid #5865F2; }

        QLineEdit, QPlainTextEdit {
            background-color: #FFFFFF; color: #313338;
            border: 1px solid #D4D7DC; border-radius: 6px;
            padding: 4px 10px; selection-background-color: #5865F2; selection-color: white;
        }
        QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #5865F2; }

        QLineEdit#spin_entry {
            border-radius: 0; border-left: none; border-right: none;
            padding: 4px;
        }
        QPushButton#spin_btn_left, QPushButton#spin_btn_right {
            background-color: #F2F3F5; border: 1px solid #D4D7DC; color: #313338;
            font-weight: bold; font-size: 14px; padding: 0; min-height: 24px;
        }
        QPushButton#spin_btn_left { border-top-right-radius: 0; border-bottom-right-radius: 0; border-right: none; }
        QPushButton#spin_btn_right { border-top-left-radius: 0; border-bottom-left-radius: 0; border-left: none; }
        QPushButton#spin_btn_left:hover, QPushButton#spin_btn_right:hover { background-color: #E3E5E8; }
        QPushButton#spin_btn_left:pressed, QPushButton#spin_btn_right:pressed { background-color: #D4D7DC; }

        QTreeWidget#tree { background-color: #FFFFFF; border: 1px solid #E3E5E8; outline: none; border-radius: 8px; padding: 5px; color: #313338; }
        QTreeWidget::item { padding: 4px; border-radius: 4px; color: #313338; }
        QTreeWidget::item:selected { background-color: #E3E5E8; color: #000000; }
        QHeaderView::section { background-color: #F2F3F5; color: #5C5E66; border: none; padding: 4px 8px; font-weight: bold; border-bottom: 1px solid #E3E5E8; }

        QComboBox {
            background-color: transparent; color: #313338;
            border: 1px solid #D4D7DC; border-radius: 6px;
            padding: 4px 6px 4px 6px;
            combobox-popup: 0;
            outline: none;
        }
        QComboBox:hover { background-color: #F2F3F5; border: 1px solid #5865F2; }
        QComboBox:focus, QComboBox:on { border: 1px solid #5865F2; }
        QComboBox::drop-down {
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 20px; border: none; background: transparent;
        }
        QComboBox::down-arrow { width: 12px; height: 12px; }
        QComboBox::down-arrow:on { top: 1px; }

        QComboBox QAbstractItemView {
            background-color: #FFFFFF; color: #313338;
            border: 1px solid #D4D7DC; border-radius: 6px;
            padding: 4px; outline: none;
            selection-background-color: #5865F2; selection-color: #FFFFFF;
        }
        QComboBox QAbstractItemView::item {
            min-height: 26px; padding: 4px 10px;
            border: none; border-radius: 4px;
        }
        QComboBox QAbstractItemView::item:hover { background-color: #F2F3F5; color: #313338; }
        QComboBox QAbstractItemView::item:selected { background-color: #5865F2; color: #FFFFFF; }

        QLabel { color: #313338; }
        QLabel#status { color: #5C5E66; }

        QScrollBar:vertical { background: transparent; width: 14px; margin: 0px; }
        QScrollBar::handle:vertical { background: #D4D7DC; min-height: 20px; border-radius: 7px; border: 3px solid #FFFFFF; }
        QScrollBar::handle:vertical:hover { background: #949BA4; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

        QScrollBar:horizontal { background: transparent; height: 14px; margin: 0px; }
        QScrollBar::handle:horizontal { background: #D4D7DC; min-width: 20px; border-radius: 7px; border: 3px solid #FFFFFF; }
        QScrollBar::handle:horizontal:hover { background: #949BA4; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

        QProgressBar { border: none; background-color: #E3E5E8; border-radius: 2px; text-align: center; color: transparent; }
        QProgressBar::chunk { background-color: #5865F2; border-radius: 2px; }
        """
        app.setStyleSheet(cls._load_stylesheet("light", qss) + cls._typography_qss())

    @classmethod
    def apply_system_theme(cls, app: QApplication):
        # Определяем светлая или тёмная системная тема и применяем
        # соответствующий ПОЛНЫЙ набор стилей (а не только типографику),
        # иначе кнопки/карточки теряют оформление по objectName.
        app.setStyle("Fusion")
        window = app.style().standardPalette().color(QPalette.ColorRole.Window)
        if window.lightnessF() < 0.5:
            cls.apply_modern_dark(app)
        else:
            cls.apply_modern_light(app)
