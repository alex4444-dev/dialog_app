#!/usr/bin/env python3
"""
Bootstrap сервер для мессенджера Диалог
Центральный узел для первоначального подключения пиров
"""

import asyncio
import logging
import json
import time
from typing import Dict, Set, Tuple
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
        self.connected_peers: Dict[Tuple[str, int], float] = {}  # {(host, port): last_seen}
        self.server = None
        
    async def start(self):
        """Запуск bootstrap сервера"""
        try:
            self.server = await asyncio.start_server(
                self.handle_peer,
                self.host, 
                self.port
            )
            
            logger.info(f"🚀 Bootstrap сервер запущен на {self.host}:{self.port}")
            logger.info("Сервер готов принимать подключения от пиров...")
            
            # Запускаем задачу для очистки неактивных пиров
            asyncio.create_task(self.cleanup_inactive_peers())
            
            async with self.server:
                await self.server.serve_forever()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске сервера: {e}")
            raise

    async def handle_peer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Обработка подключения пира с улучшенным чтением данных"""
        peer_addr = writer.get_extra_info('peername')
        peer_host, peer_port = peer_addr[0], peer_addr[1]
        
        logger.info(f"🔗 Новое подключение от {peer_host}:{peer_port}")
        
        try:
            # Читаем данные до символа новой строки (как ожидают клиенты)
            data = await reader.readuntil(b'\n')
            
            if data:
                message_str = data.decode().strip()
                try:
                    message = json.loads(message_str)
                    await self.process_message(message, peer_host, peer_port, writer)
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ Неверный JSON от {peer_host}:{peer_port}: {message_str}")
                    error_response = {
                        'type': 'error', 
                        'message': 'Invalid JSON format'
                    }
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
        """Обработка сообщений от пиров"""
        msg_type = message.get('type')
        
        if msg_type == 'register' or msg_type == 'user_online':  
            # Регистрация нового пира
            peer_port = message.get('port', port)
            await self.register_peer(host, peer_port, writer)
            
        elif msg_type == 'get_peers':
            # Запрос списка пиров
            await self.send_peer_list(host, port, writer)
            
        elif msg_type == 'heartbeat':
            # Проверка активности
            await self.update_peer_activity(host, port)
            
        else:
            logger.warning(f"⚠️  Неизвестный тип сообщения: {msg_type}")
            # Отправляем ошибку обратно клиенту
            error_response = {
                'type': 'error',
                'message': f'Unknown message type: {msg_type}'
            }
            writer.write(json.dumps(error_response).encode())
            await writer.drain()

    async def register_peer(self, host: str, port: int, writer):
        """Регистрация нового пира"""
        try:
            # Используем порт из сообщения, а не из соединения
            # (клиент может слушать на другом порту)
            peer_key = (host, port)
            self.connected_peers[peer_key] = time.time()
            
            logger.info(f"✅ Зарегистрирован пир {host}:{port}")
            logger.info(f"📊 Всего зарегистрированных пиров: {len(self.connected_peers)}")
            
            # Получаем активных пиров (исключая текущего)
            active_peers = await self.get_active_peers()
            active_peers = [p for p in active_peers if p != (host, port)]
            
            # Отправляем подтверждение и список пиров
            response = {
                'type': 'registration_success',
                'message': 'Успешная регистрация в bootstrap сети',
                'peers': active_peers,
                'your_port': port  # Для отладки
            }
            
            response_data = json.dumps(response).encode()
            writer.write(response_data)
            await writer.drain()

            logger.info(f"📤 Отправлено {len(active_peers)} пиров для {host}:{port}")
            
            # Даем время на отправку перед закрытием
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации пира {host}:{port}: {e}")
            # Отправляем ошибку клиенту
            error_response = {
                'type': 'error',
                'message': f'Registration failed: {str(e)}'
            }
            try:
                writer.write(json.dumps(error_response).encode() + b'\n')
                await writer.drain()
            except:
                pass

    async def send_peer_list(self, host: str, port: int, writer):
        """Отправка списка активных пиров"""
        active_peers = await self.get_active_peers()
        
        response = {
            'type': 'peer_list',
            'peers': active_peers
        }
        
        writer.write(json.dumps(response).encode())
        await writer.drain()
        
        logger.info(f"📋 Отправлен список из {len(active_peers)} пиров для {host}:{port}")

    async def update_peer_activity(self, host: str, port: int):
        """Обновление времени активности пира"""
        peer_key = (host, port)
        self.connected_peers[peer_key] = time.time()

    async def get_active_peers(self) -> list:
        """Получение списка активных пиров (последние 10 минут)"""
        current_time = time.time()
        active_peers = []
        
        for (host, port), last_seen in self.connected_peers.items():
            if current_time - last_seen < 600:  # 10 минут
                active_peers.append((host, port))
                
        return active_peers

    async def cleanup_inactive_peers(self):
        """Очистка неактивных пиров (каждые 5 минут)"""
        while True:
            await asyncio.sleep(300)  # 5 минут
            
            current_time = time.time()
            inactive_peers = []
            
            for peer, last_seen in self.connected_peers.items():
                if current_time - last_seen > 600:  # 10 минут неактивности
                    inactive_peers.append(peer)
            
            for peer in inactive_peers:
                del self.connected_peers[peer]
                logger.info(f"🧹 Удален неактивный пир {peer[0]}:{peer[1]}")
                
            if inactive_peers:
                logger.info(f"📊 Осталось активных пиров: {len(self.connected_peers)}")

    async def stop(self):
        """Остановка сервера"""
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