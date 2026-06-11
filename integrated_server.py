# integrated_server.py
import asyncio
import threading
import time
import logging
from bootstrap_node import BootstrapServer
from simple_media_server import SimpleMediaServer

logger = logging.getLogger('dialog_integrated')

class IntegratedServers:
    def __init__(self, bootstrap_host='0.0.0.0', bootstrap_port=8888, media_port=9100):
        self.bootstrap_host = bootstrap_host
        self.bootstrap_port = bootstrap_port
        self.media_port = media_port
        self.bootstrap_server = None
        self.media_server = None
        self.bootstrap_thread = None
        self.media_thread = None
        self._running = False

    def start(self):
        """Запускает оба сервера в фоновых потоках."""
        if self._running:
            logger.warning("Серверы уже запущены")
            return

        self._running = True

        # Запуск Bootstrap сервера (асинхронный)
        self.bootstrap_thread = threading.Thread(target=self._run_bootstrap, daemon=True)
        self.bootstrap_thread.start()

        # Запуск Media сервера (синхронный)
        self.media_thread = threading.Thread(target=self._run_media, daemon=True)
        self.media_thread.start()

        # Даём серверам время для инициализации
        time.sleep(1)
        logger.info("✅ Встроенные серверы запущены")

    def _run_bootstrap(self):
        """Запуск BootstrapServer в отдельном event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.bootstrap_server = BootstrapServer(host=self.bootstrap_host, port=self.bootstrap_port)
        try:
            loop.run_until_complete(self.bootstrap_server.start())
        except Exception as e:
            logger.error(f"Bootstrap сервер остановлен с ошибкой: {e}")

    def _run_media(self):
        """Запуск SimpleMediaServer (блокирующий)."""
        self.media_server = SimpleMediaServer(port=self.media_port)
        if self.media_server.start():
            # Бесконечное ожидание
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            finally:
                self.media_server.stop()
        else:
            logger.error("Не удалось запустить медиа-сервер")

    def stop(self):
        """Остановка серверов."""
        self._running = False
        if self.bootstrap_server:
            # Для асинхронного сервера – закрываем через цикл
            if self.bootstrap_thread and self.bootstrap_thread.is_alive():
                # Можно отправить сигнал, но проще положиться на daemon
                pass
        if self.media_server:
            self.media_server.stop()
        logger.info("Встроенные серверы остановлены")
