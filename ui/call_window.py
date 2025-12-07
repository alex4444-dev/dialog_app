import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QMessageBox,
                             QComboBox, QGroupBox, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import logging
import time
import struct
import threading
import socket
import numpy as np
import traceback

logger = logging.getLogger('dialog_gui')

class CallWindow(QWidget):
    call_ended = pyqtSignal(str)
    call_accepted = pyqtSignal(str)
    call_rejected = pyqtSignal(str)
    
    def __init__(self, username, call_type, call_id, is_outgoing=True, parent=None):
        super().__init__(parent)
        self.username = username
        self.call_type = call_type
        self.call_id = call_id
        self.is_outgoing = is_outgoing

        # Подключаем сигналы КОРРЕКТНО
        if not is_outgoing:
            # Для входящих звонков - подключаем сигналы принятия/отклонения
            self.call_accepted.connect(self.accept_call)
            self.call_rejected.connect(self.reject_call)
        
        # Сигнал завершения звонка всегда подключен
        self.call_ended.connect(self.end_call)

        logger.info(f"🔊 CallWindow.__init__: Создание окна для {username}, тип: {call_type}, исходящий: {is_outgoing}")

        self.is_active = False
        self.call_duration = 0
        self.duration_timer = QTimer()
        self.audio_initialized = False
        self.call_ended_emitted = False
        self.audio_stream = None
        self.audio_available = False
        self.accept_button_clicked = False
        
        # Аудио параметры
        self.sample_rate = 44100
        self.channels = 1
        self.dtype = 'float32'
        self.blocksize = 1024
        
        # Устройства
        self.input_device = None
        self.output_device = None
        self.audio_system_type = "Unknown"
        
        # Буфер для аудио данных
        self.audio_buffer = []
        self.buffer_size = 20
        self.audio_buffer_lock = threading.Lock()
        self.stream_id = f"call_{call_id}"

        # Счетчики для диагностики
        self.sent_packets = 0
        self.received_packets = 0
        self.last_audio_debug_time = 0
        
        # Сокет для звонка - ИНИЦИАЛИЗИРУЕМ ПУСТЫМ
        self.call_socket = None
        self.socket_set = False
        self.socket_attempts = 0
        self.max_socket_attempts = 3
        
        # Сначала инициализируем UI
        self.init_ui()
        
        # Затем определяем аудио систему
        self.detect_audio_system()

        logger.info(f"🔊 CallWindow создано успешно")
        
    def init_ui(self):
        """Инициализация интерфейса окна звонка"""
        self.setWindowTitle(f"📞 Звонок с {self.username}")
        self.setMinimumSize(550, 650)
        self.setMaximumSize(800, 900)
        self.resize(600, 700)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        
        # Главный layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        title_text = "Исходящий звонок" if self.is_outgoing else "Входящий звонок"
        title_label = QLabel(f"📞 {title_text}")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        title_label.setWordWrap(True)
        main_layout.addWidget(title_label)
        
        # Информация о звонке
        info_label = QLabel(f"Пользователь: {self.username}\nТип: {self.call_type}\nID: {self.call_id}")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 14px; color: #34495e; margin-bottom: 10px;")
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)
        
        # Группа выбора аудиоустройств
        audio_group = QGroupBox("Настройки аудио")
        audio_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        audio_layout = QVBoxLayout()
        audio_layout.setSpacing(8)
        
        # Информация о звуковой системе
        self.audio_system_label = QLabel("Определение звуковой системы...")
        self.audio_system_label.setAlignment(Qt.AlignCenter)
        self.audio_system_label.setStyleSheet("font-size: 11px; color: #7f8c8d; font-style: italic; margin-bottom: 5px;")
        self.audio_system_label.setWordWrap(True)
        audio_layout.addWidget(self.audio_system_label)
        
        # Выбор устройства ввода
        input_layout = QHBoxLayout()
        input_label = QLabel("Микрофон:")
        input_label.setFixedWidth(80)
        input_layout.addWidget(input_label)
        self.input_device_combo = QComboBox()
        self.input_device_combo.setMaximumHeight(30)
        input_layout.addWidget(self.input_device_combo)
        audio_layout.addLayout(input_layout)
        
        # Выбор устройства вывода  
        output_layout = QHBoxLayout()
        output_label = QLabel("Динамики:")
        output_label.setFixedWidth(80)
        output_layout.addWidget(output_label)
        self.output_device_combo = QComboBox()
        self.output_device_combo.setMaximumHeight(30)
        output_layout.addWidget(self.output_device_combo)
        audio_layout.addLayout(output_layout)
        
        # Кнопка применения настроек
        self.apply_audio_button = QPushButton("Применить аудиоустройства")
        self.apply_audio_button.setFixedHeight(30)
        self.apply_audio_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.apply_audio_button.clicked.connect(self.apply_audio_devices)
        audio_layout.addWidget(self.apply_audio_button)
        
        audio_group.setLayout(audio_layout)
        main_layout.addWidget(audio_group)
        
        # Индикатор состояния аудио
        self.audio_status_label = QLabel("🔇 Аудио: проверка...")
        self.audio_status_label.setAlignment(Qt.AlignCenter)
        self.audio_status_label.setStyleSheet("font-size: 14px; color: #7f8c8d; margin: 10px 0;")
        self.audio_status_label.setWordWrap(True)
        main_layout.addWidget(self.audio_status_label)
        
        # Индикатор состояния сокета
        self.socket_status_label = QLabel("🔴 Сокет: не установлен")
        self.socket_status_label.setAlignment(Qt.AlignCenter)
        self.socket_status_label.setStyleSheet("font-size: 14px; color: #e74c3c; margin: 5px 0;")
        self.socket_status_label.setWordWrap(True)
        main_layout.addWidget(self.socket_status_label)
        
        # Диагностическая информация
        self.diagnostic_label = QLabel("Ожидание установки соединения...")
        self.diagnostic_label.setAlignment(Qt.AlignCenter)
        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c; margin: 5px 0;")
        self.diagnostic_label.setWordWrap(True)
        main_layout.addWidget(self.diagnostic_label)
        
        # Детальная диагностика
        self.detailed_diagnostic_label = QLabel("")
        self.detailed_diagnostic_label.setAlignment(Qt.AlignCenter)
        self.detailed_diagnostic_label.setStyleSheet("font-size: 14px; color: #95a5a6; margin: 5px 0;")
        self.detailed_diagnostic_label.setWordWrap(True)
        main_layout.addWidget(self.detailed_diagnostic_label)
        
        # Группа тестирования
        test_group = QGroupBox("Тестирование и диагностика")
        test_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        test_layout = QHBoxLayout()
        
        # Кнопка тестирования аудио
        self.test_audio_button = QPushButton("🔊 Тест аудио")
        self.test_audio_button.setFixedHeight(35)
        self.test_audio_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.test_audio_button.clicked.connect(self.run_audio_diagnostic)
        test_layout.addWidget(self.test_audio_button)
        
        # Кнопка тестирования гудков
        self.test_tones_button = QPushButton("🔔 Тест гудков")
        self.test_tones_button.setFixedHeight(35)
        self.test_tones_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.test_tones_button.clicked.connect(self.test_call_tones)
        test_layout.addWidget(self.test_tones_button)
        
        # Кнопка диагностики сокета
        self.socket_diagnostic_button = QPushButton("🔍 Диагностика сокета")
        self.socket_diagnostic_button.setFixedHeight(35)
        self.socket_diagnostic_button.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.socket_diagnostic_button.clicked.connect(self.debug_socket_state)
        test_layout.addWidget(self.socket_diagnostic_button)
        
        test_group.setLayout(test_layout)
        main_layout.addWidget(test_group)
        
        # Таймер звонка
        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.duration_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #27ae60; margin: 10px 0;")
        self.duration_label.setVisible(False)
        main_layout.addWidget(self.duration_label)
        
        # Статус звонка
        self.status_label = QLabel("Набор номера..." if self.is_outgoing else "Входящий вызов...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; color: #7f8c8d; margin: 10px 0;")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)
        
        # Прогресс-бар (для анимации)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Бесконечная анимация
        self.progress_bar.setVisible(True)
        self.progress_bar.setFixedHeight(10)
        main_layout.addWidget(self.progress_bar)
        
        # Растягивающийся элемент для выравнивания
        main_layout.addStretch(1)
        
        # Кнопки управления звонком
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        if self.is_outgoing:
            # Для исходящего звонка - только кнопка завершения
            self.end_button = QPushButton("📞 Завершить")
            self.end_button.setFixedHeight(45)
            self.end_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.end_button.clicked.connect(self.end_call)
            buttons_layout.addWidget(self.end_button)
            
        else:
            # Для входящего звонка - кнопки принятия и отклонения
            self.accept_button = QPushButton("✅ Принять")
            self.accept_button.setFixedHeight(45)
            self.accept_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            self.accept_button.clicked.connect(self.safe_accept_call)
            
            self.reject_button = QPushButton("❌ Отклонить")
            self.reject_button.setFixedHeight(45)
            self.reject_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.reject_button.clicked.connect(self.safe_reject_call)
            
            buttons_layout.addWidget(self.accept_button)
            buttons_layout.addWidget(self.reject_button)
        
        main_layout.addLayout(buttons_layout)
        
        self.setLayout(main_layout)
        
        # Настройка таймера для обновления длительности звонка
        self.duration_timer.timeout.connect(self.update_duration)
        
        # Таймер для обновления диагностической информации
        self.diagnostic_timer = QTimer()
        self.diagnostic_timer.timeout.connect(self.update_diagnostic_info)
        self.diagnostic_timer.start(1000)
        
        # Таймер для автоматической проверки сокета
        self.socket_check_timer = QTimer()
        self.socket_check_timer.timeout.connect(self.auto_check_socket)
        self.socket_check_timer.start(2000)  # Проверка каждые 2 секунды

    def debug_socket_state(self):
        """Расширенная диагностика состояния сокета"""
        try:
            logger.info("=" * 50)
            logger.info("🔍 РАСШИРЕННАЯ ДИАГНОСТИКА СОКЕТА")
            logger.info("=" * 50)
            
            # Базовая информация
            logger.info(f"📞 ID звонка: {self.call_id}")
            logger.info(f"📞 Тип звонка: {'исходящий' if self.is_outgoing else 'входящий'}")
            logger.info(f"🔌 Сокет установлен: {self.socket_set}")
            logger.info(f"🔌 CallSocket объект: {self.call_socket}")
            logger.info(f"🔌 Попыток установки: {self.socket_attempts}")
            
            # Проверяем родительское окно
            parent_info = "None"
            if self.parent():
                parent_info = f"{type(self.parent())} - {self.parent()}"
            logger.info(f"👨‍👦 Родительское окно: {parent_info}")
            
            # Проверяем, есть ли метод для получения сокета у родителя
            if self.parent() and hasattr(self.parent(), 'get_call_socket'):
                logger.info("✅ У родителя есть метод get_call_socket")
                try:
                    parent_socket = self.parent().get_call_socket(self.call_id)
                    logger.info(f"🔌 Сокет от родителя: {parent_socket}")
                    if parent_socket and not self.call_socket:
                        logger.info("🔄 Попытка установить сокет от родителя...")
                        self.set_call_socket(parent_socket)
                except Exception as e:
                    logger.error(f"❌ Ошибка получения сокета от родителя: {e}")
            else:
                logger.warning("❌ У родителя нет метода get_call_socket")
            
            # Детальная информация о сокете
            if self.call_socket:
                try:
                    logger.info(f"🔌 Тип сокета: {type(self.call_socket)}")
                    logger.info(f"🔌 Файловый дескриптор: {self.call_socket.fileno()}")
                    logger.info(f"🔌 Таймаут: {self.call_socket.gettimeout()}")
                    
                    # Проверяем состояние сокета
                    self.call_socket.settimeout(1.0)
                    try:
                        self.call_socket.send(b'')
                        logger.info("✅ Сокет готов к отправке данных")
                    except socket.error as e:
                        logger.error(f"❌ Сокет не готов к отправке: {e}")
                    
                    try:
                        peer_addr = self.call_socket.getpeername()
                        logger.info(f"🔌 Адрес подключения: {peer_addr}")
                    except socket.error as e:
                        logger.error(f"❌ Не удалось получить адрес подключения: {e}")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки сокета: {e}")
            else:
                logger.error("❌ Сокет не установлен в CallWindow!")
                
            # Собираем диагностическую информацию для пользователя
            diagnostic_info = []
            diagnostic_info.append(f"ID звонка: {self.call_id}")
            diagnostic_info.append(f"Тип: {'исходящий' if self.is_outgoing else 'входящий'}")
            diagnostic_info.append(f"Сокет установлен: {'ДА' if self.call_socket else 'НЕТ'}")
            diagnostic_info.append(f"Попыток установки: {self.socket_attempts}")
            
            if self.call_socket:
                diagnostic_info.append("✅ Сокет присутствует")
                try:
                    self.call_socket.send(b'')
                    diagnostic_info.append("✅ Сокет готов к работе")
                except:
                    diagnostic_info.append("❌ Сокет не готов к работе")
            else:
                diagnostic_info.append("❌ Сокет отсутствует")
                
            message = "\n".join(diagnostic_info)
            QMessageBox.information(self, "Расширенная диагностика сокета", message)
            
            logger.info("=" * 50)
            logger.info("🔍 ДИАГНОСТИКА ЗАВЕРШЕНА")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"❌ Ошибка расширенной диагностики: {e}")
            QMessageBox.critical(self, "Ошибка диагностики", f"Ошибка при диагностике: {e}")

    def auto_check_socket(self):
        """Автоматическая проверка и попытка установки сокета"""
        if self.call_socket or self.socket_set or not self.isVisible():
            return
            
        if self.socket_attempts >= self.max_socket_attempts:
            self.socket_check_timer.stop()
            return
            
        logger.info(f"🔄 Автопроверка сокета (попытка {self.socket_attempts + 1}/{self.max_socket_attempts})")
        self.socket_attempts += 1
        
        # Пытаемся получить сокет от родителя
        if self.parent() and hasattr(self.parent(), 'get_call_socket'):
            try:
                logger.info("🔧 Попытка получить сокет от родителя...")
                parent_socket = self.parent().get_call_socket(self.call_id)
                if parent_socket:
                    logger.info(f"✅ Получен сокет от родителя: {parent_socket}")
                    success = self.set_call_socket(parent_socket)
                    if success:
                        logger.info("✅ Сокет успешно установлен через автопроверку")
                        self.socket_check_timer.stop()
                        return
            except Exception as e:
                logger.error(f"❌ Ошибка получения сокета от родителя: {e}")
        
        # Если это исходящий звонок и сокет еще не установлен, показываем предупреждение
        if self.is_outgoing and self.socket_attempts == 2:
            logger.warning("⚠️ Сокет все еще не установлен для исходящего звонка")
            self.diagnostic_label.setText("⚠️ Ожидание установки соединения...")

    def set_call_socket(self, call_socket):
        """Установка сокета для звонка - ДОЛЖЕН ВЫЗЫВАТЬСЯ ПЕРЕД start_call"""
        try:
            logger.info(f"🔧 CallWindow.set_call_socket: попытка установить сокет для звонка {self.call_id}")
            
            # Детальная диагностика полученного сокета
            if call_socket is None:
                logger.error(f"❌ Попытка установить ПУСТОЙ сокет для звонка {self.call_id}")
                self.socket_status_label.setText("🔴 Сокет: ошибка (пустой)")
                return False

            # Проверяем тип и состояние сокета
            logger.info(f"🔧 Полученный сокет: {type(call_socket)}, {call_socket}")
            
            # Проверяем, что это действительно сокет
            if not hasattr(call_socket, 'send') or not hasattr(call_socket, 'recv'):
                logger.error(f"❌ Полученный объект не является сокетом: {call_socket}")
                self.socket_status_label.setText("🔴 Сокет: неверный тип")
                return False
            
            # Проверяем подключение
            try:
                # Сохраняем оригинальный timeout
                original_timeout = call_socket.gettimeout()
                call_socket.settimeout(2.0)  # Увеличиваем timeout для надежности
                
                # Пробуем отправить тестовый байт
                test_byte = b'P'
                sent = call_socket.send(test_byte)
                logger.info(f"🔧 Тестовый байт отправлен: {sent} байт")
                
                # Восстанавливаем timeout
                call_socket.settimeout(original_timeout)
                
            except socket.error as e:
                logger.error(f"❌ Сокет не подключен или ошибка отправки: {e}")
                self.socket_status_label.setText(f"🔴 Сокет: ошибка подключения")
                return False
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка проверки сокета: {e}")
                self.socket_status_label.setText(f"🔴 Сокет: ошибка проверки")
                return False
            
            # Устанавливаем сокет
            self.call_socket = call_socket
            self.socket_set = True
            
            
            # Обновляем UI
            self.socket_status_label.setText("🟢 Сокет: установлен и проверен")
            self.socket_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
            
            logger.info(f"✅ Сокет для звонка {self.call_id} успешно установлен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка установки сокета: {e}")
            self.socket_status_label.setText(f"🔴 Сокет: критическая ошибка")
            return False

    def check_socket_connection(self):
        """Проверить состояние сокета соединения"""
        try:
            if self.call_socket is None:
                return False
                
            # Проверяем, что сокет действительно подключен
            try:
                original_timeout = self.call_socket.gettimeout()
                self.call_socket.settimeout(0.5)
                # Простая проверка - пытаемся отправить пустой байт
                self.call_socket.send(b'')
                self.call_socket.settimeout(original_timeout)
                return True
            except (socket.error, OSError, AttributeError) as e:
                logger.debug(f"Сокет не подключен: {e}")
                return False
                
        except Exception as e:
            logger.debug(f"Ошибка проверки сокета: {e}")
            return False

    def check_socket_and_retry(self):
        """Проверить сокет и повторить попытку начала звонка"""
        if self.call_socket and not self.is_active:
            logger.info("🔧 Сокет теперь доступен, повторная попытка start_call...")
            self.start_call()
        else:
            logger.error("❌ Сокет все еще не доступен после ожидания")
            QMessageBox.critical(self, "Ошибка", 
                               "Соединение не установлено. Нельзя начать звонок.\n\n"
                               "Проверьте:\n"
                               "1. Сетевые настройки\n"
                               "2. Брандмауэр\n"
                               "3. Доступность портов")

    def populate_audio_devices(self):
        """Заполнение списков аудиоустройств"""
        try:
            import sounddevice as sd
            
            devices = sd.query_devices()
            
            self.input_device_combo.clear()
            self.output_device_combo.clear()
            
            # Добавляем опцию "Автовыбор"
            self.input_device_combo.addItem("Автовыбор", -1)
            self.output_device_combo.addItem("Автовыбор", -1)
            
            for i, device in enumerate(devices):
                device_name = f"{i}: {device['name']}"
                # Обрезаем длинные названия
                if len(device_name) > 60:
                    device_name = device_name[:57] + "..."
                    
                if device['max_input_channels'] > 0:
                    self.input_device_combo.addItem(device_name, i)
                    
                if device['max_output_channels'] > 0:
                    self.output_device_combo.addItem(device_name, i)
            
            # Устанавливаем текущие выбранные устройства или автовыбор
            if self.input_device is not None:
                index = self.input_device_combo.findData(self.input_device)
                if index >= 0:
                    self.input_device_combo.setCurrentIndex(index)
                else:
                    self.input_device_combo.setCurrentIndex(0)
            else:
                self.input_device_combo.setCurrentIndex(0)
                
            if self.output_device is not None:
                index = self.output_device_combo.findData(self.output_device)
                if index >= 0:
                    self.output_device_combo.setCurrentIndex(index)
                else:
                    self.output_device_combo.setCurrentIndex(0)
            else:
                self.output_device_combo.setCurrentIndex(0)
                
        except Exception as e:
            logger.error(f"Ошибка заполнения списка устройств: {e}")
            self.show_audio_error(f"Ошибка списка устройств: {e}")

    def apply_audio_devices(self):
        """Применение выбранных аудиоустройств"""
        try:
            input_index = self.input_device_combo.currentData()
            output_index = self.output_device_combo.currentData()
            
            # Если выбран автовыбор, устанавливаем None
            self.input_device = input_index if input_index != -1 else None
            self.output_device = output_index if output_index != -1 else None
            
            logger.info(f"🔊 Применены устройства: ввод={self.input_device}, вывод={self.output_device}")
            
            # Переинициализируем аудиопотоки если звонок активен
            if self.is_active and self.audio_initialized:
                self.stop_audio_streams()
                success = self.initialize_audio_streams()
                if success:
                    QMessageBox.information(self, "Успех", 
                                          "Аудиоустройства применены. Звонок продолжен с новыми устройствами.")
                else:
                    QMessageBox.warning(self, "Ошибка", 
                                      "Не удалось инициализировать аудио с выбранными устройствами.")
            else:
                # Просто тестируем гудки на новых устройствах
                self.test_call_tones()
                
            # Обновляем диагностику
            self.update_audio_status_display()
                              
        except Exception as e:
            logger.error(f"Ошибка применения аудиоустройств: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось применить устройства: {e}")

    def update_audio_status_display(self):
        """Обновление отображения статуса аудио"""
        if self.input_device is not None and self.output_device is not None:
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                input_name = devices[self.input_device]['name'] if self.input_device < len(devices) else "Unknown"
                output_name = devices[self.output_device]['name'] if self.output_device < len(devices) else "Unknown"
                
                # Обрезаем длинные названия
                if len(input_name) > 30:
                    input_name = input_name[:27] + "..."
                if len(output_name) > 30:
                    output_name = output_name[:27] + "..."
                    
                self.audio_status_label.setText(f"🔊 Ввод: {input_name}\n🔊 Вывод: {output_name}")
                self.audio_status_label.setStyleSheet("font-size: 11px; color: #27ae60;")
            except:
                self.audio_status_label.setText(f"🔊 Аудио: ввод {self.input_device}, вывод {self.output_device}")
                self.audio_status_label.setStyleSheet("font-size: 11px; color: #27ae60;")
        else:
            self.audio_status_label.setText("🔊 Аудио: автовыбор устройств")
            self.audio_status_label.setStyleSheet("font-size: 11px; color: #e67e22;")

    def test_call_tones(self):
        """Тестирование гудков звонка на текущих устройствах"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ГУДКОВ ЗВОНКА...")
            
            # Определяем устройство для теста
            test_device = self.output_device
            if test_device is None:
                # Если устройство не выбрано, используем автовыбор
                try:
                    default_output = sd.default.device[1] if sd.default.device else 0
                    test_device = default_output
                except:
                    test_device = 0
            
            # Создаем тон гудка (440 Гц)
            duration = 1.0
            sample_rate = 44100
            frequency = 440
            
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * frequency * t)
            
            # Тестируем на выбранном устройстве вывода
            logger.info(f"🔊 Воспроизведение гудка на устройстве {test_device}")
            sd.play(tone, sample_rate, device=test_device)
            sd.wait()
            
            logger.info("✅ Гудок воспроизведен")
            QMessageBox.information(self, "Тест гудков", 
                                  f"Гудок воспроизведен на устройстве {test_device}. Проверьте, слышен ли звук.")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования гудков: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось воспроизвести гудок: {e}")
            return False

    def test_media_connection(self):
        """Тестирование соединения с медиа-сервером"""
        try:
            logger.info("🔊 Тестирование соединения с медиа-сервером...")
            
            if not self.call_socket:
                logger.warning("⚠️ Сокет не установлен, тестируем прямое подключение")
                
                # Пробуем подключиться напрямую к медиа-серверу
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(5.0)
                
                try:
                    test_socket.connect(('localhost', 9100))
                    logger.info("✅ Успешное подключение к медиа-серверу")
                    
                    # Тестируем регистрацию
                    test_data = {
                        'call_id': f'test_{self.call_id}',
                        'action': 'register',
                        'username': self.username
                    }
                    test_socket.send(json.dumps(test_data).encode())
                    
                    # Ждем ответ
                    response = test_socket.recv(1024)
                    if response:
                        resp = json.loads(response.decode())
                        logger.info(f"✅ Ответ медиа-сервера: {resp}")
                    
                    test_socket.close()
                    return True
                
                except ConnectionRefusedError:
                    logger.error("❌ Не удалось подключиться к медиа-серверу")
                    QMessageBox.warning(self, "Ошибка", 
                                    "Медиа-сервер недоступен.\n"
                                    "Запустите: python simple_media_server.py")
                    return False
                except Exception as e:
                    logger.error(f"❌ Ошибка тестирования: {e}")
                    return False
            else:
                # Тестируем существующее соединение
                try:
                    # Проверяем сокет
                    self.call_socket.send(b'')
                    logger.info("✅ Сокет звонка работает")
                    
                    # Отправляем тестовые данные
                    test_data = b'test_packet'
                    sent = self.call_socket.send(test_data)
                    logger.info(f"✅ Отправлено {sent} тестовых байт")
                    
                    return True
                except Exception as e:
                    logger.error(f"❌ Сокет звонка не работает: {e}")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования медиа-соединения: {e}")
            return False



    def update_diagnostic_info(self):
        """Обновление диагностической информации"""
        current_time = time.time()
        
        # Обновляем статус сокета
        socket_ok = self.check_socket_connection()
        socket_status = "🟢" if socket_ok else "🔴"
        socket_text = "установлен" if socket_ok else "не установлен"
        self.socket_status_label.setText(f"{socket_status} Сокет: {socket_text}")
        self.socket_status_label.setStyleSheet(f"font-size: 12px; color: {'#27ae60' if socket_ok else '#e74c3c'};")
        
        if self.is_active:
            audio_status = "🔊" if self.audio_initialized else "🔇"
            
            info = f"{audio_status} Аудио | {socket_status} Сокет | Отпр: {self.sent_packets} | Получ: {self.received_packets}"
            self.diagnostic_label.setText(info)
            
            # Детальная диагностика каждые 5 секунд
            if current_time - self.last_audio_debug_time > 5:
                self.last_audio_debug_time = current_time
                self.debug_audio_streams()
        else:
            # Показываем информацию о состоянии когда звонок не активен
            if self.audio_available:
                if self.audio_initialized:
                    self.diagnostic_label.setText("✅ Аудио система готова")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
                else:
                    if not socket_ok:
                        self.diagnostic_label.setText("⚠️ Ожидание установки сокета...")
                        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
                    else:
                        self.diagnostic_label.setText("⚠️ Аудио система обнаружена, но не инициализирована")
                        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
            else:
                self.diagnostic_label.setText("❌ Аудио система недоступна")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
    
    def debug_audio_streams(self):
        """Детальная диагностика аудио потоков"""
        try:
            if not self.audio_initialized:
                self.detailed_diagnostic_label.setText("Аудио потоки не инициализированы")
                return
            
            import sounddevice as sd
            
            # Проверяем состояние потоков
            input_active = hasattr(self, 'input_stream') and self.input_stream and self.input_stream.active
            output_active = hasattr(self, 'output_stream') and self.output_stream and self.output_stream.active
            
            socket_ok = self.check_socket_connection()
            socket_status = "🟢" if socket_ok else "🔴"
            
            debug_info = f"Вход: {'🟢' if input_active else '🔴'} | Выход: {'🟢' if output_active else '🔴'} | Сокет: {socket_status}"
            
            # Проверяем уровень сигнала в буфере
            buffer_level = len(self.audio_buffer)
            buffer_status = "🟢" if buffer_level > 0 else "🔴"
            
            debug_info += f" | Буфер: {buffer_status} ({buffer_level})"
            
            self.detailed_diagnostic_label.setText(debug_info)
            logger.info(f"🔍 Детальная диагностика: {debug_info}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка детальной диагностики: {e}")

    def run_audio_diagnostic(self):
        """Запуск полной диагностики аудио системы"""
        try:
            logger.info("🔊 ЗАПУСК ПОЛНОЙ ДИАГНОСТИКИ АУДИО...")
            
            # Проверяем сокет
            socket_ok = self.check_socket_connection()
            if not socket_ok:
                QMessageBox.warning(self, "Диагностика", "Сокет не установлен. Сначала установите соединение.")
                return
            
            # Тест 1: Проверка доступности sounddevice
            try:
                import sounddevice as sd
                logger.info("✅ SoundDevice импортирован успешно")
            except ImportError as e:
                logger.error(f"❌ SoundDevice не установлен: {e}")
                self.show_audio_error("SoundDevice не установлен")
                return
            
            # Тест 2: Проверка устройств
            devices = sd.query_devices()
            logger.info(f"🔊 Найдено устройств: {len(devices)}")
            
            if len(devices) == 0:
                logger.error("❌ Аудио устройства не найдены")
                self.show_audio_error("Аудио устройства не найдены")
                return
            
            # Тест 3: Проверка устройств по умолчанию
            default_input = sd.default.device[0] if sd.default.device else None
            default_output = sd.default.device[1] if sd.default.device else None
            logger.info(f"🔊 Устройство ввода по умолчанию: {default_input}")
            logger.info(f"🔊 Устройство вывода по умолчанию: {default_output}")
            
            # Тест 4: Проверка воспроизведения
            playback_result = self.test_audio_playback()
            
            # Тест 5: Проверка записи
            record_result = self.test_audio_recording()
            
            # Тест 6: Проверка петли (запись -> воспроизведение)
            loopback_result = self.test_audio_loopback()
            
            # Обновление интерфейса на основе результатов
            if playback_result and record_result and loopback_result:
                self.audio_status_label.setText("🔊 Аудио: полная диагностика пройдена")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
                self.diagnostic_label.setText("✅ Аудио система работает корректно")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
            elif playback_result:
                self.audio_status_label.setText("🔊 Аудио: воспроизведение работает")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
                self.diagnostic_label.setText("⚠️ Воспроизведение работает, запись/петля нет")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
            else:
                self.audio_status_label.setText("🔇 Аудио: проблемы с системой")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
                self.diagnostic_label.setText("❌ Проблемы с аудио системой")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
                
        except Exception as e:
            logger.error(f"❌ Ошибка диагностики: {e}")
            self.show_audio_error(f"Ошибка диагностики: {e}")

    def test_audio_loopback(self):
        """Тестирование петли записи-воспроизведения"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ПЕТЛИ ЗАПИСЬ-ВОСПРОИЗВЕДЕНИЕ...")
            
            # Определяем устройство для теста
            test_device = self.input_device if self.input_device is not None else self.output_device
            if test_device is None:
                try:
                    default_device = sd.default.device[0] if sd.default.device else 0
                    test_device = default_device
                except:
                    test_device = 0
            
            try:
                duration = 3.0
                sample_rate = 44100
                
                logger.info(f"🎤 Запись тестового сигнала на устройстве {test_device}...")
                
                # Записываем аудио с микрофона
                recording = sd.rec(int(duration * sample_rate), 
                                 samplerate=sample_rate, 
                                 channels=1,
                                 device=test_device)
                sd.wait()
                
                logger.info(f"✅ Записано {len(recording)} сэмплов")
                
                # Воспроизводим записанное аудио
                logger.info(f"🔊 Воспроизведение записанного сигнала на устройстве {test_device}...")
                sd.play(recording, sample_rate, device=test_device)
                sd.wait()
                
                logger.info("✅ Петля запись-воспроизведение работает")
                return True
                
            except Exception as e:
                logger.error(f"❌ Петля не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования петли: {e}")
            return False

    def test_audio_playback(self):
        """Тестирование воспроизведения на выбранном устройстве"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ВОСПРОИЗВЕДЕНИЯ...")
            
            # Определяем устройство для теста
            test_device = self.output_device
            if test_device is None:
                try:
                    default_output = sd.default.device[1] if sd.default.device else 0
                    test_device = default_output
                except:
                    test_device = 0
            
            try:
                # Создаем простой тестовый тон
                duration = 2.0
                frequency = 440
                sample_rate = 44100
                
                t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
                tone = 0.3 * np.sin(2 * np.pi * frequency * t)
                
                # Пробуем воспроизвести на выбранном устройстве
                sd.play(tone, sample_rate, device=test_device)
                sd.wait()
                
                logger.info(f"✅ Устройство {test_device} работает: Воспроизведение OK")
                return True
                
            except Exception as e:
                logger.error(f"❌ Устройство {test_device} не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования воспроизведения: {e}")
            return False

    def test_audio_recording(self):
        """Тестирование записи на выбранном устройстве"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ЗАПИСИ...")
            
            # Определяем устройство для теста
            test_device = self.input_device
            if test_device is None:
                try:
                    default_input = sd.default.device[0] if sd.default.device else 0
                    test_device = default_input
                except:
                    test_device = 0
            
            try:
                # Пробуем записать короткий фрагмент
                duration = 2.0
                sample_rate = 44100
                
                recording = sd.rec(int(duration * sample_rate), 
                                 samplerate=sample_rate, 
                                 channels=1,
                                 device=test_device)
                sd.wait()
                
                # Проверяем, что записаны не только нули
                max_amplitude = np.max(np.abs(recording))
                logger.info(f"✅ Запись с устройства {test_device} работает: {len(recording)} сэмплов, макс. амплитуда: {max_amplitude:.4f}")
                
                if max_amplitude < 0.001:
                    logger.warning("⚠️ Записаны только тихие сигналы или тишина")
                
                return True
                
            except Exception as e:
                logger.warning(f"❌ Запись с устройства {test_device} не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования записи: {e}")
            return False

    def safe_accept_call(self):
        """Безопасное принятие звонка с защитой от многократного нажатия"""
        if self.accept_button_clicked:
            logger.warning(f"Попытка повторного принятия звонка {self.call_id}")
            return
            
        # Проверяем наличие сокета перед принятием
        if not self.call_socket:
            QMessageBox.warning(self, "Ошибка", "Соединение не установлено. Нельзя принять звонок.")
            return
            
        self.accept_button_clicked = True
        self.accept_call()
    
    def safe_reject_call(self):
        """Безопасное отклонение звонка с защитой от многократного нажатия"""
        if self.accept_button_clicked:
            logger.warning(f"Попытка повторного отклонения звонка {self.call_id}")
            return
            
        self.accept_button_clicked = True
        self.reject_call()
        
    def detect_audio_system(self):
        """Определение звуковой системы"""
        try:
            import sounddevice as sd
            
            logger.info("🔊 ДИАГНОСТИКА АУДИО СИСТЕМЫ...")
            
            # Получаем информацию об устройствав
            devices = sd.query_devices()
            default_input = sd.default.device[0] if sd.default.device else None
            default_output = sd.default.device[1] if sd.default.device else None
            
            logger.info(f"🔊 Найдено аудио устройств: {len(devices)}")
            logger.info(f"🔊 Устройство ввода по умолчанию: {default_input}")
            logger.info(f"🔊 Устройство вывода по умолчанию: {default_output}")
            
            # Определяем тип аудиосистемы
            self.audio_system_type = "Unknown"
            if any('pipewire' in device['name'].lower() for device in devices):
                self.audio_system_type = "PipeWire"
            elif any('pulse' in device['name'].lower() for device in devices):
                self.audio_system_type = "PulseAudio"
            elif any('alsa' in device['name'].lower() for device in devices):
                self.audio_system_type = "ALSA"
            
            logger.info(f"🔊 Определена аудиосистема: {self.audio_system_type}")
            
            # Автоматический выбор устройств на основе системы
            self.auto_select_audio_devices(self.audio_system_type)
            
            # Заполняем списки устройств в UI
            self.populate_audio_devices()
            
            # Проверяем доступность аудио устройств
            if len(devices) > 0:
                self.audio_available = True
                
                # Быстрый тест воспроизведения
                test_result = self.test_audio_playback()
                
                audio_system_info = f"✅ {self.audio_system_type} система ({len(devices)} устройств)"
                
                if test_result:
                    self.audio_status_label.setText("🔊 Аудио: система готова")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
                    self.diagnostic_label.setText("✅ Аудио система работает")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
                else:
                    self.audio_status_label.setText("🔇 Аудио: есть проблемы")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
                    self.diagnostic_label.setText("⚠️ Нажмите 'Тест аудио' для диагностики")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
                    
            else:
                self.audio_available = False
                audio_system_info = "❌ Аудио устройства не найдены"
                self.audio_status_label.setText("🔇 Аудио: устройства не найдены")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
                self.diagnostic_label.setText("❌ Аудио устройства не найдены")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
                
            self.audio_system_label.setText(audio_system_info)
            logger.info(f"🔊 Результат диагностики: {audio_system_info}")
            
        except ImportError:
            self.audio_available = False
            self.audio_system_label.setText("❌ SoundDevice не установлен")
            self.audio_status_label.setText("🔇 Аудио: библиотека не установлена")
            self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
            self.diagnostic_label.setText("❌ Установите sounddevice: pip install sounddevice")
            self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
            logger.warning("SoundDevice не установлен")
        except Exception as e:
            self.audio_available = False
            self.audio_system_label.setText(f"❌ Ошибка аудио: {str(e)}")
            self.audio_status_label.setText("🔇 Аудио: ошибка инициализации")
            self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
            self.diagnostic_label.setText(f"❌ Ошибка: {str(e)}")
            self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
            logger.error(f"Ошибка инициализации аудио: {e}")

    def auto_select_audio_devices(self, audio_system_type):
        """Автоматический выбор аудиоустройств в зависимости от системы"""
        try:
            import sounddevice as sd
            
            devices = sd.query_devices()
            
            if audio_system_type == "PipeWire":
                self.find_pipewire_devices(devices)
            elif audio_system_type == "PulseAudio":
                self.find_pulseaudio_devices(devices)
            else:
                self.find_fallback_devices(devices)
                
        except Exception as e:
            logger.error(f"Ошибка автоматического выбора устройств: {e}")
            self.input_device = None
            self.output_device = None

    def find_pipewire_devices(self, devices):
        """Поиск устройств для PipeWire"""
        logger.info("🔊 Поиск устройств для PipeWire...")
        input_found = False
        output_found = False
        
        for i, device in enumerate(devices):
            name_lower = device['name'].lower()
            
            if ('analog' in name_lower or 'default' in name_lower or 
                'built-in' in name_lower or 'hdmi' not in name_lower):
                
                if device['max_input_channels'] > 0 and not input_found:
                    self.input_device = i
                    input_found = True
                    logger.info(f"🔊 PipeWire: выбрано устройство ввода {i}: {device['name']}")
                
                if device['max_output_channels'] > 0 and not output_found:
                    self.output_device = i
                    output_found = True
                    logger.info(f"🔊 PipeWire: выбрано устройство вывода {i}: {device['name']}")
                
                if input_found and output_found:
                    break
        
        if not input_found:
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    self.input_device = i
                    logger.info(f"🔊 PipeWire: резервное устройство ввода {i}: {device['name']}")
                    break
                    
        if not output_found:
            for i, device in enumerate(devices):
                if device['max_output_channels'] > 0:
                    self.output_device = i
                    logger.info(f"🔊 PipeWire: резервное устройство вывода {i}: {device['name']}")
                    break

    def find_pulseaudio_devices(self, devices):
        """Поиск устройств для PulseAudio"""
        logger.info("🔊 Поиск устройств для PulseAudio...")
        input_found = False
        output_found = False
        
        for i, device in enumerate(devices):
            name_lower = device['name'].lower()
            
            if ('pulse' in name_lower or 'default' in name_lower or
                'analog' in name_lower or 'built-in' in name_lower):
                
                if device['max_input_channels'] > 0 and not input_found:
                    self.input_device = i
                    input_found = True
                    logger.info(f"🔊 PulseAudio: выбрано устройство ввода {i}: {device['name']}")
                    
                if device['max_output_channels'] > 0 and not output_found:
                    self.output_device = i
                    output_found = True
                    logger.info(f"🔊 PulseAudio: выбрано устройство вывода {i}: {device['name']}")
                
                if input_found and output_found:
                    break
        
        if not input_found:
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    self.input_device = i
                    logger.info(f"🔊 PulseAudio: резервное устройство ввода {i}: {device['name']}")
                    break
                    
        if not output_found:
            for i, device in enumerate(devices):
                if device['max_output_channels'] > 0:
                    self.output_device = i
                    logger.info(f"🔊 PulseAudio: резервное устройство вывода {i}: {device['name']}")
                    break

    def find_fallback_devices(self, devices):
        """Резервный поиск устройств"""
        logger.info("🔊 Резервный поиск аудиоустройств...")
        input_found = False
        output_found = False
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0 and not input_found:
                self.input_device = i
                input_found = True
                logger.info(f"🔊 Fallback: устройство ввода {i}: {device['name']}")
                
            if device['max_output_channels'] > 0 and not output_found:
                self.output_device = i
                output_found = True
                logger.info(f"🔊 Fallback: устройство вывода {i}: {device['name']}")
            
            if input_found and output_found:
                break
        
        if not input_found or not output_found:
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0 and device['max_output_channels'] > 0:
                    if not input_found:
                        self.input_device = i
                        input_found = True
                    if not output_found:
                        self.output_device = i
                        output_found = True
                    logger.info(f"🔊 Fallback: комбинированное устройство {i}: {device['name']}")
                    break
    
    def start_call(self):
        """Начать звонок (после принятия)"""
        try:
            logger.info(f"🔊 Безопасный запуск звонка {self.call_id}")
            
            # Проверяем наличие сокета
            if not self.call_socket:
                logger.warning("⚠️ Сокет не установлен, пробуем получить от родителя")
                
                if self.parent() and hasattr(self.parent(), 'get_call_socket'):
                    try:
                        call_socket = self.parent().get_call_socket(self.call_id)
                        if call_socket:
                            success = self.set_call_socket(call_socket)
                            if success:
                                logger.info("✅ Сокет получен от родителя")
                            else:
                                logger.error("❌ Не удалось установить сокет от родителя")
                        else:
                            logger.error("❌ Родитель не вернул сокет")
                    except Exception as e:
                        logger.error(f"❌ Ошибка получения сокета от родителя: {e}")
            
            # Если сокета все еще нет, показываем предупреждение
            if not self.call_socket:
                logger.warning("⚠️ Звонок запускается без сокета - будет работать в локальном режиме")
                self.status_label.setText("🔇 Локальный режим (без сетевого аудио)")
                self.status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
            
            # Запускаем звонок
            self.start_call()
            
        except Exception as e:
            logger.error(f"❌ Ошибка безопасного запуска звонка: {e}")

    def safe_start_call(self):
        """Безопасный запуск звонка с проверкой сокета"""
        try:
            logger.info(f"🔊 Безопасный запуск звонка {self.call_id}")
            
            # Проверяем наличие сокета
            if not self.call_socket:
                logger.warning("⚠️ Сокет не установлен, работаем в локальном режиме")
                self.status_label.setText("🔇 Локальный режим (без сетевого аудио)")
                self.status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
            
            # Запускаем звонок
            self.start_call()
            
        except Exception as e:
            logger.error(f"❌ Ошибка безопасного запуска звонка: {e}")

    def initialize_audio_streams(self):
        """Инициализация аудио потоков на выбранных устройствах"""
        try:
            if self.audio_initialized:
                logger.info("⚠️ Аудио уже инициализировано")
                return True

            # ✅ ВАЖНАЯ ПРОВЕРКА: убедимся, что сокет установлен
            if not self.call_socket:
                logger.error("❌ ⚠️ Сокет не установлен, инициализируем локальное аудио")
                # Создаем локальные аудио потоки без сетевой передачи
                return self.initialize_local_audio()
            else:    
                self.show_audio_error("Соединение не установлено")
                return False

            import sounddevice as sd
            import numpy as np

            logger.info("🔧 Инициализация аудио потоков...")
            
            # Определяем устройства для использования
            input_device = self.input_device
            output_device = self.output_device
            
            # Если устройства не выбраны, используем автовыбор
            if input_device is None:
                try:
                    default_input = sd.default.device[0] if sd.default.device else 0
                    input_device = default_input
                except:
                    input_device = 0
                    
            if output_device is None:
                try:
                    default_output = sd.default.device[1] if sd.default.device else 0
                    output_device = default_output
                except:
                    output_device = 0
            
            logger.info(f"🔧 Используемые устройства: ввод={input_device}, вывод={output_device}")
            
            # Пробуем разные конфигурации
            configs = [
                {'samplerate': 44100, 'blocksize': 1024},
                {'samplerate': 22050, 'blocksize': 512},
                {'samplerate': 16000, 'blocksize': 256},
            ]
            
            for config in configs:
                try:
                    logger.info(f"🔧 Попытка конфигурации: {config}")
                    
                    # ✅ БЕЗОПАСНЫЙ Callback для захвата аудио с микрофона
                    def input_callback(indata, frames, time, status):
                        if status:
                            logger.debug(f"Аудио входной статус: {status}")
                
                        try:
                            # ✅ ПРОВЕРЯЕМ ВСЕ УСЛОВИЯ ПЕРЕД ОТПРАВКОЙ
                            if (self.call_socket and 
                                self.is_active and self.audio_initialized):
                                # Преобразуем в байты и отправляем
                                audio_data = indata.astype(np.float32).tobytes()
                                success = self.send_audio_data(audio_data)
                                if success:
                                    self.sent_packets += 1
                                    if self.sent_packets % 50 == 0:
                                        logger.info(f"🎤 Отправлено пакетов: {self.sent_packets}")
                        except Exception as e:
                            logger.debug(f"Ошибка в input callback: {e}")

                    # ✅ БЕЗОПАСНЫЙ Callback для воспроизведения аудио
                    def output_callback(outdata, frames, time, status):
                        if status:
                            logger.debug(f"Аудио выходной статус: {status}")
                
                        try:
                            # Получаем данные из буфера
                            audio_data = self.get_audio_data(frames)
                            if audio_data is not None:
                                outdata[:] = audio_data.reshape(-1, 1)
                                self.received_packets += 1
                                if self.received_packets % 50 == 0:
                                    logger.info(f"🔊 Воспроизведено пакетов: {self.received_packets}")
                            else:
                                outdata.fill(0)    
                        except Exception as e:
                            logger.debug(f"Ошибка в output callback: {e}")
                            outdata.fill(0)

                    # Создаем потоки с указанием выбранных устройств
                    self.input_stream = sd.InputStream(
                        device=input_device,
                        samplerate=config['samplerate'],
                        blocksize=config['blocksize'],
                        channels=self.channels,
                        callback=input_callback,
                        dtype=np.float32
                    )
                    
                    self.output_stream = sd.OutputStream(
                        device=output_device,
                        samplerate=config['samplerate'],
                        blocksize=config['blocksize'],
                        channels=self.channels,
                        callback=output_callback,
                        dtype=np.float32
                    )

                    # Запускаем потоки
                    self.input_stream.start()
                    self.output_stream.start()
                    
                    # Обновляем параметры
                    self.sample_rate = config['samplerate']
                    self.blocksize = config['blocksize']
                    
                    self.audio_initialized = True
                    logger.info(f"✅ Аудио потоки успешно инициализированы с конфигурацией: {config}")
                    
                    # ✅ ЗАПУСКАЕМ ПРИЕМНИК ДАННЫХ ПОСЛЕ УСПЕШНОЙ ИНИЦИАЛИЗАЦИИ
                    self.start_audio_receiver()
                    
                    return True
                    
                except Exception as e:
                    logger.warning(f"❌ Конфигурация {config} не сработала: {e}")
                    self.stop_audio_streams()
                    continue
            
            logger.error("❌ Все конфигурации аудио не сработали")
            return False
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка инициализации аудио: {e}")
            self.show_audio_error(f"Аудио недоступно: {e}")
            return False

    def get_audio_data(self, frames):
        """Получение аудио данных из буфера"""
        if not self.is_active:
            return None
        try:
            with self.audio_buffer_lock:
                if self.audio_buffer:
                    data = self.audio_buffer.pop(0)
                    if len(data) < frames:
                        padded_data = np.zeros(frames, dtype=np.float32)
                        padded_data[:len(data)] = data
                        return padded_data
                    return data[:frames]
            return None
        except Exception as e:
            logger.debug(f"Ошибка получения аудио данных: {e}")
            return None

    def send_audio_data(self, audio_data):
        """Отправка аудио данных с проверкой соединения"""
        try:
            if not self.call_socket or not self.is_active or not self.audio_initialized:
                return False

            # Проверяем что сокет еще подключен
            try:
                self.call_socket.send(b'')
            except socket.error:
                logger.warning("Сокет звонка отключен")
                self.is_active = False
                return False
            
            # Добавляем заголовок с размером данных
            data_size = len(audio_data)
            header = struct.pack('I', data_size)
            full_data = header + audio_data
        
            # Отправляем данные
            sent = self.call_socket.send(full_data)
            return sent > 0
            
        except Exception as e:
            logger.debug(f"🔊 Ошибка отправки аудио данных: {e}")
            return False

    def receive_audio_data(self):
        """Прием аудио данных из сокета"""
        try:
            if self.call_socket and self.is_active and self.audio_initialized:
                
                # Устанавливаем таймаут для неблокирующего чтения
                self.call_socket.settimeout(0.1)
        
                # Читаем заголовок с размером данных
                header = self.call_socket.recv(4)
                if not header or len(header) < 4:
                    return
            
                data_size = struct.unpack('I', header)[0]
    
                # Читаем аудио данные
                audio_data = b''
                while len(audio_data) < data_size:
                    chunk = self.call_socket.recv(min(4096, data_size - len(audio_data)))
                    if not chunk:
                        break
                    audio_data += chunk
        
                if len(audio_data) == data_size:
                    # Преобразуем байты в numpy array
                    audio_array = np.frombuffer(audio_data, dtype=np.float32)
                
                    # Добавляем в буфер с ограничением размера
                    with self.audio_buffer_lock:
                        if len(self.audio_buffer) < self.buffer_size:
                            self.audio_buffer.append(audio_array)
                        else:
                            self.audio_buffer.pop(0)
                            self.audio_buffer.append(audio_array)
 
            else:
                logger.warning("🔊 Не могу принять аудио: нет сокета или поток не инициализирован")
                       
        except socket.timeout:
            pass
        except Exception as e:
            if self.is_active:
                logger.debug(f"Ошибка приема аудио данных: {e}")

    def start_audio_receiver(self):
        """Запуск потока для приема аудио данных"""
        def audio_receiver():
            logger.info("Запуск приемника аудио данных")
            while self.is_active and self.call_socket:
                try:
                    self.receive_audio_data()
                except Exception as e:
                    if self.is_active:
                        logger.debug(f"Ошибка в аудио приемнике: {e}")
                    break
            logger.info("Приемник аудио данных остановлен")

        self.audio_receiver_thread = threading.Thread(target=audio_receiver, daemon=True)
        self.audio_receiver_thread.start()

    def stop_audio_streams(self):
        """Остановка аудио-потоков"""
        try:
            logger.info(f"🔴 Остановка аудио потоков для звонка {self.call_id}")
            self.audio_initialized = False 
            self.is_active = False

            if hasattr(self, 'input_stream') and self.input_stream is not None:
                try:
                    self.input_stream.stop()
                    self.input_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки input stream: {e}")
                self.input_stream = None
                
            if hasattr(self, 'output_stream') and self.output_stream is not None:
                try:
                    self.output_stream.stop()
                    self.output_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки output stream: {e}")
                self.output_stream = None

            with self.audio_buffer_lock:
                self.audio_buffer.clear()
            
            logger.info(f"✅ Аудио потоки для звонка {self.call_id} остановлены")
                
        except Exception as e:
            logger.debug(f"Ошибка остановки аудио потоков: {e}")
    
    def update_duration(self):
        """Обновление отображения длительности звонка"""
        try:
            if hasattr(self, 'call_start_time') and self.is_active:
                self.call_duration = int(time.time() - self.call_start_time)
                minutes = self.call_duration // 60
                seconds = self.call_duration % 60
                self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
        except Exception as e:
            logger.debug(f"Ошибка обновления длительности: {e}")
    
    def accept_call(self):
        """Принять входящий звонок"""
        try:
            if self.is_active:
                logger.warning(f"Звонок {self.call_id} уже принят")
                return
                
            # Проверяем сокет перед принятием
            if not self.call_socket:
                logger.error(f"❌ Не могу принять звонок {self.call_id}: сокет не установлен")
                QMessageBox.critical(self, "Ошибка", 
                                   "Соединение не установлено. Нельзя принять звонок.\n\n"
                                   "Убедитесь, что сокет был установлен через set_call_socket() перед принятием звонка.")
                return

            self.is_active = True
            self.status_label.setText("Звонок принят")
            
            # Скрываем кнопки принятия/отклонения
            self.accept_button.setVisible(False)
            self.reject_button.setVisible(False)
            
            # Показываем кнопку завершения
            self.end_button = QPushButton("📞 Завершить")
            self.end_button.setFixedHeight(45)
            self.end_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.end_button.clicked.connect(self.end_call)
            self.layout().addWidget(self.end_button)
            
            # Запускаем звонок
            self.start_call()
            
            # Отправляем сигнал о принятии звонка
            self.call_accepted.emit(self.call_id)
            
            logger.info(f"Звонок {self.call_id} принят")
            
        except Exception as e:
            logger.error(f"Ошибка принятия звонка: {e}")
    
    def reject_call(self):
        """Отклонить входящий звонок"""
        try:
            self.status_label.setText("Звонок отклонен")
            self.call_rejected.emit(self.call_id)
            self.close()
            
            logger.info(f"Звонок {self.call_id} отклонен")
            
        except Exception as e:
            logger.error(f"Ошибка отклонения звонка: {e}")
    
    def end_call(self):
        """Завершить активный звонок"""
        if getattr(self, 'call_ended_emitted', False):
            return

        try:
            self.is_active = False
            self.call_ended_emitted = True
            self.duration_timer.stop()
            self.diagnostic_timer.stop()
            self.socket_check_timer.stop()
            self.stop_audio_streams()
            self.call_ended.emit(self.call_id)
            
            logger.info(f"Звонок {self.call_id} завершен")
            
        except Exception as e:
            logger.error(f"Ошибка завершения звонка: {e}")
    
    def show_audio_error(self, message):
        """Показать ошибку аудио"""
        self.diagnostic_label.setText(f"Ошибка: {message}")
        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        try:
            logger.info(f"Закрытие окна звонка {self.call_id}")
            self.is_active = False
        
            # Останавливаем все таймеры
            try:
                if hasattr(self, 'duration_timer') and self.duration_timer.isActive():
                    self.duration_timer.stop()
            except:
                pass
            
            try:
                if hasattr(self, 'diagnostic_timer') and self.diagnostic_timer.isActive():
                    self.diagnostic_timer.stop()
            except:
                pass
            
            try:
                if hasattr(self, 'socket_check_timer') and self.socket_check_timer.isActive():
                    self.socket_check_timer.stop()
            except:
                pass
            
            # Останавливаем аудио потоки
            self.stop_audio_streams()
        
            # Закрываем сокет
            try:
                if self.call_socket:    
                    self.call_socket.close()
            except:
                pass
                
            # Отправляем сигнал о завершении только один раз
            if not getattr(self, 'call_ended_emitted', False):
                try:
                    self.call_ended.emit(self.call_id)
                    self.call_ended_emitted = True
                    logger.info(f"✅ Сигнал завершения звонка {self.call_id} отправлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сигнала завершения: {e}")
            event.accept()
            logger.info(f"Окно звонка {self.call_id} закрыто")
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при закрытии окна звонка: {e}")
            event.accept()