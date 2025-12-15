import socket
import logging
import threading
import json

logger = logging.getLogger('dialog_p2p')

class P2PChatClient:
    def __init__(self, config):
        self.config = config
        self.db = Database(config['database']['path'])
        self.auth = AuthManager(self.db)
        self.network = P2PNetwork(config, self.db)
        self.session_manager = SessionManager(self.db)
        self.current_username = None
        # Добавляем словарь для медиа-соединений
        self.media_connections = {}
        self.media_sockets = {}
        self.call_requests = {}
        self.logger = logging.getLogger('dialog_p2p')

    async def start(self):
        await self.db.initialize()
        await self.network.start()
        # Подключение к bootstrap узлам
        bootstrap_host = self.config.get('bootstrap_host', 'localhost')
        bootstrap_port = self.config.get('bootstrap_port', 8888)
        
        try:
            # Регистрируемся в bootstrap сервере
            self.network.register_with_bootstrap_sync(bootstrap_host, bootstrap_port)
            # Или получаем список пиров
            self.network.get_peers_from_bootstrap_sync(bootstrap_host, bootstrap_port)

            # Если имя пользователя установлено, отправляем его в сеть
            if self.current_username:
                self.network.set_username(self.current_username)

        except Exception as e:
            self.logger.warning(f"Bootstrap подключение не удалось: {e}")
        
    def set_username(self, username: str):
        """Установка имени пользователя для P2P сети"""
        self.current_username = username
        if hasattr(self, 'network') and self.network:
            self.network.set_username(username)

    def send_message(self, target_username, message, host=None, port=None):
        """Отправка сообщения конкретному пользователю"""
        logger.info(f"P2PClient.send_message: Попытка отправки сообщения для {target_username}")
        try:
            # Если указаны host и port, отправляем напрямую
            if host and port:
                # Логика отправки по прямому соединению
                logger.info(f"P2PClient.send_message: Host: {host}, Port: {port}")
            else:
                logger.info(f"P2PClient.send_message: Сообщение: {message}")
                # Ищем пользователя в списке пиров
                logger.info(f"P2PClient.send_message: Сообщение '{message}' обработано")
                for peer_id, peer_info in self.peers.items():
                    if peer_info.get('username') == target_username:
                        # Логика отправки сообщения peer_info
                        logger.info(f"Отправка сообщения для {target_username}: {message}")
                        break

        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
        
    def send_call_request(self, target_username, call_type):
        """Отправить запрос на звонок"""
        try:
            logger.info(f"🔊 Отправка запроса на звонок для {target_username}, тип: {call_type}")
            
            # Создаем уникальный ID звонка
            import uuid
            call_id = str(uuid.uuid4())[:8]
            
            # Сохраняем информацию о запросе
            self.call_requests[call_id] = {
                'target': target_username,
                'type': call_type,
                'status': 'pending'
            }
            
            # Отправляем через сеть
            if self.network:
                message = {
                    'type': 'call_request',
                    'call_id': call_id,
                    'call_type': call_type,
                    'from_user': self.current_username,
                    'action': 'incoming_call'
                }
                success = self.network.send_message_to_user(
                    target_username, 
                    json.dumps(message)
                )
                
                if success:
                    logger.info(f"✅ Запрос на звонок {call_id} отправлен")
                    return call_id
                else:
                    logger.error(f"❌ Не удалось отправить запрос на звонок")
                    return None
            return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки запроса на звонок: {e}")
            return None

    def send_call_response(self, call_id, response):
        """Отправить ответ на звонок (принять/отклонить/завершить)"""
        try:
            logger.info(f"🔊 Отправка ответа на звонок {call_id}: {response}")
            
            if call_id not in self.call_requests:
                logger.error(f"❌ Звонок {call_id} не найден")
                return False
            
            call_info = self.call_requests[call_id]
            target_user = call_info['target']
            
            # Отправляем ответ через сеть
            if self.network:
                message = {
                    'type': 'call_response',
                    'call_id': call_id,
                    'response': response,
                    'from_user': self.current_username
                }
                
                success = self.network.send_message_to_user(
                    target_user, 
                    json.dumps(message)
                )
                
                if success:
                    logger.info(f"✅ Ответ на звонок отправлен")
                    
                    # Если звонок завершен, очищаем медиа соединение
                    if response == 'end':
                        self.close_media_connection(call_id)
                        
                    return True
                else:
                    logger.error(f"❌ Не удалось отправить ответ на звонок")
                    return False
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ответа на звонок: {e}")
            return False
    
    def setup_media_connection(self, call_id, username):
        """Временная заглушка для установки медиа соединения"""
        logger.info(f"🔧 setup_media_connection заглушка: call_id={call_id}, username={username}")
        
        # Создаем тестовый сокет для локального тестирования
        try:
            # Создаем локальный сокет для тестирования аудио
            media_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            media_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Находим свободный порт
            media_port = self.find_free_port(9000, 10000)
            
            try:
                # Пробуем подключиться к медиа порту пользователя
                # В реальной P2P сети это будет сложнее из-за NAT
                media_socket.connect((peer_info['host'], media_port + 1))  # media_port + 1 для медиа
                
                # Сохраняем сокет
                self.media_sockets[call_id] = media_socket
                self.media_connections[call_id] = {
                    'socket': media_socket,
                    'username': username,
                    'host': peer_info['host'],
                    'port': media_port + 1,
                    'type': 'audio'
                }
            except ConnectionRefusedError:
                logger.warning(f"⚠️ Не удалось подключиться к медиа порту, используем локальное соединение")
                # Создаем локальный сокет для тестирования
                return self.create_local_media_socket(call_id)

                
        except Exception as e:
            logger.error(f"❌ Ошибка создания медиа соединения: {e}")
            # Резервный вариант: локальный сокет для тестирования
            return self.create_local_media_socket(call_id)
            
    def create_local_media_socket(self, call_id):
        """Создать локальный сокет для тестирования медиа"""
        try:
            # Создаем серверный сокет для локального тестирования
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Находим свободный порт
            test_port = self.find_free_port(10001, 11000)
            server_socket.bind(('localhost', test_port))
            server_socket.listen(1)
            server_socket.settimeout(5)  # 5 секунд на ожидание
            
            # Сохраняем серверный сокет
            self.media_connections[call_id] = {
                'server_socket': server_socket,
                'port': test_port,
                'type': 'local_test'
            }
            
            logger.info(f"🔧 Создан локальный медиа сокет на порту {test_port}")
            
            # Запускаем поток для принятия соединения
            def accept_connection():
                try:
                    client_socket, addr = server_socket.accept()
                    self.media_sockets[call_id] = client_socket
                    logger.info(f"✅ Локальное медиа соединение установлено")
                except socket.timeout:
                    logger.warning(f"⚠️ Таймаут ожидания медиа соединения")
                except Exception as e:
                    logger.error(f"❌ Ошибка принятия соединения: {e}")
            
            threading.Thread(target=accept_connection, daemon=True).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания локального медиа сокета: {e}")
            return False

    def get_media_socket(self, call_id):
        """Получить медиа сокет для звонка"""
        try:
            # Сначала пробуем получить реальный сокет
            if call_id in self.media_sockets:
                socket_obj = self.media_sockets[call_id]
                if socket_obj:
                    # Проверяем, что сокет еще живой
                    try:
                        socket_obj.send(b'P')
                        return socket_obj
                    except:
                        # Сокет мертв, удаляем его
                        del self.media_sockets[call_id]
            
            # Если нет сокета, пробуем создать локальный для тестирования
            if call_id in self.call_requests:
                call_info = self.call_requests[call_id]
                if self.create_local_media_socket(call_id):
                    # Ждем немного, чтобы соединение установилось
                    import time
                    time.sleep(0.5)
                    return self.media_sockets.get(call_id)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения медиа сокета: {e}")
            return None
    
    def close_media_connection(self, call_id):
        """Закрыть медиа соединение"""
        try:
            if call_id in self.media_sockets:
                socket_obj = self.media_sockets[call_id]
                if socket_obj:
                    socket_obj.close()
                del self.media_sockets[call_id]
            
            if call_id in self.media_connections:
                conn_info = self.media_connections[call_id]
                if 'server_socket' in conn_info:
                    conn_info['server_socket'].close()
                del self.media_connections[call_id]
            
            if call_id in self.call_requests:
                del self.call_requests[call_id]
                
            logger.info(f"🔌 Медиа соединение {call_id} закрыто")
            
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия медиа соединения: {e}")

    def find_free_port(self, start_port=9000, end_port=10000):
        """Найти свободный порт для тестирования"""
        import socket
        for port in range(start_port, end_port + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except:
                continue
        return start_port 