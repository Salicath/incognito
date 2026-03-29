
import cryptography.exceptions
import pytest

from backend.core.crypto import EncryptedPayload, decrypt, derive_key, encrypt


def test_derive_key_deterministic():
    key1 = derive_key("password123", salt=b"fixed_salt_16byt")
    key2 = derive_key("password123", salt=b"fixed_salt_16byt")
    assert key1 == key2
    assert len(key1) == 32  # 256 bits


def test_derive_key_different_passwords():
    key1 = derive_key("password1", salt=b"fixed_salt_16byt")
    key2 = derive_key("password2", salt=b"fixed_salt_16byt")
    assert key1 != key2


def test_encrypt_decrypt_roundtrip():
    key = derive_key("my_password", salt=b"fixed_salt_16byt")
    plaintext = b'{"name": "Test User", "email": "test@example.com"}'

    payload = encrypt(plaintext, key)
    assert isinstance(payload, EncryptedPayload)

    decrypted = decrypt(payload, key)
    assert decrypted == plaintext


def test_decrypt_wrong_key_fails():
    key1 = derive_key("correct_password", salt=b"fixed_salt_16byt")
    key2 = derive_key("wrong_password", salt=b"other_salt_16byt")
    plaintext = b"secret data"

    payload = encrypt(plaintext, key1)

    with pytest.raises(cryptography.exceptions.InvalidTag):
        decrypt(payload, key2)


def test_encrypted_payload_serialization():
    key = derive_key("password", salt=b"fixed_salt_16byt")
    plaintext = b"test data"

    payload = encrypt(plaintext, key)
    serialized = payload.to_bytes()
    restored = EncryptedPayload.from_bytes(serialized)

    decrypted = decrypt(restored, key)
    assert decrypted == plaintext


def test_derive_key_generates_salt():
    key1, salt1 = derive_key("password", return_salt=True)
    key2, salt2 = derive_key("password", return_salt=True)
    assert salt1 != salt2  # random salt each time
    assert len(salt1) == 16
