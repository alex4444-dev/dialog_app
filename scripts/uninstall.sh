#!/bin/bash

# Удаление мессенджера "Диалог"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🗑️  Удаление мессенджера Диалог..."

read -p "Вы уверены, что хотите удалить приложение? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Удаление отменено"
    exit 0
fi

# Удаление виртуального окружения
if [ -d "venv" ]; then
    echo "Удаление виртуального окружения..."
    rm -rf venv
fi

# Удаление кэша и временных файлов
echo "Удаление временных файлов..."
rm -rf __pycache__
rm -rf src/__pycache__
rm -rf *.log

# Вопрос о сохранении данных
read -p "Сохранить данные пользователя (базу данных, ключи, настройки)? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Удаление пользовательских данных..."
    rm -rf data
    rm -f config.yaml
else
    echo "Пользовательские данные сохранены в каталоге data/"
fi

echo ""
echo "✅ Удаление завершено"
echo ""
echo "Примечание: Python пакеты, установленные системно, не удаляются."
echo "Для полной очистки выполните: pip freeze | grep -E '(pyqt|sounddevice|cryptography)' | xargs pip uninstall -y"