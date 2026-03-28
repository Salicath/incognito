from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # 64 MB
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32  # 256 bits
_SALT_LEN = 16
_NONCE_LEN = 12


def derive_key(
    password: str,
    salt: bytes | None = None,
    return_salt: bool = False,
) -> bytes | tuple[bytes, bytes]:
    if salt is None:
        salt = os.urandom(_SALT_LEN)

    key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        type=Type.ID,
    )

    if return_salt:
        return key, salt
    return key


@dataclass(frozen=True)
class EncryptedPayload:
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        return (
            struct.pack(">H", len(self.nonce))
            + self.nonce
            + self.ciphertext
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> EncryptedPayload:
        (nonce_len,) = struct.unpack(">H", data[:2])
        nonce = data[2 : 2 + nonce_len]
        ciphertext = data[2 + nonce_len :]
        return cls(nonce=nonce, ciphertext=ciphertext)


def encrypt(plaintext: bytes, key: bytes) -> EncryptedPayload:
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return EncryptedPayload(nonce=nonce, ciphertext=ciphertext)


def decrypt(payload: EncryptedPayload, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(payload.nonce, payload.ciphertext, None)
