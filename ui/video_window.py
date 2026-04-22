#!/usr/bin/env python3
"""
Модуль для видеозвонков в мессенджере ДИАЛОГ - исправленная версия
"""

import sys
import os
import cv2
import queue
import threading
import time
import struct
import sounddevice as sd
import numpy as np
import logging
import socket
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGroupBox, QSizePolicy, QDialog,
                             QFormLayout, QComboBox, QDialogButtonBox)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize, QThread, pyqtSignal as Signal
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPalette, QColor, QRadialGradient


logger = logging.getLogger('dialog_video')

class VideoCaptureThread(QThread):
    """Поток для захвата видео с камеры"""
    
    frame_ready = Signal(np.ndarray)
    
    def __init__(self, camera_index=0, width=640, height=480, fps=30):
        super().__init__()
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self.camera = None
        self.last_frame = None
        
    def run(self):
        """Основной цикл захвата видео"""
        try:
            logger.info(f"Запуск захвата видео с камеры {self.camera_index}")
            
            # Открываем камеру
            self.camera = cv2.VideoCapture(self.camera_index)
            
            if not self.camera.isOpened():
                logger.error(f"Не удалось открыть камеру {self.camera_index}")
                return
            
            # Настраиваем параметры камеры
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.camera.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Пробуем установить кодек MJPG для лучшей цветопередачи
            try:
                self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            except:
                pass
            
            # Читаем реальные параметры
            actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"Камера настроена: {actual_width}x{actual_height} @ {actual_fps} FPS")
            
            self.running = True
            
            while self.running:
                try:
                    ret, frame = self.camera.read()
                    if ret and frame is not None:
                        # Сохраняем кадр
                        self.last_frame = frame
                        # Отправляем сигнал с кадром
                        self.frame_ready.emit(frame)
                    
                    # Пауза для достижения нужного FPS
                    time.sleep(1.0 / self.fps)
                    
                except Exception as e:
                    logger.error(f"Ошибка захвата кадра: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке захвата видео: {e}")
        finally:
            self.stop_capture()
            
    def stop_capture(self):
        """Остановка захвата видео"""
        self.running = False
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            logger.info("Камера освобождена")
            
    def get_last_frame(self):
        """Получить последний захваченный кадр"""
        return self.last_frame
        
    def __del__(self):
        self.stop_capture()

