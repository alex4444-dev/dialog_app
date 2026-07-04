import logging
import os
import threading
import wave
import numpy as np
import sounddevice as sd
from PyQt5.QtCore import QSettings

logger = logging.getLogger('dialog_gui')

class SoundManager:
    def __init__(self):
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.enabled = self.settings.value('sounds_enabled', True, type=bool)
        self.sounds = {
            'incoming_call': self.settings.value('sound_incoming_call', 'sounds/incoming_call.wav', type=str),
            'outgoing_call': self.settings.value('sound_outgoing_call', 'sounds/outgoing_call.wav', type=str),
            'message': self.settings.value('sound_message', 'sounds/message.wav', type=str),
            'file_received': self.settings.value('sound_file_received', 'sounds/file_received.wav', type=str)
        }
        # Для зацикленного воспроизведения
        self.loop_event = None
        self.loop_thread = None
        self._loop_lock = threading.Lock()

    def _play_wav(self, file_path: str):
        """Воспроизвести WAV файл через sounddevice (блокирующий вызов)"""
        try:
            with wave.open(file_path, 'rb') as wf:
                data = wf.readframes(wf.getnframes())
                samples = np.frombuffer(data, dtype=np.int16)
                if wf.getnchannels() == 2:
                    samples = samples.reshape(-1, 2)
                sd.play(samples, samplerate=wf.getframerate())
                sd.wait()  # ждём окончания воспроизведения
        except Exception as e:
            logger.error(f"Ошибка воспроизведения {file_path}: {e}")

    def play(self, sound_name: str):
        """Однократное воспроизведение звука"""
        if not self.enabled:
            return
        sound_file = self.sounds.get(sound_name)
        if not sound_file or not os.path.exists(sound_file):
            logger.debug(f"Звуковой файл не найден: {sound_file}")
            return
        threading.Thread(target=self._play_wav, args=(sound_file,), daemon=True).start()

    def play_looped(self, sound_name: str):
        """Запуск зацикленного воспроизведения звука (для входящего звонка)"""
        with self._loop_lock:
            # Если уже играет какой-то цикл, останавливаем его
            self.stop_looped()

            if not self.enabled:
                return
            sound_file = self.sounds.get(sound_name)
            if not sound_file or not os.path.exists(sound_file):
                logger.debug(f"Звуковой файл не найден: {sound_file}")
                return

            # Создаём событие для остановки цикла
            self.loop_event = threading.Event()
            self.loop_thread = threading.Thread(
                target=self._loop_play,
                args=(sound_file, self.loop_event),
                daemon=True
            )
            self.loop_thread.start()
            logger.info(f"Запущен зацикленный звук: {sound_name}")

    def _loop_play(self, sound_file: str, stop_event: threading.Event):
        """Цикл воспроизведения звука до установки stop_event"""
        while not stop_event.is_set():
            # Воспроизводим один раз
            self._play_wav(sound_file)
            # После завершения _play_wav проверяем, не было ли запроса остановки
            if stop_event.is_set():
                break
        logger.info("Зацикленный звук остановлен")

    def stop_looped(self):
        """Остановка зацикленного воспроизведения"""
        with self._loop_lock:
            if self.loop_event is not None:
                self.loop_event.set()
                if self.loop_thread and self.loop_thread.is_alive():
                    self.loop_thread.join(timeout=0.5)
                self.loop_event = None
                self.loop_thread = None
                # Принудительно останавливаем звук (если ещё играет)
                try:
                    sd.stop()
                except:
                    pass
                logger.info("Зацикленный звук остановлен по запросу")

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.settings.setValue('sounds_enabled', enabled)
        if not enabled:
            self.stop_looped()

    def set_sound_file(self, sound_name: str, file_path: str):
        self.sounds[sound_name] = file_path
        self.settings.setValue(f'sound_{sound_name}', file_path)
        self.settings.sync()