#!/bin/bash

# Восстановление базы данных из резервной копии

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/data/backups"

cd "$PROJECT_ROOT"

source venv/bin/activate

echo "🔄 Восстановление базы данных..."

# Показать доступные резервные копии
echo "Доступные резервные копии:"
ls -lt "$BACKUP_DIR"/dialog_backup_*.db 2>/dev/null | head -10

if [ $? -ne 0 ]; then
    echo "❌ Резервные копии не найдены"
    exit 1
fi

read -p "Введите имя файла для восстановления: " backup_file

if [ ! -f "$BACKUP_DIR/$backup_file" ]; then
    echo "❌ Файл не найден: $backup_file"
    exit 1
fi

# Создание резервной копии текущей БД
if [ -f "data/client.db" ]; then
    cp "data/client.db" "data/client.db.backup_$(date +%s)"
fi

# Восстановление
cp "$BACKUP_DIR/$backup_file" "data/client.db"

if [ $? -eq 0 ]; then
    echo "✅ База данных восстановлена из: $backup_file"
else
    echo "❌ Ошибка восстановления базы данных"
    exit 1
fi