class VideoWidget(QLabel):
    """Виджет для отображения видео"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMaximumSize(1920, 1080)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("""
            QLabel {
                border: 2px solid #3498db;
                border-radius: 8px;
                background-color: #000000;
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Видео не доступно")
        self.setScaledContents(True)
        
    def update_frame(self, frame):
        """Обновить кадр видео"""
        if frame is not None and len(frame) > 0:
            try:
                # Проверяем размеры кадра
                if len(frame.shape) == 2:
                    # Черно-белое изображение - конвертируем в цветное
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                elif len(frame.shape) == 3:
                    # Цветное изображение
                    if frame.shape[2] == 4:
                        # RGBA -> RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                    elif frame.shape[2] == 3:
                        # BGR -> RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                
                # Создаем QImage
                qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                self.setPixmap(QPixmap.fromImage(qt_image))
                self.setText("")
                
            except Exception as e:
                logger.error(f"Ошибка обновления кадра: {e}")
                self.setText(f"Ошибка: {str(e)[:50]}")
        else:
            self.setText("Нет видео")
            
    def clear_video(self):
        """Очистить видео"""
        self.setText("Видео не доступно")
        self.clear()

class VideoProcessor:
    """Процессор для обработки видео"""
    
    def __init__(self):
        self.frame_queue = queue.Queue(maxsize=10)
        self.processed_queue = queue.Queue(maxsize=10)
        self.running = False
        self.thread = None
        
    def start(self):
        """Запуск обработки видео"""
        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Остановка обработки видео"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            
    def put_frame(self, frame):
        """Добавить кадр для обработки"""
        try:
            if not self.frame_queue.full():
                self.frame_queue.put_nowait(frame)
        except queue.Full:
            # Очищаем очередь если переполнена
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.put_nowait(frame)
            except:
                pass
                
    def get_processed_frame(self):
        """Получить обработанный кадр"""
        try:
            return self.processed_queue.get_nowait()
        except queue.Empty:
            return None
            
    def _process_loop(self):
        """Цикл обработки видео"""
        while self.running:
            try:
                # Получаем кадр из очереди
                try:
                    frame = self.frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                if frame is None:
                    continue
                
                # Обработка кадра
                processed = self.process_frame(frame)
                
                # Добавляем в очередь обработанных
                try:
                    if not self.processed_queue.full():
                        self.processed_queue.put_nowait(processed)
                except queue.Full:
                    pass
                    
            except Exception as e:
                logger.error(f"Ошибка обработки видео: {e}")
                time.sleep(0.01)
                
    def process_frame(self, frame):
        """Обработка одного кадра"""
        try:
            # Изменение размера если нужно
            target_width = 640
            target_height = 480
            
            h, w = frame.shape[:2]
            if w != target_width or h != target_height:
                frame = cv2.resize(frame, (target_width, target_height))
            
            # Улучшение цветов
            frame = self.enhance_colors(frame)
            
            # Улучшение резкости
            frame = self.sharpen_image(frame)
            
            # Коррекция гаммы
            frame = self.gamma_correction(frame, 1.2)
            
            # Автоматическая коррекция яркости/контраста
            frame = self.auto_brightness_contrast(frame)
            
            return frame
            
        except Exception as e:
            logger.error(f"Ошибка обработки кадра: {e}")
            return frame
            
    def enhance_colors(self, frame):
        """Улучшение цветов"""
        try:
            # Конвертируем в HSV для работы с насыщенностью
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # Увеличиваем насыщенность
            hsv[:, :, 1] = cv2.multiply(hsv[:, :, 1], 1.3)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            
            # Конвертируем обратно в BGR
            enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            
            return enhanced
            
        except:
            return frame
            
    def sharpen_image(self, frame):
        """Увеличение резкости"""
        try:
            kernel = np.array([[-1, -1, -1],
                               [-1,  9, -1],
                               [-1, -1, -1]])
            sharpened = cv2.filter2D(frame, -1, kernel)
            return sharpened
        except:
            return frame
            
    def gamma_correction(self, frame, gamma=1.0):
        """Коррекция гаммы"""
        try:
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255
                              for i in np.arange(0, 256)]).astype("uint8")
            corrected = cv2.LUT(frame, table)
            return corrected
        except:
            return frame
            
    def auto_brightness_contrast(self, frame):
        """Автоматическая коррекция яркости и контраста"""
        try:
            # Конвертируем в YUV
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV)
            
            # Нормализуем яркость (канал Y)
            y = yuv[:, :, 0]
            y_eq = cv2.equalizeHist(y)
            yuv[:, :, 0] = y_eq
            
            # Конвертируем обратно
            corrected = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
            
            return corrected
        except:
            return frame

