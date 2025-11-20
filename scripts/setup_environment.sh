#!/bin/bash

# Настройка системного окружения для "Диалог"

echo "🔧 Настройка окружения для мессенджера Диалог..."

# Проверка и настройка аудио
setup_audio() {
    echo "🔊 Настройка аудио системы..."
    
    # Проверка PulseAudio/PipeWire
    if pactl info &> /dev/null; then
        echo "✅ PulseAudio обнаружен"
    else
        echo "❌ PulseAudio не запущен"
        echo "Запустите: pulseaudio --start"
    fi
    
    # Проверка доступных аудио устройств
    if command -v arecord &> /dev/null; then
        echo "Доступные аудио устройства:"
        arecord -l | head -10
    fi
}

# Настройка файрвола
setup_firewall() {
    echo "🔥 Настройка файрвола для P2P..."
    
    # Запрос на открытие портов
    read -p "Открыть порт 8888 для P2P соединений? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v ufw &> /dev/null; then
            sudo ufw allow 8888/tcp
            echo "✅ Порт 8888 открыт в ufw"
        elif command -v firewall-cmd &> /dev/null; then
            sudo firewall-cmd --add-port=8888/tcp --permanent
            sudo firewall-cmd --reload
            echo "✅ Порт 8888 открыт в firewalld"
        else
            echo "⚠️ Не удалось настроить файрвол (ufw или firewalld не найден)"
        fi
    fi
}

# Настройка автозапуска
setup_autostart() {
    echo "🔌 Настройка автозапуска..."
    
    read -p "Добавить в автозагрузку? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        AUTOSTART_DIR="$HOME/.config/autostart"
        mkdir -p "$AUTOSTART_DIR"
        
        cat > "$AUTOSTART_DIR/dialog-messenger.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Диалог Мессенджер
Exec=$PWD/scripts/start_client.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
        
        echo "✅ Автозагрузка настроена"
    fi
}

main() {
    setup_audio
    setup_firewall
    setup_autostart
    
    echo ""
    echo "✅ Настройка окружения завершена"
}

main "$@"