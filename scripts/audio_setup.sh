#!/bin/bash

# Настройка аудио системы для голосовых звонков

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

source venv/bin/activate

echo "🎧 Настройка аудио системы для звонков..."

python -c "
import sounddevice as sd
import numpy as np
import time

print('=== НАСТРОЙКА АУДИО СИСТЕМЫ ===')
print()

# Список аудио устройств
print('Доступные аудио устройства:')
devices = sd.query_devices()
for i, device in enumerate(devices):
    print(f'{i}: {device[\"name\"]}')
    print(f'   Входы: {device[\"max_input_channels\"]}, Выходы: {device[\"max_output_channels\"]}')
    print(f'   Частота: {device[\"default_samplerate\"]} Hz')
    print()

# Тест воспроизведения
print('=== ТЕСТ ВОСПРОИЗВЕДЕНИЯ ===')
try:
    duration = 2.0
    sample_rate = 44100
    frequency = 440
    
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    tone = 0.3 * np.sin(2 * np.pi * frequency * t)
    
    print('Воспроизведение тестового тона...')
    sd.play(tone, sample_rate)
    sd.wait()
    print('✅ Тест воспроизведения пройден')
except Exception as e:
    print(f'❌ Ошибка воспроизведения: {e}')

# Тест записи
print()
print('=== ТЕСТ ЗАПИСИ ===')
try:
    print('Запись в течение 3 секунд... (говорите в микрофон)')
    recording = sd.rec(int(3 * 44100), samplerate=44100, channels=1)
    sd.wait()
    
    # Анализ записи
    max_amplitude = np.max(np.abs(recording))
    print(f'Максимальная амплитуда: {max_amplitude:.4f}')
    
    if max_amplitude > 0.01:
        print('✅ Запись работает, сигнал обнаружен')
    else:
        print('⚠️ Запись работает, но сигнал очень слабый')
        
except Exception as e:
    print(f'❌ Ошибка записи: {e}')

print()
print('=== РЕКОМЕНДАЦИИ ===')
print('1. Для лучшего качества используйте внешний микрофон')
print('2. Проверьте уровни громкости в системных настройках')
print('3. Убедитесь, что правильные устройства выбраны по умолчанию')
"

echo "✅ Настройка аудио завершена"