class VideoCallWindow(QWidget):
    """Окно видеозвонка"""
    
    call_ended = pyqtSignal(str)
    call_accepted = pyqtSignal(str)
    call_rejected = pyqtSignal(str)
    video_toggled = pyqtSignal(bool)
    
    def __init__(self, username, call_id, is_outgoing=True, parent=None,
                 camera_index=0, resolution=(640,480), fps=30, quality=85, color_enhancement=True,
                 input_device=None, output_device=None):
        super().__init__(parent)
        self.username = username
        self.call_id = call_id
        self.is_outgoing = is_outgoing
        self._is_closing = False

        

        # Вместо аудио-окна создаём ядро аудио
        self.audio_core = AudioCallCore(call_id)

        
        # Видео параметры
        self.camera_index = camera_index
        self.resolution = resolution
        self.fps = fps
        self.quality = quality
        self.color_enhancement = color_enhancement
        self.color_enhancement_enabled = self.color_enhancement  # для совместимости с обработчиком
        self.video_enabled = True
        
        # Компоненты
        self.capture_thread = None
        self.video_processor = VideoProcessor()        
        self.remote_frame_queue = queue.Queue(maxsize=5)
        
        # Сокеты для видео
        self.video_socket = None
        self.video_socket_set = False
        self.socket_check_timer = QTimer()
        self.socket_check_timer.timeout.connect(self.check_video_socket)
        self.socket_attempts = 0
        self.max_socket_attempts = 5
                
        # Буферы для видео
        self.local_frame = None
        self.display_timer = QTimer()
        
        # UI
        self.init_ui()
        self.setup_video_capture()
     
    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle(f"📹 Видеозвонок с {self.username}")
        self.setMinimumSize(800, 600)
        self.setMaximumSize(1240, 650)
        self.resize(1024, 768)

        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        

        self.setStyleSheet("""
            QGroupBox {
                background-color: transparent;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                font-size: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        # Основной layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Заголовок
        title_label = QLabel(f"📹 Видеозвонок с {self.username}")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #ffffff;
            margin-bottom: 15px;
        """)
        main_layout.addWidget(title_label)
        
        # Область видео
        video_layout = QHBoxLayout()
        
        # Локальное видео (маленькое)
        self.local_video_widget = VideoWidget()
        self.local_video_widget.setMinimumSize(240, 180)
        self.local_video_widget.setMaximumSize(480, 360)
        self.local_video_widget.setStyleSheet("""
            QLabel {
                border: 2px solid #27ae60;
                border-radius: 8px;
                background-color: #000000;
            }
        """)
        self.local_video_widget.setText("Локальная камера")
        
        # Удаленное видео (большое)
        self.remote_video_widget = VideoWidget()
        self.remote_video_widget.setMinimumSize(640, 480)
        self.remote_video_widget.setText(f"Ожидание видео от {self.username}")
        
        video_layout.addWidget(self.remote_video_widget, 3)
        video_layout.addWidget(self.local_video_widget, 1)
        
        main_layout.addLayout(video_layout, 3)
        
        # Статус
        self.status_label = QLabel("🟡 Подготовка видеозвонка...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #f39c12;
            margin: 10px 0;
            padding: 8px;
            background-color: transparent;
            border-radius: 6px;
        """)
        main_layout.addWidget(self.status_label)
        
        # Информация о качестве
        self.quality_label = QLabel(f"Качество: {self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps")
        self.quality_label.setAlignment(Qt.AlignCenter)
        self.quality_label.setStyleSheet("""
            font-size: 12px;
            color: #7f8c8d;
            margin: 5px 0;
        """)
        main_layout.addWidget(self.quality_label)
        
        # Панель управления
        control_group = QGroupBox("Управление видеозвонком")
        control_layout = QHBoxLayout()
        
        # Кнопка включения/выключения видео
        self.video_toggle_button = QPushButton("📹 Выключить видео")
        self.video_toggle_button.setFixedHeight(40)
        self.video_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.video_toggle_button.clicked.connect(self.toggle_video)
        control_layout.addWidget(self.video_toggle_button)
        
        # Кнопка отключения микрофона
        self.mute_button = QPushButton("🔇 Выключить микрофон")
        self.mute_button.setFixedHeight(40)
        self.mute_button.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.mute_button.clicked.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_button)
        
        
        # Кнопка настроек видео
        self.settings_button = QPushButton("⚙️ Настройки видео")
        self.settings_button.setFixedHeight(40)
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.settings_button.clicked.connect(self.open_video_settings)
        control_layout.addWidget(self.settings_button)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Кнопки звонка
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(20)
        
        if self.is_outgoing:
            # Для исходящего звонка
            self.end_button = QPushButton("📹 Завершить видеозвонок")
            self.end_button.setFixedHeight(50)
            self.end_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.end_button.clicked.connect(self.end_call)
            self.buttons_layout.addWidget(self.end_button)       
        else:
            # Для входящего звонка
            self.accept_button = QPushButton("✅ Принять видео")
            self.accept_button.setFixedHeight(50)
            self.accept_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            self.accept_button.clicked.connect(self.accept_call)
            
            self.reject_button = QPushButton("❌ Отклонить")
            self.reject_button.setFixedHeight(50)
            self.reject_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.reject_button.clicked.connect(self.reject_call)
            
            self.buttons_layout.addWidget(self.accept_button)
            self.buttons_layout.addWidget(self.reject_button)
        
        main_layout.addLayout(self.buttons_layout)
        
        self.setLayout(main_layout)
        
        # Таймер для обновления UI
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(33)  # ~30 FPS для UI
        
    def setup_video_capture(self):
        """Настройка захвата видео"""
        self.stop_video_capture()

        try:
            # Находим доступные камеры
            self.available_cameras = self.detect_cameras()
            
            if not self.available_cameras:
                logger.warning("Камеры не найдены")
                self.video_enabled = False
                self.video_toggle_button.setText("📷 Камера не найдена")
                self.video_toggle_button.setEnabled(False)
                self.status_label.setText("❌ Камера не найдена")
                return
            
            # Создаем и настраиваем поток захвата видео
            self.capture_thread = VideoCaptureThread(
                camera_index=self.camera_index,
                width=self.resolution[0],
                height=self.resolution[1],
                fps=self.fps
            )
            
            # Подключаем сигнал готового кадра
            self.capture_thread.frame_ready.connect(self.handle_frame_ready)
            
            # Запускаем обработчик видео
            self.video_processor.start()
            
            logger.info("Видео захват настроен")
            self.status_label.setText("🟢 Камера готова")
            
        except Exception as e:
            logger.error(f"Ошибка настройки камеры: {e}")
            self.video_enabled = False
            self.status_label.setText(f"❌ Ошибка камеры: {str(e)[:50]}")
    
    def detect_cameras(self):
        """Обнаружение доступных камер"""
        cameras = []
        for i in range(4):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        logger.info(f"Найдена камера {i}: {frame.shape}")
                        cameras.append(i)
                    cap.release()
            except Exception as e:
                logger.debug(f"Ошибка проверки камеры {i}: {e}")
        return cameras
    
    def handle_frame_ready(self, frame):
        """Обработка готового кадра с камеры"""
        try:
            if frame is not None:
                # Обработка кадра
                if self.color_enhancement_enabled:
                    self.video_processor.put_frame(frame)
                    processed = self.video_processor.get_processed_frame()
                    if processed is not None:
                        self.local_frame = processed
                    else:
                        # Если обработчик не успел, используем исходный кадр
                        self.local_frame = frame
                else:
                    # Простая обработка без улучшения цветов
                    h, w = frame.shape[:2]
                    if w != 640 or h != 480:
                        frame = cv2.resize(frame, (640, 480))
                    self.local_frame = frame
                
                # Отправка по сети
                if self.video_socket and self.video_socket_set:
                    self.send_video_frame(self.local_frame)
                    
        except Exception as e:
            logger.error(f"Ошибка обработки кадра: {e}")
    
    def send_video_frame(self, frame):
        """Отправка кадра видео"""
        try:
            if frame is None:
                return
            if not self.video_socket or self.video_socket.fileno() == -1 or not self.is_socket_connected(self.video_socket):
                logger.warning("Сокет не подключён, отправка невозможна")
                return
            
            # Конвертируем BGR в RGB для лучшей цветопередачи
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                frame_rgb = frame
            
            # Сжимаем кадр в JPEG для уменьшения размера
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
            success, encoded = cv2.imencode('.jpg', frame_rgb, encode_param)
            
            if success:
                # Сериализация сжатого кадра
                data = encoded.tobytes()
                data_size = len(data)
                
                # Создание заголовка
                header = struct.pack('III', data_size, 640, 480)
                
                # Отправка
                full_data = header + data
                self.video_socket.sendall(full_data)
                
        except Exception as e:
            logger.error(f"Ошибка отправки видео: {e}")
            self.video_socket_set = False
    
    def receive_video_frame(self):
        """Прием кадра видео"""
        try:
            if not self.video_socket or self.video_socket.fileno() == -1 or not self.is_socket_connected(self.video_socket):
                return None
            # Чтение заголовка
            header = self.video_socket.recv(12)  # 3 int по 4 байта
            if len(header) < 12:
                return None
            
            data_size, width, height = struct.unpack('III', header)
            
            # Чтение данных
            data = b''
            while len(data) < data_size:
                chunk = self.video_socket.recv(min(4096, data_size - len(data)))
                if not chunk:
                    break
                data += chunk
            
            if len(data) == data_size:
                # Декодируем JPEG
                nparr = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    # Конвертируем RGB в BGR для OpenCV
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    return frame
            
            return None
        except OSError as e:
            if e.errno == 107:  # ENOTCONN
                logger.warning("Сокет не подключён при приёме видео")
            elif e.errno == 9:
                logger.warning("Сокет закрыт при приёме кадра")
            else:
                logger.error(f"Ошибка приёма видео: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка приема видео: {e}")
            return None
    
    def receive_video_loop(self):
        """Цикл приема видео"""
        logger.info("🟢 Поток приёма видео запущен")
        frame_count = 0
        try:
            while self.video_socket_set and self.video_socket:
                # Проверяем, не закрыт ли сокет
                if self.video_socket.fileno() == -1 or not self.is_socket_connected(self.video_socket):
                    logger.warning("Видео-сокет закрыт, выходим из цикла приёма")
                    break
                frame = self.receive_video_frame()
                if frame is not None:
                    try:
                        # Если очередь переполнена, удаляем старый кадр
                        if self.remote_frame_queue.full():
                            self.remote_frame_queue.get_nowait()
                        self.remote_frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass
                time.sleep(0.001)
            self.video_socket_set = False
        except OSError as e:
            if e.errno == 9:  # Bad file descriptor
                logger.warning("Видео-сокет был закрыт во время приёма")
            else:
                logger.error(f"Ошибка в receive_video_loop: {e}")
        except Exception as e:
            logger.error(f"Ошибка в receive_video_loop: {e}")
        finally:
            self.video_socket_set = False
    
    def update_ui(self):
        """Обновление UI"""
        if self.local_frame is not None:
            self.local_video_widget.update_frame(self.local_frame)
        try:
            frame = self.remote_frame_queue.get_nowait()
            if frame is not None:
                self.remote_video_widget.update_frame(frame)
        except queue.Empty:
            pass        
        # Обновление статуса
        self.update_status()
    
    def update_status(self):
        """Обновление статуса"""
        if not self.video_enabled:
            self.status_label.setText("❌ Видео отключено")
            self.status_label.setStyleSheet("font-size: 16px; color: #e74c3c;")
        elif not self.video_socket_set:
            self.status_label.setText("🟡 Ожидание видео-соединения...")
            self.status_label.setStyleSheet("font-size: 16px; color: #f39c12;")
        elif self.local_frame is not None and self.remote_frame_queue.qsize() > 0:
            self.status_label.setText("🟢 Видеозвонок активен")
            self.status_label.setStyleSheet("font-size: 16px; color: #27ae60;")
        elif self.local_frame is not None:
            self.status_label.setText("🟡 Передача видео...")
            self.status_label.setStyleSheet("font-size: 16px; color: #f39c12;")
    
    def toggle_video(self):
        """Включение/выключение видео"""
        self.video_enabled = not self.video_enabled
        
        if self.video_enabled:
            self.video_toggle_button.setText("📹 Выключить видео")
            self.setup_video_capture()
            if self.capture_thread:
                self.capture_thread.start()
            self.status_label.setText("🟢 Видео включено")
        else:
            self.video_toggle_button.setText("📹 Включить видео")
            self.stop_video_capture()
            self.status_label.setText("❌ Видео отключено")
        
        self.video_toggled.emit(self.video_enabled)
    
    def toggle_mute(self):
        """Включить/выключить микрофон в скрытом аудио-окне"""
        if hasattr(self.audio_core, 'toggle_mute'):
            self.audio_core.toggle_mute()
            if self.audio_core.muted:
                self.mute_button.setText("🔊 Включить микрофон")
                self.mute_button.setStyleSheet("""
                    QPushButton {
                        background-color: #95a5a6;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #7f8c8d;
                    }
                """)
            else:
                self.mute_button.setText("🔇 Выключить микрофон")
                self.mute_button.setStyleSheet("""
                    QPushButton {
                        background-color: #e67e22;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #d35400;
                    }
                """)
        else:
            logger.warning("Метод toggle_mute не найден в audio_call")

    def stop_video_capture(self):
        """Остановка захвата видео"""
        if self.capture_thread:
            self.capture_thread.stop_capture()
            self.capture_thread.wait()
            self.capture_thread = None
        if self.video_processor:
            self.video_processor.stop()
        self.local_video_widget.setText("Камера выключена")
        logger.info("Захват видео остановлен")
    
    def open_video_settings(self):
        """Открыть окно настроек видео"""
        was_running = self.capture_thread and self.capture_thread.isRunning()
        if was_running:
            self.stop_video_capture()
        
        from settings_window import SettingsDialog
        dlg = SettingsDialog(parent=self,
                             input_device=None,
                             output_device=None)
        
        # Сохраняем ссылку на was_running для использования в обработчике
        def on_video_settings_changed(settings):
            if 'camera_index' in settings:
                self.camera_index = settings['camera_index']
            if 'resolution' in settings:
                self.resolution = settings['resolution']
                # Обновляем отображение качества
                self.quality_label.setText(f"Качество: {self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps")
            if 'fps' in settings:
                self.fps = settings['fps']
                self.quality_label.setText(f"Качество: {self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps")
            if 'quality' in settings:
                self.quality = settings['quality']
            if 'color_enhancement' in settings:
                self.color_enhancement = settings['color_enhancement']
                self.color_enhancement_enabled = self.color_enhancement
            
            if self.video_enabled:
                self.setup_video_capture()
                if was_running and self.capture_thread:
                    self.capture_thread.start()
        
        dlg.settings_changed.connect(on_video_settings_changed)
        dlg.exec_()
    
    def is_socket_connected(self, sock):
        try:
            # getpeername() выбрасывает исключение, если сокет не подключён
            sock.getpeername()
            return True
        except:
            return False

    def set_video_socket(self, socket):
        """Установка сокета для видео"""
        self.video_socket = socket
        self.video_socket_set = True
        self.socket_attempts = 0
        # Проверяем состояние сразу
        self.check_video_socket()
        return True


    def check_video_socket(self):
        if not self.video_socket_set:
            return
        if self.video_socket and self.video_socket.fileno() != -1 and self.is_socket_connected(self.video_socket):
            # Сокет подключён – запускаем поток приёма
            self.receive_thread = threading.Thread(target=self.receive_video_loop, daemon=True)
            self.receive_thread.start()
            self.status_label.setText("🟢 Видео-соединение установлено")
            self.socket_check_timer.stop()
        else:
            self.socket_attempts += 1
            if self.socket_attempts >= self.max_socket_attempts:
                self.socket_check_timer.stop()
                self.status_label.setText("❌ Видео-сокет не готов или не подключён")
                logger.warning("Видео-сокет так и не стал подключённым")
            else:
                # Повторим проверку через 0.5 сек
                self.socket_check_timer.start(500)

    def set_audio_socket(self, socket):
        """Передать аудио-сокет от P2P сети"""
        self.audio_core.set_socket(socket)
        

    def start_call(self):
        """Начать видеозвонок после получения подтверждения"""
        if self.video_enabled and self.capture_thread and not self.capture_thread.isRunning():
            self.capture_thread.start()
        self.audio_core.start()          
        # запускает аудио
        self.status_label.setText("🟢 Видеозвонок активен")
        self.status_label.setStyleSheet("font-size: 16px; color: #ffffff;")

    def accept_call(self):
        """Принять видеозвонок"""
        self.call_accepted.emit(self.call_id)
        self.status_label.setText("✅ Видеозвонок принят")
        self.start_call()

        # Прячем кнопки принятия/отклонения
        self.accept_button.setVisible(False)
        self.reject_button.setVisible(False)
        
        # Удаляем старую кнопку завершения, если она уже есть
        if hasattr(self, 'end_button') and self.end_button is not None:
            self.end_button.setParent(None)
            self.end_button.deleteLater()
        
        # Показываем кнопку завершения
        self.end_button = QPushButton("📹 Завершить видеозвонок")
        self.end_button.setFixedHeight(50)
        self.end_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.end_button.clicked.connect(self.end_call)
        self.buttons_layout.addWidget(self.end_button)
           
    def reject_call(self):
        """Отклонить видеозвонок"""
        self.call_rejected.emit(self.call_id)
        self.close()
    
    def end_call(self):
        """Завершить видеозвонок"""
        self.stop_video_capture()
        self.audio_core.stop()
        self.video_socket_set = False
        if self.video_socket:
            try:
                self.video_socket.close()
            except:
                pass
        self.call_ended.emit(self.call_id)
        self.close()
    
    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return
        self._is_closing = True
        self.stop_video_capture()
        self.video_socket_set = False
        if self.video_socket:
            self.video_socket.close()
        self.audio_core.stop()
        if hasattr(self, 'receive_thread') and self.receive_thread:
            self.receive_thread.join(timeout=1.0)
        event.accept()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
   
        center = rect.center()
        radius = max(rect.width(), rect.height()) // 2
        
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0, QColor(10, 10, 50, 100))
        gradient.setColorAt(1, QColor(25, 25, 112, 255))

        painter.fillRect(rect, gradient)
        

class AudioCallCore:
    """Управляет аудио-потоками для видеозвонка (без GUI)"""
    def __init__(self, call_id, sample_rate=44100, chunk_size=1024):
        self.call_id = call_id
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_socket = None
        self.is_running = False
        self.input_stream = None
        self.output_stream = None
        self._recv_thread = None
        self._send_thread = None
        self._send_queue = queue.Queue(maxsize=50)
        self._recv_queue = queue.Queue(maxsize=50)
        self.muted = False
        self._stop_requested = False

    def set_socket(self, sock):
        self.audio_socket = sock
        if self.audio_socket:
            self.audio_socket.settimeout(0.1)
            self.audio_socket.setblocking(False)
        if self.is_running:
            self.start_streams()

    def start_streams(self):
        if not self.audio_socket:
            logger.warning("AudioCallCore: нет сокета для запуска потоков")
            return
        try:
            self.input_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='int16',
                blocksize=self.chunk_size,
                callback=self._audio_input_callback
            )
            self.output_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='int16',
                blocksize=self.chunk_size,
                callback=self._audio_output_callback
            )
            self.input_stream.start()
            self.output_stream.start()

            self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._send_thread.start()
            self._recv_thread.start()

            logger.info(f"AudioCallCore: аудио-потоки запущены для звонка {self.call_id}")
        except Exception as e:
            logger.error(f"AudioCallCore: ошибка инициализации аудио: {e}")
            self.stop()

    def _audio_input_callback(self, indata, frames, time, status):
        if status:
            logger.debug(f"Аудио входной статус: {status}")
        if not self.muted and self.is_running:
            try:
                data = indata.tobytes()
                self._send_queue.put_nowait(data)
            except queue.Full:
                pass

    def _audio_output_callback(self, outdata, frames, time, status):
        if status:
            logger.debug(f"Аудио выходной статус: {status}")
        try:
            data = self._recv_queue.get_nowait()
            samples = np.frombuffer(data, dtype=np.int16).reshape(-1, 1)
            if len(samples) < frames:
                outdata[:len(samples)] = samples
                outdata[len(samples):].fill(0)
            else:
                outdata[:] = samples[:frames]
        except queue.Empty:
            outdata.fill(0)

    def _send_loop(self):
        while self.is_running and not self._stop_requested and self.audio_socket:
            try:
                data = self._send_queue.get(timeout=0.1)
                try:
                    self.audio_socket.sendall(data)
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    # Сокет закрыт на другой стороне - выходим из цикла
                    logger.warning(f"AudioCallCore: сокет закрыт при отправке ({e})")
                    break
                except BlockingIOError:
                    self._send_queue.put(data)
                    time.sleep(0.01)
                except Exception as e:
                    logger.error(f"Ошибка отправки аудио: {e}")
            except queue.Empty:
                continue
        logger.info(f"AudioCallCore: поток отправки завершён для звонка {self.call_id}")

    def _recv_loop(self):
        try:
            while self.is_running and not self._stop_requested and self.audio_socket:
                try:
                    data = self.audio_socket.recv(self.chunk_size * 2)
                    if data:
                        self._recv_queue.put(data)
                except socket.timeout:
                    continue
                except BlockingIOError:
                    time.sleep(0.001)
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    # Сокет закрыт - выходим
                    logger.warning(f"AudioCallCore: сокет закрыт при приёме ({e})")
                    break
                except Exception as e:
                    logger.error(f"AudioCallCore: ошибка в recv_loop: {e}")
                    break
        except Exception as e:
            logger.error(f"AudioCallCore: критическая ошибка в recv_loop: {e}")
        logger.info(f"AudioCallCore: поток приёма завершён для звонка {self.call_id}")

    def start(self):
        self.is_running = True
        if self.audio_socket:
            self.start_streams()

    def stop(self):
        self.is_running = False
        if self.input_stream:
            try:
                self.input_stream.stop()
                self.input_stream.close()
            except:
                pass
            self.input_stream = None
        if self.output_stream:
            try:
                self.output_stream.stop()
                self.output_stream.close()
            except:
                pass
            self.output_stream = None
        if self.audio_socket:
            try:
                self.audio_socket.close()
            except:
                pass
            self.audio_socket = None
        logger.info(f"AudioCallCore: аудио-потоки остановлены для звонка {self.call_id}")

    def toggle_mute(self):
        self.muted = not self.muted
        logger.info(f"AudioCallCore: микрофон {'выключен' if self.muted else 'включен'}")