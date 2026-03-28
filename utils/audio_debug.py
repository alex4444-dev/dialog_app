# audio_debug.py
import sounddevice as sd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('audio_debug')

def check_audio_system():
    """Полная проверка аудио системы"""
    logger.info("🎵 ПОЛНАЯ ДИАГНОСТИКА АУДИО СИСТЕМЫ")
    
    try:
        # 1. Проверка устройств
        devices = sd.query_devices()
        logger.info(f"📊 Найдено устройств: {len(devices)}")
        
        if len(devices) == 0:
            logger.error("❌ Аудио устройства не найдены!")
            return False
        
        # 2. Информация об устройствах
        for i, device in enumerate(devices):
            logger.info(f"🔊 Устройство {i}: {device['name']}")
            logger.info(f"   - Входные каналы: {device['max_input_channels']}")
            logger.info(f"   - Выходные каналы: {device['max_output_channels']}")
            logger.info(f"   - Частота дискретизации: {device['default_samplerate']}")
        
        # 3. Устройства по умолчанию
        default_input = sd.default.device[0] if sd.default.device else None
        default_output = sd.default.device[1] if sd.default.device else None
        logger.info(f"🎯 Устройство ввода по умолчанию: {default_input}")
        logger.info(f"🎯 Устройство вывода по умолчанию: {default_output}")
        
        # 4. Тест воспроизведения
        logger.info("🔊 Тестирование воспроизведения...")
        try:
            duration = 2.0
            frequency = 440
            sample_rate = 44100
            
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * frequency * t)
            
            sd.play(tone, sample_rate)
            sd.wait()
            logger.info("✅ Воспроизведение работает")
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения: {e}")
            return False
        
        # 5. Тест записи
        logger.info("🎤 Тестирование записи...")
        try:
            duration = 1.0
            sample_rate = 44100
            
            recording = sd.rec(int(duration * sample_rate), 
                             samplerate=sample_rate, 
                             channels=1)
            sd.wait()
            logger.info(f"✅ Запись работает, записано {len(recording)} сэмплов")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка записи: {e}")
        
        logger.info("🎉 Диагностика завершена успешно!")
        return True
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка диагностики: {e}")
        return False

if __name__ == "__main__":
    check_audio_system()
