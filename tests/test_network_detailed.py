# test_network_detailed.py
import os
import sys
import logging
import time

# Настраиваем подробное логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/network_test.log', mode='w')
    ]
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import ClientDatabase
from network.p2p_network import P2PNetworkClient

def test_network_detailed():
    print("🧪 Детальное тестирование P2P сети с двумя узлами...")
    
    # Создаем директории для логов и данных
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # Узел 1 на порту 8888
    print("\n=== УЗЕЛ 1 ===")
    db1 = ClientDatabase("data/node1.db")
    node1 = P2PNetworkClient(db1)
    node1.listen_port = 8888
    node1.bootstrap_nodes = [{"host": "localhost", "port": 8889}]  # Указываем узел 2 как bootstrap
    
    # Узел 2 на порту 8889  
    print("\n=== УЗЕЛ 2 ===")
    db2 = ClientDatabase("data/node2.db")
    node2 = P2PNetworkClient(db2)
    node2.listen_port = 8889
    node2.bootstrap_nodes = [{"host": "localhost", "port": 8888}]  # Указываем узел 1 как bootstrap
    
    print("\n🚀 Запуск узла 1 на порту 8888...")
    if node1.start():
        print("✅ Узел 1 запущен")
        
        # Даем время узлу 1 запуститься
        time.sleep(2)
        
        print("\n🚀 Запуск узла 2 на порту 8889...")
        if node2.start():
            print("✅ Узел 2 запущен")
            
            # Устанавливаем имена пользователей для тестирования
            node1.username = "node1"
            node2.username = "node2"
            
            # Даем время на обмен информацией о пользователях
            time.sleep(2)
            
            # Мониторим подключения в течение 10 секунд
            print("\n📊 Мониторинг подключений...")
            for i in range(10):
                time.sleep(1)
                peers1 = len(node1.connected_peers)
                peers2 = len(node2.connected_peers)
                
                # Получаем имена подключенных пользователей
                users1 = []
                for peer_id, peer_info in node1.connected_peers.items():
                    if peer_info.get('username'):
                        users1.append(peer_info['username'])
                
                users2 = []
                for peer_id, peer_info in node2.connected_peers.items():
                    if peer_info.get('username'):
                        users2.append(peer_info['username'])
                
                print(f"⏱️  {i+1}s: Узел 1 - {peers1} пиров ({users1}), Узел 2 - {peers2} пиров ({users2})")
                
                # Если оба узла подключились, выходим раньше
                if peers1 > 0 and peers2 > 0:
                    print("🎉 Узлы успешно подключились друг к другу!")
                    break
            
            print(f"\n📊 Финальная статистика:")
            print(f"   Узел 1 подключен к {len(node1.connected_peers)} пирам: {list(node1.connected_peers.keys())}")
            print(f"   Узел 2 подключен к {len(node2.connected_peers)} пирам: {list(node2.connected_peers.keys())}")
            
            # Тестируем обмен сообщениями
            if node1.connected_peers and node2.connected_peers:
                print("\n🧪 Тестирование обмена сообщениями...")
                
                # Узел 1 отправляет сообщение узлу 2
                print("📤 Узел 1 отправляет сообщение узлу 2...")
                if node1.send_message("node2", "Привет от узла 1!"):
                    print("✅ Сообщение отправлено от узла 1 к узлу 2")
                else:
                    print("❌ Не удалось отправить сообщение от узла 1 к узлу 2")
                
                time.sleep(2)
                
                # Узел 2 отправляет сообщение узлу 1
                print("📤 Узел 2 отправляет сообщение узлу 1...")
                if node2.send_message("node1", "Привет от узла 2!"):
                    print("✅ Сообщение отправлено от узла 2 к узлу 1")
                else:
                    print("❌ Не удалось отправить сообщение от узла 2 к узлу 1")
            
            # Останавливаем
            print("\n🛑 Остановка узлов...")
            node2.stop()
            node1.stop()
            print("✅ Узлы остановлены")
            
        else:
            print("❌ Не удалось запустить узел 2")
            node1.stop()
    else:
        print("❌ Не удалось запустить узел 1")

if __name__ == '__main__':
    test_network_detailed()