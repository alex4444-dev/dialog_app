import pyaudio
import threading
import numpy as np

class AudioHandler:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
        self.stream_in = None
        self.stream_out = None
        
    def start_audio(self):
        self.is_recording = True
        self.stream_in = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,
            input=True,
            frames_per_buffer=1024
        )
        
        self.stream_out = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,
            output=True,
            frames_per_buffer=1024
        )
        
        self.record_thread = threading.Thread(target=self.record_audio)
        self.record_thread.start()
    
    def record_audio(self):
        while self.is_recording:
            try:
                data = self.stream_in.read(1024)
                # Здесь должна быть отправка аудио данных
                self.stream_out.write(data)
            except Exception as e:
                print(f"Audio error: {e}")
    
    def stop_audio(self):
        self.is_recording = False
        if self.stream_in:
            self.stream_in.stop_stream()
            self.stream_in.close()
        if self.stream_out:
            self.stream_out.stop_stream()
            self.stream_out.close()
