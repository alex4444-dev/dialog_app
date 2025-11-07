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
        
        # Определяем правильные устройства на основе диагностики
        self.input_device = 1   # HD-Audio Generic: ALC3234 Analog (встроенная звуковая карта)
        self.output_device = 1  # HD-Audio Generic: ALC3234 Analog (встроенная звуковая карта)
        
        # Буфер для аудио данных
        self.audio_buffer = []
        self.buffer_size = 20
        self.audio_buffer_lock = threading.Lock()
        self.stream_id = f"call_{call_id}"

        # Счетчики для диагностики
        self.sent_packets = 0
        self.received_packets = 0
        self.last_audio_debug_time = 0
        
        # Сначала инициализируем UI
        self.init_ui()
        
        # Затем определяем аудио систему
        self.detect_audio_system()

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
        
        # Индикатор состояния аудио
        self.audio_status_label = QLabel("🔇 Аудио: проверка...")
        self.audio_status_label.setAlignment(Qt.AlignCenter)
        self.audio_status_label.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        layout.addWidget(self.audio_status_label)
        
        # Диагностическая информация
        self.diagnostic_label = QLabel("Ожидание данных...")
        self.diagnostic_label.setAlignment(Qt.AlignCenter)
        self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
        layout.addWidget(self.diagnostic_label)
        
        # Детальная диагностика
        self.detailed_diagnostic_label = QLabel("")
        self.detailed_diagnostic_label.setAlignment(Qt.AlignCenter)
        self.detailed_diagnostic_label.setStyleSheet("font-size: 9px; color: #95a5a6;")
        layout.addWidget(self.detailed_diagnostic_label)
        
        # Кнопка тестирования аудио
        self.test_audio_button = QPushButton("🔊 Тест аудио")
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
        layout.addWidget(self.test_audio_button)
        
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
        current_time = time.time()
        
        if self.is_active:
            audio_status = "🔊" if self.audio_initialized else "🔇"
            info = f"{audio_status} Отправлено: {self.sent_packets} | Получено: {self.received_packets} | Буфер: {len(self.audio_buffer)}"
            self.diagnostic_label.setText(info)
            
            # Детальная диагностика каждые 5 секунд
            if current_time - self.last_audio_debug_time > 5:
                self.last_audio_debug_time = current_time
                self.debug_audio_streams()
        else:
            # Показываем информацию о состоянии аудио системы когда звонок не активен
            if self.audio_available:
                if self.audio_initialized:
                    self.diagnostic_label.setText("✅ Аудио система готова")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
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
            
            socket_status = "✅" if hasattr(self, 'call_socket') and self.call_socket else "❌"
            
            debug_info = f"Вход: {'✅' if input_active else '❌'} | Выход: {'✅' if output_active else '❌'} | Сокет: {socket_status}"
            
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
            
            # Тест 4: Проверка воспроизведения на правильном устройстве
            playback_result = self.test_audio_playback_on_correct_device()
            
            # Тест 5: Проверка записи на правильном устройстве
            record_result = self.test_audio_recording_on_correct_device()
            
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
            
            # Используем устройство 1 (встроенная звуковая карта)
            device_id = 1
            
            try:
                duration = 3.0
                sample_rate = 44100
                
                logger.info("🎤 Запись тестового сигнала...")
                
                # Записываем аудио с микрофона
                recording = sd.rec(int(duration * sample_rate), 
                                 samplerate=sample_rate, 
                                 channels=1,
                                 device=device_id)
                sd.wait()
                
                logger.info(f"✅ Записано {len(recording)} сэмплов")
                
                # Воспроизводим записанное аудио
                logger.info("🔊 Воспроизведение записанного сигнала...")
                sd.play(recording, sample_rate, device=device_id)
                sd.wait()
                
                logger.info("✅ Петля запись-воспроизведение работает")
                return True
                
            except Exception as e:
                logger.error(f"❌ Петля не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования петли: {e}")
            return False
    
    def test_audio_playback_on_correct_device(self):
        """Тестирование воспроизведения на правильном устройстве (встроенная звуковая карта)"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ВОСПРОИЗВЕДЕНИЯ НА УСТРОЙСТВЕ 1...")
            
            # Используем устройство 1 (встроенная звуковая карта)
            device_id = 1
            
            try:
                # Создаем простой тестовый тон
                duration = 2.0
                frequency = 440
                sample_rate = 44100
                
                t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
                tone = 0.3 * np.sin(2 * np.pi * frequency * t)
                
                # Пробуем воспроизвести на устройстве 1
                sd.play(tone, sample_rate, device=device_id)
                sd.wait()
                
                logger.info(f"✅ Устройство {device_id} работает: Воспроизведение OK")
                return True
                
            except Exception as e:
                logger.error(f"❌ Устройство {device_id} не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования воспроизведения: {e}")
            return False
    
    def test_audio_recording_on_correct_device(self):
        """Тестирование записи на правильном устройстве (встроенная звуковая карта)"""
        try:
            import sounddevice as sd
            import numpy as np
            
            logger.info("🔊 ТЕСТИРОВАНИЕ ЗАПИСИ НА УСТРОЙСТВЕ 1...")
            
            # Используем устройство 1 (встроенная звуковая карта)
            device_id = 1
            
            try:
                # Пробуем записать короткий фрагмент
                duration = 2.0
                sample_rate = 44100
                
                recording = sd.rec(int(duration * sample_rate), 
                                 samplerate=sample_rate, 
                                 channels=1,
                                 device=device_id)
                sd.wait()
                
                # Проверяем, что записаны не только нули
                max_amplitude = np.max(np.abs(recording))
                logger.info(f"✅ Запись с устройства {device_id} работает: {len(recording)} сэмплов, макс. амплитуда: {max_amplitude:.4f}")
                
                if max_amplitude < 0.001:
                    logger.warning("⚠️ Записаны только тихие сигналы или тишина")
                
                return True
                
            except Exception as e:
                logger.warning(f"❌ Запись с устройства {device_id} не работает: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования записи: {e}")
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
        
    def detect_audio_system(self):
        """Определение звуковой системы - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            import sounddevice as sd
            
            logger.info("🔊 ДИАГНОСТИКА АУДИО СИСТЕМЫ...")
            
            # Получаем информацию об устройствах
            devices = sd.query_devices()
            default_input = sd.default.device[0] if sd.default.device else None
            default_output = sd.default.device[1] if sd.default.device else None
            
            logger.info(f"🔊 Найдено аудио устройств: {len(devices)}")
            logger.info(f"🔊 Устройство ввода по умолчанию: {default_input}")
            logger.info(f"🔊 Устройство вывода по умолчанию: {default_output}")
            
            # Логируем информацию о каждом устройстве
            for i, device in enumerate(devices):
                logger.info(f"🔊 Устройство {i}: {device['name']} - "
                           f"Вход: {device['max_input_channels']} каналов, "
                           f"Выход: {device['max_output_channels']} каналов")
            
            # Проверяем доступность аудио устройств
            if len(devices) > 0:
                self.audio_available = True
                
                # Быстрый тест воспроизведения на правильном устройстве
                test_result = self.test_audio_playback_on_correct_device()
                
                if test_result:
                    audio_system = f"✅ Аудио система обнаружена ({len(devices)} устройств)"
                    self.audio_status_label.setText("🔊 Аудио: система готова (устройство 1)")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
                    self.diagnostic_label.setText("✅ Используется встроенная звуковая карта")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
                else:
                    audio_system = f"⚠️ Аудио система обнаружена, но есть проблемы ({len(devices)} устройств)"
                    self.audio_status_label.setText("🔇 Аудио: есть проблемы")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
                    self.diagnostic_label.setText("⚠️ Нажмите 'Тест аудио' для диагностики")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
                    
                # Показываем информацию об используемом устройстве
                if len(devices) > 1:
                    audio_system += f" | Используется: {devices[1]['name']}"
            else:
                self.audio_available = False
                audio_system = "❌ Аудио устройства не найдены"
                self.audio_status_label.setText("🔇 Аудио: устройства не найдены")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
                self.diagnostic_label.setText("❌ Аудио устройства не найдены")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
                
            self.audio_system_label.setText(audio_system)
            logger.info(f"🔊 Результат диагностики: {audio_system}")
            
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
            
            # Скрываем кнопку тестирования во время звонка
            self.test_audio_button.setVisible(False)
            
            # Запускаем таймер длительности
            self.call_start_time = time.time()
            self.duration_timer.start(1000)
            
            # Запускаем реальные аудио потоки
            if self.audio_available and self.call_type in ['audio', 'video']:
                success = self.initialize_audio_streams()
                if success:
                    self.audio_status_label.setText("🔊 Аудио: подключено (устройство 1)")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #27ae60;")
                    self.diagnostic_label.setText("✅ Аудио потоки активны на встроенной карте")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #27ae60;")
                    
                    # Запускаем приемник аудио данных
                    self.start_audio_receiver()
                    
                    logger.info("✅ Аудио система полностью инициализирована")
                else:
                    self.audio_status_label.setText("🔇 Аудио: ошибка инициализации")
                    self.audio_status_label.setStyleSheet("font-size: 12px; color: #e74c3c;")
                    self.diagnostic_label.setText("❌ Ошибка инициализации аудио")
                    self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
                logger.info("Аудио потоки запущены")
            else:
                logger.info(f"Звонок {self.call_id} начат без аудио")
                self.audio_status_label.setText("🔇 Аудио: отключено")
                self.audio_status_label.setStyleSheet("font-size: 12px; color: #e67e22;")
                self.diagnostic_label.setText("⚠️ Звонок без аудио")
                self.diagnostic_label.setStyleSheet("font-size: 10px; color: #e67e22;")
            
            logger.info(f"Звонок {self.call_id} начат")
            
        except Exception as e:
            logger.error(f"Ошибка начала звонка: {e}")
            self.show_audio_error("Ошибка инициализации звонка")
    
    def initialize_audio_streams(self):
        """Инициализация аудио потоков на правильных устройствах"""
        try:
            if self.audio_initialized:
                logger.info("⚠️ Аудио уже инициализировано")
                return True
    
            import sounddevice as sd
            import numpy as np

            logger.info("🔧 Инициализация аудио потоков на устройстве 1...")
            
            # Пробуем разные конфигурации
            configs = [
                {'samplerate': 44100, 'blocksize': 1024},
                {'samplerate': 22050, 'blocksize': 512},
                {'samplerate': 16000, 'blocksize': 256},
            ]
            
            for config in configs:
                try:
                    logger.info(f"🔧 Попытка конфигурации: {config}")
                    
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
                                    # Логируем каждые 50 пакетов
                                    if self.sent_packets % 50 == 0:
                                        logger.info(f"🎤 Отправлено пакетов: {self.sent_packets}")
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
                                # Логируем каждые 50 пакетов
                                if self.received_packets % 50 == 0:
                                    logger.info(f"🔊 Воспроизведено пакетов: {self.received_packets}")
                            else:
                                # Заполняем тишиной
                                outdata.fill(0)    
                        except Exception as e:
                            logger.debug(f"Ошибка в output callback: {e}")
                            outdata.fill(0)

                    # Создаем потоки с указанием правильного устройства (1)
                    self.input_stream = sd.InputStream(
                        device=self.input_device,  # Используем устройство 1
                        samplerate=config['samplerate'],
                        blocksize=config['blocksize'],
                        channels=self.channels,
                        callback=input_callback,
                        dtype=np.float32
                    )
                    
                    self.output_stream = sd.OutputStream(
                        device=self.output_device,  # Используем устройство 1
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
                    logger.info(f"✅ Аудио потоки успешно инициализированы на устройстве 1 с конфигурацией: {config}")
                    return True
                    
                except Exception as e:
                    logger.warning(f"❌ Конфигурация {config} не сработала на устройстве 1: {e}")
                    # Останавливаем потоки, если они были созданы
                    self.stop_audio_streams()
                    continue
            
            logger.error("❌ Все конфигурации аудио не сработали на устройстве 1")
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
            self.audio_initialized = False 
            self.is_active = False

            # Останавливаем INPUT STREAM
            if hasattr(self, 'input_stream') and self.input_stream is not None:
                try:
                    self.input_stream.stop()
                    self.input_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки input stream: {e}")
                self.input_stream = None
                
            # Останавливаем OUTPUT STREAM
            if hasattr(self, 'output_stream') and self.output_stream is not None:
                try:
                    self.output_stream.stop()
                    self.output_stream.close()
                except Exception as e:
                    logger.debug(f"Ошибка остановки output stream: {e}")
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