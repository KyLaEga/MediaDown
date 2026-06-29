import os
import json
import uuid
import re
import threading
import platform
import subprocess
import queue
from queue import Queue

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTreeWidget, QTreeWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QPlainTextEdit, QFormLayout, QFrame, QProgressBar, QMenu
)
from PySide6.QtCore import Qt, QObject, Signal, QSize, QUrl
from PySide6.QtGui import QDesktopServices

class DownloadSignals(QObject):
    """Сигналы для общения фонового потока загрузки с главным UI потоком"""
    progress = Signal(str, str, str)  # task_id, text, percent_str
    status = Signal(str, str)         # task_id, status_text
    finished = Signal(str, bool, str) # task_id, success, error_msg
    all_done = Signal()               # все загрузки завершены

class ModernSpinBox(QWidget):
    valueChanged = Signal(object)
    
    def __init__(self, is_double=False, parent=None):
        super().__init__(parent)
        self.is_double = is_double
        self._min = 0.0 if is_double else 0
        self._max = 100.0 if is_double else 100
        self._step = 1.0 if is_double else 1
        self._value = 0.0 if is_double else 0
        self._suffix = ""
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.btn_minus = QPushButton("-")
        self.btn_minus.setObjectName("spin_btn_left")
        self.btn_minus.setCursor(Qt.PointingHandCursor)
        self.btn_minus.setFixedWidth(28)
        self.btn_minus.clicked.connect(self.step_down)
        
        self.entry = QLineEdit()
        self.entry.setObjectName("spin_entry")
        self.entry.setAlignment(Qt.AlignCenter)
        self.entry.editingFinished.connect(self._on_editing_finished)
        
        self.btn_plus = QPushButton("+")
        self.btn_plus.setObjectName("spin_btn_right")
        self.btn_plus.setCursor(Qt.PointingHandCursor)
        self.btn_plus.setFixedWidth(28)
        self.btn_plus.clicked.connect(self.step_up)
        
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.entry)
        layout.addWidget(self.btn_plus)
        
    def setRange(self, minimum, maximum):
        self._min = minimum
        self._max = maximum
        self.setValue(self._value)

    def setSingleStep(self, step):
        self._step = step

    def setSuffix(self, suffix):
        self._suffix = suffix
        self.update_display()

    def setValue(self, val):
        val = max(self._min, min(self._max, val))
        if val != self._value:
            self._value = val
            self.update_display()
            self.valueChanged.emit(self._value)
        else:
            self.update_display()

    def value(self):
        return self._value

    def step_up(self):
        self.setValue(self._value + self._step)

    def step_down(self):
        self.setValue(self._value - self._step)

    def update_display(self):
        val_str = f"{self._value:.2f}" if self.is_double else str(int(self._value))
        if self.is_double and "." in val_str:
            val_str = val_str.rstrip("0").rstrip(".")
        self.entry.blockSignals(True)
        self.entry.setText(val_str + self._suffix)
        self.entry.blockSignals(False)

    def _on_editing_finished(self):
        text = self.entry.text().replace(self._suffix, "").strip()
        try:
            val = float(text) if self.is_double else int(text)
            self.setValue(val)
        except ValueError:
            self.update_display()

