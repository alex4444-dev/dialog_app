import sys
from PyQt5.QtWidgets import QApplication
from client.auth_window import LoginWindow
from client.gui_secure import SecureMainWindow
from client.network_secure import SecureNetworkClient

class SecureDialogApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.network_client = SecureNetworkClient()
        self.main_window = None
        
        # Показываем окно авторизации
        self.show_login()
        
    def show_login(self):
        """Показать окно авторизации"""
        self.login_window = LoginWindow()
        self.login_window.login_successful.connect(self.on_login_success)
        self.login_window.show()
    
    def on_login_success(self, username):
        """Обработка успешного входа"""
        self.login_window.close()
        
        # Инициализируем главное окно
        self.main_window = SecureMainWindow(self.network_client)
        self.main_window.setWindowTitle(f"Диалог - {username}")
        
        # Подключаемся к серверу
        if self.network_client.connect(username):
            print(f"Connected to server as {username}")
            self.main_window.show()
        else:
            print("Failed to connect to server")
            # Можно показать сообщение об ошибке и вернуться к логину
    
    def run(self):
        """Запуск приложения"""
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    dialog_app = SecureDialogApp()
    dialog_app.run()