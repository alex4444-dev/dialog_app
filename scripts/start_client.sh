#!/bin/bash

# Скрипт запуска клиента "Диалог"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Активация виртуального окружения
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "❌ Виртуальное окружение не найдено. Запустите install.sh"
    exit 1
fi

# Проверка конфигурации
if [ ! -f "config.yaml" ]; then
    echo "⚠️ Конфигурационный файл не найден. Создаю из примера..."
    cp config.example.yaml config.yaml
fi

# Проверка Python скрипта
if [ ! -f "main.py" ]; then
    echo "❌ Основной скрипт не найден"
    exit 1
fi

echo "🚀 Запуск мессенджера Диалог..."
echo "📁 Рабочий каталог: $PROJECT_ROOT"
echo "🐍 Python: $(python --version)"

# Запуск приложения
python main.py

# Обработка выхода
deactivate
echo "👋 Клиент завершил работу"