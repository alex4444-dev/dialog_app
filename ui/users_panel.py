from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QMenu, QAction, QListWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal
from styles.main_style import USERS_PANEL_STYLE
import logging

logger = logging.getLogger('dialog_gui')

class UsersPanel(QWidget):
    user_selected = pyqtSignal(str, str, int)  # username, host, port - ИЗМЕНЕНО!
    refresh_requested = pyqtSignal()
    call_requested = pyqtSignal(str, str)  # username, call_type
    peer_connect_requested = pyqtSignal(str, int)  # host, port
    peer_disconnect_requested = pyqtSignal(str, int)  # host, port
    
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
        
        # Кнопки звонков
        call_buttons_layout = QHBoxLayout()
        
        self.audio_call_btn = QPushButton("📞 Аудио")
        self.audio_call_btn.setToolTip("Начать аудио звонок")
        self.audio_call_btn.clicked.connect(self.start_audio_call)
        
        self.video_call_btn = QPushButton("📹 Видео")
        self.video_call_btn.setToolTip("Начать видео звонок")
        self.video_call_btn.clicked.connect(self.start_video_call)
        
        call_buttons_layout.addWidget(self.audio_call_btn)
        call_buttons_layout.addWidget(self.video_call_btn)
        
        layout.addLayout(call_buttons_layout)
        
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
        """Контекстное меню для пиров - улучшенная версия"""
        item = self.users_list.itemAt(position)
        if not item:
            return
            
        context_menu = QMenu(self)
        
        # Получаем данные пира
        peer_id = item.data(Qt.UserRole)
        peer_data = self.peers_data.get(peer_id)
    
        if not peer_data:
            return
        
        username = peer_data['username']
        status = peer_data['status']
    
        # Информация о пире
        info_action = QAction(f"Информация о {username}", self)
        info_action.triggered.connect(lambda: self.show_peer_info(peer_data))
        
        context_menu.addAction(info_action)
        context_menu.addSeparator()
    
        # Действия в зависимости от статуса
        if status == 'connected':
            disconnect_action = QAction("🔌 Отключиться", self)
            disconnect_action.triggered.connect(lambda: self.peer_disconnect_requested.emit(host, port))
            context_menu.addAction(disconnect_action)
            
            # Действия для чата и звонков
            chat_action = QAction("💬 Написать сообщение", self)
            chat_action.triggered.connect(lambda: self.user_selected.emit(username, host, port))  # ИЗМЕНЕНО!
            context_menu.addAction(chat_action)
            
            call_menu = context_menu.addMenu("📞 Позвонить")
            
            audio_call_action = QAction("Аудио звонок", self)
            audio_call_action.triggered.connect(lambda: self.call_requested.emit(username, 'audio'))
            call_menu.addAction(audio_call_action)
        
            video_call_action = QAction("Видео звонок", self)
            video_call_action.triggered.connect(lambda: self.call_requested.emit(username, 'video'))
            call_menu.addAction(video_call_action)
            
        else:
            connect_action = QAction("🔗 Подключиться", self)
            connect_action.triggered.connect(lambda: self.peer_connect_requested.emit(host, port))
            context_menu.addAction(connect_action)
        
        # Показываем меню
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
        logger.info("=== ДЕБАГ: Полученные данные для users_panel ===")
        if not users:
            logger.info("Пустой список users")
            return
            
        for i, user in enumerate(users):
            logger.info(f"Пользователь {i}: {user} (тип: {type(user)})")
            if isinstance(user, dict):
                for key, value in user.items():
                    logger.info(f"  {key}: {value} (тип: {type(value)})")
        logger.info("=== КОНЕЦ ДЕБАГА ===")

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
            self.network_status.setText(f"Сеть: ✅ Подключено ({peer_count} пиров)")
            self.network_status.setStyleSheet("""
                font-size: 12px;
                color: #27ae60;
                padding: 4px;
                background-color: #d5f4e6;
                border-radius: 4px;
            """)
        else:
            self.network_status.setText("Сеть: ❌ Не подключено")
            self.network_status.setStyleSheet("""
                font-size: 12px;
                color: #e74c3c;
                padding: 4px;
                background-color: #fadbd8;
                border-radius: 4px;
            """)
        
    def update_users(self, users):
        """Обновление списка пользователей - исправленная версия"""
        self.debug_show_received_data(users)
        try:
            self.users_list.clear()
            self.peers_data.clear()
        
            if not users:
                logger.debug("Получен пустой список пользователей")
                self.update_network_status(False, 0)
                return
                
            logger.info(f"Обновление списка пользователей: получено {len(users)} записей")
            
            connected_count = 0
            processed_peers = set()  # Для отслеживания дубликатов
            
            for user in users:
                try:
                    if isinstance(user, dict):
                        username = user.get('username', 'Неизвестный')
                        host = user.get('host', 'unknown')
                        port = user.get('port', 0)
                        
                        # Создаем уникальный идентификатор пира
                        peer_id = f"{host}:{port}"
                        
                        # Пропускаем дубликаты
                        if peer_id in processed_peers:
                            logger.warning(f"Пропущен дубликат: {username} ({host}:{port})")
                            continue
                            
                        processed_peers.add(peer_id)
                        
                        # Определяем статус
                        status = user.get('status', 'unknown')
                        if status == 'connected':
                            connected_count += 1
                        
                        # Сохраняем данные пира
                        self.peers_data[peer_id] = {
                            'username': username,
                            'host': host,
                            'port': port,
                            'status': status
                        }
                        
                        # Создаем отображаемый текст
                        status_icon = "🟢" if status == 'connected' else "🟡"
                        item_text = f"{status_icon} {username}"
                        
                        # Добавляем тип, если есть
                        user_type = user.get('type')
                        if user_type:
                            item_text += f" [{user_type}]"
                        
                        # СОЗДАЕМ QListWidgetItem ПРАВИЛЬНО
                        item = QListWidgetItem(item_text)
                        item.setData(Qt.UserRole, peer_id)
                        self.users_list.addItem(item)
                        
                        logger.debug(f"Добавлен пользователь: {username} - {status}")
                        
                    elif isinstance(user, str):
                        # Для обратной совместимости - создаем уникальный ID
                        clean_username = user.replace("👤 ", "").replace("💬 ", "")
                        peer_id = f"legacy_{clean_username}_{len(processed_peers)}"
                        
                        if peer_id in processed_peers:
                            continue
                            
                        processed_peers.add(peer_id)
                        
                        self.peers_data[peer_id] = {
                            'username': clean_username,
                            'host': 'unknown',
                            'port': 0,
                            'status': 'connected'
                        }
                        
                        item = QListWidgetItem(f"👤 {clean_username}")
                        item.setData(Qt.UserRole, peer_id)
                        self.users_list.addItem(item)
                        
                        connected_count += 1
                        logger.debug(f"Добавлен пользователь (устаревший формат): {clean_username}")
                
                except Exception as e:
                    logger.error(f"Ошибка обработки пользователя {user}: {e}")
                    continue
        
            # Обновляем статус сети
            self.update_network_status(connected_count > 0, connected_count)
            logger.info(f"Обновлено: {len(self.peers_data)} пользователей, {connected_count} подключено")
        
        except Exception as e:
            logger.error(f"Критическая ошибка обновления списка пользователей: {e}")
            # В случае ошибки очищаем список
            self.users_list.clear()
            self.update_network_status(False, 0)