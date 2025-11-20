# test_p2p.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from storage.database import ClientDatabase
from network.p2p_network import P2PNetworkClient

def test_p2p():
    print("🧪 Тестирование P2P клиента...")
    
    # Инициализация БД
    db = ClientDatabase()
    print("✅ База данных инициализирована")
    
    # Создание P2P клиента
    p2p_client = P2PNetworkClient(db)
    print("✅ P2P клиент создан")
    
    # Запуск P2P сети
    if p2p_client.start():
        print("✅ P2P сеть запущена")
        
        # Тест на 5 секунд
        import time
        time.sleep(5)
        
        # Остановка
        p2p_client.stop()
        print("✅ P2P сеть остановлена")
    else:
        print("❌ Не удалось запустить P2P сеть")

if __name__ == '__main__':
    test_p2p()