import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger('dialog_calls')

class CallManager:
    """Менеджер для управления состоянием звонков"""
    
    def __init__(self):
        self.active_calls = {}
        self.call_lock = threading.Lock()
        self.call_timeouts = {}  # Для отслеживания таймаутов звонков
        
    def add_call(self, call_id, call_data):
        """Добавление звонка"""
        with self.call_lock:
            self.active_calls[call_id] = {
                **call_data,
                'created_at': datetime.now(),
                'last_activity': datetime.now(),
                'status': 'ringing'
            }
            logger.info(f"Добавлен звонок {call_id}")
            
    def update_call_status(self, call_id, status):
        """Обновление статуса звонка"""
        with self.call_lock:
            if call_id in self.active_calls:
                self.active_calls[call_id]['status'] = status
                self.active_calls[call_id]['last_activity'] = datetime.now()
                logger.debug(f"Обновлен статус звонка {call_id}: {status}")
                
    def remove_call(self, call_id):
        """Удаление звонка"""
        with self.call_lock:
            if call_id in self.active_calls:
                del self.active_calls[call_id]
                logger.info(f"Удален звонок {call_id}")
                return True
            return False
            
    def get_call(self, call_id):
        """Получение информации о звонке"""
        with self.call_lock:
            return self.active_calls.get(call_id)
            
    def get_call_socket(self, call_id: str):
        """Получение сокета для звонка"""
        try:
            # Пытаемся получить медиа-сокет
            if call_id in self.media_sockets:
                media_socket = self.media_sockets[call_id]
                # Проверяем, что сокет работает
                try:
                    media_socket.send(b'')  # Тестовая отправка
                    logger.info(f"✅ Медиа-сокет для звонка {call_id} проверен")
                    return media_socket
                except:
                    logger.warning(f"⚠️ Медиа-сокет для звонка {call_id} не работает")
            
            # Если медиа-сокета нет, создаем новое прямое подключение
            logger.info(f"🔧 Создание прямого сокета для звонка {call_id}")
            
            # Создаем сокет для звонка
            call_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            call_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            call_socket.settimeout(5.0)
            
            # Находим свободный порт для звонка
            call_port = self._find_free_call_port()
            if not call_port:
                logger.error(f"❌ Не удалось найти свободный порт для звонка {call_id}")
                return None
        
            # Привязываем сокет
            call_socket.bind(('0.0.0.0', call_port))
            call_socket.listen(1)
            call_socket.settimeout(10.0)
        
            # Сохраняем информацию о сокете
            self.media_sockets[call_id] = call_socket
            
            logger.info(f"✅ Создан сокет для звонка {call_id} на порту {call_port}")
            return call_socket
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сокета для звонка: {e}")
            return None

    def _find_free_call_port(self):
        """Найти свободный порт для звонка"""
        for port in range(9200, 9500):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('0.0.0.0', port))
                    return port
            except:
                continue
        return None


    def is_call_active(self, call_id):
        """Проверка активности звонка"""
        with self.call_lock:
            return call_id in self.active_calls
            
    def cleanup_stalled_calls(self, timeout_seconds=300):
        """Очистка зависших звонков"""
        with self.call_lock:
            current_time = datetime.now()
            stalled_calls = []
            
            for call_id, call_data in self.active_calls.items():
                time_diff = (current_time - call_data['last_activity']).total_seconds()
                if time_diff > timeout_seconds:
                    stalled_calls.append(call_id)
            
            for call_id in stalled_calls:
                logger.warning(f"Удаляем зависший звонок {call_id}")
                del self.active_calls[call_id]
                
            return stalled_calls

# Глобальный менеджер звонков
call_manager = CallManager()

def setup_call_cleanup_thread(interval=60):
    """Запуск фонового потока для очистки звонков"""
    def cleanup_worker():
        while True:
            try:
                stalled = call_manager.cleanup_stalled_calls()
                if stalled:
                    logger.info(f"Очищено зависших звонков: {len(stalled)}")
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Ошибка в cleanup_worker: {e}")
                time.sleep(interval)
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    logger.info("Запущен поток очистки звонков")