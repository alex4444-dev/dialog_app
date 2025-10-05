from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import os
import json

class CryptoManager:
    def __init__(self):
        self.private_key = None
        self.public_key = None
        self.other_public_key = None
        self.symmetric_key = None
        
    def generate_key_pair(self):
        """Генерация RSA ключевой пары"""
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
    
    def serialize_public_key(self):
        """Сериализация публичного ключа в строку"""
        if not self.public_key:
            return None
            
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    def deserialize_public_key(self, key_str):
        """Десериализация публичного ключа из строки"""
        try:
            self.other_public_key = serialization.load_pem_public_key(
                key_str.encode('utf-8'),
                backend=default_backend()
            )
            return True
        except Exception as e:
            print(f"Error loading public key: {e}")
            return False
    
    def generate_symmetric_key(self):
        """Генерация симметричного ключа для AES"""
        return os.urandom(32)  # 256-bit key
    
    def encrypt_symmetric_key(self, symmetric_key):
        """Шифрование симметричного ключа RSA публичным ключом получателя"""
        if not self.other_public_key:
            raise Exception("No public key available for encryption")
            
        encrypted_key = self.other_public_key.encrypt(
            symmetric_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return encrypted_key
    
    def decrypt_symmetric_key(self, encrypted_key):
        """Расшифровка симметричного ключа RSA приватным ключом"""
        if not self.private_key:
            raise Exception("No private key available for decryption")
            
        decrypted_key = self.private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted_key
    
    def encrypt_message(self, message, key=None):
        """Шифрование сообщения AES-GCM"""
        if key is None:
            if self.symmetric_key is None:
                raise Exception("No symmetric key available")
            key = self.symmetric_key
        
        # Генерация случайного nonce
        nonce = os.urandom(12)
        
        # Создание шифра
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Шифрование сообщения
        ciphertext = encryptor.update(message.encode('utf-8')) + encryptor.finalize()
        
        # Получение authentication tag
        tag = encryptor.tag
        
        # Кодирование в base64 для передачи
        encrypted_data = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8')
        }
        
        return json.dumps(encrypted_data)
    
    def decrypt_message(self, encrypted_data_json, key=None):
        """Расшифровка сообщения AES-GCM"""
        if key is None:
            if self.symmetric_key is None:
                raise Exception("No symmetric key available")
            key = self.symmetric_key
        
        try:
            encrypted_data = json.loads(encrypted_data_json)
            
            # Декодирование из base64
            nonce = base64.b64decode(encrypted_data['nonce'])
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            tag = base64.b64decode(encrypted_data['tag'])
            
            # Создание дешифратора
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(nonce, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Расшифровка сообщения
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext.decode('utf-8')
            
        except Exception as e:
            print(f"Decryption error: {e}")
            return None
    
    def establish_secure_session(self, other_public_key_str):
        """Установление безопасной сессии с обменом ключами"""
        # Загрузка публичного ключа собеседника
        if not self.deserialize_public_key(other_public_key_str):
            return False
        
        # Генерация симметричного ключа
        self.symmetric_key = self.generate_symmetric_key()
        
        # Шифрование симметричного ключа для отправки
        encrypted_symmetric_key = self.encrypt_symmetric_key(self.symmetric_key)
        
        return base64.b64encode(encrypted_symmetric_key).decode('utf-8')
    
    def complete_secure_session(self, encrypted_symmetric_key_b64):
        """Завершение установления безопасной сессии"""
        try:
            encrypted_symmetric_key = base64.b64decode(encrypted_symmetric_key_b64)
            self.symmetric_key = self.decrypt_symmetric_key(encrypted_symmetric_key)
            return True
        except Exception as e:
            print(f"Session establishment failed: {e}")
            return False