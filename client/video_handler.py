import cv2
import threading
import numpy as np

class VideoHandler:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.is_streaming = False
        
    def start_video(self):
        self.is_streaming = True
        self.video_thread = threading.Thread(target=self.capture_video)
        self.video_thread.start()
    
    def capture_video(self):
        while self.is_streaming:
            ret, frame = self.cap.read()
            if ret:
                # Здесь должна быть обработка и отправка видео
                frame = cv2.resize(frame, (640, 480))
                # Отправка frame в GUI или по сети
                
    def stop_video(self):
        self.is_streaming = False
        if self.cap.isOpened():
            self.cap.release()
