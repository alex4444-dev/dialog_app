from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from styles.main_style import USERS_PANEL_STYLE

class UsersPanel(QWidget):
    user_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    call_requested = pyqtSignal(str, str)  # username, call_type
    
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
        
        # Кнопка обновления
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Обновить")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        button_layout.addWidget(self.refresh_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setStyleSheet(USERS_PANEL_STYLE)
        
    def on_user_double_clicked(self, item):
        self.user_selected.emit(item.text())
        
    def start_audio_call(self):
        """Начать аудио звонок"""
        current_item = self.users_list.currentItem()
        if current_item:
            username = current_item.text().replace("👤 ", "")
            self.call_requested.emit(username, 'audio')
        
    def start_video_call(self):
        """Начать видео звонок"""
        current_item = self.users_list.currentItem()
        if current_item:
            username = current_item.text().replace("👤 ", "")
            self.call_requested.emit(username, 'video')
        
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