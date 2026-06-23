"""
Стили для главного окна мессенджера
"""

MAIN_WINDOW_STYLE = """
    QMainWindow {
        background-color: #f8f9fa;
        font-family: 'Sans', 'Segoe UI', Arial, sans-serif;
    }
    QTabWidget::pane {
        border: 1px solid #dee2e6;
        background-color: white;
        border-radius: 8px;
        margin-top: 5px;
    }
    QTabWidget::tab-bar {
        alignment: left;
    }
    QTabBar::tab {
        background-color: #e9ecef;
        border: 1px solid #dee2e6;
        border-bottom: none;
        padding: 5px 20px;
        margin-right: 3px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-size: 18px;
        color: #495057;
        min-width: 120px;
    }
    QTabBar::tab:selected {
        background-color: white;
        color: #007bff;
        font-weight: bold;
        border-bottom: 2px solid #007bff;
    }
    QTabBar::tab:!selected {
        background-color: #f8f9fa;
        color: #6c757d;
    }
    QTabBar::tab:hover {
        background-color: #e3f2fd;
        color: #0056b3;
    }
    QTextEdit {
        border: 1px solid #ced4da;
        border-radius: 6px;
        padding: 10px;
        font-size: 16px;
        background-color: white;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    QLabel {
        font-size: 16px;
    }
    QCheckBox {
        font-size: 16px;
    }
    QGroupBox {
        font-size: 16px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 5px;
        padding: 0 5px;
    }
    QListWidget {
        border: 1px solid #ced4da;
        border-radius: 6px;
        background-color: white;
        font-size: 16px;
        font-family: 'Segoe UI', Arial, sans-serif;
        outline: none;
    }
    QListWidget::item {
        padding: 12px 8px;
        border-bottom: 1px solid #f1f3f4;
        color: #202124;
    }
    QListWidget::item:hover {
        background-color: #f8f9fa;
    }
    QListWidget::item:selected {
        background-color: #007bff;
        color: white;
        border-radius: 4px;
    }
    QPushButton {
        background-color: #f8f9fa;
        color: black;
        border: 1px outset #898b8c;
        border-radius: 6px;
        padding: 8px 18px;
        font-size: 16px;
        font-weight: 300;
        font-family: 'System-UI', 'Segoe UI', Arial, sans-serif;
    }
    QPushButton:hover {
        background-color: #c3c3c3;
    }
    QPushButton:pressed {
        background-color: #4f6070;
        border: none;
    }
    QPushButton:disabled {
        background-color: #f8f9fa;
        color: #525354;
    }
    QLineEdit {
        border: 2px solid #e9ecef;
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 16px;
        background-color: white;
        font-family: 'System UI', 'Segoe UI', Arial, sans-serif;
        selection-background-color: #007bff;
    }
    QLineEdit:focus {
        border: 2px solid #007bff;
        background-color: #fafafa;
    }
    QSpinBox {
        font-size: 16px;
    }
    QComboBox {
        font-size: 16px;
    }
    QTableWidget {
        font-size: 16px;
    }
    QMenuBar {
        background-color: white;
        border-bottom: 1px solid #dee2e6;
        font-family: 'Arial', sans-serif;
    }
    QMenuBar::item {
        padding: 8px 16px;
        background-color: transparent;
        color: #495057;
        border-radius: 4px;
    }
    QMenuBar::item:selected {
        background-color: #007bff;
        color: white;
    }
    QMenu {
        background-color: white;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 8px 0;
        font-family: 'Arial', sans-serif;
    }
    QMenu::item {
        padding: 8px 32px 8px 20px;
        color: #495057;
    }
    QMenu::item:selected {
        background-color: #007bff;
        color: white;
    }
    QMenu::separator {
        height: 1px;
        background-color: #dee2e6;
        margin: 4px 8px;
    }
    QStatusBar {
        background-color: #e9ecef;
        color: #495057;
        border-top: 1px solid #dee2e6;
        font-size: 14px;
        font-family:  'Arial', sans-serif;
        padding: 4px;
    }
    QLabel {
        font-family:  'Arial', sans-serif;
        color: #212529;
    }
"""

CHAT_WINDOW_STYLE = """
    QTextEdit#chat_history {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: white;
        font-size: 18px;
        font-family:  'Arial', sans-serif;
        line-height: 1.4;
        padding: 12px;
    }
    QLineEdit#message_input {
        border: 2px solid #e0e0e0;
        border-radius: 20px;
        padding: 14px 20px;
        font-size: 18px;
        background-color: white;
        font-family: 'System UI', Arial, sans-serif;
    }
    QLineEdit#message_input:focus {
        border: 2px solid #007bff;
        background-color: #fafafa;
    }
    QPushButton#send_btn {
        background-color: #f8f9fa;
        color: black;
        border: 1px outset #898b8c;
        border-radius: 6px;
        padding: 8px 18px;
        font-size: 16px;
        font-weight: 500;
        font-family: 'System-UI', 'Segoe UI', Arial, sans-serif;
        min-width: 100px;
    }
    QPushButton#send_btn:hover {
        background-color: #c3c3c3;
    }
    QPushButton#send_btn:pressed {
        background-color: #46f6070;
        border: none;
    }
    QPushButton#send_btn:disabled {
        background-color: #f8f9fa;
        color: #525354;
    }
"""

USERS_PANEL_STYLE = """
    QListWidget {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: white;
        font-size: 18px;
        font-family: 'System UI', Arial, sans-serif;
        outline: none;
    }
    QListWidget::item {
        padding: 12px 16px;
        border-bottom: 1px solid #f5f5f5;
        color: #333;
    }
    QListWidget::item:hover {
        background-color: #f8f9fa;
    }
    QListWidget::item:selected {
        background-color: #007bff;
        color: white;
        border-radius: 6px;
    }
    QPushButton {
        background-color: #f8f9fa;
        color: black;
        border: 1px outset #898b8c;
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 18px;
        font-family: Arial, sans-serif;
    }
    QPushButton:hover {
        background-color: #c3c3c3;
    }
    QPushButton:pressed {
        background-color: #46f6070;
        border: none;
    }
"""