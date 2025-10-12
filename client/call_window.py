import time
import cv2
import numpy as np
import pyaudio
import threading
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                             QHBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
import logging

logger = logging.getLogger('dialog_gui')

class CallWindow(QDialog):
    """Окно аудио/видео звонка"""
    
    call_ended = pyqtSignal(str)  # call_id
    call_accepted = pyqtSignal(str)  # call_id
    call_rejected = pyqtSignal(str)  # call_id
    
    def __init__(self, username, call_type, call_id, is_outgoing=True, parent=None):
        super().__init__(parent)
        self.username = username
        self.call_type = call_type  # 'audio' или 'video'
        self.call_id = call_id
        self.is_outgoing = is_outgoing
        self.is_active = False
        self.audio_active = True
        self.video_active = True
        
        # Для аудио
        self.audio = pyaudio.PyAudio()
        self.audio_stream_in = None
        self.audio_stream_out = None
        self.audio_thread = None
        self.stop_audio = False
        
        # Для видео
        self.video_capture = None
        self.video_thread = None
        self.stop_video = False
        
        self.init_ui()
        
    def init_ui(self):
        call_type_text = "Видео" if self.call_type == 'video' else "Аудио"
        direction_text = "Исходящий" if self.is_outgoing else "Входящий"
        self.setWindowTitle(f'{call_type_text} звонок {direction_text} - {self.username}')
        self.setFixedSize(600, 500)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Заголовок
        title = QLabel(f"{call_type_text} звонок с {self.username}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 20px; 
            font-weight: bold; 
            color: #2c3e50;
            margin-bottom: 10px;
        """)
        layout.addWidget(title)
        
        # Статус звонка
        self.status_label = QLabel("Установка соединения..." if self.is_outgoing else "Входящий звонок...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        layout.addWidget(self.status_label)
        
        # Видео область (только для видео звонков)
        if self.call_type == 'video':
            video_layout = QHBoxLayout()
            
            # Локальное видео
            self.local_video_label = QLabel("Локальная камера")
            self.local_video_label.setAlignment(Qt.AlignCenter)
            self.local_video_label.setFixedSize(240, 180)
            self.local_video_label.setStyleSheet("""
                QLabel {
                    background-color: #34495e;
                    border: 2px solid #2c3e50;
                    border-radius: 8px;
                    color: #ecf0f1;
                    font-size: 12px;
                }
            """)
            video_layout.addWidget(self.local_video_label)
            
            # Удаленное видео
            self.remote_video_label = QLabel("Удаленный пользователь")
            self.remote_video_label.setAlignment(Qt.AlignCenter)
            self.remote_video_label.setFixedSize(240, 180)
            self.remote_video_label.setStyleSheet("""
                QLabel {
                    background-color: #34495e;
                    border: 2px solid #2c3e50;
                    border-radius: 8px;
                    color: #ecf0f1;
                    font-size: 12px;
                }
            """)
            video_layout.addWidget(self.remote_video_label)
            
            layout.addLayout(video_layout)
        else:
            # Для аудио звонка - иконка
            audio_icon = QLabel("🎧")
            audio_icon.setAlignment(Qt.AlignCenter)
            audio_icon.setStyleSheet("font-size: 80px; margin: 20px;")
            layout.addWidget(audio_icon)
        
        # Индикаторы
        indicators_layout = QHBoxLayout()
        
        # Индикатор микрофона
        self.mic_indicator = QLabel("🎤")
        self.mic_indicator.setAlignment(Qt.AlignCenter)
        self.mic_indicator.setStyleSheet("font-size: 20px;")
        indicators_layout.addWidget(self.mic_indicator)
        
        # Индикатор камеры (только для видео)
        if self.call_type == 'video':
            self.camera_indicator = QLabel("📹")
            self.camera_indicator.setAlignment(Qt.AlignCenter)
            self.camera_indicator.setStyleSheet("font-size: 20px;")
            indicators_layout.addWidget(self.camera_indicator)
        
        # Индикатор соединения
        self.connection_indicator = QLabel("🔴")
        self.connection_indicator.setAlignment(Qt.AlignCenter)
        self.connection_indicator.setStyleSheet("font-size: 20px;")
        indicators_layout.addWidget(self.connection_indicator)
        
        layout.addLayout(indicators_layout)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        # Кнопка микрофона
        self.mic_btn = QPushButton("🎤 Выкл")
        self.mic_btn.setFixedSize(80, 40)
        self.mic_btn.clicked.connect(self.toggle_microphone)
        buttons_layout.addWidget(self.mic_btn)
        
        # Кнопка камеры (только для видео)
        if self.call_type == 'video':
            self.camera_btn = QPushButton("📹 Выкл")
            self.camera_btn.setFixedSize(80, 40)
            self.camera_btn.clicked.connect(self.toggle_camera)
            buttons_layout.addWidget(self.camera_btn)
        
        # Кнопка завершения звонка
        self.end_call_btn = QPushButton("📞 Завершить")
        self.end_call_btn.setFixedSize(120, 50)
        self.end_call_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.end_call_btn.clicked.connect(self.end_call)
        buttons_layout.addWidget(self.end_call_btn)
        
        # Кнопка принятия звонка (только для входящих)
        if not self.is_outgoing:
            self.accept_call_btn = QPushButton("📞 Принять")
            self.accept_call_btn.setFixedSize(120, 50)
            self.accept_call_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2ecc71;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                }
            """)
            self.accept_call_btn.clicked.connect(self.accept_call)
            buttons_layout.addWidget(self.accept_call_btn)
            
            # Кнопка отклонения звонка
            self.reject_call_btn = QPushButton("📞 Отклонить")
            self.reject_call_btn.setFixedSize(120, 50)
            self.reject_call_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            self.reject_call_btn.clicked.connect(self.reject_call)
            buttons_layout.addWidget(self.reject_call_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
        # Таймер для обновления UI
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(100)
        
    def update_ui(self):
        """Обновление UI звонка"""
        # Обновляем индикаторы
        if self.audio_active:
            self.mic_indicator.setText("🎤")
            self.mic_btn.setText("🎤 Вкл")
        else:
            self.mic_indicator.setText("🔇")
            self.mic_btn.setText("🎤 Выкл")
            
        if self.call_type == 'video':
            if self.video_active:
                self.camera_indicator.setText("📹")
                self.camera_btn.setText("📹 Вкл")
            else:
                self.camera_indicator.setText("📷❌")
                self.camera_btn.setText("📹 Выкл")
        
        if self.is_active:
            self.connection_indicator.setText("🟢")
            self.status_label.setText("Соединение установлено")
        else:
            self.connection_indicator.setText("🟡")
            
    def start_call(self):
        """Начать звонок"""
        self.is_active = True
        self.start_audio()
        if self.call_type == 'video':
            self.start_video()
            
    def accept_call(self):
        """Принять входящий звонок"""
        self.is_active = True
        if hasattr(self, 'accept_call_btn'):
            self.accept_call_btn.hide()
        if hasattr(self, 'reject_call_btn'):
            self.reject_call_btn.hide()
        self.start_audio()
        if self.call_type == 'video':
            self.start_video()
        self.call_accepted.emit(self.call_id)
        
    def start_audio(self):
        """Запуск аудио"""
        try:
            # Формат аудио
            format = pyaudio.paInt16
            channels = 1
            rate = 44100
            chunk = 1024
            
            # Входной поток (микрофон)
            self.audio_stream_in = self.audio.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk
            )
            
            # Выходной поток (динамики)
            self.audio_stream_out = self.audio.open(
                format=format,
                channels=channels,
                rate=rate,
                output=True,
                frames_per_buffer=chunk
            )
            
            # Запускаем поток для захвата аудио
            self.stop_audio = False
            self.audio_thread = threading.Thread(target=self.capture_audio)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            logger.info("Аудио потоки запущены")
            
        except Exception as e:
            logger.error(f"Ошибка запуска аудио: {e}")
            
    def capture_audio(self):
        """Захват аудио с микрофона"""
        while not self.stop_audio and self.audio_active:
            try:
                if self.audio_stream_in and self.audio_active:
                    data = self.audio_stream_in.read(1024, exception_on_overflow=False)
                    # Здесь можно отправить данные через сеть
                    # self.send_audio_data(data)
            except Exception as e:
                logger.error(f"Ошибка захвата аудио: {e}")
                break
                
    def start_video(self):
        """Запуск видео"""
        try:
            self.video_capture = cv2.VideoCapture(0)
            if not self.video_capture.isOpened():
                logger.error("Не удалось открыть камеру")
                return
                
            # Запускаем поток для захвата видео
            self.stop_video = False
            self.video_thread = threading.Thread(target=self.capture_video)
            self.video_thread.daemon = True
            self.video_thread.start()
            
            logger.info("Видео захват запущен")
            
        except Exception as e:
            logger.error(f"Ошибка запуска видео: {e}")
            
    def capture_video(self):
        """Захват видео с камеры"""
        while not self.stop_video and self.video_active:
            try:
                if self.video_capture and self.video_active:
                    ret, frame = self.video_capture.read()
                    if ret:
                        # Конвертируем BGR в RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        # Масштабируем
                        frame_resized = cv2.resize(frame_rgb, (240, 180))
                        
                        # Конвертируем в QImage
                        h, w, ch = frame_resized.shape
                        bytes_per_line = ch * w
                        q_img = QImage(frame_resized.data, w, h, bytes_per_line, QImage.Format_RGB888)
                        
                        # Устанавливаем в QLabel
                        self.local_video_label.setPixmap(QPixmap.fromImage(q_img))
                        
                        # Здесь можно отправить кадр через сеть
                        # encoded_frame = cv2.imencode('.jpg', frame_resized)[1].tobytes()
                        # self.send_video_data(encoded_frame)
            except Exception as e:
                logger.error(f"Ошибка захвата видео: {e}")
                break
                
    def update_remote_video(self, frame_data):
        """Обновление удаленного видео"""
        if self.call_type == 'video' and hasattr(self, 'remote_video_label'):
            try:
                # Декодируем кадр
                frame = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_resized = cv2.resize(frame_rgb, (240, 180))
                    
                    h, w, ch = frame_resized.shape
                    bytes_per_line = ch * w
                    q_img = QImage(frame_resized.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    
                    self.remote_video_label.setPixmap(QPixmap.fromImage(q_img))
            except Exception as e:
                logger.error(f"Ошибка обновления удаленного видео: {e}")
                
    def play_audio_data(self, audio_data):
        """Воспроизведение аудио данных"""
        if self.audio_stream_out and self.audio_active:
            try:
                self.audio_stream_out.write(audio_data)
            except Exception as e:
                logger.error(f"Ошибка воспроизведения аудио: {e}")
                
    def toggle_microphone(self):
        """Включить/выключить микрофон"""
        self.audio_active = not self.audio_active
        logger.info(f"Микрофон {'включен' if self.audio_active else 'выключен'}")
        
    def toggle_camera(self):
        """Включить/выключить камеру"""
        if self.call_type == 'video':
            self.video_active = not self.video_active
            if not self.video_active and hasattr(self, 'local_video_label'):
                self.local_video_label.clear()
                self.local_video_label.setText("Камера выключена")
            logger.info(f"Камера {'включена' if self.video_active else 'выключена'}")
            
    def end_call(self):
        """Завершить звонок"""
        self.stop_call()
        self.call_ended.emit(self.call_id)
        self.close()
        
    def reject_call(self):
        """Отклонить звонок"""
        self.stop_call()
        self.call_rejected.emit(self.call_id)
        self.close()
        
    def stop_call(self):
        """Остановка звонка и освобождение ресурсов"""
        try:
            self.stop_audio = True
            self.stop_video = True
            
            if self.audio_stream_in:
                self.audio_stream_in.stop_stream()
                self.audio_stream_in.close()
                
            if self.audio_stream_out:
                self.audio_stream_out.stop_stream()
                self.audio_stream_out.close()
                
            if self.video_capture:
                self.video_capture.release()
                
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=1.0)
                
            if self.video_thread and self.video_thread.is_alive():
                self.video_thread.join(timeout=1.0)
                
            self.audio.terminate()
            
            logger.info("Ресурсы звонка освобождены")
            
        except Exception as e:
            logger.error(f"Ошибка остановки звонка: {e}")
            
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.stop_call()
        event.accept()