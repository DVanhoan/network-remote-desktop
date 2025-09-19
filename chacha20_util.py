from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for ChaCha20")
    if len(nonce) != 12:
        raise ValueError("Nonce must be 12 bytes for ChaCha20")

    algorithm = algorithms.ChaCha20(key, nonce)
    cipher = Cipher(algorithm, mode=None, backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    return ciphertext

def decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for ChaCha20")
    if len(nonce) != 12:
        raise ValueError("Nonce must be 12 bytes for ChaCha20")

    algorithm = algorithms.ChaCha20(key, nonce)
    cipher = Cipher(algorithm, mode=None, backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext