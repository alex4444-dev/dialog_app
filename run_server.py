#!/usr/bin/env python3
"""
Запуск сервера мессенджера Диалог
"""

import os
import sys
import logging

# Добавляем текущую директорию в Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('server.log')
    ]
)

logger = logging.getLogger('dialog_server')

def main():
    try:
        from server.server_secure import SecureDialogServer
        
        logger.info("Запуск сервера Диалог...")
        
        server = SecureDialogServer(host='127.0.0.1', port=5555)
        logger.info(f"Сервер будет слушать на {server.host}:{server.port}")
        logger.info("Для остановки сервера нажмите Ctrl+C")
        
        server.start()
        
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}")
        print(f"Ошибка импорта: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при запуске сервера: {e}")
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()