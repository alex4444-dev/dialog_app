import asyncio
import threading
import logging
from kademlia.network import Server

logger = logging.getLogger('dialog_p2p')

class DHTNode:
    def __init__(self, port: int, bootstrap_nodes: list = None):
        self.port = port
        self.bootstrap_nodes = []
        if bootstrap_nodes:
            for node in bootstrap_nodes:
                if isinstance(node, dict):
                    host = node.get('host')
                    p = node.get('port')
                    if host and isinstance(p, int):
                        self.bootstrap_nodes.append((host, p))
                elif isinstance(node, (tuple, list)) and len(node) == 2:
                    host, p = node
                    if isinstance(p, int):
                        self.bootstrap_nodes.append((host, p))
                elif isinstance(node, str):
                    parts = node.split(':')
                    if len(parts) == 2:
                        host, p_str = parts
                        try:
                            p = int(p_str)
                            self.bootstrap_nodes.append((host, p))
                        except ValueError:
                            logger.warning(f"Неверный порт в строке: {node}")
                else:
                    logger.warning(f"Неизвестный формат узла: {node}")
        self.server = Server()
        self.loop = None
        self.thread = None
        self.is_running = False
        self._ready = threading.Event()
        self._stop_event = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._ready.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=5.0)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        self._stop_event = asyncio.Event()
        self.loop.run_until_complete(self._start_server())
        # После завершения _start_server очищаем ресурсы
        self.loop.close()

    async def _start_server(self):
        await self.server.listen(self.port)
        logger.info(f"DHT узел запущен на порту {self.port}")
        if self.bootstrap_nodes:
            await self.server.bootstrap(self.bootstrap_nodes)
            logger.info(f"Загружено bootstrap узлов: {self.bootstrap_nodes}")
        self._ready.set()
        await self._stop_event.wait()
        # stop() – синхронный метод, не используем await
        self.server.stop()
        logger.info("DHT узел завершает работу")

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.loop and self.loop.is_running() and self._stop_event is not None:
            # Устанавливаем событие, чтобы _start_server завершился
            self.loop.call_soon_threadsafe(self._stop_event.set)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("DHT узел остановлен")