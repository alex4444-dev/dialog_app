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
        './logs/p2p_network.log', 
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
    
    def __init__(self, db, port=8890, bootstrap_nodes=None):
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
        self.peers_lock = threading.Lock()

        self.media_ports = set()  # Для отслеживания используемых медиа-портов
        
        # Bootstrap узлы: если переданы, используем их, иначе пустой список
        if bootstrap_nodes is None:
            self.bootstrap_nodes = [{"host": "localhost", "port": 8888}]   # или можно оставить localhost как запасной вариант
        else:
            self.bootstrap_nodes = bootstrap_nodes

        # Система отслеживания сообщений
        self.pending_messages = {}  # message_id -> {data, timestamp, attempts, target_peer}
        self.delivered_messages = set()  # message_id подтвержденных сообщений
        self.message_retry_lock = threading.Lock()  

        # Запускаем поток для повторной отправки
        self.retry_thread = threading.Thread(target=self._retry_messages_loop, daemon=True)
        self.retry_thread.start()  

        # ДЛЯ МЕДИА-СОЕДИНЕНИЙ
        self.media_server_host = self._get_local_ip()
        self.media_server_port = 9100
        self.media_sockets = {}  # call_id -> socket
        self.media_connections = {}  # call_id -> media_info
        self.call_requests = {}  # call_id -> call_info

    def _get_local_ip(self) -> str:
        """Определяет IP-адрес машины в локальной сети (не localhost)."""
        try:
            # Подключаемся к внешнему серверу (Google DNS) – это безопасно,
            # соединение сразу закрывается, данные не отправляются.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            return ip
        except Exception:
            # Если не удалось определить, возвращаем localhost как запасной вариант
            return "127.0.0.1"
           
    def connect_to_peer_media(self, call_id, peer_username):
        """Подключение к медиа другого пользователя через центральный сервер"""
        try:
            logger.info(f"🔊 Подключение к медиа пользователя {peer_username} для звонка {call_id}")
            
            # Создаем сокет
            media_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            media_socket.settimeout(10.0)
            
            try:
                media_socket.connect((self.media_server_host, self.media_server_port))
                media_socket.settimeout(30.0)
                
                # Запрашиваем соединение с другим пользователем
                connect_data = {
                    'call_id': call_id,
                    'action': 'connect',
                    'username': self.username,
                    'peer_username': peer_username
                }
                media_socket.send(json.dumps(connect_data).encode())
                
                # Ждем ответа
                response = media_socket.recv(1024)
                if response:
                    resp_data = json.loads(response.decode())
                    if resp_data.get('status') in ['connected', 'waiting']:
                        logger.info(f"✅ Подключение к медиа установлено: {resp_data['status']}")
                        
                        # Сохраняем сокет
                        self.media_sockets[call_id] = media_socket
                        return True
                
            except ConnectionRefusedError:
                logger.error(f"❌ Не удалось подключиться к медиа-серверу")
                media_socket.close()
                return False
            except Exception as e:
                logger.error(f"❌ Ошибка подключения к медиа-серверу: {e}")
                media_socket.close()
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к медиа: {e}")
            return False

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
       
    def simple_connect(self, target_host, target_port):
        """Простое прямое подключение к другому компьютеру"""
        try:
            logger.info(f"🔗 Прямое подключение к {target_host}:{target_port}")
            
            # Подключаемся напрямую
            if self._connect_to_peer(target_host, target_port):
                logger.info(f"✅ Успешное прямое подключение к {target_host}:{target_port}")
                
                # Отправляем информацию о себе
                self_info = {
                    'type': 'user_online',
                    'username': self.username,
                    'timestamp': time.time()
                }
            
                peer_key = f"{target_host}:{target_port}"
                if peer_key in self.connected_peers:
                    self._send_to_peer(self.connected_peers[peer_key], self_info)
                
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка прямого подключения: {e}")
            return False
        
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
                    logger.debug(f"Ошибка обмена с пиром: {e}")
                    # Удаляем проблемного пира
                    if peer in self.connected_peers:
                        self.connected_peers.remove(peer)
                    continue
                
                    logger.info(f"Обмен информацией о пирах: отправлено {sent_count}/{len(connected_peers_copy)} пирам")
        
            return sent_count > 0
        
        except Exception as e:
            logger.error(f"Ошибка обмена информацией о пирах: {e}")
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
        """Подключение к указанному пиру с улучшенным логированием и блокировками"""
        try:
            peer_key = f"{host}:{port}"

            logger.info(f"🔄 Попытка подключения к {host}:{port} (мой порт: {self.listen_port})")

            # Блокируем доступ к connected_peers для проверки
            with self.peers_lock:
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
                # Помечаем пира как недоступного (вне блокировки)
                self._mark_peer_unavailable(host, port)
                return False

            # Успешное подключение – добавляем в словарь под блокировкой
            with self.peers_lock:
                self.connected_peers[peer_key] = {
                    'socket': peer_socket,
                    'address': (host, port),
                    'connected_at': time.time(),
                    'last_seen': time.time(),
                    'username': None
                }

            # Запускаем обработчик для этого пира (без блокировки)
            peer_thread = threading.Thread(
                target=self._handle_client_connection,
                args=(peer_socket, (host, port)),
                daemon=True
            )
            peer_thread.start()

            logger.info(f"🎉 Полностью подключено к пиру {host}:{port}")

            # Отправляем информацию о себе новому пиру (метод сам использует блокировку)
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

    def send_media_info(self, call_id: str, peer_username: str):
        """Отправить информацию о медиа-порте другому пиру"""
        try:
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == peer_username:
                    target_peer = peer_info
                    break
            if not target_peer:
                logger.error(f"❌ Пир {peer_username} не найден")
                return False
            
            # Получаем порт из уже существующего сокета
            sock = self.media_sockets.get(call_id)
            if not sock:
                logger.error(f"❌ Сокет для звонка {call_id} не найден")
                return False
            
            _, port = sock.getsockname()[:2]  # для серверного сокета
            
            media_info = {
                'type': 'media_info',
                'call_id': call_id,
                'media_port': port,
                'media_host': self.media_server_host,
                'action': 'setup',
                'timestamp': time.time()
            }
            return self._send_to_peer(target_peer, media_info)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки media_info: {e}")
            return False
    
    def _check_peer_connections(self):
        """Проверка активности подключенных пиров"""
        current_time = time.time()
        disconnected_peers = []

        # Копируем список пиров под блокировкой
        with self.peers_lock:
            peers_copy = list(self.connected_peers.items())

        for peer_id, peer_info in peers_copy:
            peer_username = peer_info.get('username', 'unknown')

            if current_time - peer_info.get('last_seen', 0) > 60:
                logger.info(f"🔌 Пир {peer_username} ({peer_id}) отключен по таймауту")
                disconnected_peers.append(peer_id)
            else:
                if current_time - peer_info.get('last_seen', 0) > 30:
                    try:
                        ping_data = {'type': 'ping', 'timestamp': current_time}
                        if not self._send_to_peer(peer_info, ping_data):
                            logger.info(f"🔌 Не удалось отправить ping пиру {peer_username} ({peer_id})")
                            disconnected_peers.append(peer_id)
                    except Exception as e:
                        logger.warning(f"🔌 Ошибка ping пиру {peer_username}: {e}")
                        disconnected_peers.append(peer_id)

        for peer_id in disconnected_peers:
            self._handle_peer_disconnection(peer_id)

    def _handle_peer_disconnection(self, peer_id: str):
        """Обработка отключения пира"""
        with self.peers_lock:
            if peer_id not in self.connected_peers:
                return
            peer_info = self.connected_peers[peer_id]
            username = peer_info.get('username', 'unknown')

            # Закрываем сокет (под блокировкой – безопасно)
            try:
                peer_info['socket'].close()
            except:
                pass

            # Удаляем из подключенных
            del self.connected_peers[peer_id]

            # Удаляем из known_peers, чтобы не пытаться переподключаться
            host_port = peer_id.split(':')
            if len(host_port) == 2:
                host, port = host_port
                port = int(port)
                self.known_peers = [
                    p for p in self.known_peers
                    if not (p.get('host') == host and p.get('port') == port)
                ]

        # Обновляем список пользователей (вне блокировки, чтобы не держать lock во время emit)
        online_users = self.get_online_users()
        self.user_list_updated.emit(online_users)
        logger.info(f"🔌 Пир {username} ({peer_id}) полностью отключен")
            
    def setup_video_connection(self, call_id: str, peer_username: str) -> socket.socket:
        """Настройка видео соединения"""
        try:
            logger.info(f"📹 Настройка видео соединения для звонка {call_id}")
            
            # Ищем пира по имени пользователя
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == peer_username:
                    target_peer = peer_info
                    break
            
            if not target_peer:
                logger.error(f"❌ Пир {peer_username} не найден в подключенных")
                return None
            
            peer_host, peer_port = target_peer['address']
            
            # Создаем серверный сокет для видео
            video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Находим свободный порт для видео
            video_port = self._find_free_video_port()
            if not video_port:
                logger.error("❌ Не удалось найти свободный порт для видео")
                return None
            
            try:
                video_socket.bind(('0.0.0.0', video_port))
                video_socket.listen(1)
                video_socket.settimeout(10.0)
                
                logger.info(f"📹 Видео сервер запущен на порту {video_port}")
                
                # Отправляем информацию о видео порте другому пиру
                video_info = {
                    'type': 'video_info',
                    'call_id': call_id,
                    'video_port': video_port,
                    'action': 'setup',
                    'timestamp': time.time()
                }
                
                success = self._send_to_peer(target_peer, video_info)
                
                if success:
                    logger.info(f"✅ Информация о видео порте {video_port} отправлена")
                    
                    # Сохраняем сокет
                    self.media_sockets[f"{call_id}_video"] = video_socket
                    
                    # Запускаем поток для принятия подключения
                    threading.Thread(
                        target=self._accept_video_connection,
                        args=(call_id, video_socket),
                        daemon=True
                    ).start()
                    
                    return video_socket
                else:
                    logger.error(f"❌ Не удалось отправить информацию о видео порте")
                    video_socket.close()
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Ошибка запуска видео сервера: {e}")
                video_socket.close()
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки видео соединения: {e}")
            return None
   
    def _accept_video_connection(self, call_id: str, server_socket: socket.socket):
        """Принятие входящего видео подключения"""
        try:
            logger.info(f"📹 Ожидание видео подключения для звонка {call_id}...")
            
            client_socket, client_addr = server_socket.accept()
            client_socket.settimeout(30.0)
            
            logger.info(f"✅ Видео подключение установлено от {client_addr}")
            
            # Сохраняем клиентский сокет
            self.media_sockets[f"{call_id}_video"] = client_socket
            
            # Закрываем серверный сокет
            server_socket.close()
            
            logger.info(f"✅ Видео соединение для звонка {call_id} полностью установлено")
            
        except socket.timeout:
            logger.error(f"❌ Таймаут ожидания видео подключения для звонка {call_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка принятия видео подключения: {e}")
        finally:
            server_socket.close()

    def _find_free_video_port(self):
        """Найти свободный порт для видео"""
        for port in range(9200, 9300):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('0.0.0.0', port))
                    return port
            except:
                continue
        return None

    def _handle_video_info(self, data: dict, peer_id: str):
        """Обработка информации о видео соединении"""
        try:
            call_id = data.get('call_id')
            video_port = data.get('video_port')
            action = data.get('action')
            
            if call_id and video_port and action == 'setup':
                # Получаем информацию о пире
                if peer_id in self.connected_peers:
                    peer_info = self.connected_peers[peer_id]
                    peer_host = peer_info['address'][0]
                    
                    logger.info(f"📹 Подключение к видео порту {video_port} для звонка {call_id}")
                    
                    # Подключаемся к видео серверу пира
                    video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    video_socket.settimeout(10.0)
                    
                    try:
                        video_socket.connect((peer_host, video_port))
                        video_socket.settimeout(30.0)
                        
                        # Сохраняем сокет
                        self.media_sockets[f"{call_id}_video"] = video_socket
                        
                        logger.info(f"✅ Видео соединение для звонка {call_id} установлено")
                        
                    except Exception as e:
                        logger.error(f"❌ Не удалось подключиться к видео серверу: {e}")
                        video_socket.close()
                        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео информации: {e}")

    def setup_call_connection(self, call_id: str, peer_username: str, is_outgoing: bool) -> socket.socket:
        """Настройка соединения для звонка - создает и возвращает готовый сокет"""
        try:
            logger.info(f"🔊 Настройка соединения для звонка {call_id} (исходящий: {is_outgoing})")
            
            # Ищем информацию о пире
            peer_info = None
            for pid, p_info in list(self.connected_peers.items()):
                if p_info.get('username') == peer_username:
                    peer_info = p_info
                    break
        
            if not peer_info:
                logger.error(f"❌ Пир {peer_username} не найден в подключенных")
                return None
            
            peer_host, _ = peer_info['address']
            
            if is_outgoing:                
                return self._create_outgoing_call_socket(call_id, peer_host, peer_port)
            else:
                # Для входящего звонка: берём порт, который прислал собеседник
                call_info = self.call_requests.get(call_id, {})
                peer_port = call_info.get('peer_port')
                if not peer_port:
                    logger.error(f"❌ Не найден порт собеседника для звонка {call_id}")
                    return None
                return self._connect_to_peer_call(call_id, peer_host, peer_port)        
        except Exception as e:
            logger.error(f"❌ Ошибка настройки соединения для звонка: {e}")
            return None

    def _create_outgoing_call_socket(self, call_id: str, peer_host: str, peer_port: int) -> socket.socket:
        try:
            # Получаем сохранённый локальный порт для этого звонка
            call_info = self.call_requests.get(call_id)
            if not call_info or 'local_port' not in call_info:
                logger.error(f"❌ Нет информации о локальном порте для звонка {call_id}")
                return None

            local_port = call_info['local_port']
            logger.info(f"🔧 [_create_outgoing_call_socket] Звонок {call_id}: создаём серверный сокет на порту {local_port}")

            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', local_port))
            server_socket.listen(1)
            server_socket.settimeout(30.0)

            # Сохраняем серверный сокет в media_sockets
            self.media_sockets[call_id] = server_socket

            # Запускаем поток для ожидания подключения
            threading.Thread(target=self._wait_for_call_connection, args=(call_id, server_socket), daemon=True).start()

            return server_socket

        except Exception as e:
            logger.error(f"❌ [_create_outgoing_call_socket] Звонок {call_id}: ошибка: {e}")
            return None

    def _connect_to_peer_call(self, call_id: str, peer_host: str, peer_port: int) -> socket.socket:
        """Подключение к порту собеседника (используется для входящего звонка)"""
        try:
            logger.info(f"🔧 [_connect_to_peer_call] Звонок {call_id}: подключение к {peer_host}:{peer_port}")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.settimeout(10.0)
            client_socket.connect((peer_host, peer_port))
            client_socket.settimeout(30.0)
            
            # Отправляем подтверждение
            call_info = {'type': 'call_connect', 'call_id': call_id, 'action': 'connect', 'from': self.username}
            client_socket.send(json.dumps(call_info).encode())
            
            # Ждём ответа
            response = client_socket.recv(1024)
            if response:
                resp = json.loads(response.decode())
                if resp.get('status') == 'connected':
                    logger.info(f"✅ [_connect_to_peer_call] Звонок {call_id}: подключение установлено")
                    return client_socket
            
            logger.error(f"❌ [_connect_to_peer_call] Звонок {call_id}: подтверждение не получено")
            client_socket.close()
            return None
        except Exception as e:
            logger.error(f"❌ [_connect_to_peer_call] Звонок {call_id}: ошибка: {e}")
            return None

    def _wait_for_call_connection(self, call_id: str, server_socket: socket.socket):
        """Ожидание входящего подключения для звонка (серверная сторона)"""
        try:
            logger.info(f"🔄 Ожидание подключения для звонка {call_id}...")
            client_socket, client_addr = server_socket.accept()
            client_socket.settimeout(30.0)
            logger.info(f"✅ Подключение для звонка {call_id} установлено от {client_addr}")

            # Получаем информацию о звонке (ожидаем call_connect)
            data = client_socket.recv(1024)
            if data:
                call_info = json.loads(data.decode())
                if call_info.get('type') == 'call_connect':
                    # Отправляем подтверждение
                    response = {'status': 'connected', 'call_id': call_id}
                    client_socket.send(json.dumps(response).encode())
                    # Заменяем серверный сокет на клиентский
                    self.media_sockets[call_id] = client_socket
                    # Закрываем серверный сокет
                    server_socket.close()
                    logger.info(f"✅ Соединение для звонка {call_id} полностью установлено")
                    return

            logger.error(f"❌ Неверные данные подключения для звонка {call_id}")
            client_socket.close()

        except socket.timeout:
            logger.error(f"❌ Таймаут ожидания подключения для звонка {call_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка ожидания подключения: {e}")
        finally:
            if call_id in self.media_sockets and self.media_sockets[call_id] == server_socket:
                del self.media_sockets[call_id]
    
    def get_call_socket(self, call_id: str) -> socket.socket:
        """Получение сокета для звонка"""
        try:
            if call_id in self.media_sockets:
                socket_obj = self.media_sockets[call_id]
                
                # Проверяем, что сокет еще живой
                try:
                    # Для серверных сокетов
                    if hasattr(socket_obj, 'listen'):
                        return socket_obj
                    
                    # Для клиентских сокетов
                    socket_obj.send(b'')
                    return socket_obj
                except:
                    logger.warning(f"⚠️ Сокет для звонка {call_id} не работает")
                    del self.media_sockets[call_id]
                    return None
        
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сокета: {e}")
            return None

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
        """Автоматическое подключение к известным пирам с потокобезопасной блокировкой"""
        try:
            # 1. Блокируем доступ к known_peers и connected_peers на короткое время,
            #    чтобы получить снимок списка пиров, к которым нужно попытаться подключиться.
            with self.peers_lock:
                if not self.known_peers:
                    logger.debug("Нет известных пиров для автоматического подключения")
                    return

                # Сортируем пиры по свежести (более новые – первыми)
                sorted_peers = sorted(
                    self.known_peers,
                    key=lambda x: x.get('discovered_at', 0),
                    reverse=True
                )

                # Берём копию списка, чтобы не держать блокировку во время самих подключений
                peers_to_try = []
                for peer in sorted_peers:
                    host = peer.get('host')
                    port = peer.get('port')
                    if not host or not port:
                        continue
                    # Пропускаем себя и bootstrap узлы
                    if host in ['localhost', '127.0.0.1'] and port == self.listen_port:
                        continue
                    if self._is_bootstrap_node(host, port):
                        continue
                    peer_key = f"{host}:{port}"
                    # Если уже подключены – пропускаем
                    if peer_key in self.connected_peers:
                        continue
                    # Проверяем, не пытались ли подключиться недавно (не чаще раза в минуту)
                    current_time = time.time()
                    last_attempt = peer.get('last_connect_attempt', 0)
                    if current_time - last_attempt < 60:
                        continue
                    # Обновляем время последней попытки прямо в known_peers (под блокировкой)
                    peer['last_connect_attempt'] = current_time
                    peers_to_try.append((host, port))

            # 2. Вне блокировки выполняем фактические подключения (это может быть долго)
            connected_count = 0
            for host, port in peers_to_try:
                logger.info(f"🔄 Автоматическое подключение к пиру {host}:{port}")
                if self._connect_to_peer(host, port):
                    connected_count += 1
                # Ограничиваем количество одновременных попыток (не более 3 за один цикл)
                if connected_count >= 3:
                    break

            if connected_count:
                logger.info(f"✅ Автоматически подключено к {connected_count} пирам")

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
        elif message_type == 'message':
            self._handle_message(data)
        elif message_type == 'user_online':
            self._handle_user_online(data, peer_id)
        elif message_type == 'user_offline':
            self._handle_user_offline(data)
        elif message_type == 'call_request':
            self._handle_call_request(data)
        elif message_type == 'call_response':  
            self._handle_call_response(data)
        elif message_type == 'peer_exchange':  
            self._handle_peer_exchange(data, peer_id)
        elif message_type == 'ping':
            self._handle_ping(data, peer_id)
        elif message_type == 'pong':  
            self._handle_pong(data, peer_id)
        elif message_type == 'peer_discovery':
            self._handle_peer_discovery(data)
        elif message_type == 'media_info':
            self._handle_media_info(data, peer_id)
        elif message_type == 'media_ack':
            logger.info(f"✅ Получено подтверждение медиа-соединения для звонка {data.get('call_id')}")
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

            existing_peer = None
            for pid, pinfo in list(self.connected_peers.items()):
                if pinfo.get('username') == username and pid != peer_id:
                    existing_peer = pid
                    break
        
            # Если нашли дубликат (пользователь с таким именем уже подключен под другим peer_id)
            if existing_peer:
                logger.warning(f"⚠️ Обнаружен дубликат пользователя {username}: {existing_peer} и {peer_id}")
                # Закрываем старое соединение
                try:
                    self.connected_peers[existing_peer]['socket'].close()
                except:
                    pass
                # Удаляем старую запись
                del self.connected_peers[existing_peer]
            
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

    def setup_simple_media_connection(self, call_id: str, peer_username: str) -> bool:
        """Упрощенная установка медиа-соединения"""
        try:
            logger.info(f"🔊 Упрощенная настройка медиа для звонка {call_id} с {peer_username}")
            
            # Создаем простой сокет для звонка
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Находим свободный порт
            call_port = self._find_free_call_port()
            if not call_port:
                logger.error("❌ Не удалось найти свободный порт для звонка")
                return False
        
            # Привязываем сокет
            call_socket.bind(('0.0.0.0', call_port))
            call_socket.listen(1)
            call_socket.settimeout(30.0)
            
            # Сохраняем сокет
            self.media_sockets[call_id] = call_socket
            
            # Сохраняем информацию о звонке
            if call_id not in self.call_requests:
                self.call_requests[call_id] = {}
            
            self.call_requests[call_id]['media_port'] = call_port
            self.call_requests[call_id]['media_socket'] = call_socket
            self.call_requests[call_id]['status'] = 'listening'
            
            logger.info(f"✅ Упрощенное медиа-соединение создано для звонка {call_id} на порту {call_port}")
            
            # Отправляем информацию о порте другому пиру
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == peer_username:
                    target_peer = peer_info
                    break
        
            if target_peer:
                media_info = {
                    'type': 'media_info',
                    'call_id': call_id,
                    'media_port': call_port,
                    'media_host': self.media_server_host,
                    'action': 'simple_setup',
                    'timestamp': time.time()
                }
            
                success = self._send_to_peer(target_peer, media_info)
                if success:
                    logger.info(f"✅ Информация о медиа отправлена пиру {peer_username}")
                else:
                    logger.warning(f"⚠️ Не удалось отправить информацию о медиа пиру {peer_username}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка упрощенной настройки медиа: {e}")
            return False

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
        """Получение списка онлайн пользователей с потокобезопасной блокировкой"""
        try:
            online_users = []
            seen_usernames = set()  # Для отслеживания уникальных имён

            # Блокируем доступ к connected_peers на время чтения
            with self.peers_lock:
                # Итерируем по копии списка ключей, чтобы избежать изменения словаря во время итерации
                for peer_id, peer_info in list(self.connected_peers.items()):
                    try:
                        username = peer_info.get('username')
                        if username and username not in seen_usernames:
                            seen_usernames.add(username)

                            user_data = {
                                'username': username,
                                'host': peer_info['address'][0],
                                'port': peer_info['address'][1],
                                'status': 'connected',
                                'last_seen': peer_info.get('last_seen', time.time()),
                                'peer_id': peer_id
                            }
                            online_users.append(user_data)
                            logger.debug(f"📋 Добавлен в онлайн: {username} ({peer_id})")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки пира {peer_id}: {e}")

            logger.debug(f"📊 get_online_users: {len(online_users)} уникальных пользователей онлайн")
            return online_users

        except Exception as e:
            logger.error(f"💥 Критическая ошибка в get_online_users: {e}")
            return []

    
    # Звонки
    def send_call_request(self, to_username: str, call_type: str) -> str:
        """Отправка запроса на звонок"""
        try:
            call_id = str(uuid.uuid4())

            # Выделяем порт для этого звонка (серверный)
            local_port = self._find_free_call_port()
            if not local_port:
                logger.error(f"❌ Не удалось выделить порт для звонка {call_id}")
                return None

            # Сохраняем информацию о нашем порте
            self.call_requests[call_id] = {
                'to_user': to_username,
                'call_type': call_type,
                'status': 'outgoing',
                'timestamp': time.time(),
                'local_port': local_port   
            }

            # Добавляем информацию о медиа-сервере
            media_info = {
                'media_server': self.media_server_host,  
                'media_port': local_port,
                'call_id': call_id
            }

            
            # Добавляем информацию о медиа-сервере в сообщение
            message = {
                'type': 'call_request',
                'call_id': call_id,
                'from': self.username,
                'to': to_username,
                'call_type': call_type,
                'timestamp': time.time(),
                'media_info': media_info
            }
    
            # Ищем пользователя в подключенных пирах
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == to_username:
                    target_peer = peer_info
                    break
    
            if target_peer:
                if self._send_to_peer(target_peer, message):
                    logger.info(f"📞 Отправлен запрос на звонок {call_id} пользователю {to_username}, порт {local_port}")
                    
                    
                    self.call_requests[call_id] = {
                        'to_user': to_username,
                        'call_type': call_type,
                        'status': 'outgoing',
                        'timestamp': time.time()
                    }
                    
                    self.call_received.emit('outgoing_call', to_username, call_type or 'audio', call_id)
                    return call_id
                else:
                    logger.error(f"❌ Не удалось отправить запрос на звонок пользователю {to_username}")
                    return None
            else:
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

    
    def _handle_call_request(self, data: dict):
        """Обработка входящего запроса на звонок"""
        try:
            call_id = data.get('call_id')
            from_user = data.get('from')
            call_type = data.get('call_type')
            media_info = data.get('media_info', {})
            
            if call_id and from_user:
                logger.info(f"📞 Ответ на звонок {call_id} от {from_user}")
            
                # Сохраняем информацию о звонке
                self.call_requests[call_id] = {
                    'from_user': from_user,
                    'call_type': call_type,
                    'media_info': media_info,
                    'peer_port': media_info.get('media_port'),
                    'status': 'incoming',
                    'timestamp': time.time()
                }

                # Отправляем сигнал в GUI
                self.call_received.emit('incoming_call', from_user, call_type or 'audio', call_id)
            else:
                logger.warning("⚠️ Неполный запрос на звонок")
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки запроса на звонок: {e}")

    def _handle_call_response(self, data: dict):
        """Обработка ответа на звонок"""
        try:
            call_id = data.get('call_id')
            response = data.get('response')
            from_user = data.get('from')
            
            if call_id and response and from_user:
                logger.info(f"📞 Ответ на звонок {call_id} от {from_user}: {response}")
                
                # Отправляем сигнал в GUI
                if response == 'accept':
                    self.call_received.emit('call_accepted', from_user, '', call_id)
                elif response == 'reject':
                    self.call_received.emit('call_rejected', from_user, '', call_id)
                elif response == 'end':
                    self.call_received.emit('call_ended', from_user, '', call_id)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа на звонок: {e}")

    def get_call_socket(self, call_id: str):
        """Получение сокета для звонка (обертка для get_media_socket)"""
        try:
            logger.info(f"🔧 P2PNetworkClient.get_call_socket: Получение сокета для звонка {call_id}")
            
            # Пробуем получить медиа-сокет
            media_socket = self.get_media_socket(call_id)
            
            if media_socket:
                logger.info(f"✅ Получен медиа-сокет для звонка {call_id}")
                return media_socket
            
            # Если медиа-сокета нет, создаем временный сокет для тестирования
            logger.info(f"🔄 Создание временного сокета для звонка {call_id}")
            
            # Создаем простой TCP сокет
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            temp_socket.settimeout(30.0)
            
            # Находим свободный порт
            temp_port = self._find_free_call_port()
            if temp_port:
                try:
                    temp_socket.bind(('0.0.0.0', temp_port))
                    temp_socket.listen(1)
                    logger.info(f"✅ Создан временный сокет для звонка {call_id} на порту {temp_port}")
                    
                    # Сохраняем для последующего использования
                    if call_id not in self.media_sockets:
                        self.media_sockets[call_id] = temp_socket
                    
                    return temp_socket
                except Exception as e:
                    logger.error(f"❌ Ошибка создания временного сокета: {e}")
                    temp_socket.close()
            else:
                logger.error("❌ Не удалось найти свободный порт для временного сокета")
                temp_socket.close()
            
            return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка получения сокета для звонка: {e}")
            return None
    
    def setup_media_connection(self, call_id: str, peer_username: str) -> bool:
        """Установка медиа-соединения для звонка через медиа-сервер"""
        try:
            logger.info(f"🔊 Установка медиа-соединения для звонка {call_id} с {peer_username}")
            
            # Ищем пира по имени пользователя
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == peer_username:
                    target_peer = peer_info
                    break
            
            if not target_peer:
                logger.error(f"❌ Пир {peer_username} не найден в подключенных")
                return False
        

            # Создаем серверный сокет для медиа-данных
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Находим свободный порт для медиа
            media_port = self._find_free_call_port()
            if not media_port:
                logger.error("❌ Не удалось найти свободный порт для медиа")
                return False
        
            try:
                server_socket.bind(('0.0.0.0', media_port))
                server_socket.listen(1)
                server_socket.settimeout(10.0)  # Таймаут ожидания подключения
                
                logger.info(f"🔊 Медиа-сервер запущен на порту {media_port} для звонка {call_id}")
            
            except Exception as e:
                logger.error(f"❌ Ошибка запуска медиа-сервера: {e}")
                server_socket.close()
                return False

            # Сохраняем информацию о медиа-соединении
            self.media_connections[call_id] = {
                'server_socket': server_socket,
                'port': media_port,
                'peer_username': peer_username,
                'status': 'listening',
                'connected_at': time.time()
            }

            # Сохраняем сокет для быстрого доступа
            self.media_sockets[call_id] = server_socket

            # Отправляем информацию о медиа-порте другому пиру
            media_info_msg = {
                'type': 'media_info',
                'call_id': call_id,
                'media_port': media_port,
                'media_host': self.media_server_host,
                'action': 'setup',
                'timestamp': time.time()
            }

            # Отправляем через существующее соединение
            success = self._send_to_peer(target_peer, media_info_msg)
            
            if success:
                logger.info(f"✅ Информация о медиа-порте {media_port} отправлена пиру {peer_username}")

                # Запускаем поток для принятия входящего медиа-соединения
                accept_thread = threading.Thread(
                    target=self._accept_media_connection,
                    args=(call_id, server_socket),
                    daemon=True
                )
                accept_thread.start()
                
                return True
            else:
                logger.error(f"❌ Не удалось отправить информацию о медиа-порте")
                if call_id in self.media_connections:
                    del self.media_connections[call_id]
                if call_id in self.media_sockets:
                    del self.media_sockets[call_id]
                return False
 
        except Exception as e:
            logger.error(f"❌ Критическая ошибка настройки медиа-соединения: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            return False
           
    def _handle_media_data(self, call_id: str, media_socket: socket.socket):
        """Обработка данных от медиа-сервера"""
        try:
            logger.info(f"🔊 Начало обработки медиа-данных для звонка {call_id}")
            
            while call_id in self.media_sockets and self.is_running:
                try:
                    # Читаем данные с таймаутом
                    media_socket.settimeout(1.0)
                    data = media_socket.recv(4096)
                    
                    if not data:
                        logger.info(f"🔌 Соединение с медиа-сервером для звонка {call_id} закрыто")
                        break
                    
                    # Для тестирования просто логируем полученные данные
                    logger.debug(f"📨 Получено {len(data)} байт медиа-данных для звонка {call_id}")
                    
                    # В реальном приложении здесь была бы обработка аудио
                    # Например, добавление в буфер для воспроизведения
                    
                except socket.timeout:
                    continue  # Таймаут - продолжаем
                except ConnectionResetError:
                    logger.info(f"🔌 Соединение с медиа-сервером для звонка {call_id} разорвано")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка чтения медиа-данных: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в обработчике медиа-данных: {e}")
        finally:
            # Очищаем соединение
            self.close_media_connection(call_id)    

    def _accept_media_connection(self, call_id: str, server_socket: socket.socket):
        """Принятие входящего медиа-соединения"""
        try:
            logger.info(f"🔊 Ожидание медиа-подключения для звонка {call_id}...")
            
            client_socket, client_addr = server_socket.accept()
            client_socket.settimeout(30.0)
            
            logger.info(f"✅ Медиа-подключение установлено для звонка {call_id} от {client_addr}")
            
            # Сохраняем клиентский сокет
            if call_id in self.media_connections:
                self.media_connections[call_id]['client_socket'] = client_socket
                self.media_connections[call_id]['status'] = 'connected'
                self.media_connections[call_id]['connected_at'] = time.time()
                self.media_connections[call_id]['client_addr'] = client_addr
                
                # Отправляем подтверждение
                ack_msg = {'type': 'media_ack', 'call_id': call_id, 'status': 'connected'}
                client_socket.send(json.dumps(ack_msg).encode())
                
                logger.info(f"✅ Медиа-соединение для звонка {call_id} полностью установлено")
            else:
                logger.warning(f"⚠️ Медиа-соединение {call_id} не найдено, закрываем сокет")
                client_socket.close()
                
        except socket.timeout:
            logger.warning(f"⚠️ Таймаут ожидания медиа-подключения для звонка {call_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка принятия медиа-соединения: {e}")
        finally:
            server_socket.close()

    def connect_to_media(self, call_id: str, media_port: int, peer_host: str) -> bool:
        """Подключение к медиа-серверу другого пира"""
        try:
            logger.info(f"🔊 Подключение к медиа-серверу {peer_host}:{media_port} для звонка {call_id}")
            
            # Создаем клиентский сокет
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10.0)
            
            try:
                client_socket.connect((peer_host, media_port))
                client_socket.settimeout(30.0)
                
                logger.info(f"✅ Успешное подключение к медиа-серверу для звонка {call_id}")
                
            except ConnectionRefusedError:
                logger.error(f"❌ Не удалось подключиться к медиа-серверу {peer_host}:{media_port}")
                client_socket.close()
                return False
        
            # Сохраняем сокет
            self.media_connections[call_id] = {
                'client_socket': client_socket,
                'peer_host': peer_host,
                'media_port': media_port,
                'status': 'connected',
                'connected_at': time.time()
            }
        
            # Ждем подтверждения от сервера
            try:
                data = client_socket.recv(1024)
                if data:
                    ack = json.loads(data.decode())
                    if ack.get('type') == 'media_ack' and ack.get('status') == 'connected':
                        logger.info(f"✅ Получено подтверждение медиа-соединения для звонка {call_id}")
                        return True
            except:
                logger.warning(f"⚠️ Не получено подтверждение медиа-соединения, продолжаем...")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к медиа-серверу: {e}")
            return False
    
    def get_media_socket(self, call_id: str):
        """Получение медиа-сокета для звонка"""
        try:
            if call_id in self.media_connections:
                media_info = self.media_connections[call_id]
                
                # Возвращаем клиентский сокет (если мы подключались)
                if 'client_socket' in media_info and media_info['client_socket']:
                    socket_obj = media_info['client_socket']
                    # Проверяем, что сокет еще живой
                    try:
                        socket_obj.send(b'')
                        return socket_obj
                    except:
                        logger.warning(f"⚠️ Медиа-сокет для звонка {call_id} мертв")
                        return None
                
                # Или возвращаем серверный сокет (если мы слушали)
                elif 'server_socket' in media_info and media_info['server_socket']:
                    logger.info(f"🔊 Возвращаем серверный сокет для звонка {call_id}")
                    return media_info['server_socket']
                    
            logger.warning(f"⚠️ Медиа-соединение для звонка {call_id} не найдено")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения медиа-сокета: {e}")
            return None

    def _find_free_call_port(self):
        """Найти свободный порт для звонка"""
        for port in range(9100, 9500):
            if port not in self.media_ports:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(('0.0.0.0', port))
                        # Добавляем порт в отслеживаемые
                        if not hasattr(self, 'media_ports'):
                            self.media_ports = set()
                        self.media_ports.add(port)
                        return port
                except:
                    continue
        return None

    def _handle_media_info(self, data: dict, peer_id: str):
        try:
            call_id = data.get('call_id')
            media_port = data.get('media_port')
            media_host = data.get('media_host')   # теперь получаем IP
            action = data.get('action')
            
            if not call_id or not media_port:
                logger.warning("⚠️ Неполная информация о медиа-соединении")
                return
            
            if action == 'setup':
                # Если media_host не передан, используем адрес пира (обратная совместимость)
                if not media_host and peer_id in self.connected_peers:
                    media_host = self.connected_peers[peer_id]['address'][0]
                
                if not media_host:
                    logger.error(f"❌ Не удалось определить media_host для звонка {call_id}")
                    return
                
                logger.info(f"🔊 Получена информация о медиа: {media_host}:{media_port} для звонка {call_id}")
                
                # Сохраняем информацию о медиа-соединении
                self.call_requests[call_id] = {
                    'media_port': media_port,
                    'media_host': media_host,
                    'peer_id': peer_id,
                    'status': 'pending'
                }
            
                # Отправляем сигнал в GUI для подключения к медиа
                self.call_received.emit('media_info', media_host, str(media_port), call_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки медиа-информации: {e}")

    def close_media_connection(self, call_id: str):
        """Закрытие медиа-соединения для звонка"""
        logger.info(f"🔊 close_media_connection: call_id={call_id}")
        """Закрытие медиа-соединения для звонка"""
        try:
            if call_id in self.media_sockets:
                media_socket = self.media_sockets[call_id]
                if media_socket:
                    try:
                        # Отправляем сообщение о завершении звонка
                        end_data = {'call_id': call_id, 'action': 'end'}
                        media_socket.send(json.dumps(end_data).encode())
                    except:
                        pass

                    # Закрываем сокет
                    media_socket.close()
                    logger.info(f"🔌 Медиа-соединение для звонка {call_id} закрыто")
                    if call_id in self.media_connections:
                        del self.media_connections[call_id]
                    if call_id in self.call_requests:
                        del self.call_requests[call_id]

                # Удаляем из словарей
                del self.media_sockets[call_id]

        except Exception as e:
            logger.error(f"❌ Ошибка закрытия медиа-соединения: {e}")

    @property
    def connected(self):
        """Свойство для обратной совместимости"""
        return self.is_running
