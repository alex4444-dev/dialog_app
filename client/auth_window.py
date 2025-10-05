from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLineEdit, QPushButton, QLabel, QMessageBox, QTabWidget, QWidget)
from PyQt5.QtCore import pyqtSignal, Qt, QObject
from PyQt5.QtGui import QFont

class AuthWindow(QDialog):
    login_success = pyqtSignal(str)  # Сигнал об успешном входе (username)
    show_error_signal = pyqtSignal(str, str)  # title, message
    show_success_signal = pyqtSignal(str, str)  # title, message
    enable_login_button_signal = pyqtSignal(bool)
    enable_register_button_signal = pyqtSignal(bool)
    switch_to_login_tab_signal = pyqtSignal(str)
    
    def __init__(self, network_client, parent=None):
        super().__init__(parent)
        self.network_client = network_client
        self.setWindowTitle('Аутентификация')
        self.setFixedSize(400, 300)
        self.setModal(True)  # Делаем окно модальным
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Создаем вкладки для входа и регистрации
        self.tabs = QTabWidget()
        
        # Вкладка входа
        login_tab = QWidget()
        login_layout = QVBoxLayout(login_tab)
        
        login_form = QFormLayout()
        self.login_username = QLineEdit()
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        
        login_form.addRow('Имя пользователя:', self.login_username)
        login_form.addRow('Пароль:', self.login_password)
        
        self.login_btn = QPushButton('Войти')
        self.login_btn.clicked.connect(self.handle_login)
        
        login_layout.addLayout(login_form)
        login_layout.addWidget(self.login_btn)
        login_layout.addStretch()
        
        # Вкладка регистрации
        register_tab = QWidget()
        register_layout = QVBoxLayout(register_tab)
        
        register_form = QFormLayout()
        self.register_username = QLineEdit()
        self.register_password = QLineEdit()
        self.register_password.setEchoMode(QLineEdit.Password)
        self.register_email = QLineEdit()
        
        register_form.addRow('Имя пользователя:', self.register_username)
        register_form.addRow('Пароль:', self.register_password)
        register_form.addRow('Email (необязательно):', self.register_email)
        
        self.register_btn = QPushButton('Зарегистрироваться')
        self.register_btn.clicked.connect(self.handle_register)
        
        register_layout.addLayout(register_form)
        register_layout.addWidget(self.register_btn)
        register_layout.addStretch()
        
        # Добавляем вкладки
        self.tabs.addTab(login_tab, "Вход")
        self.tabs.addTab(register_tab, "Регистрация")
        
        layout.addWidget(self.tabs)
        
    def connect_signals(self):
        self.show_error_signal.connect(self.show_error_dialog)
        self.show_success_signal.connect(self.show_success_dialog)
        self.enable_login_button_signal.connect(self.login_btn.setEnabled)
        self.enable_register_button_signal.connect(self.register_btn.setEnabled)
        self.switch_to_login_tab_signal.connect(self.switch_to_login_tab)
        
    def show_error_dialog(self, title, message):
        QMessageBox.warning(self, title, message)
        
    def show_success_dialog(self, title, message):
        QMessageBox.information(self, title, message)
        
    def switch_to_login_tab(self, username):
        self.tabs.setCurrentIndex(0)
        self.login_username.setText(username)
        
    def handle_login(self):
        username = self.login_username.text()
        password = self.login_password.text()
        
        if not username or not password:
            self.show_error_signal.emit('Ошибка', 'Заполните все поля')
            return
            
        # Отключаем кнопку во время выполнения операции
        self.login_btn.setEnabled(False)
        
        # Вызываем метод в отдельном потоке чтобы не блокировать GUI
        import threading
        thread = threading.Thread(target=self._perform_login, args=(username, password))
        thread.daemon = True
        thread.start()
            
    def _perform_login(self, username, password):
        try:
            if self.network_client.login(username, password):
                self.login_success.emit(username)
                # Закрываем окно в главном потоке
                self.accept()
            else:
                self.show_error_signal.emit('Ошибка входа', 'Неверное имя пользователя или пароль')
        except Exception as e:
            self.show_error_signal.emit('Ошибка', f'Произошла ошибка: {str(e)}')
        finally:
            self.enable_login_button_signal.emit(True)
            
    def handle_register(self):
        username = self.register_username.text()
        password = self.register_password.text()
        email = self.register_email.text()
        
        if not username or not password:
            self.show_error_signal.emit('Ошибка', 'Заполните обязательные поля')
            return
            
        # Отключаем кнопку во время выполнения операции
        self.register_btn.setEnabled(False)
        
        # Вызываем метод в отдельном потоке
        import threading
        thread = threading.Thread(target=self._perform_register, args=(username, password, email))
        thread.daemon = True
        thread.start()
            
    def _perform_register(self, username, password, email):
        try:
            if self.network_client.register(username, password, email):
                self.show_success_signal.emit('Успех', 'Регистрация выполнена успешно')
                self.switch_to_login_tab_signal.emit(username)
            else:
                self.show_error_signal.emit('Ошибка регистрации', 'Не удалось зарегистрироваться')
        except Exception as e:
            self.show_error_signal.emit('Ошибка', f'Произошла ошибка: {str(e)}')
        finally:
            self.enable_register_button_signal.emit(True)