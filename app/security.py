import base64
import hashlib
import json
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from app.config import settings

# Argon2id: 64 MiB, three iterations, four lanes; fresh 128-bit salt per password.
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, salt_len=16, hash_len=32)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def password_hash(password):
    return hasher.hash(password)


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_token():
    return secrets.token_urlsafe(32)


def cipher():
    key = hashlib.sha256(('outbox:' + settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_payload(payload):
    return cipher().encrypt(json.dumps(payload).encode()).decode()


def decrypt_payload(payload):
    return json.loads(cipher().decrypt(payload.encode()))
