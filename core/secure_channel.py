# secure_channel.py

import socket
import struct
import threading
import logging
from core.crypto import CryptoManager

logger = logging.getLogger('secure_channel')

class SecureChannel:
    def __init__(self, sock: socket.socket, crypto: CryptoManager):
        self.sock = sock
        self.crypto = crypto
        self._recv_buffer = b''
        self._closed = False
        self.sock.settimeout(None)

    def settimeout(self, timeout: float):
        self.sock.settimeout(timeout)

    def send(self, data: bytes):
        if self._closed:
            raise ConnectionError("Канал закрыт")
        try:
            encrypted = self.crypto.encrypt_packet(data)
            packet = struct.pack('!I', len(encrypted)) + encrypted
            self.sock.sendall(packet)
        except OSError as e:
            if e.errno == 9:  # Bad file descriptor
                self._closed = True
                raise ConnectionError("Сокет закрыт") from e
            raise
        except Exception as e:
            self._closed = True
            raise ConnectionError("Ошибка отправки") from e

    def recv(self) -> bytes:
        if self._closed:
            raise ConnectionError("Канал закрыт")
        try:
            while len(self._recv_buffer) < 4:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Соединение закрыто")
                self._recv_buffer += chunk
            pkt_len = struct.unpack('!I', self._recv_buffer[:4])[0]
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
        except OSError as e:
            if e.errno == 9:
                self._closed = True
                raise ConnectionError("Сокет закрыт") from e
            raise
        except Exception as e:
            self._closed = True
            raise ConnectionError("Ошибка приёма") from e

    def close(self):
        self._closed = True
        self.sock.close()