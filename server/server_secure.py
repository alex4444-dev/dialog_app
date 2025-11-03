import socket
import threading
import json
import ssl
from datetime import datetime
import logging
import sqlite3
import hashlib
import secrets
import bcrypt
import os
import time
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.fernet import Fernet

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('p2p_server.log'),
        logging.StreamHandler()
    ]
)

class SecureDialogServer:
    def __init__(self, host='localhost', port=5555):
        self.host = host
        self.port = port
        self.clients = {}
        self.user_sessions = {}
        self.nat_mapping = {}
        self.active_calls = {}  # Словарь для отслеживания активных звонков
        self.server_socket = None
        self.setup_database()
        self.setup_server()

    def setup_database(self):
        """Инициализация базы данных для пользователей"""
        try:
            self.conn = sqlite3.connect('users.db', check_same_thread=False)
            self.cursor = self.conn.cursor()
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Таблица для хранения истории звонков
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS call_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    call_type TEXT NOT NULL,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT NOT NULL,
                    duration INTEGER DEFAULT 0
                )
            ''')
            
            self.conn.commit()
            logging.info("[+] База данных инициализирована")
        except Exception as e:
            logging.error(f"[-] Ошибка инициализации базы данных: {e}")
            raise

    def setup_server(self):
        """Настройка сервера"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            
            logging.info(f"[+] Сервер запущен на {self.host}:{self.port}")
            
        except Exception as e:
            logging.error(f"[-] Ошибка настройки сервера: {e}")
            raise

    def hash_password(self, password):
        """Хеширование пароля с использованием bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password, password_hash):
        """Проверка пароля"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    def create_session(self, user_id):
        """Создание сессии для пользователя"""
        self.cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now().timestamp() + 24 * 60 * 60
        
        self.cursor.execute(
            "INSERT INTO sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user_id, session_token, expires_at)
        )
        self.conn.commit()
        
        return session_token

    def validate_session(self, session_token):
        """Проверка валидности сессии"""
        try:
            self.cursor.execute(
                "SELECT user_id, expires_at FROM sessions WHERE session_token = ?",
                (session_token,)
            )
            result = self.cursor.fetchone()
            
            if not result:
                return None
                
            user_id, expires_at = result
            if datetime.now().timestamp() > expires_at:
                self.cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
                self.conn.commit()
                return None
                
            return user_id
        except:
            return None

    def get_user_id(self, username):
        """Получение ID пользователя"""
        try:
            self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            result = self.cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logging.error(f"Ошибка получения ID пользователя {username}: {e}")
            return None

    def get_online_users(self):
        """Получение списка онлайн-пользователей"""
        online_users = []
        for username, client_data in self.clients.items():
            p2p_port = client_data.get('p2p_port', 0)
            external_ip = client_data.get('external_ip', '')
            
            online_users.append({
                'username': username,
                'p2p_port': p2p_port,
                'external_ip': external_ip,
                'last_seen': client_data.get('last_seen', datetime.now().isoformat())
            })
        
        logging.debug(f"Сейчас онлайн: {len(online_users)} пользователей: {[user['username'] for user in online_users]}")
        return online_users

    def encrypt_with_rsa(self, public_key, data):
        """Шифрование данных с помощью RSA публичного ключа"""
        try:
            encrypted = public_key.encrypt(
                data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return encrypted
        except Exception as e:
            logging.error(f"Ошибка шифрования RSA: {e}")
            return None

    def send_message_to_client(self, username, message_data):
        """Отправка сообщения конкретному клиенту - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            if username not in self.clients:
                logging.error(f"Пользователь {username} не в сети")
                return False
            
            client_data = self.clients[username]
            cipher_suite = client_data['cipher']
            client_socket = client_data['socket']
            
            # ✅ ПРОВЕРЯЕМ, ЧТО СОКЕТ ВСЕ ЕЩЕ АКТИВЕН
            try:
                # Простая проверка - отправляем 0 байт
                client_socket.send(b'')
            except (socket.error, ConnectionResetError, BrokenPipeError):
                logging.warning(f"Сокет пользователя {username} разорван, удаляем из списка")
                if username in self.clients:
                    try:
                        self.clients[username]['socket'].close()
                    except:
                        pass
                    del self.clients[username]
                return False
            
            encrypted_message = cipher_suite.encrypt(json.dumps(message_data).encode())
            
            # Отправляем сообщение с маркером конца
            data_to_send = encrypted_message + b"<END>"
            
            try:
                client_socket.send(data_to_send)
                logging.info(f"✅ Сообщение отправлено пользователю {username}: {message_data.get('type', 'unknown')}")
                return True
            except (socket.error, ConnectionResetError, BrokenPipeError) as e:
                logging.error(f"❌ Ошибка отправки сообщения пользователю {username}: {e}")
                # Удаляем клиента при ошибке отправки
                if username in self.clients:
                    try:
                        self.clients[username]['socket'].close()
                    except:
                        pass
                    del self.clients[username]
                return False
                
        except Exception as e:
            logging.error(f"❌ Неожиданная ошибка при отправке сообщения пользователю {username}: {e}")
            return False

    def handle_register(self, request, client_ip):
        """Обработка регистрации"""
        try:
            username = request['username']
            password = request['password']
            email = request.get('email', '')
            
            logging.info(f"Попытка регистрации пользователя: {username}")
            
            # Проверяем, существует ли пользователь
            self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if self.cursor.fetchone():
                return {
                    'type': 'auth_response',
                    'status': 'error',
                    'message': 'Пользователь уже существует'
                }
            
            # Создаем нового пользователя
            password_hash = self.hash_password(password)
            self.cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                (username, password_hash, email)
            )
            self.conn.commit()
            
            logging.info(f"[+] Зарегистрирован новый пользователь: {username}")
            return {
                'type': 'auth_response',
                'status': 'success',
                'message': 'Регистрация успешна'
            }
            
        except Exception as e:
            logging.error(f"Ошибка регистрации пользователя: {e}")
            return {
                'type': 'auth_response',
                'status': 'error',
                'message': f'Ошибка регистрации: {e}'
            }

    def handle_login(self, request, client_ip, client_socket, cipher_suite, address):
        """Обработка входа"""
        try:
            username = request['username']
            password = request['password']
            
            logging.info(f"Попытка входа пользователя: {username}")
            
            # Ищем пользователя
            self.cursor.execute(
                "SELECT id, password_hash FROM users WHERE username = ?",
                (username,)
            )
            result = self.cursor.fetchone()
            
            if not result:
                return {
                    'type': 'auth_response',
                    'status': 'error',
                    'message': 'Неверное имя пользователя или пароль'
                }
            
            user_id, password_hash = result
            if self.verify_password(password, password_hash):
                # Создаем сессию
                session_token = self.create_session(user_id)
                if not session_token:
                    return {
                        'type': 'auth_response',
                        'status': 'error',
                        'message': 'Ошибка создания сессии'
                    }
                
                # Регистрируем клиента как онлайн
                p2p_port = request.get('p2p_port', 0)
                external_ip = request.get('external_ip', client_ip)
                
                self.clients[username] = {
                    'socket': client_socket,
                    'cipher': cipher_suite,
                    'address': address,
                    'last_seen': datetime.now().isoformat(),
                    'user_id': user_id,
                    'p2p_port': p2p_port,
                    'external_ip': external_ip
                }
                
                logging.info(f"[+] Пользователь {username} вошел в систему. Онлайн пользователей: {len(self.clients)}")
                return {
                    'type': 'auth_response',
                    'status': 'success',
                    'message': 'Вход выполнен',
                    'session_token': session_token
                }
            else:
                return {
                    'type': 'auth_response',
                    'status': 'error',
                    'message': 'Неверное имя пользователя или пароль'
                }
                
        except Exception as e:
            logging.error(f"Ошибка входа пользователя: {e}")
            return {
                'type': 'auth_response',
                'status': 'error',
                'message': f'Ошибка входа: {e}'
            }

    def handle_get_user_list(self, username):
        """Обработка запроса списка пользователей"""
        try:
            if not username:
                return {
                    'type': 'error',
                    'message': 'Не авторизован'
                }
            
            # Получаем список онлайн-пользователей
            online_users = self.get_online_users()
            logging.info(f"Запрос списка пользователей от {username}. Найдено: {len(online_users)}")
            
            # Фильтруем текущего пользователя из списка
            filtered_users = [user for user in online_users if user['username'] != username]
            
            return {
                'type': 'user_list_update',
                'users': filtered_users
            }
            
        except Exception as e:
            logging.error(f"Ошибка получения списка пользователей: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка получения списка пользователей: {e}'
            }

    def handle_client_info(self, request, username, user_id, client_ip):
        """Обработка информации о клиенте"""
        try:
            if not username or not user_id:
                return {
                    'type': 'error',
                    'message': 'Не авторизован'
                }
            
            # Обновляем P2P информацию о клиенте
            p2p_port = request.get('p2p_port', 0)
            external_ip = request.get('external_ip', client_ip)
            
            if username in self.clients:
                self.clients[username]['p2p_port'] = p2p_port
                self.clients[username]['external_ip'] = external_ip
                self.clients[username]['last_seen'] = datetime.now().isoformat()
            
            return {
                'type': 'client_info_ack',
                'status': 'success'
            }
            
        except Exception as e:
            logging.error(f"Ошибка обработки client_info: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки информации: {e}'
            }

    def handle_heartbeat(self, username, user_id):
        """Обработка heartbeat"""
        try:
            if username and user_id and username in self.clients:
                # Обновляем время последней активности
                self.clients[username]['last_seen'] = datetime.now().isoformat()
                return {'type': 'heartbeat_ack'}
            else:
                return {'type': 'error', 'message': 'Не авторизован'}
                
        except Exception as e:
            logging.error(f"Ошибка обработки heartbeat: {e}")
            return {'type': 'error', 'message': f'Ошибка heartbeat: {e}'}

    def handle_p2p_message(self, request, from_username):
        """Обработка P2P сообщения от одного клиента другому"""
        try:
            to_username = request.get('to')
            message = request.get('message')
            message_id = request.get('message_id')
            timestamp = request.get('timestamp')
            session_token = request.get('session_token')
            
            if not to_username or not message:
                return {
                    'type': 'error',
                    'message': 'Не указан получатель или сообщение'
                }
            
            # Проверяем сессию
            if not session_token or not self.validate_session(session_token):
                return {
                    'type': 'error',
                    'message': 'Невалидная сессия'
                }
            
            logging.info(f"P2P сообщение от {from_username} к {to_username}: {message}")
            
            # Проверяем, онлайн ли получатель
            if to_username not in self.clients:
                # Отправляем отправителю статус, что пользователь не в сети
                status_message = {
                    'type': 'message_status',
                    'status': 'user_offline',
                    'message_id': message_id,
                    'details': f'Пользователь {to_username} не в сети'
                }
                self.send_message_to_client(from_username, status_message)
                return {
                    'type': 'message_status',
                    'status': 'failed',
                    'message_id': message_id,
                    'details': f'Пользователь {to_username} не в сети'
                }
            
            # Формируем сообщение для получателя
            p2p_message = {
                'type': 'p2p_message',
                'from': from_username,
                'message': message,
                'timestamp': timestamp,
                'message_id': message_id
            }
            
            # Отправляем сообщение получателю
            if self.send_message_to_client(to_username, p2p_message):
                # Отправляем отправителю подтверждение доставки
                status_message = {
                    'type': 'message_status',
                    'status': 'delivered',
                    'message_id': message_id
                }
                self.send_message_to_client(from_username, status_message)
                
                logging.info(f"P2P сообщение от {from_username} к {to_username} доставлено")
                return {
                    'type': 'message_status',
                    'status': 'success',
                    'message_id': message_id
                }
            else:
                # Ошибка отправки
                status_message = {
                    'type': 'message_status',
                    'status': 'failed',
                    'message_id': message_id,
                    'details': 'Ошибка отправки сообщения получателю'
                }
                self.send_message_to_client(from_username, status_message)
                return status_message
                
        except Exception as e:
            logging.error(f"Ошибка обработки P2P сообщения: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки сообщения: {e}'
            }

    def handle_call_request(self, request, from_username):
        """Обработка запроса на звонок - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            to_username = request.get('to')
            call_type = request.get('call_type', 'audio')
            call_id = request.get('call_id', str(uuid.uuid4()))
            session_token = request.get('session_token')
            
            logging.info(f"🔊 Обработка запроса звонка: от {from_username} к {to_username}, ID: {call_id}")
            
            if not to_username:
                return {
                    'type': 'error',
                    'message': 'Не указан получатель звонка'
                }
            
            # ✅ ПРОВЕРКА: НЕЛЬЗЯ ЗВОНИТЬ САМОМУ СЕБЕ
            if from_username == to_username:
                return {
                    'type': 'call_response',
                    'status': 'error',
                    'call_id': call_id,
                    'message': 'Нельзя звонить самому себе'
                }
            
            # Проверяем сессию
            if not session_token or not self.validate_session(session_token):
                return {
                    'type': 'error',
                    'message': 'Невалидная сессия'
                }
            
            # Проверяем, онлайн ли получатель
            if to_username not in self.clients:
                logging.warning(f"❌ Пользователь {to_username} не в сети")
                return {
                    'type': 'call_response',
                    'status': 'user_offline',
                    'call_id': call_id,
                    'message': f'Пользователь {to_username} не в сети'
                }
            
            # Проверяем, не занят ли получатель другим звонком
            if to_username in [call['to'] for call in self.active_calls.values() if call['status'] == 'ringing']:
                logging.warning(f"❌ Пользователь {to_username} уже занят в другом звонке")
                return {
                    'type': 'call_response',
                    'status': 'user_busy',
                    'call_id': call_id,
                    'message': f'Пользователь {to_username} занят другим звонком'
                }
            
            # Сохраняем информацию о звонке
            self.active_calls[call_id] = {
                'from': from_username,
                'to': to_username,
                'call_type': call_type,
                'start_time': datetime.now(),
                'status': 'ringing'
            }
            
            # Записываем в историю звонков
            self.cursor.execute(
                "INSERT INTO call_history (call_id, from_user, to_user, call_type, status) VALUES (?, ?, ?, ?, ?)",
                (call_id, from_username, to_username, call_type, 'initiated')
            )
            self.conn.commit()
            
            # Отправляем запрос на звонок получателю
            call_request = {
                'type': 'call_request',
                'from': from_username,
                'call_type': call_type,
                'call_id': call_id,
                'timestamp': datetime.now().isoformat()
            }
            
            if self.send_message_to_client(to_username, call_request):
                logging.info(f"✅ Запрос на {call_type} звонок от {from_username} к {to_username} отправлен")
                return {
                    'type': 'call_response',
                    'status': 'ringing',
                    'call_id': call_id,
                    'message': 'Звонок отправлен'
                }
            else:
                # Удаляем информацию о звонке, если отправка не удалась
                if call_id in self.active_calls:
                    del self.active_calls[call_id]
                logging.error(f"❌ Ошибка отправки запроса на звонок {call_id}")
                return {
                    'type': 'call_response',
                    'status': 'failed',
                    'call_id': call_id,
                    'message': 'Ошибка отправки запроса на звонок'
                }
                
        except Exception as e:
            logging.error(f"❌ Ошибка обработки запроса на звонок: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки запроса на звонок: {e}'
            }

    def handle_call_answer(self, request, from_username):
        """Обработка ответа на звонок - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            call_id = request.get('call_id')
            answer = request.get('answer')
            session_token = request.get('session_token')
            call_port = request.get('call_port')

            logging.info(f"🔊 Обработка ответа на звонок {call_id} от {from_username}: {answer}, порт: {call_port}")

            if not call_id or not answer:
                return {
                    'type': 'error',
                    'message': 'Не указан ID звонка или ответ'
                }

            # Проверяем сессию
            if not session_token or not self.validate_session(session_token):
                return {
                    'type': 'error',
                    'message': 'Невалидная сессия'
                }
            
            # Проверяем, существует ли звонок
            if call_id not in self.active_calls:
                logging.info(f"Запрос ответа на несуществующий звонок {call_id} от {from_username}")
                return {
                    'type': 'call_answer_response',
                    'status': 'call_not_found',
                    'call_id': call_id,
                    'message': 'Звонок не найден или уже завершен'
                }
            
            call_data = self.active_calls[call_id]

            # Проверяем, что пользователь является получателем звонка
            if call_data['to'] != from_username:
                return {
                    'type': 'error',
                    'message': 'Вы не являетесь получателем этого звонка'
                }

            if answer == 'accept':
                # Обновляем статус звонка
                call_data['status'] = 'active'
                call_data['answer_time'] = datetime.now()

                # ✅ ВСЕГДА отправляем call_accepted, даже если call_port = 0 или None
                call_accepted = {
                    'type': 'call_accepted',
                    'call_id': call_id,
                    'from': from_username,
                    'call_port': call_port if call_port is not None else 0
                }
                
                logging.info(f"🔊 Отправка call_accepted для звонка {call_id}, порт: {call_port}")
                
                if self.send_message_to_client(call_data['from'], call_accepted):
                    logging.info(f"✅ Пользователь {from_username} принял звонок {call_id}")

                    # Обновляем историю звонков
                    self.cursor.execute(
                        "UPDATE call_history SET status = ? WHERE call_id = ?",
                        ('accepted', call_id)
                    )
                    self.conn.commit()
                
                    return {
                        'type': 'call_answer_response',
                        'status': 'accepted',
                        'call_id': call_id,
                        'message': 'Звонок принят'
                    }
                else:
                    logging.error(f"❌ Не удалось отправить call_accepted для звонка {call_id}")
                    return {
                        'type': 'call_answer_response',
                        'status': 'failed',
                        'call_id': call_id,
                        'message': 'Ошибка отправки подтверждения звонка'
                    }

            elif answer == 'reject':
                # Отправляем отказ инициатору
                call_rejected = {
                    'type': 'call_rejected',
                    'call_id': call_id,
                    'from': from_username
                }
                if self.send_message_to_client(call_data['from'], call_rejected):
                    logging.info(f"✅ Пользователь {from_username} отклонил звонок {call_id}")
                
                    # Обновляем историю звонков
                    self.cursor.execute(
                        "UPDATE call_history SET status = ?, end_time = CURRENT_TIMESTAMP WHERE call_id = ?",
                        ('rejected', call_id)
                    )
                    self.conn.commit()
                
                    # Удаляем из активных звонков
                    del self.active_calls[call_id]
                
                    return {
                        'type': 'call_answer_response',
                        'status': 'rejected',
                        'call_id': call_id,
                        'message': 'Звонок отклонен'
                    }
                else:
                    return {
                        'type': 'call_answer_response',
                        'status': 'failed',
                        'call_id': call_id,
                        'message': 'Ошибка отправки отказа на звонок'
                    }
            else:
                return {
                    'type': 'error',
                    'message': 'Неверный тип ответа на звонок. Допустимые значения: accept, reject'
                }
                
        except Exception as e:
            logging.error(f"❌ Ошибка обработки ответа на звонок: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки ответа на звонок: {e}'
            }

    def handle_call_end(self, request, from_username):
        """Обработка завершения звонка"""
        try:
            call_id = request.get('call_id')
            session_token = request.get('session_token')
            
            logging.info(f"🔊 Обработка завершения звонка {call_id} от {from_username}")
            
            if not call_id:
                return {
                    'type': 'error',
                    'message': 'Не указан ID звонка'
                }
            
            # Проверяем сессию
            if not session_token or not self.validate_session(session_token):
                return {
                    'type': 'error',
                    'message': 'Невалидная сессия'
                }
            
            # Проверяем, существует ли звонок
            if call_id not in self.active_calls:
                # Звонок уже завершен - это нормальная ситуация
                logging.info(f"Запрос на завершение несуществующего звонка {call_id} от {from_username}")
                return {
                    'type': 'call_end_response',
                    'status': 'already_ended',
                    'call_id': call_id,
                    'message': 'Звонок уже завершен'
                }
            
            call_data = self.active_calls[call_id]
            
            # Проверяем, что пользователь является участником звонка
            if from_username not in [call_data['from'], call_data['to']]:
                return {
                    'type': 'error',
                    'message': 'Вы не являетесь участником этого звонка'
                }
            
            # Определяем другого участника
            other_party = call_data['to'] if from_username == call_data['from'] else call_data['from']
            
            # Отправляем уведомление о завершении звонка другому участнику
            call_ended = {
                'type': 'call_ended',
                'call_id': call_id,
                'from': from_username
            }
            
            if other_party in self.clients:
                self.send_message_to_client(other_party, call_ended)
                logging.info(f"🔊 Уведомление о завершении звонка {call_id} отправлено пользователю {other_party}")
            
            # Рассчитываем длительность звонка
            end_time = datetime.now()
            start_time = call_data['start_time']
            duration = int((end_time - start_time).total_seconds())
            
            # Обновляем историю звонков
            self.cursor.execute(
                "UPDATE call_history SET status = ?, end_time = ?, duration = ? WHERE call_id = ?",
                ('ended', end_time, duration, call_id)
            )
            self.conn.commit()
            
            # Удаляем из активных звонков
            del self.active_calls[call_id]
            
            logging.info(f"✅ Звонок {call_id} завершен пользователем {from_username}. Длительность: {duration} сек.")
            
            return {
                'type': 'call_end_response',
                'status': 'ended',
                'call_id': call_id,
                'duration': duration,
                'message': 'Звонок завершен'
            }
                
        except Exception as e:
            logging.error(f"❌ Ошибка обработки завершения звонка: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки завершения звонка: {e}'
            }

    def handle_ice_candidate(self, request, from_username):
        """Обработка ICE-кандидатов для WebRTC"""
        try:
            call_id = request.get('call_id')
            candidate = request.get('candidate')
            target_user = request.get('target_user')
            session_token = request.get('session_token')
            
            if not call_id or not candidate or not target_user:
                return {
                    'type': 'error',
                    'message': 'Не указан ID звонка, кандидат или целевой пользователь'
                }
            
            # Проверяем сессию
            if not session_token or not self.validate_session(session_token):
                return {
                    'type': 'error',
                    'message': 'Невалидная сессия'
                }
            
            # Проверяем, существует ли звонок
            if call_id not in self.active_calls:
                return {
                    'type': 'error',
                    'message': 'Звонок не найден'
                }
            
            # Отправляем ICE-кандидат целевому пользователю
            ice_message = {
                'type': 'ice_candidate',
                'call_id': call_id,
                'candidate': candidate,
                'from_user': from_username
            }
            
            if self.send_message_to_client(target_user, ice_message):
                logging.debug(f"ICE-кандидат от {from_username} к {target_user} для звонка {call_id} отправлен")
                return {
                    'type': 'ice_candidate_response',
                    'status': 'sent',
                    'call_id': call_id
                }
            else:
                return {
                    'type': 'ice_candidate_response',
                    'status': 'failed',
                    'call_id': call_id,
                    'message': 'Ошибка отправки ICE-кандидата'
                }
                
        except Exception as e:
            logging.error(f"Ошибка обработки ICE-кандидата: {e}")
            return {
                'type': 'error',
                'message': f'Ошибка обработки ICE-кандидата: {e}'
            }

    def handle_server_status(self, request):
        """Диагностика состояния сервера"""
        try:
            status_info = {
                'type': 'server_status',
                'online_users': len(self.clients),
                'active_calls': len(self.active_calls),
                'users': list(self.clients.keys()),
                'calls': list(self.active_calls.keys())
            }
            return status_info
        except Exception as e:
            return {
                'type': 'error',
                'message': f'Ошибка получения статуса: {e}'
            }

    def cleanup_user_calls(self, username, reason="user_disconnected"):
        """Завершение всех активных звонков пользователя"""
        try:
            calls_to_end = []
            for call_id, call_data in self.active_calls.items():
                if username in [call_data['from'], call_data['to']]:
                    calls_to_end.append(call_id)
            
            logging.info(f"🔊 Завершение {len(calls_to_end)} звонков для пользователя {username}, причина: {reason}")
            
            for call_id in calls_to_end:
                try:
                    call_data = self.active_calls[call_id]
                    other_party = call_data['to'] if username == call_data['from'] else call_data['from']
                    
                    # Отправляем уведомление о завершении звонка другому участнику
                    if other_party in self.clients:
                        call_ended = {
                            'type': 'call_ended',
                            'call_id': call_id,
                            'from': username,
                            'reason': reason
                        }
                        self.send_message_to_client(other_party, call_ended)
                        logging.info(f"🔊 Уведомление о завершении звонка {call_id} отправлено пользователю {other_party}")
                    
                    # Обновляем историю звонков
                    end_time = datetime.now()
                    start_time = call_data['start_time']
                    duration = int((end_time - start_time).total_seconds())
                    
                    self.cursor.execute(
                        "UPDATE call_history SET status = ?, end_time = ?, duration = ? WHERE call_id = ?",
                        (f'ended_{reason}', end_time, duration, call_id)
                    )
                    self.conn.commit()
                    
                    # Удаляем из активных звонков
                    del self.active_calls[call_id]
                    
                    logging.info(f"🔊 Звонок {call_id} завершен из-за {reason}")
                except Exception as e:
                    logging.error(f"❌ Ошибка при завершении звонка {call_id}: {e}")
                    
        except Exception as e:
            logging.error(f"❌ Ошибка в cleanup_user_calls: {e}")

    def handle_client(self, client_socket, address):
        """Обработка подключения клиента"""
        username = None
        user_id = None
        client_ip, client_port = address
        cipher_suite = None
        
        try:
            logging.info(f"[+] Новое подключение от {address}")
            
            # Получаем публичный ключ клиента
            public_key_data = b""
            start_time = time.time()
            
            while time.time() - start_time < 30:
                try:
                    client_socket.settimeout(5)
                    chunk = client_socket.recv(4096)
                    if chunk:
                        public_key_data += chunk
                        if public_key_data.endswith(b"<END>"):
                            public_key_data = public_key_data[:-5]
                            break
                    elif not chunk:  # Клиент отключился
                        logging.info("Клиент отключился при отправке публичного ключа")
                        return
                except socket.timeout:
                    if time.time() - start_time >= 30:
                        logging.error("Таймаут получения публичного ключа")
                        return
                    continue
                except Exception as e:
                    logging.error(f"Ошибка получения публичного ключа: {e}")
                    return
            
            if not public_key_data:
                logging.error("Не получен публичный ключ от клиента")
                client_socket.close()
                return
            
            # Загружаем публичный ключ
            try:
                client_public_key = serialization.load_pem_public_key(public_key_data)
                logging.info("Публичный ключ клиента успешно загружен")
            except Exception as e:
                logging.error(f"Ошибка загрузки публичного ключа: {e}")
                client_socket.close()
                return
            
            # Генерируем AES ключ
            aes_key = Fernet.generate_key()
            cipher_suite = Fernet(aes_key)
            logging.info("AES ключ сгенерирован")
            
            # Шифруем AES ключ публичным ключом клиента
            encrypted_aes_key = self.encrypt_with_rsa(client_public_key, aes_key)
            
            if encrypted_aes_key is None:
                logging.error("Не удалось зашифровать AES ключ")
                client_socket.close()
                return
            
            # Отправляем зашифрованный AES ключ клиенту
            try:
                client_socket.send(encrypted_aes_key + b"<END>")
                logging.info("AES ключ успешно отправлен клиенту")
            except Exception as e:
                logging.error(f"Ошибка отправки AES ключа: {e}")
                client_socket.close()
                return
            
            # Основной цикл обработки запросов клиента
            while True:
                # Получаем запрос от клиента с большим таймаутом
                encrypted_request = b""
                start_time = time.time()
                received_data = False
                
                while time.time() - start_time < 300:
                    try:
                        client_socket.settimeout(10)
                        chunk = client_socket.recv(4096)
                        if chunk:
                            received_data = True
                            encrypted_request += chunk
                            if encrypted_request.endswith(b"<END>"):
                                encrypted_request = encrypted_request[:-5]
                                break
                        elif not chunk:  # Клиент отключился
                            logging.info("Клиент отключился")
                            return
                    except socket.timeout:
                        if received_data:
                            continue
                        else:
                            if time.time() - start_time >= 300:
                                continue
                            else:
                                continue
                    except Exception as e:
                        logging.error(f"Ошибка получения запроса: {e}")
                        break
                
                if not encrypted_request and not received_data:
                    continue
                
                if not encrypted_request:
                    logging.info("Пустой запрос, продолжаем ждать")
                    continue
                
                # Расшифровываем запрос
                try:
                    decrypted_request = cipher_suite.decrypt(encrypted_request)
                    request_str = decrypted_request.decode('utf-8')
                    request = json.loads(request_str)
                    logging.info(f"Получен запрос от {username or 'unknown'}: {request['type']}")
                except Exception as e:
                    logging.error(f"Ошибка расшифровки запроса: {e}")
                    error_response = {
                        'type': 'error',
                        'message': f'Ошибка обработки запроса: {e}'
                    }
                    try:
                        encrypted_error = cipher_suite.encrypt(json.dumps(error_response).encode())
                        client_socket.send(encrypted_error + b"<END>")
                    except:
                        pass
                    continue
                
                # Обрабатываем тип запроса
                try:
                    if request['type'] == 'register':
                        response = self.handle_register(request, client_ip)
                        
                    elif request['type'] == 'login':
                        response = self.handle_login(request, client_ip, client_socket, cipher_suite, address)
                        if response.get('status') == 'success':
                            username = request['username']
                            user_id = self.get_user_id(username)
                    
                    elif request['type'] == 'get_user_list':
                        response = self.handle_get_user_list(username)
                    
                    elif request['type'] == 'client_info':
                        response = self.handle_client_info(request, username, user_id, client_ip)
                    
                    elif request['type'] == 'heartbeat':
                        response = self.handle_heartbeat(username, user_id)
                    
                    elif request['type'] == 'p2p_message':
                        response = self.handle_p2p_message(request, username)
                    
                    elif request['type'] == 'call_request':
                        response = self.handle_call_request(request, username)
                    
                    elif request['type'] == 'call_answer':
                        response = self.handle_call_answer(request, username)
                    
                    elif request['type'] == 'call_end':
                        response = self.handle_call_end(request, username)
                    
                    elif request['type'] == 'ice_candidate':
                        response = self.handle_ice_candidate(request, username)
                    
                    elif request['type'] == 'server_status':
                        response = self.handle_server_status(request)
                    
                    else:
                        response = {
                            'type': 'error',
                            'message': f'Неизвестный тип запроса: {request["type"]}'
                        }
                    
                    # Отправляем ответ
                    try:
                        encrypted_response = cipher_suite.encrypt(json.dumps(response).encode())
                        client_socket.send(encrypted_response + b"<END>")
                        logging.info(f"Ответ на {request['type']} отправлен")
                    except Exception as e:
                        logging.error(f"Ошибка отправки ответа: {e}")
                        break
                        
                except Exception as e:
                    logging.error(f"Ошибка обработки запроса {request.get('type', 'unknown')}: {e}")
                    error_response = {
                        'type': 'error',
                        'message': f'Внутренняя ошибка сервера: {e}'
                    }
                    try:
                        encrypted_error = cipher_suite.encrypt(json.dumps(error_response).encode())
                        client_socket.send(encrypted_error + b"<END>")
                    except:
                        pass
                
        except Exception as e:
            logging.error(f"Ошибка обработки клиента {username or 'unknown'}: {e}")
        finally:
            # При отключении клиента завершаем все его активные звонки
            if username:
                logging.info(f"🔊 Обработка отключения пользователя {username}")
                self.cleanup_user_calls(username, "user_disconnected")
                
                if username in self.clients:
                    try:
                        self.clients[username]['socket'].close()
                    except:
                        pass
                    del self.clients[username]
                    logging.info(f"[-] Пользователь {username} отключился")
            try:
                client_socket.close()
            except:
                pass

    def start(self):
        """Запуск сервера"""
        logging.info("[+] Сервер ожидает подключений...")
        
        # Запускаем очистку неактивных клиентов в отдельном потоке
        cleanup_thread = threading.Thread(target=self.cleanup_inactive_clients, daemon=True)
        cleanup_thread.start()
        
        # Запускаем очистку зависших звонков в отдельном потоке
        call_cleanup_thread = threading.Thread(target=self.cleanup_stalled_calls, daemon=True)
        call_cleanup_thread.start()
        
        while True:
            try:
                client_socket, address = self.server_socket.accept()
                logging.info(f"Принято новое соединение от {address}")
                
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                thread.start()
                
            except Exception as e:
                logging.error(f"Ошибка при принятии соединения: {e}")

    def cleanup_inactive_clients(self):
        """Очистка неактивных клиентов - УЛУЧШЕННАЯ ВЕРСИЯ"""
        while True:
            time.sleep(30)  # Проверяем каждые 30 секунд
            try:
                current_time = datetime.now()
                inactive_users = []
                
                # Проверяем всех подключенных клиентов
                for username, client_data in self.clients.items():
                    last_seen_str = client_data.get('last_seen', '')
                    if last_seen_str:
                        try:
                            last_seen = datetime.fromisoformat(last_seen_str)
                            time_diff = (current_time - last_seen).total_seconds()
                            
                            # ✅ УВЕЛИЧИВАЕМ ТАЙМАУТ ДО 2 МИНУТ
                            if time_diff > 120:  # 2 минуты
                                inactive_users.append(username)
                        except ValueError:
                            inactive_users.append(username)
                    else:
                        # Если нет времени последней активности, помечаем как неактивного
                        inactive_users.append(username)
                
                # Удаляем неактивных клиентов
                for username in inactive_users:
                    if username in self.clients:
                        try:
                            # ✅ ЗАВЕРШАЕМ АКТИВНЫЕ ЗВОНКИ ПЕРЕД УДАЛЕНИЕМ
                            self.cleanup_user_calls(username, "user_timeout")
                            
                            self.clients[username]['socket'].close()
                        except:
                            pass
                        del self.clients[username]
                        logging.info(f"[-] Удален неактивный пользователь {username}")
                
            except Exception as e:
                logging.error(f"Ошибка при очистке неактивных клиентов: {e}")

    def cleanup_stalled_calls(self):
        """Очистка зависших звонков"""
        while True:
            time.sleep(60)
            try:
                current_time = datetime.now()
                stalled_calls = []
                
                # Проверяем все активные звонки
                for call_id, call_data in self.active_calls.items():
                    start_time = call_data['start_time']
                    time_diff = (current_time - start_time).total_seconds()
                    
                    # ✅ УВЕЛИЧИВАЕМ ТАЙМАУТ ДО 5 МИНУТ для активных звонков
                    if call_data['status'] == 'ringing' and time_diff > 120:  # 2 минуты для "звонящих"
                        stalled_calls.append(call_id)
                    elif call_data['status'] == 'active' and time_diff > 300:  # 5 минут для активных
                        stalled_calls.append(call_id)
                
                # Завершаем зависшие звонки
                for call_id in stalled_calls:
                    try:
                        call_data = self.active_calls[call_id]
                        
                        # Отправляем уведомления участникам
                        for username in [call_data['from'], call_data['to']]:
                            if username in self.clients:
                                call_ended = {
                                    'type': 'call_ended',
                                    'call_id': call_id,
                                    'from': 'system',
                                    'reason': 'timeout'
                                }
                                self.send_message_to_client(username, call_ended)
                        
                        # Обновляем историю звонков
                        self.cursor.execute(
                            "UPDATE call_history SET status = ?, end_time = CURRENT_TIMESTAMP WHERE call_id = ?",
                            ('timeout', call_id)
                        )
                        self.conn.commit()
                        
                        # Удаляем из активных звонков
                        del self.active_calls[call_id]
                        
                        logging.info(f"Зависший звонок {call_id} завершен системой")
                    except Exception as e:
                        logging.error(f"Ошибка при завершении зависшего звонка {call_id}: {e}")
                
            except Exception as e:
                logging.error(f"Ошибка при очистке зависших звонков: {e}")

if __name__ == "__main__":
    server = SecureDialogServer()
    server.start()