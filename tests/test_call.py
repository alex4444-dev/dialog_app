#!/usr/bin/env python3
"""
Тестирование звонков
"""

import socket
import threading
import time
import json

def test_media_connection():
    """Тест медиа-соединения"""
    print("🔊 Тестирование медиа-соединения...")
    
    # Подключаемся к медиа-серверу
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        sock.connect(('localhost', 9100))
        print("✅ Подключено к медиа-серверу")
        
        # Регистрируемся
        register_data = {
            'call_id': 'test_call_123',
            'action': 'register',
            'username': 'test_user'
        }
        sock.send(json.dumps(register_data).encode())
        
        # Ждем ответ
        response = sock.recv(1024)
        if response:
            resp = json.loads(response.decode())
            print(f"📨 Ответ сервера: {resp}")
            
            # Тестовая отправка данных
            test_data = b"test_audio_data"
            sock.send(test_data)
            
            # Ждем эхо
            echo = sock.recv(1024)
            print(f"🔊 Получено эхо: {len(echo)} байт")
            
    except ConnectionRefusedError:
        print("❌ Не удалось подключиться к медиа-серверу")
        print("Запустите медиа-сервер: python simple_media_server.py")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    test_media_connection()