import os
import sys
import asyncio
import socket
import threading
import base64
import secrets   
import hashlib   
import hmac
import time
import uuid
import logging
import logging.handlers
import socket
import random
import json
from typing import Dict, List, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal, QSettings, QStandardPaths
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer


# Добавляем путь к текущей директории для импорта модулей
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
try:
    from core.crypto import CryptoManager
    from core.secure_channel import SecureChannel
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все файлы находятся в правильной структуре папок")
    sys.exit(1)


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

def _find_free_call_port(self):
    """Найти свободный порт для звонка (аудио/видео)"""
    if not hasattr(self, 'media_ports'):
        self.media_ports = set()
    for port in range(9100, 9500):
        if port in self.media_ports:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', port))
                self.media_ports.add(port)
                return port
        except OSError:
            continue
    return None

def _release_call_port(self, port):
    if hasattr(self, 'media_ports') and port in self.media_ports:
        self.media_ports.remove(port)


class P2PNetworkClient(QObject):
    """P2P сетевой клиент для мессенджера Диалог с полным обменом пирами"""
    
    # Сигналы для GUI
    message_received = pyqtSignal(str, str)  # from_user, message
    user_list_updated = pyqtSignal(list)
    connection_status_changed = pyqtSignal(str)
    call_received = pyqtSignal(str, str, str, str)  # action, username, call_type, call_id
    video_socket_ready = pyqtSignal(str, object)
    file_received = pyqtSignal(str, str)  # from_username, save_path
    file_progress = pyqtSignal(str, int, int)  # file_id, sent_bytes, total_bytes
    
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
        self.active_audio_calls = {}  # call_id -> peer_id
        self.media_ports = set()  # Для отслеживания используемых медиа-портов
        self.peer_crypto = {}  # peer_id -> CryptoManager
        self.webrtc_connections = {}  # peer_id -> RTCPeerConnection
        self.webrtc_channels = {}      # peer_id -> RTCDataChannel
        self.webrtc_loop = None        # asyncio event loop в отдельном потоке
        self.webrtc_thread = None
        
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
        self.active_file_transfers = {}  # file_id -> transfer_info
        self.settings = QSettings('DialogApp', 'P2PClient')

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

            # Инициализируем asyncio event loop в отдельном потоке
            self.webrtc_loop = None
            self.webrtc_thread = threading.Thread(target=self._start_webrtc_loop, daemon=True)
            self.webrtc_thread.start()
        
            logger.info(f"🚀 Клиент запущен на порту {self.listen_port}")
            self.connection_status_changed.emit("✅ Сеть запущена")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка запуска клиента: {e}")
            self.connection_status_changed.emit("❌ Ошибка запуска сети")
            return False

    def stop(self):
        """Остановка P2P клиента"""
        self.is_running = False
        
        # Закрываем слушающий сокет, чтобы не принимать новые подключения
        if self.listener_socket:
            try:
                self.listener_socket.close()
            except:
                pass

        # Отправляем уведомление о выходе всем пирам (используем копию ключей)
        offline_msg = {'type': 'user_offline', 'username': self.username}
        
        # Итерируемся по копии списка ключей, чтобы избежать изменения словаря во время итерации
        for peer_id in list(self.connected_peers.keys()):
            peer_info = self.connected_peers.get(peer_id)
            if peer_info:
                # Пытаемся отправить сообщение, но игнорируем ошибки (пир уже мог отключиться)
                self._send_to_peer(peer_info, offline_msg)
                # Закрываем сокет пира
                try:
                    peer_info['socket'].close()
                except:
                    pass
    
        # Очищаем словарь подключённых пиров
        self.connected_peers.clear()
        
        # Сохраняем известные пиры в БД (если нужно)
        self._save_known_peers()
        
        logger.info("P2P клиент остановлен")

    def _start_webrtc_loop(self):
        """Запускает asyncio event loop для WebRTC в отдельном потоке"""
        self.webrtc_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.webrtc_loop)
        self.webrtc_loop.run_forever()

    def _run_coro(self, coro):
        """Запустить корутину в webrtc_loop и дождаться результата (блокирующий вызов из синхронного кода)"""
        if not self.webrtc_loop:
            raise RuntimeError("WebRTC loop not running")
        future = asyncio.run_coroutine_threadsafe(coro, self.webrtc_loop)
        return future.result(timeout=10)

    async def _create_webrtc_offer(self, peer_id: str, peer_info: dict):
        """Создать offer для установки WebRTC-соединения с пиром"""
        from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
        
        # Конфигурация ICE из config.yaml
        ice_servers = []
        for srv in self.config.get('media', {}).get('ice_servers', []):
            ice_servers.append(RTCIceServer(urls=srv['urls']))
        
        config = RTCConfiguration(iceServers=ice_servers)
        pc = RTCPeerConnection(configuration=config)
        
        # Создаём DataChannel для обмена сообщениями (поверх WebRTC)
        channel = pc.createDataChannel("dialog")
        
        @channel.on("open")
        def on_open():
            logger.info(f"✅ WebRTC DataChannel открыт с {peer_id}")
            # После открытия канала можно отправить приветствие или сразу использовать
            pass
    
        @channel.on("message")
        def on_message(message):
            # message – это bytes (или str). Здесь уже будет ваше зашифрованное сообщение.
            # Обрабатываем так же, как в _process_received_data
            try:
                if isinstance(message, bytes):
                    data = json.loads(message.decode('utf-8'))
                else:
                    data = json.loads(message)
                # Имитируем получение от этого же peer_id
                self._process_received_data(data, peer_id)
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения из WebRTC: {e}")
        
        # Генерируем offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Сохраняем pc и channel
        self.webrtc_connections[peer_id] = pc
        self.webrtc_channels[peer_id] = channel
        
        return pc.localDescription

    async def _handle_webrtc_answer(self, peer_id: str, answer_sdp: str, answer_type: str):
        """Установить answer от пира"""
        pc = self.webrtc_connections.get(peer_id)
        if not pc:
            logger.error(f"Нет WebRTC соединения для {peer_id}")
            return
        answer = RTCSessionDescription(sdp=answer_sdp, type=answer_type)
        await pc.setRemoteDescription(answer)
    
    def _initiate_webrtc_connection(self, peer_id: str, peer_info: dict):
        """Инициирует WebRTC соединение с пиром (отправляет offer)"""
        from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

        # Загружаем STUN/TURN серверы из config (или ставим по умолчанию)
        ice_servers = []
        # Если у вас есть config с секцией media.ice_servers, используйте её
        # Для примера – публичные STUN
        ice_servers.append(RTCIceServer(urls=["stun:stun.l.google.com:19302"]))
        # Можно добавить TURN позже

        config = RTCConfiguration(iceServers=ice_servers)
        pc = RTCPeerConnection(configuration=config)

        # Создаём DataChannel для обмена сообщениями (он будет открыт автоматически)
        channel = pc.createDataChannel("dialog")

        @channel.on("open")
        def on_open():
            logger.info(f"✅ WebRTC DataChannel открыт с {peer_id}")

        @channel.on("message")
        def on_message(message):
            # Обработка входящего сообщения (уже расшифровано DTLS, но ваше E2E ещё поверх)
            try:
                if isinstance(message, bytes):
                    data = json.loads(message.decode('utf-8'))
                else:
                    data = json.loads(message)
                self._process_received_data(data, peer_id)
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения из WebRTC: {e}")

        # Асинхронно создаём offer и устанавливаем local description
        async def create_offer():
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            return pc.localDescription

        offer_desc = self._run_coro(create_offer())

        # Сохраняем объекты
        self.webrtc_connections[peer_id] = pc
        self.webrtc_channels[peer_id] = channel   # канал пока не открыт, но объект есть

        # Отправляем offer через существующий TCP-канал
        signal_msg = {
            'type': 'webrtc_offer',
            'sdp': offer_desc.sdp,
            'sdp_type': offer_desc.type,   # обычно "offer"
            'peer_id': peer_id
        }
        if self._send_to_peer(peer_info, signal_msg):
            logger.info(f"📤 WebRTC offer отправлен {peer_id}")
        else:
            logger.error(f"Не удалось отправить offer {peer_id}")

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
        """Установка имени пользователя (вызывается после логина)"""
        self.username = username
        logger.info(f"Установлено имя пользователя: {username}")
        with self.peers_lock:
            for peer_id in list(self.connected_peers.keys()):
                self._send_self_info(peer_id)
  
    def broadcast_self_info(self):
        """Разослать информацию о себе всем подключённым пирам"""
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
                    'client_version': '1.0.0',
                    'listen_port': self.listen_port
                }
        
                self._send_to_peer(self.connected_peers[peer_id], self_info)
                logger.debug(f"Отправлена информация о себе пиру {peer_id}: {self.username}")
        
        except Exception as e:
            logger.error(f"Ошибка отправки информации о себе: {e}")

    def _handle_webrtc_offer(self, data: dict, peer_id: str):
        """Приём offer от пира, создание answer"""
    
        offer_sdp = data['sdp']
        offer_type = data['sdp_type']   # "offer"
        offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)

        ice_servers = [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
        config = RTCConfiguration(iceServers=ice_servers)
        pc = RTCPeerConnection(configuration=config)

        # Обработчик входящего DataChannel (создаётся автоматически, когда remote создаст канал)
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"📡 Входящий DataChannel от {peer_id}, label={channel.label}")
            self.webrtc_channels[peer_id] = channel

            @channel.on("message")
            def on_message(message):
                try:
                    if isinstance(message, bytes):
                        data = json.loads(message.decode())
                    else:
                        data = json.loads(message)
                    self._process_received_data(data, peer_id)
                except Exception as e:
                    logger.error(f"Ошибка обработки сообщения из WebRTC: {e}")

        # Устанавливаем remote description (offer)
        async def set_remote():
            await pc.setRemoteDescription(offer)
            return await pc.createAnswer()

        answer_desc = self._run_coro(set_remote())

        # Устанавливаем local description (answer)
        async def set_local():
            await pc.setLocalDescription(answer_desc)

        self._run_coro(set_local())

        # Сохраняем peer connection
        self.webrtc_connections[peer_id] = pc

        # Отправляем answer обратно через существующий TCP-канал
        peer_info = self.connected_peers.get(peer_id)
        if peer_info:
            answer_msg = {
                'type': 'webrtc_answer',
                'sdp': pc.localDescription.sdp,
                'sdp_type': pc.localDescription.type,   # "answer"
                'peer_id': peer_id
            }
            self._send_to_peer(peer_info, answer_msg)
            logger.info(f"📤 WebRTC answer отправлен {peer_id}")
        else:
            logger.error(f"Пир {peer_id} не найден для отправки answer")
    
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

    def get_peers_list(self) -> List[Dict]:
        """Возвращает список подключённых пиров для отображения в интерфейсе."""
        peers = []
        for peer_id, peer_info in self.connected_peers.items():
            peers.append({
                'id': peer_id,
                'address': f"{peer_info['address'][0]}:{peer_info['address'][1]}",
                'username': peer_info.get('username', 'unknown'),
                'connected_at': peer_info.get('connected_at')
            })
        return peers

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
                    'username': None,
                    'secure_mode': False
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
        if not self.username:
            logger.debug("Имя пользователя не задано, пропускаем отправку user_online")
            return       
        try:
            if peer_id not in self.connected_peers:
                return
            
            self_info = {
                'type': 'user_online',
                'username': self.username,
                'timestamp': time.time(),
                'client_version': '1.0.0',
                'listen_port': self.listen_port
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
        bootstrap_update_interval = 120  # 5 минут - обновляем bootstrap реже
        auto_connect_interval = 15
        user_list_update_interval = 15  # 15 секунд
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
        """Проверка активности подключенных пиров и удаление неактивных."""
        current_time = time.time()
        disconnected_peers = []

        # Копируем список пиров под блокировкой
        with self.peers_lock:
            peers_copy = list(self.connected_peers.items())

        for peer_id, peer_info in peers_copy:
            last_seen = peer_info.get('last_seen', 0)
            username = peer_info.get('username', 'unknown')
            idle_time = current_time - last_seen

            # 1. Если у пира ещё нет имени (ещё не получили user_online) и прошло >30 секунд – удаляем
            if username == 'unknown' and idle_time > 30:
                logger.info(f"🔌 Удаляем пира {peer_id} без имени (не ответил, {idle_time:.0f} сек)")
                disconnected_peers.append(peer_id)
                continue

            # 2. Основной таймаут – 60 секунд бездействия
            if idle_time > 60:
                # Проверяем, есть ли активный звонок, использующий этого пира
                call_active = any(peer_id == active_peer for active_peer in self.active_audio_calls.values())
                if not call_active:
                    logger.info(f"🔌 Пир {username} ({peer_id}) отключен по таймауту ({idle_time:.0f} сек)")
                    disconnected_peers.append(peer_id)
                else:
                    logger.debug(f"Пир {peer_id} участвует в активном звонке – не отключаем")
            else:
                # Обновляем last_seen для активного пира (чтобы не отключался)
                peer_info['last_seen'] = current_time
                # Периодически шлём ping, если давно не было активности (15 секунд)
                if idle_time > 15:
                    try:
                        ping_data = {'type': 'ping', 'timestamp': current_time}
                        if not self._send_to_peer(peer_info, ping_data):
                            logger.info(f"🔌 Не удалось отправить ping пиру {username} ({peer_id})")
                            disconnected_peers.append(peer_id)
                    except Exception as e:
                        logger.warning(f"🔌 Ошибка ping пиру {username}: {e}")
                        disconnected_peers.append(peer_id)

        # Удаляем отключившихся пиров
        for peer_id in disconnected_peers:
            self._handle_peer_disconnection(peer_id)

    def _handle_peer_disconnection(self, peer_id: str):
        """Обработка отключения пира"""
        with self.peers_lock:
            if peer_id not in self.connected_peers:
                return
            peer_info = self.connected_peers[peer_id]
            username = peer_info.get('username', 'unknown')

            if peer_id in self.active_audio_calls.values():
                logger.warning(f"Пир {peer_id} участвует в активном звонке – не удаляем")
                return
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
        """Настройка видео соединения (серверная часть)"""
        try:
            logger.info(f"📹 Настройка видео соединения для звонка {call_id}")
            
            # Получаем сохранённый видео порт (выделенный при отправке запроса)
            call_info = self.call_requests.get(call_id, {})
            video_port = call_info.get('video_local_port')
            if not video_port:
                logger.error(f"❌ Не найден видео порт для звонка {call_id}")
                return None
            
            # Создаём серверный сокет на этом порту
            video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            try:
                video_socket.bind(('0.0.0.0', video_port))
                video_socket.listen(1)
                video_socket.settimeout(10.0)
                logger.info(f"📹 Видео сервер запущен на порту {video_port}")
                
                # Запускаем поток для принятия подключения
                threading.Thread(
                    target=self._accept_video_connection,
                    args=(call_id, video_socket),
                    daemon=True
                ).start()
                
                return video_socket
            except Exception as e:
                logger.error(f"❌ Ошибка запуска видео сервера на порту {video_port}: {e}")
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
            secure = self._perform_media_key_exchange(client_socket, initiator=False)
            self.media_sockets[f"{call_id}_video"] = secure

            # ОТПРАВЛЯЕМ СИГНАЛ, ЧТО КЛИЕНТСКИЙ СОКЕТ ГОТОВ
            self.video_socket_ready.emit(call_id, secure)
            
            # Закрываем серверный сокет
            server_socket.close()
            
            logger.info(f"✅ Видео соединение для звонка {call_id} полностью установлено")
            
        except socket.timeout:
            logger.error(f"❌ Таймаут ожидания видео подключения для звонка {call_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка принятия видео подключения: {e}")
        finally:
            try:
                server_socket.close()
            except:
                pass

    def wait_for_call_socket(self, call_id: str, timeout=10.0):
        """Ожидание появления клиентского сокета для звонка (после установки соединения)"""
        start = time.time()
        while time.time() - start < timeout:
            if call_id in self.media_sockets:
                sock = self.media_sockets[call_id]
                # Проверяем, что сокет не серверный (не слушает) и подключён
                if self._is_client_socket(sock):
                    return sock           
            time.sleep(0.2)
        return None

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
                        secure = self._perform_media_key_exchange(video_socket, initiator=True)
                        self.media_sockets[f"{call_id}_video"] = secure
                        
                        logger.info(f"✅ Видео соединение для звонка {call_id} установлено")
                        
                    except Exception as e:
                        logger.error(f"❌ Не удалось подключиться к видео серверу: {e}")
                        video_socket.close()
                        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео информации: {e}")

    def setup_call_connection(self, call_id: str, peer_username: str, is_outgoing: bool):
        """
        Устанавливает медиа-соединение для звонка.
        Для исходящего звонка ожидает готовый клиентский сокет (уже SecureChannel),
        для входящего – подключается к медиа-серверу собеседника, выполняет обмен ключами.
        Возвращает защищённый канал или None при ошибке.
        """
        try:
            logger.info(f"🔊 Установка медиа-соединения для звонка {call_id}, исходящий: {is_outgoing}")

            # === Исходящий звонок ===
            if is_outgoing:
                start_time = time.time()
                timeout = 10.0  # до 10 секунд на ожидание подключения собеседника
                while time.time() - start_time < timeout:
                    sock = self.media_sockets.get(call_id)
                    # Теперь _is_client_socket понимает SecureChannel
                    if self._is_client_socket(sock):
                        logger.info(f"✅ Найден готовый клиентский сокет для исходящего звонка {call_id}")
                        return sock
                    time.sleep(0.2)
                logger.error(f"❌ Таймаут ожидания клиентского сокета для исходящего звонка {call_id}")
                return None

            # === Входящий звонок ===
            # 1. Найти информацию о пире по username
            target_peer = None
            for peer_id, pinfo in self.connected_peers.items():
                if pinfo.get('username') == peer_username:
                    target_peer = pinfo
                    break

            if not target_peer:
                logger.error(f"❌ Пир {peer_username} не найден в подключённых")
                return None

            # 2. Получить данные о медиа-сервере собеседника из call_requests
            call_info = self.call_requests.get(call_id)
            if not call_info:
                logger.error(f"❌ Нет информации о входящем звонке {call_id}")
                return None

            peer_host = call_info.get('media_host') or call_info.get('peer_host')
            peer_port = call_info.get('media_port') or call_info.get('peer_port')
            if not peer_host or not peer_port:
                logger.error(f"❌ Неизвестен адрес или порт медиа для звонка {call_id}")
                return None

            # 3. Подключиться к медиа-серверу собеседника
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10.0)
            try:
                client_socket.connect((peer_host, peer_port))
                client_socket.settimeout(30.0)
                logger.info(f"✅ Подключение к медиа {peer_host}:{peer_port} для звонка {call_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка подключения к медиа: {e}")
                client_socket.close()
                return None

            

            # 5. Обмен ключами – клиентская сторона (initiator=True)
            try:
                secure = self._perform_media_key_exchange(client_socket, initiator=True)   
            except Exception as e:
                logger.error(f"❌ Ошибка обмена ключами: {e}")
                client_socket.close()
                return None

            
            # Сохраняем защищённый канал
            self.media_sockets[call_id] = secure

            # Привязываем звонок к активным аудиовызовам
            peer_id = f"{peer_host}:{peer_port}"
            if call_id not in self.active_audio_calls:
                self.active_audio_calls[call_id] = peer_id

            logger.info(f"✅ Медиа-соединение для входящего звонка {call_id} готово")
            return secure

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в setup_call_connection: {e}")
            return None

    def _is_client_socket(self, sock):
        """Проверяет, что сокет жив, не является слушающим (серверным), в том числе SecureChannel."""
        if sock is None:
            return False
        # Защищённый канал всегда считается активным клиентским сокетом
        if isinstance(sock, SecureChannel):
            return True
        try:
            if sock.fileno() == -1:
                return False
        except:
            return False
        try:
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
                return False
        except:
            return False
        return True

    def _derive_key(self, master_key: bytes, context: str) -> bytes:
        """
        Выводит производный ключ из мастер-ключа с использованием HKDF или HMAC-SHA256.
        context – уникальная строка для каждого канала (например, "audio_call_id" или "video_call_id").
        """
        import hmac, hashlib
        # Простой вариант: HMAC(master_key, context) -> 32 байта
        return hmac.new(master_key, context.encode('utf-8'), hashlib.sha256).digest()[:32]

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
            peer_id = f"{peer_host}:{peer_port}"
            self.active_audio_calls[call_id] = peer_id
            
            return server_socket

           
        except Exception as e:
            logger.error(f"❌ [_create_outgoing_call_socket] Звонок {call_id}: ошибка: {e}")
            return None

    def _connect_to_peer_call(self, call_id: str, peer_host: str, peer_port: int) -> socket.socket:
        for attempt in range(5):
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(5.0)
                client_socket.connect((peer_host, peer_port))
                client_socket.settimeout(30.0)

                msg = {'type': 'call_connect', 'call_id': call_id, 'action': 'connect', 'from': self.username}
                client_socket.send(json.dumps(msg).encode())

                resp_data = client_socket.recv(1024)
                if resp_data:
                    resp = json.loads(resp_data.decode())
                    if resp.get('status') == 'connected' and resp.get('call_id') == call_id:
                        logger.info(f"✅ Соединение для звонка {call_id} установлено")
                        peer_id = f"{peer_host}:{peer_port}"
                        self.active_audio_calls[call_id] = peer_id
                        return client_socket

                client_socket.close()
            except Exception as e:
                logger.warning(f"Попытка {attempt+1} не удалась: {e}")
            time.sleep(1)
        return None

    def _wait_for_call_connection(self, call_id: str, server_socket: socket.socket):
        attempts = 0
        max_attempts = 10
        try:
            server_socket.settimeout(0.5)   # неблокирующий режим для цикла
            while attempts < max_attempts and self.is_running:
                try:
                    client_socket, client_addr = server_socket.accept()
                    client_socket.settimeout(30.0)
                    logger.info(f"✅ Подключение для звонка {call_id} от {client_addr}")

                    # Ждём call_connect
                    data = client_socket.recv(1024)
                    if data:
                        call_info = json.loads(data.decode())
                        if call_info.get('type') == 'call_connect' and call_info.get('call_id') == call_id:
                            response = {'status': 'connected', 'call_id': call_id}
                            client_socket.send(json.dumps(response).encode())
                            # Заменяем серверный сокет на клиентский
                            secure = self._perform_media_key_exchange(client_socket, initiator=False)
                            self.media_sockets[call_id] = secure
                            server_socket.close()
                            logger.info(f"✅ Соединение для звонка {call_id} полностью установлено")
                            return
                    client_socket.close()
                except socket.timeout:
                    pass
                except BlockingIOError:
                    time.sleep(0.1)
                attempts += 1
                time.sleep(0.5)

            logger.error(f"❌ Не удалось установить соединение для звонка {call_id}")
            if call_id in self.media_sockets:
                del self.media_sockets[call_id]
        except Exception as e:
            logger.error(f"❌ Ошибка ожидания подключения: {e}")
        finally:
            server_socket.close()
            # Освобождаем порт
            if call_id in self.call_requests and 'local_port' in self.call_requests[call_id]:
                self._release_call_port(self.call_requests[call_id]['local_port'])

    def get_call_socket(self, call_id: str):
        """Получение сокета для звонка (только уже установленный клиентский)"""
        try:
            logger.info(f"🔧 P2PNetworkClient.get_call_socket: Получение сокета для звонка {call_id}")           
            if call_id in self.media_sockets:
                socket_obj = self.media_sockets[call_id]
                # Проверяем, что это клиентский сокет (не серверный) и жив
                if self._is_client_socket(socket_obj):
                    return socket_obj       
            return None   # клиентский сокет ещё не готов
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
    
        # Для сообщений и звонков – проверяем чёрный список (если есть имя отправителя)
        from_user = data.get('from') or data.get('username')
        if from_user and self.db and self.db.is_blocked(from_user):
            logger.info(f"🚫 Игнорируем сообщение/звонок от заблокированного пользователя {from_user}")
            # Для звонка можно отправить автоматический reject
            if message_type == 'call_request':
                call_id = data.get('call_id')
                if call_id:
                    self.send_call_response(call_id, 'reject')
            return

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
        elif message_type == 'file_request':
            self._handle_file_request(data, peer_id)
        elif message_type == 'file_chunk':
            self._handle_file_chunk(data, peer_id)
        elif message_type == 'file_complete':
            self._handle_file_complete(data, peer_id)
        elif message_type == 'file_ack':
            self._handle_file_ack(data, peer_id)
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
        elif message_type == 'webrtc_offer':
            self._handle_webrtc_offer(data, peer_id)
        elif message_type == 'webrtc_answer':
            self._handle_webrtc_answer(data, peer_id)
        elif message_type == 'media_ack':            
            logger.info(f"✅ Получено подтверждение медиа-соединения для звонка {data.get('call_id')}")
        else:
            logger.warning(f"Неизвестный тип сообщения: {message_type}")

    def send_message(self, to_username: str, message: str, message_id: str = None) -> bool:
        try:
            if not message_id:
                import uuid
                message_id = str(uuid.uuid4())

            # Ищем ВСЕХ пиров с таким же именем пользователя
            candidates = []
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == to_username:
                    candidates.append((peer_id, peer_info))

            if not candidates:
                logger.warning(f"⚠️ Пользователь {to_username} не найден в подключенных пирах")
                return False

            message_data = {
                    'type': 'message',
                    'from': self.username,
                    'to': to_username,
                    'message': message,
                    'message_id': message_id,
                    'timestamp': time.time(),
                    'requires_ack': True
                }

            # Внутри send_message, после поиска кандидатов
            # Сначала пробуем WebRTC
            for peer_id, channel in self.webrtc_channels.items():
                if self.connected_peers.get(peer_id, {}).get('username') == to_username:
                    try:
                        # 1. Сериализуем и отправляем
                        channel.send(json.dumps(message_data).encode())
                        
                        # 2. Добавляем в pending_messages для отслеживания подтверждения
                        with self.message_retry_lock:
                            self.pending_messages[message_id] = {
                                'message_data': message_data,
                                'target_peer': self.connected_peers[peer_id],  # сохраняем peer_info для fallback
                                'timestamp': time.time(),
                                'last_sent': time.time(),
                                'attempts': 1,        # первая попытка
                                'webrtc_channel': channel  # пометка, что отправлено через WebRTC (опционально)
                            }
                        logger.info(f"✅ Сообщение {message_id} отправлено через WebRTC пользователю {to_username}")    
                        return True
                    except Exception as e:
                        logger.warning(f"WebRTC отправка не удалась: {e}")
            
            
            # Пробуем отправить, по очереди проверяя сокеты
            for peer_id, target_peer in candidates:
                # Проверка живости сокета
                sock = target_peer.get('socket')
                if sock:
                    try:
                        sock.send(b'')          # пустой пакет – если сокет мёртв, вылетит исключение
                    except:
                        logger.info(f"🔌 Сокет {peer_id} мёртв, удаляем пира")
                        self._handle_peer_disconnection(peer_id)
                        continue

                # Добавляем в pending (если ещё не добавлено из WebRTC-блока)
                if message_id not in self.pending_messages:         
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
                    logger.warning(f"⚠️ Не удалось отправить через {peer_id}, пробуем следующий...")

            logger.error(f"❌ Все попытки отправки сообщения {message_id} пользователю {to_username} не удались")
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
        username = data.get('username')
        if username == self.username:
            logger.debug(f"Игнорируем user_online для себя: {username}")
            return

        if peer_id not in self.connected_peers:
            return

        # Сохраняем listen_port, если он есть
        listen_port = data.get('listen_port')
        if listen_port:
            self.connected_peers[peer_id]['listen_port'] = listen_port

        # Проверка и удаление дубликатов (одинаковый username, разные peer_id)
        if username:
            existing_peer = None
            for pid, pinfo in list(self.connected_peers.items()):
                if pinfo.get('username') == username and pid != peer_id:
                    # Определяем, какой пир оставить, а какой удалить.
                    new_has_port = bool(listen_port)
                    old_has_port = bool(pinfo.get('listen_port'))

                    if old_has_port and not new_has_port:
                        # Существующий пир имеет постоянный порт, новый – временный.
                        # Удаляем новый (текущий peer_id) и выходим, не обновляя его данные.
                        logger.info(f"👥 Игнорируем временное соединение {peer_id} для {username}, "
                                    f"т.к. уже есть постоянное {pid}")
                        try:
                            self.connected_peers[peer_id]['socket'].close()
                        except:
                            pass
                        del self.connected_peers[peer_id]
                        return  # НЕ продолжаем обработку peer_id

                    elif new_has_port and not old_has_port:
                        # Новый пир имеет постоянный порт, старый – временный.
                        # Удаляем старый (existing_peer).
                        existing_peer = pid
                        break
                    else:
                        # Оба имеют или оба не имеют listen_port.
                        # Чтобы не терять связь, оставляем более старое соединение (existing_peer),
                        # а новое закрываем. Исключение: если старое уже неактивно (last_seen > 60).
                        if pinfo.get('last_seen', 0) < time.time() - 60:
                            existing_peer = pid
                            break
                        else:
                            logger.info(f"👥 Дубликат {username}: оставляем {pid}, удаляем {peer_id}")
                            try:
                                self.connected_peers[peer_id]['socket'].close()
                            except:
                                pass
                            del self.connected_peers[peer_id]
                            return

            if existing_peer:
                if any(pid == existing_peer for pid in self.active_audio_calls.values()):
                    logger.warning(f"Пир {existing_peer} имеет активный звонок – не закрываем")
                    return
                logger.warning(f"⚠️ Обнаружен дубликат пользователя {username}: {existing_peer} и {peer_id}. Закрываем {existing_peer}")
                try:
                    self.connected_peers[existing_peer]['socket'].close()
                except:
                    pass
                del self.connected_peers[existing_peer]

        # Обновляем данные текущего пира (если он не был удалён)
        if peer_id in self.connected_peers:
            if username:
                self.connected_peers[peer_id]['username'] = username
                self.connected_peers[peer_id]['last_seen'] = time.time()
                logger.info(f"👤 Пользователь {username} в сети (пир {peer_id})")        
                # Через пару секунд пробуем установить WebRTC (чтобы не мешать основному обмену)
                threading.Timer(2.0, self._initiate_webrtc_connection, args=(peer_id, self.connected_peers[peer_id])).start()
                online_users = self.get_online_users()
                self.user_list_updated.emit(online_users)
                logger.info(f"📊 Обновлен список пользователей: {len(online_users)} пользователей онлайн")
            
            else:
                self.connected_peers[peer_id]['last_seen'] = time.time()
                logger.debug(f"Пир {peer_id} без имени, last_seen обновлён")

    def _handle_user_offline(self, data: dict):
        username = data.get('username')
        if not username:
            return
        logger.info(f"Пользователь {username} вышел из сети")
        # Находим пира с таким именем
        to_remove = None
        for peer_id, peer_info in self.connected_peers.items():
            if peer_info.get('username') == username:
                to_remove = peer_id
                break
        if to_remove:
            self._handle_peer_disconnection(to_remove)
    
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
                client_socket.settimeout(30.0)
                peer_key = f"{address[0]}:{address[1]}"

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
                    'username': None,
                    'secure_mode': False
                }

                # ОТПРАВЛЯЕМ СВОЁ ИМЯ НОВОМУ ПИРУ (ВАЖНО!)
                self._send_self_info(peer_key)

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
                    time.sleep(1)

    def _handle_client_connection(self, client_socket: socket.socket, address: tuple):
        peer_id = f"{address[0]}:{address[1]}"
        logger.info(f"Начало обработки соединения с {address}")

        # Получаем ссылку на словарь пира (должен существовать)
        peer_info = self.connected_peers.get(peer_id)
        if not peer_info:
            logger.error(f"Пир {peer_id} не найден в connected_peers")
            client_socket.close()
            return

        try:
            # ---- ЭТАП 1: Обработка открытых сообщений (пока secure_mode = False) ----
            buffer = b''
            while not peer_info.get('secure_mode', False) and self.is_running:
                # Проверяем, что пир всё ещё в словаре и сокет не изменился
                if peer_id not in self.connected_peers:
                    logger.debug(f"Пир {peer_id} удалён из словаря, выходим")
                    break
                current_peer_info = self.connected_peers.get(peer_id)
                if current_peer_info.get('socket') != client_socket:
                    logger.debug(f"Сокет пира {peer_id} был заменён, выходим")
                    break

                try:
                    data = client_socket.recv(4096)
                    if not data:
                        logger.info(f"Соединение с {address} закрыто удалённой стороной")
                        break
                    buffer += data
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line:
                            try:
                                message = json.loads(line.decode('utf-8'))
                                # Обновляем last_seen
                                peer_info['last_seen'] = time.time()
                                # Обрабатываем сообщение (в том числе обмен ключами и user_online)
                                self._process_received_data(message, peer_id)
                            except json.JSONDecodeError:
                                logger.warning(f"Неверный JSON от {address}")
                except socket.timeout:
                    continue
                except OSError as e:
                    if e.errno == 9:  # Bad file descriptor
                        logger.debug(f"Сокет {address} уже закрыт, выходим")
                        break
                    else:
                        logger.error(f"Ошибка приёма данных от {address}: {e}")
                        break
                except Exception as e:
                    logger.error(f"Ошибка приёма данных от {address}: {e}")
                    break

            # ---- ЭТАП 2: После перехода в secure_mode ----
            if peer_info.get('secure_mode', False) and self.is_running:
                logger.info(f"Переход в защищённый режим для {address}")
                secure_channel = peer_info['socket']   # теперь это объект SecureChannel
                while self.is_running:
                    try:
                        decrypted_bytes = secure_channel.recv(timeout=1.0)
                        if not decrypted_bytes:
                            break
                        message = json.loads(decrypted_bytes.decode('utf-8'))
                        peer_info['last_seen'] = time.time()
                        self._process_received_data(message, peer_id)
                    except socket.timeout:
                        continue
                    except ConnectionError:
                        logger.info(f"Защищённое соединение с {address} разорвано")
                        break
                    except json.JSONDecodeError:
                        logger.warning(f"Неверный JSON в защищённом канале от {address}")
                    except Exception as e:
                        logger.error(f"Ошибка в защищённом канале: {e}")
                        break

        except Exception as e:
            logger.error(f"Критическая ошибка в обработчике соединения: {e}")
        finally:
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
        """Отправляет словарь данных пиру. Если канал защищён – шифрует, иначе – в открытом виде."""
        try:
            serialized = json.dumps(data).encode('utf-8')
            sock = peer_info['socket']
            if hasattr(sock, 'recv') and isinstance(sock, SecureChannel):
                # SecureChannel.send сам обрабатывает шифрование и упаковку.
                sock.send(serialized)
            else:
                # Обычный сокет: отправляем с разделителем \n
                sock.sendall(serialized + b'\n')
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
        try:
            online_users = []
            seen_usernames = set()
            with self.peers_lock:
                for peer_id, peer_info in list(self.connected_peers.items()):
                    try:
                        username = peer_info.get('username')
                        if username and username != self.username and username not in seen_usernames:
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
                    except Exception as e:
                        logger.error(f"Ошибка обработки пира {peer_id}: {e}")
            logger.info(f"🔍 get_online_users вернул {len(online_users)} пользователей: {[u['username'] for u in online_users]}")
            return online_users
        except Exception as e:
            logger.error(f"Ошибка в get_online_users: {e}")
            return []
    
    # Звонки
    def send_call_request(self, to_username: str, call_type: str) -> str:
        """Отправка запроса на звонок (аудио или видео)"""
        try:
            call_id = str(uuid.uuid4())

            # 1. Найти свободный порт для аудио
            local_port = self._find_free_call_port()
            if not local_port:
                logger.error(f"❌ Не удалось выделить порт для звонка {call_id}")
                return None

            # === СОЗДАЁМ СЕРВЕРНЫЙ СОКЕТ ДО ОТПРАВКИ ЗАПРОСА ===
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', local_port))
            server_socket.listen(1)
            server_socket.settimeout(10.0)

            if not hasattr(self, 'pending_media_sockets'):
                self.pending_media_sockets = {}
            self.pending_media_sockets[call_id] = server_socket

            # Запускаем accept_media (будет ждать подключения)
            def accept_media():
                try:
                    client_sock, client_addr = server_socket.accept()
                    logger.info(f"✅ Медиа-подключение для звонка {call_id} от {client_addr}")
                    # Сначала обмен ключами (серверная сторона, initiator=False)
                    secure = self._perform_media_key_exchange(client_sock, initiator=False)
                    self.media_sockets[call_id] = secure
                    if call_id in self.pending_media_sockets:
                        del self.pending_media_sockets[call_id]
                    server_socket.close()
                except Exception as e:
                    logger.error(f"❌ Ошибка в accept_media для {call_id}: {e}")
                    if call_id in self.media_sockets:
                        del self.media_sockets[call_id]
                    if call_id in self.pending_media_sockets:
                        del self.pending_media_sockets[call_id]
                    server_socket.close()

            threading.Thread(target=accept_media, daemon=True).start()
            # ===================================================

            media_info = {
                'media_server': self._get_local_ip(),
                'media_port': local_port,
                'call_id': call_id
            }

            # 2. Если видеозвонок – найти свободный порт для видео
            video_port = None
            if call_type == 'video':
                video_port = self._find_free_call_port()
                if video_port:
                    media_info['video_port'] = video_port
                    logger.info(f"📹 Выделен видео-порт {video_port} для звонка {call_id}")
                    logger.info(f"📹 Отправляем media_info: {media_info}")
                else:
                    logger.warning(f"⚠️ Не удалось выделить видео-порт для звонка {call_id}, видеопоток не будет работать")

            
            # 3. Сохраняем информацию о звонке (после того как все порты определены)
            call_info = {
                'to_user': to_username,
                'call_type': call_type,
                'status': 'outgoing',
                'timestamp': time.time(),
                'local_port': local_port
            }
            if video_port:
                call_info['video_local_port'] = video_port
            self.call_requests[call_id] = call_info

            # 4. Найти пира по имени
            target_peer = None
            for peer_id, peer_info in list(self.connected_peers.items()):
                if peer_info.get('username') == to_username:
                    target_peer = peer_info
                    break

            if not target_peer:
                available = [p.get('username') for p in self.connected_peers.values() if p.get('username')]
                logger.error(f"❌ Пользователь {to_username} не найден. Доступны: {available}")
                return None

            # 5. Получить локальный IP, видимый этому пиру (через существующий сокет)
            sock = target_peer['socket']
            if hasattr(sock, 'sock'):          # SecureChannel
                sock = sock.sock
            try:
                local_ip = sock.getsockname()[0]
            except Exception:
                local_ip = self._get_local_ip()   # fallback
                logger.warning(f"Не удалось получить IP из сокета, используем {local_ip}")

            # 6. Сформировать media_info с правильным IP
            media_info = {
                'media_server': local_ip,
                'media_port': local_port,
                'call_id': call_id
            }
            if video_port:
                media_info['video_port'] = video_port
                logger.info(f"📹 Отправляем media_info: {media_info}")
            else:
                logger.info(f"🔊 Отправляем media_info: {media_info}")

            # 7. Отправить запрос
            message = {
                'type': 'call_request',
                'call_id': call_id,
                'from': self.username,
                'to': to_username,
                'call_type': call_type,
                'timestamp': time.time(),
                'media_info': media_info
            }

            if self._send_to_peer(target_peer, message):
                logger.info(f"📞 Отправлен запрос на {call_type} звонок {call_id} пользователю {to_username}, аудио порт {local_port}")
                if video_port:
                    logger.info(f"📹 Видео порт для звонка {call_id}: {video_port}")
                # Не отправляем сигнал outgoing_call, т.к. окно создаётся в gui
                return call_id
            else:
                logger.error(f"❌ Не удалось отправить запрос на звонок пользователю {to_username}")
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
            
            logger.info(f"📥 _handle_call_request: получен call_id={call_id}, media_info={media_info}")
            
            if call_id and from_user:
                logger.info(f"📞 Ответ на звонок {call_id} от {from_user}")
            
                # Сохраняем информацию о звонке
                if call_id and from_user:
                    self.call_requests[call_id] = {
                        'from_user': from_user,
                        'call_type': call_type,
                        'media_host': media_info.get('media_server'),
                        'media_port': media_info.get('media_port'),
                        'status': 'incoming',
                        'timestamp': time.time()
                    }

                # Если есть видео-порт, сохраняем его отдельно
                if 'video_port' in media_info:
                    self.call_requests[call_id]['video_port'] = media_info['video_port']
                    logger.info(f"📹 Видео порт собеседника: {media_info['video_port']}")
                else:
                    logger.warning("⚠️ В media_info нет video_port")

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
        try:
            # 1. Закрываем сокет, если он есть
            if call_id in self.media_sockets:
                media_socket = self.media_sockets[call_id]
                if media_socket:
                    try:
                        # Отправляем уведомление о завершении звонка
                        end_data = {'call_id': call_id, 'action': 'end'}
                        media_socket.send(json.dumps(end_data).encode())
                    except:
                        pass
                    media_socket.close()
                    logger.info(f"🔌 Медиа-соединение для звонка {call_id} закрыто")

            # 2. Удаляем из всех вспомогательных словарей
            if call_id in self.media_connections:
                del self.media_connections[call_id]
            if call_id in self.call_requests:
                del self.call_requests[call_id]
            if call_id in self.media_sockets:
                del self.media_sockets[call_id]

            # 3. КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: удаляем call_id из набора активных звонков
            if call_id in self.active_audio_calls:
                del self.active_audio_calls[call_id]
                logger.debug(f"Активный звонок {call_id} удалён из active_audio_calls")

        except Exception as e:
            logger.error(f"❌ Ошибка закрытия медиа-соединения: {e}")
        
    # Файлы
    def send_file(self, to_username: str, file_path: str) -> bool:
        """Отправка файла пользователю"""
        import os, uuid
        if not os.path.exists(file_path):
            logger.error(f"Файл не найден: {file_path}")
            return False

        # Найти peer по username
        target_peer = None
        for peer_id, pinfo in self.connected_peers.items():
            if pinfo.get('username') == to_username:
                target_peer = pinfo
                break
        if not target_peer:
            logger.error(f"Пользователь {to_username} не в сети")
            return False

        file_size = os.path.getsize(file_path)
        max_size_mb = self.settings.value('max_file_size_mb', 100, type=int)
        if file_size > max_size_mb * 1024 * 1024:
            logger.error(f"Файл слишком большой: {file_size} байт (макс {max_size_mb} МБ)")
            return False

        file_name = os.path.basename(file_path)
        file_id = str(uuid.uuid4())

        # Сохраняем информацию о передаче
        self.active_file_transfers[file_id] = {
            'peer': target_peer,
            'to_username': to_username,
            'file_path': file_path,
            'file_size': file_size,
            'sent_bytes': 0,
            'status': 'sending'
        }

        # Отправляем запрос на передачу файла
        request_msg = {
            'type': 'file_request',
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size,
            'from': self.username,
            'to': to_username,
            'timestamp': time.time()
        }
        if not self._send_to_peer(target_peer, request_msg):
            logger.error("Не удалось отправить запрос на передачу файла")
            return False

        # Запускаем поток для отправки чанков
        threading.Thread(target=self._send_file_chunks, args=(file_id,), daemon=True).start()
        logger.info(f"Начата отправка файла {file_name} (ID {file_id}) пользователю {to_username}")
        return True
    
    def _send_file_chunks(self, file_id: str, chunk_size=8192):
        transfer = self.active_file_transfers.get(file_id)
        if not transfer:
            return
        file_path = transfer['file_path']
        peer = transfer['peer']
        file_size = transfer['file_size']
        try:
            with open(file_path, 'rb') as f:
                offset = 0
                while offset < file_size and file_id in self.active_file_transfers:
                    f.seek(offset)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    import base64
                    b64_data = base64.b64encode(chunk).decode('ascii')
                    chunk_msg = {
                        'type': 'file_chunk',
                        'file_id': file_id,
                        'offset': offset,
                        'data': b64_data,
                        'size': len(chunk)
                    }
                    if not self._send_to_peer(peer, chunk_msg):
                        logger.error(f"Ошибка отправки чанка файла {file_id} на офсете {offset}")
                        break
                    offset += len(chunk)
                    transfer['sent_bytes'] = offset
                    self.file_progress.emit(file_id, offset, file_size)
                    time.sleep(0.005)  # небольшая задержка, чтобы не перегружать сеть
            # После отправки всех чанков – уведомляем о завершении
            complete_msg = {'type': 'file_complete', 'file_id': file_id, 'status': 'ok'}
            self._send_to_peer(peer, complete_msg)
            logger.info(f"Файл {file_path} отправлен, ID {file_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки файла {file_id}: {e}")
        finally:
            if file_id in self.active_file_transfers:
                del self.active_file_transfers[file_id]
    
    def _handle_file_request(self, data: dict, peer_id: str):
        """Обработка запроса на получение файла"""
        file_id = data['file_id']
        file_name = data['file_name']
        file_size = data['file_size']
        from_user = data['from']

        # Проверка максимального размера
        max_size_mb = self.settings.value('max_file_size_mb', 100, type=int)
        if file_size > max_size_mb * 1024 * 1024:
            logger.warning(f"Файл {file_name} слишком большой ({file_size} байт)")
            reject_msg = {'type': 'file_complete', 'file_id': file_id, 'status': 'too_large'}
            self._send_to_peer(self.connected_peers.get(peer_id, {}), reject_msg)
            return

        # Папка для сохранения
        download_folder = self.settings.value('download_folder')
        if not download_folder:
            download_folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
            # Сохраняем это значение в настройки, чтобы в следующий раз не вычислять
            self.settings.setValue('download_folder', download_folder)
            self.settings.sync()
        os.makedirs(download_folder, exist_ok=True)
        save_path = os.path.join(download_folder, file_name)
        counter = 1
        while os.path.exists(save_path):
            name, ext = os.path.splitext(file_name)
            save_path = os.path.join(download_folder, f"{name}_{counter}{ext}")
            counter += 1

        self.active_file_transfers[file_id] = {
            'save_path': save_path,
            'file_size': file_size,
            'received_bytes': 0,
            'file_handle': open(save_path, 'wb'),
            'from_user': from_user,
            'peer_id': peer_id,
            'status': 'receiving'
        }

        # Отправляем подтверждение готовности
        ack_msg = {'type': 'file_ack', 'file_id': file_id, 'status': 'ready'}
        self._send_to_peer(self.connected_peers.get(peer_id, {}), ack_msg)
        logger.info(f"Начинаем приём файла {file_name} (ID {file_id}) от {from_user}")

    def _handle_file_chunk(self, data: dict, peer_id: str):
        file_id = data['file_id']
        offset = data['offset']
        b64_data = data['data']
        import base64
        chunk = base64.b64decode(b64_data)
        transfer = self.active_file_transfers.get(file_id)
        if not transfer or transfer['status'] != 'receiving':
            logger.warning(f"Неожиданный чанк для {file_id}")
            return
        try:
            transfer['file_handle'].seek(offset)
            transfer['file_handle'].write(chunk)
            transfer['received_bytes'] += len(chunk)
            self.file_progress.emit(file_id, transfer['received_bytes'], transfer['file_size'])
        except Exception as e:
            logger.error(f"Ошибка записи чанка файла {file_id}: {e}")

    def _handle_file_complete(self, data: dict, peer_id: str):
        file_id = data['file_id']
        status = data.get('status', 'ok')
        transfer = self.active_file_transfers.get(file_id)
        if transfer:
            transfer['file_handle'].close()
            if status == 'ok':
                logger.info(f"Файл {transfer['save_path']} успешно получен")
                self.file_received.emit(transfer['from_user'], transfer['save_path'])
            else:
                logger.warning(f"Передача файла {file_id} завершена с ошибкой: {status}")
                if os.path.exists(transfer['save_path']):
                    os.remove(transfer['save_path'])
            del self.active_file_transfers[file_id]
        else:
            logger.warning(f"Файл {file_id} уже завершён или не существует")

    def _handle_file_ack(self, data: dict, peer_id: str):
        """Подтверждение готовности к приёму (опционально)"""
        file_id = data.get('file_id')
        status = data.get('status')
        if status == 'ready':
            logger.debug(f"Собеседник готов принять файл {file_id}")
        
    # Шифрование
    def _perform_key_exchange(self, peer_id: str, sock: socket.socket):
        """Выполняет обмен ключами и заменяет обычный сокет на SecureChannel."""
        crypto = CryptoManager()
        crypto.generate_key_pair()
        # Отправляем свой публичный ключ
        pub_key_str = crypto.serialize_public_key()
        self._send_raw(sock, json.dumps({'type': 'public_key', 'key': pub_key_str}).encode() + b'\n')
        # Ждём публичный ключ от собеседника
        raw = self._recv_raw(sock)
        if not raw:
            raise Exception("Не получен публичный ключ")
        data = json.loads(raw.decode())
        if data.get('type') != 'public_key':
            raise Exception("Неверный тип сообщения")
        crypto.deserialize_public_key(data['key'])
        # Генерируем симметричный ключ и шифруем
        sym_key = crypto.generate_symmetric_key()
        encrypted_key = crypto.encrypt_symmetric_key(sym_key)
        self._send_raw(sock, json.dumps({'type': 'symmetric_key', 'key': base64.b64encode(encrypted_key).decode()}).encode() + b'\n')
        # Получаем подтверждение (опционально)
        # Заменяем сокет на защищённый
        crypto.symmetric_key = sym_key
        secure = SecureChannel(sock, crypto)
        self.connected_peers[peer_id]['socket'] = secure
        self.peer_crypto[peer_id] = crypto
        logger.info(f"Ключи установлены с {peer_id}")
    
    def _send_raw(self, sock: socket.socket, data: bytes) -> None:
        """Отправляет данные с завершающим '\n'."""
        sock.sendall(data)

    def _recv_raw(self, sock: socket.socket) -> Optional[bytes]:
        """Получает одну строку до '\n', возвращает декодированные байты без '\n'."""
        buf = b''
        while b'\n' not in buf:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                buf += chunk
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Ошибка приёма данных: {e}")
                return None
        line, rest = buf.split(b'\n', 1)
        # Остаток можно сохранить, если нужно, но в данном протоколе мы используем только одну строку
        return line

    def _perform_media_key_exchange(self, sock: socket.socket, initiator: bool):
        """
        Асимметричный обмен ключами для медиа‑канала.
        initiator=True  – клиент (подключается), генерирует симметричный ключ.
        initiator=False – сервер (принимает), получает ключ от клиента.
        Возвращает SecureChannel.
        """
        logger.info("🔐 Обмен ключами для медиа (initiator=%s)", initiator)
        crypto = CryptoManager()
        crypto.generate_key_pair()

        # 1. Обе стороны обмениваются публичными ключами
        # Отправляем свой ключ
        pub_key = crypto.serialize_public_key()
        self._send_raw(sock, json.dumps({'type': 'public_key', 'key': pub_key}).encode() + b'\n')
        # Получаем ключ партнёра
        raw = self._recv_raw(sock)
        if not raw:
            raise ConnectionError("Не получен публичный ключ партнёра")
        data = json.loads(raw.decode())
        if data.get('type') != 'public_key':
            raise ValueError("Ожидалось сообщение 'public_key'")
        crypto.deserialize_public_key(data['key'])
        logger.debug("Публичные ключи exchanged")

        if initiator:
            # 2. Клиент генерирует симметричный ключ и отправляет серверу
            sym_key = crypto.generate_symmetric_key()
            encrypted_key = crypto.encrypt_symmetric_key(sym_key)
            enc_b64 = base64.b64encode(encrypted_key).decode()
            self._send_raw(sock, json.dumps({'type': 'symmetric_key', 'key': enc_b64}).encode() + b'\n')
            crypto.symmetric_key = sym_key
            logger.debug("Симметричный ключ отправлен серверу")
        else:
            # 3. Сервер принимает зашифрованный симметричный ключ от клиента
            raw_key = self._recv_raw(sock)
            if not raw_key:
                raise ConnectionError("Не получен симметричный ключ от клиента")
            key_data = json.loads(raw_key.decode())
            encrypted_key = base64.b64decode(key_data['key'])
            crypto.symmetric_key = crypto.decrypt_symmetric_key(encrypted_key)
            logger.debug("Симметричный ключ получен и расшифрован")

        secure = SecureChannel(sock, crypto)
        logger.info("✅ Защищённый медиа-канал установлен")
        return secure

    @property
    def connected(self):
        """Свойство для обратной совместимости"""
        return self.is_running
