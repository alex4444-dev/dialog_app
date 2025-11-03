import sys
import os
import threading
import time
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QAction, QMenu, 
                             QMessageBox, QStatusBar, QTextEdit, QDialog,
                             QSystemTrayIcon, QStyle, QDesktopWidget)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon



# Добавляем путь к текущей директории для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from network_secure import SecureNetworkClient
    from auth_window import AuthWindow
    from users_panel import UsersPanel
    from chat_window import ChatWindow
    from notifications import NotificationWindow
    from call_window import CallWindow
    from call_utils import call_manager
    from audio_utils import audio_manager
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все файлы находятся в той же папке")
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

class SecureMainWindow(QMainWindow):
    # Определяем сигналы как атрибуты класса
    sig_message_received = pyqtSignal(str, str)
    sig_user_list_updated = pyqtSignal(list)
    sig_connection_status = pyqtSignal(str)
    sig_message_status = pyqtSignal(str, str)
    sig_call_received = pyqtSignal(str, str, str, str)  # action, username, call_type, call_id
    sig_system_message = pyqtSignal(str)  # Для безопасных системных сообщений
    sig_call_status = pyqtSignal(str, str)  # call_id, action
    
    def __init__(self, network_client, username):
        super().__init__()
        self.network_client = network_client
        self.username = username
        self.active_chats = {}
        self.is_authenticated = True
        self.pending_messages = {}
        self.notifications_enabled = True
        self.active_notifications = []
        
        # Для звонков
        self.active_calls = {}
        self.pending_calls = {}
        
        # Таймер для обновлений вместо отдельного потока
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_update_timer)
        
        # Сразу подключаем сигналы к слотам
        self.sig_message_received.connect(self.handle_message)
        self.sig_user_list_updated.connect(self.update_user_list)
        self.sig_connection_status.connect(self.update_connection_status)
        self.sig_message_status.connect(self.handle_message_status)
        self.sig_call_received.connect(self.handle_call)
        self.sig_system_message.connect(self.on_system_message)
        self.sig_call_status.connect(self.on_call_status)

        # ДИАГНОСТИКА: проверяем установку обработчиков
        logger.info("🔊 Установка обработчиков сетевых событий...")
        
        # Устанавливаем безопасные обработчики
        self.network_client.set_message_handler(self.handle_incoming_message)
        self.network_client.set_status_handler(self.handle_incoming_status)
        self.network_client.set_call_handler(self.handle_incoming_call)
        
        logger.info(f"🔊 Обработчик сообщений: {self.network_client.message_handler}")
        logger.info(f"🔊 Обработчик статусов: {self.network_client.status_handler}")
        logger.info(f"🔊 Обработчик звонков: {self.network_client.call_handler}")

        self.init_ui()
        
    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle(f'💬 Диалог - Безопасный мессенджер (Пользователь: {self.username})')
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
        self.statusBar().showMessage(f'✅ Подключено как: {self.username}')
        
        # Подключаем сигналы панели пользователей
        self.users_panel.user_selected.connect(self.open_chat)
        self.users_panel.refresh_requested.connect(self.refresh_user_list)
        self.users_panel.call_requested.connect(self.start_call)
        
        # Создаем системный трей
        self.setup_system_tray()
        
        # Запускаем работу мессенджера
        self.start_messaging()
        
        logger.info("Интерфейс инициализирован, сигналы подключены")
        
    def setup_system_tray(self):
        """Настройка системного трея"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            # Устанавливаем стандартную иконку
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
            self.tray_icon.setToolTip("Диалог - Безопасный мессенджер")
            
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
            
        # Создаем и показываем уведомление
        notification = NotificationWindow(title, message)
        notification.show_notification()
        self.active_notifications.append(notification)
        
        # Удаляем уведомление из списка после закрытия
        def remove_notification():
            if notification in self.active_notifications:
                self.active_notifications.remove(notification)
                
        notification.close_animation.finished.connect(remove_notification)
        
        # Также показываем уведомление в системном трее если доступно
        if self.tray_icon:
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.Information,
                3000
            )
        
    def on_tab_changed(self, index):
        """Обработка смены вкладки"""
        if index > 0:  # Не системная вкладка
            widget = self.tabs.widget(index)
            if hasattr(widget, 'set_active'):
                widget.set_active(True)
                # Помечаем все активные чаты как неактивные, кроме текущего
                for username, chat in self.active_chats.items():
                    if chat != widget and hasattr(chat, 'set_active'):
                        chat.set_active(False)
        
    def start_messaging(self):
        """Запуск работы мессенджера после успешной аутентификации"""
        self.sig_connection_status.emit("✅ Подключено к серверу")
        
        # Инициализируем аудио
        try:
            audio_ready = self.network_client.setup_universal_audio()
            if audio_ready:
                self.system_chat.append(f"✅ Аудио система: {self.network_client.audio_system}")
            else:
                self.system_chat.append("⚠️ Аудио недоступно")
        except Exception as e:
            logger.error(f"Ошибка инициализации аудио: {e}")
            self.system_chat.append("⚠️ Аудио недоступно")

        # Запускаем heartbeat
        try:
            self.network_client.start_heartbeat()
        except Exception as e:
            logger.error(f"Ошибка запуска heartbeat: {e}")

        # Отправляем информацию о клиенте
        try:
            self.network_client.send_client_info()
        except Exception as e:
            logger.error(f"Ошибка отправки client_info: {e}")

        # Запускаем получение обновлений через таймер
        self.start_listen_for_updates()
        
        # Обновляем список пользователей
        try:
            self.refresh_user_list()
        except Exception as e:
            logger.error(f"Ошибка обновления списка пользователей: {e}")

        self.system_chat.append(f"✅ Успешный вход как: {self.username}")
        
    def create_system_tab(self):
        """Создание системной вкладки для сообщений"""
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.setContentsMargins(12, 12, 12, 12)
        
        self.system_chat = QTextEdit()
        self.system_chat.setReadOnly(True)
        system_layout.addWidget(self.system_chat)
        
        self.tabs.addTab(system_tab, "📊 Система")
        
    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu('Файл')

        refresh_action = QAction('🔄 Обновить список пользователей', self)
        refresh_action.triggered.connect(self.refresh_user_list)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        # Уведомления
        notifications_menu = file_menu.addMenu('🔔 Уведомления')
        
        self.enable_notifications_action = QAction('Включить уведомления', self, checkable=True)
        self.enable_notifications_action.setChecked(True)
        self.enable_notifications_action.triggered.connect(self.toggle_notifications)
        notifications_menu.addAction(self.enable_notifications_action)
        
        file_menu.addSeparator()
        
        # Меню Звонки
        calls_menu = menubar.addMenu('📞 Звонки')
        
        call_settings_action = QAction('⚙️ Настройки звонков', self)
        call_settings_action.triggered.connect(self.show_call_settings)
        calls_menu.addAction(call_settings_action)
        
        file_menu.addSeparator()
        
        # Выход из системы
        logout_action = QAction('🚪 Выйти из системы', self)
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        # Выход из приложения
        exit_action = QAction('❌ Выйти', self)
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)
        
        # Меню Аккаунт
        account_menu = menubar.addMenu('👤 Аккаунт')
        
        profile_action = QAction('👤 Мой профиль', self)
        profile_action.triggered.connect(self.show_profile)
        account_menu.addAction(profile_action)
       
    def show_call_settings(self):
        """Показать настройки звонков"""
        QMessageBox.information(self, 'Настройки звонков', 
                              'Настройки аудио/видео:\n\n'
                              '• Микрофон: Системный по умолчанию\n'
                              '• Камера: Системная по умолчанию\n'
                              '• Динамики: Системные по умолчанию\n\n'
                              'Для изменения настроек проверьте системные настройки звука и видео.')
        
    def toggle_notifications(self, enabled):
        """Включение/выключение уведомлений"""
        self.notifications_enabled = enabled
        status = "включены" if enabled else "выключены"
        self.system_chat.append(f"🔔 Уведомления {status}")
        logger.info(f"Уведомления {status}")
        
    def show_profile(self):
        """Показать информацию о профиле"""
        QMessageBox.information(self, '👤 Мой профиль', 
                              f'Имя пользователя: {self.username}\n'
                              f'Статус: Online\n'
                              f'Активных чатов: {len(self.active_chats)}\n'
                              f'Активных звонков: {len(self.active_calls)}')
        
    def close_application(self):
        """Закрытие приложения"""
        self.close()
        
    def disconnect_from_server(self):
        """Отключение от сервера"""
        self.stop_listen_for_updates()
        self.network_client.disconnect()
        self.sig_connection_status.emit("❌ Отключено от сервера")
        self.is_authenticated = False
        
    def handle_incoming_message(self, from_user, message):
        """Обработка входящего сообщения от сервера"""
        logger.info(f"SecureMainWindow.handle_incoming_message: Получено сообщение от {from_user}: {message}")
        self.sig_message_received.emit(from_user, message)
        
    def handle_incoming_status(self, status, details):
        """Обработка входящего статуса от сервера"""
        logger.info(f"SecureMainWindow.handle_incoming_status: Получен статус: {status} - {details}")
        self.sig_message_status.emit(status, details)
        
    def handle_incoming_call(self, action, from_user, call_type=None, call_id=None):
        """Обработка входящего звонка от сервера - С ДОБАВЛЕНИЕМ CALL_IP"""
        logger.info(f"SecureMainWindow.handle_incoming_call: Получен звонок: {action} от {from_user}, тип: {call_type}, ID: {call_id}")
        
        # ДИАГНОСТИКА: выводим в системный чат
        self.system_chat.append(f"🔊 Сетевой обработчик: {action} от {from_user}")
        
        self.sig_call_received.emit(action, from_user, call_type, call_id)
        
    def start_listen_for_updates(self):
        """Запуск прослушивания обновлений от сервера через таймер"""
        # Запускаем таймер для обновлений каждые 20 секунд
        self.update_timer.start(20000)  # 20 секунд
        logger.info("Таймер обновлений запущен")
        
    def stop_listen_for_updates(self):
        """Остановка прослушивания обновлений"""
        self.is_authenticated = False
        if self.update_timer.isActive():
            self.update_timer.stop()
            logger.info("Таймер обновлений остановлен")
        
    def on_update_timer(self):
        """Обработчик таймера обновлений - безопасно работает в главном потоке"""
        if not self.is_authenticated or not self.network_client.connected:
            self.update_timer.stop()
            return
            
        try:
            # Получаем список пользователей
            users = self.network_client.get_user_list()
            if users is not None:
                self.sig_user_list_updated.emit(users)
                
        except Exception as e:
            error_msg = str(e)
            if "Не авторизован" in error_msg or "authorized" in error_msg.lower():
                self.is_authenticated = False
                self.system_chat.append("❌ Ошибка авторизации. Требуется повторный вход.")
                self.update_timer.stop()
            else:
                self.system_chat.append(f"⚠️ Ошибка получения обновлений: {e}")
        
    def refresh_user_list(self):
        """Обновление списка пользователей"""
        if self.network_client.connected and self.is_authenticated:
            users = self.network_client.get_user_list()
            if users:
                self.sig_user_list_updated.emit(users)
        
    def open_chat(self, username):
        """Открытие чата с пользователем"""
        logger.info(f"SecureMainWindow.open_chat: Открытие чата с {username}")
        
        # Убираем эмодзи из имени пользователя если есть
        clean_username = username.replace("👤 ", "")
        
        if clean_username in self.active_chats:
            chat_window = self.active_chats[clean_username]
            index = self.tabs.indexOf(chat_window)
            if index >= 0:
                self.tabs.setCurrentIndex(index)
                chat_window.set_active(True)
                logger.info(f"SecureMainWindow.open_chat: Чат с {clean_username} уже открыт, переключаемся на него")
                return
            else:
                # Вкладка не найдена, удаляем из активных чатов
                del self.active_chats[clean_username]
                logger.warning(f"SecureMainWindow.open_chat: Вкладка чата с {clean_username} не найдена, создаем заново")
            
        # Создаем новое окно чата
        logger.info(f"SecureMainWindow.open_chat: Создание нового чата с {clean_username}")
        chat_window = ChatWindow(clean_username)
        chat_window.message_sent.connect(self.send_message)
        chat_window.unread_count_changed.connect(self.update_tab_title)
        chat_window.call_requested.connect(self.start_call)
        
        # Добавляем вкладку
        tab_index = self.tabs.addTab(chat_window, f"💬 {clean_username}")
        self.tabs.setCurrentIndex(tab_index)
        chat_window.set_active(True)
        
        # Сохраняем ссылку на чат
        self.active_chats[clean_username] = chat_window
        logger.info(f"SecureMainWindow.open_chat: Чат с {clean_username} создан и добавлен в активные чаты. Индекс вкладки: {tab_index}")
        
    def close_chat_tab(self, index):
        """Закрытие вкладки чата"""
        if index == 0:  # Не закрываем системную вкладку
            return
            
        widget = self.tabs.widget(index)
        tab_text = self.tabs.tabText(index)
        
        # Убираем эмодзи из имени пользователя для поиска в active_chats
        username = tab_text.replace("💬 ", "")
        
        if username in self.active_chats:
            del self.active_chats[username]
            logger.info(f"SecureMainWindow.close_chat_tab: Закрыт чат с {username}")
            
        self.tabs.removeTab(index)
        
    def update_tab_title(self, username, unread_count):
        """Обновление заголовка вкладки с непрочитанными"""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if hasattr(widget, 'username') and widget.username == username:
                unread_text = f" ({unread_count}📩)" if unread_count > 0 else ""
                self.tabs.setTabText(i, f"💬 {username}{unread_text}")
                break
        
    def send_message(self, username, message):
        """Отправка сообщения"""
        if not self.network_client.connected:
            QMessageBox.warning(self, 'Ошибка', 'Нет подключения к серверу')
            return
            
        if not self.is_authenticated:
            QMessageBox.warning(self, 'Ошибка', 'Не авторизован')
            return
            
        try:
            logger.info(f"SecureMainWindow.send_message: Попытка отправить сообщение пользователю {username}: {message}")
            
            # Создаем уникальный ID для сообщения
            message_id = f"{username}_{time.time()}"
            self.pending_messages[message_id] = (username, message)
            
            if self.network_client.send_p2p_message(username, message, message_id):
                self.system_chat.append(f"✅ Сообщение отправлено пользователю {username}")
                logger.info(f"SecureMainWindow.send_message: Сообщение успешно отправлено")
            else:
                self.system_chat.append(f"❌ Не удалось отправить сообщение пользователю {username}")
                logger.error(f"SecureMainWindow.send_message: Ошибка отправки сообщения")
                
        except Exception as e:
            logger.error(f"SecureMainWindow.send_message: Ошибка отправки сообщения: {e}")
            QMessageBox.critical(self, 'Ошибка', f'Ошибка отправки: {e}')
            
    def handle_message(self, username, message):
        """Обработка полученного сообщения"""
        logger.info(f"SecureMainWindow.handle_message: НАЧАЛО ОБРАБОТКИ сообщения от {username}: {message}")
        
        # ДИАГНОСТИКА: сразу показываем в системной вкладке
        self.system_chat.append(f"📨 Получено сообщение от {username}: {message}")
        
        # Проверяем, не является ли это системным сообщением
        if username == "system":
            self.system_chat.append(f"📢 Система: {message}")
            return
            
        # Показываем уведомление, если окно не активно или свернуто
        if not self.isActiveWindow() or self.isMinimized():
            self.show_notification(f"💬 Новое сообщение от {username}", message)
            
        # Открываем чат с пользователем, если он еще не открыт
        if username not in self.active_chats:
            logger.info(f"SecureMainWindow.handle_message: Чат с {username} не открыт, открываем...")
            self.open_chat(username)
        
        # Добавляем сообщение в чат
        if username in self.active_chats:
            logger.info(f"SecureMainWindow.handle_message: Добавление сообщения в чат с {username}")
            chat_window = self.active_chats[username]
            
            # Проверяем, что чат существует и доступен
            if chat_window and hasattr(chat_window, 'add_message'):
                # Проверяем, активна ли сейчас эта вкладка
                current_index = self.tabs.currentIndex()
                current_widget = self.tabs.widget(current_index)
                is_active = current_widget == chat_window
                
                chat_window.set_active(is_active)
                chat_window.add_message(username, message, is_own=False)
                
                # Активируем вкладку с этим чатом, если она не активна
                if not is_active:
                    index = self.tabs.indexOf(chat_window)
                    if index >= 0:
                        logger.info(f"SecureMainWindow.handle_message: Вкладка чата с {username} не активна, но сообщение добавлено")
                else:
                    logger.info(f"SecureMainWindow.handle_message: Вкладка чата с {username} активна, сообщение добавлено")
            else:
                logger.error(f"SecureMainWindow.handle_message: Чат с {username} не инициализирован правильно")
        else:
            logger.error(f"SecureMainWindow.handle_message: Не удалось найти чат с {username} после попытки открытия")
            self.system_chat.append(f"❌ Ошибка: не удалось открыть чат с {username}")
            
        # Принудительно обновляем интерфейс
        QApplication.processEvents()
        logger.info(f"SecureMainWindow.handle_message: ЗАВЕРШЕНИЕ ОБРАБОТКИ сообщения от {username}")
            
    def handle_message_status(self, status, details):
        """Обработка статуса доставки сообщения"""
        logger.info(f"SecureMainWindow.handle_message_status: Обработка статуса сообщения: {status} - {details}")
        if status == "delivered":
            self.system_chat.append(f"✅ Сообщение доставлено: {details}")
        elif status == "failed":
            self.system_chat.append(f"❌ Ошибка доставки: {details}")
        elif status == "user_offline":
            self.system_chat.append(f"⚠️ Пользователь offline: {details}")
        elif status == "error":
            self.system_chat.append(f"⚠️ Ошибка: {details}")
            
    def start_call(self, username, call_type):
        """Начать звонок с пользователем"""
        logger.info(f"SecureMainWindow.start_call: Начало {call_type} звонка с {username}")
        
        # Отправляем запрос на звонок
        call_id = self.network_client.send_call_request(username, call_type)
        if not call_id:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить запрос на звонок')
            return
            
        # Создаем окно звонка
        call_window = CallWindow(username, call_type, call_id, is_outgoing=True, parent=self)
        call_window.call_ended.connect(self.end_call)
        call_window.show()
        
        # Сохраняем информацию о звонке - ИСПРАВЛЕННАЯ СТРОКА
        self.active_calls[call_id] = {
            'window': call_window,
            'username': username,
            'type': call_type,
            'outgoing': True
        }
        
        self.pending_calls[call_id] = username
        
        self.system_chat.append(f"📞 Отправлен запрос на {call_type} звонок пользователю {username}")
        
    def handle_call(self, action, from_user, call_type=None, call_id=None):
        """Обработка входящего звонка"""
        logger.info(f"SecureMainWindow.handle_call: Обработка звонка: {action} от {from_user}, тип: {call_type}, ID: {call_id}")
        

        # ДИАГНОСТИКА: сразу показываем в системном чате
        self.system_chat.append(f"🔊 Сигнал звонка: {action} от {from_user}")

        if action == 'incoming_call':
            # Входящий звонок
            self.handle_incoming_call_request(from_user, call_type, call_id)
            
        elif action == 'call_accepted':
            # Звонок принят
            self.handle_call_accepted(from_user, call_id)
            
        elif action == 'call_rejected':
            # Звонок отклонен
            self.handle_call_rejected(from_user, call_id)
            
        elif action == 'call_ended':
            # Звонок завершен
            self.handle_call_ended(from_user, call_id)
            
        elif action == 'call_info':
            # Информация о звонке
            self.handle_call_info(from_user, call_id)

        else:
            logger.warning(f"🔊 Неизвестное действие звонка: {action}")
            
    def handle_incoming_call_request(self, from_user, call_type, call_id):
        """Обработка входящего запроса на звонка"""
        # ПРОВЕРКА НА ДУБЛИРУЮЩИЕСЯ ЗВОНКИ
        if call_id in self.active_calls:
            logger.warning(f"Дублирующий запрос на звонок {call_id}, игнорируем")
            return

        logger.info(f"Обработка входящего звонка от {from_user}, тип: {call_type}")

        # ДИАГНОСТИКА: выводим в системный чат
        self.system_chat.append(f"🔊 ВХОДЯЩИЙ ЗВОНОК от {from_user}, тип: {call_type}")

        # Показываем уведомление
        self.show_notification(
            f"📞 Входящий {call_type} звонок",
            f"Пользователь {from_user} звонит вам"
        )
        
        # Создаем окно звонка
        try:
            call_window = CallWindow(from_user, call_type, call_id, is_outgoing=False, parent=self)
            call_window.call_ended.connect(self.end_call)
            call_window.call_accepted.connect(self.accept_call)
            call_window.call_rejected.connect(self.reject_call)
            
            # Сохраняем информацию о звонке
            self.active_calls[call_id] = {
                'window': call_window,
                'username': from_user,
                'type': call_type,
                'outgoing': False
            }

            # ПОКАЗЫВАЕМ ОКНО ЯВНО
            call_window.show()
            call_window.raise_()  # Поднимаем на передний план
            call_window.activateWindow()  # Активируем
        
            logger.info(f"🔊 Окно звонка показано и активировано")
        
            self.system_chat.append(f"📞 Входящий {call_type} звонок от {from_user}")
            logger.info(f"Создано окно звонка для {call_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания окна звонка: {e}")
            self.system_chat.append(f"❌ Ошибка создания окна звонка: {e}")
        
        
    def handle_call_accepted(self, from_user, call_id, call_port=None):
        """Обработка принятия звонка другим пользователем"""
        self.logger.info(f"🔊 Звонок принят пользователем {from_user}, порт: {call_port}")
        
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            
            # ПОДКЛЮЧАЕМСЯ К МЕДИА-СЕРВЕРУ ПОЛЬЗОВАТЕЛЯ
            if call_port and call_port > 0:
                # Используем localhost для тестирования
                host = 'localhost' 
                
                self.logger.info(f"🔊 Подключение к медиа-серверу {from_user} на {host}:{call_port}")
                
                if self.network_client.connect_to_call_server(host, call_port, call_id):
                    # Настраиваем сокет в окне звонка
                    call_info['window'].call_socket = self.network_client.call_sockets[call_id]
                    
                    # Запускаем реальные аудио потоки
                    call_info['window'].initialize_real_audio_streams()
                    call_info['window'].start_audio_receiver()
                    
                    self.logger.info("✅ Аудио соединение установлено")
                    self.system_chat.append(f"✅ Аудио соединение с {from_user} установлено")
                else:
                    self.logger.error("❌ Не удалось установить аудио соединение")
                    self.system_chat.append(f"⚠️ Не удалось установить аудио соединение с {from_user}")
            else:
                self.logger.warning("⚠️ Порт медиа-сервера не указан, продолжаем без аудио")
                self.system_chat.append(f"⚠️ Звонок с {from_user} продолжается без аудио")

            # Запускаем звонок в UI в любом случае
            call_info['window'].start_call()
            self.system_chat.append(f"✅ Пользователь {from_user} принял звонок")
        else:
            self.logger.warning(f"Звонок {call_id} не найден в активных звонках")
        
    def handle_call_rejected(self, from_user, call_id):
        """Обработка отклонения звонка"""
        logger.info(f"SecureMainWindow.handle_call_rejected: Звонок отклонен пользователем {from_user}")
        
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            call_window = call_info['window']
            
            # Закрываем окно звонка
            call_window.close()
            
            # Удаляем из активных звонков
            del self.active_calls[call_id]
            
            QMessageBox.information(self, 'Звонок отклонен', f'Пользователь {from_user} отклонил ваш звонок')
            self.system_chat.append(f"❌ Пользователь {from_user} отклонил звонок")
            
    def handle_call_ended(self, from_user, call_id):
        """Обработка завершения звонка"""
        logger.info(f"SecureMainWindow.handle_call_ended: Звонок завершен пользователем {from_user}")
        
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            call_window = call_info['window']
            
            # Закрываем окно звонка
            call_window.close()
            
            # Удаляем из активных звонков
            del self.active_calls[call_id]
            
            self.system_chat.append(f"📞 Звонок с {from_user} завершен")
        else:
            logger.info(f"Звонок {call_id} уже удален из активных")
            
    def handle_call_info(self, from_user, call_id):
        """Обработка информации о звонке"""
        logger.info(f"SecureMainWindow.handle_call_info: Информация о звонке от {from_user}")
        
    def accept_call(self, call_id):
        """Принять входящий звонок - ПРОСТАЯ И НАДЕЖНАЯ ВЕРСИЯ"""
        try:
            logger.info(f"=== ПОПЫТКА ПРИНЯТЬ ЗВОНОК {call_id} ===")
    
            if call_id not in self.active_calls:
                logger.error(f"❌ Звонок {call_id} не найден в active_calls")
                logger.error(f"❌ Доступные звонки: {list(self.active_calls.keys())}")
                return
        
            call_info = self.active_calls[call_id]
            username = call_info['username']
            logger.info(f"🔍 Информация о звонке: {call_info}")

            # 1. Запускаем медиа-сервер
            logger.info("🔊 Запуск медиа-сервера...")
            call_port = self.network_client.start_call_server(call_id, port=0)
            if not call_port:
                logger.error("❌ Не удалось запустить медиа-сервер")
                self.system_chat.append("❌ Не удалось запустить медиа-сервер")
                return

            logger.info(f"🔊 Медиа-сервер запущен на порту: {call_port}")

            

            logger.info("✅ Подтверждение отправлено успешно")

            # Отправляем подтверждение
            logger.info(f"📤 Отправка подтверждения на сервер с портом {call_port}...")
            if self.network_client.send_call_answer(call_id, 'accept', call_port):
                logger.info("✅ Подтверждение отправлено успешно")
        
            # 3. Запускаем ожидание медиа-соединения в отдельном потоке
            def wait_for_connection():
                logger.info(f"🔊 Ожидание медиа-соединения для звонка {call_id}...")
            
                # Ждем соединения
                if self.network_client.accept_call_connection(call_id, timeout=30):
                    logger.info(f"✅ Медиа-соединение для звонка {call_id} установлено")
                
                    # Устанавливаем сокет в окне звонка
                    if call_id in self.network_client.call_sockets:
                        logger.error(f"❌ Сокет для звонка {call_id} не создан")
                        return

                        call_socket = self.network_client.call_sockets[call_id]
                        logger.info(f"🔍 Сокет звонка: {call_socket}, тип: {type(call_socket)}")

                        success = self.network_client.accept_call_connection(call_id)
                        if success:
                            logger.info(f"✅ Медиа-соединение для звонка {call_id} установлено")

                            
                            # Настраиваем сокет в окне звонка
                            if call_id in self.network_client.call_sockets:
                                call_info['window'].call_socket = self.network_client.call_sockets[call_id]
                                logger.info(f"🔍 Сокет установлен в окне звонка: {call_info['window'].call_socket}")             
                        
                                # Запускаем аудио
                                try:
                                    call_info['window'].initialize_real_audio_streams()
                                    call_info['window'].start_audio_receiver()
                                    logger.info("✅ Аудио потоки запущены")
                                except Exception as e:
                                    logger.error(f"❌ Ошибка запуска аудио: {e}")
                            else:
                                logger.error("❌ Сокет звонка не найден после установки соединения")
                        else:
                            logger.error(f"❌ Не удалось установить медиа-соединение для звонка {call_id}")
                            self.system_chat.append("⚠️ Аудио соединение не установлено, но звонок продолжается")
                                
                    # Запускаем в отдельном потоке
                    media_thread = threading.Thread(target=wait_for_connection, daemon=True)
                    media_thread.start()
        
                    # Запускаем звонок в UI
                    call_info['window'].accept_call()
                    self.system_chat.append(f"✅ Вы приняли звонок от {username}")
                    logger.info("✅ Звонок принят в UI")
                else:
                    logger.error("❌ Не удалось отправить подтверждение")
                    self.system_chat.append("❌ Не удалось отправить подтверждение звонка")
    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в accept_call: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")


    def reject_call(self, call_id):
        """Отклонить входящий звонок"""
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            username = call_info['username']
            
            # Отправляем отклонение
            if self.network_client.send_call_answer(call_id, 'reject'):
                # Закрываем окно звонка
                call_info['window'].close()
                del self.active_calls[call_id]
                self.system_chat.append(f"❌ Вы отклонили звонок от {username}")
            else:
                QMessageBox.warning(self, 'Ошибка', 'Не удалось отправить отклонение звонка')
                
    def end_call(self, call_id):
        """Завершить активный звонок"""
        try:
            if call_id not in self.active_calls:
                logger.info(f"Попытка завершить несуществующий звонок {call_id}")
                return
            
            call_info = self.active_calls[call_id]
            username = call_info['username']
            
            # ✅ ПЕРВОЕ ДЕЛО - ОСТАНАВЛИВАЕМ UI
            if 'window' in call_info and call_info['window']:
                try:
                    # Используем отложенное закрытие для безопасности
                    call_info['window'].hide()
                    call_info['window'].deleteLater()
                except Exception as e:
                    logger.error(f"Ошибка закрытия окна звонка: {e}")

            # Отправляем сообщение о завершении
            success = self.network_client.send_call_end(call_id)
            if not success:
                logger.warning(f"Не удалось отправить сообщение о завершении звонка {call_id}")

            # Останавливаем медиа-ресурсы
            self.network_client.stop_call(call_id)
            
            
            
            # Удаляем из активных звонков
            if call_id in self.active_calls:
                del self.active_calls[call_id]
            
            self.system_chat.append(f"📞 Вы завершили звонок с {username}")
        
        except Exception as e:
            logger.error(f"❌ Ошибка завершения звонка {call_id}: {e}")
 
    def update_user_list(self, users):
        """Обновление списка пользователей"""
        logger.info(f"SecureMainWindow.update_user_list: Обновление списка пользователей: {len(users) if users else 0} пользователей")
        self.users_panel.update_users(users)
        
    def update_connection_status(self, status):
        """Обновление статуса соединения"""
        self.statusBar().showMessage(status)
        self.system_chat.append(f"{status}")

    def logout(self):
        """Выход из системы"""
        reply = QMessageBox.question(self, 'Выход из системы', 
                                   'Вы уверены, что хотите выйти из системы?', 
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Завершаем все активные звонки
            for call_id in list(self.active_calls.keys()):
                self.end_call(call_id)
                
            self.stop_listen_for_updates()
            self.network_client.logout()
            self.network_client.session_token = None
            self.network_client.username = None
            self.is_authenticated = False
            self.close()
            
    def closeEvent(self, event):
        """Обработка закрытия приложения"""
        # Завершаем все активные уведомления
        for notification in self.active_notifications:
            notification.close()
            
        # Завершаем все активные звонки
        for call_id in list(self.active_calls.keys()):
            self.end_call(call_id)
            
        self.disconnect_from_server()
        event.accept()

    # Безопасные методы для межпоточного общения
    def on_system_message(self, message):
        """Обработчик системных сообщений в главном потоке"""
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
            # Настройка аудио в главном потоке
            if call_id in self.network_client.call_sockets:
                call_window.call_socket = self.network_client.call_sockets[call_id]
                call_window.initialize_real_audio_streams()
                call_window.start_audio_receiver()
                self.system_chat.append("✅ Аудио соединение установлено")

class DialogApplication:
    """Класс управления приложением - запускает аутентификацию, затем главное окно"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.network_client = SecureNetworkClient()
        self.auth_window = None
        self.main_window = None
        
    def run(self):
        """Запуск приложения"""
        # Показываем окно авторизации сразу
        self.show_auth_dialog()
        
    def show_auth_dialog(self):
        """Показать диалог аутентификации"""
        self.auth_window = AuthWindow(self.network_client)
        self.auth_window.login_success.connect(self.on_login_success)
        
        # Запускаем подключение к серверу в фоне
        self.connect_to_server()
        
        # Запускаем диалог и проверяем результат
        result = self.auth_window.exec_()
        if result == QDialog.Rejected:
            self.on_auth_cancelled()
        
    def connect_to_server(self):
        """Подключение к серверу в фоновом режиме"""
        def connect_thread():
            logger.info("Попытка подключения к серверу...")
            self.auth_window.update_status("Установка соединения...")
            
            if self.network_client.connect():
                logger.info("Успешное подключение к серверу")
                # Обновляем статус в UI
                self.auth_window.update_status("✅ Подключено к серверу")
            else:
                logger.error("Не удалось подключиться к серверу")
                # Показываем ошибку в UI
                self.auth_window.update_status("❌ Ошибка подключения")
                QMessageBox.warning(self.auth_window, 'Ошибка', 'Не удалось подключиться к серверу')
        
        threading.Thread(target=connect_thread, daemon=True).start()
        
    def on_login_success(self, username):
        """Обработка успешного входа"""
        logger.info(f"Успешная аутентификация пользователя: {username}")
        # Создаем и показываем главное окно
        self.main_window = SecureMainWindow(self.network_client, username)
        self.main_window.show()
        
    def on_auth_cancelled(self):
        """Обработка отмены аутентификации"""
        logger.info("Аутентификация отменена")
        self.network_client.disconnect()
        sys.exit(0)

def main():
    app = DialogApplication()
    app.run()
    sys.exit(app.app.exec_())

if __name__ == '__main__':
    main()