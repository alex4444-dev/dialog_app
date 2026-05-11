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

    def send(self, data: bytes):
        """Отправляет данные, предварительно шифруя."""
        if self._closed:
            raise ConnectionError("Канал закрыт")
        encrypted = self.crypto.encrypt_packet(data)
        # добавляем длину пакета
        packet = struct.pack('!I', len(encrypted)) + encrypted
        self.sock.sendall(packet)

    def recv(self, timeout: float = None) -> bytes:
        """Принимает один полный пакет, расшифровывает и возвращает."""
        if timeout is not None:
            self.sock.settimeout(timeout)
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
            raise
        except Exception as e:
            logger.error(f"Ошибка приёма: {e}")
            self.close()
            raise

    def close(self):
        self._closed = True
        self.sock.close()