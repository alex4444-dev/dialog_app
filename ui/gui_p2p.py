# gui_p2p.py
import sys
import os
import threading
import time
import logging
import socket

from typing import List, Dict, Tuple
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QAction, QMenu, 
                             QMessageBox, QStatusBar, QTextEdit, QDialog,
                             QSystemTrayIcon, QStyle, QDesktopWidget)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QIcon

# Добавляем путь к текущей директории для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from network.p2p_network import P2PNetworkClient
    from auth_window import AuthWindow
    from users_panel import UsersPanel
    from chat_window import ChatWindow
    from notifications import NotificationWindow
    from settings_window import SettingsDialog
    from call_window import CallWindow
    from video_window import VideoCallWindow
    from storage.database import ClientDatabase
    from core.auth_manager import AuthManager
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все файлы находятся в правильной структуре папок")
    sys.exit(1)

# Импортируем стили
try:
    from styles.main_style import MAIN_WINDOW_STYLE
except ImportError as e:
    print(f"Ошибка импорта стилей: {e}")
    MAIN_WINDOW_STYLE = ""

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('dialog_gui')

class P2PMainWindow(QMainWindow):
    # Сигналы для межпоточного общения
    peer_connected = pyqtSignal(str, int)  # host, port
    peer_disconnected = pyqtSignal(str, int)  # host, port
    network_status_changed = pyqtSignal(bool, int)  # is_connected, peer_count
    sig_message_received = pyqtSignal(str, str)
    sig_user_list_updated = pyqtSignal(list)
    sig_connection_status = pyqtSignal(str)
    sig_message_status = pyqtSignal(str, str)
    sig_call_received = pyqtSignal(str, str, str, str)
    sig_system_message = pyqtSignal(str)
    sig_call_status = pyqtSignal(str, str)
    
    def __init__(self, p2p_client, username, db):
        super().__init__()
        self.p2p_client = p2p_client
        self.username = username
        self.db = db
        self.auth_manager = AuthManager(db)
        self.active_chats = {}
        self.is_authenticated = True
        self.pending_messages = {}
        self.notifications_enabled = True
        self.active_notifications = []
        self.peers_data = {}
        # Инициализация P2P обработчиков
        self.logger = logging.getLogger('dialog_gui')
        # Для медиа-соединений звонков
        self.media_connections = {}

        # Для звонков
        self.active_calls = {}
        self.pending_calls = {}

        # Для хранения сокетов звонков
        self.call_sockets = {}  # Словарь для хранения сокетов по call_id
        self.calls_lock = threading.Lock()
        
        self.settings = QSettings('DialogApp', 'P2PClient')
        self.audio_input_device = self.settings.value('audio_input_device', None, type=int)
        self.audio_output_device = self.settings.value('audio_output_device', None, type=int)

        # Таймеры для обновлений
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_update_timer)
        
        # Подключаем сигналы P2P клиента
        self.connect_p2p_signals()
        
        # Подключаем собственные сигналы
        self.sig_message_received.connect(self.handle_message)
        self.sig_user_list_updated.connect(self.update_user_list)
        self.sig_connection_status.connect(self.update_connection_status)
        self.sig_message_status.connect(self.handle_message_status)
        self.sig_call_received.connect(self.handle_call)
        self.sig_system_message.connect(self.on_system_message)
        self.sig_call_status.connect(self.on_call_status)
        self.chat_windows = {}

        #if hasattr(self.p2p_client, 'message_received'):
        #    self.p2p_client.message_received.connect(self.handle_received_message)

        self.init_ui()      
    
    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle(f'💬 ДИАЛОГ - Коммуникационная платформа (Пользователь: {self.username})')
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # Левая панель - пользователи
        self.users_panel = UsersPanel()
        # Обновляем подключение сигналов панели пользователей
        self.users_panel.user_selected.connect(self.open_chat)
        self.users_panel.refresh_requested.connect(self.refresh_user_list)
        self.users_panel.call_requested.connect(self.start_call)
        # Добавляем новые сигналы для P2P управления
        self.users_panel.peer_connect_requested.connect(self.connect_to_peer)
        self.users_panel.peer_disconnect_requested.connect(self.disconnect_from_peer)
        
        self.users_panel.setFixedWidth(280)
        main_layout.addWidget(self.users_panel)
        
        # Правая панель - чаты
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_chat_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)
        
        
        # Создаем системную вкладку
        self.create_system_tab()
        
        # Панель меню
        self.create_menu()
        
        # Статус бар
        self.statusBar().showMessage(f'✅ В сети: Подключено как {self.username}')
        
        # Создаем системный трей
        self.setup_system_tray()
        
        # Запускаем работу ком. платформы ДИАЛОГ с задержкой
        QTimer.singleShot(1000, self.start_p2p_messaging)
        
        logger.info("P2P интерфейс инициализирован")

    def show_audio_settings(self):
        """Показать окно настроек аудио"""
        try:
            dialog = SettingsDialog(parent=self,
                                    input_device=self.audio_input_device,
                                    output_device=self.audio_output_device)
            # Подключаем сигнал для получения изменённых настроек
            dialog.settings_changed.connect(self.on_settings_changed)
            dialog.exec_()
        except Exception as e:
            logger.error(f"Ошибка открытия окна настроек: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть окно настроек:\n{e}")

    def on_settings_changed(self, settings):
        """Обновляет настройки аудио в главном окне и во всех активных звонках"""
        if not isinstance(settings, dict):
            logger.warning("on_settings_changed: передан некорректный объект, ожидался dict")
            return

        new_input = settings.get('input_device')
        new_output = settings.get('output_device')

        # Обновляем в главном окне
        self.audio_input_device = new_input
        self.audio_output_device = new_output

        # Сохраняем в QSettings
        self.settings.setValue('audio_input_device', new_input)
        self.settings.setValue('audio_output_device', new_output)
        self.settings.sync()

        logger.info(f"Главное окно: обновлены настройки аудио: ввод={new_input}, вывод={new_output}")

        # Обновляем устройства во всех активных окнах звонков
        updated_count = 0
        for call_id, info in self.active_calls.items():
            window = info.get('window')
            if window:
                window.input_device = new_input
                window.output_device = new_output
                logger.debug(f"Звонок {call_id}: устройства обновлены (ввод={new_input}, вывод={new_output})")
                updated_count += 1

        if updated_count > 0:
            logger.info(f"Настройки аудио переданы в {updated_count} активных звонков. "
                        "Для применения изменений может потребоваться перезапуск звонка.")
        else:
            logger.info("Активных звонков нет, настройки сохранены.")

    def _finalize_call_accept(self, call_id, call_window):
        """Завершающая стадия принятия звонка"""
        try:
            # Проверяем, установлен ли сокет
            if not call_window.socket_set:
                logger.warning(f"⚠️ Сокет для звонка {call_id} еще не установлен")
                
                # Пробуем получить сокет из P2P клиента
                if self.p2p_client:
                    call_socket = self.p2p_client.get_call_socket(call_id)
                    if call_socket:
                        call_window.set_call_socket(call_socket)
            
            # Запускаем звонок в UI
            call_window.accept_call()
            
            self.system_chat.append(f"✅ Звонок с {call_window.username} принят")
            logger.info(f"✅ Звонок {call_id} принят")
            
        except Exception as e:
            logger.error(f"❌ Ошибка финализации принятия звонка: {e}")    
        
    def setup_system_tray(self):
        """Настройка системного трея"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
            self.tray_icon.setToolTip("Диалог - P2P Мессенджер")
            
            # Создаем контекстное меню для трея
            tray_menu = QMenu()
            
            show_action = tray_menu.addAction("Показать/Скрыть")
            show_action.triggered.connect(self.toggle_window)
            
            tray_menu.addSeparator()
            
            exit_action = tray_menu.addAction("Выход")
            exit_action.triggered.connect(self.close_application)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_icon_activated)
            self.tray_icon.show()
            
            logger.info("Системный трей инициализирован")
        else:
            self.tray_icon = None
            logger.warning("Системный трей недоступен")
            
    def create_system_tab(self):
        """Создание системной вкладки для сообщений"""
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.setContentsMargins(12, 12, 12, 12)
        
        self.system_chat = QTextEdit()
        self.system_chat.setReadOnly(True)
        system_layout.addWidget(self.system_chat)
        
        self.tabs.addTab(system_tab, "📊 P2P Система")
        
    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu('Файл')

        refresh_action = QAction('🔄 Обновить список пользователей', self)
        refresh_action.triggered.connect(self.refresh_user_list)
        file_menu.addAction(refresh_action)
        
        # Добавляем действие диагностики
        debug_action = QAction('🔍 Диагностика P2P', self)
        debug_action.triggered.connect(self.debug_p2p_structure)
        file_menu.addAction(debug_action)
        
        file_menu.addSeparator()
        
        # Добавляем действие для добавления пира
        add_peer_action = QAction('➕ Добавить пир вручную', self)
        add_peer_action.triggered.connect(self.show_add_peer_dialog)
        file_menu.addAction(add_peer_action)

        # В меню Файл добавьте:
        force_connect_action = QAction('🔗 Принудительно подключиться к пирам', self)
        force_connect_action.triggered.connect(self.force_connect_peers)
        file_menu.addAction(force_connect_action)
        
        # Команда для вызова Окна настроек
        settings_action = QAction('⚙️ Настройки', self)
        settings_action.triggered.connect(self.show_audio_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        # Уведомления
        notifications_menu = file_menu.addMenu('🔔 Уведомления')
        
        self.enable_notifications_action = QAction('Включить уведомления', self, checkable=True)
        self.enable_notifications_action.setChecked(True)
        self.enable_notifications_action.triggered.connect(self.toggle_notifications)
        notifications_menu.addAction(self.enable_notifications_action)
        
        file_menu.addSeparator()
        
        # Выход из системы
        logout_action = QAction('🚪 Выйти из системы', self)
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        # Выход из приложения
        exit_action = QAction('❌ Выйти', self)
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)
        
        # Меню Сеть
        network_menu = menubar.addMenu('🌐 Сеть')
        
        network_info_action = QAction('📊 Информация о сети', self)
        network_info_action.triggered.connect(self.show_network_info)
        network_menu.addAction(network_info_action)
        
        peers_action = QAction('👥 Список пиров', self)
        peers_action.triggered.connect(self.show_peers_list)
        network_menu.addAction(peers_action)
        
        # Меню Аккаунт
        account_menu = menubar.addMenu('👤 Аккаунт')
        
        profile_action = QAction('👤 Мой профиль', self)
        profile_action.triggered.connect(self.show_profile)
        account_menu.addAction(profile_action)

    def setup_p2p_integration(self):
        """Интеграция с P2P сетью - безопасная версия"""
        try:
            self.system_chat.append("🔧 Настройка интеграции с P2PNetworkClient...")
            
            # Проверяем, что P2P клиент доступен и работает
            if not hasattr(self, 'p2p_client') or self.p2p_client is None:
                self.system_chat.append("❌ P2P клиент не доступен")
                return
            
            if not hasattr(self.p2p_client, 'is_running') or not self.p2p_client.is_running:
                self.system_chat.append("❌ P2P клиент не запущен")
                return
        
            # Запускаем диагностику
            self.debug_p2p_structure()

            # Создаем таймер для обновления списка пиров, если его нет
            if not hasattr(self, 'peer_update_timer'):
                self.peer_update_timer = QTimer()
                self.peer_update_timer.timeout.connect(self.update_peers_from_p2p)
        
            # Запускаем обновление каждые 10 секунд
            self.peer_update_timer.start(10000)
        
            # Первоначальное обновление
            QTimer.singleShot(1000, self.update_peers_from_p2p)
            self.system_chat.append("✅ P2P интеграция настроена")
            self.statusBar().showMessage("✅ P2P сеть активна")

        except Exception as e:
            error_msg = f"❌ Ошибка настройки P2P интеграции: {e}"
            self.logger.error(f"Ошибка настройки P2P интеграции: {e}")
            self.system_chat.append(error_msg)

    def debug_p2p_structure(self):
        """Отладочная информация о структуре P2PNetworkClient"""
        try:
            self.system_chat.append("🔍 Диагностика P2PNetworkClient:")
            
            if not hasattr(self, 'p2p_client'):
                self.system_chat.append("  ❌ p2p_client не существует")
                return
                
            p2p_client = self.p2p_client
            self.system_chat.append(f"  ✅ p2p_client: {type(p2p_client)}")
            
            # Проверяем основные атрибуты P2PNetworkClient
            attrs = ['connected_peers', 'known_peers', 'start', 'stop', 'is_running', 'bootstrap_connected', 'port']
            for attr in attrs:
                if hasattr(p2p_client, attr):
                    value = getattr(p2p_client, attr)
                    if callable(value):
                        self.system_chat.append(f"  ✅ {attr}: метод")
                    elif hasattr(value, '__len__'):
                        self.system_chat.append(f"  ✅ {attr}: {len(value)} элементов")
                    else:
                        self.system_chat.append(f"  ✅ {attr}: {value}")
                else:
                    self.system_chat.append(f"  ❌ {attr}: отсутствует")
            
            # Детальная информация о connected_peers
            if hasattr(p2p_client, 'connected_peers'):
                connected_peers = p2p_client.connected_peers
                self.system_chat.append(f"  📊 connected_peers: {len(connected_peers)} элементов")
                if len(connected_peers) > 0:
                    for i, peer in enumerate(list(connected_peers)[:3]):  # Показываем первые 3
                        self.system_chat.append(f"    {i+1}. {peer} (тип: {type(peer)})")
                        if hasattr(peer, 'host') and hasattr(peer, 'port'):
                            self.system_chat.append(f"      host: {peer.host}, port: {peer.port}")
                        elif isinstance(peer, tuple) and len(peer) == 2:
                            self.system_chat.append(f"      host: {peer[0]}, port: {peer[1]}")
                else:
                    self.system_chat.append("    📭 Список пуст")
            
            # Детальная информация о known_peers
            if hasattr(p2p_client, 'known_peers'):
                known_peers = p2p_client.known_peers
                self.system_chat.append(f"  📊 known_peers: {len(known_peers)} элементов")
                if len(known_peers) > 0:
                    for i, peer in enumerate(list(known_peers)[:3]):  # Показываем первые 3
                        self.system_chat.append(f"    {i+1}. {peer} (тип: {type(peer)})")
                        if isinstance(peer, tuple) and len(peer) == 2:
                            self.system_chat.append(f"      host: {peer[0]}, port: {peer[1]}")
                else:
                    self.system_chat.append("    📭 Список пуст")
                    
        except Exception as e:
            self.system_chat.append(f"❌ Ошибка диагностики: {e}")

    def handle_message(self, username, message):
        """Обработка полученного сообщения"""
        logger.info(f"P2PMainWindow.handle_message: Получено сообщение от {username}: {message}")
        
        self.system_chat.append(f"📨 Получено сообщение от {username}: {message}")
        
        if username == "system":
            self.system_chat.append(f"📢 Система: {message}")
            return
            
        if not self.isActiveWindow() or self.isMinimized():
            self.show_notification(f"💬 Новое сообщение от {username}", message)
            
        if username not in self.chat_windows:
            self.open_chat(username)
        
        if username in self.chat_windows:
            logger.info(f"P2PMainWindow.handle_message: Добавление сообщения в чат с {username}")
            chat_window = self.chat_windows[username]
            
            if chat_window and hasattr(chat_window, 'add_message'):
                current_index = self.tabs.currentIndex()
                current_widget = self.tabs.widget(current_index)
                is_active = current_widget == chat_window
                
                chat_window.set_active(is_active)
                chat_window.add_message(username, message, is_own=False)
                
                if not is_active:
                    index = self.tabs.indexOf(chat_window)
                    if index >= 0:
                        logger.info(f"P2PMainWindow.handle_message: Вкладка чата с {username} не активна")
                else:
                    logger.info(f"P2PMainWindow.handle_message: Вкладка чата с {username} активна")
            else:
                logger.error(f"P2PMainWindow.handle_message: Чат с {username} не инициализирован правильно")
        else:
            logger.error(f"P2PMainWindow.handle_message: Не удалось найти чат с {username}")
            self.system_chat.append(f"❌ Ошибка: не удалось открыть чат с {username}")
            
        QApplication.processEvents()
        logger.info(f"P2PMainWindow.handle_message: Обработка сообщения от {username} завершена")

    def handle_media_info(self, call_id):
        """Обработка информации о медиа-соединении"""
        try:
            logger.info(f"🔊 Получена информация о медиа для звонка {call_id}")
            
            if call_id not in self.active_calls:
                logger.error(f"❌ Звонок {call_id} не найден в активных")
                return
            
            call_info = self.active_calls[call_id]
            username = call_info['username']
            call_window = call_info['window']
            
            # Получаем информацию о медиа-порте из P2P клиента
            if hasattr(self.p2p_client, 'call_requests') and call_id in self.p2p_client.call_requests:
                media_info = self.p2p_client.call_requests[call_id]
                media_port = media_info.get('media_port')
                media_host = media_info.get('media_host')
                
                logger.info(f"🔊 Подключение к медиа {media_host}:{media_port} для звонка {call_id}")
                
                # Подключаемся к медиа-серверу
                if self.p2p_client.connect_to_media(call_id, media_port, media_host):
                    logger.info(f"✅ Успешное подключение к медиа для звонка {call_id}")
                    
                    # Получаем сокет и устанавливаем в окне
                    media_socket = self.p2p_client.get_media_socket(call_id)
                    if media_socket:
                        # В зависимости от типа звонка устанавливаем соответствующий сокет
                        if call_info.get('type') == 'video':
                            # Для видеозвонка медиа-сокет относится к аудио
                            if hasattr(call_window, 'set_audio_socket'):
                                success = call_window.set_audio_socket(media_socket)
                                logger.info(f"🎥 Аудио-сокет установлен в окне видеозвонка {call_id}")
                            else:
                                logger.warning(f"⚠️ У окна видеозвонка нет метода set_audio_socket")
                                success = False
                        else:
                            # Для аудиозвонка
                            success = call_window.set_call_socket(media_socket)
                        
                        if success:
                            logger.info(f"✅ Медиа-сокет установлен в окне звонка {call_id}")
                            
                            # Если окно ещё не активно (для исходящего звонка), запускаем его
                            if hasattr(call_window, 'is_active') and not call_window.is_active:
                                call_window.start_call()
                        else:
                            logger.error(f"❌ Не удалось установить медиа-сокет")
                    else:
                        logger.error(f"❌ Не удалось получить медиа-сокет")
                else:
                    logger.error(f"❌ Не удалось подключиться к медиа для звонка {call_id}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки медиа-информации: {e}")

    def handle_received_message(self, sender_username, message, host=None, port=None):
        """Обработчик входящих сообщений"""
        try:
            logger.info(f"P2PMainWindow.handle_received_message: Получено сообщение от {sender_username}: {message}")
            
            # Создаем ключ для поиска чата
            user_key = f"{sender_username}"
        
            # Если чат уже открыт, добавляем сообщение
            if user_key in self.chat_windows:
                chat_window = self.chat_windows[user_key]
                chat_window.add_message(sender_username, message, is_own=False)
            else:
                # Если чат не открыт, создаем его
                self.open_chat(sender_username, host, port)
                # Добавляем сообщение после создания чата
                if user_key in self.chat_windows:
                    self.chat_windows[user_key].add_message(sender_username, message, is_own=False)
                    
            logger.info(f"P2PMainWindow.handle_received_message: Сообщение обработано")
            
        except Exception as e:
            logger.error(f"P2PMainWindow.handle_received_message: Ошибка обработки сообщения: {e}")

    def force_connect_peers(self):
        """Принудительное подключение к известным пирам"""
        try:
            if hasattr(self.p2p_client, '_auto_connect_to_known_peers'):
                self.p2p_client._auto_connect_to_known_peers()
                self.system_chat.append("🔄 Принудительное подключение к известным пирам...")
            else:
                self.system_chat.append("❌ Метод автоматического подключения не доступен")
        except Exception as e:
            self.system_chat.append(f"❌ Ошибка принудительного подключения: {e}")

    def update_user_list(self, users):
        """Обновление списка пользователей"""
        self.logger.info(f"P2PMainWindow.update_user_list: Обновление списка пользователей: {len(users) if users else 0} пользователей")

        # Логируем первые несколько пользователей для отладки
        if users:
            for i, user in enumerate(users[:3]):  # Первые 3
                self.logger.info(f"Пользователь {i}: {user}")

        try:
            # Преобразуем данные в правильный формат
            peers_data = []
        
            if users:
                for user in users:
                    if isinstance(user, dict):
                        # Проверяем разные возможные форматы данных
                        if 'username' in user and 'address' in user:
                            # Формат из P2PNetwork.get_online_users()
                            username = user['username']
                            address = user['address']
                        
                            # Парсим адрес
                            if address == 'local':
                                # Это текущий пользователь, пропускаем
                                continue
                            elif ':' in address:
                                host, port_str = address.split(':', 1)
                                try:
                                    port = int(port_str)
                                except ValueError:
                                    port = 0
                            else:
                                host = 'unknown'
                                port = 0
                            
                            peers_data.append({
                                'username': username,
                                'host': host,
                                'port': port,
                                'status': 'connected'
                            })
                        elif 'username' in user and 'host' in user and 'port' in user:
                            # Уже правильный формат
                            peers_data.append(user)
                        else:
                            self.logger.warning(f"Неизвестный формат пользователя: {user}")
                    elif isinstance(user, str):
                        # Старый формат строки
                        clean_username = user.replace("👤 ", "")
                        peers_data.append({
                            'username': clean_username,
                            'host': 'unknown',
                            'port': 0,
                            'status': 'connected'
                        })
        
            # Обновляем UI с преобразованными данными
            self.update_user_list_with_peers(peers_data)
        
        except Exception as e:
            self.logger.error(f"Ошибка в update_user_list: {e}")
            # В случае ошибки показываем пустой список
            self.users_panel.update_users([])
    
    def update_connection_status(self, status):
        """Обновление статуса соединения"""
        self.statusBar().showMessage(status)
        if hasattr(self, 'system_chat'):
            self.system_chat.append(f"{status}")

    def handle_message_status(self, status, details):
        """Обработка статуса доставки сообщения"""
        self.logger.info(f"P2PMainWindow.handle_message_status: Обработка статуса сообщения: {status} - {details}")
        if hasattr(self, 'system_chat'):
            if status == "delivered":
                self.system_chat.append(f"✅ Сообщение доставлено: {details}")
            elif status == "failed":
                self.system_chat.append(f"❌ Ошибка доставки: {details}")
            elif status == "user_offline":
                self.system_chat.append(f"⚠️ Пользователь offline: {details}")
            elif status == "error":
                self.system_chat.append(f"⚠️ Ошибка: {details}")
   
    def handle_call(self, action, from_user, call_type, call_id):
        """Обработка входящего звонка через P2P сеть"""
        logger.info(f"P2PMainWindow.handle_call: Обработка звонка: {action} от {from_user}, тип: {call_type}, ID: {call_id}")

        self.system_chat.append(f"🔊 Сигнал звонка: {action} от {from_user}")

        if action == 'incoming_call':
            if call_type == 'video':
                self.handle_incoming_video_call(from_user, call_id)
            else:
                self.handle_incoming_call_request(from_user, call_type, call_id)
                
        elif action == 'outgoing_call':
            # Ничего не делаем, окно уже создано в start_video_call
            logger.debug(f"Игнорируем outgoing_call для {call_id}")
                
        elif action == 'call_accepted':
            self.handle_call_accepted(from_user, call_id)
            
        elif action == 'call_rejected':
            self.handle_call_rejected(from_user, call_id)
            
        elif action == 'call_ended':
            self.handle_call_ended(from_user, call_id)

        elif action == 'media_info':
            self.handle_media_info(call_id)    
        
        elif action == 'call_info':
            self.handle_call_info(from_user, call_id)

        else:
            logger.warning(f"🔊 Неизвестное действие звонка: {action}")
            
    def on_system_message(self, message):
        """Обработчик системных сообщений в главном потоке"""
        if hasattr(self, 'system_chat'):
            self.system_chat.append(message)
   
    def on_call_status(self, call_id, action):
        """Обработчик статусов звонков в главном потоке"""
        if call_id not in self.active_calls:
            return
            
        call_info = self.active_calls[call_id]
        call_window = call_info['window']
        
        if action == "accept_call":
            call_window.accept_call()
        elif action == "start_call":
            call_window.start_call()
        elif action == "setup_audio":
            if hasattr(self.p2p_client, 'get_media_socket'):
                call_socket = self.p2p_client.get_media_socket(call_id)
                if call_socket:
                    call_window.call_socket = call_socket
                    call_window.initialize_audio_streams()
                    if hasattr(self, 'system_chat'):
                        self.system_chat.append("✅ Аудио соединение установлено")
    
    def on_video_socket_ready(self, call_id, client_socket):
        """Обновить видео-сокет в окне звонка после установки соединения"""
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            video_window = call_info['window']
            if hasattr(video_window, 'set_video_socket'):
                video_window.set_video_socket(client_socket)
                logger.info(f"✅ Видео-сокет обновлён на клиентский для звонка {call_id}")
            else:
                logger.warning(f"Окно звонка {call_id} не имеет метода set_video_socket")
        else:
            logger.warning(f"Звонок {call_id} не найден в активных при получении видео-сокета")

    def open_chat(self, username, host=None, port=None):
        """Открытие чата с пользователем"""
        try:
            logger.info(f"P2PMainWindow.open_chat: Начало открытия чата с {username}")

            # Очищаем имя от возможных лишних символов
            clean_username = username.replace("👤 ", "").replace("💬 ", "").strip()

            # КЛЮЧ – ТОЛЬКО ИМЯ ПОЛЬЗОВАТЕЛЯ, без IP:порта
            user_key = clean_username

            # Если чат с таким именем уже открыт – просто активируем вкладку
            if user_key in self.chat_windows:
                chat_window = self.chat_windows[user_key]
                index = self.tabs.indexOf(chat_window)
                if index >= 0:
                    self.tabs.setCurrentIndex(index)
                    chat_window.set_active(True)
                logger.info(f"P2PMainWindow.open_chat: Чат с {clean_username} уже открыт")
                return

            # Создаём новый чат (host и port передаются только для информации, если нужны)
            logger.info(f"P2PMainWindow.open_chat: Создание нового чата с {clean_username}")
            chat_window = ChatWindow(clean_username, host, port)

            # Подключаем сигналы
            chat_window.message_sent.connect(self.on_message_sent)
            chat_window.unread_count_changed.connect(self.on_unread_count_changed)
            chat_window.call_requested.connect(self.on_call_requested)

            # Добавляем вкладку
            tab_index = self.tabs.addTab(chat_window, f"💬 {clean_username}")
            self.tabs.setCurrentIndex(tab_index)

            # Сохраняем в общий словарь окон чатов
            self.chat_windows[user_key] = chat_window

            logger.info(f"P2PMainWindow.open_chat: Чат с {clean_username} успешно создан (ключ: {user_key})")

        except Exception as e:
            logger.error(f"P2PMainWindow.open_chat: Ошибка открытия чата: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def on_tab_changed(self, index):
        """Обработчик изменения активной вкладки"""
        try:
            if index == -1:  # Нет активных вкладок
                return
                
            # Получаем текущий виджет
            current_widget = self.tabs.widget(index)
            
            # Если это ChatWindow, устанавливаем его активным
            if isinstance(current_widget, ChatWindow):
                current_widget.set_active(True)
                logger.info(f"P2PMainWindow.on_tab_changed: Активирована вкладка чата с {current_widget.username}")
            
            # Деактивируем все остальные вкладки чатов
            for i in range(self.tabs.count()):
                if i != index:
                    widget = self.tabs.widget(i)
                    if isinstance(widget, ChatWindow):
                        widget.set_active(False)
                        
        except Exception as e:
            logger.error(f"P2PMainWindow.on_tab_changed: Ошибка: {e}")

    def close_chat_tab(self, index):
        if index == 0:  # Не закрываем системную вкладку
            return
            
        widget = self.tabs.widget(index)
        if widget is None:
            return
        username = None
        # Получаем имя пользователя из атрибута виджета
        if hasattr(widget, 'username'):
            username = widget.username
    
        # Удаляем из словарей
        if username:
            if username in self.active_chats:
                del self.active_chats[username]
            if username in self.chat_windows:
                del self.chat_windows[username]
            logger.info(f"P2PMainWindow.close_chat_tab: Закрыт чат с {username}")
        
        self.tabs.removeTab(index)

    def update_tab_title(self, username, unread_count):
        """Обновление заголовка вкладки с непрочитанными"""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if hasattr(widget, 'username') and widget.username == username:
                unread_text = f" ({unread_count}📩)" if unread_count > 0 else ""
                self.tabs.setTabText(i, f"💬 {username}{unread_text}")
                break
        
    def on_message_sent(self, username, message):
        """Обработчик отправки сообщения из чата"""
        try:
            logger.info(f"P2PMainWindow.on_message_sent: Отправка сообщения для {username}: {message}")
            # Вызываем метод отправки сообщения из P2P клиента
            if hasattr(self, 'p2p_client') and self.p2p_client:
                self.p2p_client.send_message(username, message)
            else:
                logger.error("P2PMainWindow.on_message_sent: P2P клиент не доступен")
        except Exception as e:
            logger.error(f"P2PMainWindow.on_message_sent: Ошибка отправки сообщения: {e}")

    def get_call_socket(self, call_id):
        """Получить сокет для звонка по его ID"""
        try:
            logger.info(f"🔍 Запрос сокета для звонка {call_id}")
            
            # Проверяем в словаре call_sockets
            if call_id in self.call_sockets:
                socket = self.call_sockets[call_id]
                if socket:
                    logger.info(f"✅ Сокет найден в call_sockets для звонка {call_id}")
                    return socket
        
            # Проверяем в активных звонках
            if call_id in self.active_calls:
                call_info = self.active_calls[call_id]

                # Сначала проверяем поле 'socket'
                if 'socket' in call_info and call_info['socket']:
                    logger.info(f"✅ Сокет найден в active_calls для звонка {call_id}")
                    return call_info['socket']
            
                # Затем проверяем, есть ли сокет в окне
                if 'window' in call_info and call_info['window']:
                    window = call_info['window']
                    if hasattr(window, 'call_socket') and window.call_socket:
                        logger.info(f"✅ Сокет найден в окне звонка {call_id}")
                        return window.call_socket

            # Пробуем получить от P2P клиента
            if hasattr(self.p2p_client, 'get_call_socket'):
                try:
                    socket = self.p2p_client.get_call_socket(call_id)
                    if socket:
                        logger.info(f"✅ Сокет получен от P2P клиента для звонка {call_id}")
                        return socket
                except Exception as e:
                    logger.error(f"❌ Ошибка получения сокета от P2P клиента: {e}")
            
            logger.warning(f"⚠️ Сокет не найден для звонка {call_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в get_call_socket: {e}")
            return None

    def force_setup_socket(self, call_id):
        """Принудительная установка сокета для звонка"""
        try:
            logger.info(f"🔄 Принудительная установка сокета для звонка {call_id}")
            
            if call_id not in self.active_calls:
                logger.error(f"❌ Звонок {call_id} не найден")
                return False
                
            call_info = self.active_calls[call_id]
            call_window = call_info.get('window')
            
            if not call_window:
                logger.error(f"❌ Окно звонка {call_id} не найдено")
                return False
                
            # Если сокет уже установлен, ничего не делаем
            if hasattr(call_window, 'socket_set') and call_window.socket_set:
                logger.info(f"✅ Сокет уже установлен для звонка {call_id}")
                return True
                
            # Получаем сокет
            socket = self.get_call_socket(call_id)
            if not socket:
                logger.error(f"❌ Не удалось получить сокет для звонка {call_id}")
                return False
                
            # Устанавливаем сокет
            success = call_window.set_call_socket(socket)
            if success:
                logger.info(f"✅ Сокет принудительно установлен для звонка {call_id}")
                return True
            else:
                logger.error(f"❌ Не удалось принудительно установить сокет для звонка {call_id}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка принудительной установки сокета: {e}")
            return False

    def _set_audio_socket_with_retry(self, video_window, call_id, timeout=5):
        """Ожидает появления клиентского аудио-сокета и устанавливает его в окно видеозвонка"""
        def wait_and_set():
            try:
                client_sock = self.p2p_client.wait_for_call_socket(call_id, timeout=timeout)
                if client_sock:
                    video_window.set_audio_socket(client_sock)
                    logger.info(f"✅ Аудио-сокет для звонка {call_id} установлен")
                else:
                    logger.error(f"❌ Не удалось получить клиентский аудио-сокет для звонка {call_id}")
                    video_window.status_label.setText("❌ Ошибка: аудио не работает")
            except Exception as e:
                logger.error(f"Ошибка в _set_audio_socket_with_retry: {e}")
        threading.Thread(target=wait_and_set, daemon=True).start()

    def show_incoming_call(self, call_id, from_user, call_type):
        """Показать окно входящего звонка"""
        try:
            logger.info(f"=== ПОКАЗ ВХОДЯЩЕГО ЗВОНКА {call_id} ===")
            
            # Создаем окно звонка
            call_window = CallWindow(from_user, call_type, call_id, is_outgoing=False, parent=self, input_device=self.audio_input_device, output_device=self.audio_output_device)
            call_window.connection_established.connect(call_window.initialize_audio_streams)
            call_window.call_ended.connect(self.end_call)
            
            # Сохраняем в активных звонках
            self.active_calls[call_id] = {
                'window': call_window,
                'username': from_user,
                'type': call_type,
                'outgoing': False
            }
            
            # Показываем окно
            call_window.show()
            call_window.raise_()
            call_window.activateWindow()
            
            logger.info(f"✅ Окно входящего звонка показано")
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа входящего звонка: {e}")

    def handle_duplicate_usernames(self, username, host, port):
        """Обработка ситуаций с одинаковыми именами пользователей"""
        # Можно добавить суффикс или предупреждение
        logger.warning(f"Обнаружен пользователь с существующим именем: {username}")
        
        # Временное решение - добавляем суффикс с портом
        unique_username = f"{username}_{port}"
        return unique_username

    def on_unread_count_changed(self, username, unread_count):
        """Обработчик изменения количества непрочитанных сообщений"""
        try:
            logger.info(f"P2PMainWindow.on_unread_count_changed: Для {username} непрочитанных: {unread_count}")
            # Здесь можно обновить счетчик непрочитанных в интерфейсе
        except Exception as e:
            logger.error(f"P2PMainWindow.on_unread_count_changed: Ошибка: {e}")

    def on_call_requested(self, username, call_type):
        try:
            logger.info(f"P2PMainWindow.on_call_requested: Запрос {call_type} звонка для {username}")
            # Проверяем, нет ли уже активного звонка с этим пользователем
            for call_id, info in self.active_calls.items():
                if info.get('username') == username:
                    QMessageBox.information(self, "Звонок уже активен", 
                                            f"У вас уже есть активный звонок с {username}")
                    return
            # Если тип 'video', вызываем видеозвонок, иначе аудио
            if call_type == 'video':
                self.start_video_call(username)
            else:
                self.start_call(username, call_type)
        except Exception as e:
            logger.error(f"P2PMainWindow.on_call_requested: Ошибка запроса звонка: {e}")

    def update_peers_from_p2p(self):
        """Обновление информации о пирах - работаем напрямую с P2PNetworkClient"""
        try:
            peers_data = []
            
            # Проверяем доступность P2P клиента
            if not hasattr(self, 'p2p_client') or self.p2p_client is None:
                self.system_chat.append("❌ P2P клиент не инициализирован")
                return
            
            p2p_client = self.p2p_client
        
            # Получаем подключенные пиры (исключая bootstrap)
            connected_peers = []
            if hasattr(p2p_client, 'connected_peers'):
                try:
                    connected_peers = list(p2p_client.connected_peers)
                    # Фильтруем bootstrap узлы
                    connected_peers = [
                        peer for peer in connected_peers 
                        if not self._is_bootstrap_peer(peer, p2p_client)
                    ]
                    self.system_chat.append(f"📊 Найдено {len(connected_peers)} подключенных пиров (исключая bootstrap)")
                except Exception as e:
                    self.logger.warning(f"Ошибка получения connected_peers: {e}")
            
            # Остальной код обработки пиров...
            # [существующий код метода]
            
        except Exception as e:
            self.logger.error(f"Ошибка получения информации о пирах: {e}")

    def _is_bootstrap_peer(self, peer, p2p_client):
        try:
            if isinstance(peer, str):
                host, port_str = peer.split(':')
                port = int(port_str)
            else:
                host = peer.get('host')
                port = peer.get('port')
            for node in p2p_client.bootstrap_nodes:
                if host == node['host'] and port == node['port']:
                    return True
        except:
            pass
        return False

    def update_user_list_with_peers(self, peers_data):
        """Обновление списка пользователей с данными о пирах"""
        try:
            # Сохраняем данные о пирах
            self.peers_data.clear()
            for peer in peers_data:
                peer_id = f"{peer['host']}:{peer['port']}"
                self.peers_data[peer_id] = peer
    
            # Обновляем панель пользователей
            if hasattr(self, 'users_panel'):
                self.users_panel.update_users(peers_data)
    
            # Обновляем статус сети
            connected_count = len([p for p in peers_data if p.get('status') == 'connected'])
            is_connected = connected_count > 0 or len(peers_data) > 0
            self.update_network_status(is_connected, connected_count)
        
            # Логируем результат
            self.logger.info(f"Обновлено {len(peers_data)} пиров (подключено: {connected_count})")
        
        except Exception as e:
            self.logger.error(f"Ошибка: {e}")
            if hasattr(self, 'system_chat'):
                self.system_chat.append(f"⚠️ Ошибка обновления списка пользователей: {e}")

    def handle_call_request(self, data: dict):
        """Обработка входящего запроса на звонок"""
        try:
            call_id = data.get('call_id')
            from_user = data.get('from')
            call_type = data.get('call_type')
            
            if call_id and from_user:
                logger.info(f"🔊 Входящий звонок {call_id} от {from_user}")
                
                # Создаем окно звонка
                self.show_incoming_call(call_id, from_user, call_type)
                
            else:
                logger.warning("⚠️ Неполный запрос на звонок")
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки запроса на звонок: {e}")
    
    def get_network_info(self):
        """Получение информации о сети - работаем напрямую с P2PNetworkClient"""
        try:
            info = {
                'connected_peers': 0,
                'known_peers': 0,
                'status': 'Unknown',
                'port': 'Unknown'
            }
            
            if hasattr(self, 'p2p_client') and self.p2p_client is not None:
                p2p_client = self.p2p_client
            
                # Подключенные пиры
                if hasattr(p2p_client, 'connected_peers'):
                    info['connected_peers'] = len(p2p_client.connected_peers)
            
                # Известные пиры
                if hasattr(p2p_client, 'known_peers'):
                    info['known_peers'] = len(p2p_client.known_peers)
            
                # Порт
                if hasattr(p2p_client, 'port'):
                    info['port'] = p2p_client.port
                
                # Статус
                if info['connected_peers'] > 0:
                    info['status'] = 'Connected'
                elif info['known_peers'] > 0:
                    info['status'] = 'Known peers available'
                else:
                    info['status'] = 'No peers'
                
            return info
        
        except Exception as e:
            self.logger.error(f"Ошибка получения информации о сети: {e}")
            return {'status': f'Error: {e}'}
  
    def connect_to_peer(self, host: str, port: int):
        """Подключиться к пиру"""
        try:
            self.logger.info(f"Подключение к пиру {host}:{port}")
        
            # Используем метод P2PNetwork для подключения
            if hasattr(self.p2p_client, 'network') and hasattr(self.p2p_client.network, 'connect_to_peer'):
                success = self.p2p_client.network.connect_to_peer_sync(host, port)
                if success:
                    self.system_chat.append(f"✅ Подключение к {host}:{port} выполнено")
                    # Обновляем список пиров через короткое время
                    QTimer.singleShot(1000, self.update_peers_from_p2p)
                else:
                    self.system_chat.append(f"❌ Не удалось подключиться к {host}:{port}")
            else:
                self.system_chat.append(f"⚠️ Метод подключения к пирам не доступен")
            
        except Exception as e:
            self.logger.error(f"Ошибка подключения к пиру: {e}")
            self.system_chat.append(f"❌ Ошибка подключения: {e}")
  
    def disconnect_from_peer(self, host: str, port: int):
        """Отключиться от пира"""
        try:
            self.logger.info(f"Отключение от пира {host}:{port}")
        
            if hasattr(self.p2p_client, 'network') and hasattr(self.p2p_client.network, 'disconnect_from_peer'):
                success = self.p2p_client.network.disconnect_from_peer_sync(host, port)
                if success:
                    self.system_chat.append(f"✅ Отключение от {host}:{port} выполнено")
                    self.update_peers_from_p2p()
                else:
                    self.system_chat.append(f"❌ Не удалось отключиться от {host}:{port}")
            else:
                self.system_chat.append(f"⚠️ Метод отключения от пиров не доступен")
            
        except Exception as e:
            self.logger.error(f"Ошибка отключения от пира: {e}")
            self.system_chat.append(f"❌ Ошибка отключения: {e}")

    def setup_media_for_call(self, call_id, username):
        """Настройка медиа для звонка - критически важный метод"""
        try:
            logger.info(f"=== НАСТРОЙКА МЕДИА ДЛЯ ЗВОНКА {call_id} ===")
            
            # 1. Проверяем, есть ли окно звонка
            if call_id not in self.active_calls:
                logger.error(f"❌ Окно звонка {call_id} не найдено")
                return False
            
            call_info = self.active_calls[call_id]
            call_window = call_info['window']
            
            # 2. Устанавливаем медиа соединение через P2P клиент
            logger.info("🔧 Вызов p2p_client.setup_media_connection...")
            if self.p2p_client and self.p2p_client.setup_media_connection(call_id, username):
                logger.info("✅ Медиа соединение установлено в P2P клиенте")
                
                # 3. Получаем медиа сокет
                logger.info("🔧 Получение медиа сокета...")
                media_socket = self.p2p_client.get_media_socket(call_id)
                if media_socket:
                    logger.info(f"✅ Медиа сокет получен: {media_socket}")
                    
                    # 4. Устанавливаем сокет в окне звонка
                    logger.info("🔧 Установка сокета в окне звонка...")
                    success = call_window.set_call_socket(media_socket)
                    
                    if success:
                        logger.info("✅ Сокет успешно установлен в окне звонка")
                        
                        # 5. Запускаем звонок
                        if call_info['outgoing']:
                            # Для исходящего звонка сразу запускаем
                            logger.info("🔧 Запуск исходящего звонка...")
                            call_window.start_call()
                        else:
                            # Для входящего - готовим к запуску
                            logger.info("✅ Окно звонка готово к принятию")
                        
                        return True
                    else:
                        logger.error("❌ Не удалось установить сокет в окне звонка")
                        return False
                else:
                    logger.error("❌ Не удалось получить медиа сокет")
                    return False
            else:
                logger.error("❌ Не удалось установить медиа соединение")
                return False
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка настройки медиа: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            return False

    def start_call(self, username, call_type='audio'):
        """Начать аудиозвонок с пользователем (исходящий)"""
        online_users = self.p2p_client.get_online_users()
        if not any(u['username'] == username for u in online_users):
            QMessageBox.warning(self, 'Ошибка', f'Пользователь {username} не в сети')
            return

        if not self.p2p_client:
            QMessageBox.warning(self, 'Ошибка', 'P2P клиент не инициализирован')
            return

        call_id = self.p2p_client.send_call_request(username, call_type)
        if not call_id:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить запрос на звонок')
            return

        # Создаём окно аудиозвонка
        call_window = CallWindow(
            username, call_type, call_id, is_outgoing=True, parent=self,
            input_device=self.audio_input_device,
            output_device=self.audio_output_device
        )
        call_window.call_ended.connect(self.end_call)

        # Сохраняем информацию о звонке
        self.active_calls[call_id] = {
            'window': call_window,
            'username': username,
            'type': call_type,
            'outgoing': True,
            'status': 'pending'
        }

        # Создаём серверный сокет для аудио
        self.p2p_client.setup_call_connection(call_id, username, is_outgoing=True)
        
        # Запускаем поток ожидания клиентского сокета
        def wait_for_client_socket():
            client_sock = self.p2p_client.wait_for_call_socket(call_id, timeout=10)
            if client_sock:
                logger.info(f"✅ Получен клиентский сокет для звонка {call_id}")
                # Передаём клиентский сокет в окно звонка
                call_window.set_call_socket(client_sock)
                # Если звонок ещё не запущен (кнопка не нажата), ничего страшного
                # set_call_socket сам вызовет аудио, когда is_active станет True
            else:
                logger.error(f"❌ Не удалось получить клиентский сокет для звонка {call_id}")
                call_window.status_label.setText("❌ Ошибка: аудио-сокет не работает")
        threading.Thread(target=wait_for_client_socket, daemon=True).start()

        # Показываем окно
        call_window.show()
        call_window.raise_()
        call_window.activateWindow()

        logger.info(f"📞 Отправлен запрос на {call_type} звонок пользователю {username}")
        self.system_chat.append(f"📞 Отправлен запрос на {call_type} звонок пользователю {username}")

    def setup_outgoing_media(self, call_id, username, call_window):
        """Настройка медиа для исходящего звонка"""
        try:
            logger.info("🔧 Настройка исходящего соединения для исходящего звонка...")
            # Получаем сокет для звонка
            call_socket = self.p2p_client.setup_call_connection(call_id, username, is_outgoing=True)
            
            if call_socket:
                logger.info(f"✅ Исходящий сокет для звонка {call_id} создан")
                
                # Сохраняем сокет в словаре
                self.call_sockets[call_id] = call_socket

                # Сохраняем сокет в информации о звонке
                if call_id in self.active_calls:
                    self.active_calls[call_id]['socket'] = call_socket

                # Устанавливаем сокет в окне
                success = call_window.set_call_socket(call_socket)
                if success:
                    logger.info(f"✅ Сокет установлен для звонка {call_id}")

                    # Запускаем таймер для проверки, установился ли сокет
                    QTimer.singleShot(1000, lambda: self.verify_socket_setup(call_id, call_window))
                else:
                    logger.error(f"❌ Не удалось установить сокет для звонка {call_id}")
                    self.system_chat.append(f"⚠️ Звонок начат, но аудио может не работать")
            else:
                logger.warning(f"⚠️ Не удалось получить сокет для звонка {call_id}")
                self.system_chat.append(f"⚠️ Звонок начат, но аудио соединение не установлено")
            
            logger.info(f"📞 Отправлен запрос на {call_type} звонок пользователю {username}")
            self.system_chat.append(f"📞 Отправлен запрос на {call_type} звонок пользователю {username}")

        except Exception as e:
            logger.error(f"❌ Ошибка настройки медиа для исходящего звонка: {e}")

    def accept_call(self, call_id):
        try:
            if call_id not in self.active_calls:
                return
            call_info = self.active_calls[call_id]
            username = call_info['username']
            call_window = call_info['window']

            if self.p2p_client and self.p2p_client.send_call_response(call_id, 'accept'):
                # Для входящего звонка сокет уже должен быть клиентским, но проверим
                if hasattr(call_window, 'audio_core') and not call_window.audio_core.audio_socket:
                    # Если сокета нет – пробуем получить ещё раз
                    audio_socket = self.p2p_client.setup_call_connection(call_id, username, is_outgoing=False)
                    if audio_socket:
                        call_window.set_audio_socket(audio_socket)
                # Запускаем звонок
                if hasattr(call_window, 'start_call'):
                    call_window.start_call()
                self.system_chat.append(f"✅ Звонок {call_id} принят")
            else:
                QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить подтверждение звонка')
        except Exception as e:
            logger.error(f"Ошибка в accept_call: {e}")
    
    def reject_call(self, call_id):
        """Отклонить входящий звонок"""
        try:
            logger.info(f"=== ОТКЛОНЕНИЕ ЗВОНКА {call_id} ===") 


            if call_id not in self.active_calls:
                logger.error(f"❌ Звонок {call_id} не найден в active_calls")
                return
                
            call_info = self.active_calls[call_id]
            username = call_info['username']
            call_window = call_info['window']
                
            # Отправляем отклонение через P2P сеть
            if self.p2p_client and self.p2p_client.send_call_response(call_id, 'reject'):
                logger.info("✅ Отклонение отправлено через P2P сеть")
                
                # Закрываем окно
                call_window.close()

                # Удаляем из активных звонков
                if call_id in self.active_calls:
                    del self.active_calls[call_id]
                self.system_chat.append(f"❌ Вы отклонили звонок от {username}")
            else:
                QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить отклонение звонка')

        except Exception as e:
            logger.error(f"❌ Ошибка в reject_call: {e}")

    def end_call(self, call_id):
        logger.info(f"=== ЗАВЕРШЕНИЕ ЗВОНКА {call_id} ===")
        with self.calls_lock:
            if call_id not in self.active_calls:
                logger.warning(f"Звонок {call_id} уже завершен или не существует")
                return
            call_info = self.active_calls[call_id]
            username = call_info['username']
            if 'window' in call_info and call_info['window']:
                try:
                    call_info['window'].hide()
                    call_info['window'].deleteLater()
                except Exception as e:
                    logger.error(f"Ошибка закрытия окна звонка: {e}")
            if self.p2p_client:
                success = self.p2p_client.send_call_response(call_id, 'end')
                if not success:
                    logger.warning(f"Не удалось отправить сообщение о завершении звонка {call_id}")
                self.p2p_client.close_media_connection(call_id)
            if call_id in self.call_sockets:
                try:
                    socket = self.call_sockets[call_id]
                    if socket:
                        socket.close()
                except:
                    pass
                del self.call_sockets[call_id]
            del self.active_calls[call_id]
            self.system_chat.append(f"📞 Вы завершили звонок с {username}")
            logger.info(f"✅ Звонок {call_id} завершен")                  
    
    def verify_socket_setup(self, call_id, call_window):
        """Проверка, что сокет успешно установлен в окне"""
        try:
            logger.info(f"🔍 Проверка установки сокета для звонка {call_id}")
            
            if not call_window.socket_set:
                logger.warning(f"⚠️ Сокет не установлен в окне звонка {call_id}")
                
                # Пробуем еще раз получить сокет из словаря
                if call_id in self.call_sockets:
                    socket = self.call_sockets[call_id]
                    if socket:
                        logger.info(f"🔄 Повторная попытка установки сокета для {call_id}")
                        success = call_window.set_call_socket(socket)
                        if success:
                            logger.info(f"✅ Сокет успешно установлен при повторной попытке")
                        else:
                            logger.error(f"❌ Не удалось установить сокет при повторной попытке")
                else:
                    logger.error(f"❌ Сокет не найден в словаре call_sockets")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки установки сокета: {e}")

    def setup_call_socket_for_window(self, call_id):
        """Принудительно установить сокет в окне звонка"""
        try:
            if call_id not in self.active_calls:
                logger.warning(f"⚠️ Звонок {call_id} не найден")
                return False
                
            call_info = self.active_calls[call_id]
            call_window = call_info.get('window')
            
            if not call_window:
                logger.error(f"❌ Окно звонка {call_id} не найдено")
                return False
                
            # Получаем сокет
            socket = self.get_call_socket(call_id)
            if not socket:
                logger.error(f"❌ Не удалось получить сокет для звонка {call_id}")
                return False
                
            # Устанавливаем сокет
            success = call_window.set_call_socket(socket)
            if success:
                logger.info(f"✅ Сокет успешно установлен в окне звонка {call_id}")
                return True
            else:
                logger.error(f"❌ Не удалось установить сокет в окне звонка {call_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки сокета: {e}")
            return False

    def show_all_active_calls(self):
        """Показать все активные окна звонков"""
        for call_id, call_info in self.active_calls.items():
            window = call_info['window']
            if window and hasattr(window, 'isVisible') and not window.isVisible():
                logger.info(f"🔊 Принудительно показываем окно звонка {call_id}")
                window.show()
                window.raise_()
                window.activateWindow()

    def show_network_info(self):
        """Показать информацию о P2P сети"""
        try:
            network_info = self.get_network_info()
        
            info_text = f"P2P Сеть:\n\n"
            info_text += f"Подключенные пиры: {network_info.get('connected_peers', 0)}\n"
            info_text += f"Известные пиры: {network_info.get('known_peers', 0)}\n"
            info_text += f"Статус: {network_info.get('status', 'Unknown')}\n"
            info_text += f"Порт: {network_info.get('port', 'Unknown')}\n"
        
            QMessageBox.information(self, 'Информация о сети', info_text)
        except Exception as e:
            QMessageBox.warning(self, 'Ошибка', f'Не удалось получить информацию о сети: {e}')

    def show_peers_list(self):
        """Показать список пиров"""
        try:
            if not self.p2p_client:
                QMessageBox.warning(self, 'Ошибка', 'P2P клиент не инициализирован')
                return
                
            peers = self.p2p_client.get_peers_list()
            if peers:
                peers_text = "Подключенные пиры:\n\n"
                for peer in peers:
                    peers_text += f"• {peer.get('address', 'Unknown')} (ID: {peer.get('id', 'Unknown')})\n"
            else:
                peers_text = "Нет подключенных пиров"
                
            QMessageBox.information(self, 'Список пиров', peers_text)
        except Exception as e:
            QMessageBox.warning(self, 'Ошибка', f'Не удалось получить список пиров: {e}')
    
    def toggle_notifications(self, enabled):
        """Включение/выключение уведомлений"""
        self.notifications_enabled = enabled
        status = "включены" if enabled else "выключены"
        self.system_chat.append(f"🔔 Уведомления {status}")
        logger.info(f"Уведомления {status}")
        
    def show_profile(self):
        """Показать информацию о профиле"""
        user_info = self.db.get_user_info(self.username)
        if user_info:
            QMessageBox.information(self, '👤 Мой профиль', 
                                  f'Имя пользователя: {self.username}\n'
                                  f'Зарегистрирован: {user_info.get("registered_at", "Unknown")}\n'
                                  f'Статус: Online\n'
                                  f'Активных чатов: {len(self.active_chats)}\n'
                                  f'Активных звонков: {len(self.active_calls)}')
        else:
            QMessageBox.information(self, '👤 Мой профиль', 
                                  f'Имя пользователя: {self.username}\n'
                                  f'Статус: Online\n'
                                  f'Активных чатов: {len(self.active_chats)}\n'
                                  f'Активных звонков: {len(self.active_calls)}')
        
    def refresh_user_list(self):
        """Обновление списка пользователей"""
        if hasattr(self, 'p2p_client') and self.p2p_client.is_running and self.is_authenticated:
            # Обновляем информацию о пирах
            self.update_peers_from_p2p()
            self.system_chat.append("🔄 Обновление списка пиров...")
        
    def start_p2p_messaging(self):
        """Запуск работы P2P мессенджера - синхронная версия"""
        try:
            self.system_chat.append("🔄 Запуск P2P сети...")
            
            # Проверяем наличие P2P клиента
            if not hasattr(self, 'p2p_client') or self.p2p_client is None:
                self.system_chat.append("❌ P2P клиент не инициализирован")
                self.statusBar().showMessage("❌ P2P клиент не инициализирован")
                return False
            
            # Проверяем состояние P2P клиента
            self.system_chat.append(f"✅ P2P клиент найден: {type(self.p2p_client)}")
                
            # Запускаем P2P сеть
            if hasattr(self.p2p_client, 'start'):
                self.system_chat.append("🔧 Вызов p2p_client.start()...")
                success = self.p2p_client.start()
                if success:
                    self.system_chat.append("✅ P2P сеть запущена")
                    self.statusBar().showMessage("✅ P2P сеть запущена")

                    # Автоматическое подключение к пирам через 10 секунд
                    QTimer.singleShot(10000, self.force_connect_peers)

                    # Настраиваем интеграцию с небольшой задержкой
                    QTimer.singleShot(2000, self.setup_p2p_integration)
                    
                    # Первоначальное обновление списка пиров
                    QTimer.singleShot(3000, self.update_peers_from_p2p)
                    # Запускаем периодическое обновление
                    self.start_listen_for_updates()
                
                    self.system_chat.append(f"✅ Успешный вход как: {self.username}")
                    return True
                else:
                    self.system_chat.append("❌ Не удалось запустить P2P сеть")
                    self.statusBar().showMessage("❌ Не удалось запустить P2P сеть")
                    return False
            else:
                self.system_chat.append("⚠️ P2P клиент не имеет метода start")
                self.statusBar().showMessage("⚠️ P2P клиент не имеет метода start")
                return False          
        except Exception as e:
            error_msg = f"❌ Ошибка запуска P2P сети: {e}"
            self.logger.error(error_msg)
            self.system_chat.append(error_msg)
            self.statusBar().showMessage("❌ Ошибка запуска P2P сети")
            return False
    
    def start_listen_for_updates(self):
        """Запуск прослушивания обновлений от P2P сети"""
        self.update_timer.start(20000)  # 20 секунд
        logger.info("Таймер обновлений P2P запущен")
        
    def stop_listen_for_updates(self):
        """Остановка прослушивания обновлений"""
        self.is_authenticated = False
        if hasattr(self, 'update_timer') and self.update_timer.isActive():
            self.update_timer.stop()
            logger.info("Таймер обновлений остановлен")
        if hasattr(self, 'peer_update_timer') and self.peer_update_timer.isActive():
            self.peer_update_timer.stop()
            logger.info("Таймер пиров остановлен")
        
    def on_update_timer(self):
        """Обработчик таймера обновлений"""
        if not self.is_authenticated or not hasattr(self.p2p_client, 'is_running') or not self.p2p_client.is_running:
            self.update_timer.stop()
            return
            
        try:
            # Обновляем информацию о пирах
            self.update_peers_from_p2p()
            
        except Exception as e:
            error_msg = str(e)
            self.system_chat.append(f"⚠️ Ошибка получения обновлений: {e}")
  
    def close_application(self):
        """Закрытие приложения"""
        self.close()
        
    def disconnect_from_network(self):
        """Отключение от P2P сети"""
        self.stop_listen_for_updates()
        if self.p2p_client:
            self.p2p_client.stop()
        self.sig_connection_status.emit("❌ Отключено от P2P сети")
        self.is_authenticated = False

    def connect_p2p_signals(self):
        """Подключение сигналов от P2P клиента"""
        if not self.p2p_client:
            return
            
        if hasattr(self.p2p_client, 'message_received'):
            self.p2p_client.message_received.connect(self.sig_message_received.emit)
        if hasattr(self.p2p_client, 'user_list_updated'):
            self.p2p_client.user_list_updated.connect(self.sig_user_list_updated.emit)
        if hasattr(self.p2p_client, 'connection_status_changed'):
            self.p2p_client.connection_status_changed.connect(self.sig_connection_status.emit)
        if hasattr(self.p2p_client, 'call_received'):
            self.p2p_client.call_received.connect(self.sig_call_received.emit)
        
    def show_initial_network_info(self):
        """Показать начальную информацию о сети"""
        network_info = self.get_network_info()
        self.system_chat.append(f"📊 Сеть: {network_info.get('status')}, пиров: {network_info.get('connected_peers')}/{network_info.get('known_peers')}")
       
    def setup_call_media(self, call_id, username, is_outgoing):
        """Упрощенная настройка медиа для звонка"""
        try:
            logger.info(f"🔊 Настройка медиа для звонка {call_id} (исходящий: {is_outgoing})")
            
            if not self.p2p_client:
                logger.error("❌ P2P клиент не инициализирован")
                return False
        
            # Проверяем, поддерживает ли клиент упрощенные медиа-соединения
            if hasattr(self.p2p_client, 'setup_simple_media_connection'):
                if is_outgoing:
                    # Для исходящего звонка регистрируемся на сервере
                    success = self.p2p_client.setup_simple_media_connection(call_id, username)
                    if success:
                        logger.info(f"✅ Исходящее медиа-соединение установлено для {call_id}")
                        return True
                    else:
                        logger.error(f"❌ Не удалось установить исходящее медиа-соединение")
                        return False
                else:
                    # Для входящего звонка подключаемся к другому пользователю
                    success = self.p2p_client.connect_to_peer_media(call_id, username)
                    if success:
                        logger.info(f"✅ Входящее медиа-соединение установлено для {call_id}")
                        return True
                    else:
                        logger.error(f"❌ Не удалось установить входящее медиа-соединение")
                        return False
            else:
                logger.warning("⚠️ P2P клиент не поддерживает упрощенные медиа-соединения")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки медиа: {e}")
            return False

    def update_network_status(self, is_connected: bool, peer_count: int):
        """Обновление статуса сети"""
        if is_connected:
            status_text = f"✅ P2P сеть: Подключено ({peer_count} пиров)" 
            self.statusBar().showMessage(status_text)
            # Обновляем системный чат
            if hasattr(self, 'system_chat'):
                self.system_chat.append(f"🌐 Сеть: подключено {peer_count} пиров")
        else:
            status_text = "❌ P2P сеть: Не подключено"
            self.statusBar().showMessage(status_text)
    
        # Обновляем статус в панели пользователей
        if hasattr(self, 'users_panel'):
            self.users_panel.update_network_status(is_connected, peer_count)
            
    def tray_icon_activated(self, reason):
        """Обработка активации иконки в трее"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_window()
            
    def toggle_window(self):
        """Показать/скрыть окно"""
        if self.isVisible():
            if self.isMinimized():
                self.showNormal()
            else:
                self.hide()
        else:
            self.show()
            self.activateWindow()
            
    def show_notification(self, title, message):
        """Показать уведомление"""
        if not self.notifications_enabled:
            return
            
        notification = NotificationWindow(title, message)
        notification.show_notification()
        self.active_notifications.append(notification)
        
        def remove_notification():
            if notification in self.active_notifications:
                self.active_notifications.remove(notification)
                
        notification.close_animation.finished.connect(remove_notification)
        
        if self.tray_icon:
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.Information,
                3000
            )

    def handle_incoming_call_request(self, from_user, call_type, call_id):
        """Обработка входящего запроса на звонка"""
        try:
            logger.info(f"=== ОБРАБОТКА ВХОДЯЩЕГО ЗВОНКА {call_id} ОТ {from_user} ===")
            
            if call_id in self.active_calls:
                logger.warning(f"Дублирующий запрос на звонок {call_id}, игнорируем")
                return

            # Создаем окно звонка
            call_window = CallWindow(from_user, call_type, call_id, is_outgoing=False, parent=self,
                                        input_device=self.audio_input_device,
                                        output_device=self.audio_output_device)
            call_window.call_ended.connect(self.end_call)
            call_window.call_accepted.connect(self.accept_call)
            call_window.call_rejected.connect(self.reject_call)
            

            # Получаем или создаем сокет для звонка
            if self.p2p_client:
                logger.info(f"🔧 Настройка соединения для входящего звонка {call_id}")
                
                # Создаем серверный сокет для входящего звонка
                call_socket = self.p2p_client.setup_call_connection(
                    call_id, from_user, is_outgoing=False
                )
            
                if call_socket:
                    logger.info(f"✅ Получен сокет типа {type(call_socket)} для звонка {call_id}")
                    # проверяем, не серверный ли он
                    try:
                        logger.info(f"   is_client={not bool(call_socket.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN))}")
                    except:
                        pass
                    self.call_sockets[call_id] = call_socket
                    # Устанавливаем сокет в окне
                    success = call_window.set_call_socket(call_socket)
                    if success:
                        # Убедимся, что приёмник запущен сразу (вдруг окно уже активно)
                        if call_window.is_active and not call_window.audio_initialized:
                            call_window.initialize_audio_streams()
                        logger.info(f"✅ Сокет установлен в окне звонка {call_id}")
                    else:
                        logger.error(f"❌ Не удалось установить сокет в окне звонка {call_id}")
                else:
                    logger.error(f"❌ Не удалось создать сокет для входящего звонка {call_id}")
            
            # Сохраняем информацию о звонке
            self.active_calls[call_id] = {
                'window': call_window,
                'username': from_user,
                'type': call_type,
                'outgoing': False,
                'status': 'incoming'
            }
            
            # Показываем окно
            call_window.show()
            call_window.raise_()
            call_window.activateWindow()
            
            # Показываем уведомление
            self.show_notification(
                f"📞 Входящий {call_type} звонок",
                f"Пользователь {from_user} звонит вам"
            )
        
            logger.info(f"✅ Окно звонка {call_id} показано")
            self.system_chat.append(f"📞 Входящий {call_type} звонок от {from_user}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания окна звонка: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            self.system_chat.append(f"❌ Ошибка создания окна звонка: {e}")

    def handle_incoming_video_call(self, from_user, call_id):
        """Обработка входящего видеозвонка"""
        try:
            logger.info(f"=== ОБРАБОТКА ВХОДЯЩЕГО ВИДЕОЗВОНКА {call_id} ОТ {from_user} ===")

            # Получаем информацию о звонке из P2P клиента
            call_info = self.p2p_client.call_requests.get(call_id, {})
            media_host = call_info.get('media_host')
            video_port = call_info.get('video_port')

            # Чтение настроек видео
            settings = QSettings('DialogApp', 'P2PClient')
            camera_index = settings.value('video_camera_index', 0, type=int)
            res_w = settings.value('video_resolution_width', 640, type=int)
            res_h = settings.value('video_resolution_height', 480, type=int)
            fps = settings.value('video_fps', 30, type=int)
            quality = settings.value('video_quality', 85, type=int)
            color_enhancement = settings.value('video_color_enhancement', True, type=bool)

            # Создаём окно видеозвонка
            video_window = VideoCallWindow(
                from_user, call_id, is_outgoing=False, parent=self,
                camera_index=camera_index,
                resolution=(res_w, res_h),
                fps=fps,
                quality=quality,
                color_enhancement=color_enhancement,
                input_device=self.audio_input_device,
                output_device=self.audio_output_device
            )
            video_window.call_ended.connect(self.end_call)
            video_window.call_accepted.connect(self.accept_call)
            video_window.call_rejected.connect(self.reject_call)

            # ===== АУДИО: для входящего звонка создаём клиентский сокет (подключаемся к пиру) =====
            audio_socket = self.p2p_client.setup_call_connection(call_id, from_user, is_outgoing=False)
            if audio_socket:
                video_window.set_audio_socket(audio_socket)
                logger.info(f"✅ Аудио-сокет для входящего звонка {call_id} установлен")
            else:
                logger.error(f"❌ Не удалось создать аудио-сокет для входящего звонка {call_id}")
                video_window.status_label.setText("❌ Ошибка: аудио не работает")

            # Сохраняем информацию о звонке
            self.active_calls[call_id] = {
                'window': video_window,
                'username': from_user,
                'type': 'video',
                'outgoing': False,
                'status': 'incoming'
            }

            # Показываем окно
            video_window.show()
            video_window.raise_()
            video_window.activateWindow()

            # Функция для подключения видео (как было раньше)
            def try_connect_video(attempt=0):
                if attempt >= 10:
                    logger.error(f"❌ Не удалось подключиться к видео после 10 попыток")
                    video_window.status_label.setText("❌ Ошибка подключения видео")
                    return

                call_info = self.p2p_client.call_requests.get(call_id, {})
                video_port = call_info.get('video_port')
                media_host = call_info.get('media_host')

                if not media_host:
                    for peer_id, pinfo in self.p2p_client.connected_peers.items():
                        if pinfo.get('username') == from_user:
                            media_host = pinfo['address'][0]
                            break

                if not video_port or not media_host:
                    logger.warning(f"⚠️ Попытка {attempt+1}: video_port={video_port}, media_host={media_host}, повтор через 0.5 сек")
                    QTimer.singleShot(500, lambda: try_connect_video(attempt+1))
                    return

                try:
                    video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    video_socket.settimeout(5.0)
                    video_socket.connect((media_host, video_port))
                    video_socket.settimeout(30.0)
                    video_window.set_video_socket(video_socket)
                    logger.info(f"✅ Видео-сокет подключён к {media_host}:{video_port}")
                except Exception as e:
                    logger.warning(f"⚠️ Попытка {attempt+1}: не удалось подключиться к видео: {e}")
                    QTimer.singleShot(1000, lambda: try_connect_video(attempt+1))

            QTimer.singleShot(100, lambda: try_connect_video(0))

            # Уведомление
            self.show_notification(
                f"📹 Входящий видеозвонок",
                f"Пользователь {from_user} звонит вам с видео"
            )

            logger.info(f"✅ Окно видеозвонка {call_id} показано")
            self.system_chat.append(f"📹 Входящий видеозвонок от {from_user}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания окна видеозвонка: {e}")
            self.system_chat.append(f"❌ Ошибка создания окна видеозвонка: {e}")

    def start_video_call(self, username):
        """Начать видеозвонок с пользователем (исходящий)"""
        # Отладочная информация
        online_users = self.p2p_client.get_online_users()
        logger.info(f"Онлайн пользователи перед видеозвонком: {[u['username'] for u in online_users]}")

        if not any(u['username'] == username for u in online_users):
            QMessageBox.warning(self, 'Ошибка', f'Пользователь {username} не в сети')
            return

        if not self.p2p_client:
            QMessageBox.warning(self, 'Ошибка', 'P2P клиент не инициализирован')
            return

        # Чтение настроек видео
        settings = QSettings('DialogApp', 'P2PClient')
        camera_index = settings.value('video_camera_index', 0, type=int)
        res_w = settings.value('video_resolution_width', 640, type=int)
        res_h = settings.value('video_resolution_height', 480, type=int)
        fps = settings.value('video_fps', 30, type=int)
        quality = settings.value('video_quality', 85, type=int)
        color_enhancement = settings.value('video_color_enhancement', True, type=bool)

        # Отправляем запрос на видеозвонок
        call_id = self.p2p_client.send_call_request(username, 'video')
        if not call_id:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить запрос на видеозвонок')
            return

        # Создаём окно видеозвонка
        video_window = VideoCallWindow(
            username, call_id, is_outgoing=True, parent=self,
            camera_index=camera_index,
            resolution=(res_w, res_h),
            fps=fps,
            quality=quality,
            color_enhancement=color_enhancement,
            input_device=self.audio_input_device,
            output_device=self.audio_output_device
        )
        video_window.call_ended.connect(self.end_call)

        # Подключаем сигнал готовности видео-сокета (если нужно)
        self.p2p_client.video_socket_ready.connect(self.on_video_socket_ready)

        # Получаем серверный сокет для видео (или None)
        video_socket = self.p2p_client.setup_video_connection(call_id, username)
        if video_socket:
            video_window.set_video_socket(video_socket)
            logger.info(f"✅ Видео-сокет для звонка {call_id} создан")
        else:
            logger.warning(f"⚠️ Не удалось получить видео-сокет для звонка {call_id}")
            self.system_chat.append(f"⚠️ Видеозвонок начат, но видео соединение не установлено")

        # ===== АУДИО: создаём серверный сокет и запускаем ожидание клиентского подключения =====
        self.p2p_client.setup_call_connection(call_id, username, is_outgoing=True)
        
        # Для исходящего звонка audio_socket – это серверный сокет.
        # Запускаем фоновое ожидание, когда он примет входящее соединение.
        self._set_audio_socket_with_retry(video_window, call_id, timeout=5)
        
        # Сохраняем информацию о звонке
        self.active_calls[call_id] = {
            'window': video_window,
            'username': username,
            'type': 'video',
            'outgoing': True,
            'status': 'pending'
        }

        # Показываем окно
        video_window.show()
        video_window.raise_()
        video_window.activateWindow()

        logger.info(f"📹 Отправлен запрос на видеозвонок пользователю {username}")
        self.system_chat.append(f"📹 Отправлен запрос на видеозвонок пользователю {username}")

    def _retry_audio_socket(self, video_window, call_id, username, is_outgoing):
        audio_socket = self.p2p_client.setup_call_connection(call_id, username, is_outgoing=is_outgoing)
        if audio_socket:
            video_window.set_audio_socket(audio_socket)
            logger.info(f"Аудио-сокет для {call_id} успешно создан с повторной попытки")
        else:
            logger.warning(f"Не удалось создать аудио-сокет для {call_id} после повторной попытки")
        
    
    def handle_call_accepted(self, from_user, call_id):
        logger.info(f"🔊 Звонок принят пользователем {from_user}")
        with self.calls_lock:
            if call_id in self.active_calls:
                call_info = self.active_calls[call_id]
                call_window = call_info['window']
                if call_info['outgoing']:
                    # Для исходящего звонка просто запускаем его (медиа придёт позже)
                    call_window.start_call()
                # Для входящего звонка ничего не делаем – accept_call уже выполнен
            else:
                logger.warning(f"Звонок {call_id} не найден в активных")

    def handle_call_rejected(self, from_user, call_id):
        """Обработка отклонения звонка"""
        logger.info(f"P2PMainWindow.handle_call_rejected: Звонок отклонен пользователем {from_user}")
        
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            call_window = call_info['window']
            
            call_window.close()
            del self.active_calls[call_id]
            
            QMessageBox.information(self, 'Звонок отклонен', f'Пользователь {from_user} отклонил ваш звонок')
            self.system_chat.append(f"❌ Пользователь {from_user} отклонил звонок")
            
    def handle_call_ended(self, from_user, call_id):
        """Обработка завершения звонка"""
        logger.info(f"P2PMainWindow.handle_call_ended: Звонок завершен пользователем {from_user}")
        
        with self.calls_lock:
            if call_id in self.active_calls:
                call_info = self.active_calls[call_id]
                call_window = call_info.get('window')
                if call_window:
                    call_window._closing_by_network = True
                    call_window.close()
                del self.active_calls[call_id]
                if call_id in self.call_sockets:
                    try:
                        socket = self.call_sockets[call_id]
                        if socket:
                            socket.close()
                    except:
                        pass
                    del self.call_sockets[call_id]
                self.system_chat.append(f"📞 Звонок с {from_user} завершен")
            else:
                logger.info(f"Звонок {call_id} уже удален из активных")
            
    def handle_call_info(self, from_user, call_id):
        """Обработка информации о звонке"""
        logger.info(f"P2PMainWindow.handle_call_info: Информация о звонке от {from_user}")

    def show_add_peer_dialog(self):
        """Показать диалог добавления пира"""
        from PyQt5.QtWidgets import QInputDialog
        
        host, ok = QInputDialog.getText(self, 'Добавить пир', 'Введите адрес пира (host:port):')
        if ok and host:
            try:
                if ':' in host:
                    host_parts = host.split(':')
                    peer_host = host_parts[0]
                    peer_port = int(host_parts[1])
                    self.connect_to_peer(peer_host, peer_port)
                else:
                    QMessageBox.warning(self, 'Ошибка', 'Неверный формат. Используйте: host:port')
            except ValueError:
                QMessageBox.warning(self, 'Ошибка', 'Неверный порт')

    def logout(self):
        """Выход из системы"""
        reply = QMessageBox.question(self, 'Выход из системы', 
                                   'Вы уверены, что хотите выйти из системы?',
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.disconnect_from_network()
            self.close()
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.disconnect_from_network()
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.hide()
        event.accept()

class P2PDialogApplication:
    """Класс управления P2P приложением"""
    
    def __init__(self, bootstrap_nodes=None):
        self.bootstrap_nodes = bootstrap_nodes or []
        self.app = QApplication(sys.argv)
        self.db = ClientDatabase()
        self.auth_manager = AuthManager(self.db)
        self.p2p_client = P2PNetworkClient(self.db, bootstrap_nodes=self.bootstrap_nodes)
        self.auth_window = None
        self.main_window = None
        
    def run(self):
        """Запуск P2P приложения"""
        self.show_auth_dialog()
        
    def show_auth_dialog(self):
        """Показать диалог аутентификации"""
        self.auth_window = AuthWindow(self.p2p_client, self.auth_manager, None)
        self.auth_window.login_success.connect(self.on_login_success)
        
        # Запускаем подключение к P2P сети в фоне
        self.connect_to_p2p_network()
        
        result = self.auth_window.exec_()
        if result == QDialog.Rejected:
            self.on_auth_cancelled()
        
    def connect_to_p2p_network(self):
        """Подключение к P2P сети в фоновом режиме"""
        def connect_thread():
            logger.info("Попытка подключения к P2P сети...")
            self.auth_window.update_status("Подключение к P2P сети...")
            
            if self.p2p_client and self.p2p_client.start():
                logger.info("Успешное подключение к P2P сети")
                self.auth_window.update_status("✅ Подключено к P2P сети")
            else:
                logger.error("Не удалось подключиться к P2P сети")
                self.auth_window.update_status("❌ Ошибка подключения к P2P сети")
                QMessageBox.warning(self.auth_window, 'Ошибка', 'Не удалось подключиться к P2P сети')
        
        threading.Thread(target=connect_thread, daemon=True).start()
        
    def on_login_success(self, username):
        """Обработка успешного входа"""
        logger.info(f"Успешная аутентификация пользователя: {username}")
    
        # Устанавливаем имя пользователя в P2P клиенте
        if self.p2p_client and hasattr(self.p2p_client, 'set_username'):
            self.p2p_client.set_username(username)
    
        self.main_window = P2PMainWindow(self.p2p_client, username, self.db)
        self.main_window.show()

    def on_auth_cancelled(self):
        """Обработка отмены аутентификации"""
        logger.info("Аутентификация отменена")
        if self.p2p_client:
            self.p2p_client.stop()
        sys.exit(0)

def main():
    app = P2PDialogApplication(bootstrap_nodes=bootstrap_nodes)
    app.run()
    sys.exit(app.app.exec_())

if __name__ == '__main__':
    main()