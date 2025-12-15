# test_bootstrap.py
import socket
import json
import time

def test_connection():
    """Тестирование подключения к bootstrap"""
    try:
        print("Тестирование подключения к bootstrap...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        # Пробуем подключиться
        sock.connect(('127.0.0.1', 8888))
        print("✅ Подключение успешно")
        
        # Отправляем тестовое сообщение
        message = {
            'type': 'register',
            'port': 12345,
            'username': 'test_user'
        }
        
        sock.sendall(json.dumps(message).encode() + b'\n')
        print("✅ Сообщение отправлено")
        
        # Получаем ответ
        data = sock.recv(4096)
        response = json.loads(data.decode().strip())
        print(f"✅ Ответ получен: {response}")
        
        sock.close()
        return True
        
    except ConnectionRefusedError:
        print("❌ Bootstrap сервер не запущен или недоступен")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    test_connection()