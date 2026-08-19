"""
tests/test_cipher_engine.py
============================
Unit tests for the AES-256-GCM CipherEngine.
"""

import base64
import os
import pytest
import pyarrow as pa

# Generate a fresh 32-byte test key
_TEST_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()

# Patch the secrets manager to return the test key directly
import unittest.mock as mock

from veloctra_transformers.cipher_engine import CipherEngine


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("APP_TEST_CIPHER_KEY", _TEST_KEY)
    with mock.patch(
        "veloctra_transformers.cipher_engine.resolve_secret",
        return_value=_TEST_KEY,
    ):
        yield CipherEngine(key_ref="env:APP_TEST_CIPHER_KEY")



def test_encrypt_returns_string(engine):
    result = engine.encrypt("4111111111111111")
    assert isinstance(result, str)
    assert len(result) > 20


def test_encrypt_decrypt_roundtrip(engine):
    plaintext = "4111111111111111"
    encrypted = engine.encrypt(plaintext)
    decrypted = engine.decrypt(encrypted)
    assert decrypted == plaintext


def test_encrypt_different_values_produce_different_ciphertexts(engine):
    c1 = engine.encrypt("Hello")
    c2 = engine.encrypt("Hello")
    # Due to random nonce, same plaintext → different ciphertext
    assert c1 != c2


def test_decrypt_different_nonce_same_plaintext(engine):
    c1 = engine.encrypt("test")
    c2 = engine.encrypt("test")
    assert engine.decrypt(c1) == engine.decrypt(c2) == "test"


def test_encrypt_none_returns_none(engine):
    assert engine.encrypt(None) is None


def test_decrypt_none_returns_none(engine):
    assert engine.decrypt(None) is None


def test_encrypt_column(engine):
    col = pa.array(["4111111111111111", "5500005555555559", None])
    result = engine.encrypt_column(col)
    assert result[0] is not None
    assert result[2] is None


def test_decrypt_column(engine):
    originals = ["visa_number_001", "mastercard_002"]
    col = pa.array([engine.encrypt(v) for v in originals])
    decrypted = engine.decrypt_column(col)
    assert decrypted == originals



def test_encrypt_batch_fields(engine):
    batch = pa.RecordBatch.from_pydict({
        "name": ["Alice", "Bob"],
        "card_number": ["4111111111111111", "5500005555555559"],
        "amount": [100.0, 200.0],
    })
    result = engine.encrypt_batch_fields(batch, ["card_number"])
    # card_number should be encrypted (not the original)
    assert result.column("card_number")[0].as_py() != "4111111111111111"
    # name and amount should be untouched
    assert result.column("name")[0].as_py() == "Alice"
    assert result.column("amount")[0].as_py() == 100.0


def test_encrypt_decrypt_batch_roundtrip(engine):
    batch = pa.RecordBatch.from_pydict({
        "ssn": ["123-45-6789", "987-65-4321"],
        "name": ["Alice", "Bob"],
    })
    encrypted = engine.encrypt_batch_fields(batch, ["ssn"])
    decrypted = engine.decrypt_batch_fields(encrypted, ["ssn"])
    assert decrypted.column("ssn")[0].as_py() == "123-45-6789"
    assert decrypted.column("ssn")[1].as_py() == "987-65-4321"


def test_wrong_key_raises_on_decrypt():
    key1 = base64.urlsafe_b64encode(os.urandom(32)).decode()
    key2 = base64.urlsafe_b64encode(os.urandom(32)).decode()

    # Use plain-value refs (no env: prefix) so secrets_manager returns them directly
    with mock.patch("veloctra_transformers.cipher_engine.resolve_secret", return_value=key1):
        engine1 = CipherEngine("plain-key1")
        encrypted = engine1.encrypt("secret-data")

    with mock.patch("veloctra_transformers.cipher_engine.resolve_secret", return_value=key2):
        engine2 = CipherEngine("plain-key2")
        with pytest.raises(Exception):  # cryptography.exceptions.InvalidTag
            engine2.decrypt(encrypted)

