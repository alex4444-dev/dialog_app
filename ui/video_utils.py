#!/usr/bin/env python3
"""
Утилиты для видеозвонков
"""

import cv2
import numpy as np
import logging
import threading
import time
from queue import Queue

logger = logging.getLogger('dialog_video_utils')

class VideoCompressor:
    """Компрессор видео"""
    
    def __init__(self, quality=85):
        self.quality = quality
        
    def compress_frame(self, frame, target_size=(640, 480)):
        """Сжатие кадра"""
        try:
            # Изменение размера
            resized = cv2.resize(frame, target_size)
            
            # Кодирование в JPEG с указанным качеством
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
            success, encoded = cv2.imencode('.jpg', resized, encode_param)
            
            if success:
                return encoded.tobytes()
            return None
            
        except Exception as e:
            logger.error(f"Ошибка сжатия кадра: {e}")
            return None
    
    def decompress_frame(self, data, original_size=(640, 480)):
        """Декомпрессия кадра"""
        try:
            # Декодирование JPEG
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame
            return None
            
        except Exception as e:
            logger.error(f"Ошибка декомпрессии кадра: {e}")
            return None

class VideoBuffer:
    """Буфер для видео кадров"""
    
    def __init__(self, max_size=30):
        self.buffer = Queue(maxsize=max_size)
        self.lock = threading.Lock()
        
    def put_frame(self, frame):
        """Добавить кадр в буфер"""
        try:
            if not self.buffer.full():
                self.buffer.put(frame, block=False)
            else:
                # Если буфер полон, удаляем старый кадр
                self.buffer.get(block=False)
                self.buffer.put(frame, block=False)
        except:
            pass
    
    def get_frame(self):
        """Получить кадр из буфера"""
        try:
            if not self.buffer.empty():
                return self.buffer.get(block=False)
        except:
            pass
        return None
    
    def clear(self):
        """Очистить буфер"""
        while not self.buffer.empty():
            try:
                self.buffer.get(block=False)
            except:
                break
    
    def size(self):
        """Текущий размер буфера"""
        return self.buffer.qsize()

class VideoAnalyzer:
    """Анализатор видео качества"""
    
    @staticmethod
    def calculate_frame_quality(frame):
        """Вычисление качества кадра"""
        try:
            if frame is None:
                return 0
            
            # Преобразуем в оттенки серого
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            
            # Вычисляем вариацию Лапласиана (мера размытости)
            fm = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Нормализуем (0-100)
            quality = min(100, max(0, int(fm / 10)))
            return quality
            
        except Exception as e:
            logger.error(f"Ошибка вычисления качества кадра: {e}")
            return 0
    
    @staticmethod
    def detect_faces(frame):
        """Обнаружение лиц в кадре"""
        try:
            # Загружаем классификатор для обнаружения лиц
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            
            # Преобразуем в оттенки серого
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            
            # Обнаруживаем лица
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            # Рисуем прямоугольники вокруг лиц
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
            return len(faces), frame
            
        except Exception as e:
            logger.error(f"Ошибка обнаружения лиц: {e}")
            return 0, frame