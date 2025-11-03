import sys
import os
import traceback
import signal

def handle_exception(exc_type, exc_value, exc_traceback):
    """Обработчик необработанных исключений"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
        
    print("❌ Необработанное исключение:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)

def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    print("\n🔴 Получен сигнал завершения...")
    sys.exit(0)

# Устанавливаем обработчики
sys.excepthook = handle_exception
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    # Добавляем текущую директорию в путь
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    # Пытаемся импортировать и запустить
    try:
        from client.gui_secure import main as gui_main
        print("✅ Запуск GUI...")
        gui_main()
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        # Пробуем альтернативный путь
        try:
            client_dir = os.path.join(current_dir, 'client')
            sys.path.insert(0, client_dir)
            from gui_secure import main as gui_main
            print("✅ Запуск GUI из папки client...")
            gui_main()
        except ImportError as e2:
            print(f"❌ Ошибка импорта из папки client: {e2}")
            traceback.print_exc()
            input("Нажмите Enter для выхода...")
            sys.exit(1)

if __name__ == '__main__':
    main()