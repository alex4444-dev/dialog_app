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

    def _play_wav(self, file_path: str):
        """Воспроизвести WAV файл через sounddevice"""
        try:
            with wave.open(file_path, 'rb') as wf:
                data = wf.readframes(wf.getnframes())
                samples = np.frombuffer(data, dtype=np.int16)
                if wf.getnchannels() == 2:
                    samples = samples.reshape(-1, 2)
                sd.play(samples, samplerate=wf.getframerate())
                sd.wait()
        except Exception as e:
            logger.error(f"Ошибка воспроизведения {file_path}: {e}")

    def play(self, sound_name: str):
        if not self.enabled:
            return
        sound_file = self.sounds.get(sound_name)
        if not sound_file or not os.path.exists(sound_file):
            logger.debug(f"Звуковой файл не найден: {sound_file}")
            return
        threading.Thread(target=self._play_wav, args=(sound_file,), daemon=True).start()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.settings.setValue('sounds_enabled', enabled)

    def set_sound_file(self, sound_name: str, file_path: str):
        self.sounds[sound_name] = file_path
        self.settings.setValue(f'sound_{sound_name}', file_path)
        self.settings.sync()