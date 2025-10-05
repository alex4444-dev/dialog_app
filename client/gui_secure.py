import sys
import os
import threading
import time
import logging
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QAction, QMenu, 
                             QMessageBox, QStatusBar, QTextEdit, QLineEdit,
                             QPushButton, QListWidget, QLabel, QDialog,
                             QDialogButtonBox, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QIcon

# Добавляем путь к текущей директории для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from network_secure import SecureNetworkClient
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что файл network_secure.py находится в той же папке")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('dialog_gui')

class RegistrationWindow(QDialog):
    registration_success = pyqtSignal(str)
    
    def __init__(self, network_client, parent=None):
        super().__init__(parent)
        self.network_client = network_client
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('Регистрация - Диалог')
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel("Создание нового аккаунта")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Форма регистрации
        form_layout = QFormLayout()
        
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Введите имя пользователя")
        
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Введите email")
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Введите пароль")
        
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit.setPlaceholderText("Повторите пароль")
        
        form_layout.addRow('Имя пользователя:', self.username_edit)
        form_layout.addRow('Email:', self.email_edit)
        form_layout.addRow('Пароль:', self.password_edit)
        form_layout.addRow('Подтверждение пароля:', self.confirm_password_edit)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        self.register_btn = QPushButton("Зарегистрироваться")
        self.register_btn.clicked.connect(self.register)
        self.register_btn.setDefault(True)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.register_btn)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
        
        # Ссылка на вход
        login_link = QLabel("Уже есть аккаунт? <a href='login'>Войти</a>")
        login_link.setAlignment(Qt.AlignCenter)
        login_link.linkActivated.connect(self.show_login)
        layout.addWidget(login_link)
        
        self.setLayout(layout)
        
    def validate_input(self):
        """Проверка введенных данных"""
        username = self.username_edit.text().strip()
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()
        
        # Проверка имени пользователя
        if len(username) < 3:
            QMessageBox.warning(self, 'Ошибка', 'Имя пользователя должно содержать минимум 3 символа')
            return False
            
        # Проверка email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            QMessageBox.warning(self, 'Ошибка', 'Введите корректный email адрес')
            return False
            
        # Проверка пароля
        if len(password) < 6:
            QMessageBox.warning(self, 'Ошибка', 'Пароль должен содержать минимум 6 символов')
            return False
            
        # Проверка подтверждения пароля
        if password != confirm_password:
            QMessageBox.warning(self, 'Ошибка', 'Пароли не совпадают')
            return False
            
        return True
        
    def register(self):
        """Регистрация нового пользователя"""
        if not self.validate_input():
            return
            
        username = self.username_edit.text().strip()
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        
        if not self.network_client.connected:
            QMessageBox.warning(self, 'Ошибка', 'Нет подключения к серверу')
            return
            
        # Показываем индикатор загрузки
        self.setCursor(Qt.WaitCursor)
        self.register_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        try:
            if self.network_client.register(username, password, email):
                QMessageBox.information(self, 'Успех', 'Регистрация прошла успешно! Теперь вы можете войти в систему.')
                self.registration_success.emit(username)
                self.accept()
            else:
                error_msg = getattr(self.network_client, 'last_error', 'Неизвестная ошибка')
                QMessageBox.critical(self, 'Ошибка', f'Ошибка регистрации: {error_msg}')
        except Exception as e:
            logger.error(f"Ошибка при регистрации: {e}")
            QMessageBox.critical(self, 'Ошибка', f'Ошибка регистрации: {str(e)}')
        finally:
            self.setCursor(Qt.ArrowCursor)
            self.register_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            
    def show_login(self):
        """Показать окно входа"""
        self.reject()

