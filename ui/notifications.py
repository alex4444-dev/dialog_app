import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                             QSystemTrayIcon, QMenu, QAction, QStyle, QDesktopWidget)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QIcon, QPixmap, QPainter

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