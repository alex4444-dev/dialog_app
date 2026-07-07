#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расширенное окно настроек приложения ДИАЛОГ.
Содержит вкладки: Основные, Аудио, Видео, Горячие клавиши, Сеть.
"""

import sys
import os
import logging
import cv2
import yaml
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                             QListWidget, QListWidgetItem, QStackedWidget,
                             QPushButton, QDialogButtonBox, QLabel,
                             QGroupBox, QComboBox, QMessageBox,
                             QCheckBox, QFormLayout, QLineEdit, QSpinBox, QFileDialog, QTableWidget, QTableWidgetItem,
                             QKeySequenceEdit, QHeaderView, QSizePolicy, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QStandardPaths
from PyQt5.QtGui import QImage, QPixmap, QKeySequence
import sounddevice as sd
import numpy as np


# Добавляем путь к текущей директории для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    

# Импортируем стили
try:
    from ui.dialogs import show_question_dialog
    from styles.main_style import MAIN_WINDOW_STYLE
except ImportError as e:
    print(f"Ошибка импорта стилей: {e}")
    MAIN_WINDOW_STYLE = ""

logger = logging.getLogger('dialog_gui')


class GeneralSettingsPage(QWidget):
    """Вкладка основных настроек: звуки, файлы, общие параметры"""
    nickname_changed = pyqtSignal(str)

    def __init__(self, parent=None, current_nickname=None):
        super().__init__(parent)
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.current_nickname = current_nickname or ""
        self.main_window = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        user_group = QGroupBox("Пользователь")
        user_layout = QVBoxLayout(user_group)
        row_nick = QHBoxLayout()
        row_nick.addWidget(QLabel("Псевдоним (ник):"))
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setText(self.current_nickname)
        self.nickname_edit.setPlaceholderText("Введите новый псевдоним")
        row_nick.addWidget(self.nickname_edit)
        self.apply_nick_btn = QPushButton("Применить")
        self.apply_nick_btn.clicked.connect(self.apply_nickname)
        row_nick.addWidget(self.apply_nick_btn)
        user_layout.addLayout(row_nick)
        layout.addWidget(user_group)

        autostart_group = QGroupBox("Автозагрузка")
        autostart_layout = QVBoxLayout(autostart_group)
        self.autostart_check = QCheckBox("Запускать программу при старте системы")
        self.autostart_check.setChecked(self.is_autostart_enabled())
        self.autostart_check.toggled.connect(self.toggle_autostart)
        autostart_layout.addWidget(self.autostart_check)
        layout.addWidget(autostart_group)

        files_group = QGroupBox("Файлы")
        files_layout = QVBoxLayout(files_group)
        row_folder = QHBoxLayout()
        row_folder.addWidget(QLabel("Папка для сохранения:"))
        self.download_path = QLineEdit()
        default_download = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        self.download_path.setText(self.settings.value('download_folder', default_download, type=str))
        self.download_path.setReadOnly(True)
        row_folder.addWidget(self.download_path)
        btn_folder = QPushButton("Изменить...")
        btn_folder.clicked.connect(self.browse_download_folder)
        row_folder.addWidget(btn_folder)
        files_layout.addLayout(row_folder)

        self.max_file_size = QSpinBox()
        self.max_file_size.setRange(1, 1024)
        self.max_file_size.setValue(self.settings.value('max_file_size_mb', 500, type=int))
        self.max_file_size.setSuffix(" МБ")
        files_layout.addWidget(QLabel("Максимальный размер файла:"))
        files_layout.addWidget(self.max_file_size)

        layout.addWidget(files_group)
        layout.addStretch()

        sound_group = QGroupBox("Звуковые уведомления")
        sound_layout = QVBoxLayout(sound_group)

        self.enable_sounds_check = QCheckBox("Включить звуки")
        self.enable_sounds_check.setChecked(self.settings.value('sounds_enabled', True, type=bool))
        sound_layout.addWidget(self.enable_sounds_check)

        row_in = QHBoxLayout()
        row_in.addWidget(QLabel("Входящий звонок:"))
        self.incoming_call_path = QLineEdit()
        self.incoming_call_path.setText(self.settings.value('sound_incoming_call', 'sounds/incoming_call.wav', type=str))
        self.incoming_call_path.setReadOnly(True)
        row_in.addWidget(self.incoming_call_path)
        btn_in = QPushButton("Обзор...")
        btn_in.clicked.connect(lambda: self.browse_sound('incoming_call'))
        row_in.addWidget(btn_in)
        sound_layout.addLayout(row_in)

        row_out = QHBoxLayout()
        row_out.addWidget(QLabel("Исходящий звонок:"))
        self.outgoing_call_path = QLineEdit()
        self.outgoing_call_path.setText(self.settings.value('sound_outgoing_call', 'sounds/outgoing_call.wav', type=str))
        self.outgoing_call_path.setReadOnly(True)
        row_out.addWidget(self.outgoing_call_path)
        btn_out = QPushButton("Обзор...")
        btn_out.clicked.connect(lambda: self.browse_sound('outgoing_call'))
        row_out.addWidget(btn_out)
        sound_layout.addLayout(row_out)

        row_msg = QHBoxLayout()
        row_msg.addWidget(QLabel("Новое сообщение:"))
        self.message_path = QLineEdit()
        self.message_path.setText(self.settings.value('sound_message', 'sounds/message.wav', type=str))
        self.message_path.setReadOnly(True)
        row_msg.addWidget(self.message_path)
        btn_msg = QPushButton("Обзор...")
        btn_msg.clicked.connect(lambda: self.browse_sound('message'))
        row_msg.addWidget(btn_msg)
        sound_layout.addLayout(row_msg)

        row_file_snd = QHBoxLayout()
        row_file_snd.addWidget(QLabel("Файл получен:"))
        self.file_received_path = QLineEdit()
        self.file_received_path.setText(self.settings.value('sound_file_received', 'sounds/file_received.wav', type=str))
        self.file_received_path.setReadOnly(True)
        row_file_snd.addWidget(self.file_received_path)
        btn_file_snd = QPushButton("Обзор...")
        btn_file_snd.clicked.connect(lambda: self.browse_sound('file_received'))
        row_file_snd.addWidget(btn_file_snd)
        sound_layout.addLayout(row_file_snd)

        layout.addWidget(sound_group)

        blacklist_group = QGroupBox("🚫 Чёрный список")
        blacklist_layout = QVBoxLayout(blacklist_group)
        self.manage_blacklist_btn = QPushButton("📋 Управление чёрным списком")
        self.manage_blacklist_btn.clicked.connect(self.open_blacklist_dialog)
        blacklist_layout.addWidget(self.manage_blacklist_btn)
        blacklist_group.setLayout(blacklist_layout)
        layout.addWidget(blacklist_group)

    # ---------- Методы ----------
    def apply_nickname(self):
        new_nick = self.nickname_edit.text().strip()
        if not new_nick:
            QMessageBox.warning(self, "Ошибка", "Псевдоним не может быть пустым")
            return
        if new_nick == self.current_nickname:
            return
        self.settings.setValue('nickname', new_nick)
        self.current_nickname = new_nick
        self.nickname_changed.emit(new_nick)
        QMessageBox.information(self, "Успех", f"Псевдоним изменён на {new_nick}")

    def is_autostart_enabled(self):
        if sys.platform == 'win32':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                return False
        elif sys.platform == 'darwin':
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.dialogapp.plist")
            return os.path.exists(plist_path)
        else:
            desktop_path = os.path.expanduser("~/.config/autostart/dialogapp.desktop")
            return os.path.exists(desktop_path)

    def toggle_autostart(self, enabled):
        if enabled:
            self._enable_autostart()
        else:
            self._disable_autostart()

    def _enable_autostart(self):
        app_path = os.path.abspath(sys.argv[0])
        if sys.platform == 'win32':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "DialogApp", 0, winreg.REG_SZ, app_path)
            winreg.CloseKey(key)
        elif sys.platform == 'darwin':
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>Label</key>
                <string>com.dialogapp</string>
                <key>ProgramArguments</key>
                <array>
                    <string>{app_path}</string>
                </array>
                <key>RunAtLoad</key>
                <true/>
            </dict>
            </plist>"""
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.dialogapp.plist")
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            os.chmod(plist_path, 0o644)
        else:
            desktop_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(desktop_dir, exist_ok=True)
            desktop_path = os.path.join(desktop_dir, "dialogapp.desktop")
            desktop_content = f"""[Desktop Entry]
            Type=Application
            Name=DialogApp
            Exec={app_path}
            Hidden=false
            NoDisplay=false
            X-GNOME-Autostart-enabled=true
            """
            with open(desktop_path, 'w') as f:
                f.write(desktop_content)

    def _disable_autostart(self):
        if sys.platform == 'win32':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "DialogApp")
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass
        elif sys.platform == 'darwin':
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.dialogapp.plist")
            if os.path.exists(plist_path):
                os.remove(plist_path)
        else:
            desktop_path = os.path.expanduser("~/.config/autostart/dialogapp.desktop")
            if os.path.exists(desktop_path):
                os.remove(desktop_path)

    def browse_sound(self, sound_name):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите звуковой файл", "",
                                                "Звуковые файлы (*.wav);;Все файлы (*)")
        if file_path:
            # Определяем папку sounds приложения
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sounds_dir = os.path.join(base_dir, 'sounds')
            os.makedirs(sounds_dir, exist_ok=True)

            file_name = os.path.basename(file_path)
            dest_path = os.path.join(sounds_dir, file_name)

            # Если выбранный файл уже лежит в папке sounds, просто используем его имя
            # Иначе копируем файл в папку sounds (перезаписываем при совпадении имён)
            if os.path.dirname(file_path) != sounds_dir:
                import shutil
                shutil.copy2(file_path, dest_path)
                logger.info(f"Звуковой файл скопирован в {dest_path}")

            # Сохраняем только имя файла (относительный путь)
            self.settings.setValue(f'sound_{sound_name}', file_name)
            self.settings.sync()

            # Обновляем отображение в поле ввода
            if sound_name == 'incoming_call':
                self.incoming_call_path.setText(file_name)
            elif sound_name == 'outgoing_call':
                self.outgoing_call_path.setText(file_name)
            elif sound_name == 'message':
                self.message_path.setText(file_name)
            elif sound_name == 'file_received':
                self.file_received_path.setText(file_name)

    def browse_download_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения файлов")
        if folder:
            self.download_path.setText(folder)
            self.settings.setValue('download_folder', folder)

    def open_blacklist_dialog(self):
        if not self.main_window:
            parent = self.parent()
            while parent:
                if hasattr(parent, 'main_window') and parent.main_window:
                    self.main_window = parent.main_window
                    break
                parent = parent.parent()
            if not self.main_window:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить главное окно приложения")
                return

        dialog = QDialog(self)
        dialog.setWindowTitle("Чёрный список")
        dialog.setMinimumWidth(350)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        if self.main_window.p2p_client and hasattr(self.main_window.p2p_client, 'db'):
            blacklist = self.main_window.p2p_client.db.get_blacklist()
            for item in blacklist:
                list_widget.addItem(item['username'])
        else:
            list_widget.addItem("Невозможно загрузить список")
            list_widget.setEnabled(False)
        layout.addWidget(list_widget)

        btn_unblock = QPushButton("🔓 Разблокировать выбранного")
        def unblock():
            current = list_widget.currentItem()
            if current:
                username = current.text()
                if show_question_dialog(dialog, "Подтверждение", f"Разблокировать пользователя {username}?"):
                    self.main_window.unblock_user(username)
                    list_widget.takeItem(list_widget.row(current))
            else:
                QMessageBox.information(dialog, "Внимание", "Выберите пользователя")
        btn_unblock.clicked.connect(unblock)
        layout.addWidget(btn_unblock)
        dialog.exec_()

    def set_main_window(self, main_window):
        self.main_window = main_window

    def get_settings(self):
        return {
            'sounds_enabled': self.enable_sounds_check.isChecked(),
            'sound_incoming_call': self.incoming_call_path.text(),
            'sound_outgoing_call': self.outgoing_call_path.text(),
            'sound_message': self.message_path.text(),
            'sound_file_received': self.file_received_path.text(),
            'download_folder': self.download_path.text(),
            'max_file_size_mb': self.max_file_size.value()
        }


