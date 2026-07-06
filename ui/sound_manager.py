import logging
import os
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl, QObject, QSettings, pyqtSignal

logger = logging.getLogger('dialog_gui')

class SoundManager(QObject):
    sound_finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.enabled = self.settings.value('sounds_enabled', True, type=bool)

        self.base_sound_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'sounds'
        )
        logger.info(f"SoundManager: базовая папка для звуков: {self.base_sound_dir}")

        self.sounds = {
            'incoming_call': self.settings.value('sound_incoming_call', 'incoming_call.wav', type=str),
            'outgoing_call': self.settings.value('sound_outgoing_call', 'outgoing_call.wav', type=str),
            'message': self.settings.value('sound_message', 'message.wav', type=str),
            'file_received': self.settings.value('sound_file_received', 'file_received.wav', type=str)
        }

        self.player = QMediaPlayer()
        self.loop_player = QMediaPlayer()
        self.loop_player.mediaStatusChanged.connect(self._on_loop_status_changed)
        self._loop_sound_name = None

    def _resolve_path(self, sound_name):
        filename = self.sounds.get(sound_name)
        if not filename:
            logger.warning(f"Нет имени файла для звука {sound_name}")
            return None

        if os.path.isabs(filename) and os.path.exists(filename):
            return filename

        local_path = os.path.join(self.base_sound_dir, filename)
        if os.path.exists(local_path):
            return local_path

        cwd_path = os.path.join(os.getcwd(), 'sounds', filename)
        if os.path.exists(cwd_path):
            return cwd_path

        logger.warning(f"Файл звука не найден: {filename} (искали в {local_path} и {cwd_path})")
        return None

    def _get_sound_url(self, sound_name):
        path = self._resolve_path(sound_name)
        if not path:
            return None
        return QUrl.fromLocalFile(path)

    def play(self, sound_name):
        if not self.enabled:
            return
        url = self._get_sound_url(sound_name)
        if url:
            self.player.setMedia(QMediaContent(url))
            self.player.play()

    def play_looped(self, sound_name):
        if not self.enabled:
            return
        self.stop_looped()
        url = self._get_sound_url(sound_name)
        if url:
            self.loop_player.setMedia(QMediaContent(url))
            self._loop_sound_name = sound_name
            self.loop_player.play()

    def stop_looped(self):
        if self.loop_player.state() == QMediaPlayer.PlayingState:
            self.loop_player.stop()
        self._loop_sound_name = None

    def _on_loop_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia and self._loop_sound_name is not None:
            self.loop_player.play()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.settings.setValue('sounds_enabled', enabled)
        if not enabled:
            self.stop_looped()

    def set_sound_file(self, sound_name, file_path):
        filename = os.path.basename(file_path)
        self.sounds[sound_name] = filename
        self.settings.setValue(f'sound_{sound_name}', filename)
        self.settings.sync()