# utils/config.py
import yaml
import os

def load_config():
    """Загрузка конфигурации"""
    config_path = "config.yaml"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    else:
        # Конфигурация по умолчанию
        return {
            'network': {
                'min_port': 9000,
                'max_port': 10000,
                'max_port_attempts': 100,
                'bootstrap_nodes': [{"host": "localhost", "port": 9000}]
            },
            'database': {
                'path': './data/client.db'
            },
            'logging': {
                'level': 'INFO',
                'file': './logs/client.log'
            }
        }

# Обновите P2PNetworkClient для использования конфигурации
class P2PNetworkClient(QObject):
    def __init__(self, db, config=None):
        super().__init__()
        self.db = db
        self.config = config or load_config()
        
        # Используем настройки из конфигурации
        network_config = self.config.get('network', {})
        self.min_port = network_config.get('min_port', 9000)
        self.max_port = network_config.get('max_port', 10000)
        self.max_port_attempts = network_config.get('max_port_attempts', 100)
        self.bootstrap_nodes = network_config.get('bootstrap_nodes', [])
        
        # Остальная инициализация...