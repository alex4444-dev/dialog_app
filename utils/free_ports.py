# free_ports.py
import os
import subprocess
import signal

def free_ports(ports):
    """Освобождает указанные порты"""
    for port in ports:
        try:
            # Находим PID процесса, занимающего порт
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, 
                text=True
            )
            if result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"🛑 Завершаем процесс {pid} на порту {port}")
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"✅ Порт {port} освобожден")
            else:
                print(f"✅ Порт {port} свободен")
        except Exception as e:
            print(f"⚠️ Не удалось проверить порт {port}: {e}")

if __name__ == '__main__':
    ports_to_free = [8888, 8889, 8890, 8891, 8892, 8893, 8894, 8895]
    print("🧹 Освобождаем порты...")
    free_ports(ports_to_free)
    print("🎉 Готово!")