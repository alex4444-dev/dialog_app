import socket
import json
import threading
import logging
import time
import hashlib
import queue
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

class SecureNetworkClient:
    def __init__(self, host='localhost', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.connected = False
        self.session_token = None
        self.username = None
        self.p2p_sockets = {}
        
        # Генерируем RSA ключи для клиента
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        self.public_key = self.private_key.public_key()
        
        self.aes_key = None
        self.cipher_suite = None
        
        # Очередь для входящих сообщений
        self.message_queue = queue.Queue()
        self.message_handler = None
        self.status_handler = None
        
        # Флаги управления потоками
        self.stop_listener = False
        self.listener_thread = None
        self.socket_lock = threading.Lock()
        
        # Для синхронных запросов
        self.pending_response = None
        self.response_event = threading.Event()
        self.expected_response_type = None
        
        # Настройка логирования
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('dialog_network')

    def set_message_handler(self, handler):
        """Установка обработчика входящих сообщений"""
        self.logger.info(f"Установлен обработчик сообщений: {handler}")
        self.message_handler = handler

    def set_status_handler(self, handler):
        """Установка обработчика статусов сообщений"""
        self.logger.info(f"Установлен обработчик статусов: {handler}")
        self.status_handler = handler

    def connect(self, host=None, port=None):
        """Подключение к серверу"""
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        
        return self.connect_to_server()

    def connect_to_server(self):
        """Установка безопасного соединения с сервером"""
        try:
            # Закрываем предыдущее соединение
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
            
            # Создаем новый сокет
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(15)
            
            # Подключаемся к серверу
            self.logger.info(f"Попытка подключения к {self.host}:{self.port}")
            self.server_socket.connect((self.host, self.port))
            self.logger.info("TCP соединение установлено")
            
            # Отправляем публичный ключ серверу
            public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            self.logger.debug(f"Отправка публичного ключа ({len(public_key_pem)} байт)")
            self.server_socket.send(public_key_pem + b"<END>")
            self.logger.info("Публичный ключ отправлен")
            
            # Получаем зашифрованный AES ключ от сервера
            encrypted_data = b""
            start_time = time.time()
            
            while time.time() - start_time < 15:
                try:
                    self.server_socket.settimeout(2)
                    chunk = self.server_socket.recv(4096)
                    if chunk:
                        encrypted_data += chunk
                        if encrypted_data.endswith(b"<END>"):
                            encrypted_data = encrypted_data[:-5]
                            break
                    else:
                        self.logger.error("Соединение разорвано сервером")
                        return False
                except socket.timeout:
                    if time.time() - start_time >= 15:
                        self.logger.error("Таймаут получения AES ключа")
                        return False
                    continue
                except Exception as e:
                    self.logger.error(f"Ошибка получения AES ключа: {e}")
                    return False
            
            if not encrypted_data:
                self.logger.error("Не получен AES ключ от сервера")
                return False
            
            self.logger.debug(f"Получен зашифрованный AES ключ ({len(encrypted_data)} байт)")
            
            # Дешифруем AES ключ нашим приватным ключом
            try:
                self.aes_key = self.private_key.decrypt(
                    encrypted_data,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                self.logger.info("AES ключ успешно дешифрован")
                
                # Создаем cipher suite для шифрования сообщений
                self.cipher_suite = Fernet(self.aes_key)
                
                self.connected = True
                self.logger.info("Успешно подключено к серверу")
                
                # Запускаем прослушиватель сообщений
                self.start_message_listener()
                
                return True
                
            except Exception as e:
                self.logger.error(f"Ошибка дешифрования AES ключа: {e}")
                return False
            
        except Exception as e:
            self.logger.error(f"Ошибка подключения к серверу: {e}")
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
                self.server_socket = None
            return False

    def start_message_listener(self):
        """Запуск прослушивания сообщений от сервера"""
        if self.listener_thread and self.listener_thread.is_alive():
            return
            
        self.stop_listener = False
        
        def listener():
            self.logger.info("Запуск прослушивателя сообщений")
            buffer = b""
            
            while self.connected and not self.stop_listener:
                try:
                    # Устанавливаем небольшой таймаут для возможности прерывания
                    self.server_socket.settimeout(0.5)
                    
                    try:
                        chunk = self.server_socket.recv(4096)
                        if chunk:
                            buffer += chunk
                            self.logger.debug(f"Получено {len(chunk)} байт, буфер: {len(buffer)} байт")
                        else:
                            # Пустой chunk - соединение закрыто
                            self.logger.error("Соединение закрыто сервером")
                            self.connected = False
                            break
                    except socket.timeout:
                        # Таймаут - это нормально, продолжаем
                        pass
                    except Exception as e:
                        if self.connected and not self.stop_listener:
                            self.logger.error(f"Ошибка чтения из сокета: {e}")
                        break
                    
                    # Обрабатываем полные сообщения из буфера
                    while b"<END>" in buffer:
                        message_end = buffer.find(b"<END>")
                        message_data = buffer[:message_end]
                        buffer = buffer[message_end + 5:]  # +5 для длины "<END>"
                        
                        if message_data:
                            self.logger.debug(f"Обработка сообщения длиной {len(message_data)} байт")
                            self.process_received_message(message_data)
                            
                except Exception as e:
                    if self.connected and not self.stop_listener:
                        self.logger.error(f"Ошибка в прослушивателе сообщений: {e}")
                    break
                    
            self.logger.info("Прослушиватель сообщений остановлен")
        
        self.listener_thread = threading.Thread(target=listener, daemon=True)
        self.listener_thread.start()

    def process_received_message(self, encrypted_data):
        """Обработка полученного зашифрованного сообщения"""
        try:
            self.logger.debug(f"Дешифровка сообщения длиной {len(encrypted_data)} байт")
            decrypted_data = self.cipher_suite.decrypt(encrypted_data)
            self.logger.debug(f"Расшифрованные данные: {decrypted_data[:100]}...")
            
            message = json.loads(decrypted_data.decode('utf-8'))
            
            message_type = message.get('type')
            self.logger.info(f"=== ПОЛУЧЕНО СООБЩЕНИЕ ТИПА: {message_type} ===")
            self.logger.debug(f"Полное сообщение: {message}")
            
            # Если мы ожидаем ответ определенного типа
            if (self.expected_response_type and 
                message_type == self.expected_response_type and 
                self.response_event and 
                not self.response_event.is_set()):
                self.logger.debug(f"Это ожидаемый ответ типа {self.expected_response_type}")
                self.pending_response = message
                self.response_event.set()
                return
            
            # Обработка асинхронных сообщений
            if message_type == 'p2p_message':
                from_user = message.get('from')
                text = message.get('message')
                if from_user and text:
                    self.logger.info(f"!!! ВХОДЯЩЕЕ P2P СООБЩЕНИЕ от {from_user}: {text}")
                    if self.message_handler:
                        self.logger.info(f"Вызов обработчика сообщений для {from_user}")
                        self.message_handler(from_user, text)
                    else:
                        self.logger.error("Нет установленного обработчика сообщений!")
                else:
                    self.logger.error(f"Некорректное P2P сообщение: from={from_user}, text={text}")
                    
            elif message_type == 'message_status':
                status = message.get('status')
                details = message.get('details', '')
                message_id = message.get('message_id', '')
                
                self.logger.info(f"Получен статус сообщения: {status} - {details}")
                
                if self.status_handler:
                    if status == 'delivered':
                        self.status_handler('delivered', f"ID: {message_id}")
                    elif status == 'failed':
                        self.status_handler('failed', f"ID: {message_id} - {details}")
                    elif status == 'user_offline':
                        self.status_handler('user_offline', details)
                else:
                    self.logger.error("Нет установленного обработчика статусов!")
                    
            elif message_type == 'auth_response':
                self.logger.info(f"Получен ответ на аутентификацию: {message.get('status')}")
            elif message_type == 'user_list_update':
                self.logger.info(f"Получено обновление списка пользователей")
            elif message_type == 'system_message':
                system_msg = message.get('message', '')
                if system_msg and self.message_handler:
                    self.message_handler('system', system_msg)
            elif message_type == 'heartbeat_ack':
                self.logger.debug("Получено подтверждение heartbeat")
            elif message_type == 'error':
                error_msg = message.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка от сервера: {error_msg}")
                if self.status_handler:
                    self.status_handler('error', error_msg)
            else:
                self.logger.warning(f"Неизвестный тип сообщения: {message_type}")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка декодирования JSON: {e}")
            self.logger.error(f"Полученные данные: {decrypted_data}")
        except Exception as e:
            self.logger.error(f"Ошибка обработки сообщения: {e}")

    def send_encrypted_message(self, data):
        """Отправка зашифрованного сообщения на сервер"""
        with self.socket_lock:
            try:
                if not self.connected:
                    self.logger.error("Нет подключения к серверу")
                    return False

                json_data = json.dumps(data, ensure_ascii=False).encode()
                encrypted_data = self.cipher_suite.encrypt(json_data)
                
                # Отправляем данные с маркером конца
                data_to_send = encrypted_data + b"<END>"
                total_sent = 0
                while total_sent < len(data_to_send):
                    sent = self.server_socket.send(data_to_send[total_sent:])
                    if sent == 0:
                        raise RuntimeError("Соединение разорвано")
                    total_sent += sent
                    
                self.logger.debug(f"Отправлено {total_sent} байт")
                return True
                
            except (socket.error, ConnectionResetError) as e:
                self.logger.error(f"Сетевая ошибка при отправке: {e}")
                self.connected = False
                return False
            except Exception as e:
                self.logger.error(f"Ошибка отправки сообщения: {e}")
                return False

    def send_request(self, request_data, expected_response_type, timeout=10):
        """Отправка запроса на сервер и ожидание ответа определенного типа"""
        if not self.connected or not self.server_socket:
            self.logger.error("Нет подключения к серверу для отправки запроса")
            return None
        
        # Сбрасываем состояние ожидания
        self.pending_response = None
        self.response_event.clear()
        self.expected_response_type = expected_response_type
        
        try:
            # Логируем запрос (без пароля в открытом виде)
            logged_request = request_data.copy()
            if 'password' in logged_request:
                logged_request['password'] = '***'
            self.logger.info(f"Отправка запроса: {logged_request}")
            
            if self.send_encrypted_message(request_data):
                # Ждем ответа определенного типа
                if self.response_event.wait(timeout=timeout):
                    response = self.pending_response
                    self.logger.info(f"Получен ответ: {response}")
                    return response
                else:
                    self.logger.error(f"Таймаут ожидания ответа типа {expected_response_type}")
                    return None
            else:
                self.logger.error("Не удалось отправить запрос")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка отправки запроса: {e}")
            return None
        finally:
            # Сбрасываем ожидание
            self.expected_response_type = None
            self.response_event.clear()
            self.pending_response = None

    def send_p2p_message(self, to_username, message, message_id=None):
        """Отправка P2P сообщения другому пользователю"""
        try:
            if not self.connected:
                self.logger.error("Нет подключения к серверу")
                return False

            # Генерируем ID сообщения если не предоставлен
            if not message_id:
                message_id = str(uuid.uuid4())
                
            message_data = {
                'type': 'p2p_message',
                'to': to_username,
                'message': message,
                'timestamp': time.time(),
                'from': self.username,
                'message_id': message_id
            }
            
            # Добавляем session_token для аутентификации
            if self.session_token:
                message_data['session_token'] = self.session_token
                
            self.logger.info(f"Отправка сообщения пользователю {to_username}: {message} (ID: {message_id})")
            success = self.send_encrypted_message(message_data)
            
            if success:
                self.logger.info(f"Сообщение успешно отправлено на сервер")
            else:
                self.logger.error(f"Не удалось отправить сообщение на сервер")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки P2P сообщения: {e}")
            return False

    def register(self, username, password, email=""):
        """Регистрация нового пользователя"""
        self.logger.info(f"Регистрация пользователя {username}")
        
        request_data = {
            'type': 'register',
            'username': username,
            'password': password,
            'email': email
        }
        
        response = self.send_request(request_data, 'auth_response')
        if response is None:
            self.logger.error("Не получен ответ от сервера при регистрации")
            return False
            
        if response.get('status') == 'success':
            self.logger.info("Регистрация успешна")
            return True
        else:
            error_msg = response.get('message', 'Неизвестная ошибка')
            self.logger.error(f"Ошибка регистрации: {error_msg}")
            return False

    def login(self, username, password):
        """Аутентификация пользователя"""
        self.logger.info(f"Вход пользователя {username}")
        
        request_data = {
            'type': 'login',
            'username': username,
            'password': password
        }
        
        response = self.send_request(request_data, 'auth_response')
        
        if response is None:
            self.logger.error("Не получен ответ от сервера при попытке входа")
            return False
        
        if response.get('status') == 'success':
            self.session_token = response.get('session_token')
            self.username = username
            self.logger.info("Вход выполнен успешно")
            return True
        else:
            error_msg = response.get('message', 'Неизвестная ошибка')
            self.logger.error(f"Ошибка входа: {error_msg}")
            return False

    def get_user_list(self):
        """Получение списка пользователей от сервера"""
        if not self.session_token:
            self.logger.error("Попытка получить список пользователей без авторизации")
            return None
            
        request_data = {
            'type': 'get_user_list',
            'session_token': self.session_token
        }
        
        self.logger.info("Запрос списка пользователей")
        
        response = self.send_request(request_data, 'user_list_update')
        
        if response is None:
            self.logger.error("Не получен ответ при запросе списка пользователей")
            return None
            
        users = response.get('users', [])
        self.logger.info(f"Получено пользователей: {len(users)}")
        
        # Извлекаем только имена пользователей из словарей
        if users and isinstance(users[0], dict):
            usernames = [user.get('username', '') for user in users if user.get('username')]
            return usernames
        else:
            return users

    def disconnect(self):
        """Отключение от сервера"""
        try:
            self.connected = False
            self.stop_listener = True
            if self.listener_thread and self.listener_thread.is_alive():
                self.listener_thread.join(timeout=2.0)
            if self.server_socket:
                self.server_socket.close()
            self.logger.info("Отключено от сервера")
        except Exception as e:
            self.logger.error(f"Ошибка при отключении: {e}")

    def reconnect(self):
        """Переподключение к серверу"""
        self.logger.info("Попытка переподключения...")
        try:
            self.disconnect()
            time.sleep(2)
            return self.connect()
        except Exception as e:
            self.logger.error(f"Ошибка переподключения: {e}")
            return False

    def start_heartbeat(self):
        """Периодическая отправка heartbeat для поддержания сессии"""
        def send_heartbeat():
            if self.connected and not self.stop_listener:
                try:
                    heartbeat_data = {
                        'type': 'heartbeat',
                        'session_token': self.session_token
                    }
                    self.send_encrypted_message(heartbeat_data)
                except Exception as e:
                    self.logger.error(f"Ошибка heartbeat: {e}")
            # Перезапускаем таймер
            if self.connected and not self.stop_listener:
                threading.Timer(30.0, send_heartbeat).start()

        # Запускаем первый heartbeat
        if self.connected and not self.stop_listener:
            threading.Timer(30.0, send_heartbeat).start()

if __name__ == "__main__":
    client = SecureNetworkClient()
    if client.connect():
        print("Подключение установлено")
        # Тестируем регистрацию
        if client.register("test_user", "test_password"):
            print("Регистрация успешна")
        else:
            print("Ошибка регистрации")
        client.disconnect()
    else:
        print("Ошибка подключения")