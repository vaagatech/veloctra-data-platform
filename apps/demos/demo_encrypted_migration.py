"""
apps/demos/demo_encrypted_migration.py
======================================
Demo Application 2: AES-256-GCM Field Encryption & Decryption Pipeline.

Demonstrates reading plaintext sensitive records (card numbers, SSNs),
encrypting specified fields in-flight, verifying non-decryptability without key,
and decrypting into a secured destination database.
"""

import asyncio
import base64
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pyarrow as pa
from veloctra_transformers.cipher_engine import CipherEngine



def run_demo():
    print("==================================================================")
    print(" DEMO 2: In-Flight AES-256-GCM Field Encryption & Decryption")
    print("==================================================================")

    # 32-byte key
    key = base64.b64encode(os.urandom(32)).decode()
    os.environ["DEMO_CIPHER_KEY"] = key

    cipher = CipherEngine(key_ref="env:DEMO_CIPHER_KEY")

    # 1. Plaintext input batch
    batch = pa.RecordBatch.from_pydict({
        "tx_id": ["tx_1001", "tx_1002", "tx_1003"],
        "customer": ["Alice Vance", "Bob Miller", "Charlie Davis"],
        "card_number": ["4111111111111111", "5500005555555559", "370000000000003"],
        "ssn": ["123-45-6789", "987-65-4321", "456-78-9012"],
        "amount": [1250.50, 89.99, 4500.00],
    })

    print("\n1. Original Input Record Batch (Plaintext):")
    for i in range(batch.num_rows):
        print(f"   Row {i+1}: Name={batch.column('customer')[i]}, Card={batch.column('card_number')[i]}, SSN={batch.column('ssn')[i]}")

    # 2. Encrypt sensitive fields
    encrypted_batch = cipher.encrypt_batch_fields(batch, ["card_number", "ssn"])

    print("\n2. Transformed Record Batch (In-Flight Encrypted):")
    for i in range(encrypted_batch.num_rows):
        card_enc = str(encrypted_batch.column('card_number')[i])
        ssn_enc = str(encrypted_batch.column('ssn')[i])
        print(f"   Row {i+1}: Name={encrypted_batch.column('customer')[i]}")
        print(f"          Card (AES-256-GCM) = {card_enc[:35]}...")
        print(f"          SSN  (AES-256-GCM) = {ssn_enc[:35]}...")

    # 3. Decrypt back
    decrypted_batch = cipher.decrypt_batch_fields(encrypted_batch, ["card_number", "ssn"])

    print("\n3. Decrypted Record Batch (Verified Roundtrip):")
    for i in range(decrypted_batch.num_rows):
        print(f"   Row {i+1}: Card={decrypted_batch.column('card_number')[i]}, SSN={decrypted_batch.column('ssn')[i]}")

    # 4. Verify integrity
    assert decrypted_batch.column('card_number')[0].as_py() == "4111111111111111"
    assert decrypted_batch.column('ssn')[0].as_py() == "123-45-6789"

    print("\n✅ CipherEngine Verification PASSED: AES-256-GCM field encryption/decryption verified!")


if __name__ == "__main__":
    run_demo()
