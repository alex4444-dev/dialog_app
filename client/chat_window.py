from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                             QLineEdit, QPushButton, QLabel)
from PyQt5.QtCore import pyqtSignal

class ChatWindow(QWidget):
    message_sent = pyqtSignal(str, str)  # Сигнал отправки сообщения (username, message)
    
    def __init__(self, username, parent=None):
        super().__init__(parent)
        self.username = username
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Заголовок с именем пользователя
        title = QLabel(f'Чат с {self.username}')
        title.setStyleSheet('font-weight: bold; font-size: 14px;')
        layout.addWidget(title)
        
        # История сообщений
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)
        
        # Панель ввода сообщения
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton('Отправить')
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        
    def send_message(self):
        message = self.message_input.text().strip()
        if message:
            self.message_sent.emit(self.username, message)
            self.chat_history.append(f'Вы: {message}')
            self.message_input.clear()
            
    def add_message(self, sender, message):
        prefix = 'Вы' if sender == 'self' else sender
        self.chat_history.append(f'{prefix}: {message}')