class MainWindow(QWidget):
    """Главное окно приложения - Единый интерфейс загрузчика на PySide6"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle('Universal Media Downloader')
        self.resize(900, 600)
        self.setMinimumSize(800, 500)
        
        self.download_queue = Queue()
        self.active_downloads = 0
        self.download_lock = threading.Lock()
        self.worker_cond = threading.Condition(self.download_lock)
        self.task_items = {} # task_id -> QTreeWidgetItem
        self.task_data_map = {} # task_id -> task_data
        self.is_paused = False
        self.active_downloaders = {} # task_id -> downloader
        self.cancelled_tasks = set() # task_id -> bool
        self.is_stopped = False
        
        # Настройки по умолчанию
        self.settings_file = os.path.expanduser('~/.universal_media_downloader.json')
        self.settings = {
            'output_dir': os.path.expanduser('~/Downloads/Media'),
            'media_type': 'auto',
            'format_str': 'best',
            'quality': 'лучшее',
            'theme': 'Темная',
            'max_tasks': 3,
            'rate_limit_delay': 1.0
        }
        self.load_settings()
        
        # Запуск фоновых потоков загрузчиков по количеству max_tasks
        self.worker_threads = []
        for _ in range(self.settings.get('max_tasks', 3)):
            t = threading.Thread(target=self._worker_thread, daemon=True)
            t.start()
            self.worker_threads.append(t)
            
        
        # Настройка сигналов
        self.signals = DownloadSignals()
        self.signals.progress.connect(self.update_progress)
        self.signals.status.connect(self.update_status)
        self.signals.finished.connect(self.download_finished)
        self.signals.all_done.connect(self.all_downloads_done)
        
        # Применяем тему при старте
        from gui.theme import ThemeManager
        self.ThemeManager = ThemeManager
        self.apply_theme(self.settings.get('theme', 'Темная'))
        
        self.create_ui()
        self._on_media_setting_changed(None)
        
    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings.update(json.load(f))
            except Exception as e:
                print(f"Ошибка загрузки настроек: {e}")

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")

    def create_ui(self):
        # Главный горизонтальный контейнер для сайдбара и основной части
        main_h_layout = QHBoxLayout(self)
        main_h_layout.setContentsMargins(10, 10, 10, 10)
        main_h_layout.setSpacing(12)
        
        # --- ЛЕВАЯ ПАНЕЛЬ (САЙДБАР) ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)
        
        # Заголовок настроек и кнопка Помощь
        settings_header = QHBoxLayout()
        lbl_settings_title = QLabel("Настройки")
        lbl_settings_title.setProperty("txt", "h2")
        settings_header.addWidget(lbl_settings_title)
        
        settings_header.addStretch()
        
        self.btn_help = QPushButton("Помощь")
        self.btn_help.setObjectName("secondary")
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self.show_help)
        settings_header.addWidget(self.btn_help)
        
        sidebar_layout.addLayout(settings_header)
        
        def create_divider():
            d = QFrame()
            d.setObjectName("divider")
            return d
            
        sidebar_layout.addWidget(create_divider())
        
        # Группа 1: Сохранение
        lbl_group_save = QLabel("<b>Сохранение:</b>")
        sidebar_layout.addWidget(lbl_group_save)
        
        # Папка сохранения (LineEdit + Browse Button)
        path_layout = QHBoxLayout()
        self.output_dir_entry = QLineEdit()
        self.output_dir_entry.setText(self.settings['output_dir'])
        self.output_dir_entry.setCursorPosition(len(self.settings['output_dir']))
        self.output_dir_entry.setReadOnly(True)
        self.output_dir_entry.setToolTip(self.settings['output_dir'])
        
        self.btn_browse = QPushButton()
        self.btn_browse.setObjectName("secondary")
        self.btn_browse.setStyleSheet("padding: 4px;")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self.select_output_dir)
        self.btn_browse.setFixedWidth(40)
        path_layout.addWidget(self.output_dir_entry, stretch=1)
        path_layout.addWidget(self.btn_browse)
        sidebar_layout.addLayout(path_layout)
        
        # Формат и качество
        format_layout = QFormLayout()
        format_layout.setLabelAlignment(Qt.AlignLeft)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(8)
        
        self.media_type_combo = QComboBox()
        self.media_type_combo.addItems(['auto', 'video', 'audio', 'gallery'])
        self.media_type_combo.setCurrentText(self.settings.get('media_type', 'auto'))
        self.media_type_combo.currentTextChanged.connect(self._on_media_setting_changed)
        format_layout.addRow("Тип медиа:", self.media_type_combo)
        
        self.format_str_combo = QComboBox()
        self.format_str_combo.addItems(['best', 'mp4', 'mkv', 'mp3', 'm4a', 'jpg', 'png'])
        self.format_str_combo.setCurrentText(self.settings.get('format_str', 'best'))
        self.format_str_combo.currentTextChanged.connect(self._on_media_setting_changed)
        format_layout.addRow("Формат:", self.format_str_combo)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['лучшее', '2160p (4K)', '1440p (2K)', '1080p', '720p', '480p', '360p'])
        self.quality_combo.setCurrentText(self.settings.get('quality', 'лучшее'))
        self.quality_combo.currentTextChanged.connect(self._on_media_setting_changed)
        format_layout.addRow("Качество:", self.quality_combo)
        
        sidebar_layout.addLayout(format_layout)
        
        sidebar_layout.addWidget(create_divider())
        
        # Группа 2: Ограничения сети
        lbl_group_net = QLabel("<b>Сеть и потоки:</b>")
        sidebar_layout.addWidget(lbl_group_net)
        
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)
        
        self.spin_tasks = ModernSpinBox()
        self.spin_tasks.setRange(1, 10)
        self.spin_tasks.setValue(self.settings.get('max_tasks', 3))
        self.spin_tasks.valueChanged.connect(self.update_network_settings)
        form_layout.addRow("Задач:", self.spin_tasks)
        
        self.spin_delay = ModernSpinBox(is_double=True)
        self.spin_delay.setRange(0.0, 5.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setValue(self.settings.get('rate_limit_delay', 1.0))
        self.spin_delay.valueChanged.connect(self.update_network_settings)
        form_layout.addRow("Задержка (с):", self.spin_delay)
        sidebar_layout.addLayout(form_layout)
        
        # Статус нагрузки сети
        self.lbl_network_load = QLabel()
        self.lbl_network_load.setWordWrap(True)
        sidebar_layout.addWidget(self.lbl_network_load)
        self.update_network_settings()
        
        sidebar_layout.addWidget(create_divider())
        
        # Группа 3: Оформление
        lbl_group_theme = QLabel("<b>Интерфейс:</b>")
        sidebar_layout.addWidget(lbl_group_theme)
        
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Тема:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(['Темная', 'Светлая', 'Системная'])
        self.theme_combo.setCurrentText(self.settings.get('theme', 'Темная'))
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        theme_layout.addWidget(self.theme_combo, stretch=1)
        sidebar_layout.addLayout(theme_layout)
        
        sidebar_layout.addStretch()
        
        # --- ПРАВАЯ ЧАСТЬ (РАБОЧАЯ ОБЛАСТЬ) ---
        main_content = QWidget()
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(12)
        
        # Карточка 1: Добавление ссылок
        input_card = QWidget()
        input_card.setObjectName("card")
        input_card_layout = QVBoxLayout(input_card)
        input_card_layout.setContentsMargins(12, 12, 12, 12)
        input_card_layout.setSpacing(8)
        
        lbl_input_title = QLabel("Добавить новые ссылки")
        lbl_input_title.setProperty("txt", "h2")
        input_card_layout.addWidget(lbl_input_title)
        
        self.url_entry = QPlainTextEdit()
        self.url_entry.setPlaceholderText("Вставьте ссылки на медиа (каждая с новой строки)...")
        self.url_entry.setMaximumHeight(80)
        input_card_layout.addWidget(self.url_entry)
        
        btn_download_layout = QHBoxLayout()
        btn_download_layout.addStretch()
        self.btn_download = QPushButton("Скачать")
        self.btn_download.setObjectName("primary")
        self.btn_download.setCursor(Qt.PointingHandCursor)
        self.btn_download.clicked.connect(self.add_to_queue)
        btn_download_layout.addWidget(self.btn_download)
        input_card_layout.addLayout(btn_download_layout)
        
        main_content_layout.addWidget(input_card)
        
        # Карточка 2: Очередь загрузок
        queue_card = QWidget()
        queue_card.setObjectName("card")
        queue_card_layout = QVBoxLayout(queue_card)
        queue_card_layout.setContentsMargins(12, 12, 12, 12)
        queue_card_layout.setSpacing(8)
        
        # Панель заголовка и кнопок управления очередью
        header_layout = QHBoxLayout()
        self.lbl_queue_title = QLabel("Очередь")
        self.lbl_queue_title.setProperty("txt", "h2")
        header_layout.addWidget(self.lbl_queue_title)
        
        header_layout.addStretch()
        
        self.btn_pause = QPushButton("Пауза")
        self.btn_pause.setObjectName("secondary")
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.clicked.connect(self.toggle_pause)
        header_layout.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("Остановить")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_all_downloads)
        header_layout.addWidget(self.btn_stop)
        
        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.setObjectName("secondary")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_completed)
        header_layout.addWidget(self.btn_clear)
        
        queue_card_layout.addLayout(header_layout)
        
        # Дерево задач
        self.tree = QTreeWidget()
        self.tree.setObjectName("tree")
        self.tree.setHeaderLabels(["URL ресурса", "Статус", "Прогресс"])
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.setRootIsDecorated(False)
        
        tree_header = self.tree.header()
        tree_header.setSectionResizeMode(0, QHeaderView.Stretch)
        tree_header.setSectionResizeMode(1, QHeaderView.Fixed)
        tree_header.setSectionResizeMode(2, QHeaderView.Fixed)
        tree_header.setStretchLastSection(False)
        
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        queue_card_layout.addWidget(self.tree)
        main_content_layout.addWidget(queue_card, stretch=1)
        
        # Статус-бар внизу рабочей области
        self.lbl_status = QLabel("Готово")
        self.lbl_status.setObjectName("status")
        main_content_layout.addWidget(self.lbl_status)

        # Общий индикатор прогресса очереди
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        main_content_layout.addWidget(self.progress_bar)
        
        # Добавляем все панели в главный layout
        main_h_layout.addWidget(sidebar)
        main_h_layout.addWidget(main_content, stretch=1)
        
        # Загружаем иконки кнопок
        self.update_button_icons()

    def update_button_icons(self):
        colors = self.ThemeManager.colors()
        text_color = colors.get("text", "#DBDEE1")
        
        # Кнопка Скачать (primary)
        self.btn_download.setIcon(self.ThemeManager.make_icon("download", "white"))
        self.btn_download.setIconSize(QSize(16, 16))
        
        # Кнопка Обзор (secondary)
        self.btn_browse.setIcon(self.ThemeManager.make_icon("folder", text_color))
        self.btn_browse.setIconSize(QSize(16, 16))
        
        # Кнопка Пауза
        pause_glyph = "play" if self.is_paused else "pause"
        self.btn_pause.setIcon(self.ThemeManager.make_icon(pause_glyph, text_color))
        self.btn_pause.setIconSize(QSize(16, 16))
        
        # Кнопка Остановить
        self.btn_stop.setIcon(self.ThemeManager.make_icon("stop", "white"))
        self.btn_stop.setIconSize(QSize(16, 16))
        
        # Кнопка Очистить
        self.btn_clear.setIcon(self.ThemeManager.make_icon("trash", text_color))
        self.btn_clear.setIconSize(QSize(16, 16))

    def _on_media_setting_changed(self, _):
        media_type = self.media_type_combo.currentText()
        self.settings['media_type'] = media_type
        self.settings['format_str'] = self.format_str_combo.currentText()
        self.settings['quality'] = self.quality_combo.currentText()
        
        # Разрешаем выбор качества только для видео или авто
        is_video_or_auto = media_type in ['video', 'auto']
        self.quality_combo.setEnabled(is_video_or_auto)
        
        self.save_settings()
            
    def update_network_settings(self):
        if not hasattr(self, 'spin_tasks'):
            return
            
        tasks = self.spin_tasks.value()
        delay = self.spin_delay.value()
        
        self.settings['max_tasks'] = tasks
        self.settings['rate_limit_delay'] = delay
        self.save_settings()
        
        current_threads = len([t for t in getattr(self, 'worker_threads', []) if t.is_alive()])
        if tasks > current_threads:
            if not hasattr(self, 'worker_threads'):
                self.worker_threads = []
            for _ in range(tasks - current_threads):
                t = threading.Thread(target=self._worker_thread, daemon=True)
                t.start()
                self.worker_threads.append(t)
        
        self.lbl_network_load.setText(f"Нагрузка: {tasks} задач одновременно")
        self.lbl_network_load.setStyleSheet("color: #22c55e; font-weight: bold;")
            
        with self.worker_cond:
            self.worker_cond.notify_all()

    def apply_theme(self, theme_name):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return
            
        if theme_name == 'Темная':
            self.ThemeManager.apply_modern_dark(app)
        elif theme_name == 'Светлая':
            self.ThemeManager.apply_modern_light(app)
        elif theme_name == 'Системная':
            self.ThemeManager.apply_system_theme(app)
            
        self.settings['theme'] = theme_name
        self.save_settings()
        
        if hasattr(self, 'btn_download'):
            self.update_button_icons()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        colors = self.ThemeManager.colors()
        text_color = colors.get("text", "#DBDEE1")
        if self.is_paused:
            self.btn_pause.setText("Продолжить")
            self.btn_pause.setIcon(self.ThemeManager.make_icon("play", text_color))
            with self.download_lock:
                for d in self.active_downloaders.values():
                    d.pause()
            self.lbl_status.setText("Загрузка приостановлена")
        else:
            self.btn_pause.setText("Пауза")
            self.btn_pause.setIcon(self.ThemeManager.make_icon("pause", text_color))
            with self.download_lock:
                for d in self.active_downloaders.values():
                    d.resume()
            self.lbl_status.setText("Загрузка возобновлена")

    def stop_all_downloads(self):
        # 1. Очистить очередь ожидания
        with self.download_lock:
            self.is_stopped = True
            while not self.download_queue.empty():
                try:
                    item = self.download_queue.get_nowait()
                    # Меняем статус в UI для ожидающих
                    task_id = item['task_id']
                    if task_id in self.task_items:
                        tree_item = self.task_items[task_id]
                        tree_item.setText(1, "Отменено")
                        tree_item.setToolTip(1, "Загрузка отменена пользователем")
                    self.download_queue.task_done()
                except Exception:
                    break
                    
        # 2. Отменить активные загрузки
        with self.download_lock:
            for d in self.active_downloaders.values():
                d.cancel()
        
        # 3. Снять паузу, если была (чтобы потоки могли завершиться)
        if self.is_paused:
            self.toggle_pause()
            
        self.lbl_status.setText("Загрузка отменена. Потоки скоро завершатся.")

    def closeEvent(self, event):
        """Корректное завершение при закрытии окна: отменяем активные загрузки
        и снимаем паузу, чтобы их потоки успели закрыть сессии и удалить
        временные папки (а не были убиты резко вместе с процессом)."""
        self.is_stopped = True
        with self.download_lock:
            # Очистить очередь ожидания
            while not self.download_queue.empty():
                try:
                    self.download_queue.get_nowait()
                    self.download_queue.task_done()
                except Exception:
                    break
            # Отменить активные загрузки и снять паузу
            for d in self.active_downloaders.values():
                d.cancel()
                d.resume()
        super().closeEvent(event)

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", self.output_dir_entry.text())
        if folder:
            self.output_dir_entry.setText(folder)
            self.output_dir_entry.setCursorPosition(len(folder))
            self.output_dir_entry.setToolTip(folder)
            self.settings['output_dir'] = folder
            self.save_settings()

    def clear_completed(self):
        """Удалить завершенные или ошибочные элементы из списка"""
        root = self.tree.invisibleRootItem()
        for i in reversed(range(root.childCount())):
            item = root.child(i)
            status = item.text(1)
            if status not in ["Ожидание...", "Скачивается..."]:
                root.removeChild(item)
                # Cleanup task_items и task_data_map
                for k, v in list(self.task_items.items()):
                    if v == item:
                        del self.task_items[k]
                        self.task_data_map.pop(k, None)

    def keyPressEvent(self, event):
        """Поддержка удаления по кнопке Delete/Backspace"""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.tree.selectedItems():
                status = item.text(1)
                if status not in ["Ожидание...", "Скачивается..."]:
                    self.tree.invisibleRootItem().removeChild(item)
                    for k, v in list(self.task_items.items()):
                        if v == item:
                            del self.task_items[k]
                            self.task_data_map.pop(k, None)
        else:
            super().keyPressEvent(event)

    def add_to_queue(self):
        text = self.url_entry.toPlainText()
        self.is_stopped = False
        if not text.strip():
            return
            
        # Ищем все ссылки в тексте (пропуская обычный текст)
        urls = re.findall(r'(https?://[^\s<>"]+|www\.[^\s<>"]+)', text)
        
        if not urls:
            QMessageBox.warning(self, "Ошибка ввода", "Не найдено ни одной ссылки в тексте.")
            return
            
        self.url_entry.clear()
        
        # Сохраняем текущие настройки
        self.settings['media_type'] = self.media_type_combo.currentText()
        self.settings['format_str'] = self.format_str_combo.currentText()
        self.settings['quality'] = self.quality_combo.currentText()
        self.settings['output_dir'] = self.output_dir_entry.text()
        self.save_settings()
        
        for url in urls:
            if url.startswith('www.'):
                url = 'http://' + url
                
            task_id = str(uuid.uuid4())
            item = QTreeWidgetItem(self.tree)
            item.setText(0, url)
            item.setText(1, "Ожидание...")
            item.setToolTip(1, "Ожидает начала загрузки")
            item.setText(2, "0%")
            self.task_items[task_id] = item
            
            task_data = {
                'task_id': task_id,
                'url': url,
                'media_type': self.settings['media_type'],
                'format_str': self.settings['format_str'],
                'quality': self.settings.get('quality', 'лучшее'),
                'output_dir': self.settings['output_dir']
            }
            self.task_data_map[task_id] = task_data
            self.download_queue.put(task_data)
            
        with self.worker_cond:
            self.worker_cond.notify_all()
            
        self.update_queue_count()

    # --- Слоты для обновления UI из фонового потока ---
    
    def update_status(self, task_id, status_text):
        item = self.task_items.get(task_id)
        if item:
            if "ошибка" in status_text.lower():
                item.setText(1, "Ошибка")
            else:
                item.setText(1, status_text)
            item.setToolTip(1, status_text)
            self.update_queue_count()
            
    def update_progress(self, task_id, text, percent_str):
        item = self.task_items.get(task_id)
        if item:
            item.setText(1, "Скачивается...")
            item.setToolTip(1, text)
            item.setText(2, percent_str)

    def download_finished(self, task_id, success, msg):
        item = self.task_items.get(task_id)
        if item:
            if success and msg.startswith("PARTIAL:"):
                frac = msg.split(":", 1)[1]
                item.setText(1, "Частично")
                item.setToolTip(1, f"Загружены не все страницы ({frac})")
                item.setText(2, "100%")
            elif success:
                item.setText(1, "Завершено")
                item.setToolTip(1, "Загрузка успешно завершена")
                item.setText(2, "100%")
            else:
                item.setText(1, "Ошибка")
                item.setToolTip(1, f"Ошибка: {msg}")
                item.setText(2, "0%")
        self.update_queue_count()
                
    def all_downloads_done(self):
        self.update_queue_count()

    def update_queue_count(self):
        total = self.tree.topLevelItemCount()
        self.lbl_queue_title.setText(f"Очередь ({total})")
        
        completed = 0
        active = 0
        for i in range(total):
            item = self.tree.topLevelItem(i)
            status = item.text(1)
            if status in ["Завершено", "Отменено", "Ошибка", "Частично"]:
                completed += 1
            elif status not in ["Ожидание..."]:
                active += 1
                
        if total == 0:
            self.lbl_status.setText("Готов к работе")
            self.progress_bar.setValue(0)
            self.progress_bar.setToolTip("")
        else:
            if completed == total:
                self.lbl_status.setText("Все загрузки завершены")
                self.progress_bar.setValue(100)
            else:
                self.lbl_status.setText(f"Скачивается {active} из {total} (Выполнено: {completed})")
                self.progress_bar.setValue(int(completed / total * 100))
            self.progress_bar.setToolTip(f"{completed} / {total}")
            
    def show_help(self):
        help_text = """