class AudioSettingsPage(QWidget):
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

        audio_group = QGroupBox("Аудио устройства")
        audio_layout = QVBoxLayout(audio_group)

        self.audio_system_label = QLabel("Определение звуковой системы...")
        self.audio_system_label.setAlignment(Qt.AlignCenter)
        self.audio_system_label.setWordWrap(True)
        audio_layout.addWidget(self.audio_system_label)

        mic_layout = QHBoxLayout()
        mic_layout.addWidget(QLabel("Микрофон:"))
        self.input_device_combo = QComboBox()
        self.input_device_combo.setMinimumWidth(250)
        mic_layout.addWidget(self.input_device_combo)
        audio_layout.addLayout(mic_layout)

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

        cam_group = QGroupBox("Камера")
        cam_layout = QVBoxLayout()
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self.on_camera_changed)
        cam_layout.addWidget(self.camera_combo)
        cam_group.setLayout(cam_layout)
        layout.addWidget(cam_group)

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

        self.apply_btn = QPushButton("Применить")
        self.apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(self.apply_btn)

        layout.addStretch()

        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        self.fps_combo.currentIndexChanged.connect(self.on_fps_changed)
        self.quality_combo.currentIndexChanged.connect(self.on_quality_changed)
        self.color_enhance_check.stateChanged.connect(self.on_color_enhance_changed)

    def detect_cameras(self):
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
        try:
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
            try:
                self.color_enhance_check.setChecked(self.color_enhancement)
            except RuntimeError:
                pass
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек видео: {e}")

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
        pass

    def on_color_enhance_changed(self):
        try:
            self.color_enhancement = self.color_enhance_check.isChecked()
        except RuntimeError:
            pass

    def start_preview(self):
        if self.preview_active:
            self.stop_preview()

        if self.camera_index == -1:
            self.preview_label.setText("Камера не выбрана")
            return

        try:
            from ui.video_window import VideoCaptureThread, VideoProcessor
        except ImportError:
            from ui.video_window import VideoCaptureThread, VideoProcessor

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

        try:
            self.color_enhancement = self.color_enhance_check.isChecked()
        except RuntimeError:
            self.color_enhancement = False

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
        if frame is None:
            return
        if self.color_enhancement:
            self.video_processor.put_frame(frame)
            processed = self.video_processor.get_processed_frame()
            if processed is not None:
                frame = processed
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

    def get_current_settings(self):
        try:
            selected_camera = self.camera_combo.currentData()
            if selected_camera is not None and selected_camera != -1:
                self.camera_index = selected_camera
            elif self.available_cameras:
                self.camera_index = self.available_cameras[0]
            else:
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

            try:
                self.color_enhancement = self.color_enhance_check.isChecked()
            except RuntimeError:
                self.color_enhancement = False

            return {
                'camera_index': self.camera_index,
                'resolution': self.resolution,
                'fps': self.fps,
                'quality': self.quality,
                'color_enhancement': self.color_enhancement
            }
        except Exception as e:
            logger.error(f"Ошибка получения настроек видео: {e}")
            return {
                'camera_index': self.camera_index,
                'resolution': self.resolution,
                'fps': self.fps,
                'quality': self.quality,
                'color_enhancement': self.color_enhancement
            }

    def apply_settings(self):
        try:
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

            try:
                self.color_enhancement = self.color_enhance_check.isChecked()
            except RuntimeError:
                self.color_enhancement = False

            self.save_settings()
            self.video_settings_changed.emit({
                'camera_index': self.camera_index,
                'resolution': self.resolution,
                'fps': self.fps,
                'quality': self.quality,
                'color_enhancement': self.color_enhancement
            })
        except Exception as e:
            logger.error(f"Ошибка применения настроек видео: {e}")

    def closeEvent(self, event):
        try:
            self.color_enhance_check.stateChanged.disconnect(self.on_color_enhance_changed)
        except:
            pass
        self.stop_preview()
        event.accept()


