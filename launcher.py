# simple_test.py
import os
import sys
import time

# Освобождаем порты
os.system("pkill -f 'python'")  # Осторожно! Убьет все Python процессы
time.sleep(2)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import ClientDatabase
from network.p2p_network import P2PNetworkClient

def test_single_node():
    """Тест одного узла на гарантированно свободном порту"""
    print("🧪 Тестирование одного узла...")
    
    # Используем высокий порт, который редко используется
    db = ClientDatabase("data/test_single.db")
    client = P2PNetworkClient(db)
    client.listen_port = 65432  # Обычно свободный порт
    
    if client.start():
        print("✅ Узел запущен успешно!")
        print(f"📡 Порт: {client.listen_port}")
        
        # Работаем 10 секунд
        time.sleep(10)
        
        client.stop()
        print("🛑 Узел остановлен")
        return True
    else:
        print("❌ Не удалось запустить узел")
        return False

if __name__ == '__main__':
    test_single_node()