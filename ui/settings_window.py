#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расширенное окно настроек приложения ДИАЛОГ.
Содержит вкладки: Основные, Аудио и видео, Горячие клавиши, Сеть и др.
"""

import logging
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QListWidget, QListWidgetItem, QStackedWidget,
                             QPushButton, QDialogButtonBox, QLabel,
                             QGroupBox, QComboBox, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
import sounddevice as sd
import numpy as np

logger = logging.getLogger('dialog_gui')


class GeneralSettingsPage(QWidget):
    """Вкладка основных настроек (пока заглушка)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Основные настройки приложения"))
        layout.addWidget(QLabel("Здесь будут общие параметры"))
        layout.addStretch()


class AudioVideoSettingsPage(QWidget):
    """
    Вкладка настроек аудио и видео.
    Позволяет выбирать устройства ввода/вывода и тестировать их.
    """
    # Сигнал об изменении настроек аудио (для немедленного применения)
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


class SettingsDialog(QDialog):
    """
    Главное диалоговое окно настроек с навигацией по категориям.
    """
    # Сигнал, испускаемый при сохранении всех настроек (при OK/Apply)
    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None, input_device=None, output_device=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки приложения")
        self.setMinimumSize(700, 500)
        self.setModal(True)

        # Данные для страниц (здесь можно хранить все настройки)
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
        self.audio_video_page = AudioVideoSettingsPage(
            current_input=self.settings_data['input_device'],
            current_output=self.settings_data['output_device']
        )

        # Добавляем в стек
        self.stacked_widget.addWidget(self.general_page)
        self.stacked_widget.addWidget(self.audio_video_page)

        # Добавляем пункты навигации
        items = [
            ("Основные", 0),
            ("Аудио и видео", 1),
            ("Горячие клавиши", 2),  # пока без страницы
            ("Сеть", 3)               # пока без страницы
        ]
        for text, idx in items:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, idx)
            self.nav_list.addItem(item)

        # Подключаем сигнал смены пункта
        self.nav_list.currentItemChanged.connect(self.on_nav_changed)

        # Кнопки диалога
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)

        # Добавляем кнопки внизу (под стеком, на всю ширину)
        # Для этого создаём вертикальный layout, в котором стек и кнопки
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.stacked_widget)
        right_layout.addWidget(button_box)

        # Заменяем правую часть: удаляем старый stacked_widget и добавляем right_layout
        main_layout.removeWidget(self.stacked_widget)
        main_layout.addLayout(right_layout, 1)

        # Подключаем сигналы от страницы аудио, чтобы обновлять внутренние данные
        self.audio_video_page.audio_settings_changed.connect(self.on_audio_settings_changed)

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
        """Обновить внутренние данные при изменении настроек аудио"""
        logger.debug(f"on_audio_settings_changed received: {settings}")
        self.settings_data.update(settings)

    def apply_settings(self):
        """Применить все настройки (испускает сигнал)"""
        # Собираем все настройки со страниц
        # Пока только аудио, но можно добавить и другие
        print(f"DEBUG: apply_settings отправляет: {self.settings_data}")
        self.settings_changed.emit(self.settings_data)
        logger.info("Настройки применены")
        # Можно показать уведомление
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def accept(self):
        """При OK: применяем и закрываем"""
        self.apply_settings()
        super().accept()

    def reject(self):
        """При Cancel: просто закрываем без сохранения"""
        super().reject()