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
                             QDialogButtonBox, QFormLayout, QFrame, QSystemTrayIcon,
                             QStyle, QDesktopWidget)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QIcon, QFont, QPixmap, QPainter, QColor

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

# Импортируем стили из отдельных файлов
try:
    from styles.auth_style import AUTH_DIALOG_STYLE, REGISTER_STYLE_EXTRA, LOGIN_STYLE_EXTRA
    from styles.main_style import MAIN_WINDOW_STYLE, CHAT_WINDOW_STYLE, USERS_PANEL_STYLE
except ImportError as e:
    print(f"Ошибка импорта стилей: {e}")
    print("Убедитесь, что папка styles и файлы стилей существуют")
    # Создаем базовые стили на случай ошибки импорта
    AUTH_DIALOG_STYLE = ""
    REGISTER_STYLE_EXTRA = ""
    LOGIN_STYLE_EXTRA = ""
    MAIN_WINDOW_STYLE = ""
    CHAT_WINDOW_STYLE = ""
    USERS_PANEL_STYLE = ""

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('dialog_gui')

class NotificationWindow(QWidget):
    """Всплывающее окно уведомления"""
    
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.title = title
        self.message = message
        self.init_ui()
        self.setup_animation()
        
    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(300, 100)
        
        # Позиционируем в правом верхнем углу
        screen_geometry = QDesktopWidget().availableGeometry()
        x = screen_geometry.width() - self.width() - 20
        y = 50
        self.move(x, y)
        
        # Создаем основной контейнер
        container = QWidget(self)
        container.setGeometry(0, 0, 300, 100)
        container.setStyleSheet("""
            QWidget {
                background-color: #2c3e50;
                border-radius: 10px;
                border: 2px solid #34495e;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)
        
        # Заголовок уведомления
        title_label = QLabel(self.title)
        title_label.setStyleSheet("""
            QLabel {
                color: #ecf0f1;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        layout.addWidget(title_label)
        
        # Текст сообщения
        message_label = QLabel(self.message)
        message_label.setStyleSheet("""
            QLabel {
                color: #bdc3c7;
                font-size: 12px;
            }
        """)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)
        
        # Кнопка закрытия
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_btn.clicked.connect(self.close_notification)
        
        # Размещаем кнопку закрытия в правом верхнем углу
        close_btn.move(275, 5)
        
    def setup_animation(self):
        """Настройка анимации появления и исчезновения"""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.close_animation = QPropertyAnimation(self, b"windowOpacity")
        self.close_animation.setDuration(300)
        self.close_animation.setStartValue(1)
        self.close_animation.setEndValue(0)
        self.close_animation.setEasingCurve(QEasingCurve.InCubic)
        self.close_animation.finished.connect(self.hide)
        
    def show_notification(self):
        """Показать уведомление с анимацией"""
        self.show()
        self.animation.start()
        
        # Автоматическое закрытие через 5 секунд
        QTimer.singleShot(5000, self.close_notification)
        
    def close_notification(self):
        """Закрыть уведомление с анимацией"""
        self.close_animation.start()
        
    def mousePressEvent(self, event):
        """Закрытие при клике"""
        self.close_notification()

class RegistrationWindow(QDialog):
    registration_success = pyqtSignal(str)
    
    def __init__(self, network_client, parent=None):
        super().__init__(parent)
        self.network_client = network_client
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('Регистрация - Диалог')
        self.setFixedSize(450, 500)
        self.setStyleSheet(AUTH_DIALOG_STYLE + REGISTER_STYLE_EXTRA)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Заголовок
        title = QLabel("Создание аккаунта")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Подзаголовок
        subtitle = QLabel("Присоединяйтесь к нашему сообществу")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.8); margin-bottom: 20px;")
        layout.addWidget(subtitle)
        
        # Форма регистрации
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
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
        form_layout.addRow('Подтверждение:', self.confirm_password_edit)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        self.register_btn = QPushButton("Создать аккаунт")
        self.register_btn.clicked.connect(self.register)
        self.register_btn.setDefault(True)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.register_btn)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
        
        # Ссылка на вход
        login_link = QLabel("Уже есть аккаунт? <a href='login' style='color: #e3f2fd;'>Войти в систему</a>")
        login_link.setObjectName("link")
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
        self.register_btn.setText("Регистрация...")
        
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
            self.register_btn.setText("Создать аккаунт")
            
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
        self.setWindowTitle('Вход в Диалог')
        self.setFixedSize(450, 500)
        self.setStyleSheet(AUTH_DIALOG_STYLE + LOGIN_STYLE_EXTRA)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Заголовок
        title = QLabel("Добро пожаловать")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Подзаголовок
        subtitle = QLabel("Войдите в свой аккаунт")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Статус
        self.status_label = QLabel("Подключаемся к серверу...")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Форма входа
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
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
        
        self.login_btn = QPushButton("Войти в систему")
        self.login_btn.clicked.connect(self.authenticate)
        self.login_btn.setDefault(True)
        
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.login_btn)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
        
        # Ссылка на регистрацию
        register_link = QLabel("Нет аккаунта? <a href='register' style='color: #e3f2fd;'>Зарегистрироваться</a>")
        register_link.setObjectName("link")
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
        self.login_btn.setText("Вход...")
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
            self.login_btn.setText("Войти в систему")
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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Заголовок
        title = QLabel("Пользователи онлайн")
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
        
        # Список пользователей
        self.users_list = QListWidget()
        self.users_list.itemDoubleClicked.connect(self.on_user_double_clicked)
        layout.addWidget(self.users_list)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        button_layout.addWidget(self.refresh_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setStyleSheet(USERS_PANEL_STYLE)
        
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
                        self.users_list.addItem(f"👤 {username}")
                elif isinstance(user, str):
                    # Убираем эмодзи если уже есть
                    clean_username = user.replace("👤 ", "")
                    self.users_list.addItem(f"👤 {clean_username}")

class ChatWindow(QWidget):
    message_sent = pyqtSignal(str, str)  # username, message
    unread_count_changed = pyqtSignal(str, int)  # username, unread_count
    
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.message_count = 0  # Счетчик всех сообщений
        self.unread_count = 0   # Счетчик непрочитанных сообщений
        self.is_active_tab = False  # Флаг активности вкладки
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Заголовок с счетчиком сообщений
        self.title_label = QLabel(f"💬 Чат с {self.username}")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            color: #2c3e50; 
            padding: 12px;
            background-color: #f8f9fa;
            border-radius: 8px;
        """)
        layout.addWidget(self.title_label)
        
        # История сообщений
        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("chat_history")
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)
        
        # Поле ввода и кнопка отправки
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)
        
        self.message_input = QLineEdit()
        self.message_input.setObjectName("message_input")
        self.message_input.returnPressed.connect(self.send_message)
        self.message_input.setPlaceholderText("Введите сообщение...")
        
        self.send_btn = QPushButton("📤 Отправить")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input, 4)
        input_layout.addWidget(self.send_btn, 1)
        
        layout.addLayout(input_layout)
        self.setLayout(layout)
        
        # Применяем стили
        self.setStyleSheet(CHAT_WINDOW_STYLE)
        self.update_title()
        
    def set_active(self, active):
        """Установка флага активности вкладки"""
        self.is_active_tab = active
        if active and self.unread_count > 0:
            self.mark_as_read()
            
    def mark_as_read(self):
        """Пометить все сообщения как прочитанные"""
        if self.unread_count > 0:
            old_unread = self.unread_count
            self.unread_count = 0
            self.update_title()
            self.unread_count_changed.emit(self.username, 0)
            logger.info(f"ChatWindow.mark_as_read: Сброшено {old_unread} непрочитанных сообщений в чате с {self.username}")
        
    def update_title(self):
        """Обновление заголовка с учетом непрочитанных"""
        unread_text = f" ({self.unread_count}📩)" if self.unread_count > 0 else ""
        self.title_label.setText(f"💬 Чат с {self.username}{unread_text}")
        
    def send_message(self):
        message = self.message_input.text().strip()
        if message:
            self.message_sent.emit(self.username, message)
            self.add_message("Вы", message, is_own=True)
            self.message_input.clear()
            
    def add_message(self, sender, message, is_own=False):
        try:
            logger.info(f"ChatWindow.add_message: Добавление сообщения в чат {self.username}: {sender} - {message}")
            
            # Увеличиваем общий счетчик сообщений
            self.message_count += 1
            
            # Увеличиваем счетчик непрочитанных, если это не наше сообщение и вкладка не активна
            if not is_own and not self.is_active_tab:
                self.unread_count += 1
                self.unread_count_changed.emit(self.username, self.unread_count)
                logger.info(f"ChatWindow.add_message: Увеличено количество непрочитанных до {self.unread_count}")
            
            self.update_title()
            
            # Простой текст без HTML
            timestamp = time.strftime("%H:%M:%S")
            if is_own:
                full_message = f"[{timestamp}] 👤 Вы: {message}"
            else:
                full_message = f"[{timestamp}] 👤 {sender}: {message}"
            
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
        self.notifications_enabled = True  # Флаг для уведомлений
        self.active_notifications = []  # Список активных уведомлений
        
        # Сразу подключаем сигналы к слотам
        self.sig_message_received.connect(self.handle_message)
        self.sig_user_list_updated.connect(self.update_user_list)
        self.sig_connection_status.connect(self.update_connection_status)
        self.sig_message_status.connect(self.handle_message_status)
        
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
        self.tabs.currentChanged.connect(self.on_tab_changed)  # Отслеживаем смену вкладок
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
        # Устанавливаем обработчик входящих сообщений
        logger.info("Установка обработчиков сообщений и статусов")
        self.network_client.set_message_handler(self.handle_incoming_message)
        self.network_client.set_status_handler(self.handle_incoming_status)
        self.sig_connection_status.emit("✅ Подключено к серверу")
        
        # Запускаем heartbeat
        self.network_client.start_heartbeat()
        
        # Запускаем получение обновлений
        self.start_listen_for_updates()
        
        # Обновляем список пользователей
        self.refresh_user_list()
        
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
                              f'Активных чатов: {len(self.active_chats)}')
        
    def close_application(self):
        """Закрытие приложения"""
        self.disconnect_from_server()
        QApplication.quit()
        
    def disconnect_from_server(self):
        """Отключение от сервера"""
        self.stop_listen_for_updates()
        self.network_client.disconnect()
        self.sig_connection_status.emit("❌ Отключено от сервера")
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
                    self.system_chat.append("❌ Ошибка авторизации. Требуется повторный вход.")
                    break
                else:
                    self.system_chat.append(f"⚠️ Ошибка получения обновлений: {e}")
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
        
        # Убираем эмодзи из имени пользователя если есть
        clean_username = username.replace("👤 ", "")
        
        if clean_username in self.active_chats:
            chat_window = self.active_chats[clean_username]
            index = self.tabs.indexOf(chat_window)
            if index >= 0:
                self.tabs.setCurrentIndex(index)
                chat_window.set_active(True)  # Активируем чат
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
        
        # Добавляем вкладку
        tab_index = self.tabs.addTab(chat_window, f"💬 {clean_username}")
        self.tabs.setCurrentIndex(tab_index)
        chat_window.set_active(True)  # Новая вкладка активна
        
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
            
    def show_notification(self, username, message):
        """Показать уведомление о новом сообщении"""
        if not self.notifications_enabled:
            return
            
        # Создаем и показываем уведомление
        notification = NotificationWindow(
            f"💬 Новое сообщение от {username}",
            message
        )
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
                f"💬 Диалог - сообщение от {username}",
                message,
                QSystemTrayIcon.Information,
                3000
            )
            
    def handle_message(self, username, message):
        """Обработка полученного сообщения"""
        logger.info(f"SecureMainWindow.handle_message: НАЧАЛО ОБРАБОТКИ сообщения от {username}: {message}")
        logger.info(f"SecureMainWindow.handle_message: Активные чаты: {list(self.active_chats.keys())}")
        
        # ДИАГНОСТИКА: сразу показываем в системной вкладке
        self.system_chat.append(f"📨 Получено сообщение от {username}: {message}")
        
        # Проверяем, не является ли это системным сообщением
        if username == "system":
            self.system_chat.append(f"📢 Система: {message}")
            return
            
        # Показываем уведомление, если окно не активно или свернуто
        if not self.isActiveWindow() or self.isMinimized():
            self.show_notification(username, message)
            
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
        # Закрываем все активные уведомления
        for notification in self.active_notifications:
            notification.close()
            
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