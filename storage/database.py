import sqlite3
import hashlib
import secrets
import time
from typing import List, Dict, Optional

class ClientDatabase:
    """Локальная база данных клиента Диалог"""
    
    def __init__(self, db_path: str = "data/dialog_client.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных"""
        conn = self._get_connection()
        try:
            # Таблица пользователей
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    public_key TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP
                )
            ''')
            
            # Таблица сессий
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (username) REFERENCES users (username)
                )
            ''')
            
            # Таблица сообщений
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    message TEXT NOT NULL,
                    message_id TEXT UNIQUE,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered BOOLEAN DEFAULT FALSE,
                    read BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (from_user) REFERENCES users (username),
                    FOREIGN KEY (to_user) REFERENCES users (username)
                )
            ''')
            
            # Таблица известных пиров
            conn.execute('''
                CREATE TABLE IF NOT EXISTS peers (
                    peer_id TEXT PRIMARY KEY,
                    address TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    last_seen TIMESTAMP,
                    is_connected BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Таблица черного списка
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blacklist (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    blocked_username TEXT UNIQUE NOT NULL,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица контактов (друзей)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS contacts (
                    contact_username TEXT PRIMARY KEY,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        finally:
            conn.close()
    
    def _get_connection(self):
        """Получение соединения с БД"""
        return sqlite3.connect(self.db_path)
    
    def create_user(self, username: str, password: str, email: str = None) -> bool:
        """Создание нового пользователя"""
        conn = self._get_connection()
        try:
            password_hash = self._hash_password(password)
            conn.execute(
                'INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)',
                (username, password_hash, email)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def verify_user(self, username: str, password: str) -> bool:
        """Проверка учетных данных пользователя"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                'SELECT password_hash FROM users WHERE username = ?',
                (username,)
            )
            result = cursor.fetchone()
            if result:
                stored_hash = result[0]
                return self._verify_password(password, stored_hash)
            return False
        finally:
            conn.close()
    
    def user_exists(self, username: str) -> bool:
        """Проверка существования пользователя"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                'SELECT 1 FROM users WHERE username = ?',
                (username,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def store_message(self, from_user: str, to_user: str, message: str, message_id: str = None):
        """Сохранение сообщения в БД"""
        conn = self._get_connection()
        try:
            if not message_id:
                message_id = f"{from_user}_{to_user}_{time.time()}"
            
            conn.execute(
                'INSERT INTO messages (from_user, to_user, message, message_id) VALUES (?, ?, ?, ?)',
                (from_user, to_user, message, message_id)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_user_messages(self, username: str, other_user: str, limit: int = 100) -> List[Dict]:
        """Получение истории сообщений с пользователем"""
        conn = self._get_connection()
        try:
            cursor = conn.execute('''
                SELECT from_user, to_user, message, timestamp 
                FROM messages 
                WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (username, other_user, other_user, username, limit))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'from_user': row[0],
                    'to_user': row[1],
                    'message': row[2],
                    'timestamp': row[3]
                })
            
            return messages[::-1]  # Возвращаем в хронологическом порядке
        finally:
            conn.close()
    
    def get_online_users(self) -> List[Dict]:
        """Получение списка онлайн пользователей (из локальной БД)"""
        # В P2P архитектуре этот метод может быть дополнен
        # информацией из сети
        conn = self._get_connection()
        try:
            cursor = conn.execute('''
                SELECT username, last_seen FROM users 
                WHERE last_seen > datetime('now', '-5 minutes')
                ORDER BY username
            ''')
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'username': row[0],
                    'last_seen': row[1]
                })
            
            return users
        finally:
            conn.close()
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Получение информации о пользователе"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                'SELECT username, email, registered_at, last_seen FROM users WHERE username = ?',
                (username,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    'username': result[0],
                    'email': result[1],
                    'registered_at': result[2],
                    'last_seen': result[3]
                }
            return None
        finally:
            conn.close()
    
    def store_offline_message(self, to_user: str, message: str, message_id: str):
        """Сохранение оффлайн сообщения"""
        self.store_message('system', to_user, f"Оффлайн: {message}", message_id)
    
    def _hash_password(self, password: str) -> str:
        """Хэширование пароля"""
        salt = secrets.token_hex(16)
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() + ':' + salt
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Проверка пароля"""
        try:
            hash_value, salt = stored_hash.split(':')
            computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
            return computed_hash == hash_value
        except:
            return False

    def store_system_message(self, to_user: str, message: str, message_id: str = None):
        """Сохранение системного сообщения в чат с пользователем"""
        if not message_id:
            message_id = f"system_{to_user}_{time.time()}"
        conn = self._get_connection()
        try:
            conn.execute(
                'INSERT INTO messages (from_user, to_user, message, message_id) VALUES (?, ?, ?, ?)',
                ('system', to_user, message, message_id)
            )
            conn.commit()
        finally:
            conn.close()

    def add_contact(self, username: str) -> bool:
        """Добавить пользователя в список контактов"""
        if not self.user_exists(username):
            return False
        conn = self._get_connection()
        try:
            conn.execute('INSERT OR IGNORE INTO contacts (contact_username) VALUES (?)', (username,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def remove_contact(self, username: str) -> bool:
        """Удалить пользователя из списка контактов"""
        conn = self._get_connection()
        try:
            conn.execute('DELETE FROM contacts WHERE contact_username = ?', (username,))
            conn.commit()
            return True
        finally:
            conn.close()

    def is_contact(self, username: str) -> bool:
        """Проверить, является ли пользователь контактом"""
        conn = self._get_connection()
        try:
            cursor = conn.execute('SELECT 1 FROM contacts WHERE contact_username = ?', (username,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def get_all_contacts(self) -> List[str]:
        """Получить список всех имён контактов"""
        conn = self._get_connection()
        try:
            cursor = conn.execute('SELECT contact_username FROM contacts ORDER BY added_at')
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def add_to_blacklist(self, username: str):
        conn = self._get_connection()
        try:
            conn.execute("INSERT OR IGNORE INTO blacklist (blocked_username) VALUES (?)", (username,))
            conn.commit()
        finally:
            conn.close()

    def remove_from_blacklist(self, username: str):
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM blacklist WHERE blocked_username = ?", (username,))
            conn.commit()
        finally:
            conn.close()

    def is_blocked(self, username: str) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT 1 FROM blacklist WHERE blocked_username = ?", (username,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def get_blacklist(self) -> list:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT blocked_username, blocked_at FROM blacklist ORDER BY blocked_at")
            return [{"username": row[0], "blocked_at": row[1]} for row in cursor.fetchall()]
        finally:
            conn.close()