class AuthWindow(QDialog):
    login_success = pyqtSignal(str)
    
    def __init__(self, network_client, parent=None):
        super().__init__(parent)
        self.network_client = network_client
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('Аутентификация - Диалог')
        self.setFixedSize(350, 300)
        
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel("Вход в систему")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Статус
        self.status_label = QLabel("Подключаемся к серверу...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Форма входа
        form_layout = QFormLayout()
        
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Введите имя пользователя")
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Введите пароль")
        
        form_layout.addRow('Имя пользователя:', self.username_edit)
        form_layout.addRow('Пароль:', self.password_edit)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        self.login_btn = QPushButton("Войти")
        self.login_btn.clicked.connect(self.authenticate)
        self.login_btn.setDefault(True)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.login_btn)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
        
        # Ссылка на регистрацию
        register_link = QLabel("Нет аккаунта? <a href='register'>Зарегистрироваться</a>")
        register_link.setAlignment(Qt.AlignCenter)
        register_link.linkActivated.connect(self.show_registration)
        layout.addWidget(register_link)
        
        self.setLayout(layout)
        
    def update_status(self, message):
        """Обновление статуса подключения"""
        self.status_label.setText(message)
        QApplication.processEvents()
        
    def authenticate(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, 'Ошибка', 'Заполните все поля')
            return
            
        if not self.network_client.connected:
            QMessageBox.warning(self, 'Ошибка', 'Нет подключения к серверу')
            return
            
        # Показываем индикатор загрузки
        self.setCursor(Qt.WaitCursor)
        self.login_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Проверка учетных данных...")
        
        try:
            if self.network_client.login(username, password):
                self.login_success.emit(username)
                self.accept()
            else:
                error_msg = getattr(self.network_client, 'last_error', 'Неверные данные для входа или проблема с сервером')
                QMessageBox.critical(self, 'Ошибка', error_msg)
                self.status_label.setText("Ошибка аутентификации")
        finally:
            self.setCursor(Qt.ArrowCursor)
            self.login_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            if not self.network_client.connected:
                self.status_label.setText("Нет подключения к серверу")

    def show_registration(self):
        """Показать окно регистрации"""
        registration_window = RegistrationWindow(self.network_client, self)
        registration_window.registration_success.connect(self.on_registration_success)
        registration_window.exec_()
        
    def on_registration_success(self, username):
        """Обработка успешной регистрации"""
        # Автоматически заполняем поле имени пользователя
        self.username_edit.setText(username)
        self.password_edit.setFocus()

class UsersPanel(QWidget):
    user_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel("Пользователи")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Список пользователей
        self.users_list = QListWidget()
        self.users_list.itemDoubleClicked.connect(self.on_user_double_clicked)
        layout.addWidget(self.users_list)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        button_layout.addWidget(self.refresh_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def on_user_double_clicked(self, item):
        self.user_selected.emit(item.text())
        
    def update_users(self, users):
        """Обновление списка пользователей"""
        self.users_list.clear()
        if users:
            for user in users:
                if isinstance(user, dict):
                    username = user.get('username')
                    if username:
                        self.users_list.addItem(username)
                elif isinstance(user, str):
                    self.users_list.addItem(user)

class ChatWindow(QWidget):
    message_sent = pyqtSignal(str, str)  # username, message
    
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel(f"Чат с {self.username}")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # История сообщений
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)
        
        # Поле ввода и кнопка отправки
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.returnPressed.connect(self.send_message)
        self.message_input.setPlaceholderText("Введите сообщение...")
        
        self.send_btn = QPushButton("Отправить")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        self.setLayout(layout)
        
    def send_message(self):
        message = self.message_input.text().strip()
        if message:
            self.message_sent.emit(self.username, message)
            self.add_message("Вы", message, is_own=True)
            self.message_input.clear()
            
    def add_message(self, sender, message, is_own=False):
        try:
            logger.info(f"ChatWindow.add_message: Добавление сообщения в чат {self.username}: {sender} - {message}")
            
            # Простой текст без HTML
            timestamp = time.strftime("%H:%M:%S")
            if is_own:
                full_message = f"[{timestamp}] Вы: {message}"
            else:
                full_message = f"[{timestamp}] {sender}: {message}"
            
            # Добавляем сообщение в историю
            self.chat_history.append(full_message)
            
            # Прокручиваем вниз
            scrollbar = self.chat_history.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
            # Принудительно обновляем отображение
            self.chat_history.repaint()
            QApplication.processEvents()
            
            logger.info(f"ChatWindow.add_message: Сообщение успешно добавлено в чат {self.username}: '{full_message}'")
            
        except Exception as e:
            logger.error(f"ChatWindow.add_message: Ошибка при добавлении сообщения в чат: {e}")

