#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расширенное окно настроек приложения ДИАЛОГ.
Содержит вкладки: Основные, Аудио, Видео, Горячие клавиши, Сеть.
"""

import logging
import cv2
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QListWidget, QListWidgetItem, QStackedWidget,
                             QPushButton, QDialogButtonBox, QLabel,
                             QGroupBox, QComboBox, QMessageBox,
                             QCheckBox, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings
from PyQt5.QtGui import QImage, QPixmap
import sounddevice as sd
import numpy as np

logger = logging.getLogger('dialog_gui')


class GeneralSettingsPage(QWidget):
    """Вкладка основных настроек (заглушка)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Основные настройки приложения"))
        layout.addWidget(QLabel("Здесь будут общие параметры"))
        layout.addStretch()


class AudioSettingsPage(QWidget):
    """
    Вкладка настроек аудио.
    Позволяет выбирать устройства ввода/вывода и тестировать их.
    """
    audio_settings_changed = pyqtSignal(dict)

    def __init__(self, current_input=None, current_output=None, parent=None):
        super().__init__(parent)
        self.input_device = current_input
        self.output_device = current_output
        self.audio_system_type = "Unknown"
        self.init_ui()
        self.detect_audio_system()
        self.populate_audio_devices()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Аудио устройства ---
        audio_group = QGroupBox("Аудио устройства")
        audio_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        audio_layout = QVBoxLayout(audio_group)

        self.audio_system_label = QLabel("Определение звуковой системы...")
        self.audio_system_label.setAlignment(Qt.AlignCenter)
        self.audio_system_label.setWordWrap(True)
        self.audio_system_label.setStyleSheet("font-size: 12px; color: #7f8c8d; font-style: italic;")
        audio_layout.addWidget(self.audio_system_label)

        # Микрофон
        mic_layout = QHBoxLayout()
        mic_layout.addWidget(QLabel("Микрофон:"))
        self.input_device_combo = QComboBox()
        self.input_device_combo.setMinimumWidth(250)
        mic_layout.addWidget(self.input_device_combo)
        audio_layout.addLayout(mic_layout)

        # Динамики
        spk_layout = QHBoxLayout()
        spk_layout.addWidget(QLabel("Динамики:"))
        self.output_device_combo = QComboBox()
        self.output_device_combo.setMinimumWidth(250)
        spk_layout.addWidget(self.output_device_combo)
        audio_layout.addLayout(spk_layout)

        self.apply_audio_button = QPushButton("Применить устройства")
        self.apply_audio_button.clicked.connect(self.apply_audio_devices)
        audio_layout.addWidget(self.apply_audio_button)

        layout.addWidget(audio_group)

        # --- Тестирование ---
        test_group = QGroupBox("Тестирование")
        test_layout = QVBoxLayout(test_group)

        self.test_status_label = QLabel("Нажмите кнопку для проверки")
        self.test_status_label.setAlignment(Qt.AlignCenter)
        test_layout.addWidget(self.test_status_label)

        btn_row1 = QHBoxLayout()
        self.test_tones_btn = QPushButton("🔔 Гудок")
        self.test_tones_btn.clicked.connect(self.test_call_tones)
        btn_row1.addWidget(self.test_tones_btn)

        self.test_playback_btn = QPushButton("▶️ Воспроизведение")
        self.test_playback_btn.clicked.connect(self.test_audio_playback)
        btn_row1.addWidget(self.test_playback_btn)
        test_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.test_record_btn = QPushButton("🎤 Запись")
        self.test_record_btn.clicked.connect(self.test_audio_recording)
        btn_row2.addWidget(self.test_record_btn)

        self.test_loopback_btn = QPushButton("🔄 Петля")
        self.test_loopback_btn.clicked.connect(self.test_audio_loopback)
        btn_row2.addWidget(self.test_loopback_btn)
        test_layout.addLayout(btn_row2)

        self.full_diagnostic_btn = QPushButton("🔍 Полная диагностика")
        self.full_diagnostic_btn.clicked.connect(self.run_audio_diagnostic)
        test_layout.addWidget(self.full_diagnostic_btn)

        layout.addWidget(test_group)
        layout.addStretch()

    # ---- Вспомогательные методы для аудио ----
    def detect_audio_system(self):
        try:
            devices = sd.query_devices()
            system = "Unknown"
            for d in devices:
                name_lower = d['name'].lower()
                if 'pipewire' in name_lower:
                    system = "PipeWire"
                    break
                elif 'pulse' in name_lower:
                    system = "PulseAudio"
                    break
                elif 'alsa' in name_lower:
                    system = "ALSA"
                    break
            self.audio_system_type = system
            self.audio_system_label.setText(f"Система: {system} | Устройств: {len(devices)}")
        except Exception as e:
            logger.error(f"Ошибка определения аудиосистемы: {e}")
            self.audio_system_label.setText("Не удалось определить аудиосистему")

    def populate_audio_devices(self):
        try:
            devices = sd.query_devices()
            self.input_device_combo.clear()
            self.output_device_combo.clear()
            self.input_device_combo.addItem("Автовыбор (по умолчанию)", -1)
            self.output_device_combo.addItem("Автовыбор (по умолчанию)", -1)
            for i, dev in enumerate(devices):
                name = f"{i}: {dev['name']}"
                if len(name) > 60:
                    name = name[:57] + "..."
                if dev['max_input_channels'] > 0:
                    self.input_device_combo.addItem(name, i)
                if dev['max_output_channels'] > 0:
                    self.output_device_combo.addItem(name, i)
            self._set_combo_to_device(self.input_device_combo, self.input_device)
            self._set_combo_to_device(self.output_device_combo, self.output_device)
        except Exception as e:
            logger.error(f"Ошибка заполнения списка устройств: {e}")

    def _set_combo_to_device(self, combo, device_index):
        if device_index is not None:
            idx = combo.findData(device_index)
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(0)

    def apply_audio_devices(self):
        input_idx = self.input_device_combo.currentData()
        output_idx = self.output_device_combo.currentData()
        new_input = input_idx if input_idx != -1 else None
        new_output = output_idx if output_idx != -1 else None
        if new_input != self.input_device or new_output != self.output_device:
            self.input_device = new_input
            self.output_device = new_output
            settings = {'input_device': self.input_device, 'output_device': self.output_device}
            self.audio_settings_changed.emit(settings)
            logger.info(f"Настройки аудио изменены: ввод={self.input_device}, вывод={self.output_device}")
            QMessageBox.information(self, "Успех", "Настройки аудио применены.")
            self.populate_audio_devices()
        else:
            QMessageBox.information(self, "Информация", "Настройки не изменились.")

    # ---- Тесты (скопированы из предыдущей версии) ----
    def test_audio_playback(self):
        try:
            test_device = self.output_device
            if test_device is None:
                test_device = sd.default.device[1] if sd.default.device else 0
            duration = 2.0
            frequency = 440
            sr = 44100
            t = np.linspace(0, duration, int(sr * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * frequency * t)
            self.test_status_label.setText("🔊 Воспроизведение...")
            sd.play(tone, sr, device=test_device)
            sd.wait()
            self.test_status_label.setText("✅ Воспроизведение успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка теста воспроизведения: {e}")
            self.test_status_label.setText("❌ Ошибка воспроизведения")
            QMessageBox.warning(self, "Ошибка", f"Не удалось воспроизвести звук:\n{e}")
            return False

    def test_audio_recording(self):
        try:
            test_device = self.input_device
            if test_device is None:
                test_device = sd.default.device[0] if sd.default.device else 0
            duration = 2.0
            sr = 44100
            self.test_status_label.setText("🎤 Запись...")
            recording = sd.rec(int(duration * sr), samplerate=sr, channels=1,
                               device=test_device, dtype='float32')
            sd.wait()
            max_amp = np.max(np.abs(recording))
            if max_amp < 0.01:
                self.test_status_label.setText("⚠️ Запись выполнена, но сигнал тихий")
                QMessageBox.warning(self, "Результат", "Уровень сигнала низкий.")
            else:
                self.test_status_label.setText("✅ Запись успешна")
                QMessageBox.information(self, "Результат", f"Запись OK, амплитуда {max_amp:.3f}")
            return True
        except Exception as e:
            logger.error(f"Ошибка теста записи: {e}")
            self.test_status_label.setText("❌ Ошибка записи")
            QMessageBox.warning(self, "Ошибка", f"Не удалось записать звук:\n{e}")
            return False

    def test_audio_loopback(self):
        try:
            in_dev = self.input_device or sd.default.device[0]
            out_dev = self.output_device or sd.default.device[1]
            duration = 3.0
            sr = 44100
            self.test_status_label.setText("🔄 Петля (запись→воспроизведение)...")
            recording = sd.rec(int(duration * sr), samplerate=sr, channels=1,
                               device=in_dev, dtype='float32')
            sd.wait()
            sd.play(recording, samplerate=sr, device=out_dev)
            sd.wait()
            self.test_status_label.setText("✅ Петля выполнена")
            return True
        except Exception as e:
            logger.error(f"Ошибка теста петли: {e}")
            self.test_status_label.setText("❌ Ошибка петли")
            QMessageBox.warning(self, "Ошибка", f"Тест петли не удался:\n{e}")
            return False

    def test_call_tones(self):
        try:
            test_device = self.output_device or sd.default.device[1] or 0
            duration = 1.0
            frequency = 440
            sr = 44100
            t = np.linspace(0, duration, int(sr * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * frequency * t)
            self.test_status_label.setText("🔔 Гудок...")
            sd.play(tone, sr, device=test_device)
            sd.wait()
            self.test_status_label.setText("✅ Гудок воспроизведён")
            return True
        except Exception as e:
            logger.error(f"Ошибка теста гудка: {e}")
            self.test_status_label.setText("❌ Ошибка гудка")
            QMessageBox.warning(self, "Ошибка", f"Не удалось воспроизвести гудок:\n{e}")
            return False

    def run_audio_diagnostic(self):
        self.test_status_label.setText("🔍 Запуск диагностики...")
        playback_ok = self.test_audio_playback()
        if playback_ok:
            record_ok = self.test_audio_recording()
            if record_ok:
                loop_ok = self.test_audio_loopback()
                if loop_ok:
                    self.test_status_label.setText("✅ Полная диагностика пройдена")
                    QMessageBox.information(self, "Диагностика", "Все тесты пройдены.")
                else:
                    self.test_status_label.setText("⚠️ Диагностика: запись/воспроизведение работают, петля нет")
            else:
                self.test_status_label.setText("⚠️ Диагностика: воспроизведение работает, запись нет")
        else:
            self.test_status_label.setText("❌ Диагностика не пройдена")


class VideoSettingsPage(QWidget):
    """Вкладка настроек видео с предпросмотром"""
    video_settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera_index = 0
        self.resolution = (640, 480)
        self.fps = 30
        self.quality = 85
        self.color_enhancement = True
        self.preview_active = False
        self.capture_thread = None
        self.video_processor = None
        self.available_cameras = []

        self.init_ui()
        self.detect_cameras()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Группа выбора камеры
        cam_group = QGroupBox("Камера")
        cam_layout = QVBoxLayout()
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self.on_camera_changed)
        cam_layout.addWidget(self.camera_combo)
        cam_group.setLayout(cam_layout)
        layout.addWidget(cam_group)

        # Группа настроек качества
        quality_group = QGroupBox("Настройки качества")
        form_layout = QFormLayout()

        self.resolution_combo = QComboBox()
        resolutions = [
            ("160x120", 160, 120),
            ("320x240", 320, 240),
            ("640x480", 640, 480)           
        ]
        for name, w, h in resolutions:
            self.resolution_combo.addItem(name, (w, h))
        form_layout.addRow("Разрешение:", self.resolution_combo)

        self.fps_combo = QComboBox()
        fps_options = [(f"{f} FPS", f) for f in [5, 10, 15, 30]]
        for name, f in fps_options:
            self.fps_combo.addItem(name, f)
        form_layout.addRow("Частота кадров:", self.fps_combo)

        self.quality_combo = QComboBox()
        qualities = [
            ("Низкое (40)", 40),
            ("Среднее (60)", 60),
            ("Высокое (75)", 75),
            ("Оригинальное (85)", 85)
        ]
        for name, q in qualities:
            self.quality_combo.addItem(name, q)
        form_layout.addRow("Качество JPEG:", self.quality_combo)

        self.color_enhance_check = QCheckBox("Улучшение цветов")
        self.color_enhance_check.setChecked(True)
        form_layout.addRow(self.color_enhance_check)

        quality_group.setLayout(form_layout)
        layout.addWidget(quality_group)

        # Группа предпросмотра
        preview_group = QGroupBox("Предпросмотр видео")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(320, 240)
        self.preview_label.setStyleSheet("background-color: black;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("Камера не выбрана")
        preview_layout.addWidget(self.preview_label)

        btn_layout = QHBoxLayout()
        self.start_preview_btn = QPushButton("▶️ Запустить предпросмотр")
        self.start_preview_btn.clicked.connect(self.start_preview)
        self.stop_preview_btn = QPushButton("⏹️ Остановить предпросмотр")
        self.stop_preview_btn.clicked.connect(self.stop_preview)
        self.stop_preview_btn.setEnabled(False)
        btn_layout.addWidget(self.start_preview_btn)
        btn_layout.addWidget(self.stop_preview_btn)
        preview_layout.addLayout(btn_layout)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Кнопка применения
        self.apply_btn = QPushButton("Применить")
        self.apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(self.apply_btn)

        layout.addStretch()

        # Подключаем сигналы изменения настроек для динамического обновления предпросмотра
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        self.fps_combo.currentIndexChanged.connect(self.on_fps_changed)
        self.quality_combo.currentIndexChanged.connect(self.on_quality_changed)
        self.color_enhance_check.stateChanged.connect(self.on_color_enhance_changed)

    def detect_cameras(self):
        """Обнаружение доступных камер"""
        self.available_cameras = []
        for i in range(4):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        self.available_cameras.append(i)
                    cap.release()
            except:
                pass
        self.camera_combo.clear()
        if self.available_cameras:
            for idx in self.available_cameras:
                self.camera_combo.addItem(f"Камера {idx}", idx)
        else:
            self.camera_combo.addItem("Камеры не найдены", -1)
            self.camera_combo.setEnabled(False)
            self.start_preview_btn.setEnabled(False)

    def load_settings(self):
        settings = QSettings('DialogApp', 'P2PClient')
        self.camera_index = settings.value('video_camera_index', 0, type=int)
        if self.camera_index not in self.available_cameras:
            self.camera_index = self.available_cameras[0] if self.available_cameras else -1
        if self.camera_index != -1:
            idx = self.camera_combo.findData(self.camera_index)
            if idx >= 0:
                self.camera_combo.setCurrentIndex(idx)

        res_w = settings.value('video_resolution_width', 320, type=int)
        res_h = settings.value('video_resolution_height', 240, type=int)
        self.resolution = (res_w, res_h)
        for i in range(self.resolution_combo.count()):
            w, h = self.resolution_combo.itemData(i)
            if w == res_w and h == res_h:
                self.resolution_combo.setCurrentIndex(i)
                break

        self.fps = settings.value('video_fps', 15, type=int)
        for i in range(self.fps_combo.count()):
            if self.fps_combo.itemData(i) == self.fps:
                self.fps_combo.setCurrentIndex(i)
                break

        self.quality = settings.value('video_quality', 60, type=int)
        for i in range(self.quality_combo.count()):
            if self.quality_combo.itemData(i) == self.quality:
                self.quality_combo.setCurrentIndex(i)
                break

        self.color_enhancement = settings.value('video_color_enhancement', True, type=bool)
        self.color_enhance_check.setChecked(self.color_enhancement)

    def save_settings(self):
        settings = QSettings('DialogApp', 'P2PClient')
        settings.setValue('video_camera_index', self.camera_index)
        settings.setValue('video_resolution_width', self.resolution[0])
        settings.setValue('video_resolution_height', self.resolution[1])
        settings.setValue('video_fps', self.fps)
        settings.setValue('video_quality', self.quality)
        settings.setValue('video_color_enhancement', self.color_enhancement)

    def on_camera_changed(self):
        if self.preview_active:
            self.stop_preview()
            self.start_preview()

    def on_resolution_changed(self):
        if self.preview_active:
            self.stop_preview()
            self.start_preview()

    def on_fps_changed(self):
        if self.preview_active:
            self.stop_preview()
            self.start_preview()

    def on_quality_changed(self):
        pass  # Качество влияет только на сжатие, предпросмотр не требует перезапуска

    def on_color_enhance_changed(self):
        self.color_enhancement = self.color_enhance_check.isChecked()

    def start_preview(self):
        if self.preview_active:
            self.stop_preview()

        if self.camera_index == -1:
            self.preview_label.setText("Камера не выбрана")
            return

        try:
            from video_window import VideoCaptureThread, VideoProcessor
        except ImportError:
            from .video_window import VideoCaptureThread, VideoProcessor

        # Получаем текущие настройки
        res_data = self.resolution_combo.currentData()
        if res_data:
            width, height = res_data
        else:
            width, height = 640, 480
        self.resolution = (width, height)

        fps = self.fps_combo.currentData()
        if fps:
            self.fps = fps

        quality = self.quality_combo.currentData()
        if quality:
            self.quality = quality

        self.color_enhancement = self.color_enhance_check.isChecked()

        # Создаём поток захвата
        self.capture_thread = VideoCaptureThread(
            camera_index=self.camera_index,
            width=width,
            height=height,
            fps=fps
        )
        self.video_processor = VideoProcessor()
        self.video_processor.start()

        self.capture_thread.frame_ready.connect(self.on_frame_received)
        self.capture_thread.start()

        self.preview_active = True
        self.start_preview_btn.setEnabled(False)
        self.stop_preview_btn.setEnabled(True)

    def on_frame_received(self, frame):
        """Обработка кадра для предпросмотра"""
        if frame is None:
            return
        if self.color_enhancement:
            self.video_processor.put_frame(frame)
            processed = self.video_processor.get_processed_frame()
            if processed is not None:
                frame = processed
        # Конвертация в QImage и отображение
        if len(frame.shape) == 3:
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
            elif frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
            self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview_label.setText("")

    def stop_preview(self):
        if self.capture_thread:
            self.capture_thread.stop_capture()
            self.capture_thread.wait()
            self.capture_thread = None
        if self.video_processor:
            self.video_processor.stop()
            self.video_processor = None
        self.preview_active = False
        self.preview_label.clear()
        self.preview_label.setText("Предпросмотр остановлен")
        self.start_preview_btn.setEnabled(True)
        self.stop_preview_btn.setEnabled(False)

    def apply_settings(self):
        # Сохраняем настройки из текущих комбобоксов
        self.camera_index = self.camera_combo.currentData()
        if self.camera_index == -1:
            self.camera_index = 0

        res_data = self.resolution_combo.currentData()
        if res_data:
            self.resolution = res_data

        fps = self.fps_combo.currentData()
        if fps:
            self.fps = fps

        quality = self.quality_combo.currentData()
        if quality:
            self.quality = quality

        self.color_enhancement = self.color_enhance_check.isChecked()

        self.save_settings()
        self.video_settings_changed.emit({
            'camera_index': self.camera_index,
            'resolution': self.resolution,
            'fps': self.fps,
            'quality': self.quality,
            'color_enhancement': self.color_enhancement
        })

    def closeEvent(self, event):
        self.stop_preview()
        event.accept()


class HotkeysSettingsPage(QWidget):
    """Вкладка горячих клавиш (заглушка)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Настройки горячих клавиш"))
        layout.addWidget(QLabel("Здесь будут настройки комбинаций клавиш"))
        layout.addStretch()


class NetworkSettingsPage(QWidget):
    """Вкладка сетевых настроек (заглушка)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Сетевые настройки"))
        layout.addWidget(QLabel("Здесь будут настройки P2P сети, прокси и т.д."))
        layout.addStretch()


class SettingsDialog(QDialog):
    """
    Главное диалоговое окно настроек с навигацией по категориям.
    """
    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None, input_device=None, output_device=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки приложения")
        self.setMinimumSize(825, 500)
        self.setMaximumSize(985, 600)
        self.setModal(True)

        self.settings_data = {
            'input_device': input_device,
            'output_device': output_device,
        }

        # Основной layout
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)

        # Левая панель навигации
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(150)
        self.nav_list.setStyleSheet("""
            QListWidget {
                background-color: #f0f0f0;
                border: none;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #ddd;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)
        main_layout.addWidget(self.nav_list)

        # Правая панель (стек страниц)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)

        # Создаём страницы
        self.general_page = GeneralSettingsPage()
        self.audio_page = AudioSettingsPage(
            current_input=self.settings_data['input_device'],
            current_output=self.settings_data['output_device']
        )
        self.video_page = VideoSettingsPage()
        self.hotkeys_page = HotkeysSettingsPage()
        self.network_page = NetworkSettingsPage()

        # Обёртываем каждую страницу в QScrollArea
        from PyQt5.QtWidgets import QScrollArea

        def wrap_with_scroll(widget):
            scroll = QScrollArea()
            scroll.setWidget(widget)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            return scroll



        # Добавляем в стек в правильном порядке (соответствует индексам навигации)
        self.stacked_widget.addWidget(wrap_with_scroll(self.general_page))   # индекс 0
        self.stacked_widget.addWidget(wrap_with_scroll(self.audio_page))     # индекс 1
        self.stacked_widget.addWidget(wrap_with_scroll(self.video_page))     # индекс 2
        self.stacked_widget.addWidget(wrap_with_scroll(self.hotkeys_page))   # индекс 3
        self.stacked_widget.addWidget(wrap_with_scroll(self.network_page))   # индекс 4

        # Добавляем пункты навигации
        items = [
            ("Основные", 0),
            ("Аудио", 1),
            ("Видео", 2),
            ("Горячие клавиши", 3),
            ("Сеть", 4)
        ]
        for text, idx in items:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, idx)
            self.nav_list.addItem(item)

        # Подключаем сигнал смены пункта
        self.nav_list.currentItemChanged.connect(self.on_nav_changed)

        # Кнопки диалога
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()  

        # Создаём кнопки
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Отмена")
        btn_apply = QPushButton("Применить")

        # Задаём размеры кнопок (опционально)
        btn_ok.setFixedWidth(80)
        btn_cancel.setFixedWidth(120)
        btn_apply.setFixedWidth(150)

        # Добавляем кнопки в layout в нужном порядке
        button_layout.addWidget(btn_ok)
        button_layout.addWidget(btn_cancel)
        button_layout.addWidget(btn_apply)

        # Подключаем сигналы
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_apply.clicked.connect(self.apply_settings)

        # Добавляем кнопки внизу (под стеком, на всю ширину)
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.stacked_widget)
        right_layout.addLayout(button_layout)

        # Заменяем правую часть: удаляем старый stacked_widget и добавляем right_layout
        main_layout.removeWidget(self.stacked_widget)
        main_layout.addLayout(right_layout, 1)

        # Подключаем сигналы от страниц
        self.audio_page.audio_settings_changed.connect(self.on_audio_settings_changed)
        self.video_page.video_settings_changed.connect(self.on_video_settings_changed)

        # Выбираем первый пункт
        self.nav_list.setCurrentRow(0)

    def on_nav_changed(self, current, previous):
        """Переключение страницы при выборе пункта навигации"""
        if current is None:
            return
        idx = current.data(Qt.UserRole)
        if idx is not None and idx < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(idx)

    def on_audio_settings_changed(self, settings):
        logger.debug(f"on_audio_settings_changed received: {settings}")
        self.settings_data.update(settings)

    def on_video_settings_changed(self, settings):
        self.settings_data.update(settings)
        logger.debug(f"Видеонастройки обновлены: {settings}")

    def apply_settings(self):
        """Применить все настройки (испускает сигнал)"""
        self.settings_changed.emit(self.settings_data)
        logger.info("Настройки применены")
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def accept(self):
        self.apply_settings()
        super().accept()

    def reject(self):
        super().reject()