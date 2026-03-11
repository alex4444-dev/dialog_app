# main.py
import os
import sys
import logging
import yaml

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,  # Убедитесь, что уровень DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Вывод в консоль
        logging.FileHandler('app_debug.log')  # И в файл
    ]
)

logger = logging.getLogger('dialog_gui')

# Убедитесь, что все логгеры используют DEBUG
logging.getLogger().setLevel(logging.DEBUG)

# Добавляем текущую директорию в sys.path ПЕРВОЙ СТРОКОЙ
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Загружаем конфигурацию
config_path = os.path.join(current_dir, 'config.yaml')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print("✅ Конфигурация загружена")
except Exception as e:
    print(f"❌ Ошибка загрузки config.yaml: {e}")
    sys.exit(1)

# Получаем bootstrap-узлы
bootstrap_nodes = config['network']['bootstrap_nodes']

print(f"🚀 Запуск мессенджера Диалог из: {current_dir}")

try:
    from storage.database import ClientDatabase
    from network.p2p_network import P2PNetworkClient
    from core.auth_manager import AuthManager
    from ui.gui_p2p import P2PDialogApplication
    print("✅ Все модули успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("🔍 Проверьте структуру проекта:")
    for folder in ['core', 'network', 'storage', 'ui']:
        folder_path = os.path.join(current_dir, folder)
        if os.path.exists(folder_path):
            print(f"   ✅ {folder}: {os.listdir(folder_path)}")
        else:
            print(f"   ❌ {folder}: не существует")
    sys.exit(1)

def main():
    # Создаем необходимые директории
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    print("🎯 Инициализация приложения...")
    app = P2PDialogApplication(bootstrap_nodes=bootstrap_nodes)
    app.run()
    sys.exit(app.app.exec_())

if __name__ == '__main__':
    main()