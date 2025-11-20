import logging
import time
from typing import Optional, Dict

logger = logging.getLogger('dialog_auth')

class AuthManager:
    """Менеджер аутентификации для P2P мессенджера"""
    
    def __init__(self, db):
        self.db = db
        self.current_user = None
        self.session_token = None
    
    def register(self, username: str, password: str, email: str = None) -> Dict:
        """Регистрация нового пользователя"""
        try:
            # Валидация входных данных
            if not self._validate_username(username):
                return {'success': False, 'error': 'Неверное имя пользователя'}
            
            if not self._validate_password(password):
                return {'success': False, 'error': 'Неверный пароль'}
            
            # Создание пользователя
            if self.db.create_user(username, password, email):
                logger.info(f"Пользователь {username} зарегистрирован")
                return {'success': True, 'username': username}
            else:
                return {'success': False, 'error': 'Пользователь уже существует'}
                
        except Exception as e:
            logger.error(f"Ошибка регистрации: {e}")
            return {'success': False, 'error': str(e)}
    
    def login(self, username: str, password: str) -> Dict:
        """Аутентификация пользователя"""
        try:
            if self.db.verify_user(username, password):
                self.current_user = username
                self.session_token = self._generate_session_token()
                
                # Обновляем время последнего входа
                self._update_last_seen(username)
                
                logger.info(f"Пользователь {username} вошел в систему")
                return {'success': True, 'username': username, 'session_token': self.session_token}
            else:
                return {'success': False, 'error': 'Неверные учетные данные'}
                
        except Exception as e:
            logger.error(f"Ошибка входа: {e}")
            return {'success': False, 'error': str(e)}
    
    def logout(self, username: str) -> bool:
        """Выход пользователя"""
        try:
            if self.current_user == username:
                self.current_user = None
                self.session_token = None
                logger.info(f"Пользователь {username} вышел из системы")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка выхода: {e}")
            return False
    
    def validate_session(self, session_token: str) -> bool:
        """Проверка валидности сессии"""
        return self.session_token == session_token and self.current_user is not None
    
    def get_current_user(self) -> Optional[str]:
        """Получение текущего пользователя"""
        return self.current_user
    
    def _validate_username(self, username: str) -> bool:
        """Валидация имени пользователя"""
        if not username or len(username) < 3:
            return False
        # Дополнительные проверки можно добавить здесь
        return True
    
    def _validate_password(self, password: str) -> bool:
        """Валидация пароля"""
        if not password or len(password) < 6:
            return False
        return True
    
    def _generate_session_token(self) -> str:
        """Генерация токена сессии"""
        import secrets
        return secrets.token_hex(32)
    
    def _update_last_seen(self, username: str):
        """Обновление времени последней активности"""
        # Эта функция может быть реализована в Database классе
        pass