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