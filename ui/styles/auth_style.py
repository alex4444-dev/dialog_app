"""
Стили для окон аутентификации и регистрации
"""

AUTH_DIALOG_STYLE = """
    QDialog {
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #667eea, stop: 1 #764ba2);
        color: white;
    }
    QLabel {
        color: white;
        font-size: 18px;
    }
    QLabel#title {
        font-size: 28px;
        font-weight: bold;
        color: white;
        padding: 10px;
    }
    QLabel#subtitle {
        font-size: 16px;
        color: rgba(255, 255, 255, 0.8);
    }
    QLabel#status {
        background-color: rgba(255, 255, 255, 0.1);
        border-radius: 5px;
        padding: 8px;
        margin: 5px;
    }
    QLineEdit {
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-radius: 8px;
        padding: 12px;
        font-size: 14px;
        color: #333;
        margin: 5px;
    }
    QLineEdit:focus {
        border: 2px solid #4CAF50;
        background-color: white;
    }
    QPushButton {
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #4CAF50, stop: 1 #45a049);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 12px;
        font-size: 14px;
        font-weight: bold;
        margin: 5px;
    }
    QPushButton:hover {
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #45a049, stop: 1 #4CAF50);
    }
    QPushButton:pressed {
        background: #3e8e41;
    }
    QPushButton#cancel {
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #f44336, stop: 1 #d32f2f);
    }
    QPushButton#cancel:hover {
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #d32f2f, stop: 1 #f44336);
    }
    QLabel#link {
        color: #e3f2fd;
        font-size: 13px;
        text-decoration: underline;
    }
    QLabel#link:hover {
        color: #bbdefb;
    }
"""

# Дополнительные стили для окон
REGISTER_STYLE_EXTRA = """
    QLabel#title {
        font-size: 24px;
    }
"""

LOGIN_STYLE_EXTRA = """
    QLabel#title {
        font-size: 28px;
    }
"""