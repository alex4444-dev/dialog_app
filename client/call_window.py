import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QMessageBox,
                             QComboBox, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import logging
import time

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
        self.is_active = False
        self.call_duration = 0
        self.duration_timer = QTimer()
        self.audio_initialized = False
        self.call_ended_emitted = False
        self.audio_stream = None
        self.audio_available = False
        self.accept_button_clicked = False  # ✅ ЗАЩИТА ОТ МНОГОКРАТНОГО НАЖАТИЯ
        
        self.init_ui()
        self.detect_audio_system()
        
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
            self.accept_button.clicked.connect(self.safe_accept_call)  # ✅ БЕЗОПАСНЫЙ ВЫЗОВ
            
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
            self.reject_button.clicked.connect(self.safe_reject_call)  # ✅ БЕЗОПАСНЫЙ ВЫЗОВ
            
            buttons_layout.addWidget(self.accept_button)
            buttons_layout.addWidget(self.reject_button)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
        # Настройка таймера для обновления длительности звонка
        self.duration_timer.timeout.connect(self.update_duration)
    
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
        """Определение звуковой системы - БЕЗОПАСНАЯ ВЕРСИЯ"""
        try:
            # ✅ БЕЗОПАСНАЯ ПРОВЕРКА ДОСТУПНОСТИ AUDIO
            try:
                import sounddevice as sd
                self.sd = sd
                
                # Простой тест доступности аудио
                devices = sd.query_devices()
                logger.info(f"🔊 Найдено аудио устройств: {len(devices)}")
                
                default_input = sd.default.device[0]
                default_output = sd.default.device[1]
                logger.info(f"🎤 Устройство ввода по умолчанию: {default_input}")
                logger.info(f"🔊 Устройство вывода по умолчанию: {default_output}")

                if len(devices) > 0:
                    self.audio_available = True
                    audio_system = f"Аудио доступно ({len(devices)} устройств)"

                    # Запускаем быстрый тест
                    QTimer.singleShot(1000, self.test_audio_system)
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
                
        except Exception as e:
            logger.error(f"Критическая ошибка определения звуковой системы: {e}")
            self.audio_available = False
            self.audio_system_label.setText("Аудио недоступно")
    
    def start_call(self):
        """Начать звонок (после принятия) - БЕЗОПАСНАЯ ВЕРСИЯ"""
        try:
            if self.is_active:  # ✅ ЗАЩИТА ОТ ПОВТОРНОГО ЗАПУСКА
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
            
            # ✅ ОТЛОЖЕННАЯ ИНИЦИАЛИЗАЦИЯ АУДИО ДЛЯ ИЗБЕЖАНИЯ ОШИБОК
            if self.audio_available and self.call_type in ['audio', 'video']:
                # Запускаем аудио в отдельном потоке с задержкой
                QTimer.singleShot(100, self.safe_initialize_audio)
            else:
                logger.info(f"Звонок {self.call_id} начат без аудио")
            
            logger.info(f"Звонок {self.call_id} начат")
            
        except Exception as e:
            logger.error(f"Ошибка начала звонка: {e}")
            self.show_audio_error("Ошибка инициализации звонка")
    
    def safe_initialize_audio(self):
        """Безопасная инициализация аудио с обработкой исключений"""
        try:
            if self.audio_initialized:  # ✅ ЗАЩИТА ОТ ПОВТОРНОЙ ИНИЦИАЛИЗАЦИИ
                return

            # ВМЕСТО упрощенной версии используем реальную
            self.initialize_real_audio_streams()
            self.audio_initialized = True
            logger.info("Реальные аудио потоки инициализированы")
                
            import sounddevice as sd
            import numpy as np
            
            # ✅ ПРОСТЫЕ И БЕЗОПАСНЫЕ ПАРАМЕТРЫ
            self.sample_rate = 44100
            self.channels = 1
            self.dtype = 'float32'
            self.blocksize = 1024

            # Инициализация буфера
            self.audio_buffer = []
            self.buffer_size = 10

            logger.info(f"Инициализация аудио: sample_rate={self.sample_rate}, channels={self.channels}")
            
            # Callback для захвата аудио с микрофона
            def input_callback(indata, outdata, frames, time, status):
                if status:
                    logger.info(f"Аудио входной статус: {status}")
                
                    try:
                        if hasattr(self, 'call_socket') and self.call_socket and self.is_active:
                           # Отправляем аудио данные через сокет
                           audio_data = indata.copy()
                           logger.debug(f"Захвачено аудио: {len(audio_data)} samples, макс. амплитуда: {np.max(np.abs(audio_data)):.4f}")
                           self.send_audio_data(audio_data.tobytes())
                        else:
                           logger.warning("Нет сокета или звонок не активен для отправки аудио") 
                    except Exception:
                        # Игнорируем все ошибки в callback
                        logger.error(f"Ошибка в input callback: {e}")

            # Callback для воспроизведения аудио
            def output_callback(outdata, frames, time, status):
                if status:
                    logger.info(f"Аудио выходной статус: {status}")
            
                try:
                    if self.audio_buffer and self.is_active:
                        # Берем данные из буфера
                        audio_data = self.audio_buffer.pop(0)
                        outdata[:] = audio_data
                        logger.debug(f"Воспроизведение аудио: {len(audio_data)} samples")
                    else:
                        # Если буфер пуст - тишина
                        outdata.fill(0)
                        if self.is_active:
                            logger.debug("Буфер аудио пуст - воспроизводится тишина")
                except Exception as e:
                    logger.error(f"Ошибка в output callback: {e}")
                    outdata.fill(0)
            
            # Создаем отдельные потоки для ввода и вывода
            logger.info("Создание InputStream...")
            self.input_stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=self.channels,
                callback=input_callback,
                dtype=self.dtype
            )

            logger.info("Создание OutputStream...")
            self.output_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                channels=self.channels,
                callback=output_callback,
                dtype=self.dtype
            )   
            
            # Запускаем потоки
            logger.info("Запуск аудио потоков...")
            self.input_stream.start()
            self.output_stream.start()
            self.audio_initialized = True
        
            logger.info("✅ Реальные аудио потоки успешно инициализированы и запущены")
        except Exception as e:
            logger.warning(f"Не удалось инициализировать аудио поток: {e}")
            self.audio_initialized = False
            # Не показываем ошибку пользователю - звонок может работать без аудио
    
    def stop_audio_streams(self):
        """Остановка аудио-потоков - БЕЗОПАСНАЯ ВЕРСИЯ"""
        try:
            if hasattr(self, 'audio_stream') and self.audio_stream is not None:
                try:
                    self.audio_stream.stop()
                except Exception:
                    pass
                try:
                    self.audio_stream.close()
                except Exception:
                    pass
                self.audio_stream = None
                self.audio_initialized = False
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
            if self.is_active:  # ✅ ЗАЩИТА ОТ ПОВТОРНОГО ПРИНЯТИЯ
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
        """Завершить звонок"""
        if getattr(self, 'call_ended_emitted', False):
            return

        try:
            self.is_active = False
            self.call_ended_emitted = True
            self.duration_timer.stop()
            self.stop_audio_streams()
            self.call_ended.emit(self.call_id)
            
            logger.info(f"Звонок {self.call_id} завершен")
            
        except Exception as e:
            logger.error(f"Ошибка завершения звонка: {e}")
    
    def initialize_real_audio_streams(self):
        """Инициализация реальных аудио потоков с передачей данных"""
        try:
            if self.audio_initialized:
                return
            
            import sounddevice as sd
            import numpy as np
        
            # Параметры аудио
            self.sample_rate = 44100
            self.channels = 1
            self.dtype = 'float32'
            self.blocksize = 1024
        
            # Буфер для аудио данных
            self.audio_buffer = []
            self.buffer_size = 10  # Количество блоков в буфере

            # Callback для захвата аудио с микрофона
            def input_callback(indata, frames, time, status):
                if status:
                    logger.debug(f"Аудио входной статус: {status}")
            
                try:
                    if hasattr(self, 'call_socket') and self.call_socket and self.is_active:
                        # Отправляем аудио данные через сокет
                        audio_data = indata.copy()
                        self.send_audio_data(audio_data.tobytes())
                except Exception as e:
                    logger.debug(f"Ошибка в input callback: {e}")
            
            # Callback для воспроизведения аудио
            def output_callback(outdata, frames, time, status):
                if status:
                    logger.debug(f"Аудио выходной статус: {status}")
            
                try:
                    if self.audio_buffer and self.is_active:
                        # Берем данные из буфера
                        audio_data = self.audio_buffer.pop(0)
                        # Копируем данные в outdata, обрезая если нужно
                        min_frames = min(audio_data.shape[0], outdata.shape[0])
                        outdata[:min_frames] = audio_data[:min_frames]
                        
                        # Если данные короче чем outdata, заполняем остаток нулями
                        if min_frames < outdata.shape[0]:
                            outdata[min_frames:] = 0
                        else:
                            # Если буфер пуст - тишина
                            outdata.fill(0)
                except Exception as e:
                    logger.debug(f"Ошибка в output callback: {e}")
                    outdata.fill(0)

            # Создаем отдельные потоки для ввода и вывода
            self.input_stream = sd.InputStream(
               samplerate=self.sample_rate,
               blocksize=self.blocksize,
               channels=self.channels,
               callback=input_callback,
               dtype=self.dtype
            )

            self.output_stream = sd.OutputStream(
               samplerate=self.sample_rate,
               blocksize=self.blocksize,
               channels=self.channels,
               callback=output_callback,
               dtype=self.dtype
            )

            # Запускаем потоки
            self.input_stream.start()
            self.output_stream.start()
            self.audio_initialized = True
        
            logger.info("Реальные аудио потоки инициализированы")
        except Exception as e:
            logger.error(f"Ошибка инициализации реальных аудио потоков: {e}")
            self.audio_initialized = False

    def start_audio_receiver(self):
        """Запуск потока для приема аудио данных"""
        import threading
    
        def audio_receiver():
            while self.is_active and hasattr(self, 'call_socket') and self.call_socket:
                try:
                    self.receive_audio_data()
                except Exception as e:
                    if self.is_active:
                        logger.debug(f"Ошибка в аудио приемнике: {e}")
                    break
    
        self.audio_receiver_thread = threading.Thread(target=audio_receiver, daemon=True)
        self.audio_receiver_thread.start()

    def send_audio_data(self, audio_data):
        """Отправка аудио данных через сокет"""
        try:
            if (hasattr(self, 'call_socket') and self.call_socket 
                and self.is_active and self.audio_initialized):
            
                logger.debug(f"Отправка аудио данных: {len(audio_data)} байт")
                
                # Добавляем заголовок с размером данных
                header = struct.pack('I', len(audio_data))
                total_sent = self.call_socket.send(header + audio_data)
                logger.debug(f"📤 Отправлено {total_sent} байт")
            else:
                logger.warning("Не могу отправить аудио: нет сокета или поток не инициализирован")   
        except Exception as e:
            logger.error(f"Ошибка отправки аудио данных: {e}")

    def receive_audio_data(self):
        """Прием аудио данных из сокета"""
        try:
            if (hasattr(self, 'call_socket') and self.call_socket 
                and self.is_active and self.audio_initialized):
            
                # Читаем заголовок с размером данных
                header = self.call_socket.recv(4)
                if not header:
                    logger.warning("Пустой заголовок аудио данных")
                    return
                
                data_size = struct.unpack('I', header)[0]
                logger.debug(f"📥 Ожидаем аудио данных: {data_size} байт")
            
                # Читаем аудио данные
                audio_data = b''
                while len(audio_data) < data_size:
                    chunk = self.call_socket.recv(data_size - len(audio_data))
                    if not chunk:
                        logger.warning("Неполные аудио данные")
                        break
                    audio_data += chunk
            
                if len(audio_data) == data_size:
                    # Преобразуем байты в numpy array и добавляем в буфер
                    import numpy as np
                    audio_array = np.frombuffer(audio_data, dtype='float32')
                    # Изменяем форму чтобы соответствовать outdata
                    audio_array = audio_array.reshape(-1, 1)  # (frames, channels)
                
                    if len(self.audio_buffer) < self.buffer_size:
                        self.audio_buffer.append(audio_array)
                    else:
                        # Если буфер полон, удаляем самый старый элемент
                        self.audio_buffer.pop(0)
                        self.audio_buffer.append(audio_array)
                else: 
                    logger.warning(f"Неполные данные: получено {len(audio_data)} из {data_size} байт")    
        except Exception as e:
            logger.debug(f"Ошибка приема аудио данных: {e}")

    def test_audio_system(self):
        """Тестирование аудио системы"""
        try:
            import sounddevice as sd
            import numpy as np
        
            logger.info("🔊 Запуск теста аудио системы...")
        
            # Тест воспроизведения
            duration = 2.0
            sample_rate = 44100
            frequency = 440  # Ля первой октавы
        
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * frequency * t)
        
            logger.info("🔊 Воспроизведение тестового тона...")
            sd.play(tone, sample_rate)
            sd.wait()
            logger.info("✅ Тест воспроизведения завершен")
        
            # Тест записи
            logger.info("🎤 Тест записи с микрофона (5 секунд)...")
            recording = sd.rec(int(5 * sample_rate), samplerate=sample_rate, channels=1)
            sd.wait()
        
            max_amplitude = np.max(np.abs(recording))
            logger.info(f"🎤 Запись завершена, макс. амплитуда: {max_amplitude:.4f}")
        
            if max_amplitude < 0.01:
                logger.warning("⚠️ Возможно, микрофон не работает или очень тихий")
            else:
                logger.info("✅ Микрофон работает нормально")
            
        except Exception as e:
            logger.error(f"❌ Ошибка теста аудио: {e}")

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        try:
            if self.is_active:
                self.end_call()
            else:
                self.stop_audio_streams()
            event.accept()
        except Exception as e:
            logger.error(f"Ошибка при закрытии окна звонка: {e}")
            event.accept()