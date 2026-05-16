# sound_manager.py
import logging
import os
from PyQt5.QtMultimedia import QSound
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

    def play(self, sound_name: str):
        if not self.enabled:
            return
        sound_file = self.sounds.get(sound_name)
        if not sound_file or not os.path.exists(sound_file):
            logger.debug(f"Звуковой файл не найден: {sound_file}")
            return
        try:
            QSound.play(sound_file)
        except Exception as e:
            logger.error(f"Ошибка воспроизведения звука {sound_name}: {e}")

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.settings.setValue('sounds_enabled', enabled)

    def set_sound_file(self, sound_name: str, file_path: str):
        self.sounds[sound_name] = file_path
        self.settings.setValue(f'sound_{sound_name}', file_path)
        self.settings.sync()