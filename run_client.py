import sys
import logging
import os

# Добавляем путь к текущей директории для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from client.gui_secure import DialogApplication

def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Создаем приложение
    dialog_app = DialogApplication()
    
    # Запускаем логику приложения
    dialog_app.run()
    
    # Запускаем главный цикл приложения
    sys.exit(dialog_app.app.exec_())

if __name__ == '__main__':
    main()