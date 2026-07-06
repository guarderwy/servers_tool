"""AES-256-GCM 加密/解密实现"""

import os
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def derive_key(password: str, salt: bytes) -> bytes:
    """通过 PBKDF2 从主密码派生 AES 密钥"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_data(data: str, password: str) -> str:
    """
    加密数据，返回 base64 编码的字符串。
    格式: base64(salt + nonce + ciphertext)
    """
    salt = os.urandom(16)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data.encode("utf-8"), None)
    return base64.b64encode(salt + nonce + ciphertext).decode("ascii")


def decrypt_data(encrypted_b64: str, password: str) -> str:
    """
    解密 base64 编码的加密数据。
    失败时抛出异常。
    """
    raw = base64.b64decode(encrypted_b64)
    salt = raw[:16]
    nonce = raw[16:28]
    ciphertext = raw[28:]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def encrypt_json(data: dict, password: str) -> str:
    """加密 JSON 对象"""
    return encrypt_data(json.dumps(data, ensure_ascii=False), password)


def decrypt_json(encrypted_b64: str, password: str) -> dict:
    """解密为 JSON 对象"""
    return json.loads(decrypt_data(encrypted_b64, password))