class SecureMainWindow(QMainWindow):
    # Определяем сигналы как атрибуты класса с префиксом sig_
    sig_message_received = pyqtSignal(str, str)
    sig_user_list_updated = pyqtSignal(list)
    sig_connection_status = pyqtSignal(str)
    sig_message_status = pyqtSignal(str, str)
    
    def __init__(self, network_client, username):
        super().__init__()
        self.network_client = network_client
        self.username = username
        self.active_chats = {}
        self.update_thread = None
        self.is_authenticated = True  # Уже аутентифицированы при создании
        self.pending_messages = {}
        
        # Сразу подключаем сигналы к слотам
        self.sig_message_received.connect(self.handle_message)
        self.sig_user_list_updated.connect(self.update_user_list)
        self.sig_connection_status.connect(self.update_connection_status)
        self.sig_message_status.connect(self.handle_message_status)
        
        self.init_ui()
        
    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle(f'Диалог - Безопасный мессенджер (Пользователь: {self.username})')
        self.setGeometry(100, 100, 900, 600)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QHBoxLayout(central_widget)
        
        # Левая панель - пользователи
        self.users_panel = UsersPanel()
        self.users_panel.setFixedWidth(250)
        main_layout.addWidget(self.users_panel)
        
        # Правая панель - чаты
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_chat_tab)
        main_layout.addWidget(self.tabs)
        
        # Создаем системную вкладку
        self.create_system_tab()
        
        # Панель меню
        self.create_menu()
        
        # Статус бар
        self.statusBar().showMessage(f'Подключено как: {self.username}')
        
        # Подключаем сигналы панели пользователей
        self.users_panel.user_selected.connect(self.open_chat)
        self.users_panel.refresh_requested.connect(self.refresh_user_list)
        
        # Запускаем работу мессенджера
        self.start_messaging()
        
        logger.info("Интерфейс инициализирован, сигналы подключены")
        
    def start_messaging(self):
        """Запуск работы мессенджера после успешной аутентификации"""
        # Устанавливаем обработчик входящих сообщений
        logger.info("Установка обработчиков сообщений и статусов")
        self.network_client.set_message_handler(self.handle_incoming_message)
        self.network_client.set_status_handler(self.handle_incoming_status)
        self.sig_connection_status.emit("Подключено к серверу")
        
        # Запускаем heartbeat
        self.network_client.start_heartbeat()
        
        # Запускаем получение обновлений
        self.start_listen_for_updates()
        
        # Обновляем список пользователей
        self.refresh_user_list()
        
        self.system_chat.append(f"Успешный вход как: {self.username}")
        
    def create_system_tab(self):
        """Создание системной вкладки для сообщений"""
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        
        self.system_chat = QTextEdit()
        self.system_chat.setReadOnly(True)
        system_layout.addWidget(self.system_chat)
        
        self.tabs.addTab(system_tab, "Система")
        
    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu('Файл')
        
        refresh_action = QAction('Обновить список пользователей', self)
        refresh_action.triggered.connect(self.refresh_user_list)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        # Выход из системы
        logout_action = QAction('Выйти из системы', self)
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)
        
        # Выход из приложения
        exit_action = QAction('Выйти', self)
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)
        
        # Меню Аккаунт
        account_menu = menubar.addMenu('Аккаунт')
        
        profile_action = QAction('Мой профиль', self)
        profile_action.triggered.connect(self.show_profile)
        account_menu.addAction(profile_action)
        
    def show_profile(self):
        """Показать информацию о профиле"""
        QMessageBox.information(self, 'Мой профиль', 
                              f'Имя пользователя: {self.username}\n'
                              f'Статус: Online')
        
    def close_application(self):
        """Закрытие приложения"""
        self.disconnect_from_server()
        QApplication.quit()
        
    def disconnect_from_server(self):
        """Отключение от сервера"""
        self.stop_listen_for_updates()
        self.network_client.disconnect()
        self.sig_connection_status.emit("Отключено от сервера")
        self.is_authenticated = False
        
    def handle_incoming_message(self, from_user, message):
        """Обработка входящего сообщения от сервера"""
        logger.info(f"SecureMainWindow.handle_incoming_message: Получено сообщение от {from_user}: {message}")
        # Испускаем сигнал, который вызовет handle_message в главном потоке
        self.sig_message_received.emit(from_user, message)
        
    def handle_incoming_status(self, status, details):
        """Обработка входящего статуса от сервера"""
        logger.info(f"SecureMainWindow.handle_incoming_status: Получен статус: {status} - {details}")
        self.sig_message_status.emit(status, details)
        
    def start_listen_for_updates(self):
        """Запуск прослушивания обновлений от сервера"""
        if self.update_thread and self.update_thread.is_alive():
            return
            
        self.update_thread = threading.Thread(target=self.listen_for_updates, daemon=True)
        self.update_thread.start()
        
    def stop_listen_for_updates(self):
        """Остановка прослушивания обновлений"""
        self.is_authenticated = False
        
    def listen_for_updates(self):
        """Прослушивание обновлений от сервера"""
        while self.network_client.connected and self.is_authenticated:
            try:
                # Получаем список пользователей
                users = self.network_client.get_user_list()
                if users is not None:
                    self.sig_user_list_updated.emit(users)
                
                time.sleep(20)
            
            except Exception as e:
                error_msg = str(e)
                if "Не авторизован" in error_msg or "authorized" in error_msg.lower():
                    self.is_authenticated = False
                    self.system_chat.append("Ошибка авторизации. Требуется повторный вход.")
                    break
                else:
                    self.system_chat.append(f"Ошибка получения обновлений: {e}")
                time.sleep(20)
        
    def refresh_user_list(self):
        """Обновление списка пользователей"""
        if self.network_client.connected and self.is_authenticated:
            users = self.network_client.get_user_list()
            if users:
                self.sig_user_list_updated.emit(users)
        
    def open_chat(self, username):
        """Открытие чата с пользователем"""
        logger.info(f"SecureMainWindow.open_chat: Открытие чата с {username}")
        
        if username in self.active_chats:
            chat_window = self.active_chats[username]
            index = self.tabs.indexOf(chat_window)
            if index >= 0:
                self.tabs.setCurrentIndex(index)
                logger.info(f"SecureMainWindow.open_chat: Чат с {username} уже открыт, переключаемся на него")
                return
            else:
                # Вкладка не найдена, удаляем из активных чатов
                del self.active_chats[username]
                logger.warning(f"SecureMainWindow.open_chat: Вкладка чата с {username} не найдена, создаем заново")
            
        # Создаем новое окно чата
        logger.info(f"SecureMainWindow.open_chat: Создание нового чата с {username}")
        chat_window = ChatWindow(username)
        chat_window.message_sent.connect(self.send_message)
        
        # Добавляем вкладку
        tab_index = self.tabs.addTab(chat_window, username)
        self.tabs.setCurrentIndex(tab_index)
        
        # Сохраняем ссылку на чат
        self.active_chats[username] = chat_window
        logger.info(f"SecureMainWindow.open_chat: Чат с {username} создан и добавлен в активные чаты. Индекс вкладки: {tab_index}")
        
    def close_chat_tab(self, index):
        """Закрытие вкладки чата"""
        if index == 0:  # Не закрываем системную вкладку
            return
            
        widget = self.tabs.widget(index)
        tab_text = self.tabs.tabText(index)
        
        if tab_text in self.active_chats:
            del self.active_chats[tab_text]
            logger.info(f"SecureMainWindow.close_chat_tab: Закрыт чат с {tab_text}")
            
        self.tabs.removeTab(index)
        
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
                self.system_chat.append(f"Сообщение отправлено пользователю {username}")
                logger.info(f"SecureMainWindow.send_message: Сообщение успешно отправлено")
            else:
                self.system_chat.append(f"Не удалось отправить сообщение пользователю {username}")
                logger.error(f"SecureMainWindow.send_message: Ошибка отправки сообщения")
                
        except Exception as e:
            logger.error(f"SecureMainWindow.send_message: Ошибка отправки сообщения: {e}")
            QMessageBox.critical(self, 'Ошибка', f'Ошибка отправки: {e}')
            
    def handle_message(self, username, message):
        """Обработка полученного сообщения"""
        logger.info(f"SecureMainWindow.handle_message: НАЧАЛО ОБРАБОТКИ сообщения от {username}: {message}")
        logger.info(f"SecureMainWindow.handle_message: Активные чаты: {list(self.active_chats.keys())}")
        
        # ДИАГНОСТИКА: сразу показываем в системной вкладке
        self.system_chat.append(f"ДИАГНОСТИКА: Получено сообщение от {username}: {message}")
        
        # Проверяем, не является ли это системным сообщением
        if username == "system":
            self.system_chat.append(f"Система: {message}")
            return
            
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
                chat_window.add_message(username, message)
                
                # Активируем вкладку с этим чатом
                index = self.tabs.indexOf(chat_window)
                if index >= 0:
                    self.tabs.setCurrentIndex(index)
                    logger.info(f"SecureMainWindow.handle_message: Активирована вкладка чата с {username}, индекс: {index}")
                else:
                    logger.error(f"SecureMainWindow.handle_message: Не удалось найти вкладку для чата с {username}")
            else:
                logger.error(f"SecureMainWindow.handle_message: Чат с {username} не инициализирован правильно")
        else:
            logger.error(f"SecureMainWindow.handle_message: Не удалось найти чат с {username} после попытки открытия")
            self.system_chat.append(f"Ошибка: не удалось открыть чат с {username}")
            
        # Принудительно обновляем интерфейс
        QApplication.processEvents()
        logger.info(f"SecureMainWindow.handle_message: ЗАВЕРШЕНИЕ ОБРАБОТКИ сообщения от {username}")
            
    def handle_message_status(self, status, details):
        """Обработка статуса доставки сообщения"""
        logger.info(f"SecureMainWindow.handle_message_status: Обработка статуса сообщения: {status} - {details}")
        if status == "delivered":
            self.system_chat.append(f"✓ Сообщение доставлено: {details}")
        elif status == "failed":
            self.system_chat.append(f"✗ Ошибка доставки: {details}")
        elif status == "user_offline":
            self.system_chat.append(f"⚠ Пользователь offline: {details}")
        elif status == "error":
            self.system_chat.append(f"⚠ Ошибка: {details}")
            
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
            self.stop_listen_for_updates()
            self.network_client.logout()
            self.network_client.session_token = None
            self.network_client.username = None
            self.is_authenticated = False
            self.close()
            
    def closeEvent(self, event):
        """Обработка закрытия приложения"""
        self.disconnect_from_server()
        event.accept()

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
            if self.network_client.connect():
                logger.info("Успешное подключение к серверу")
                # Обновляем статус в UI
                self.auth_window.update_status("Подключено к серверу. Введите учетные данные.")
            else:
                logger.error("Не удалось подключиться к серверу")
                # Показываем ошибку в UI
                self.auth_window.update_status("Ошибка подключения к серверу")
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