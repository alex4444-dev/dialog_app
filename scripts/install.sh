#!/bin/bash

# Скрипт установки мессенджера "Диалог"
set -e

echo "🚀 Установка мессенджера Диалог..."

# Проверка зависимостей
check_dependencies() {
    echo "🔍 Проверка зависимостей..."
    
    # Проверка Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python3 не установлен"
        exit 1
    fi
    
    # Проверка pip
    if ! command -v pip3 &> /dev/null; then
        echo "❌ pip3 не установлен"
        exit 1
    fi
    
    echo "✅ Зависимости проверены"
}

# Создание виртуального окружения
setup_venv() {
    echo "🐍 Создание виртуального окружения..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    echo "✅ Виртуальное окружение создано"
}

# Установка Python пакетов
install_packages() {
    echo "📦 Установка Python пакетов..."
    
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Дополнительные аудио пакеты
    pip install sounddevice
    pip install numpy
    
    echo "✅ Пакеты установлены"
}

# Создание структуры каталогов
create_directories() {
    echo "📁 Создание структуры каталогов..."
    
    mkdir -p data
    mkdir -p data/keys
    mkdir -p data/backups
    mkdir -p logs
    mkdir -p cache
    
    echo "✅ Каталоги созданы"
}

# Настройка конфигурации
setup_config() {
    echo "⚙️ Настройка конфигурации..."
    
    if [ ! -f "config.yaml" ]; then
        cp config.example.yaml config.yaml
        echo "✅ Конфигурационный файл создан"
    else
        echo "⚠️ Конфигурационный файл уже существует"
    fi
}

# Генерация ключей безопасности
generate_keys() {
    echo "🔑 Генерация ключей безопасности..."
    
    if [ ! -f "data/keys/private_key.pem" ]; then
        ./scripts/generate_keys.sh
    else
        echo "⚠️ Ключи уже существуют"
    fi
}

# Основная процедура установки
main() {
    echo "=========================================="
    echo "   Установка мессенджера 'Диалог'"
    echo "=========================================="
    
    check_dependencies
    setup_venv
    install_packages
    create_directories
    setup_config
    generate_keys
    
    echo ""
    echo "🎉 Установка завершена!"
    echo ""
    echo "Для запуска выполните:"
    echo "  ./scripts/start_client.sh"
    echo ""
    echo "Для настройки аудио:"
    echo "  ./scripts/audio_setup.sh"
    echo ""
}

main "$@"