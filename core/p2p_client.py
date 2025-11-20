class P2PChatClient:
    def __init__(self, config):
        self.config = config
        self.db = Database(config['database']['path'])
        self.auth = AuthManager(self.db)
        self.network = P2PNetwork(config, self.db)
        self.session_manager = SessionManager(self.db)
        self.current_username = None

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
        

    
    def setup_media_connection(self, call_id, username):
        """Временная заглушка для установки медиа соединения"""
        logger.info(f"🔧 setup_media_connection заглушка: call_id={call_id}, username={username}")
        
        # Создаем тестовый сокет для локального тестирования
        try:
            # Создаем локальный сокет для тестирования аудио
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Находим свободный порт
            test_port = self.find_free_port()
            test_socket.bind(('localhost', test_port))
            test_socket.listen(1)
            
            # В реальной реализации здесь должно быть P2P соединение
            logger.info(f"🔧 Создан тестовый медиа сокет на порту {test_port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания тестового медиа соединения: {e}")
            return False

    def find_free_port(self):
        """Найти свободный порт для тестирования"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]