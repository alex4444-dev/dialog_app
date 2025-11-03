import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QMessageBox,
                             QComboBox, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from audio_utils import audio_manager
import logging
import time
import struct
import threading
import socket
import numpy as np

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
        
        # Буфер для аудио данных
        self.audio_buffer = []
        self.buffer_size = 20
        self.audio_buffer_lock = threading.Lock()
        self.stream_id = f"call_{call_id}"

        # Счетчики для диагностики
        self.sent_packets = 0
        self.received_packets = 0
        
        self.init_ui()
        self.detect_audio_system()

        # Индикатор состояния аудио
        self.audio_status_label = QLabel("🔇 Аудио: проверка...")
        self.audio_status_label.setAlignment(Qt.AlignCenter)
        self.audio_status_label.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        
        # Добавляем в layout после его создания
        layout = self.layout()
        if layout:
            layout.addWidget(self.audio_status_label)

        logger.info(f"🔊 CallWindow создано успешно")
        
    def init_ui(self):
        """Инициализация интерфейса окна звонка"""
        self.setWindowTitle(f"📞 Звонок с {self.username}")
        self.setFixedSize(500, 400)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Заголовок
        title_text = "Исходящий звонок" if self.is_outgoing else "Входящий звонок"
        title_label = QLabel(f"📞 {title_text}")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)
        
        # Информация о звонке
        info_label = QLabel(f"Пользователь: {self.username}\nТип: {self.call_type}")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 14px; color: #34495e;")
        layout.addWidget(info_label)
        
        # Информация о звуковой системе
        self.audio_system_label = QLabel("Определение звуковой системы...")
        self.audio_system_label.setAlignment(Qt.AlignCenter)
        self.audio_system_label.setStyleSheet("font-size: 11px; color: #7f8c8d; font-style: italic;")
        layout.addWidget(self.audio_system_label)
        
        # Диагностическая информация
        self.diagnostic_label = QLabel("Ожидание данных...")
        self.diagnostic_label.setAlignment(Qt.AlignCenter)
        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
        layout.addWidget(self.diagnostic_label)
        
        # Таймер звонка
        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.duration_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #27ae60;")
        self.duration_label.setVisible(False)
        layout.addWidget(self.duration_label)
        
        # Статус звонка
        self.status_label = QLabel("Набор номера..." if self.is_outgoing else "Входящий вызов...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        layout.addWidget(self.status_label)
        
        # Прогресс-бар (для анимации)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Бесконечная анимация
        self.progress_bar.setVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Кнопки управления звонком
        buttons_layout = QHBoxLayout()
        
        if self.is_outgoing:
            # Для исходящего звонка - только кнопка завершения
            self.end_button = QPushButton("📞 Завершить")
            self.end_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
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
            self.accept_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            self.accept_button.clicked.connect(self.safe_accept_call)
            
            self.reject_button = QPushButton("❌ Отклонить")
            self.reject_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.reject_button.clicked.connect(self.safe_reject_call)
            
            buttons_layout.addWidget(self.accept_button)
            buttons_layout.addWidget(self.reject_button)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
        # Настройка таймера для обновления длительности звонка
        self.duration_timer.timeout.connect(self.update_duration)
        
        # Таймер для обновления диагностической информации
        self.diagnostic_timer = QTimer()
        self.diagnostic_timer.timeout.connect(self.update_diagnostic_info)
        self.diagnostic_timer.start(1000)  # Обновлять каждую секунду
    
    def update_diagnostic_info(self):
        """Обновление диагностической информации"""
        if self.is_active:
            info = f"Отправлено: {self.sent_packets} | Получено: {self.received_packets} | Буфер: {len(self.audio_buffer)}"
            self.diagnostic_label.setText(info)
    
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
        
    def detect_audio_system(self):
        """Определение звуковой системы - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            import sounddevice as sd
            self.sd = sd
            
            # Простой тест доступности аудио
            devices = sd.query_devices()
            default_output = sd.default.device[1] if sd.default.device else None
            
            if len(devices) > 0:
                self.audio_available = True
                audio_system = f"Обнаружена звуковая система ({len(devices)} устройств)"
                
                # Проверяем устройство вывода по умолчанию
                if default_output is not None and default_output < len(devices):
                    output_device = devices[default_output]
                    audio_system += f" | Выход: {output_device['name']}"
            else:
                self.audio_available = False
                audio_system = "Аудио устройства не найдены"
                
            self.audio_system_label.setText(audio_system)
            logger.info(f"Аудио система: {audio_system}")
            
        except ImportError:
            self.audio_available = False
            self.audio_system_label.setText("SoundDevice не установлен")
            logger.warning("SoundDevice не установлен")
        except Exception as e:
            self.audio_available = False
            self.audio_system_label.setText(f"Ошибка аудио: {str(e)}")
            logger.error(f"Ошибка инициализации аудио: {e}")
    
    def start_call(self):
        """Начать звонок (после принятия)"""
        try:
            if self.is_active:
                logger.warning(f"Попытка повторного запуска звонка {self.call_id}")
                return
                
            self.is_active = True
            self.status_label.setText("Звонок активен")
            self.status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
            self.progress_bar.setVisible(False)
            self.duration_label.setVisible(True)
            self.call_ended_emitted = False
            
            # Запускаем таймер длительности
            self.call_start_time = time.time()
            self.duration_timer.start(1000)
            
            # Запускаем реальные аудио потоки
            if self.audio_available and self.call_type in ['audio', 'video']:
                self.initialize_real_audio_streams()
                if self.audio_initialized:
                    self.audio_status_label.setText("🔊 Аудио: подключено")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
                else:
                    self.audio_status_label.setText("🔇 Аудио: ошибка инициализации")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
                    # Продолжаем без аудио
                    logger.info(f"Звонок {self.call_id} продолжен без аудио")
                logger.info("Реальные аудио потоки запущены")
            else:
                logger.info(f"Звонок {self.call_id} начат без аудио")
                self.audio_status_label.setText("🔇 Аудио: отключено")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
            
            logger.info(f"Звонок {self.call_id} начат")
            
        except Exception as e:
            logger.error(f"Ошибка начала звонка: {e}")
            self.show_audio_error("Ошибка инициализации звонка")
    
    def initialize_real_audio_streams(self):
        """Инициализация реальных аудио потоков - УЛУЧШЕННАЯ ВЕРСИЯ ДЛЯ LINUX"""
        try:
            if self.audio_initialized:
                logger.info("⚠️ Аудио уже инициализировано")
                return
    
            import sounddevice as sd
            import numpy as np

            # Устанавливаем параметры для Linux/ALSA
            extra_settings = {}
            try:
                # Пытаемся использовать более совместимые параметры для ALSA
                extra_settings = {
                    'latency': 'high',
                    'dtype': np.float32
                }
            except:
                pass
    
            # Callback для захвата аудио с микрофона
            def input_callback(indata, frames, time, status):
                if status:
                    logger.debug(f"Аудио входной статус: {status}")
        
                try:
                    if hasattr(self, 'call_socket') and self.call_socket and self.is_active:
                        # Преобразуем в байты и отправляем
                        audio_data = indata.astype(np.float32).tobytes()
                        success = self.send_audio_data(audio_data)
                        if success:
                            self.sent_packets += 1
                            if self.sent_packets % 100 == 0:
                                logger.debug(f"🔊 Отправлено пакетов: {self.sent_packets}")        
                except Exception as e:
                    logger.debug(f"Ошибка в input callback: {e}")

            # Callback для воспроизведения аудио
            def output_callback(outdata, frames, time, status):
                if status:
                    logger.debug(f"Аудио выходной статус: {status}")
        
                try:
                    # Получаем данные из буфера
                    audio_data = self.get_audio_data(frames)
                    if audio_data is not None:
                        outdata[:] = audio_data.reshape(-1, 1)
                        if self.received_packets % 100 == 0:
                            logger.debug(f"🔊 Воспроизведено пакетов: {self.received_packets}")           
                    else:
                        # Заполняем тишиной
                        outdata.fill(0)    
                except Exception as e:
                    logger.debug(f"Ошибка в output callback: {e}")
                    outdata.fill(0)

            # Создаем потоки с обработкой ошибок
            logger.info("🔧 Попытка создания аудио потоков...")
            
            try:
                # Пытаемся создать InputStream
                self.input_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.blocksize,
                    channels=self.channels,
                    callback=input_callback,
                    dtype=np.float32,
                    **extra_settings
                )
                logger.info("✅ InputStream создан")
            except Exception as e:
                logger.error(f"❌ Ошибка создания InputStream: {e}")
                self.input_stream = None

            try:
                # Пытаемся создать OutputStream
                self.output_stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.blocksize,
                    channels=self.channels,
                    callback=output_callback,
                    dtype=np.float32,
                    **extra_settings
                )
                logger.info("✅ OutputStream создан")
            except Exception as e:
                logger.error(f"❌ Ошибка создания OutputStream: {e}")
                self.output_stream = None

            # Запускаем только те потоки, которые удалось создать
            if self.input_stream:
                try:
                    self.input_stream.start()
                    logger.info("✅ InputStream запущен")
                except Exception as e:
                    logger.error(f"❌ Ошибка запуска InputStream: {e}")
                    self.input_stream = None

            if self.output_stream:
                try:
                    self.output_stream.start()
                    logger.info("✅ OutputStream запущен")
                except Exception as e:
                    logger.error(f"❌ Ошибка запуска OutputStream: {e}")
                    self.output_stream = None

            # Если хотя бы один поток запущен, считаем аудио инициализированным
            self.audio_initialized = self.input_stream is not None or self.output_stream is not None
            
            if self.audio_initialized:
                logger.info("✅ Аудио потоки частично или полностью инициализированы")
            else:
                logger.warning("⚠️ Не удалось инициализировать аудио потоки")
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка инициализации аудио: {e}")
            self.show_audio_error(f"Аудио недоступно: {e}")
            self.audio_initialized = False

    def get_audio_data(self, frames):
        """Получение аудио данных из буфера"""
        if not self.is_active:
            return None
        try:
            with self.audio_buffer_lock:
                if self.audio_buffer:
                    # Берем первый элемент из буфера
                    data = self.audio_buffer.pop(0)
                    # Если данных меньше чем нужно, дополняем нулями
                    if len(data) < frames:
                        padded_data = np.zeros(frames, dtype=np.float32)
                        padded_data[:len(data)] = data
                        return padded_data
                    return data[:frames]  # Обрезаем если больше
            return None
        except Exception as e:
            logger.debug(f"Ошибка получения аудио данных: {e}")
            return None

    def send_audio_data(self, audio_data):
        """Отправка аудио данных с проверкой соединения"""
        try:
            if (not hasattr(self, 'call_socket') or not self.call_socket or 
                not self.is_active or not self.audio_initialized):
                return False

            # Проверяем что сокет еще подключен
            try:
                # Простая проверка - пытаемся отправить 0 байт
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
            if sent > 0:
                if self.sent_packets % 50 == 0:
                    logger.debug(f"🔊 Отправлено {sent} байт аудио данных")
                return True
            else:
                logger.warning("🔊 Не удалось отправить аудио данные (sent=0)")
                return False
        except Exception as e:
            logger.debug(f"🔊 Ошибка отправки аудио данных: {e}")
            return False

    def receive_audio_data(self):
        """Прием аудио данных из сокета"""
        try:
            if (hasattr(self, 'call_socket') and self.call_socket
                and self.is_active and self.audio_initialized):
                
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
                            # Если буфер полон, удаляем самый старый элемент
                            self.audio_buffer.pop(0)
                            self.audio_buffer.append(audio_array)
                    
                    self.received_packets += 1
                
                    if self.received_packets % 50 == 0:
                        logger.debug(f"🔊 Получено {len(audio_data)} байт аудио данных")
 
            else:
                logger.warning("🔊 Не могу принять аудио: нет сокета или поток не инициализирован")
                       
        except socket.timeout:
            pass  # Таймаут - это нормально
        except Exception as e:
            if self.is_active:
                logger.debug(f"Ошибка приема аудио данных: {e}")

    def start_audio_receiver(self):
        """Запуск потока для приема аудио данных"""
        def audio_receiver():
            logger.info("Запуск приемника аудио данных")
            while self.is_active and hasattr(self, 'call_socket') and self.call_socket:
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
            # Сначала сбрасываем флаг
            self.audio_initialized = False 
            self.is_active = False

            # Останавливаем INPUT STREAM
            if hasattr(self, 'input_stream') and self.input_stream is not None:
                try:
                    self.input_stream.stop()
                except Exception as e:
                    logger.debug(f"Ошибка остановки input stream: {e}")
                try:
                    self.input_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка закрытия input stream: {e}")
                self.input_stream = None
                
            # Останавливаем OUTPUT STREAM
            if hasattr(self, 'output_stream') and self.output_stream is not None:
                try:
                    self.output_stream.stop()
                except Exception as e:
                    logger.debug(f"Ошибка остановки output stream: {e}")
                try:
                    self.output_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка закрытия output stream: {e}")
                self.output_stream = None

            # Очищаем буфер
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
                
            self.is_active = True
            self.status_label.setText("Звонок принят")
            
            # Скрываем кнопки принятия/отклонения
            self.accept_button.setVisible(False)
            self.reject_button.setVisible(False)
            
            # Показываем кнопку завершения
            self.end_button = QPushButton("📞 Завершить")
            self.end_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
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
            
            # Останавливаем аудио потоки
            self.stop_audio_streams()
        
            # Закрываем сокет
            try:
                if hasattr(self, 'call_socket') and self.call_socket:    
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