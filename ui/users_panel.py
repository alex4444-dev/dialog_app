from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QMenu, QAction, QListWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal
from ui.styles.main_style import USERS_PANEL_STYLE
import logging

logger = logging.getLogger('dialog_gui')

class UsersPanel(QWidget):
    user_selected = pyqtSignal(str, str, int)  # username, host, port - ИЗМЕНЕНО!
    refresh_requested = pyqtSignal()
    call_requested = pyqtSignal(str, str)  # username, call_type
    peer_connect_requested = pyqtSignal(str, int)  # host, port
    peer_disconnect_requested = pyqtSignal(str, int)  # host, port    
    block_user = pyqtSignal(str)      # username
    unblock_user = pyqtSignal(str)    # username
    add_contact_requested = pyqtSignal(str)      # username
    remove_contact_requested = pyqtSignal(str)   # username
    
    def __init__(self):
        super().__init__()
        self.peers_data = {}  # {peer_id: {'username': str, 'host': str, 'port': int, 'status': str}}
        self.init_ui()
               
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Заголовок
        title = QLabel("Пользователи в сети")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            color: #2c3e50; 
            padding: 12px;
            background-color: #f8f9fa;
            border-radius: 8px;
        """)
        layout.addWidget(title)
        
        # Статус сети
        self.network_status = QLabel("Сеть: ❌ Не подключено")
        self.network_status.setAlignment(Qt.AlignCenter)
        self.network_status.setStyleSheet("""
            font-size: 12px;
            color: #e74c3c;
            padding: 4px;
            background-color: #fadbd8;
            border-radius: 4px;
        """)
        layout.addWidget(self.network_status)
        
        # Список пользователей
        self.users_list = QListWidget()
        self.users_list.itemDoubleClicked.connect(self.on_user_double_clicked)
        self.users_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.users_list.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.users_list)
        
        # Панель управления сетью
        network_layout = QHBoxLayout()

        layout.addLayout(network_layout)
        
        # Кнопка обновления
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        button_layout.addWidget(self.refresh_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setStyleSheet(USERS_PANEL_STYLE)
        
    def show_context_menu(self, position):
        item = self.users_list.itemAt(position)
        if not item:
            return

        context_menu = QMenu(self)

        peer_id = item.data(Qt.UserRole)
        peer_data = self.peers_data.get(peer_id)
        if not peer_data:
            return

        username = peer_data['username']
        host = peer_data['host']
        port = peer_data['port']
        status = peer_data['status']

        # Информация о пире
        info_action = QAction(f"Информация о {username}", self)
        info_action.triggered.connect(lambda: self.show_peer_info(peer_data))
        context_menu.addAction(info_action)
        context_menu.addSeparator()

        # Действия в зависимости от статуса (онлайн/офлайн)
        if status == 'online':
            disconnect_action = QAction("🔌 Отключиться", self)
            disconnect_action.triggered.connect(lambda: self.peer_disconnect_requested.emit(host, port))
            context_menu.addAction(disconnect_action)

            chat_action = QAction("💬 Написать сообщение", self)
            chat_action.triggered.connect(lambda: self.user_selected.emit(username, host, port))
            context_menu.addAction(chat_action)

            call_menu = context_menu.addMenu("📞 Позвонить")
            audio_call_action = QAction("Аудио звонок", self)
            audio_call_action.triggered.connect(lambda: self.call_requested.emit(username, 'audio'))
            call_menu.addAction(audio_call_action)

            video_call_action = QAction("Видео звонок", self)
            video_call_action.triggered.connect(lambda: self.call_requested.emit(username, 'video'))
            call_menu.addAction(video_call_action)

            context_menu.addSeparator()

            block_action = QAction("🚫 Заблокировать", self)
            block_action.triggered.connect(lambda: self.block_user.emit(username))
            context_menu.addAction(block_action)

            unblock_action = QAction("🔓 Разблокировать", self)
            unblock_action.triggered.connect(lambda: self.unblock_user.emit(username))
            context_menu.addAction(unblock_action)

        else:
            # Для офлайн-пользователей – только подключиться (если известен адрес)
            if host != 'unknown' and port != 0:
                connect_action = QAction("🔗 Подключиться", self)
                connect_action.triggered.connect(lambda: self.peer_connect_requested.emit(host, port))
                context_menu.addAction(connect_action)

        # Действия с контактами (доступны для всех, даже офлайн)
        context_menu.addSeparator()
        add_contact_action = QAction("➕ Добавить в контакты", self)
        add_contact_action.triggered.connect(lambda: self.add_contact_requested.emit(username))
        context_menu.addAction(add_contact_action)

        remove_contact_action = QAction("➖ Удалить из контактов", self)
        remove_contact_action.triggered.connect(lambda: self.remove_contact_requested.emit(username))
        context_menu.addAction(remove_contact_action)

        context_menu.exec_(self.users_list.mapToGlobal(position))

    def show_peer_info(self, peer_data):
        """Показать информацию о пире"""
        from PyQt5.QtWidgets import QMessageBox
        
        info_text = f"""
        Имя пользователя: {peer_data['username']}
        Хост: {peer_data['host']}
        Порт: {peer_data['port']}
        Статус: {peer_data['status']}
        """
        
        QMessageBox.information(self, "Информация о пире", info_text.strip())

    def debug_show_received_data(self, users):
        """Метод для отладки - показать полученные данные"""
        if not users:
            logger.info("Пустой список users")
            return
            
        for i, user in enumerate(users):
            logger.info(f"Пользователь {i}: {user} (тип: {type(user)})")
            if isinstance(user, dict):
                for key, value in user.items():
                    logger.info(f"  {key}: {value} (тип: {type(value)})")
        
    def on_user_double_clicked(self, item):
        """Обработка двойного клика по пользователю - УПРОЩЕННАЯ ВЕРСИЯ"""
        if not item:
            return
            
        peer_id = item.data(Qt.UserRole)
        if peer_id and peer_id in self.peers_data:
            peer_data = self.peers_data[peer_id]
            username = peer_data['username']
            host = peer_data['host']
            port = peer_data['port']
            
            logger.info(f"UsersPanel: Двойной клик по пользователю {username} ({host}:{port})")
            
            # ВСЕГДА открываем чат при двойном клике, независимо от статуса
            self.user_selected.emit(username, host, port)  # ИЗМЕНЕНО!
            
            # Если не подключен, автоматически подключаемся
            if peer_data.get('status') != 'connected':
                logger.info(f"UsersPanel: Автоматическое подключение к {username}")
                self.peer_connect_requested.emit(host, port)

    def start_audio_call(self):
        """Начать аудио звонок"""
        current_item = self.users_list.currentItem()
        if current_item:
            peer_id = current_item.data(Qt.UserRole)
            if peer_id and peer_id in self.peers_data:
                username = self.peers_data[peer_id]['username']
                self.call_requested.emit(username, 'audio')
        
    def start_video_call(self):
        """Начать видео звонок"""
        current_item = self.users_list.currentItem()
        if current_item:
            peer_id = current_item.data(Qt.UserRole)
            if peer_id and peer_id in self.peers_data:
                username = self.peers_data[peer_id]['username']
                self.call_requested.emit(username, 'video')
        
    def add_peer_manually(self):
        """Добавить пир вручную"""
        from PyQt5.QtWidgets import QInputDialog, QMessageBox
        
        host, ok = QInputDialog.getText(self, "Добавить пир", "Введите хост:")
        if ok and host:
            port, ok = QInputDialog.getInt(self, "Добавить пир", "Введите порт:", 9000, 1000, 65535, 1)
            if ok:
                # Эмитируем сигнал для главного окна
                self.peer_connect_requested.emit(host, port)
                
    def disconnect_from_peer(self):
        """Отключиться от выбранного пира"""
        current_item = self.users_list.currentItem()
        if current_item:
            peer_id = current_item.data(Qt.UserRole)
            if peer_id and peer_id in self.peers_data:
                peer_data = self.peers_data[peer_id]
                self.peer_disconnect_requested.emit(peer_data['host'], peer_data['port'])
        
    def update_network_status(self, is_connected: bool, peer_count: int = 0):
        """Обновление статуса сети"""
        if is_connected:
            self.network_status.setText(f"Сеть: ✅ Подключено ({peer_count} Пользователей)")
            self.network_status.setStyleSheet("""
                font-size: 12px;
                color: #27ae60;
                padding: 4px;
                background-color: #d5f4e6;
                border-radius: 4px;
            """)
        else:
            self.network_status.setText("Сеть: ❌ Список пуст")
            self.network_status.setStyleSheet("""
                font-size: 12px;
                color: #2a4b5c;
                padding: 4px;
                background-color: #d5f4e6;
                border-radius: 4px;
            """)
        
    def update_users(self, users, contacts=None):
        """
        Обновление списка пользователей с учётом контактов (друзей).
        :param users: список онлайн-пользователей (словари)
        :param contacts: список имён друзей из БД (если None, берём из self.contacts)
        """
        # Если контакты не переданы, пытаемся получить через главное окно (если есть доступ)
        if contacts is None:
            if self.parent() and hasattr(self.parent(), 'get_contacts'):
                contacts = self.parent().get_contacts()
            else:
                contacts = []

        # Создаём множество имён онлайн-пользователей для быстрого поиска
        online_usernames = {u['username'] for u in users if isinstance(u, dict) and 'username' in u}

        # Строим словарь всех пользователей (онлайн + офлайн друзья)
        all_users = []
        processed = set()

        # Добавляем онлайн-пользователей
        for user in users:
            username = user.get('username')
            if username and username not in processed:
                user['status'] = 'online'
                user['is_contact'] = username in contacts
                all_users.append(user)
                processed.add(username)

        # Добавляем офлайн-друзей, которых нет в онлайн-списке
        for contact in contacts:
            if contact not in processed:
                all_users.append({
                    'username': contact,
                    'host': 'unknown',
                    'port': 0,
                    'status': 'offline',
                    'is_contact': True,
                    'online': False
                })
                processed.add(contact)

        # Теперь обновляем UI с объединённым списком
        self._update_list(all_users)

    def _update_list(self, users):
        """Обновление QListWidget на основе подготовленного списка"""
        self.users_list.clear()
        self.peers_data.clear()

        if not users:
            self.update_network_status(False, 0)
            return

        connected_count = 0
        for user in users:
            username = user.get('username', 'Неизвестный')
            host = user.get('host', 'unknown')
            port = user.get('port', 0)
            status = user.get('status', 'offline')
            is_contact = user.get('is_contact', False)

            peer_id = f"{host}:{port}" if host != 'unknown' else f"offline_{username}"

            # Сохраняем данные
            self.peers_data[peer_id] = {
                'username': username,
                'host': host,
                'port': port,
                'status': status,
                'is_contact': is_contact
            }

            # Определяем иконку статуса
            if status == 'online':
                status_icon = "🟢"
                connected_count += 1
            else:
                status_icon = "⚪"  # серый кружок для офлайн

            # Формируем текст: добавляем звёздочку для друзей
            friend_icon = "👥 " if is_contact else ""
            item_text = f"{status_icon} {friend_icon}{username}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, peer_id)
            self.users_list.addItem(item)

        self.update_network_status(connected_count > 0, connected_count)
        logger.info(f"Обновлено: {len(users)} пользователей (онлайн: {connected_count}, друзей: {sum(1 for u in users if u.get('is_contact'))})")
