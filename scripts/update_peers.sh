#!/bin/bash

# Обновление списка известных пиров

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

source venv/bin/activate

echo "🔄 Обновление списка пиров..."

python -c "
import requests
import yaml
import os

def update_peers_list():
    # Загрузка публичных bootstrap узлов
    try:
        print('Загрузка списка публичных узлов...')
        
        # Пример получения списка узлов из внешнего источника
        # (можно заменить на свой источник)
        public_nodes = [
            'node1.dialog-messenger.org:8888',
            'node2.dialog-messenger.org:8888',
            'p2p.dialog.example.com:8888'
        ]
        
        # Чтение текущего конфига
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
        else:
            config = {}
        
        # Обновление списка bootstrap узлов
        if 'network' not in config:
            config['network'] = {}
        
        current_nodes = set(config['network'].get('bootstrap_nodes', []))
        new_nodes = set(public_nodes)
        
        # Добавляем только новые узлы
        updated_nodes = list(current_nodes.union(new_nodes))
        config['network']['bootstrap_nodes'] = updated_nodes
        
        # Сохранение обновленного конфига
        with open('config.yaml', 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        print(f'✅ Список узлов обновлен. Всего узлов: {len(updated_nodes)}')
        for node in updated_nodes:
            print(f'   - {node}')
            
    except Exception as e:
        print(f'❌ Ошибка обновления списка узлов: {e}')

update_peers_list()
"

echo "✅ Список пиров обновлен"