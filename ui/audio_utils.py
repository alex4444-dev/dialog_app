import logging
import threading
import time

logger = logging.getLogger('dialog_audio')

class AudioResourceManager:
    """Менеджер для управления аудио ресурсами"""
    
    def __init__(self):
        self.audio_streams = {}
        self.audio_lock = threading.Lock()
        
    def register_stream(self, stream_id, stream):
        """Регистрация аудио потока"""
        with self.audio_lock:
            self.audio_streams[stream_id] = stream
            logger.info(f"Зарегистрирован аудио поток: {stream_id}")
            
    def unregister_stream(self, stream_id):
        """Удаление аудио потока"""
        with self.audio_lock:
            if stream_id in self.audio_streams:
                try:
                    stream = self.audio_streams[stream_id]
                    if hasattr(stream, 'stop'):
                        stream.stop()
                    if hasattr(stream, 'close'):
                        stream.close()
                    logger.info(f"Аудио поток {stream_id} остановлен и удален")
                except Exception as e:
                    logger.error(f"Ошибка остановки аудио потока {stream_id}: {e}")
                finally:
                    del self.audio_streams[stream_id]
                    
    def cleanup_all(self):
        """Очистка всех аудио ресурсов"""
        with self.audio_lock:
            stream_ids = list(self.audio_streams.keys())
            for stream_id in stream_ids:
                self.unregister_stream(stream_id)
            logger.info("Все аудио ресурсы очищены")

# Глобальный менеджер аудио ресурсов
audio_manager = AudioResourceManager()