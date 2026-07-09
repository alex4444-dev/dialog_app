import sys
import os
import queue
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QMessageBox,
                             QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import  QRadialGradient, QPalette, QColor, QPainter, QPixmap
import logging
import time
import struct
import threading
import socket
import numpy as np
import json
import sounddevice as sd
from ui.dialogs import show_question_dialog
            

MAX_AUDIO_PACKET_SIZE = 65536  # до 4096 сэмплов float32
        

logger = logging.getLogger('dialog_gui')

class CallWindow(QWidget):
    call_ended = pyqtSignal(str)
    call_accepted = pyqtSignal(str)
    call_rejected = pyqtSignal(str)
    call_started = pyqtSignal(str)
    connection_established = pyqtSignal()
    
    def __init__(self, username, call_type, call_id, is_outgoing=True, parent=None, input_device=None, output_device=None, sound_manager=None):
        super().__init__(parent)
        self.username = username
        self.call_type = call_type
        self.call_id = call_id
        self.is_outgoing = is_outgoing
        self.socket_set = False
        self.input_device = input_device   # теперь сохраняем переданные устройства
        self.output_device = output_device
        self.sound_manager = sound_manager
        self._recv_buffer = b''   # буфер для приёма данных

        logger.info(f"🔊 CallWindow.__init__: Создание окна для {username}, тип: {call_type}, исходящий: {is_outgoing}")

        self.is_active = False
        self.call_duration = 0
        self.audio_initialized = False
        self.call_ended_emitted = False
        self.accept_button_clicked = False
        self.muted = False
        self.send_audio_active = True
        
        # Аудио параметры
        self.sample_rate = 44100
        self.channels = 1
        self.dtype = 'float32'
        self.blocksize = 4096
        
        # Буфер для аудио данных
        self.audio_buffer = queue.Queue(maxsize=100)
        
        # Счетчики для диагностики
        self.sent_packets = 0
        self.received_packets = 0
        
        # Сокет для звонка
        self.call_socket = None
        self.socket_set = False
        self.socket_attempts = 0
        self.max_socket_attempts = 3
        
        # Флаги для отслеживания состояния
        self.secure_mode = False
        self.audio_receiver_running = False
        self.audio_receiver_thread = None
        self.local_mode = False
        self._closing_by_network = False  # Для предотвращения двойной отправки сигнала
        
        # Сначала инициализируем UI
        self.init_ui()

        # Инициализируем таймеры
        self.socket_check_timer = QTimer()
        self.socket_check_timer.timeout.connect(self.auto_check_socket)
              
        # Запускаем проверку сокета (для исходящих звонков)
        if is_outgoing:
            QTimer.singleShot(1000, self.socket_check_timer.start)  # Запустить через секунду

        self.show()  
        self.raise_()  
        self.activateWindow()  

        logger.info(f"🔊 CallWindow создано успешно")
            
    def init_ui(self):
        """Инициализация интерфейса окна звонка"""
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"📞 Звонок с {self.username}")
        self.setFixedSize(650, 480)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        # Главный layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Заголовок
        title_text = "Исходящий звонок" if self.is_outgoing else "Входящий звонок"
        self.title_label = QLabel(f"📞 {title_text}")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        self.title_label.setWordWrap(True)
        main_layout.addWidget(self.title_label)

        # Аватар
        self.avatar_label = QLabel()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(script_dir, "assets", "img", "background.png")
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.avatar_label.setPixmap(scaled)
            self.avatar_label.setFixedSize(scaled.size())
            self.avatar_label.setVisible(True)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(self.avatar_label, 0, Qt.AlignCenter)

        # Информация о звонке
        info_label = QLabel(f"Пользователь: {self.username}")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 14px; color: #ffffff; margin-bottom: 5px;")
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        # Индикатор состояния аудио
        self.audio_status_label = QLabel("🔇 Аудио: проверка...")
        self.audio_status_label.setAlignment(Qt.AlignCenter)
        self.audio_status_label.setStyleSheet("font-size: 16px; color: #FFFFFF; margin: 5px 0;")
        self.audio_status_label.setWordWrap(True)
        main_layout.addWidget(self.audio_status_label)

        # Таймер звонка
        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.duration_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #FFFFFF; background-color: transparent; padding: 3px; margin: 3px 0;")
        self.duration_label.setVisible(False)
        main_layout.addWidget(self.duration_label)

        # Статус звонка
        self.status_label = QLabel("Набор номера..." if self.is_outgoing else "Входящий вызов...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; color: #ffffff; margin: 10px 0; font-weight: 500; padding: 5px; background-color: transparent;")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # Растягивающийся элемент для выравнивания
        main_layout.addStretch(1)

        # --- Кнопки управления звонком ---
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)

        # start_button – всегда создаём, но показываем только для исходящего
        self.start_button = QPushButton("📞 Начать звонок")
        self.start_button.clicked.connect(self.start_call)
        self.start_button.setStyleSheet("""
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
        if self.is_outgoing:
            buttons_layout.addWidget(self.start_button)
        else:
            self.start_button.hide()

        # cancel_button – только для исходящего
        self.cancel_button = QPushButton("❌ Отмена")
        self.cancel_button.clicked.connect(self.cancel_call)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        if self.is_outgoing:
            buttons_layout.addWidget(self.cancel_button)
        else:
            self.cancel_button.hide()

        # Кнопка видеозвонка (только для исходящих)
        self.video_button = QPushButton("📹 Видеозвонок")
        self.video_button.setFixedHeight(45)
        self.video_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.video_button.clicked.connect(self.upgrade_to_video)
        if self.is_outgoing:
            buttons_layout.addWidget(self.video_button)
        else:
            self.video_button.hide()

        # Кнопки для входящего звонка
        self.accept_button = QPushButton("✅ Принять")
        self.accept_button.clicked.connect(self.accept_call)
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
        if not self.is_outgoing:
            buttons_layout.addWidget(self.accept_button)
        else:
            self.accept_button.hide()

        self.reject_button = QPushButton("❌ Отклонить")
        self.reject_button.clicked.connect(self.reject_call)
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
        if not self.is_outgoing:
            buttons_layout.addWidget(self.reject_button)
        else:
            self.reject_button.hide()

        main_layout.addLayout(buttons_layout)

        # --- Активные кнопки (для активного звонка) ---
        active_buttons_layout = QHBoxLayout()
        self.mute_button = QPushButton("🔊 Микрофон вкл")
        self.mute_button.clicked.connect(self.toggle_mute)
        self.mute_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        active_buttons_layout.addWidget(self.mute_button)

        self.end_button = QPushButton("📞 Завершить звонок")
        self.end_button.clicked.connect(self.end_call)
        self.end_button.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e68900; }
        """)
        active_buttons_layout.addWidget(self.end_button)

        self.active_buttons_widget = QWidget()
        self.active_buttons_widget.setLayout(active_buttons_layout)
        self.active_buttons_widget.hide()
        main_layout.addWidget(self.active_buttons_widget)

        # Прогресс-бар (анимация ожидания)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setFixedHeight(6)
        main_layout.addWidget(self.progress_bar)

        # Таймер для обновления длительности
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_duration)

        self.setLayout(main_layout)

    def toggle_mute(self):
        """Включение/выключение микрофона"""
        self.muted = not self.muted
        if self.muted:
            logger.info("🔇 Микрофон выключен")
            if hasattr(self, 'status_label'):
                self.mute_button.setText("🔇 Микрофон выкл")
        else:
            logger.info("🎤 Микрофон включён")
            if hasattr(self, 'status_label'):
                self.mute_button.setText("🔊 Микрофон вкл")
            
    def set_call_socket(self, call_socket):
        try:
            if call_socket is None:
                return False
            # Определяем тип сокета
            if hasattr(call_socket, 'recv') and hasattr(call_socket, 'send'):
                # Это может быть как обычный socket, так и SecureChannel
                # Если у объекта есть метод fileno() и он возвращает int, то это обычный socket
                if hasattr(call_socket, 'fileno'):
                    self.secure_mode = False
                else:
                    # Предполагаем, что это SecureChannel (у него нет fileno)
                    self.secure_mode = True
            self.call_socket = call_socket
            if hasattr(call_socket, 'settimeout'):
                call_socket.settimeout(0.5)
            else:
                # Если это обычный сокет
                try:
                    call_socket.settimeout(0.5)   # таймаут 0.5 сек
                except:
                    pass
            self.socket_set = True
            self.local_mode = False
            self.status_label.setText("🟢 Соединение установлено")
            if self.is_active and not self.audio_initialized:
                QTimer.singleShot(100, self._do_start_call)
            return True
        except Exception as e:
            logger.error(f"Ошибка установки сокета: {e}")
            return False

    def auto_check_socket(self):
        """Автоматическая проверка и попытка установки сокета"""
        if self.call_socket or self.socket_set or not self.isVisible() or self.local_mode:
            return
        # Получаем сокет от родителя (если есть метод)
        if self.parent() and hasattr(self.parent(), 'get_call_socket'):
            parent_socket = self.parent().get_call_socket(self.call_id)
            if parent_socket:
                self.set_call_socket(parent_socket)
                self.socket_check_timer.stop()
                return
        self.socket_attempts += 1
        if self.socket_attempts >= self.max_socket_attempts:
            self.socket_check_timer.stop()
            self.local_mode = True
            self.status_label.setText("⚠️ Локальный режим (без сети)")        
           
    def accept_call(self):
        try:
            if self.sound_manager:
                self.sound_manager.stop()
            self.accept_button.hide()
            self.reject_button.hide()
            self.active_buttons_widget.show()
            self.duration_label.setVisible(True)
            self.progress_bar.hide()
            self.is_active = True

            # Если сокета ещё нет – ждём
            if not self.call_socket:
                self.status_label.setText("⏳ Ожидание соединения...")
                # Запускаем проверку с повторами
                self.accept_retry_count = 0
                self.check_socket_for_accept()
                return

            # Сокет есть – запускаем сетевой режим
            self.local_mode = False
            success = self.initialize_audio_streams()
            if success:
                self.call_start_time = time.time()
                self.duration_timer.start(1000)
                self.status_label.setText("✅ Звонок активен")
                self.call_accepted.emit(self.call_id)
            else:
                self.status_label.setText("❌ Ошибка аудио")
        except Exception as e:
            logger.error(f"Ошибка принятия звонка: {e}")

    def reject_call(self):
        """Отклонить входящий звонок"""
        if self.sound_manager:
            self.sound_manager.stop()
        logger.info(f"🔊 Отклонение звонка {self.call_id}")
        self.call_rejected.emit(self.call_id)
        self.close()
    
    def end_call(self):
        """Завершить активный звонок"""
        if self.sound_manager:
            self.sound_manager.stop()
        self.call_ended.emit(self.call_id)
        self.close()
    
    def cancel_call(self):
        """Отменить исходящий звонок"""
        logger.info(f"🔊 Отмена звонка {self.call_id}")
        self.call_ended.emit(self.call_id)
        self.close()
     
    def set_incoming_socket(self, call_socket):
        """Установка сокета для входящего звонка"""
        try:
            if self.is_outgoing:
                logger.warning(f"⚠️ Попытка установить сокет для исходящего звонка через set_incoming_socket")
                return False
                
            logger.info(f"🔧 Установка сокета для входящего звонка {self.call_id}")
            
            if call_socket is None:
                logger.error("❌ Передан пустой сокет для входящего звонка")
                return False
                
            # Устанавливаем сокет
            self.call_socket = call_socket
            try:
                call_socket.settimeout(0.5)   # таймаут 0.5 сек
            except:
                pass
            self.socket_set = True
            self.local_mode = False
            
            # Проверяем подключение
            try:
                original_timeout = call_socket.gettimeout()
                call_socket.settimeout(2.0)
                call_socket.send(b'PING')
                call_socket.settimeout(original_timeout)
                logger.info("✅ Сокет для входящего звонка проверен")
            except Exception as e:
                logger.warning(f"⚠️ Сокет не подключен: {e}")
                self.local_mode = True
                
            # Обновляем статус
            self.status_label.setText("🟢 Сокет: установлен")
            self.status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
            
            # Если звонок уже принят, инициализируем аудио
            if self.is_active and not self.audio_initialized:
                logger.info("🔊 Инициализация аудио после установки сокета...")
                QTimer.singleShot(100, self.initialize_audio_streams)   
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка установки сокета для входящего звонка: {e}")
            self.status_label.setText("🔴 Сокет: ошибка установки")
            return False

    def check_socket_for_accept(self):
        """Периодическая проверка появления сокета для входящего звонка"""
        if self.check_socket_connection():
            # Сокет появился – запускаем сетевой режим
            self.local_mode = False
            success = self.initialize_audio_streams()
            if success:
                self.call_start_time = time.time()
                self.duration_timer.start(1000)
                self.status_label.setText("✅ Звонок активен")
                self.call_accepted.emit(self.call_id)
            else:
                self.status_label.setText("❌ Ошибка аудио")
            return

        # Сокета всё нет – увеличиваем счётчик
        self.accept_retry_count = getattr(self, 'accept_retry_count', 0) + 1
        if self.accept_retry_count <= 6:  # 6 попыток * 500 мс = 3 секунды
            self.status_label.setText(f"⏳ Ожидание соединения... ({self.accept_retry_count}/6)")
            QTimer.singleShot(500, self.check_socket_for_accept)
        else:
            # Время вышло – переходим в локальный режим
            self.status_label.setText("⚠️ Соединение не установлено, локальный режим")
            self.local_mode = True
            success = self.initialize_local_audio()
            if success:
                self.call_start_time = time.time()
                self.duration_timer.start(1000)
                self.status_label.setText("🔇 Локальный режим (без сети)")
                self.call_accepted.emit(self.call_id)
            else:
                self.status_label.setText("❌ Ошибка аудио")

    def get_call_socket_from_parent(self):
        """Получение сокета от родительского окна"""
        try:
            if not self.parent():
                logger.warning("⚠️ Нет родительского окна для получения сокета")
                return None
            
            if hasattr(self.parent(), 'get_call_socket'):
                logger.info(f"🔍 Запрос сокета от родителя для звонка {self.call_id}")
                socket = self.parent().get_call_socket(self.call_id)
                
                if socket:
                    logger.info(f"✅ Получен сокет от родителя: {socket}")
                    return socket
                else:
                    logger.warning(f"⚠️ Родитель вернул пустой сокет для звонка {self.call_id}")
            else:
                logger.warning("⚠️ У родителя нет метода get_call_socket")
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения сокета от родителя: {e}")

        return None

    def check_socket_connection(self):
        try:
            if self.call_socket is None:
                return False
            # Если это серверный сокет (слушает)
            if hasattr(self.call_socket, 'listen') and self.call_socket.fileno() != -1:
                # Серверный сокет жив, но подключения ещё может не быть
                return True
            # Для клиентских проверяем отправкой
            try:
                original_timeout = self.call_socket.gettimeout()
                self.call_socket.settimeout(0.5)
                self.call_socket.send(b'')
                self.call_socket.settimeout(original_timeout)
                return True
            except (socket.error, OSError, AttributeError) as e:
                logger.debug(f"Сокет не подключен: {e}")
                return False
        except Exception as e:
            logger.debug(f"Ошибка проверки сокета: {e}")
            return False
       
    def safe_accept_call(self):
        """Безопасное принятие звонка с защитой от многократного нажатия"""
        if self.accept_button_clicked:
            logger.warning(f"Попытка повторного принятия звонка {self.call_id}")
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
  
    def start_call(self):
        """Начать звонок (исходящий) - вызывается по кнопке"""
        try:
            logger.info(f"🔊 Запуск исходящего звонка {self.call_id}")
                        
            
            # Скрываем кнопки
            self.start_button.hide()
            self.cancel_button.hide()
            self.active_buttons_widget.show()
            self.duration_label.setVisible(True)
            self.progress_bar.hide()


            self.is_active = True  # устанавливаем флаг, что звонок активен

                           
            # Проверяем наличие сокета
            if not self.call_socket:
                # Если сокета ещё нет, пробуем получить от родителя или ждём
                parent_socket = self.get_call_socket_from_parent()
                
                if parent_socket:
                    success = self.set_call_socket(parent_socket)
                else:
                    self.status_label.setText("⏳ Ожидание соединения...")
                    QTimer.singleShot(1000, self.retry_start_call)
                    return

            self._do_start_call()
        except Exception as e:
            logger.error(f"❌ Ошибка запуска звонка: {e}")

    def _do_start_call(self):
        """Внутренний запуск звонка после того, как сокет установлен"""
        if self.local_mode:
            success = self.initialize_local_audio()
        else:
            success = self.initialize_audio_streams()

        if success:
            self.call_start_time = time.time()
            self.duration_timer.start(1000)
            self.status_label.setText("✅ Звонок активен")
            logger.info(f"✅ Звонок {self.call_id} успешно запущен")
        else:
            self.status_label.setText("❌ Ошибка аудио")
            logger.error(f"❌ Не удалось инициализировать аудио для звонка {self.call_id}")        

    def retry_start_call(self):
        """Повторная попытка запуска звонка, если сокет ещё не готов"""
        if self.call_socket:
            self._do_start_call()
        else:
            self.status_label.setText("⚠️ Соединение не установлено, повтор через 2 сек...")
            QTimer.singleShot(2000, self.retry_start_call)

    def initialize_audio_streams(self):
        """Инициализация аудио потоков на выбранных устройствах"""
        try:
            if self.audio_initialized:
                logger.info("⚠️ Аудио уже инициализировано")
                return True

            logger.info(f"🔧 initialize_audio_streams: call_socket={self.call_socket}, local_mode={self.local_mode}")
            
            # Определяем режим работы
            if not self.call_socket or self.local_mode:
                logger.info("🔊 Работа в локальном режиме (без сетевого аудио)")
                return self.initialize_local_audio()

            logger.info("🔧 Инициализация аудио потоков...")
            
            # Определяем устройства для использования
            input_device = self.input_device
            output_device = self.output_device
            
            # Если устройства не выбраны, используем автовыбор
            if input_device is None:
                try:
                    input_device = sd.default.device[0] if sd.default.device else None     
                except:
                    input_device = None
                    
            if output_device is None:
                try:
                    output_device = sd.default.device[1] if sd.default.device else None      
                except:
                    output_device = None
            
            logger.info(f"🔧 Используемые устройства: ввод={input_device}, вывод={output_device}")
            
            # Пробуем разные конфигурации
            configs = [
                {'samplerate': 44100, 'blocksize': 4096},
                {'samplerate': 22050, 'blocksize': 512},
                {'samplerate': 16000, 'blocksize': 256},
            ]
            
            for config in configs:
                try:
                    logger.info(f"🔧 Попытка конфигурации: {config}")
                    
                    def input_callback(indata, frames, time, status):
                        if not self.muted:
                            logger.debug(f"🎤 Микрофон включён, отправка {frames} семплов")
                            self.send_audio_data(indata)
                        else:
                            logger.debug("🔇 Микрофон выключен, данные не отправляются")
                        if status:
                            logger.debug(f"Аудио входной статус: {status}")
                        
                    # Callback для воспроизведения аудио
                    def output_callback(outdata, frames, time, status):
                        if status:
                            logger.debug(f"Аудио выходной статус: {status}")
                        if self.received_packets == 0:
                            logger.info("🔔 output_callback вызван впервые")
                        try:
                            # Получаем данные из буфера
                            audio_data = self.get_audio_data(frames)
                            if audio_data is not None:
                                outdata[:] = audio_data.reshape(-1, 1)
                                if self.received_packets % 50 == 0:
                                    logger.debug(f"🔊 Воспроизведено пакетов: {self.received_packets}")
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

                    # Обновляем параметры
                    self.sample_rate = config['samplerate']
                    self.blocksize = config['blocksize']
                    
                    self.audio_initialized = True
                    logger.info(f"✅ Аудио потоки успешно инициализированы с конфигурацией: {config}")
                    
                    
                    # Запускаем потоки
                    self.input_stream.start()
                    self.output_stream.start()
                    
                    
                    
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
            return False

    def initialize_local_audio(self):
        """Инициализация локального аудио (без сетевого соединения)"""
        try:
            logger.info("🔊 Инициализация локального аудио (тестовый режим)")
            
            
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
            
            logger.info(f"🔧 Используемые устройства для локального аудио: ввод={input_device}, вывод={output_device}")
            
            # Создаем буфер для локального тестирования
            self.local_audio_buffer = []
            self.local_buffer_lock = threading.Lock()
            
            # Callback для захвата аудио
            def input_callback(indata, frames, time, status):
                if status:
                    logger.debug(f"Локальный входной статус: {status}")
            
                try:
                    # Сохраняем данные в буфер для локального воспроизведения
                    with self.local_buffer_lock:
                        if len(self.local_audio_buffer) < 5:  # Ограничиваем размер буфера
                            self.local_audio_buffer.append(indata.copy())
                except Exception as e:
                    logger.debug(f"Ошибка в локальном input callback: {e}")
            
            # Callback для воспроизведения аудио
            def output_callback(outdata, frames, time, status):
                if status:
                    logger.debug(f"Локальный выходной статус: {status}")
                
                try:
                    # Получаем данные из локального буфера
                    with self.local_buffer_lock:
                        if self.local_audio_buffer:
                            data = self.local_audio_buffer.pop(0)
                            if len(data) >= frames:
                                outdata[:] = data[:frames]
                            else:
                                # Если данных недостаточно, заполняем нулями
                                outdata[:len(data)] = data
                                outdata[len(data):] = 0
                        else:
                            outdata.fill(0)
                except Exception as e:
                    logger.debug(f"Ошибка в локальном output callback: {e}")
                    outdata.fill(0)
            
            # Создаем отдельные потоки
            self.input_stream = sd.InputStream(
                device=input_device,
                samplerate=44100,
                blocksize=1024,
                channels=self.channels,
                callback=input_callback,
                dtype=np.float32
            )
            
            self.output_stream = sd.OutputStream(
                device=output_device,
                samplerate=44100,
                blocksize=1024,
                channels=self.channels,
                callback=output_callback,
                dtype=np.float32
            )
            
            # Запускаем потоки
            self.input_stream.start()
            self.output_stream.start()
            
            self.audio_initialized = True
            self.local_mode = True
            
            logger.info("✅ Локальное аудио инициализировано (тестовый режим)")
            
            # Показываем статус
            self.audio_status_label.setText("🔊 Локальный режим (аудио тест)")
            self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
            self.status_label.setText("🔇 Локальный режим (тестовый)")
            self.status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
            return True
            
        except Exception as e:
            logger.error(f"❌ Локальное аудио неддоступно: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось запустить локальное аудио: {e}")
            return False

    def get_audio_data(self, frames):
        if not self.is_active:
            return None
        try:
            # Неблокирующее получение
            data = self.audio_buffer.get_nowait()
            if len(data) < frames:
                padded_data = np.zeros(frames, dtype=np.float32)
                padded_data[:len(data)] = data
                return padded_data
            return data[:frames]
        except queue.Empty:
            return None
        except Exception as e:
            logger.debug(f"Ошибка получения аудио данных: {e}")
            return None

    def send_audio_data(self, audio_data):
        if self.muted:
            return False
        # Проверяем флаги до попытки отправки
        if not self.is_active:
            return False
        if not self.call_socket:
            return False
        if not self.audio_initialized:
            return False
        if self.local_mode:
            return False
        try:
            if isinstance(audio_data, np.ndarray):
                raw = audio_data.tobytes()
            else:
                raw = bytes(audio_data)

            header = struct.pack('!I', len(raw))
            packet = header + raw

            if self.secure_mode:
                self.call_socket.send(packet)
            else:
                self.call_socket.sendall(packet)
            self.sent_packets += 1
            if self.sent_packets % 50 == 0:
                logger.info(f"✅ Отправлен аудио-пакет #{self.sent_packets} ({len(packet)} байт)")
            return True
        except BrokenPipeError:
            logger.warning("🔌 send_audio_data: соединение разорвано")
            return False
        except ConnectionResetError:
            logger.warning("🔌 send_audio_data: соединение сброшено")
            return False
        except socket.timeout:
            logger.warning("⏱️ send_audio_data: таймаут отправки")
            return False
        except OSError as e:
            if e.errno == 9:  # Bad file descriptor – сокет закрыт
                logger.warning("🔌 Попытка отправки в закрытый сокет")
            else:
                logger.error(f"Ошибка ОС при отправке аудио: {e}")
            return False
        except ConnectionError as e:
            logger.warning(f"🔌 Ошибка соединения при отправке: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка отправки аудио: {e}", exc_info=True)
            return False
    
    def _audio_receiver_loop(self):
        logger.info("Запуск аудио-приёмника")
        buffer = b''
        synced = False
        while self.is_active and self.audio_receiver_running and self.call_socket:
            try:
                if self.secure_mode:
                    try:
                        # recv() без аргумента timeout (таймаут задан заранее через settimeout)
                        packet = self.call_socket.recv()
                        if not packet:
                            break
                        if len(packet) < 4:
                            continue
                        data_len = struct.unpack('!I', packet[:4])[0]
                        if 0 < data_len <= MAX_AUDIO_PACKET_SIZE and len(packet) >= 4 + data_len:
                            audio_bytes = packet[4:4+data_len]
                            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                            self._put_to_buffer(audio_array)
                    except socket.timeout:
                        # Таймаут – просто ждём следующий пакет
                        continue
                    except Exception as e:
                        if self.is_active:
                            logger.error(f"❌ Ошибка приёма (защищённый режим): {e}")
                        break
                else:
                    try:
                        chunk = self.call_socket.recv(4096)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"❌ Ошибка приёма: {e}")
                        break

                    if not chunk:
                        logger.warning("🔌 Соединение закрыто удалённой стороной (пустой чанк)")
                        break

                    buffer += chunk
                    logger.debug(f"📥 Получено {len(chunk)} байт, буфер приёмника: {len(buffer)}")

                    # Поиск первого корректного пакета (синхронизация)
                    while not synced and len(buffer) >= 4:
                        maybe_len = struct.unpack('!I', buffer[:4])[0]
                        if 0 < maybe_len <= MAX_AUDIO_PACKET_SIZE:
                            synced = True
                            logger.info("🔄 Синхронизация аудиопотока успешна")
                        else:
                            buffer = buffer[1:]
                            if len(buffer) % 4096 == 0:
                                logger.debug(f"⏳ Ожидание синхронизации, буфер {len(buffer)} байт")

                    # Извлечение пакетов после синхронизации
                    while synced and len(buffer) >= 4:
                        data_len = struct.unpack('!I', buffer[:4])[0]
                        if not (0 < data_len <= MAX_AUDIO_PACKET_SIZE):
                            logger.warning("⚠️ Некорректный заголовок пакета, сброс синхронизации")
                            synced = False
                            break
                        if len(buffer) >= 4 + data_len:
                            audio_bytes = buffer[4:4+data_len]
                            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                            self._put_to_buffer(audio_array)
                            buffer = buffer[4+data_len:]
                        else:
                            break
            except Exception as e:
                if self.is_active:
                    logger.error(f"❌ Ошибка в цикле приёма: {e}")
                break
        self.audio_receiver_running = False
        logger.info("Аудио-приёмник остановлен")

    def _put_to_buffer(self, audio_array):
        """Вспомогательный метод для вставки в очередь с логированием"""
        try:
            self.audio_buffer.put_nowait(audio_array)
            self.received_packets += 1
            if self.received_packets % 50 == 0:
                logger.info(f"📥 Принят аудио-пакет #{self.received_packets}, буфер: {self.audio_buffer.qsize()}")
        except queue.Full:
            logger.warning("⚠️ Буфер воспроизведения переполнен, пакет отброшен")

    def start_audio_receiver(self):
        """Запуск потока для приема аудио данных"""
        if self.audio_receiver_running or self.local_mode:
            return
        self.audio_receiver_running = True
        self.audio_receiver_thread = threading.Thread(target=self._audio_receiver_loop, daemon=True)
        self.audio_receiver_thread.start()
            
    def stop_audio_streams(self):
        """Остановка аудио-потоков"""
        try:
            logger.info(f"🔴 Остановка аудио потоков для звонка {self.call_id}")
            self.audio_initialized = False 
            self.is_active = False
            self.audio_receiver_running = False

            
                
            if hasattr(self, 'input_stream') and self.input_stream is not None:
                try:
                    if self.input_stream.active:
                        self.input_stream.stop()
                    self.input_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки input stream: {e}")
                self.input_stream = None
                
            if hasattr(self, 'output_stream') and self.output_stream is not None:
                try:
                    if self.output_stream.active:
                        self.output_stream.stop()
                    self.output_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки output stream: {e}")
                self.output_stream = None

            # Очищаем буферы
            while not self.audio_buffer.empty():
                try:
                    self.audio_buffer.get_nowait()
                except queue.Empty:
                    break
            
            # Очищаем локальный буфер если он есть
            if hasattr(self, 'local_audio_buffer'):
                with self.local_buffer_lock:
                    self.local_audio_buffer.clear()
            
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
    
    def upgrade_to_video(self):
        """Обновление до видеозвонка"""
        try:
            if show_question_dialog(self, 'Перейти на видеозвонок', 'Вы хотите перейти на видеозвонок?\nЭто потребует согласия собеседника.'):
                # Закрываем текущий аудиозвонок
                self.end_call()
                
                # Отправляем запрос на видеозвонок через родительское окно
                if self.parent():
                    self.parent().start_video_call(self.username)
                    
        except Exception as e:
            logger.error(f"Ошибка перехода на видеозвонок: {e}")

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        try:
            if self.sound_manager:
                self.sound_manager.stop()
            # Устанавливаем флаги, чтобы остановить любые новые попытки отправки
            self.is_active = False
            self.audio_receiver_running = False   # сигнал остановки потока
            self.duration_timer.stop()
            self.socket_check_timer.stop()

            # Останавливаем аудио-потоки (синхронно)
            self.stop_audio_streams()

            # Теперь закрываем сокет и обнуляем ссылку
            if self.call_socket:
                try:
                    self.call_socket.close()
                except:
                    pass
                self.call_socket = None


            # Если поток приёмника ещё жив, ждём его завершения
            if self.audio_receiver_thread and self.audio_receiver_thread.is_alive():
                self.audio_receiver_thread.join(timeout=0.5)  # ждём завершения

            
            if not self._closing_by_network and not getattr(self, 'call_ended_emitted', False):
                self.call_ended.emit(self.call_id)
                self.call_ended_emitted = True
            event.accept()
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при закрытии окна звонка: {e}")
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        # Центр окна
        center = rect.center()
        # Радиус градиента – половина диагонали, чтобы покрыть все углы
        radius = max(rect.width(), rect.height()) // 2

        gradient = QRadialGradient(center, radius)
        # Прозрачный центр – изображение будет видно чётко
        gradient.setColorAt(0, QColor(0, 0, 0, 100))
        # Тёмно-синий по краям (можно заменить на любой оттенок)
        gradient.setColorAt(1, QColor(25, 25, 112, 255))  # MidnightBlue

        painter.fillRect(rect, gradient)
        super().paintEvent(event)