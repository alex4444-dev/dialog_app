"""
Конфигурационные настройки мессенджера Диалог
"""

import os
from typing import List, Dict

# Базовые настройки приложения
APP_CONFIG = {
    'name': 'Диалог Мессенджер',
    'version': '1.0.0',
    'description': 'Защищенный мессенджер с P2P звонками',
    'author': 'Dialog Team',
    'license': 'MIT'
}

# Настройки сети
NETWORK_CONFIG = {
    'server_host': 'localhost',
    'server_port': 12345,
    'p2p_port_range': (50000, 51000),  # Диапазон портов для P2P соединений
    'socket_timeout': 10,
    'buffer_size': 4096
}

# Российские STUN-серверы (приоритетные)
RUSSIAN_STUN_SERVERS = [
    ('stun.1cbit.ru', 3478),          # 1C-Bitrix
    ('stun.agava.ru', 3478),          # Agava
    ('stun.sibnet.ru', 3478),         # Sibnet
    ('stun.yandex.ru', 3478),         # Yandex
    ('stun.megafon.ru', 3478),        # Мегафон
    ('stun.mts.ru', 3478),            # МТС
    ('stun.beeline.ru', 3478),        # Билайн
    ('stun.rt.ru', 3478),             # Ростелеком
]

# Международные STUN-серверы (резервные)
INTERNATIONAL_STUN_SERVERS = [
    ('stun.l.google.com', 19302),
    ('stun1.l.google.com', 19302),
    ('stun2.l.google.com', 19302),
    ('stun3.l.google.com', 19302),
    ('stun4.l.google.com', 19302),
    ('stun.voipbuster.com', 3478),
    ('stun.voipstunt.com', 3478)
]

# Все STUN-серверы (российские приоритетнее)
STUN_SERVERS = RUSSIAN_STUN_SERVERS + INTERNATIONAL_STUN_SERVERS

# Российские TURN-серверы
RUSSIAN_TURN_SERVERS = [
    {
        'urls': [
            'turn:turn.agava.ru:3478?transport=udp',
            'turn:turn.agava.ru:3478?transport=tcp'
        ],
        'username': 'agava_username',  # Требует регистрации на agava.ru
        'credential': 'agava_password',
        'provider': 'Agava'
    },
    {
        'urls': [
            'turn:turn.yandex.ru:3478?transport=udp',
            'turn:turn.yandex.ru:3478?transport=tcp'
        ],
        'username': 'anonymous',
        'credential': 'anonymous',
        'provider': 'Yandex'
    }
]

# Международные TURN-серверы (резервные)
INTERNATIONAL_TURN_SERVERS = [
    {
        'urls': [
            'turn:global.turn.twilio.com:3478?transport=udp',
            'turn:global.turn.twilio.com:3478?transport=tcp'
        ],
        'username': 'twilio_username',  # Требует регистрации на twilio.com
        'credential': 'twilio_password',
        'provider': 'Twilio'
    },
    {
        'urls': [
            'turn:numb.viagenie.ca:3478?transport=udp',
            'turn:numb.viagenie.ca:3478?transport=tcp'
        ],
        'username': 'free_username',  # Бесплатный сервер
        'credential': 'free_password',
        'provider': 'Viagenie'
    }
]

# Все TURN-серверы
TURN_SERVERS = RUSSIAN_TURN_SERVERS + INTERNATIONAL_TURN_SERVERS

# Настройки базы данных
DATABASE_CONFIG = {
    'path': 'users.db',
    'timeout': 30,
    'check_same_thread': False
}

# Настройки шифрования
ENCRYPTION_CONFIG = {
    'key_size': 2048,
    'aes_key_length': 32,  # 256-bit
    'nonce_length': 12,
    'hash_algorithm': 'sha256',
    'encryption_mode': 'AES-GCM'
}

# Настройки аудио
AUDIO_CONFIG = {
    'sample_rate': 44100,
    'channels': 1,
    'chunk_size': 1024,
    'format': 8,  # pyaudio.paInt16
    'silence_threshold': 500
}

# Настройки видео
VIDEO_CONFIG = {
    'width': 640,
    'height': 480,
    'fps': 30,
    'codec': 'H264',
    'bitrate': 500000
}

# Настройки логирования
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'dialog.log',
    'max_size': 10485760,  # 10 MB
    'backup_count': 5
}

# Пути к файлам
PATHS = {
    'logs': 'logs',
    'downloads': 'downloads',
    'config': 'config',
    'cache': '.cache'
}

def get_stun_servers() -> List[tuple]:
    """Получение списка STUN-серверов"""
    return STUN_SERVERS

def get_turn_servers() -> List[Dict]:
    """Получение списка TURN-серверов"""
    return TURN_SERVERS

def get_turn_credentials(provider: str = None) -> Dict:
    """Получение учетных данных TURN-сервера"""
    if provider:
        for server in TURN_SERVERS:
            if server['provider'] == provider:
                return server
    return TURN_SERVERS[0] if TURN_SERVERS else None

# Создаем необходимые директории
for path in PATHS.values():
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

if __name__ == "__main__":
    print(f"{APP_CONFIG['name']} v{APP_CONFIG['version']}")
    print(f"STUN серверов: {len(STUN_SERVERS)}")
    print(f"TURN серверов: {len(TURN_SERVERS)}")
    print("Конфигурация загружена успешно")