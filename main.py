# main.py

import os
import sys
import yaml
import logging

# === 1. Определяем базовую директорию (для скомпилированного EXE и исходников) ===
if getattr(sys, 'frozen', False):
    # Запущено как собранный EXE
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# === 2. Создаём папку для логов ДО любых импортов ===
log_dir = os.path.join(base_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

# === 3. Настраиваем логирование с абсолютным путём ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(log_dir, 'app_debug.log'))
    ]
)

logger = logging.getLogger('dialog_gui')
logger.setLevel(logging.DEBUG)

# === 4. Теперь можно импортировать остальные модули ===
try:
    from integrated_server import IntegratedServers
    from storage.database import ClientDatabase
    from network.p2p_network import P2PNetworkClient
    from core.auth_manager import AuthManager
    from ui.gui_p2p import P2PDialogApplication
    print("✅ Все модули успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# Загружаем конфигурацию
config_path = os.path.join(base_dir, 'config.yaml')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print("✅ Конфигурация загружена")
except Exception as e:
    print(f"❌ Ошибка загрузки config.yaml: {e}")
    sys.exit(1)

bootstrap_nodes = config['network']['bootstrap_nodes']

def main():
    # Дополнительные папки (уже созданы, но на всякий случай)
    os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)

    # Запускаем встроенные серверы (bootstrap + media)
    integrated = IntegratedServers()
    integrated.start()

    print("🎯 Инициализация приложения...")
    app = P2PDialogApplication(bootstrap_nodes=bootstrap_nodes)
    app.run()
    sys.exit(app.app.exec_())

    # После закрытия GUI останавливаем серверы
    integrated.stop()

if __name__ == '__main__':
    main()
