from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QLabel, QPushButton, QLineEdit)
from PyQt5.QtCore import pyqtSignal

class UsersPanel(QWidget):
    user_selected = pyqtSignal(str)  # Сигнал о выборе пользователя для чата
    refresh_requested = pyqtSignal()  # Сигнал запроса обновления списка
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Заголовок
        title = QLabel('Пользователи онлайн')
        title.setStyleSheet('font-weight: bold; font-size: 14px;')
        layout.addWidget(title)
        
        # Список пользователей
        self.users_list = QListWidget()
        self.users_list.itemDoubleClicked.connect(self.on_user_double_clicked)
        layout.addWidget(self.users_list)
        
        # Панель управления
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton('Обновить')
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        self.p2p_btn = QPushButton('Запустить P2P')
        self.p2p_btn.clicked.connect(self.start_p2p_listener)
        
        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.p2p_btn)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # Статус P2P
        self.p2p_status = QLabel('P2P: Неактивен')
        layout.addWidget(self.p2p_status)
        
    def on_user_double_clicked(self, item):
        self.user_selected.emit(item.text())
        
    def update_users(self, users):
        self.users_list.clear()
        for user in users:
            self.users_list.addItem(user['username'])
            
    def set_p2p_status(self, status, active):
        self.p2p_status.setText(f'P2P: {status}')
        color = 'green' if active else 'red'
        self.p2p_status.setStyleSheet(f'color: {color};')
        
    def start_p2p_listener(self):
        # Этот метод будет реализован в основном GUI
        pass