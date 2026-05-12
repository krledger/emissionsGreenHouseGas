"""
crypto_utils.py
===============
Simple passphrase-based file encryption using Fernet (AES-128-CBC).

The passphrase is used to derive a key via PBKDF2.  A random salt is
generated per encryption and stored as the first 16 bytes of the
output file.  The remainder is the Fernet token.

Usage:
    from crypto_utils import encrypt_file, decrypt_file

    encrypt_file("data.csv", "data.csv.enc", passphrase="secret")
    decrypt_file("data.csv.enc", passphrase="secret")  -> bytes

Last updated: 2026-05-12
"""

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


SALT_LENGTH = 16
KDF_ITERATIONS = 480_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from a passphrase and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def encrypt_file(src_path: str, dst_path: str, passphrase: str):
    """Encrypt a file and write salt + ciphertext to dst_path."""
    salt = os.urandom(SALT_LENGTH)
    key = _derive_key(passphrase, salt)
    f = Fernet(key)

    with open(src_path, "rb") as fh:
        plaintext = fh.read()

    token = f.encrypt(plaintext)

    with open(dst_path, "wb") as fh:
        fh.write(salt + token)


def decrypt_file(enc_path: str, passphrase: str) -> bytes:
    """Decrypt an encrypted file and return the plaintext bytes."""
    with open(enc_path, "rb") as fh:
        data = fh.read()

    salt = data[:SALT_LENGTH]
    token = data[SALT_LENGTH:]
    key = _derive_key(passphrase, salt)
    f = Fernet(key)

    return f.decrypt(token)


def decrypt_to_file(enc_path: str, dst_path: str, passphrase: str):
    """Decrypt an encrypted file and write plaintext to dst_path."""
    plaintext = decrypt_file(enc_path, passphrase)
    with open(dst_path, "wb") as fh:
        fh.write(plaintext)
