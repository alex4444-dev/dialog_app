#!/bin/bash

# Резервное копирование базы данных

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/data/backups"

cd "$PROJECT_ROOT"

source venv/bin/activate

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/dialog_backup_$TIMESTAMP.db"

mkdir -p "$BACKUP_DIR"

echo "💾 Резервное копирование базы данных..."

if [ -f "data/client.db" ]; then
    cp "data/client.db" "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        echo "✅ Резервная копия создана: $BACKUP_FILE"
        
        # Очистка старых резервных копий (оставляем последние 10)
        ls -t "$BACKUP_DIR"/dialog_backup_*.db | tail -n +11 | xargs -r rm
        echo "🗑️  Старые резервные копии очищены"
    else
        echo "❌ Ошибка создания резервной копии"
        exit 1
    fi
else
    echo "⚠️ Файл базы данных не найден"
fi