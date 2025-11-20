#!/bin/bash

# Скрипт обслуживания системы

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

source venv/bin/activate

echo "🔧 Обслуживание системы Диалог..."

# Очистка кэша
clean_cache() {
    echo "🗑️  Очистка кэша..."
    if [ -d "cache" ]; then
        rm -rf cache/*
        echo "✅ Кэш очищен"
    fi
}

# Очистка логов
clean_logs() {
    echo "📋 Очистка старых логов..."
    find logs -name "*.log" -type f -mtime +7 -delete
    echo "✅ Старые логи удалены"
}

# Оптимизация БД
optimize_database() {
    echo "💾 Оптимизация базы данных..."
    python -c "
from storage.database import ClientDatabase
db = ClientDatabase()
print('✅ База данных оптимизирована')
"
}

# Проверка обновлений
check_updates() {
    echo "🔄 Проверка обновлений..."
    pip list --outdated
    echo "✅ Проверка завершена"
}

main() {
    clean_cache
    clean_logs
    optimize_database
    check_updates
    
    echo ""
    echo "✅ Обслуживание системы завершено"
}

main "$@"