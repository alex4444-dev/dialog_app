#!/usr/bin/env python3
"""
Простой медиа-сервер для тестирования звонков
"""

import socket
import threading
import json
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('media_server')

class SimpleMediaServer:
    def __init__(self, port=9100):
        self.port = port
        self.clients = {}  # call_id -> socket
        self.is_running = False
        self.server_socket = None
        
    def start(self):
        """Запуск сервера"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(10)
            self.is_running = True
            
            logger.info(f"🔊 Медиа-сервер запущен на порту {self.port}")
            
            # Запускаем поток для приема подключений
            accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            accept_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска сервера: {e}")
            return False
    
    def _accept_connections(self):
        """Прием подключений"""
        while self.is_running:
            try:
                client_socket, addr = self.server_socket.accept()
                client_socket.settimeout(30.0)
                
                logger.info(f"✅ Подключен клиент {addr}")
                
                # Запускаем обработчик для клиента
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.is_running:
                    logger.error(f"Ошибка приема подключения: {e}")
    
    def _handle_client(self, client_socket, addr):
        """Обработка клиента"""
        try:
            # Получаем информацию о звонке
            data = client_socket.recv(1024)
            if data:
                info = json.loads(data.decode())
                call_id = info.get('call_id')
                action = info.get('action')
                
                if call_id:
                    logger.info(f"🔊 Звонок {call_id}: {action} от {addr}")
                    
                    if action == 'register':
                        # Регистрируем клиента
                        self.clients[call_id] = client_socket
                        
                        # Отправляем подтверждение
                        response = {'status': 'registered', 'call_id': call_id}
                        client_socket.send(json.dumps(response).encode())
                        
                        # Простая эхо-логика для тестирования
                        self._echo_audio(client_socket, call_id)
                        
                    elif action == 'connect':
                        # Ищем другого участника звонка
                        other_client = self.clients.get(call_id)
                        if other_client:
                            logger.info(f"🔊 Соединяем участников звонка {call_id}")
                            
                            # Сообщаем обоим клиентам о соединении
                            response = {'status': 'connected', 'call_id': call_id}
                            client_socket.send(json.dumps(response).encode())
                            other_client.send(json.dumps(response).encode())
                            
                            # Запускаем пересылку аудио между клиентами
                            self._forward_audio(client_socket, other_client, call_id)
                        else:
                            logger.warning(f"⚠️ Второй участник звонка {call_id} не найден")
                            response = {'status': 'waiting', 'call_id': call_id}
                            client_socket.send(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки клиента {addr}: {e}")
        finally:
            client_socket.close()
    
    def _echo_audio(self, client_socket, call_id):
        """Эхо-сервер для тестирования аудио"""
        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                # Отправляем эхо
                client_socket.send(data)
                
        except Exception as e:
            logger.debug(f"Клиент {call_id} отключен: {e}")
    
    def _forward_audio(self, client1, client2, call_id):
        """Пересылка аудио между двумя клиентами"""
        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.send(data)
            except:
                pass
        
        # Запускаем потоки для двунаправленной пересылки
        thread1 = threading.Thread(target=forward, args=(client1, client2), daemon=True)
        thread2 = threading.Thread(target=forward, args=(client2, client1), daemon=True)
        
        thread1.start()
        thread2.start()
        
        logger.info(f"🔊 Запущена пересылка аудио для звонка {call_id}")
    
    def stop(self):
        """Остановка сервера"""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info("Медиа-сервер остановлен")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Медиа-сервер для звонков')
    parser.add_argument('--port', type=int, default=9100, help='Порт сервера')
    
    args = parser.parse_args()
    
    server = SimpleMediaServer(args.port)
    
    try:
        if server.start():
            # Бесконечное ожидание
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Остановка сервера...")
        server.stop()