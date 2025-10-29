import socket
import json
import threading
import logging
import time
import hashlib
import queue
import uuid
import struct
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
        self.call_handler = None
        
        # Флаги управления потоками
        self.stop_listener = False
        self.listener_thread = None
        self.socket_lock = threading.Lock()
        
        # Для синхронных запросов
        self.pending_response = None
        self.response_event = threading.Event()
        self.expected_response_type = None
        
        # Для звонков
        self.call_sockets = {}
        self.call_ports = {}
        self.active_call = None
        self.call_threads = {}
        self.audio_available = False
        self.audio_system = "Unknown"
        self.clients_info = {} # Для хранения информации о других клиентах
        
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

    def set_call_handler(self, handler):
        """Установка обработчика звонков"""
        self.logger.info(f"Установлен обработчик звонков: {handler}")
        self.call_handler = handler

    def handle_call_accepted(self, from_user, call_id, call_port):
        """Обработка принятия звонка другим пользователем"""
        self.logger.info(f"Звонок принят пользователем {from_user}")
    
        if call_id in self.active_calls:
            call_info = self.active_calls[call_id]
            call_window = call_info['window']
        
            # ✅ СОХРАНЯЕМ ИНФОРМАЦИЮ О ПОЛЬЗОВАТЕЛЕ
            if from_user not in self.clients_info:
                self.clients_info[from_user] = {}
        
            if call_port:
                self.clients_info[from_user]['call_port'] = call_port
        
            # Запускаем звонок в UI
            call_window.start_call()
        
            self.system_chat.append(f"✅ Пользователь {from_user} принял звонок")
        
        else:
            self.logger.warning(f"Звонок {call_id} не найден в активных звонках")

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
                # Поддержка разных форматов полей от сервера
                from_user = message.get('from') or message.get('from_user') or message.get('sender')
                text = message.get('message') or message.get('text') or message.get('content')
                
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
                
                # Игнорируем ошибки о несуществующих звонках - это нормальная ситуация
                if "Звонок не найден" in error_msg or "call_not_found" in error_msg:
                    self.logger.info("Игнорируем ошибку о несуществующем звонке (нормальная ситуация)")
                elif "Неверный тип ответа на звонок" in error_msg:
                    self.logger.warning("Сервер сообщает о неверном типе ответа на звонок. Проверьте формат отправляемых данных.")
                else:
                    self.logger.error(f"Ошибка от сервера: {error_msg}")
                    if self.status_handler:
                        self.status_handler('error', error_msg)
            
            # Обработка сообщений о звонках
            elif message_type == 'call_request':
                from_user = message.get('from')
                call_type = message.get('call_type', 'audio')
                call_id = message.get('call_id')
                
                self.logger.info(f"Входящий звонок от {from_user}, тип: {call_type}")
                if self.call_handler:
                    self.call_handler('incoming_call', from_user, call_type, call_id)
                    
            elif message_type == 'call_accepted':
                from_user = message.get('from')
                call_id = message.get('call_id')
                call_port = message.get('call_port')
                
                self.logger.info(f"Звонок принят пользователем {from_user}")
                if self.call_handler:
                    self.call_handler('call_accepted', from_user, call_id, call_port)
                    
            elif message_type == 'call_rejected':
                from_user = message.get('from')
                call_id = message.get('call_id')
                
                self.logger.info(f"Звонок отклонен пользователем {from_user}")
                if self.call_handler:
                    self.call_handler('call_rejected', from_user, call_id)
                    
            elif message_type == 'call_ended':
                from_user = message.get('from')
                call_id = message.get('call_id')
                
                self.logger.info(f"Звонок завершен пользователем {from_user}")
                if self.call_handler:
                    self.call_handler('call_ended', from_user, call_id)
                    
            elif message_type == 'call_info':
                from_user = message.get('from')
                call_id = message.get('call_id')
                call_port = message.get('call_port')
                
                self.logger.info(f"Информация о звонке от {from_user}, порт: {call_port}")
                if self.call_handler:
                    self.call_handler('call_info', from_user, call_id, call_port)
                    
            # Обработка ответов на запросы завершения звонка
            elif message_type == 'call_end_response':
                status = message.get('status')
                call_id = message.get('call_id')
                duration = message.get('duration', 0)
                
                if status == 'already_ended':
                    self.logger.info(f"Звонок {call_id} уже был завершен (нормальная ситуация)")
                elif status == 'ended':
                    self.logger.info(f"Звонок {call_id} успешно завершен, длительность: {duration} сек.")
                else:
                    self.logger.warning(f"Неизвестный статус завершения звонка: {status}")
                    
            elif message_type == 'call_answer_response':
                status = message.get('status')
                call_id = message.get('call_id')
                
                if status == 'call_not_found':
                    self.logger.info(f"Звонок {call_id} не найден при попытке ответа")
                elif status in ['accepted', 'rejected']:
                    self.logger.info(f"Ответ на звонок {call_id}: {status}")
                else:
                    self.logger.warning(f"Неизвестный статус ответа на звонок: {status}")
                    
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
                self.logger.info("=== НАЧАЛО ОТПРАВКИ СООБЩЕНИЯ ===")

                if not self.connected:
                    self.logger.error("Нет подключения к серверу")
                    return False

                if not self.server_socket:
                    self.logger.error("❌ Нет сокета сервера")
                    return False

                # Проверяем cipher_suite
                if not self.cipher_suite:
                    self.logger.error("❌ Нет cipher_suite для шифрования")
                    return False

                # Логируем отправляемые данные (без пароля)
                logged_data = data.copy()
                if 'password' in logged_data:
                    logged_data['password'] = '***'
                self.logger.info(f"📤 Отправляемые данные: {logged_data}")


                # Сериализуем в JSON
                json_data = json.dumps(data, ensure_ascii=False).encode()
                self.logger.info(f"📄 JSON данные ({len(json_data)} байт)")

                # Шифруем
                encrypted_data = self.cipher_suite.encrypt(json_data)
                self.logger.info(f"🔒 Зашифрованные данные ({len(encrypted_data)} байт)")

                # Отправляем данные с маркером конца
                data_to_send = encrypted_data + b"<END>"
                self.logger.info(f"📦 Полные данные для отправки ({len(data_to_send)} байт)")
                
                # Отправляем данные
                total_sent = 0
                attempts = 0
                max_attempts = 3
                
                while total_sent < len(data_to_send) and attempts < max_attempts:
                    try:
                        sent = self.server_socket.send(data_to_send[total_sent:])
                        if sent == 0:
                            self.logger.error("❌ Соединение разорвано (sent=0)")
                            self.connected = False
                            return False
                        
                        total_sent += sent
                        self.logger.info(f"📨 Отправлено {sent} байт, всего {total_sent}/{len(data_to_send)}")
                    
                    except socket.error as e:
                        attempts += 1
                        self.logger.warning(f"⚠️ Ошибка сокета (попытка {attempts}/{max_attempts}): {e}")
                        
                        if attempts >= max_attempts:
                            raise e
                        time.sleep(0.1)  # Короткая пауза перед повторной попыткой

                    if total_sent == len(data_to_send):
                        self.logger.info("✅ Сообщение успешно отправлено")
                        return True
                    else:
                        self.logger.error(f"❌ Отправлено только {total_sent}/{len(data_to_send)} байт")
                        return False

                self.logger.debug(f"Отправлено {total_sent} байт")
                return True
                
            except (socket.error, ConnectionResetError) as e:
                self.logger.error(f"Сетевая ошибка при отправке: {e}")
                self.connected = False
                return False
            except Exception as e:
                self.logger.error(f"Ошибка отправки сообщения: {e}")
                import traceback
                self.logger.error(f"Трассировка: {traceback.format_exc()}")
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
                'message_id': message_id,
                'session_token': self.session_token
            }
            
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

    # Методы для звонков
    def send_call_request(self, to_username, call_type='audio'):
        """Отправка запроса на звонок"""
        try:
            if not self.connected:
                self.logger.error("Нет подключения к серверу")
                return None

            call_id = str(uuid.uuid4())
                
            call_data = {
                'type': 'call_request',
                'to': to_username,
                'call_type': call_type,
                'call_id': call_id,
                'session_token': self.session_token
            }
            
            self.logger.info(f"Отправка запроса на звонок пользователю {to_username}, тип: {call_type}")
            success = self.send_encrypted_message(call_data)
            
            if success:
                self.logger.info(f"Запрос на звонок успешно отправлен")
                return call_id
            else:
                self.logger.error(f"Не удалось отправить запрос на звонок")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка отправки запроса на звонок: {e}")
            return None

    def send_call_answer(self, call_id, answer, call_port=None):
        """Отправка ответа на звонок (accept или reject)"""
        try:
            if not self.connected or not self.server_socket:
                if not self.ensure_connection():
                    self.logger.error("Не удалось восстановить соединение")
                    return False

            # Проверяем корректность ответа
            if answer not in ['accept', 'reject']:
                self.logger.error(f"Недопустимый тип ответа на звонок: {answer}")
                return False

            response_data = {
                'type': 'call_answer',
                'call_id': call_id,
                'answer': answer,
                'session_token': self.session_token
            }
            
            if answer == 'accept':
                response_data['call_port'] = call_port
            
            self.logger.info(f"Отправка ответа на звонок {call_id}: {answer}")
            self.logger.debug(f"Данные ответа: {response_data}")
            
            success = self.send_encrypted_message(response_data)
            
            if success:
                self.logger.info(f"Ответ на звонок успешно отправлен")
                return True
            else:
                self.logger.error(f"Не удалось отправить ответ на звонок")
                return False
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")
            return False

    def send_call_end(self, call_id):
        """Отправка сообщения о завершении звонка"""
        try:
            if not self.connected:
                self.logger.error("Нет подключения к серверу")
                return False

            end_data = {
                'type': 'call_end',
                'call_id': call_id,
                'session_token': self.session_token
            }
            
            self.logger.info(f"Отправка сообщения о завершении звонка {call_id}")
            success = self.send_encrypted_message(end_data)
            
            if success:
                self.logger.info(f"Сообщение о завершении звонка успешно отправлено")
                return True
            else:
                self.logger.error(f"Не удалось отправить сообщение о завершении звонка")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения о завершении звонка: {e}")
            return False

    def send_ice_candidate(self, call_id, candidate, target_user):
        """Отправка ICE-кандидата для WebRTC"""
        try:
            if not self.connected:
                self.logger.error("Нет подключения к серверу")
                return False

            ice_data = {
                'type': 'ice_candidate',
                'call_id': call_id,
                'candidate': candidate,
                'target_user': target_user,
                'session_token': self.session_token
            }
            
            self.logger.info(f"Отправка ICE-кандидата для звонка {call_id} пользователю {target_user}")
            success = self.send_encrypted_message(ice_data)
            
            if success:
                self.logger.info(f"ICE-кандидат успешно отправлен")
                return True
            else:
                self.logger.error(f"Не удалось отправить ICE-кандидат")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка отправки ICE-кандидата: {e}")
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
        
        # ✅ ОБНОВЛЯЕМ ИНФОРМАЦИЮ О КЛИЕНТАХ
        self.update_clients_info(users)

        # Извлекаем только имена пользователей из словарей
        if users and isinstance(users[0], dict):
            usernames = [user.get('username', '') for user in users if user.get('username')]
            return usernames
        else:
            return users

    def send_client_info(self, p2p_port=0, external_ip=''):
        """Отправка информации о клиенте (P2P порт и внешний IP)"""
        if not self.session_token:
            self.logger.error("Попытка отправить client_info без авторизации")
            return False
            
        request_data = {
            'type': 'client_info',
            'p2p_port': p2p_port,
            'external_ip': external_ip,
            'session_token': self.session_token
        }
        
        self.logger.info(f"Отправка client_info: порт={p2p_port}, IP={external_ip}")
        return self.send_encrypted_message(request_data)

    def logout(self):
        """Выход из системы"""
        self.session_token = None
        self.username = None
        self.logger.info("Выход из системы выполнен")

    def disconnect(self):
        """Отключение от сервера"""
        try:
            self.connected = False
            self.stop_listener = True
            
            # Закрываем все звонки
            for call_id in list(self.call_threads.keys()):
                self.stop_call(call_id)
                
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

    def check_connection(self):
        """Проверка состояния соединения"""
        self.logger.info("=== ПРОВЕРКА СОЕДИНЕНИЯ ===")
        self.logger.info(f"connected: {self.connected}")
        self.logger.info(f"server_socket: {self.server_socket}")
        self.logger.info(f"session_token: {'Есть' if self.session_token else 'Нет'}")
        self.logger.info(f"cipher_suite: {'Есть' if self.cipher_suite else 'Нет'}")

        if self.connected and self.server_socket:
            try:
                # Простая проверка "ping"
                test_data = {'type': 'heartbeat', 'session_token': self.session_token}
                return self.send_encrypted_message(test_data)
            except:
                return False
        return False

    def ensure_connection(self):
        """Обеспечение соединения с сервером (переподключение при необходимости)"""
        if self.check_connection():
            return True
    
        self.logger.warning("Соединение разорвано, пытаемся переподключиться...")
        return self.reconnect()

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

    # Методы для работы с медиа-звонками
    def start_call_server(self, call_id, port=0):
        """Запуск сервера для приема медиа-данных"""
        try:
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            call_socket.bind(('0.0.0.0', port))
            call_socket.listen(1)
            
            actual_port = call_socket.getsockname()[1]
            self.call_sockets[call_id] = call_socket
            self.call_ports[call_id] = actual_port
            
            self.logger.info(f"Сервер звонка {call_id} запущен на порту {actual_port}")
            return actual_port
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера звонка: {e}")
            return None

    def connect_to_call(self, call_id, host, port):
        """Подключение к медиа-серверу другого пользователя"""
        try:
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.connect((host, port))
            self.call_sockets[call_id] = call_socket
            
            self.logger.info(f"Подключение к звонку {call_id} на {host}:{port} установлено")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка подключения к звонку: {e}")
            return False

    def send_media_data(self, call_id, data_type, data):
        """Отправка медиа-данных через звонок"""
        try:
            if call_id not in self.call_sockets:
                self.logger.error(f"Звонок {call_id} не активен")
                return False
                
            call_socket = self.call_sockets[call_id]
            
            # Формируем заголовок: тип данных (1 байт) + длина данных (4 байта)
            header = struct.pack('BI', ord(data_type), len(data))
            message = header + data
            
            call_socket.sendall(message)
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки медиа-данных: {e}")
            return False

    def receive_media_data(self, call_id, callback):
        """Прием медиа-данных через звонок"""
        def receive_thread():
            try:
                if call_id not in self.call_sockets:
                    return
                    
                call_socket = self.call_sockets[call_id]
                
                while call_id in self.call_sockets:
                    # Читаем заголовок
                    header = call_socket.recv(5)
                    if not header:
                        break
                        
                    data_type_char, data_length = struct.unpack('BI', header)
                    data_type = chr(data_type_char)
                    
                    # Читаем данные
                    data = b''
                    while len(data) < data_length:
                        chunk = call_socket.recv(data_length - len(data))
                        if not chunk:
                            break
                        data += chunk
                    
                    if len(data) == data_length:
                        callback(data_type, data)
                    else:
                        self.logger.error("Неполные данные получены")
                        break
                        
            except Exception as e:
                self.logger.error(f"Ошибка приема медиа-данных: {e}")
            finally:
                self.logger.info(f"Поток приема медиа-данных для звонка {call_id} завершен")
        
        thread = threading.Thread(target=receive_thread, daemon=True)
        self.call_threads[call_id] = thread
        thread.start()

    def stop_call(self, call_id):
        """Остановка звонка и очистка ресурсов"""
        try:
            if call_id in self.call_sockets:
                self.call_sockets[call_id].close()
                del self.call_sockets[call_id]
                
            if call_id in self.call_ports:
                del self.call_ports[call_id]
                
            if call_id in self.call_threads:
                if self.call_threads[call_id].is_alive():
                    self.call_threads[call_id].join(timeout=1.0)
                del self.call_threads[call_id]
                
            self.logger.info(f"Звонок {call_id} остановлен")
            
        except Exception as e:
            self.logger.error(f"Ошибка остановки звонка: {e}")

    def update_clients_info(self, users):
        """Обновление информации о клиентах при получении списка пользователей"""
        try:
            for user in users:
                if isinstance(user, dict):
                    username = user.get('username')
                    if username and username not in self.clients_info:
                        self.clients_info[username] = {
                            'external_ip': user.get('external_ip', ''),
                            'p2p_port': user.get('p2p_port', 0)
                        }
        except Exception as e:
            self.logger.error(f"Ошибка обновления информации о клиентах: {e}")

    # Универсальные методы для работы с аудио
    def setup_universal_audio(self):
        """Универсальная настройка аудио - БЕЗОПАСНАЯ ВЕРСИЯ"""
        try:
            # Проверяем доступность sounddevice
            try:
                import sounddevice as sd
                self.sd = sd
            
                # Простая проверка доступности аудио
                try:
                    devices = sd.query_devices()
                    self.audio_available = len(devices) > 0
                    self.audio_system = "Доступно"
                    self.logger.info(f"Аудио система инициализирована, устройств: {len(devices)}")
                    return True
                except Exception as e:
                    self.logger.warning(f"Аудио устройства недоступны: {e}")
                    self.audio_available = False
                    return False
                
            except ImportError:
                self.logger.warning("SoundDevice не установлен, аудио недоступно")
                self.audio_available = False
                return False
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации универсального аудио: {e}")
            self.audio_available = False
            return False

    def connect_to_call_server(self, host, port, call_id):
        """Подключение к серверу звонка другого пользователя"""
        try:
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.settimeout(5)
            call_socket.connect((host, port))
        
            self.call_sockets[call_id] = call_socket
            self.logger.info(f"Подключение к звонку {call_id} на {host}:{port} установлено")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка подключения к серверу звонка: {e}")
            return False

    def send_call_answer(self, call_id, answer, call_port=None):
        """Отправка ответа на звонок(accept или reject)"""
        try:
            if not self.connected or not self.server_socket:
                # ИСПРАВЛЕНО: убрана лишняя строка с if not self.ensure_connection()
                
                if not self.ensure_connection():
                    self.logger.error("Не удалось восстановить соединение")
                    return False

                
            # Проверяем корректность ответа
            if answer not in ['accept', 'reject']:
                self.logger.error(f"Недопустимый тип ответа на звонок: {answer}")
                return False

            response_data = {
                'type': 'call_answer',
                'call_id': call_id,
                'answer': answer,
                'session_token': self.session_token
            }
        
            if answer == 'accept' and call_port is not None:
                response_data['call_port'] = call_port
        
            self.logger.info(f"Отправка ответа на звонок {call_id}: {answer}")
            self.logger.debug(f"Данные ответа: {response_data}")
            
            success = self.send_encrypted_message(response_data)
        
            if success:
                self.logger.info(f"Ответ на звонок успешно отправлен")
                return True
            else:
                self.logger.error(f"Не удалось отправить ответ на звонок")
                return False
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки ответа на звонок: {e}")
            return False

    def _detect_active_audio_system(self):
        """Определение активной звуковой системы"""
        try:
            import subprocess
            import os
            
            # Проверяем PipeWire
            if os.path.exists("/usr/bin/pw-top") or "pipewire" in os.popen("ps aux").read().lower():
                return "PipeWire"
            
            # Проверяем PulseAudio
            if os.path.exists("/usr/bin/pulseaudio") or "pulseaudio" in os.popen("ps aux").read().lower():
                return "PulseAudio"
            
            # Проверяем через sounddevice
            try:
                devices = self.sd.query_devices()
                if devices:
                    # Анализируем имена устройств для определения системы
                    device_names = [device['name'].lower() for device in devices]
                    if any('pipewire' in name for name in device_names):
                        return "PipeWire"
                    elif any('pulse' in name for name in device_names):
                        return "PulseAudio"
                    else:
                        return "ALSA"
            except:
                pass
            
            return "ALSA (по умолчанию)"
            
        except Exception as e:
            self.logger.warning(f"Не удалось определить звуковую систему: {e}")
            return "Неизвестно"

    def create_universal_audio_stream(self, callback, sample_rate=16000, channels=1):
        """Создание универсального аудио потока"""
        if not self.audio_available:
            self.logger.error("Аудио недоступно")
            return None
        
        try:
            import sounddevice as sd
            
            stream = sd.Stream(
                samplerate=sample_rate,
                channels=channels,
                dtype='float32',
                callback=callback,
                latency='low'
            )
            
            self.logger.info("Универсальный аудио поток создан")
            return stream
            
        except Exception as e:
            self.logger.error(f"Ошибка создания аудио потока: {e}")
            return None

    def test_audio_system(self):
        """Тестирование звуковой системы"""
        if not self.audio_available:
            return "Аудио недоступно"
        
        try:
            import sounddevice as sd
            import numpy as np
            
            info = f"Активная звуковая система: {self.audio_system}\n\n"
            
            devices = sd.query_devices()
            default_input = sd.default.device[0]
            default_output = sd.default.device[1]
            
            info += f"Устройств найдено: {len(devices)}\n"
            info += f"Устройство ввода по умолчанию: {default_input}\n"
            info += f"Устройство вывода по умолчанию: {default_output}\n\n"
            
            # Простой тест воспроизведения
            try:
                duration = 1.0
                frequency = 440
                sample_rate = 44100
                
                t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
                tone = 0.3 * np.sin(2 * np.pi * frequency * t)
                
                sd.play(tone, sample_rate)
                sd.wait()
                
                info += "✅ Тест воспроизведения выполнен успешно!"
            except Exception as e:
                info += f"❌ Ошибка теста воспроизведения: {e}"
            
            return info
            
        except Exception as e:
            return f"Ошибка тестирования аудио: {e}"
    
    def start_call_server(self, call_id, port=0):
        """Запуск сервера для приема медиа-данных"""
        try:
            # ✅ ПРОВЕРЯЕМ, НЕ ЗАПУЩЕН ЛИ УЖЕ СЕРВЕР ДЛЯ ЭТОГО ЗВОНКА
            if call_id in self.call_sockets:
                self.logger.info(f"Сервер для звонка {call_id} уже запущен")
                return self.call_ports.get(call_id)
            
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
            # ✅ БЕЗОПАСНАЯ ПРИВЯЗКА С ОБРАБОТКОЙ ОШИБОК
            try:
                call_socket.bind(('0.0.0.0', port))
                call_socket.listen(1)
            
                actual_port = call_socket.getsockname()[1]
                self.call_sockets[call_id] = call_socket
                self.call_ports[call_id] = actual_port
            
                self.logger.info(f"Сервер звонка {call_id} запущен на порту {actual_port}")
                return actual_port
            
            except Exception as bind_error:
                self.logger.error(f"Ошибка привязки сервера звонка: {bind_error}")
                call_socket.close()
                return None
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера звонка: {e}")  # ✅ ИСПРАВЛЕНО: self.logger
        return None
   
    def cleanup_audio_resources(self):
        """Очистка всех аудио ресурсов"""
        try:
            # Останавливаем все активные звонки
            for call_id in list(self.call_threads.keys()):
                self.stop_call(call_id)
                
            # Закрываем все аудио потоки
            if hasattr(self, 'sd'):
                import sounddevice as sd
                # Останавливаем все активные потоки sounddevice
                try:
                    sd.stop()
                except:
                    pass
                    
            self.logger.info("Аудио ресурсы очищены")
            
        except Exception as e:
            self.logger.error(f"Ошибка очистки аудио ресурсов: {e}")

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