<h3>Как пользоваться?</h3>
<ol>
<li>Вставьте одну или несколько ссылок (по одной на строку) в поле ввода.</li>
<li>Укажите нужный <b>тип медиа</b> (auto, video, audio или gallery) и желаемый <b>формат/качество</b>.</li>
<li>Нажмите <b>Скачать</b>. Программа автоматически загрузит медиа-файлы с помощью yt-dlp или gallery-dl.</li>
</ol>
<h3>Частые ошибки:</h3>
<ul>
<li><b>Сайт не поддерживается:</b> Убедитесь, что сайт поддерживается библиотеками yt-dlp или gallery-dl.</li>
<li><b>Connection timeout / Ошибка сети:</b> Сайт заблокирован или недоступен. Попробуйте использовать VPN.</li>
<li><b>Ошибка авторизации / Защита:</b> Некоторые сайты требуют авторизации или защищены Cloudflare, которую программа не может обойти автоматически.</li>
</ul>
        """
        QMessageBox.information(self, "Помощь и решения проблем", help_text)
        
    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item:
            # Найти task_id для этого QTreeWidgetItem
            task_id = None
            for k, v in self.task_items.items():
                if v == item:
                    task_id = k
                    break
            
            if not task_id:
                return
                
            status = item.text(1)
            task_data = self.task_data_map.get(task_id)
            file_path = task_data.get('file_path') if task_data else None
            
            menu = QMenu()

            
            # Для завершенных файлов
            if status in ["Завершено", "Частично"] and file_path and os.path.exists(file_path):
                action_open_file = menu.addAction("Открыть файл")
                action_show_folder = menu.addAction("Показать в папке")
                menu.addSeparator()
            else:
                action_open_file = None
                action_show_folder = None
            
            # Для активных / ожидающих
            if status in ["Ожидание...", "Скачивается..."]:
                action_cancel = menu.addAction("Отменить загрузку")
                menu.addSeparator()
            else:
                action_cancel = None
                
            action_open = menu.addAction("Открыть ссылку в браузере")
            
            # Для завершенных, ошибочных или отмененных
            if status not in ["Ожидание...", "Скачивается..."]:
                action_delete = menu.addAction("Удалить из списка")
            else:
                action_delete = None
                
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            
            if action == action_open:
                QDesktopServices.openUrl(QUrl(item.text(0)))
            elif status in ["Завершено", "Частично"] and file_path and os.path.exists(file_path):
                if action == action_open_file:
                    self.open_file(file_path)
                elif action == action_show_folder:
                    self.show_in_folder(file_path)
            elif status in ["Ожидание...", "Скачивается..."] and action == action_cancel:
                self.cancel_task(task_id)
                
            if action_delete and action == action_delete:
                self.tree.invisibleRootItem().removeChild(item)
                self.task_items.pop(task_id, None)
                self.task_data_map.pop(task_id, None)
                self.update_queue_count()

    def cancel_task(self, task_id):
        """Отменить конкретную задачу"""
        with self.download_lock:
            self.cancelled_tasks.add(task_id)
            if task_id in self.active_downloaders:
                self.active_downloaders[task_id].cancel()
            
            # Обновить UI
            item = self.task_items.get(task_id)
            if item:
                status = item.text(1)
                if status == "Ожидание...":
                    item.setText(1, "Отменено")
                    item.setToolTip(1, "Загрузка отменена пользователем")
                    item.setText(2, "0%")
                elif status == "Скачивается...":
                    item.setText(1, "Отмена...")
                    item.setToolTip(1, "Отмена загрузки...")
                    
        self.lbl_status.setText("Запрос на отмену задачи отправлен")

    def show_in_folder(self, file_path):
        """Открыть папку и выделить файл в системном проводнике"""
        if not file_path:
            return
        
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)], shell=True)
                return
            elif system == "Darwin":
                subprocess.run(['open', '-R', file_path])
                return
        except Exception as e:
            print(f"Ошибка выделения файла в проводнике: {e}")
            
        # Резервный кроссплатформенный вариант: просто открыть папку
        folder = os.path.dirname(file_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def open_file(self, file_path):
        """Открыть файл в системном просмотрщике по умолчанию"""
        if not file_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    # --- Фоновый поток ---
    
    def _worker_thread(self):
        """Фоновый поток для обработки очереди скачивания (работает постоянно)"""
        while True:
            with self.worker_cond:
                while self.active_downloads >= self.settings.get('max_tasks', 3) or self.download_queue.empty():
                    self.worker_cond.wait()
                
                try:
                    task = self.download_queue.get_nowait()
                    self.active_downloads += 1
                except queue.Empty:
                    continue
                
            task_id = task['task_id']
            url = task['url']
            
            # Проверяем, не была ли задача отменена или остановлена
            with self.download_lock:
                if task_id in self.cancelled_tasks or self.is_stopped:
                    self.signals.finished.emit(task_id, False, "Отменено пользователем")
                    with self.worker_cond:
                        self.active_downloads -= 1
                        self.worker_cond.notify_all()
                    self.download_queue.task_done()
                    continue

            downloader = None

            try:
                self.signals.status.emit(task_id, "Скачивается...")

                def progress_callback(percent, total, text):
                    self.signals.progress.emit(task_id, text, f"{percent}%")

                os.makedirs(task['output_dir'], exist_ok=True)

                from core.downloader import UniversalMediaDownloader
                downloader = UniversalMediaDownloader()

                with self.download_lock:
                    self.active_downloaders[task_id] = downloader
                    if self.is_paused:
                        downloader.pause()

                result = downloader.download_media(
                    url=url,
                    output_dir=task['output_dir'],
                    media_type=task['media_type'],
                    format_str=task['format_str'],
                    quality=task.get('quality', 'лучшее'),
                    progress_callback=progress_callback
                )

                if result:
                    file_path = result.get('file_path')
                    if file_path:
                        with self.download_lock:
                            if task_id in self.task_data_map:
                                self.task_data_map[task_id]['file_path'] = file_path
                    self.signals.finished.emit(task_id, True, "")
                else:
                    self.signals.finished.emit(task_id, False, "Ошибка неизвестна")
            except Exception as e:
                # Любой непредвиденный сбой не должен «убивать» поток-воркер
                self.signals.finished.emit(task_id, False, str(e))
            finally:
                if downloader is not None:
                    downloader.close()
                    with self.download_lock:
                        self.active_downloaders.pop(task_id, None)
                
                # Удаляем из списка отмененных
                with self.download_lock:
                    self.cancelled_tasks.discard(task_id)

                with self.worker_cond:
                    self.active_downloads -= 1
                    self.worker_cond.notify_all()
                    if self.active_downloads == 0 and self.download_queue.empty():
                        self.signals.all_done.emit()
                self.download_queue.task_done()


