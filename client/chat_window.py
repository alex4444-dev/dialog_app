import time
import logging
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QLineEdit, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from styles.main_style import CHAT_WINDOW_STYLE

logger = logging.getLogger('dialog_gui')

class ChatWindow(QWidget):
    message_sent = pyqtSignal(str, str)  # username, message
    unread_count_changed = pyqtSignal(str, int)  # username, unread_count
    call_requested = pyqtSignal(str, str)  # username, call_type
    
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
        
        # Кнопки звонков в чате
        call_buttons_layout = QHBoxLayout()
        
        self.audio_call_btn = QPushButton("📞 Аудио звонок")
        self.audio_call_btn.setToolTip("Начать аудио звонок")
        self.audio_call_btn.clicked.connect(lambda: self.call_requested.emit(self.username, 'audio'))
        
        self.video_call_btn = QPushButton("📹 Видео звонок")
        self.video_call_btn.setToolTip("Начать видео звонок")
        self.video_call_btn.clicked.connect(lambda: self.call_requested.emit(self.username, 'video'))
        
        call_buttons_layout.addWidget(self.audio_call_btn)
        call_buttons_layout.addWidget(self.video_call_btn)
        
        layout.addLayout(call_buttons_layout)
        
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