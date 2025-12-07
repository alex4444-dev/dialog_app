#!/usr/bin/env python3
"""
Запуск всей системы ДИАЛОГ
"""

import subprocess
import sys
import os
import time
import threading

def run_command(command, name):
    """Запуск команды в отдельном потоке"""
    print(f"🚀 Запуск {name}...")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Чтение вывода в реальном времени
        def read_output():
            for line in process.stdout:
                print(f"[{name}] {line}", end='')
        
        def read_errors():
            for line in process.stderr:
                print(f"[{name} ERROR] {line}", end='')
        
        # Запускаем потоки для чтения вывода
        stdout_thread = threading.Thread(target=read_output, daemon=True)
        stderr_thread = threading.Thread(target=read_errors, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        return process
        
    except Exception as e:
        print(f"❌ Ошибка запуска {name}: {e}")
        return None

def main():
    """Главная функция"""
    print("=" * 50)
    print("🚀 ЗАПУСК СИСТЕМЫ ДИАЛОГ")
    print("=" * 50)
    
    processes = []
    
    try:
        # 1. Запуск бутстрап-сервера
        bootstrap_proc = run_command("python bootstrap_node.py", "bootstrap")
        if bootstrap_proc:
            processes.append(("bootstrap", bootstrap_proc))
        time.sleep(2)
        
        # 2. Запуск медиа-сервера
        media_proc = run_command("python simple_media_server.py --port 9100", "media")
        if media_proc:
            processes.append(("media", media_proc))
        time.sleep(2)
        
        # 3. Запуск теста медиа-сервера
        print("🔊 Тестирование медиа-сервера...")
        test_proc = subprocess.run(
            "python test_call.py",
            shell=True,
            capture_output=True,
            text=True
        )
        print(test_proc.stdout)
        if test_proc.stderr:
            print(f"⚠️ Предупреждения: {test_proc.stderr}")
        
        # 4. Инструкции для пользователя
        print("\n" + "=" * 50)
        print("✅ Система запущена!")
        print("\nИнструкции:")
        print("1. Запустите первый экземпляр приложения:")
        print("   python main.py --port 9000 --debug")
        print("\n2. Запустите второй экземпляр приложения:")
        print("   python main.py --port 9001 --debug")
        print("\n3. Зарегистрируйте двух пользователей")
        print("4. Найдите друг друга в списке пользователей")
        print("5. Откройте чат и нажмите кнопку звонка")
        print("=" * 50)
        
        # Ожидание завершения
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Остановка системы...")
            
    finally:
        # Остановка всех процессов
        for name, proc in processes:
            if proc.poll() is None:  # Если процесс еще работает
                print(f"🛑 Остановка {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        
        print("✅ Все процессы остановлены")

if __name__ == "__main__":
    main()