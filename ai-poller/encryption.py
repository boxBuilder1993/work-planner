"""AES-256-GCM encryption compatible with WorkPlanner web and Android apps.

Key derivation: PBKDF2-HMAC-SHA256, 210,000 iterations, 16-byte salt -> 32-byte key.
Encrypt format: [IV (12 bytes)][ciphertext + auth tag (16 bytes)].
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

PBKDF2_ITERATIONS = 210_000
KEY_LENGTH_BYTES = 32
SALT_LENGTH_BYTES = 16
IV_LENGTH_BYTES = 12


def generate_salt() -> bytes:
    return os.urandom(SALT_LENGTH_BYTES)


def derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH_BYTES,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt(plain_bytes: bytes, key: bytes) -> bytes:
    iv = os.urandom(IV_LENGTH_BYTES)
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(iv, plain_bytes, None)
    return iv + ciphertext_and_tag


def decrypt(encrypted_bytes: bytes, key: bytes) -> bytes:
    iv = encrypted_bytes[:IV_LENGTH_BYTES]
    ciphertext_and_tag = encrypted_bytes[IV_LENGTH_BYTES:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext_and_tag, None)
