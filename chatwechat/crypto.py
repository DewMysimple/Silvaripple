from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import struct
from ctypes import wintypes

from .errors import CorruptDatabase


PAGE_SIZE = 4096
SALT_SIZE = 16
RESERVE_SIZE = 80
IV_SIZE = 16
HMAC_SIZE = 64
SQLITE_HEADER = b"SQLite format 3\x00"


def derive_page_key(passphrase: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", passphrase, salt, 256_000, 32)


def derive_mac_key(page_key: bytes, salt: bytes) -> bytes:
    mac_salt = bytes(byte ^ 0x3A for byte in salt)
    return hashlib.pbkdf2_hmac("sha512", page_key, mac_salt, 2, 32)


def page_hmac(page: bytes, page_number: int, page_key: bytes, salt: bytes) -> bytes:
    if len(page) != PAGE_SIZE:
        raise ValueError("page must be exactly 4096 bytes")
    start = SALT_SIZE if page_number == 1 else 0
    authenticated = page[start : PAGE_SIZE - HMAC_SIZE]
    return hmac.new(derive_mac_key(page_key, salt), authenticated + struct.pack("<I", page_number), hashlib.sha512).digest()


def validate_page_key(page: bytes, page_key: bytes) -> bool:
    if len(page) != PAGE_SIZE or len(page_key) != 32:
        return False
    expected = page[-HMAC_SIZE:]
    actual = page_hmac(page, 1, page_key, page[:SALT_SIZE])
    return hmac.compare_digest(expected, actual)


class WindowsCngAes:
    BCRYPT_AES_ALGORITHM = "AES"
    BCRYPT_CHAINING_MODE = "ChainingMode"
    BCRYPT_CHAIN_MODE_CBC = "ChainingModeCBC"
    BCRYPT_OBJECT_LENGTH = "ObjectLength"

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows CNG is required")
        self.bcrypt = ctypes.WinDLL("bcrypt.dll")

    @staticmethod
    def _check(status: int) -> None:
        if status < 0:
            raise OSError(f"Windows CNG failed with NTSTATUS 0x{status & 0xFFFFFFFF:08x}")

    def decrypt_cbc(self, key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
        if len(key) != 32 or len(iv) != 16 or len(ciphertext) % 16:
            raise ValueError("invalid AES-256-CBC parameters")
        algorithm = wintypes.HANDLE()
        self._check(self.bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(algorithm), self.BCRYPT_AES_ALGORITHM, None, 0))
        key_handle = wintypes.HANDLE()
        key_object = None
        try:
            mode = ctypes.create_unicode_buffer(self.BCRYPT_CHAIN_MODE_CBC)
            self._check(
                self.bcrypt.BCryptSetProperty(
                    algorithm,
                    self.BCRYPT_CHAINING_MODE,
                    ctypes.cast(mode, ctypes.POINTER(ctypes.c_ubyte)),
                    ctypes.sizeof(mode),
                    0,
                )
            )
            object_length = wintypes.DWORD()
            result_size = wintypes.DWORD()
            self._check(
                self.bcrypt.BCryptGetProperty(
                    algorithm,
                    self.BCRYPT_OBJECT_LENGTH,
                    ctypes.byref(object_length),
                    ctypes.sizeof(object_length),
                    ctypes.byref(result_size),
                    0,
                )
            )
            key_object = ctypes.create_string_buffer(object_length.value)
            key_buffer = ctypes.create_string_buffer(key)
            self._check(
                self.bcrypt.BCryptGenerateSymmetricKey(
                    algorithm,
                    ctypes.byref(key_handle),
                    key_object,
                    object_length.value,
                    key_buffer,
                    len(key),
                    0,
                )
            )
            source = ctypes.create_string_buffer(ciphertext)
            iv_buffer = ctypes.create_string_buffer(iv)
            output = ctypes.create_string_buffer(len(ciphertext))
            written = wintypes.DWORD()
            self._check(
                self.bcrypt.BCryptDecrypt(
                    key_handle,
                    source,
                    len(ciphertext),
                    None,
                    iv_buffer,
                    len(iv),
                    output,
                    len(output),
                    ctypes.byref(written),
                    0,
                )
            )
            return output.raw[: written.value]
        finally:
            if key_handle:
                self.bcrypt.BCryptDestroyKey(key_handle)
            if algorithm:
                self.bcrypt.BCryptCloseAlgorithmProvider(algorithm, 0)


def decrypt_page(page: bytes, page_number: int, page_key: bytes, salt: bytes, aes: WindowsCngAes | None = None) -> bytes:
    if len(page) != PAGE_SIZE:
        raise CorruptDatabase(f"第 {page_number} 页长度不正确")
    expected = page[-HMAC_SIZE:]
    actual = page_hmac(page, page_number, page_key, salt)
    if not hmac.compare_digest(expected, actual):
        raise CorruptDatabase(f"第 {page_number} 页 HMAC 校验失败")
    start = SALT_SIZE if page_number == 1 else 0
    footer = PAGE_SIZE - RESERVE_SIZE
    ciphertext = page[start:footer]
    iv = page[footer : footer + IV_SIZE]
    plaintext = (aes or WindowsCngAes()).decrypt_cbc(page_key, iv, ciphertext)
    if page_number == 1:
        return SQLITE_HEADER + plaintext + bytes(RESERVE_SIZE)
    return plaintext + bytes(RESERVE_SIZE)


def parse_candidate_literals(blob: bytes) -> list[bytes]:
    import re

    unmasked = bytes(byte ^ bytes.fromhex(
        "d2c7442458020000004889442450488b450048844c2448488944254048584c24"
    )[index % 32] for index, byte in enumerate(blob))
    results: list[bytes] = []
    seen: set[bytes] = set()
    for match in re.finditer(rb"[xX]'([0-9a-fA-F]{64,192})'", unmasked):
        run = match.group(1).decode("ascii")
        starts = [0]
        if len(run) > 96:
            starts.extend(range(0, len(run) - 63, 32))
            starts.append(len(run) - 64)
        for start in dict.fromkeys(starts):
            if start + 64 > len(run):
                continue
            candidate = bytes.fromhex(run[start : start + 64])
            if len(set(candidate)) >= 15 and candidate not in seen:
                seen.add(candidate)
                results.append(candidate)
    return results
