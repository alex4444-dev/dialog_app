# secure_channel.py

import socket
import struct
import threading
import logging
from crypto import CryptoManager

logger = logging.getLogger('secure_channel')

class SecureChannel:
    def __init__(self, sock: socket.socket, crypto: CryptoManager):
        self.sock = sock
        self.crypto = crypto
        self._recv_buffer = b''
        self._closed = False
        # Устанавливаем таймаут по умолчанию (можно будет изменить через settimeout)
        self.sock.settimeout(None)

    def settimeout(self, timeout: float):
        """Устанавливает таймаут для внутреннего сокета."""
        self.sock.settimeout(timeout)

    def send(self, data: bytes):
        if self._closed:
            raise ConnectionError("Канал закрыт")
        encrypted = self.crypto.encrypt_packet(data)
        packet = struct.pack('!I', len(encrypted)) + encrypted
        self.sock.sendall(packet)

    def recv(self) -> bytes:
        """Принимает один полный пакет (без аргумента timeout, таймаут задан ранее)."""
        try:
            # Читаем длину пакета
            while len(self._recv_buffer) < 4:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Соединение закрыто")
                self._recv_buffer += chunk
            pkt_len = struct.unpack('!I', self._recv_buffer[:4])[0]
            # Читаем весь пакет
            while len(self._recv_buffer) < 4 + pkt_len:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Соединение закрыто")
                self._recv_buffer += chunk
            encrypted = self._recv_buffer[4:4+pkt_len]
            self._recv_buffer = self._recv_buffer[4+pkt_len:]
            return self.crypto.decrypt_packet(encrypted)
        except socket.timeout:
            raise   # пробрасываем выше для обработки
        except Exception as e:
            logger.error(f"Ошибка приёма: {e}")
            self.close()
            raise

    def close(self):
        self._closed = True
        self.sock.close()