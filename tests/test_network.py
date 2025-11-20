# test_network.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import ClientDatabase
from network.p2p_network import P2PNetworkClient

def test_network():
    print("🧪 Тестирование P2P сети с двумя узлами...")
    
    # Узел 1 на порту 8888
    db1 = ClientDatabase("data/node1.db")
    node1 = P2PNetworkClient(db1)
    node1.listen_port = 8888
    
    # Узел 2 на порту 8889  
    db2 = ClientDatabase("data/node2.db")
    node2 = P2PNetworkClient(db2)
    node2.listen_port = 8889
    node2.bootstrap_nodes = [{"host": "localhost", "port": 8888}]
    
    print("🚀 Запуск узла 1 на порту 8888...")
    if node1.start():
        print("✅ Узел 1 запущен")
        
        print("🚀 Запуск узла 2 на порту 8889...")
        if node2.start():
            print("✅ Узел 2 запущен")
            
            # Ждем подключения
            import time
            time.sleep(5)
            
            print(f"🔗 Узел 1 подключен к {len(node1.connected_peers)} пирам")
            print(f"🔗 Узел 2 подключен к {len(node2.connected_peers)} пирам")
            
            # Останавливаем
            node2.stop()
            node1.stop()
            print("✅ Узлы остановлены")
        else:
            print("❌ Не удалось запустить узел 2")
            node1.stop()
    else:
        print("❌ Не удалось запустить узел 1")

if __name__ == '__main__':
    test_network()