class HotkeysSettingsPage(QWidget):
    hotkeys_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.hotkeys = {}
        self.init_ui()
        self.load_hotkeys()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Действие", "Комбинация клавиш"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit_hotkey)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("➕ Добавить")
        self.add_btn.clicked.connect(self.add_hotkey)
        self.edit_btn = QPushButton("✏️ Изменить")
        self.edit_btn.clicked.connect(self.edit_hotkey)
        self.delete_btn = QPushButton("🗑️ Удалить")
        self.delete_btn.clicked.connect(self.delete_hotkey)
        self.reset_btn = QPushButton("🔄 Сбросить все")
        self.reset_btn.clicked.connect(self.reset_defaults)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.reset_btn)
        layout.addLayout(btn_layout)

        info_label = QLabel("ℹ️ Горячие клавиши работают, когда окно приложения активно. "
                            "Для ввода комбинации нажмите нужные клавиши (например, Ctrl+Shift+M).")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 10pt; margin-top: 8px;")
        layout.addWidget(info_label)

    def load_hotkeys(self):
        self.hotkeys = {}
        size = self.settings.beginReadArray("hotkeys")
        for i in range(size):
            self.settings.setArrayIndex(i)
            action = self.settings.value("action")
            shortcut = self.settings.value("shortcut")
            if action and shortcut:
                self.hotkeys[action] = shortcut
        self.settings.endArray()
        if not self.hotkeys:
            self.load_defaults()
        self.update_table()

    def load_defaults(self):
        self.hotkeys = {
            "Отправить сообщение": "Ctrl+Enter",
            "Ответить на звонок": "Ctrl+Shift+A",
            "Отклонить звонок": "Ctrl+Shift+R",
            "Завершить звонок": "Ctrl+Shift+E",
            "Вкл/Выкл микрофон": "Ctrl+M",
            "Показать/скрыть окно": "Ctrl+Shift+W",
            "Открыть настройки": "Ctrl+,",
            "Выйти из приложения": "Ctrl+Q"
        }

    def update_table(self):
        self.table.setRowCount(len(self.hotkeys))
        for row, (action, shortcut) in enumerate(self.hotkeys.items()):
            self.table.setItem(row, 0, QTableWidgetItem(action))
            self.table.setItem(row, 1, QTableWidgetItem(shortcut))
        self.table.resizeColumnsToContents()

    def add_hotkey(self):
        action, shortcut = self.show_hotkey_dialog()
        if action and shortcut:
            if action in self.hotkeys:
                QMessageBox.warning(self, "Дубликат", f"Действие '{action}' уже существует.")
                return
            self.hotkeys[action] = shortcut
            self.save_hotkeys()
            self.update_table()

    def edit_hotkey(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Редактирование", "Сначала выберите запись.")
            return
        action = self.table.item(current_row, 0).text()
        old_shortcut = self.hotkeys.get(action, "")
        new_action, new_shortcut = self.show_hotkey_dialog(action, old_shortcut)
        if new_action and new_shortcut:
            if new_action != action and new_action in self.hotkeys:
                QMessageBox.warning(self, "Дубликат", f"Действие '{new_action}' уже существует.")
                return
            del self.hotkeys[action]
            self.hotkeys[new_action] = new_shortcut
            self.save_hotkeys()
            self.update_table()

    def delete_hotkey(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Удаление", "Сначала выберите запись.")
            return
        action = self.table.item(current_row, 0).text()
        if show_question_dialog(self, "Подтверждение", f"Удалить горячую клавишу для действия '{action}'?"):
            del self.hotkeys[action]
            self.save_hotkeys()
            self.update_table()

    def reset_defaults(self):
        if show_question_dialog(self, "Сброс настроек", "Вернуть горячие клавиши к значениям по умолчанию?"):
            self.load_defaults()
            self.save_hotkeys()
            self.update_table()

    def show_hotkey_dialog(self, current_action="", current_shortcut=""):
        dialog = QDialog(self)
        dialog.setWindowTitle("Горячая клавиша")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Действие:"))
        action_edit = QLineEdit()
        action_edit.setText(current_action)
        action_edit.setPlaceholderText("Например: Отправить сообщение")
        layout.addWidget(action_edit)
        layout.addWidget(QLabel("Комбинация клавиш:"))
        key_edit = QKeySequenceEdit()
        if current_shortcut:
            key_edit.setKeySequence(QKeySequence(current_shortcut))
        layout.addWidget(key_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            action = action_edit.text().strip()
            shortcut = key_edit.keySequence().toString()
            if not action:
                QMessageBox.warning(dialog, "Ошибка", "Действие не может быть пустым.")
                return None, None
            if not shortcut:
                QMessageBox.warning(dialog, "Ошибка", "Комбинация клавиш не задана.")
                return None, None
            return action, shortcut
        return None, None

    def save_hotkeys(self):
        self.settings.beginWriteArray("hotkeys")
        for i, (action, shortcut) in enumerate(self.hotkeys.items()):
            self.settings.setArrayIndex(i)
            self.settings.setValue("action", action)
            self.settings.setValue("shortcut", shortcut)
        self.settings.endArray()
        self.settings.sync()
        self.hotkeys_changed.emit(self.hotkeys)

    def get_hotkeys(self):
        return self.hotkeys.copy()


class NetworkSettingsPage(QWidget):
    network_settings_changed = pyqtSignal(dict)
    network_restart_requested = pyqtSignal(dict)

    def __init__(self, parent=None, p2p_client=None):
        super().__init__(parent)
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.p2p_client = p2p_client
        self.init_ui()
        self.ice_servers = []  # список словарей с ключами urls, username, credential
        self.load_settings()
        self.load_ice_servers()
        self.update_network_status()

        try:
            self.refresh_external_ip()
        except Exception as e:
            logger.error(f"Ошибка обновления внешнего IP: {e}")
            self.public_ip_label.setText("Ошибка")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        port_group = QGroupBox("Локальный порт")
        port_layout = QHBoxLayout()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setToolTip("Порт, на котором клиент будет принимать подключения")
        port_layout.addWidget(QLabel("Порт:"))
        port_layout.addWidget(self.port_spin)
        port_layout.addStretch()
        port_group.setLayout(port_layout)
        layout.addWidget(port_group)

        bootstrap_group = QGroupBox("Bootstrap-узлы")
        bootstrap_group.setToolTip("Узлы для первоначального входа в сеть")
        bootstrap_layout = QVBoxLayout()
        self.bootstrap_table = QTableWidget()
        self.bootstrap_table.setColumnCount(2)
        self.bootstrap_table.setHorizontalHeaderLabels(["Хост", "Порт"])
        self.bootstrap_table.horizontalHeader().setStretchLastSection(True)
        self.bootstrap_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.bootstrap_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.bootstrap_table.setMinimumHeight(200)
        self.bootstrap_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bootstrap_layout.addWidget(self.bootstrap_table)

        btn_layout = QHBoxLayout()
        self.add_bootstrap_btn = QPushButton("➕ Добавить")
        self.add_bootstrap_btn.clicked.connect(self.add_bootstrap_node)
        self.edit_bootstrap_btn = QPushButton("✏️ Изменить")
        self.edit_bootstrap_btn.clicked.connect(self.edit_bootstrap_node)
        self.del_bootstrap_btn = QPushButton("🗑️ Удалить")
        self.del_bootstrap_btn.clicked.connect(self.del_bootstrap_node)
        btn_layout.addWidget(self.add_bootstrap_btn)
        btn_layout.addWidget(self.edit_bootstrap_btn)
        btn_layout.addWidget(self.del_bootstrap_btn)
        btn_layout.addStretch()
        bootstrap_layout.addLayout(btn_layout)
        bootstrap_group.setLayout(bootstrap_layout)
        layout.addWidget(bootstrap_group)

        ice_group = QGroupBox("ICE-серверы (STUN/TURN)")
        ice_layout = QVBoxLayout()
        self.ice_table = QTableWidget()
        self.ice_table.setColumnCount(3)
        self.ice_table.setHorizontalHeaderLabels(["URL", "Логин", "Пароль"])
        self.ice_table.horizontalHeader().setStretchLastSection(True)
        self.ice_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ice_table.setMinimumHeight(150)
        ice_layout.addWidget(self.ice_table)

        self.turn_enabled_check = QCheckBox("Использовать TURN-серверы (ретрансляция)")
        self.turn_enabled_check.setChecked(True)
        self.turn_enabled_check.toggled.connect(self.on_turn_toggled)
        ice_layout.addWidget(self.turn_enabled_check)
        ice_group.setLayout(ice_layout)

        # Кнопки управления ICE-серверами
        ice_btn_layout = QHBoxLayout()
        self.add_ice_btn = QPushButton("➕ Добавить")
        self.add_ice_btn.clicked.connect(self.add_ice_server)
        self.edit_ice_btn = QPushButton("✏️ Изменить")
        self.edit_ice_btn.clicked.connect(self.edit_ice_server)
        self.del_ice_btn = QPushButton("🗑️ Удалить")
        self.del_ice_btn.clicked.connect(self.delete_ice_server)
        ice_btn_layout.addWidget(self.add_ice_btn)
        ice_btn_layout.addWidget(self.edit_ice_btn)
        ice_btn_layout.addWidget(self.del_ice_btn)
        ice_btn_layout.addStretch()
        ice_layout.addLayout(ice_btn_layout)

        layout.addWidget(ice_group)

        info_group = QGroupBox("Статус сети")
        info_layout = QFormLayout()
        self.status_label = QLabel("Неизвестно")
        self.peers_label = QLabel("0")
        self.known_peers_label = QLabel("0")
        self.public_ip_label = QLabel("Не определён")
        info_layout.addRow("Статус:", self.status_label)
        info_layout.addRow("Подключенные пиры:", self.peers_label)
        info_layout.addRow("Известные пиры:", self.known_peers_label)
        info_layout.addRow("Публичный IP:", self.public_ip_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        btn_row = QHBoxLayout()
        self.test_connection_btn = QPushButton("🔍 Проверить подключение (bootstrap и TURN)")
        self.test_connection_btn.clicked.connect(self.test_connection)
        btn_row.addWidget(self.test_connection_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        self.restart_btn = QPushButton("🔄 Сохранить и перезапустить сеть")
        self.restart_btn.setToolTip("Сохранить порт и bootstrap-узлы, затем перезапустить P2P-клиент")
        self.restart_btn.clicked.connect(self.on_restart_clicked)
        layout.addWidget(self.restart_btn)

        layout.addStretch()

    def load_ice_servers(self):
        try:
            if hasattr(self, 'p2p_client') and self.p2p_client:
                config = self.p2p_client.config
            else:
                config = self._load_config_from_file()
            self.ice_servers = config.get('media', {}).get('ice_servers', []).copy()
            self.update_ice_table()
        except Exception as e:
            logger.error(f"Ошибка загрузки ICE-серверов: {e}")
            self.ice_servers = []
            self.update_ice_table()

    def update_ice_table(self):
        self.ice_table.setRowCount(len(self.ice_servers))
        for row, srv in enumerate(self.ice_servers):
            self.ice_table.setItem(row, 0, QTableWidgetItem(srv.get('urls', '')))
            self.ice_table.setItem(row, 1, QTableWidgetItem(srv.get('username', '')))
            self.ice_table.setItem(row, 2, QTableWidgetItem(srv.get('credential', '')))
        self.ice_table.resizeColumnsToContents()

    def add_ice_server(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить ICE-сервер")
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("stun:stun.l.google.com:19302")
        user_edit = QLineEdit()
        user_edit.setPlaceholderText("логин (если требуется)")
        pass_edit = QLineEdit()
        pass_edit.setPlaceholderText("пароль (если требуется)")
        pass_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("URL:", url_edit)
        form_layout.addRow("Логин:", user_edit)
        form_layout.addRow("Пароль:", pass_edit)
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            urls = url_edit.text().strip()
            username = user_edit.text().strip()
            credential = pass_edit.text().strip()
            if urls:
                new_server = {'urls': urls}
                if username:
                    new_server['username'] = username
                if credential:
                    new_server['credential'] = credential
                self.ice_servers.append(new_server)
                self.update_ice_table()
                self.save_ice_servers()

    def edit_ice_server(self):
        row = self.ice_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Редактирование", "Выберите сервер для редактирования")
            return
        srv = self.ice_servers[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать ICE-сервер")
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        url_edit = QLineEdit(srv.get('urls', ''))
        user_edit = QLineEdit(srv.get('username', ''))
        pass_edit = QLineEdit(srv.get('credential', ''))
        pass_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("URL:", url_edit)
        form_layout.addRow("Логин:", user_edit)
        form_layout.addRow("Пароль:", pass_edit)
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            urls = url_edit.text().strip()
            username = user_edit.text().strip()
            credential = pass_edit.text().strip()
            if urls:
                self.ice_servers[row]['urls'] = urls
                self.ice_servers[row]['username'] = username
                self.ice_servers[row]['credential'] = credential
                self.update_ice_table()
                self.save_ice_servers()

    def delete_ice_server(self):
        row = self.ice_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Удаление", "Выберите сервер для удаления")
            return
        if show_question_dialog(self, "Подтверждение", "Удалить выбранный ICE-сервер?"):
            self.ice_servers.pop(row)
            self.update_ice_table()
            self.save_ice_servers()

    def save_ice_servers(self):
        try:
            # Обновляем конфиг в p2p_client, если есть
            if self.p2p_client and hasattr(self.p2p_client, 'config'):
                if 'media' not in self.p2p_client.config:
                    self.p2p_client.config['media'] = {}
                self.p2p_client.config['media']['ice_servers'] = self.ice_servers.copy()
            # Сохраняем в config.yaml
            self._save_ice_to_config()
        except Exception as e:
            logger.error(f"Ошибка сохранения ICE-серверов: {e}")

    def _save_ice_to_config(self):
        import yaml
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        config_path = os.path.join(project_root, 'config.yaml')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}
            if 'media' not in config:
                config['media'] = {}
            config['media']['ice_servers'] = self.ice_servers.copy()
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения ICE-серверов в config.yaml: {e}")

    def _load_config_from_file(self):
        import yaml
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        config_path = os.path.join(project_root, 'config.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Не удалось загрузить config.yaml: {e}")
            return {}

    def on_turn_toggled(self, checked):
        self.settings.setValue('use_turn', checked)

    def refresh_external_ip(self):
        try:
            import urllib.request
            import json
            ip = None
            services = [
                'https://api.ipify.org?format=json',
                'https://icanhazip.com',
                'https://checkip.amazonaws.com',
            ]
            for url in services:
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        if url.endswith('json'):
                            data = json.loads(response.read().decode())
                            ip = data.get('ip')
                        else:
                            ip = response.read().decode().strip()
                        if ip and self._is_valid_ipv4(ip):
                            break
                except:
                    continue
            if ip:
                self.public_ip_label.setText(ip)
                self.public_ip_label.setStyleSheet("color: green;")
            else:
                self.public_ip_label.setText("Не удалось определить")
                self.public_ip_label.setStyleSheet("color: red;")
        except Exception as e:
            logger.error(f"Ошибка получения внешнего IP: {e}")
            self.public_ip_label.setText("Ошибка")
            self.public_ip_label.setStyleSheet("color: red;")

    def _is_valid_ipv4(self, ip):
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for p in parts:
            try:
                if not (0 <= int(p) <= 255):
                    return False
            except ValueError:
                return False
        return True

    def test_connection(self):
        import socket
        results = []

        nodes = self.get_bootstrap_nodes()
        if nodes:
            results.append("🔄 Проверка bootstrap-узлов:")
            for host, port in nodes:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    sock.connect((host, port))
                    sock.close()
                    results.append(f"  ✅ {host}:{port} – доступен")
                except Exception as e:
                    results.append(f"  ❌ {host}:{port} – недоступен ({str(e)})")
        else:
            results.append("⚠️ Нет bootstrap-узлов для проверки")

        ice_servers = self._get_ice_servers()
        turn_servers = [s for s in ice_servers if s['urls'].startswith('turn:')]
        if turn_servers and self.turn_enabled_check.isChecked():
            results.append("\n🔄 Проверка TURN-серверов (TCP):")
            for srv in turn_servers:
                url = srv['urls']
                host = None
                port = None
                if '?' in url:
                    base, params = url.split('?', 1)
                else:
                    base = url
                if base.startswith('turn:'):
                    base = base[5:]
                if ':' in base:
                    host, port_str = base.split(':', 1)
                    try:
                        port = int(port_str)
                    except:
                        port = None
                else:
                    host = base
                    port = 80
                if not host:
                    continue
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((host, port))
                    sock.close()
                    results.append(f"  ✅ {host}:{port} – доступен")
                except Exception as e:
                    results.append(f"  ❌ {host}:{port} – недоступен ({str(e)})")
        else:
            results.append("\nℹ️ TURN-серверы не проверяются (отключены или не найдены)")

        QMessageBox.information(self, "Результаты проверки", "\n".join(results))

    def update_network_status(self):
        if self.p2p_client:
            try:
                connected = len(self.p2p_client.connected_peers) if hasattr(self.p2p_client, 'connected_peers') else 0
                known = len(self.p2p_client.known_peers) if hasattr(self.p2p_client, 'known_peers') else 0
                status = "✅ Подключено" if connected > 0 else "❌ Не подключено"
                self.status_label.setText(status)
                self.peers_label.setText(str(connected))
                self.known_peers_label.setText(str(known))
            except Exception as e:
                logger.error(f"Ошибка обновления статуса сети: {e}")

    def _get_ice_servers(self):
        if hasattr(self, 'p2p_client') and self.p2p_client:
            config = self.p2p_client.config
        else:
            config = self._load_config_from_file()
        return config.get('media', {}).get('ice_servers', [])

    def load_settings(self):
        port = self.settings.value('network_port', 8890, type=int)
        self.port_spin.setValue(port)

        # Загружаем bootstrap-узлы из config.yaml (приоритет)
        nodes = self._load_defaults_from_config()
        if not nodes:
            # если нет, из QSettings
            size = self.settings.beginReadArray("bootstrap_nodes")
            for i in range(size):
                self.settings.setArrayIndex(i)
                host = self.settings.value("host")
                p = self.settings.value("port")
                if host and p:
                    nodes.append((host, p))
            self.settings.endArray()
        if not nodes:
            nodes = [("localhost", 8888)]
        self.update_bootstrap_table(nodes)

        # Состояние чекбокса TURN
        use_turn = self.settings.value('use_turn', True, type=bool)
        self.turn_enabled_check.setChecked(use_turn)
    
    def save_settings(self):
        port = self.port_spin.value()
        nodes = self.get_bootstrap_nodes()
        use_turn = self.turn_enabled_check.isChecked()

        # Сохраняем в QSettings
        self.settings.setValue('network_port', port)
        self.settings.setValue('use_turn', use_turn)
        self.settings.beginWriteArray("bootstrap_nodes")
        for i, (host, p) in enumerate(nodes):
            self.settings.setArrayIndex(i)
            self.settings.setValue("host", host)
            self.settings.setValue("port", p)
        self.settings.endArray()
        self.settings.sync()

        # Сохраняем в config.yaml (если клиент есть – обновляем его)
        if self.p2p_client:
            self.p2p_client.listen_port = port
            self.p2p_client.bootstrap_nodes = [{'host': h, 'port': p} for h, p in nodes]
            # также можно обновить media.ice_servers, но они обычно не меняются через UI
        self._save_to_config(port, nodes)
        self.save_ice_servers()

    def _save_to_config(self, port, nodes):
        import yaml
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        config_path = os.path.join(project_root, 'config.yaml')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}
            if 'network' not in config:
                config['network'] = {}
            config['network']['bootstrap_nodes'] = [{'host': h, 'port': p} for h, p in nodes]
            config['network']['min_port'] = port  # или другой ключ
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения config.yaml: {e}")

    def get_bootstrap_nodes(self):
        nodes = []
        for row in range(self.bootstrap_table.rowCount()):
            host_item = self.bootstrap_table.item(row, 0)
            port_item = self.bootstrap_table.item(row, 1)
            if host_item and port_item:
                host = host_item.text()
                try:
                    port = int(port_item.text())
                    nodes.append((host, port))
                except ValueError:
                    pass
        return nodes

    def update_bootstrap_table(self, nodes):
        self.bootstrap_table.setRowCount(len(nodes))
        for row, (host, port) in enumerate(nodes):
            self.bootstrap_table.setItem(row, 0, QTableWidgetItem(host))
            self.bootstrap_table.setItem(row, 1, QTableWidgetItem(str(port)))
        self.bootstrap_table.resizeColumnsToContents()
        self.network_settings_changed.emit(self.get_settings())

    def _load_defaults_from_config(self):
        import yaml
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        config_path = os.path.join(project_root, 'config.yaml')
        if not os.path.exists(config_path):
            return []
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            nodes = config.get('network', {}).get('bootstrap_nodes', [])
            result = []
            for node in nodes:
                if isinstance(node, dict) and 'host' in node and 'port' in node:
                    result.append((node['host'], node['port']))
                elif isinstance(node, list) and len(node) == 2:
                    result.append((node[0], node[1]))
            return result
        except Exception as e:
            logger.error(f"Ошибка чтения config.yaml: {e}")
            return []

    def on_restart_clicked(self):
        self.save_settings()
        settings = self.get_settings()
        self.network_restart_requested.emit(settings)

    def on_port_changed(self, value):
        self.network_settings_changed.emit(self.get_settings())

    def add_bootstrap_node(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить bootstrap-узел")
        layout = QVBoxLayout(dialog)
        host_edit = QLineEdit()
        host_edit.setPlaceholderText("IP-адрес или домен")
        port_edit = QSpinBox()
        port_edit.setRange(1, 65535)
        port_edit.setValue(8888)
        layout.addWidget(QLabel("Хост:"))
        layout.addWidget(host_edit)
        layout.addWidget(QLabel("Порт:"))
        layout.addWidget(port_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            host = host_edit.text().strip()
            if host:
                nodes = self.get_bootstrap_nodes()
                nodes.append((host, port_edit.value()))
                self.update_bootstrap_table(nodes)

    def edit_bootstrap_node(self):
        row = self.bootstrap_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Редактирование", "Выберите узел для редактирования")
            return
        host = self.bootstrap_table.item(row, 0).text()
        port = int(self.bootstrap_table.item(row, 1).text())
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать bootstrap-узел")
        layout = QVBoxLayout(dialog)
        host_edit = QLineEdit(host)
        port_edit = QSpinBox()
        port_edit.setRange(1, 65535)
        port_edit.setValue(port)
        layout.addWidget(QLabel("Хост:"))
        layout.addWidget(host_edit)
        layout.addWidget(QLabel("Порт:"))
        layout.addWidget(port_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() == QDialog.Accepted:
            new_host = host_edit.text().strip()
            if new_host:
                nodes = self.get_bootstrap_nodes()
                nodes[row] = (new_host, port_edit.value())
                self.update_bootstrap_table(nodes)

    def del_bootstrap_node(self):
        row = self.bootstrap_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Удаление", "Выберите узел для удаления")
            return
        nodes = self.get_bootstrap_nodes()
        nodes.pop(row)
        self.update_bootstrap_table(nodes)

    def get_settings(self):
        return {
            'network_port': self.port_spin.value(),
            'bootstrap_nodes': self.get_bootstrap_nodes(),
            'use_turn': self.turn_enabled_check.isChecked()
        }


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None, input_device=None, output_device=None, p2p_client=None):
        super().__init__(parent)
        self.p2p_client = p2p_client
        self.setWindowTitle("Настройки приложения")
        self.setMinimumSize(825, 500)
        self.setMaximumSize(985, 600)
        self.setModal(True)

        self.settings_data = {
            'input_device': input_device,
            'output_device': output_device,
        }

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

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
                background-color: #8f949a;
                color: white;
            }
        """)
        
        main_layout.addWidget(self.nav_list)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        self.stacked_widget = QStackedWidget()
        right_layout.addWidget(self.stacked_widget, 1)

        # Создаём страницы
        self.general_page = GeneralSettingsPage(current_nickname=parent.username if parent else "")
        if parent:
            self.general_page.set_main_window(parent)
        self.general_page.nickname_changed.connect(self.on_nickname_changed)

        self.audio_page = AudioSettingsPage(
            current_input=self.settings_data['input_device'],
            current_output=self.settings_data['output_device']
        )
        self.video_page = VideoSettingsPage()
        self.hotkeys_page = HotkeysSettingsPage()
        self.network_page = NetworkSettingsPage(p2p_client=self.p2p_client)
        self.network_page.network_restart_requested.connect(self.on_network_restart_requested)

        def wrap_with_scroll(widget):
            scroll = QScrollArea()
            scroll.setWidget(widget)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            return scroll

        self.stacked_widget.addWidget(wrap_with_scroll(self.general_page))
        self.stacked_widget.addWidget(wrap_with_scroll(self.audio_page))
        self.stacked_widget.addWidget(wrap_with_scroll(self.video_page))
        self.stacked_widget.addWidget(wrap_with_scroll(self.hotkeys_page))
        self.stacked_widget.addWidget(wrap_with_scroll(self.network_page))

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

        self.nav_list.currentItemChanged.connect(self.on_nav_changed)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Отмена")
        btn_apply = QPushButton("Применить")

        btn_ok.setFixedWidth(80)
        btn_cancel.setFixedWidth(120)
        btn_apply.setFixedWidth(150)

        button_layout.addWidget(btn_ok)
        button_layout.addWidget(btn_cancel)
        button_layout.addWidget(btn_apply)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_apply.clicked.connect(self.apply_settings)

        right_layout.addLayout(button_layout)
        main_layout.addWidget(right_widget, 1)

        self.audio_page.audio_settings_changed.connect(self.on_audio_settings_changed)
        self.video_page.video_settings_changed.connect(self.on_video_settings_changed)

        self.nav_list.setCurrentRow(0)
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        


    def on_nav_changed(self, current, previous):
        if current is None:
            return
        idx = current.data(Qt.UserRole)
        if idx is not None and idx < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(idx)

    def on_nickname_changed(self, new_nickname):
        self.settings_changed.emit({'nickname': new_nickname})

    def on_audio_settings_changed(self, settings):
        logger.debug(f"on_audio_settings_changed received: {settings}")
        self.settings_data.update(settings)

    def on_video_settings_changed(self, settings):
        self.settings_data.update(settings)
        logger.debug(f"Видеонастройки обновлены: {settings}")

    def on_network_restart_requested(self, settings):
        self.settings_changed.emit({'network_restart': settings})

    def apply_settings(self):
        all_settings = {}
        all_settings.update(self.general_page.get_settings())
        all_settings.update({
            'input_device': self.audio_page.input_device,
            'output_device': self.audio_page.output_device
        })
        all_settings.update(self.video_page.get_current_settings())
        all_settings.update(self.hotkeys_page.get_hotkeys())
        self.settings_changed.emit(all_settings)
        logger.info("Настройки применены")
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def accept(self):
        self.apply_settings()
        super().accept()

    def reject(self):
        super().reject()