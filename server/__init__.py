"""
Пакет серверной части мессенджера 'Диалог'
"""

__version__ = "1.0.0"

from .server_secure import SecureDialogServer

# Простой менеджер пользователей если основной недоступен
class SimpleUserManager:
    def __init__(self):
        self.users = {}
    
    def get_online_users(self):
        return []
    
    def search_users(self, term):
        return []
    
    def add_friend(self, user1, user2):
        return True

# Экспортируем классы
__all__ = ['SecureDialogServer', 'SimpleUserManager']