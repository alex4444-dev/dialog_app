#!/usr/bin/env python3
"""
Bootstrap сервер для мессенджера Диалог
Центральный узел для первоначального подключения пиров и ретрансляции сигналов WebRTC
"""

import asyncio
import logging
import json
import time
from typing import Dict, Set, Tuple, Optional, List
import argparse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bootstrap_node')


class BootstrapServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        self.host = host
        self.port = port
        self.connected_peers: Dict[Tuple[str, int], float] = {}
        self.username_to_addr: Dict[str, Tuple[str, int]] = {}
        self.pending_signals: Dict[str, List[dict]] = {}
        self.signal_ttl = 300
        self.server = None
        self._signal_lock_obj = asyncio.Lock()  # создаём сразу

    async def start(self):
        try:
            self.server = await asyncio.start_server(
                self.handle_peer,
                self.host,
                self.port
            )
            logger.info(f"🚀 Bootstrap сервер запущен на {self.host}:{self.port}")
            logger.info("Сервер готов принимать подключения от пиров...")

            asyncio.create_task(self.cleanup_inactive_peers())
            asyncio.create_task(self.cleanup_old_signals())

            async with self.server:
                await self.server.serve_forever()

        except Exception as e:
            logger.error(f"❌ Ошибка при запуске сервера: {e}")
            raise

    async def handle_peer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer_addr = writer.get_extra_info('peername')
        peer_host, peer_port = peer_addr[0], peer_addr[1]
        logger.info(f"🔗 Новое подключение от {peer_host}:{peer_port}")

        try:
            data = await reader.readuntil(b'\n')
            if data:
                message_str = data.decode().strip()
                try:
                    message = json.loads(message_str)
                    await self.process_message(message, peer_host, peer_port, writer)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Неверный JSON от {peer_host}:{peer_port}: {message_str}")
                    error_response = {'type': 'error', 'message': 'Invalid JSON format'}
                    writer.write(json.dumps(error_response).encode() + b'\n')
                    await writer.drain()

        except asyncio.IncompleteReadError:
            logger.warning(f"⚠️ Неполные данные от {peer_host}:{peer_port}")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения от {peer_host}:{peer_port}: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
                logger.debug(f"🔌 Закрыто соединение с {peer_host}:{peer_port}")
            except:
                pass

    async def process_message(self, message: dict, host: str, port: int, writer):
        msg_type = message.get('type')

        if msg_type in ('register', 'user_online'):
            peer_port = message.get('port', port)
            username = message.get('username')
            await self.register_peer(host, peer_port, username, writer)

        elif msg_type == 'get_peers':
            await self.send_peer_list(host, port, writer)

        elif msg_type == 'heartbeat':
            await self.update_peer_activity(host, port)

        elif msg_type == 'signal':
            await self.handle_signal(message, host, port, writer)

        elif msg_type == 'get_signals':
            await self.send_pending_signals(message, host, port, writer)

        else:
            logger.warning(f"⚠️ Неизвестный тип сообщения: {msg_type}")
            error_response = {'type': 'error', 'message': f'Unknown message type: {msg_type}'}
            writer.write(json.dumps(error_response).encode() + b'\n')
            await writer.drain()

    # ========== РЕГИСТРАЦИЯ И УПРАВЛЕНИЕ ПИРАМИ ==========

    async def register_peer(self, host: str, port: int, username: Optional[str], writer):
        peer_key = (host, port)
        self.connected_peers[peer_key] = time.time()

        if username:
            old_addr = self.username_to_addr.get(username)
            if old_addr and old_addr != peer_key:
                if old_addr in self.connected_peers:
                    del self.connected_peers[old_addr]
                logger.info(f"👤 Пользователь {username} перерегистрирован с {old_addr} на {peer_key}")
            self.username_to_addr[username] = peer_key
            logger.info(f"✅ Зарегистрирован пир {host}:{port} (username: {username})")
        else:
            logger.info(f"✅ Зарегистрирован пир {host}:{port} (без имени)")

        logger.info(f"📊 Всего зарегистрированных пиров: {len(self.connected_peers)}")

        active_peers_info = await self.get_active_peers_info()
        # Исключаем самого себя
        active_peers_info = [p for p in active_peers_info if not (p['host'] == host and p['port'] == port)]

        response = {
            'type': 'registration_success',
            'message': 'Успешная регистрация в bootstrap сети',
            'peers': active_peers_info,
            'your_port': port
        }
        writer.write(json.dumps(response).encode() + b'\n')
        await writer.drain()
        logger.info(f"📤 Отправлено {len(active_peers_info)} пиров для {host}:{port}")
        await asyncio.sleep(0.1)

    async def send_peer_list(self, host: str, port: int, writer):
        active_peers_info = await self.get_active_peers_info()
        response = {'type': 'peer_list', 'peers': active_peers_info}
        writer.write(json.dumps(response).encode() + b'\n')
        await writer.drain()
        logger.info(f"📋 Отправлен список из {len(active_peers_info)} пиров для {host}:{port}")

    async def update_peer_activity(self, host: str, port: int):
        peer_key = (host, port)
        if peer_key in self.connected_peers:
            self.connected_peers[peer_key] = time.time()

    async def get_active_peers(self) -> list:
        current_time = time.time()
        active_peers = []
        for (host, port), last_seen in self.connected_peers.items():
            if current_time - last_seen < 600:
                active_peers.append((host, port))
        return active_peers

    async def get_active_peers_info(self) -> List[dict]:
        current_time = time.time()
        result = []
        for (host, port), last_seen in self.connected_peers.items():
            if current_time - last_seen < 600:
                username = None
                for uname, addr in self.username_to_addr.items():
                    if addr == (host, port):
                        username = uname
                        break
                result.append({'host': host, 'port': port, 'username': username})
        return result

    async def cleanup_inactive_peers(self):
        while True:
            await asyncio.sleep(300)
            current_time = time.time()
            to_remove = []
            for peer, last_seen in self.connected_peers.items():
                if current_time - last_seen > 600:
                    to_remove.append(peer)
            for peer in to_remove:
                del self.connected_peers[peer]
                for username, addr in list(self.username_to_addr.items()):
                    if addr == peer:
                        del self.username_to_addr[username]
                        break
                logger.info(f"🧹 Удален неактивный пир {peer[0]}:{peer[1]}")
            if to_remove:
                logger.info(f"📊 Осталось активных пиров: {len(self.connected_peers)}")

    # ========== НОВЫЕ МЕТОДЫ ДЛЯ СИГНАЛИЗАЦИИ ==========

    async def handle_signal(self, message: dict, host: str, port: int, writer):
        target_username = message.get('to')
        signal_data = message.get('data')

        if not target_username or signal_data is None:
            error_response = {'type': 'error', 'message': 'Missing "to" or "data" field'}
            writer.write(json.dumps(error_response).encode() + b'\n')
            await writer.drain()
            return

        from_username = message.get('from')
        if not from_username:
            from_username = self._get_username_by_addr(host, port)
            if not from_username:
                from_username = f"anonymous_{host}_{port}"

        async with self._signal_lock_obj:
            if target_username not in self.pending_signals:
                self.pending_signals[target_username] = []
            self.pending_signals[target_username].append({
                'from': from_username,
                'data': signal_data,
                'timestamp': time.time()
            })

        logger.info(f"📨 Сигнал от {from_username} для {target_username} сохранён")

        ack = {'type': 'signal_ack', 'status': 'stored'}
        writer.write(json.dumps(ack).encode() + b'\n')
        await writer.drain()

    async def send_pending_signals(self, message: dict, host: str, port: int, writer):
        username = message.get('username')
        if not username:
            username = self._get_username_by_addr(host, port)
            if not username:
                error_response = {'type': 'error', 'message': 'Cannot determine username'}
                writer.write(json.dumps(error_response).encode() + b'\n')
                await writer.drain()
                return

        async with self._signal_lock_obj:
            signals = self.pending_signals.pop(username, [])

        response = {
            'type': 'signal_list',
            'signals': signals
        }
        writer.write(json.dumps(response).encode() + b'\n')
        await writer.drain()
        logger.info(f"📤 Отправлено {len(signals)} сигналов для {username}")

    def _get_username_by_addr(self, host: str, port: int) -> Optional[str]:
        for username, addr in self.username_to_addr.items():
            if addr == (host, port):
                return username
        return None

    async def cleanup_old_signals(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            async with self._signal_lock_obj:
                for username, signals in list(self.pending_signals.items()):
                    new_signals = [s for s in signals if now - s['timestamp'] < self.signal_ttl]
                    if new_signals:
                        self.pending_signals[username] = new_signals
                    else:
                        del self.pending_signals[username]
                        logger.debug(f"🧹 Очищены сигналы для {username} (устарели)")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("🛑 Bootstrap сервер остановлен")


async def main():
    parser = argparse.ArgumentParser(description='Bootstrap сервер для мессенджера Диалог')
    parser.add_argument('--host', default='0.0.0.0', help='Хост для прослушивания')
    parser.add_argument('--port', type=int, default=8888, help='Порт для прослушивания')
    parser.add_argument('--debug', action='store_true', help='Включить debug режим')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("🔍 Debug режим включен")

    bootstrap = BootstrapServer(args.host, args.port)

    try:
        await bootstrap.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания...")
    finally:
        await bootstrap.stop()


if __name__ == "__main__":
    asyncio.run(main())