import asyncio
import socket
import threading
import time
import uuid
import logging
import logging.handlers
import socket
import random
import json
from typing import Dict, List, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal


import logging
import logging.handlers

# Настройка улучшенного логирования
def setup_advanced_logging():
    logger = logging.getLogger('dialog_p2p')
    logger.setLevel(logging.DEBUG)
    
    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # File handler с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        'p2p_network.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Инициализация логирования
logger = setup_advanced_logging()


def find_free_port(start_port=8888, max_attempts=50):
        """Находит свободный порт в диапазоне"""
        for attempt in range(max_attempts):
            port = start_port + attempt
            try:
                # Пробуем создать временный сокет для проверки порта
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('0.0.0.0', port))
                    return port
            except OSError:
                continue
                return None  # Не нашли свободный порт


class P2PNetworkClient(QObject):
    """P2P сетевой клиент для мессенджера Диалог с полным обменом пирами"""
    
    # Сигналы для GUI
    message_received = pyqtSignal(str, str)  # from_user, message
    user_list_updated = pyqtSignal(list)
    connection_status_changed = pyqtSignal(str)
    call_received = pyqtSignal(str, str, str, str)  # action, username, call_type, call_id
    
    def __init__(self, db, port=8890):
        super().__init__()
        self.db = db
        self.username = None
        self.is_running = False
        self.connected_peers = {}  # peer_id -> peer_info
        self.known_peers = []      # Список известных пиров для подключения
        self.listen_port = port
        self.listener_socket = None
        self.peer_exchange_interval = 30  # секунды между обменами
        self.last_peer_exchange = 0
        
        # Bootstrap узлы для первоначального подключения
        self.bootstrap_nodes = [
            {"host": "localhost", "port": 8888},
            # Можно добавить публичные bootstrap узлы
        ] 

        # Система отслеживания сообщений
        self.pending_messages = {}  # message_id -> {data, timestamp, attempts, target_peer}
        self.delivered_messages = set()  # message_id подтвержденных сообщений
        self.message_retry_lock = threading.Lock()  

        # Запускаем поток для повторной отправки
        self.retry_thread = threading.Thread(target=self._retry_messages_loop, daemon=True)
        self.retry_thread.start()  

    def _retry_messages_loop(self):
        """Цикл повторной отправки неподтвержденных сообщений"""
        while self.is_running:
            try:
                current_time = time.time()
                messages_to_retry = []
                
                with self.message_retry_lock:
                    for msg_id, msg_data in list(self.pending_messages.items()):
                        # Проверяем условия для повторной отправки
                        if (current_time - msg_data['last_sent'] > 5 and 
                            msg_data['attempts'] < 3 and
                            msg_id not in self.delivered_messages):
                            messages_to_retry.append((msg_id, msg_data))
                
                for msg_id, msg_data in messages_to_retry:
                    logger.info(f"🔄 Повторная отправка сообщения {msg_id}")
                    self._send_message_direct(
                        msg_data['target_peer'], 
                        msg_data['message_data'],
                        msg_id
                    )
                
                time.sleep(2)  # Проверяем каждые 2 секунды
                
            except Exception as e:
                logger.error(f"Ошибка в цикле повторной отправки: {e}")
                time.sleep(5)
    
    def start(self) -> bool:
        """Упрощенный запуск P2P клиента"""
        try:
            self.is_running = True
        
            # Простая логика поиска порта
            for port in range(9000, 9100):
                try:
                    self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.listener_socket.bind(('0.0.0.0', port))
                    self.listener_socket.listen(5)
                    self.listener_socket.settimeout(1.0)
                    self.listen_port = port
                    logger.info(f"✅ Успешно привязан к порту {port}")
                    break
                except OSError as e:
                    if e.errno == 98:  # Address already in use
                        logger.debug(f"Порт {port} занят, пробуем следующий...")
                        continue
                    else:
                        raise
            else:
                logger.error("❌ Не удалось найти свободный порт в диапазоне 9000-9100")
                return False
        
            # Загружаем известные пиры
            self._load_known_peers()
        
            # Подключаемся к bootstrap узлам
            self._connect_to_bootstrap_nodes()

            # ЗАПУСКАЕМ ПОТОК ДЛЯ ПРИНЯТИЯ ВХОДЯЩИХ СОЕДИНЕНИЙ
            self.accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.accept_thread.start()
        
            # Запускаем обслуживание сети
            self.maintenance_thread = threading.Thread(target=self._network_maintenance, daemon=True)
            self.maintenance_thread.start()
        
            logger.info(f"🚀 P2P клиент запущен на порту {self.listen_port}")
            self.connection_status_changed.emit("✅ P2P сеть запущена")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка запуска P2P клиента: {e}")
            self.connection_status_changed.emit("❌ Ошибка запуска P2P сети")
            return False

    def stop(self):
        """Остановка P2P клиента"""
        self.is_running = False
        if self.listener_socket:
            self.listener_socket.close()
        
        for peer_id, peer_info in self.connected_peers.items():
            peer_info['socket'].close()
        self.connected_peers.clear()
        
        # Сохраняем известные пиры в БД
        self._save_known_peers()
        
        logger.info("P2P клиент остановлен")
    
    def register_with_bootstrap_sync(self, bootstrap_host: str, bootstrap_port: int):
        """Синхронная регистрация в bootstrap сервере"""
        try:
            import socket
            import json
        
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((bootstrap_host, bootstrap_port))
        
            registration_message = {
                'type': 'register',
                'port': self.listen_port
            }
        
            sock.send(json.dumps(registration_message).encode())
        
            # Читаем ответ
            data = sock.recv(1024)
            if data:
                response = json.loads(data.decode())
                if response.get('type') == 'registration_success':
                    logger.info(f"✅ Успешная регистрация в bootstrap сервере")
                    # Добавляем полученных пиров в known_peers
                    for peer_host, peer_port in response.get('peers', []):
                        if (peer_host, peer_port) != (bootstrap_host, bootstrap_port):
                            if not any(p.get('host') == peer_host and p.get('port') == peer_port for p in self.known_peers):
                                self.known_peers.append({
                                    'host': peer_host, 
                                    'port': peer_port,
                                    'discovered_at': time.time(),
                                    'source': 'bootstrap'
                                })
                                logger.info(f"📥 Добавлен пир {peer_host}:{peer_port}")
        
            sock.close()
        
        except Exception as e:
            logger.warning(f"❌ Не удалось зарегистрироваться в bootstrap сервере: {e}")

    def set_username(self, username: str):
        """Установка имени пользователя для P2P сети"""
        self.username = username
        logger.info(f"P2P сеть: установлено имя пользователя '{username}'")
    
        # Отправляем информацию о себе всем подключенным пирам
        for peer_id in list(self.connected_peers.keys()):
            self._send_self_info(peer_id)

    def _send_self_info(self, peer_id: str):
        """Отправка информации о себе пиру"""
        try:
            if peer_id not in self.connected_peers:
                return
        
                self_info = {
                    'type': 'user_online',
                    'username': self.username,  # Теперь здесь будет реальное имя
                    'timestamp': time.time(),
                    'client_version': '1.0.0'
                }
        
                self._send_to_peer(self.connected_peers[peer_id], self_info)
                logger.debug(f"Отправлена информация о себе пиру {peer_id}: {self.username}")
        
        except Exception as e:
            logger.error(f"Ошибка отправки информации о себе: {e}")

    def _handle_user_online(self, data: dict, peer_id: str):
        """Обработка уведомления о входе пользователя"""
        username = data.get('username')
        if username and peer_id in self.connected_peers:
            self.connected_peers[peer_id]['username'] = username
            self.connected_peers[peer_id]['last_seen'] = time.time()
        
            logger.info(f"Пользователь {username} в сети (пир {peer_id})")
        
            # Обновляем список пользователей в GUI
            online_users = self.get_online_users()
            self.user_list_updated.emit(online_users)

    def get_peers_from_bootstrap_sync(self, bootstrap_host: str, bootstrap_port: int):
        """Синхронное получение списка пиров от bootstrap сервера"""
        try:
            import socket
            import json
        
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((bootstrap_host, bootstrap_port))
        
            request_message = {
                'type': 'get_peers'
            }
        
            sock.send(json.dumps(request_message).encode())
        
            data = sock.recv(1024)
            if data:
                response = json.loads(data.decode())
                if response.get('type') == 'peer_list':
                    for peer_host, peer_port in response.get('peers', []):
                        if not any(p.get('host') == peer_host and p.get('port') == peer_port for p in self.known_peers):
                            self.known_peers.append({
                                'host': peer_host,
                                'port': peer_port,
                                'discovered_at': time.time(),
                                'source': 'bootstrap'
                            })
                            logger.info(f"📥 Получен пир {peer_host}:{peer_port} от bootstrap")
                
                    logger.info(f"📥 Всего получено {len(response.get('peers', []))} пиров от bootstrap сервера")
        
            sock.close()
        
        except Exception as e:
            logger.warning(f"❌ Не удалось получить пиров от bootstrap сервера: {e}")
    
    def connect_to_all_known_peers(self):
        """Подключиться ко всем известным пирам (для тестирования)"""
        logger.info("🔗 Ручное подключение ко всем известным пирам")
        connected_count = 0
        
        for peer in list(self.known_peers):
            try:
                host = peer.get('host')
                port = peer.get('port')
                
                if host and port and not self._is_bootstrap_node(host, port):
                    if self._connect_to_peer(host, port):
                        connected_count += 1
                        
            except Exception as e:
                logger.error(f"Ошибка ручного подключения к {peer}: {e}")
        
        logger.info(f"✅ Ручное подключение завершено: {connected_count} успешных подключений")
        return connected_count
        
    def _load_known_peers(self):
        """Загрузка известных пиров из базы данных"""
        try:
            # Временная реализация - можно интегрировать с БД
            self.known_peers = self.bootstrap_nodes.copy()
            logger.info(f"Загружено {len(self.known_peers)} известных пиров")
        except Exception as e:
            logger.error(f"Ошибка загрузки известных пиров: {e}")
    
    def _save_known_peers(self):
        """Сохранение известных пиров в базу данных"""
        try:
            # Временная реализация - можно интегрировать с БД
            logger.info(f"Сохранено {len(self.known_peers)} известных пиров")
        except Exception as e:
            logger.error(f"Ошибка сохранения известных пиров: {e}")
    
    def _exchange_peer_info(self):
        """Полный обмен информацией о пирах между узлами сети"""
        try:
            current_time = time.time()
            
            # Обмениваемся не чаще чем раз в peer_exchange_interval секунд
            if current_time - self.last_peer_exchange < self.peer_exchange_interval:
                return
                
            self.last_peer_exchange = current_time
            
            if not self.connected_peers:
                logger.debug("Нет подключенных пиров для обмена информацией")
                return
            
            # Подготавливаем список известных пиров для обмена
            peer_list = []
            
            # Добавляем подключенных пиров
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username'):
                    peer_list.append({
                        'host': peer_info['address'][0],
                        'port': peer_info['address'][1],
                        'username': peer_info['username'],
                        'last_seen': peer_info.get('last_seen', current_time),
                        'type': 'connected'
                    })
            
            # Добавляем известные пиры (но не более 20 чтобы не перегружать)
            for peer in list(self.known_peers[:20]):
                peer_list.append({
                    'host': peer['host'],
                    'port': peer['port'],
                    'type': 'known',
                    'source': 'local'
                })
            
            if not peer_list:
                logger.debug("Нет пиров для обмена")
                return
            
            # Создаем сообщение для обмена
            exchange_data = {
                'type': 'peer_exchange',
                'peers': peer_list,
                'timestamp': current_time,
                'from': self.username or 'unknown'
            }
            
            # Рассылаем информацию всем подключенным пирам
            successful_sends = 0
            for peer_id, peer_info in list(self.connected_peers.items()):
                if self._send_to_peer(peer_info, exchange_data):
                    successful_sends += 1
            
            logger.info(f"Обмен информацией о пирах: отправлено {successful_sends}/{len(self.connected_peers)} пирам, {len(peer_list)} записей")
            
        except Exception as e:
            logger.error(f"Ошибка обмена информацией о пирах: {e}")
    
    def exchange_peer_info_sync(self):
        """Синхронный обмен информацией о пирах"""
        try:
            # Создаем копию для безопасной итерации
            connected_peers_copy = list(self.connected_peers)
            sent_count = 0
        
            for peer in connected_peers_copy:
                try:
                    # Подготовка данных для обмена
                    peer_info = {
                        'type': 'peer_exchange',
                        'peers': list(self.known_peers),
                        'timestamp': time.time()
                    }
                
                    # Синхронная отправка
                    if self.send_to_peer_sync(peer, json.dumps(peer_info).encode()):
                        sent_count += 1
                    
                except Exception as e:
                    self.logger.debug(f"Ошибка обмена с пиром: {e}")
                    # Удаляем проблемного пира
                    if peer in self.connected_peers:
                        self.connected_peers.remove(peer)
                    continue
                
                    self.logger.info(f"Обмен информацией о пирах: отправлено {sent_count}/{len(connected_peers_copy)} пирам")
        
            return sent_count > 0
        
        except Exception as e:
            self.logger.error(f"Ошибка обмена информацией о пирах: {e}")
            return False

    def send_to_peer_sync(self, peer, data):
        """Синхронная отправка данных пиру"""
        try:
            if hasattr(peer, 'writer'):
                writer = peer.writer
                if not writer.is_closing():
                    writer.write(data)
                    # Для синхронной работы можем использовать drain() в отдельном потоке
                    # или использовать буферизированную отправку
                    return True
            return False
        except (ConnectionError, BrokenPipeError, OSError) as e:
            logger.debug(f"Обрыв соединения с пиром: {e}")
            # Удаляем пира из подключенных
            if peer in self.connected_peers:
                self.connected_peers.remove(peer)
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка отправки: {e}")
            return False

    def _handle_peer_exchange(self, data: dict, peer_id: str):
        """Обработка полученной информации о пирах"""
        try:
            received_peers = data.get('peers', [])
            from_user = data.get('from', 'unknown')
            
            logger.info(f"Получена информация о {len(received_peers)} пирах от {from_user}")
            
            new_peers_found = 0
            current_time = time.time()
            
            for peer_info in received_peers:
                try:
                    host = peer_info.get('host')
                    port = peer_info.get('port')
                    
                    # Проверяем валидность данных
                    if not host or not port:
                        continue
                    
                    # Игнорируем себя
                    if host in ['localhost', '127.0.0.1', '0.0.0.0'] and port == self.listen_port:
                        continue
                    
                    # Игнорируем невалидные порты
                    if not (1024 <= port <= 65535):
                        continue
                    
                    peer_key = f"{host}:{port}"
                    
                    # Проверяем, не подключены ли уже к этому пиру
                    if peer_key in list(self.connected_peers.keys()):
                        # Обновляем информацию о существующем пире
                        self.connected_peers[peer_key]['last_seen'] = current_time
                        if peer_info.get('username'):
                            self.connected_peers[peer_key]['username'] = peer_info['username']
                        continue
                    
                    # Проверяем, есть ли уже в известных пирах
                    peer_exists = any(p.get('host') == host and p.get('port') == port for p in list(self.known_peers))
                    
                    if not peer_exists:
                        # Добавляем в известные пиры
                        new_peer = {
                            'host': host,
                            'port': port,
                            'discovered_at': current_time,
                            'source': f"exchange_from_{from_user}",
                            'username': peer_info.get('username')
                        }
                        self.known_peers.append(new_peer)
                        new_peers_found += 1
                        
                        # Пытаемся подключиться к новому пиру (с задержкой чтобы не перегружать)
                        threading.Timer(2.0, self._connect_to_peer, args=(host, port)).start()
                        
                        logger.debug(f"Обнаружен новый пир: {host}:{port} от {from_user}")
                
                except Exception as e:
                    logger.debug(f"Ошибка обработки информации о пире {peer_info}: {e}")
            
            if new_peers_found > 0:
                logger.info(f"Обнаружено {new_peers_found} новых пиров от {from_user}")
                
                # Сохраняем обновленный список известных пиров
                self._save_known_peers()
                
        except Exception as e:
            logger.error(f"Ошибка обработки обмена пирами: {e}")
    
    def _connect_to_peer(self, host: str, port: int):
        """Подключение к указанному пиру с улучшенным логированием"""
        try:
            peer_key = f"{host}:{port}"
            
            logger.info(f"🔄 Попытка подключения к {host}:{port} (мой порт: {self.listen_port})")
            
            # Проверяем, не подключены ли уже
            if peer_key in self.connected_peers:
                logger.info(f"✅ Уже подключены к пиру {peer_key}")
                return True
            
            # Проверяем, не пытаемся ли подключиться к себе
            if host in ['localhost', '127.0.0.1'] and port == self.listen_port:
                logger.debug(f"⚠️ Пропускаем подключение к себе {host}:{port}")
                return False
            
            # Проверяем, не является ли это bootstrap узлом
            if self._is_bootstrap_node(host, port):
                logger.debug(f"⚠️ Пропускаем bootstrap узел {host}:{port}")
                return False
            
            logger.info(f"🔗 Установка соединения с {host}:{port}")
            
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.settimeout(10.0)
            peer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            try:
                peer_socket.connect((host, port))
                peer_socket.settimeout(30.0)
                logger.info(f"✅ Успешное подключение к {host}:{port}")
                
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                logger.warning(f"❌ Не удалось подключиться к {host}:{port}: {e}")
                peer_socket.close()
                
                # Помечаем пира как недоступного
                self._mark_peer_unavailable(host, port)
                return False
        
            # Успешное подключение
            self.connected_peers[peer_key] = {
                'socket': peer_socket,
                'address': (host, port),
                'connected_at': time.time(),
                'last_seen': time.time(),
                'username': None
            }
        
            # Запускаем обработчик для этого пира
            peer_thread = threading.Thread(
                target=self._handle_client_connection,
                args=(peer_socket, (host, port)),
                daemon=True
            )
            peer_thread.start()
            
            logger.info(f"🎉 Полностью подключено к пиру {host}:{port}")
            
            # Отправляем информацию о себе новому пиру
            self._send_self_info(peer_key)
            
            return True
        
        except Exception as e:
            logger.error(f"💥 Критическая ошибка подключения к {host}:{port}: {e}")
            return False

    def _mark_peer_unavailable(self, host: str, port: int):
        """Пометить пира как недоступного"""
        try:
            # Удаляем из известных пиров
            self.known_peers = [
                p for p in self.known_peers 
                if not (p.get('host') == host and p.get('port') == port)
            ]
            logger.info(f"🗑️ Удален недоступный пир {host}:{port}")
        except Exception as e:
            logger.debug(f"Ошибка пометки пира как недоступного: {e}")

    def _is_bootstrap_node(self, host: str, port: int) -> bool:
        """Проверяет, является ли узел bootstrap узлом"""
        for node in self.bootstrap_nodes:
            if node['host'] == host and node['port'] == port:
                return True
        return False

    def _send_self_info(self, peer_id: str):
        """Отправка информации о себе новому пиру"""
        try:
            if peer_id not in self.connected_peers:
                return
            
            self_info = {
                'type': 'user_online',
                'username': self.username,
                'timestamp': time.time(),
                'client_version': '1.0.0'
            }
            
            self._send_to_peer(self.connected_peers[peer_id], self_info)
            logger.debug(f"Отправлена информация о себе пиру {peer_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки информации о себе: {e}")
    
    def _connect_to_bootstrap_nodes(self):
        """Подключение к bootstrap узлам с временными соединениями"""
        connected_count = 0
        
        logger.info(f"🔄 Регистрация в {len(self.bootstrap_nodes)} bootstrap узлах...")

        for node in self.bootstrap_nodes:
            try:
                host = node['host']
                port = node['port']
                
                # Пропускаем попытку подключения к себе
                if host in ['localhost', '127.0.0.1'] and port == self.listen_port:
                    continue
                
                # Используем временное соединение для регистрации
                if self._register_with_bootstrap(host, port):
                    connected_count += 1
                    logger.info(f"✅ Успешная регистрация в bootstrap узле {host}:{port}")
                else:
                    logger.warning(f"❌ Не удалось зарегистрироваться в bootstrap узле {host}:{port}")
                    
            except Exception as e:
                logger.error(f"Ошибка регистрации в bootstrap узле {node}: {e}")
        
        logger.info(f"Зарегистрировано в {connected_count}/{len(self.bootstrap_nodes)} bootstrap узлах")
        
        # НЕ добавляем bootstrap узлы в connected_peers - они не для постоянного соединения

    def _register_with_bootstrap(self, host: str, port: int) -> bool:
        """Временная регистрация в bootstrap узле (без постоянного соединения)"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host, port))
            
            # Регистрация
            registration_message = {
                'type': 'register',
                'port': self.listen_port,
                'username': self.username  # Если есть имя пользователя, отправляем
            }
            
            sock.send(json.dumps(registration_message).encode() + b'\n')
            
        # Читаем ответ
            data = sock.recv(4096)
            if data:
                response = json.loads(data.decode())
                if response.get('type') == 'registration_success':
                    logger.info(f"✅ Успешная регистрация в bootstrap сервере")
                    # Добавляем полученных пиров в known_peers
                    for peer_host, peer_port in response.get('peers', []):
                        if (peer_host, peer_port) != (host, port):
                            if not any(p.get('host') == peer_host and p.get('port') == peer_port for p in self.known_peers):
                                self.known_peers.append({
                                    'host': peer_host, 
                                    'port': peer_port,
                                    'discovered_at': time.time(),
                                    'source': 'bootstrap'
                                })
                                logger.info(f"📥 Добавлен пир {peer_host}:{peer_port}")
                    
                    # ЗАКРЫВАЕМ соединение после регистрации - это нормально!
                    sock.close()
                    return True
            sock.close()
            return False
        
        except Exception as e:
            logger.warning(f"❌ Не удалось зарегистрироваться в bootstrap сервере: {e}")
            return False

    def _network_maintenance(self):
        """Обслуживание сети - обмен информацией о пирах, проверка соединений"""
        last_bootstrap_update = 0
        last_auto_connect = 0
        last_user_list_update = 0
        last_message_cleanup = 0
        bootstrap_update_interval = 300  # 5 минут - обновляем bootstrap реже
        auto_connect_interval = 30
        user_list_update_interval = 15  # секунд
        message_cleanup_interval = 300  # 5 минут

        while self.is_running:
            try:
                current_time = time.time()

                # АВТОМАТИЧЕСКОЕ ПОДКЛЮЧЕНИЕ К ИЗВЕСТНЫМ ПИРАМ
                if current_time - last_auto_connect >= auto_connect_interval:
                    self._auto_connect_to_known_peers()
                    last_auto_connect = current_time
                    
                # ПЕРИОДИЧЕСКАЯ перерегистрация в bootstrap узлах (раз в 5 минут)
                if current_time - last_bootstrap_update >= bootstrap_update_interval:
                    logger.info("🔄 Периодическое обновление регистрации в bootstrap узлах...")
                    self._connect_to_bootstrap_nodes()
                    last_bootstrap_update = current_time
                
                # Обновляем список пользователей периодически
                if current_time - last_user_list_update >= user_list_update_interval:
                    online_users = self.get_online_users()
                    self.user_list_updated.emit(online_users)
                    last_user_list_update = current_time

                # Очистка старых сообщений
                if current_time - last_message_cleanup >= message_cleanup_interval:
                    self._cleanup_old_messages()
                    last_message_cleanup = current_time
                
                # Проверяем соединения с пирами 
                self._check_peer_connections()
                
                # Обмениваемся информацией о пирах
                self._exchange_peer_info()
                
                # Очищаем старые известные пиры (старше 24 часов)
                self._cleanup_old_peers()
                
                time.sleep(10)  # Основная пауза между циклами
                
            except Exception as e:
                logger.error(f"Ошибка обслуживания сети: {e}")
                time.sleep(30)  # Большая пауза при ошибке

    def _check_peer_connections(self):
        """Проверка активности подключенных пиров с улучшенной логикой"""
        current_time = time.time()
        disconnected_peers = []
        
        for peer_id, peer_info in list(self.connected_peers.items()):
            # Если пир не активен более 60 секунд, считаем его отключенным
            if current_time - peer_info.get('last_seen', 0) > 60:
                logger.info(f"🔌 Пир {peer_username} ({peer_id}) отключен по таймауту активности")
                disconnected_peers.append(peer_id)
            else:
                # Отправляем ping для проверки соединения (только если не было активности 30+ секунд)
                if current_time - peer_info.get('last_seen', 0) > 30:
                    try:
                        ping_data = {'type': 'ping', 'timestamp': current_time}
                        if not self._send_to_peer(peer_info, ping_data):
                            logger.info(f"🔌 Не удалось отправить ping пиру {peer_username} ({peer_id})")
                            disconnected_peers.append(peer_id)
                        else:
                            logger.debug(f"✅ Ping отправлен пиру {peer_username} ({peer_id})")
                    except Exception as e:
                        logger.warning(f"🔌 Ошибка отправки ping пиру {peer_username} ({peer_id}): {e}")
                        disconnected_peers.append(peer_id)
        
        # Закрываем соединения с отключенными пирами
        for peer_id in disconnected_peers:
            self._handle_peer_disconnection(peer_id)

    def _handle_peer_disconnection(self, peer_id: str):
        """Обработка отключения пира"""
        try:
            if peer_id in self.connected_peers:
                peer_info = self.connected_peers[peer_id]
                username = peer_info.get('username', 'unknown')
                
                # Закрываем сокет
                try:
                    peer_info['socket'].close()
                except:
                    pass
                
                # Удаляем из подключенных
                del self.connected_peers[peer_id]
                
                # Помечаем сообщения для этого пользователя как недоставленные
                self._mark_messages_undelivered(username)
                
                logger.info(f"🔌 Пир {username} ({peer_id}) полностью отключен")
                
                # Обновляем список пользователей
                online_users = self.get_online_users()
                self.user_list_updated.emit(online_users)
                
        except Exception as e:
            logger.error(f"Ошибка обработки отключения пира {peer_id}: {e}")
                

    def _mark_messages_undelivered(self, username: str):
        """Помечаем сообщения для пользователя как недоставленные"""
        try:
            with self.message_retry_lock:
                undelivered_count = 0
                for msg_id, msg_data in list(self.pending_messages.items()):
                    if (msg_data['message_data'].get('to') == username and 
                        msg_id not in self.delivered_messages):
                        undelivered_count += 1
                        # Можно добавить логику для уведомления UI о недоставленных сообщениях
                
                if undelivered_count > 0:
                    logger.warning(f"⚠️ {undelivered_count} сообщений для {username} не доставлено")
                    
        except Exception as e:
            logger.error(f"Ошибка пометки недоставленных сообщений: {e}")
        
            
    def _cleanup_old_peers(self):
        """Очистка старых записей о пирах"""
        current_time = time.time()
        max_age = 24 * 60 * 60  # 24 часа
        
        initial_count = len(self.known_peers)
        self.known_peers = [
            p for p in self.known_peers 
            if current_time - p.get('discovered_at', 0) < max_age
        ]
        
        if len(self.known_peers) < initial_count:
            logger.info(f"Очищено {initial_count - len(self.known_peers)} старых пиров")
    
    def _auto_connect_to_known_peers(self):
        """Автоматическое подключение к известным пирам с улучшенной логикой"""
        try:
            if not self.known_peers:
                logger.debug("Нет известных пиров для автоматического подключения")
                return
                
            current_time = time.time()
            connected_count = len(self.connected_peers)
            
            logger.info(f"🔄 Автоматическое подключение: {len(self.known_peers)} известных пиров, {connected_count} уже подключено")
            
            # Подключаемся к самым свежим пирам сначала
            sorted_peers = sorted(
                self.known_peers, 
                key=lambda x: x.get('discovered_at', 0), 
                reverse=True
            )
        
            for peer in sorted_peers:
                try:
                    host = peer.get('host')
                    port = peer.get('port')
                    
                    if not host or not port:
                        continue
                        
                    # Пропускаем себя
                    if host in ['localhost', '127.0.0.1'] and port == self.listen_port:
                        continue
                    
                    # Пропускаем bootstrap узлы
                    if self._is_bootstrap_node(host, port):
                        continue
                    
                    peer_key = f"{host}:{port}"
                
                    # Если уже подключены, пропускаем
                    if peer_key in self.connected_peers:
                        continue
                    
                    # Проверяем, не пытались ли подключиться недавно
                    last_attempt = peer.get('last_connect_attempt', 0)
                    if current_time - last_attempt < 60:  # Не чаще чем раз в минуту
                        continue
                    
                    # Обновляем время последней попытки
                    peer['last_connect_attempt'] = current_time
                    
                    logger.info(f"🔄 Автоматическое подключение к пиру {host}:{port}")
                    
                    # Запускаем подключение (не в отдельном потоке, чтобы не перегружать)
                    if self._connect_to_peer(host, port):
                        connected_count += 1
                    
                    # Ограничиваем количество одновременных попыток
                    if connected_count >= 3:
                        break
                        
                except Exception as e:
                    logger.debug(f"Ошибка автоматического подключения к пиру {peer}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка автоматического подключения: {e}")

    def _process_received_data(self, data: dict, peer_id: str):
        """Обработка полученных данных с поддержкой обмена пирами"""
        message_type = data.get('type')

        logger.debug(f"📨 Получено сообщение типа '{message_type}' от {peer_id}")
    

        if message_type == 'chat_message':
            self._handle_chat_message(data, peer_id)
        elif message_type == 'message_ack':
            self._handle_message_ack(data)
        elif message_type == 'user_online':
            self._handle_user_online(data, peer_id)    
        elif message_type == 'message':
            self._handle_message(data)
        elif message_type == 'user_online':
            self._handle_user_online(data, peer_id)
        elif message_type == 'user_offline':
            self._handle_user_offline(data)
        elif message_type == 'call_request':
            self._handle_call_request(data)
        elif message_type == 'peer_exchange':  # ДОБАВЛЕНО
            self._handle_peer_exchange(data, peer_id)
        elif message_type == 'ping':
            self._handle_ping(data, peer_id)
        elif message_type == 'pong':  
            self._handle_pong(data, peer_id)
        elif message_type == 'peer_discovery':
            self._handle_peer_discovery(data)
        else:
            logger.warning(f"Неизвестный тип сообщения: {message_type}")

    def send_message(self, to_username: str, message: str, message_id: str = None) -> bool:
        """Отправка сообщения пользователю через P2P сеть"""
        try:
            if not message_id:
                import uuid
                message_id = str(uuid.uuid4())
        
            # Ищем пользователя в подключенных пирах
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == to_username:
                    target_peer = peer_info
                    break
        
            if target_peer:
                message_data = {
                    'type': 'message',
                    'from': self.username,
                    'to': to_username,
                    'message': message,
                    'message_id': message_id,
                    'timestamp': time.time(),
                    'requires_ack': True  # Требуем подтверждение
                }

                # Сохраняем в ожидающие подтверждения
                with self.message_retry_lock:
                    self.pending_messages[message_id] = {
                        'message_data': message_data,
                        'target_peer': target_peer,
                        'timestamp': time.time(),
                        'last_sent': time.time(),
                        'attempts': 0
                }
            
                success = self._send_message_direct(target_peer, message_data, message_id)
                if success:
                    logger.info(f"✅ Сообщение {message_id} отправлено пользователю {to_username}")
                    return True
                else:
                    logger.error(f"❌ Не удалось отправить сообщение {message_id} пользователю {to_username}")
                    return False
            else:
                logger.warning(f"⚠️ Пользователь {to_username} не найден в подключенных пирах")
                # Показываем список доступных пользователей для отладки
                available_users = []
                for peer_id, peer_info in list(self.connected_peers.items()):
                    if peer_info.get('username'):
                        available_users.append(peer_info['username'])
            
                logger.info(f"📋 Доступные пользователи: {available_users}")
                return False
            
        except Exception as e:
            logger.error(f"💥 Ошибка отправки сообщения: {e}")
            return False

    def _handle_chat_message(self, data: dict, peer_id: str):
        """Обработка входящего сообщения чата"""
        try:
            from_user = data.get('from')
            message = data.get('message')
            message_id = data.get('message_id')
            requires_ack = data.get('requires_ack', False)
        
            if from_user and message:
                logger.info(f"📨 Получено сообщение от {from_user}: {message} (ID: {message_id})")

                # Отправляем подтверждение получения, если требуется
                if requires_ack and message_id:
                    ack_data = {
                        'type': 'message_ack',
                        'message_id': message_id,
                        'timestamp': time.time()
                    }
                    if peer_id in self.connected_peers:
                        self._send_to_peer(self.connected_peers[peer_id], ack_data)
                        logger.debug(f"📨 Отправлено подтверждение для сообщения {message_id}")
            
                # Сохраняем сообщение в БД
                if hasattr(self, 'db'):
                    self.db.store_message(from_user, self.username, message, message_id)
                
                # Отправляем сигнал в GUI
                self.message_received.emit(from_user, message)
                
            else:
                logger.warning("⚠️ Получено некорректное сообщение чата")
        
        except Exception as e:
            logger.error(f"💥 Ошибка обработки сообщения чата: {e}")

    def _send_message_direct(self, peer_info: Dict, message_data: dict, message_id: str = None) -> bool:
        """Прямая отправка сообщения с обновлением статистики"""
        try:
            success = self._send_to_peer(peer_info, message_data)
            
            if success and message_id:
                with self.message_retry_lock:
                    if message_id in self.pending_messages:
                        self.pending_messages[message_id]['last_sent'] = time.time()
                        self.pending_messages[message_id]['attempts'] += 1
                        logger.debug(f"Обновлена статистика для сообщения {message_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Ошибка прямой отправки сообщения: {e}")
            return False

    def _handle_message_ack(self, data: dict):
        """Обработка подтверждения доставки сообщения"""
        try:
            message_id = data.get('message_id')
            
            if message_id:
                with self.message_retry_lock:
                    if message_id in self.pending_messages:
                        del self.pending_messages[message_id]
                        self.delivered_messages.add(message_id)
                        logger.info(f"✅ Подтверждение доставки для сообщения {message_id}")
                    else:
                        logger.warning(f"⚠️ Получено подтверждение для неизвестного сообщения {message_id}")
                        
        except Exception as e:
            logger.error(f"Ошибка обработки подтверждения: {e}")
    
    def _handle_message(self, data: dict):
        """Обработка входящего сообщения"""
        try:
            from_user = data.get('from')
            message = data.get('message')
            message_id = data.get('message_id')
        
            if from_user and message:
                logger.info(f"📨 Получено сообщение от {from_user}: {message}")
            
                # Сохраняем сообщение в БД
                if hasattr(self, 'db'):
                    self.db.store_message(from_user, self.username, message, message_id)
            
                # Отправляем сигнал в GUI
                self.message_received.emit(from_user, message)
            
            else:
                logger.warning("⚠️ Получено некорректное сообщение")
            
        except Exception as e:
            logger.error(f"💥 Ошибка обработки сообщения: {e}")
        
    def _handle_ping(self, data: dict, peer_id: str):
        """Обработка ping-сообщения"""
        try:
            # Обновляем время последней активности
            if peer_id in self.connected_peers:
                self.connected_peers[peer_id]['last_seen'] = time.time()
            
            # Отправляем pong в ответ
            pong_data = {
                'type': 'pong',
                'timestamp': data.get('timestamp'),
                'response_time': time.time()
            }
            
            if peer_id in self.connected_peers:
                self._send_to_peer(self.connected_peers[peer_id], pong_data)
                
        except Exception as e:
            logger.debug(f"Ошибка обработки ping: {e}")
    
    def _handle_pong(self, data: dict, peer_id: str):
        """Обработка pong-сообщения"""
        try:
            # Обновляем время последней активности
            if peer_id in self.connected_peers:
                self.connected_peers[peer_id]['last_seen'] = time.time()
        
            logger.debug(f"✅ Получен pong от {peer_id}")
        except Exception as e:
            logger.debug(f"Ошибка обработки pong: {e}")

    def _handle_user_online(self, data: dict, peer_id: str):
        """Обработка уведомления о входе пользователя"""
        username = data.get('username')
        if username and peer_id in self.connected_peers:
            self.connected_peers[peer_id]['username'] = username
            self.connected_peers[peer_id]['last_seen'] = time.time()
            
            logger.info(f"👤 Пользователь {username} в сети (пир {peer_id})")
            
            # НЕМЕДЛЕННО обновляем список пользователей в GUI
            online_users = self.get_online_users()
            self.user_list_updated.emit(online_users)
            
            # Логируем для отладки
            logger.info(f"📊 Обновлен список пользователей: {len(online_users)} пользователей онлайн")
    
    def _handle_user_offline(self, data: dict):
        """Обработка уведомления о выходе пользователя"""
        username = data.get('username')
        if username:
            logger.info(f"Пользователь {username} вышел из сети")
    
    def _handle_peer_discovery(self, data: dict):
        """Обработка запроса на обнаружение пиров"""
        try:
            # Отправляем список известных пиров в ответ
            peer_list = []
            for peer in self.known_peers[:10]:  # Не более 10 пиров
                peer_list.append({
                    'host': peer['host'],
                    'port': peer['port']
                })
            
            response = {
                'type': 'peer_discovery_response',
                'peers': peer_list,
                'timestamp': time.time()
            }
            
            # Отправляем ответ (нужен peer_id отправителя)
            # Эта логика может быть расширена при необходимости
            
        except Exception as e:
            logger.error(f"Ошибка обработки обнаружения пиров: {e}")
    
    def _cleanup_old_messages(self):
        """Очистка старых сообщений из трекера"""
        try:
            current_time = time.time()
            max_age = 3600  # 1 час
            
            with self.message_retry_lock:
                # Очищаем pending_messages
                old_messages = [
                    msg_id for msg_id, msg_data in self.pending_messages.items()
                    if current_time - msg_data['timestamp'] > max_age
                ]
                
                for msg_id in old_messages:
                    del self.pending_messages[msg_id]
                
                # Очищаем delivered_messages (оставляем только последние 1000)
                if len(self.delivered_messages) > 1000:
                    # Преобразуем в список, отсортируем по времени (если храним время) или просто обрежем
                    self.delivered_messages = set(list(self.delivered_messages)[-500:])
                
                if old_messages:
                    logger.info(f"🧹 Очищено {len(old_messages)} старых сообщений")
                    
        except Exception as e:
            logger.error(f"Ошибка очистки старых сообщений: {e}")

    # Остальные методы остаются без изменений...
    def _accept_connections(self):
        """Принятие входящих соединений"""
        while self.is_running:
            try:
                client_socket, address = self.listener_socket.accept()
                logger.info(f"Новое подключение от {address}")
                
                # Устанавливаем таймауты для сокета
                client_socket.settimeout(30.0)  # Таймаут операций 30 секунд
            
                peer_key = f"{address[0]}:{address[1]}"
                

                # Проверяем, не подключены ли уже к этому пиру
                if peer_key in self.connected_peers:
                    logger.info(f"⚠️ Повторное подключение от {address}, закрываем предыдущее")
                    try:
                        old_socket = self.connected_peers[peer_key]['socket']
                        old_socket.close()
                    except:
                        pass
                
                
                # Добавляем пира в список подключенных
                self.connected_peers[peer_key] = {
                    'socket': client_socket,
                    'address': address,
                    'connected_at': time.time(),
                    'last_seen': time.time(),
                    'username': None
                }
                
                # Обрабатываем соединение в отдельном потоке
                client_thread = threading.Thread(
                    target=self._handle_client_connection,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()

                logger.info(f"🔄 Обработчик запущен для входящего подключения {address}")
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    logger.error(f"Ошибка принятия соединения: {e}")
                    time.sleep(1)  # Пауза при ошибке
    
    def _handle_client_connection(self, client_socket: socket.socket, address: tuple):
        """Обработка клиентского соединения с улучшенной стабильностью"""
        peer_id = f"{address[0]}:{address[1]}"
        logger.info(f"🔄 Начало обработки соединения с {address}")
        
        # ПРОВЕРЯЕМ, не является ли это bootstrap узлом
        if self._is_bootstrap_node(address[0], address[1]):
            logger.info(f"⚠️ Входящее соединение от bootstrap узла {address} - обрабатываем временно")
        
        try:
            buffer = b""
            while self.is_running:
                try:
                    # Читаем данные с таймаутом
                    data = client_socket.recv(4096)
                    if not data:
                        logger.info(f"🔌 Соединение с {address} закрыто удаленной стороной")
                        break
                    
                    buffer += data
                    
                    # Пытаемся декодировать JSON сообщения
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line:
                            try:
                                message = json.loads(line.decode('utf-8'))
                                
                                # Обновляем время последней активности
                                if peer_id in self.connected_peers:
                                    self.connected_peers[peer_id]['last_seen'] = time.time()
                                
                                # Обрабатываем полученные данные
                                self._process_received_data(message, peer_id)
                                
                            except json.JSONDecodeError as e:
                                logger.warning(f"❌ Неверный JSON от {address}: {e}")
                            except Exception as e:
                                logger.error(f"❌ Ошибка обработки данных от {address}: {e}")
                    
                except socket.timeout:
                    continue  # Таймаут - продолжаем
                except ConnectionResetError:
                    logger.info(f"🔌 Соединение с {address} разорвано")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка чтения данных от {address}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обработки соединения с {address}: {e}")
        finally:
            # Обрабатываем отключение
            self._handle_peer_disconnection(peer_id)

    def _send_to_peer(self, peer_info: Dict, data: dict) -> bool:
        """Отправка данных пиру"""
        try:
            serialized_data = json.dumps(data).encode('utf-8') + b'\n'  # Добавляем разделитель
            peer_info['socket'].sendall(serialized_data)
            return True
        except BrokenPipeError:
            logger.warning(f"🔌 Соединение с пиром разорвано при отправке")
            return False
        except ConnectionResetError:
            logger.warning(f"🔌 Соединение с пиром сброшено")
            return False
        except Exception as e:
            logger.debug(f"Ошибка отправки данных пиру: {e}")
            return False
    
    def _serialize_data(self, data: dict) -> bytes:
        """Сериализация данных для отправки"""
        return json.dumps(data).encode('utf-8')
    
    def _receive_data(self, sock: socket.socket) -> Optional[dict]:
        """Получение и десериализация данных"""
        try:
            data = sock.recv(4096)
            if data:
                return json.loads(data.decode('utf-8'))
            return None
        except Exception as e:
            logger.debug(f"Ошибка получения данных: {e}")
            return None
    
    def get_online_users(self) -> List[Dict]:
        """Получение списка онлайн пользователей с улучшенным логированием"""
        online_users = []

        # Пользователи из подключенных пиров
        for peer_id, peer_info in list(self.connected_peers.items()):
            if peer_info.get('username'):
                user_data = {
                    'username': peer_info['username'],
                    'host': peer_info['address'][0],
                    'port': peer_info['address'][1],
                    'status': 'connected',
                    'last_seen': peer_info.get('last_seen', time.time())
                }
                online_users.append(user_data)
                logger.debug(f"📋 Добавлен в онлайн: {peer_info['username']})")

        logger.debug(f"📊 get_online_users: {len(online_users)} пользователей онлайн")
        return online_users


    def send_call_request(self, to_username: str, call_type: str) -> str:
        """Отправка запроса на звонок"""
        try:
            call_id = str(uuid.uuid4())
            message = {
                'type': 'call_request',
                'call_id': call_id,
                'from': self.username,
                'to': to_username,
                'call_type': call_type,
                'timestamp': time.time()
            }
        
            # Ищем пира с указанным именем пользователя
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == to_username:
                    if self._send_to_peer(peer_info, message):
                        logger.info(f"📞 Отправлен запрос на звонок {call_id} пользователю {to_username}")
                        return call_id
                    else:
                        logger.error(f"❌ Не удалось отправить запрос на звонок пользователю {to_username}")
                        return None
            logger.warning(f"⚠️ Пользователь {to_username} не найден в подключенных пирах")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки запроса на звонок: {e}")
            return None

    def send_call_response(self, call_id: str, response: str) -> bool:
        """Отправка ответа на запрос звонка (accept/reject/end)"""
        try:
            message = {
                'type': 'call_response',
                'call_id': call_id,
                'response': response,
                'from': self.username,
                'timestamp': time.time()
            }
            
            # Отправляем ответ всем пирам (в реальности нужно отправлять конкретному пиру)
            sent = False
            for peer_id, peer_info in list(self.connected_peers.items()):
                if self._send_to_peer(peer_info, message):
                    sent = True
                    logger.info(f"📞 Отправлен ответ на звонок {call_id}: {response}")
                    break
            return sent
        
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ответа на звонок: {e}")
            return False

    def setup_media_connection(self, call_id: str, peer_username: str) -> bool:
        """Установка медиа-соединения для звонка - ВРЕМЕННАЯ ЗАГЛУШКА"""
        logger.info(f"🔊 setup_media_connection заглушка: call_id={call_id}, peer={peer_username}")
        # В реальной реализации здесь должна быть установка P2P медиа соединения
        # Пока возвращаем True для тестирования аудио функционала
        return True

    def get_media_socket(self, call_id: str):
        """Получение медиа-сокета для звонка - ВРЕМЕННАЯ ЗАГЛУШКА"""
        logger.info(f"🔊 get_media_socket заглушка: call_id={call_id}")
        # В реальной реализации здесь должен возвращаться реальный сокет
        # Пока возвращаем None - аудио будет работать в локальном режиме
        return None

    def close_media_connection(self, call_id: str):
        """Закрытие медиа-соединения для звонка"""
        logger.info(f"🔊 close_media_connection: call_id={call_id}")
        # Заглушка для будущей реализации

    @property
    def connected(self):
        """Свойство для обратной совместимости"""
        return self.is_running