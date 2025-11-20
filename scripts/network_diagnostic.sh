#!/bin/bash

# Диагностика P2P сети

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

source venv/bin/activate

echo "🌐 Диагностика P2P сети..."

python -c "
import socket
import logging
from src.network.p2p_network import P2PNetworkClient
from src.storage.database import ClientDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('diagnostic')

def run_diagnostic():
    db = ClientDatabase()
    client = P2PNetworkClient(db)
    
    print('=== ДИАГНОСТИКА P2P СЕТИ ===')
    print()
    
    # Проверка порта
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('0.0.0.0', 8888))
        print('✅ Порт 8888 доступен')
        sock.close()
    except OSError:
        print('❌ Порт 8888 занят')
    
    # Проверка подключения к bootstrap узлам
    print()
    print('=== ПРОВЕРКА BOOTSTRAP УЗЛОВ ===')
    
    bootstrap_nodes = [
        ('localhost', 8888),
        # Добавьте другие узлы для проверки
    ]
    
    for host, port in bootstrap_nodes:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            if result == 0:
                print(f'✅ {host}:{port} - доступен')
            else:
                print(f'❌ {host}:{port} - недоступен')
            sock.close()
        except Exception as e:
            print(f'❌ {host}:{port} - ошибка: {e}')
    
    # Информация о сети
    print()
    print('=== ИНФОРМАЦИЯ О СЕТИ ===')
    
    import netifaces
    interfaces = netifaces.interfaces()
    for iface in interfaces:
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                print(f'📡 Интерфейс: {iface}')
                print(f'   IP: {addr[\"addr\"]}')
                print(f'   Маска: {addr[\"netmask\"]}')

run_diagnostic()
"

echo "✅ Диагностика завершена"