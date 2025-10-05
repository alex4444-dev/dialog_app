import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger('dialog_user_manager')

class UserManager:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Инициализация базы данных пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            public_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_online BOOLEAN DEFAULT FALSE
        )
        ''')
        
        # Таблица сессий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # Таблица контактов (друзья)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            contact_id INTEGER,
            alias TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (contact_id) REFERENCES users (id),
            UNIQUE(user_id, contact_id)
        )
        ''')
        
        # Таблица сообщений (для истории)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            content TEXT NOT NULL,
            encrypted BOOLEAN DEFAULT FALSE,
            message_type TEXT DEFAULT 'text',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered BOOLEAN DEFAULT FALSE,
            read BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (sender_id) REFERENCES users (id),
            FOREIGN KEY (receiver_id) REFERENCES users (id)
        )
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info(f"База данных инициализирована: {self.db_path}")
    
    def hash_password(self, password: str) -> str:
        """Хеширование пароля с солью"""
        salt = secrets.token_hex(16)
        return f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        if not password_hash or '$' not in password_hash:
            return False
            
        try:
            salt, stored_hash = password_hash.split('$', 1)
            computed_hash = hashlib.sha256((salt + password).encode()).hexdigest()
            return computed_hash == stored_hash
        except:
            return False
    
    def register_user(self, username: str, password: str, public_key: str = None) -> bool:
        """Регистрация нового пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                logger.warning(f"Пользователь {username} уже существует")
                return False
            
            # Хешируем пароль
            password_hash = self.hash_password(password)
            
            # Добавляем пользователя
            cursor.execute('''
            INSERT INTO users (username, password_hash, public_key, created_at)
            VALUES (?, ?, ?, ?)
            ''', (username, password_hash, public_key, datetime.now()))
            
            conn.commit()
            logger.info(f"Пользователь {username} успешно зарегистрирован")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка базы данных при регистрации пользователя {username}: {e}")
            return False
        finally:
            conn.close()
    
    def authenticate_user(self, username: str, password: str) -> bool:
        """Аутентификация пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT password_hash FROM users WHERE username = ?", 
                (username,)
            )
            result = cursor.fetchone()
            
            if result and self.verify_password(password, result[0]):
                # Обновляем время последнего входа
                cursor.execute(
                    "UPDATE users SET last_login = ?, is_online = TRUE WHERE username = ?",
                    (datetime.now(), username)
                )
                conn.commit()
                logger.info(f"Пользователь {username} успешно аутентифицирован")
                return True
                
            logger.warning(f"Неудачная аутентификация для пользователя {username}")
            return False
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка базы данных при аутентификации пользователя {username}: {e}")
            return False
        finally:
            conn.close()
    
    def update_user_online_status(self, username: str, is_online: bool) -> bool:
        """Обновление статуса онлайн/оффлайн"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET is_online = ? WHERE username = ?",
                (is_online, username)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                status = "онлайн" if is_online else "оффлайн"
                logger.info(f"Статус пользователя {username} изменен на {status}")
                return True
            return False
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления статуса пользователя {username}: {e}")
            return False
        finally:
            conn.close()
    
    def get_online_users(self, exclude_user: str = None) -> List[Dict]:
        """Получение списка онлайн пользователей"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if exclude_user:
                cursor.execute('''
                SELECT username, last_login FROM users 
                WHERE is_online = TRUE AND username != ?
                ORDER BY username
                ''', (exclude_user,))
            else:
                cursor.execute('''
                SELECT username, last_login FROM users 
                WHERE is_online = TRUE 
                ORDER BY username
                ''')
            
            online_users = []
            for row in cursor.fetchall():
                online_users.append({
                    'username': row[0],
                    'last_login': row[1],
                    'is_online': True
                })
            
            logger.debug(f"Найдено {len(online_users)} онлайн пользователей")
            return online_users
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения онлайн пользователей: {e}")
            return []
        finally:
            conn.close()

    
    
    def get_all_users(self) -> List[Dict]:
        """Получение списка всех пользователей"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT username, is_online, last_login FROM users 
            ORDER BY username
            ''')
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'username': row[0],
                    'is_online': bool(row[1]),
                    'last_login': row[2]
                })
            
            return users
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            return []
        finally:
            conn.close()
    
    def update_public_key(self, username: str, public_key: str) -> bool:
        """Обновление публичного ключа пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET public_key = ? WHERE username = ?",
                (public_key, username)
            )
            conn.commit()
            
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Публичный ключ пользователя {username} обновлен")
            return success
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления публичного ключа пользователя {username}: {e}")
            return False
        finally:
            conn.close()
    
    def get_public_key(self, username: str) -> Optional[str]:
        """Получение публичного ключа пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT public_key FROM users WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения публичного ключа пользователя {username}: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_id(self, username: str) -> Optional[int]:
        """Получение ID пользователя по имени"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения ID пользователя {username}: {e}")
            return None
        finally:
            conn.close()
    
    def add_contact(self, username: str, contact_username: str, alias: str = None) -> bool:
        """Добавление контакта пользователю"""
        try:
            user_id = self.get_user_id(username)
            contact_id = self.get_user_id(contact_username)
            
            if not user_id or not contact_id or user_id == contact_id:
                logger.warning(f"Невалидные ID для добавления контакта: {username} -> {contact_username}")
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR IGNORE INTO contacts (user_id, contact_id, alias)
            VALUES (?, ?, ?)
            ''', (user_id, contact_id, alias))
            
            conn.commit()
            
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Пользователь {contact_username} добавлен в контакты пользователя {username}")
            return success
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления контакта {contact_username} пользователю {username}: {e}")
            return False
        finally:
            conn.close()
    
    def get_contacts(self, username: str) -> List[Dict]:
        """Получение списка контактов пользователя"""
        try:
            user_id = self.get_user_id(username)
            if not user_id:
                return []
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT u.username, c.alias, u.is_online
            FROM contacts c
            JOIN users u ON c.contact_id = u.id
            WHERE c.user_id = ?
            ORDER BY u.is_online DESC, u.username
            ''', (user_id,))
            
            contacts = []
            for row in cursor.fetchall():
                contacts.append({
                    'username': row[0],
                    'alias': row[1] or row[0],
                    'is_online': bool(row[2])
                })
            
            return contacts
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения контактов пользователя {username}: {e}")
            return []
        finally:
            conn.close()
    
    def search_users(self, search_term: str, exclude_user: str = None) -> List[Dict]:
        """Поиск пользователей по имени"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if exclude_user:
                cursor.execute('''
                SELECT username, is_online, last_login FROM users 
                WHERE username LIKE ? AND username != ?
                ORDER BY username
                ''', (f'%{search_term}%', exclude_user))
            else:
                cursor.execute('''
                SELECT username, is_online, last_login FROM users 
                WHERE username LIKE ? 
                ORDER BY username
                ''', (f'%{search_term}%',))
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'username': row[0],
                    'is_online': bool(row[1]),
                    'last_login': row[2]
                })
            
            logger.debug(f"Поиск '{search_term}': найдено {len(users)} пользователей")
            return users
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка поиска пользователей по запросу '{search_term}': {e}")
            return []
        finally:
            conn.close()
    
    def save_message(self, sender: str, receiver: str, content: str, 
                    encrypted: bool = False, message_type: str = "text") -> bool:
        """Сохранение сообщения в историю"""
        try:
            sender_id = self.get_user_id(sender)
            receiver_id = self.get_user_id(receiver)
            
            if not sender_id or not receiver_id:
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO messages (sender_id, receiver_id, content, encrypted, message_type)
            VALUES (?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, content, encrypted, message_type))
            
            conn.commit()
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка сохранения сообщения от {sender} к {receiver}: {e}")
            return False
        finally:
            conn.close()
    
    def get_message_history(self, user1: str, user2: str, limit: int = 100) -> List[Dict]:
        """Получение истории сообщений между двумя пользователями"""
        try:
            user1_id = self.get_user_id(user1)
            user2_id = self.get_user_id(user2)
            
            if not user1_id or not user2_id:
                return []
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT 
                u1.username as sender,
                u2.username as receiver,
                m.content,
                m.encrypted,
                m.message_type,
                m.timestamp,
                m.delivered,
                m.read
            FROM messages m
            JOIN users u1 ON m.sender_id = u1.id
            JOIN users u2 ON m.receiver_id = u2.id
            WHERE (m.sender_id = ? AND m.receiver_id = ?)
               OR (m.sender_id = ? AND m.receiver_id = ?)
            ORDER BY m.timestamp DESC
            LIMIT ?
            ''', (user1_id, user2_id, user2_id, user1_id, limit))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'sender': row[0],
                    'receiver': row[1],
                    'content': row[2],
                    'encrypted': bool(row[3]),
                    'type': row[4],
                    'timestamp': row[5],
                    'delivered': bool(row[6]),
                    'read': bool(row[7])
                })
            
            return messages[::-1]  # Возвращаем в хронологическом порядке
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения истории сообщений между {user1} и {user2}: {e}")
            return []
        finally:
            conn.close()
    
    def user_exists(self, username: str) -> bool:
        """Проверка существования пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            )
            return cursor.fetchone() is not None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка проверки существования пользователя {username}: {e}")
            return False
        finally:
            conn.close()
    
    def cleanup_old_sessions(self, days: int = 30):
        """Очистка старых сессий"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            cursor.execute(
                "DELETE FROM sessions WHERE created_at < ?",
                (cutoff_date,)
            )
            
            conn.commit()
            deleted_count = cursor.rowcount
            logger.info(f"Очищено {deleted_count} старых сессий")
            return deleted_count
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка очистки старых сессий: {e}")
            return 0
        finally:
            conn.close()

# Создание синглтона для менеджера пользователей
user_manager = UserManager()

if __name__ == "__main__":
    # Тестирование функциональности
    logging.basicConfig(level=logging.INFO)
    
    manager = UserManager("test_users.db")
    
    # Очищаем старую базу если есть
    if os.path.exists("test_users.db"):
        os.remove("test_users.db")
    
    # Регистрация тестовых пользователей
    manager.register_user("alice", "password123", "alice_public_key")
    manager.register_user("bob", "password456", "bob_public_key")
    manager.register_user("charlie", "password789", "charlie_public_key")
    
    print("Тестовые пользователи созданы:")
    print("Alice: password123")
    print("Bob: password456") 
    print("Charlie: password789")
    
    # Тест аутентификации
    print("\nТест аутентификации:")
    print("Alice auth:", manager.authenticate_user("alice", "password123"))
    print("Bob auth:", manager.authenticate_user("bob", "password456"))
    print("Invalid auth:", manager.authenticate_user("alice", "wrongpass"))
    
    # Тест добавления в друзья
    print("\nТест добавления в друзья:")
    manager.add_contact("alice", "bob", "Bob Friend")
    manager.add_contact("alice", "charlie", "Charlie")
    
    contacts = manager.get_contacts("alice")
    print("Контакты Alice:", contacts)
    
    # Тест поиска
    print("\nТест поиска:")
    search_results = manager.search_users("a")
    print("Поиск 'a':", [user['username'] for user in search_results])
    
    print("\nТестирование завершено успешно!")