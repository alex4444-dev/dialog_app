#!/usr/bin/env python3
"""
Тестирование медиа-соединений для звонков
"""

import socket
import threading
import time
import json

def create_media_server(port=9100):
    """Создание тестового медиа-сервера"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(1)
    print(f"🔊 Медиа-сервер запущен на порту {port}")
    
    def handle_client(client_socket, addr):
        print(f"✅ Подключен клиент {addr}")
        try:
            # Отправляем подтверждение
            ack = json.dumps({'type': 'media_ack', 'status': 'connected'})
            client_socket.send(ack.encode())
            
            # Простая эхо-логика для теста
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                print(f"📨 Получено: {len(data)} байт")
                # Эхо-ответ
                client_socket.send(data)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        finally:
            client_socket.close()
            print(f"🔌 Клиент {addr} отключен")
    
    while True:
        client, addr = server.accept()
        threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()

def create_media_client(port=9100):
    """Создание тестового медиа-клиента"""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(5.0)
    
    try:
        client.connect(('localhost', port))
        print(f"✅ Подключен к медиа-серверу на порту {port}")
        
        # Получаем подтверждение
        data = client.recv(1024)
        if data:
            ack = json.loads(data.decode())
            print(f"📨 Получено подтверждение: {ack}")
        
        # Тестовая отправка данных
        for i in range(3):
            test_data = f"Тестовые данные {i}".encode()
            client.send(test_data)
            time.sleep(1)
            
            # Получаем эхо
            echo = client.recv(1024)
            print(f"🔊 Эхо: {echo}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        create_media_server()
    else:
        create_media_client()