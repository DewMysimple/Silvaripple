import hashlib
import hmac
import os
import struct
import sqlite3

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from chatwechat.crypto import (
    HMAC_SIZE,
    PAGE_SIZE,
    RESERVE_SIZE,
    WindowsCngAes,
    derive_mac_key,
    parse_candidate_literals,
    validate_page_key,
)
from chatwechat.keystore import KeyStore
from chatwechat.config import Settings, SettingsStore
from chatwechat.key_capture import CONFIG_CIPHER_NAME, derive_image_keys, scan_candidates, scan_image_aes_key
from chatwechat.redaction import redact
from chatwechat.snapshot import ReadOnlySnapshotter, TempManager, validate_sqlite_structure


def encrypted_page(key: bytes, salt: bytes, plaintext: bytes) -> bytes:
    iv = bytes(range(16))
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    page = bytearray(salt + ciphertext + iv + bytes(HMAC_SIZE))
    mac = hmac.new(derive_mac_key(key, salt), page[16 : PAGE_SIZE - RESERVE_SIZE + 16] + struct.pack("<I", 1), hashlib.sha512).digest()
    page[-HMAC_SIZE:] = mac
    return bytes(page)


def test_snapshot_retries_windows_sharing_violation(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    source.write_bytes(b"snapshot")
    task = tmp_path / "task"
    task.mkdir()
    original = __import__("shutil").copyfile
    attempts = 0

    def flaky_copy(src, dst):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return original(src, dst)

    monkeypatch.setattr("chatwechat.snapshot.shutil.copyfile", flaky_copy)
    monkeypatch.setattr("chatwechat.snapshot.time.sleep", lambda _seconds: None)
    copied = ReadOnlySnapshotter(TempManager(tmp_path / "temp"), retries=3).copy_consistent(source, task)

    assert attempts == 3
    assert copied.read_bytes() == b"snapshot"


def test_key_validation_and_corruption():
    key, salt = bytes(range(32)), bytes(range(16))
    page = encrypted_page(key, salt, b"P" * (PAGE_SIZE - 16 - RESERVE_SIZE))
    assert validate_page_key(page, key)
    assert not validate_page_key(page, b"x" * 32)
    damaged = bytearray(page); damaged[100] ^= 1
    assert not validate_page_key(bytes(damaged), key)
    assert not validate_page_key(page[:-1], key)


def test_cng_decrypts_aes_cbc():
    key, iv, plaintext = bytes(range(32)), bytes(range(16)), b"A" * 64
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    encrypted = encryptor.update(plaintext) + encryptor.finalize()
    assert WindowsCngAes().decrypt_cbc(key, iv, encrypted) == plaintext


def test_candidate_decode_scans_multiple_offsets():
    key1, key2 = bytes(range(32)), bytes(range(32, 64))
    literal = b"X'" + key1.hex().encode() + key2.hex().encode() + b"'"
    mask = bytes.fromhex("d2c7442458020000004889442450488b450048844c2448488944254048584c24")
    blob = bytes(value ^ mask[index % len(mask)] for index, value in enumerate(literal))
    candidates = parse_candidate_literals(blob)
    assert key1 in candidates and key2 in candidates


def test_dpapi_key_store_roundtrip(tmp_path):
    store = KeyStore(tmp_path)
    key, salt = os.urandom(32), os.urandom(16)
    store.put_database_key("account", salt, key)
    assert store.get_database_key("account", salt) == key
    raw = store.path.read_text(encoding="utf-8")
    assert key.hex() not in raw
    assert store.covered_salts()["account"]


def test_settings_persist_only_opaque_last_account_id(tmp_path):
    store = SettingsStore(tmp_path)
    store.save(Settings(last_account_id="opaque-account-hash"))
    loaded = store.load()
    assert loaded.last_account_id == "opaque-account-hash"
    raw = store.path.read_text(encoding="utf-8")
    assert "message" not in raw and "wxid_" not in raw


def test_config_cipher_memory_object_scan():
    base = 0x100000
    region = bytearray(4096)
    name_offset, node_offset = 0x100, 0x2F0
    name_address = base + name_offset
    region[name_offset:name_offset + len(CONFIG_CIPHER_NAME)] = CONFIG_CIPHER_NAME
    struct.pack_into("<QQ", region, node_offset + 0x10, name_address, len(CONFIG_CIPHER_NAME))
    config_address = 0x200000
    struct.pack_into("<Q", region, node_offset + 0x28, config_address)
    key = bytes(range(32))
    literal = b"x'" + key.hex().encode() + b"'"
    mask = bytes.fromhex("d2c7442458020000004889442450488b450048844c2448488944254048584c24")
    blob = bytes(value ^ mask[index % len(mask)] for index, value in enumerate(literal))
    data_address = 0x300000
    obj = bytearray(0x28)
    struct.pack_into("<QQ", obj, 0x8, data_address, len(blob))

    class FakeMemory:
        def regions(self): return [(base, len(region))]
        def chunks(self, regions, overlap=0):
            yield base, bytes(region)
        def read(self, address, size):
            if base <= address and address + size <= base + len(region):
                start = address - base
                return bytes(region[start:start + size])
            if address == config_address + 0x88:
                return bytes(obj[:size])
            if address == data_address:
                return blob[:size]
            return None

    assert key in list(scan_candidates(FakeMemory()))


def test_redaction_hides_account_and_key():
    text = "wxid_private_123 " + ("ab" * 32)
    cleaned = redact(text)
    assert "wxid_private_123" not in cleaned
    assert "ab" * 32 not in cleaned


def test_image_memory_candidate_requires_real_header():
    candidate = b"0123456789abcdefABCDEF0123456789"
    plaintext = b"\x89PNG\r\n\x1a\n" + b"x" * 8
    encryptor = Cipher(algorithms.AES(candidate[:16]), modes.ECB()).encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    class FakeMemory:
        def regions(self, writable_only=False): return [(0x1000, 128)]
        def chunks(self, regions, overlap=0): yield 0x1000, b"!" + candidate + b"!"

    assert scan_image_aes_key(FakeMemory(), ciphertext) == candidate[:16]
    assert scan_image_aes_key(FakeMemory(), b"x" * 16) is None
    xor_key, aes_key = derive_image_keys(0x1234, "wxid_example_9999")
    assert xor_key == b"4" and len(aes_key) == 16


def test_decrypted_snapshot_passes_sqlite_structure_check(tmp_path):
    plain_path = tmp_path / "plain.db"
    connection = sqlite3.connect(plain_path)
    connection.execute("PRAGMA page_size=4096")
    connection.execute("VACUUM")
    connection.close()
    plain = bytearray(plain_path.read_bytes())
    plain[20] = 80
    struct.pack_into(">H", plain, 105, PAGE_SIZE - RESERVE_SIZE)
    key, salt = bytes(range(32)), bytes(range(16))
    encrypted_path = tmp_path / "encrypted.db"
    encrypted_path.write_bytes(encrypted_page(key, salt, bytes(plain[16 : PAGE_SIZE - RESERVE_SIZE])))
    decrypted = ReadOnlySnapshotter(TempManager(tmp_path / "temp")).decrypt(
        encrypted_path, key, tmp_path / "decrypted.db"
    )
    check = sqlite3.connect(decrypted).execute("PRAGMA quick_check").fetchone()[0]
    assert check == "ok"


def test_structure_check_handles_fts_shadow_tables(tmp_path):
    path = tmp_path / "fts.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE VIRTUAL TABLE search_fts USING fts5(value)")
    connection.execute("INSERT INTO search_fts(value) VALUES ('hello')")
    connection.commit()
    connection.close()

    validate_sqlite_structure(path)
    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()
