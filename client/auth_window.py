import re
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QHBoxLayout, QFormLayout, 
                             QMessageBox, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal
from styles.auth_style import AUTH_DIALOG_STYLE, REGISTER_STYLE_EXTRA, LOGIN_STYLE_EXTRA
import logging

logger = logging.getLogger('dialog_gui')

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