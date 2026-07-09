import logging
import os
import sys
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtCore import QUrl, QObject, QSettings, pyqtSignal, QTimer

logger = logging.getLogger('dialog_gui')

class SoundManager(QObject):
    sound_finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.enabled = self.settings.value('sounds_enabled', True, type=bool)

        # Определяем базовую папку для ресурсов
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_sound_dir = os.path.join(base_path, 'sounds')
        logger.info(f"SoundManager: базовая папка для звуков: {self.base_sound_dir}")

        self.sounds = {
            'incoming_call': self.settings.value('sound_incoming_call', 'incoming_call.wav', type=str),
            'outgoing_call': self.settings.value('sound_outgoing_call', 'outgoing_call.wav', type=str),
            'message': self.settings.value('sound_message', 'message.wav', type=str),
            'file_received': self.settings.value('sound_file_received', 'file_received.wav', type=str)
        }

        # Используем QSoundEffect вместо QMediaPlayer
        self.player = QSoundEffect()
        self.player.setVolume(1.0)
        self.loop_player = QSoundEffect()
        self.loop_player.setVolume(1.0)
        # Для зацикливания используем таймер (QSoundEffect может не поддерживать Infinite)
        self._loop_timer = None
        self._loop_sound_name = None

    def _resolve_path(self, sound_name):
        filename = self.sounds.get(sound_name)
        if not filename:
            logger.warning(f"Нет имени файла для звука {sound_name}")
            return None

        # 1. Сначала ищем рядом с исполняемым файлом
        exe_dir = os.path.dirname(sys.executable)
        exe_path = os.path.join(exe_dir, 'sounds', filename)
        if os.path.exists(exe_path):
            logger.info(f"Звук найден: {exe_path}")
            return exe_path

        # 2. Если не нашли – ищем во временной папке (для встроенных звуков)
        if getattr(sys, 'frozen', False):
            meipass_path = os.path.join(sys._MEIPASS, 'sounds', filename)
            if os.path.exists(meipass_path):
                logger.info(f"Звук найден (MEIPASS): {meipass_path}")
                return meipass_path

        # 3. Ищем в рабочей директории (запасной вариант)
        cwd_path = os.path.join(os.getcwd(), 'sounds', filename)
        if os.path.exists(cwd_path):
            logger.info(f"Звук найден (CWD): {cwd_path}")
            return cwd_path

        logger.warning(f"Файл звука не найден: {filename}")
        return None

    def _get_sound_url(self, sound_name):
        path = self._resolve_path(sound_name)
        if not path:
            return None
        url = QUrl.fromLocalFile(path)
        if not url.isValid():
            logger.error(f"Некорректный URL для {path}: {url.errorString()}")
            return None
        return url

    def play(self, sound_name):
        if not self.enabled:
            logger.debug("Звуки отключены")
            return
        url = self._get_sound_url(sound_name)
        if url:
            if self.player.isPlaying():
                self.player.stop()
            self.player.setSource(url)
            self.player.play()
            logger.info(f"Воспроизведение звука: {sound_name}")

    def play_looped(self, sound_name):
        if not self.enabled:
            logger.debug("Звуки отключены")
            return
        self.stop_looped()
        url = self._get_sound_url(sound_name)
        if url:
            self.loop_player.setSource(url)
            self._loop_sound_name = sound_name
            self.loop_player.play()
            # Запускаем таймер для перезапуска, если звук закончился
            if self._loop_timer is None:
                self._loop_timer = QTimer()
                self._loop_timer.timeout.connect(self._loop_play)
            # Проверяем каждые 300 мс, не закончился ли звук
            self._loop_timer.start(300)
            logger.info(f"Запущен зацикленный звук: {sound_name}")

    def _loop_play(self):
        # Если зацикленный звук не играет и есть имя – перезапускаем
        if not self.loop_player.isPlaying() and self._loop_sound_name is not None:
            url = self._get_sound_url(self._loop_sound_name)
            if url:
                self.loop_player.setSource(url)
                self.loop_player.play()
                logger.debug(f"Перезапуск зацикленного звука: {self._loop_sound_name}")
        # Если звук всё ещё играет – ничего не делаем

    def stop_looped(self):
        if self.loop_player.isPlaying():
            self.loop_player.stop()
        if self._loop_timer is not None and self._loop_timer.isActive():
            self._loop_timer.stop()
        self._loop_sound_name = None
        logger.info("Зацикленный звук остановлен")

    def stop(self):
        self.stop_looped()
        if self.player.isPlaying():
            self.player.stop()
        logger.info("Все звуки остановлены")

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