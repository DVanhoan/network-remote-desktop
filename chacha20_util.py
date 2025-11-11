from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def encrypt(key: str, nonce: str, plaintext: bytes) -> bytes:
    try:
        key = key.encode('utf-8')
        nonce = nonce.encode('utf-8')

        if len(key) != 32:
            raise ValueError("Key must be 32 bytes for ChaCha20")
        if len(nonce) != 16:
            raise ValueError("Nonce must be 16 bytes for ChaCha20")

        algorithm = algorithms.ChaCha20(key, nonce)
        cipher = Cipher(algorithm, mode=None, backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()

        return ciphertext
    except Exception as e:
        print(f"Lỗi khi mã hóa dữ liệu: {e}")
        return b''

def decrypt(key: str, nonce: str, ciphertext: bytes) -> bytes:
    key = key.encode('utf-8')
    nonce = nonce.encode('utf-8')

    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for ChaCha20")
    if len(nonce) != 16:
        raise ValueError("Nonce must be 16 bytes for ChaCha20")

    algorithm = algorithms.ChaCha20(key, nonce)
    cipher = Cipher(algorithm, mode=None, backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext