from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Iterable

from .crypto import PAGE_SIZE, parse_candidate_literals, validate_page_key
from .discovery import database_files, optional_database_files
from .keystore import KeyStore
from .redaction import stable_id


MEM_COMMIT = 0x1000
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
READABLE = {0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80}
CONFIG_CIPHER_NAME = b"com.Tencent.WCDB.Config.Cipher"
MAX_USER_ADDRESS = 0x0000800000000000


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wintypes.DWORD),
        ("_pad1", wintypes.DWORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("_pad2", wintypes.DWORD),
    ]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def weixin_pids() -> list[int]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        raw = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
            encoding="gbk",
            errors="ignore",
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[tuple[int, int]] = []
    for line in raw.splitlines():
        columns = [part.strip().strip('"') for part in re.split(r'","|,', line)]
        if len(columns) < 2 or columns[0].casefold() != "weixin.exe":
            continue
        try:
            memory = int(re.sub(r"\D", "", columns[4])) if len(columns) > 4 else 0
            rows.append((memory, int(columns[1])))
        except ValueError:
            continue
    return [pid for _, pid in sorted(rows, reverse=True)]


class ProcessMemory:
    def __init__(self, pid: int):
        self.kernel32 = ctypes.windll.kernel32
        self.handle = self.kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.handle:
            raise PermissionError(f"无法只读打开 Weixin.exe 进程 PID {pid}")

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "ProcessMemory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def regions(self, writable_only: bool = False) -> list[tuple[int, int]]:
        regions: list[tuple[int, int]] = []
        mbi = MBI()
        address = 0
        while address < 0x7FFFFFFFFFFF:
            if not self.kernel32.VirtualQueryEx(
                self.handle, ctypes.c_uint64(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
            ):
                break
            allowed = {0x04, 0x08, 0x40, 0x80} if writable_only else READABLE
            if mbi.State == MEM_COMMIT and mbi.Protect in allowed and 0 < mbi.RegionSize < 500 * 1024 * 1024:
                regions.append((mbi.BaseAddress, mbi.RegionSize))
            next_address = mbi.BaseAddress + mbi.RegionSize
            if next_address <= address:
                break
            address = next_address
        return regions

    def read(self, address: int, size: int) -> bytes | None:
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        if self.kernel32.ReadProcessMemory(
            self.handle, ctypes.c_uint64(address), buffer, size, ctypes.byref(read)
        ):
            return buffer.raw[: read.value]
        return None

    def chunks(self, regions: Iterable[tuple[int, int]], overlap: int = 0) -> Iterable[tuple[int, bytes]]:
        chunk_size = 2 * 1024 * 1024
        for base, size in regions:
            offset, tail, tail_base = 0, b"", base
            while offset < size:
                length = min(chunk_size, size - offset)
                chunk = self.read(base + offset, length) or b""
                data_base = tail_base if tail else base + offset
                data = tail + chunk
                if data:
                    yield data_base, data
                    tail = data[-overlap:] if overlap else b""
                    tail_base = data_base + len(data) - len(tail)
                offset += length


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0] if len(data) >= offset + 8 else 0


def _find(memory: ProcessMemory, regions: list[tuple[int, int]], needle: bytes) -> set[int]:
    found: set[int] = set()
    for base, data in memory.chunks(regions, len(needle) - 1):
        offset = data.find(needle)
        while offset >= 0:
            found.add(base + offset)
            offset = data.find(needle, offset + 1)
    return found


def scan_candidates(memory: ProcessMemory) -> Iterable[bytes]:
    regions = memory.regions()
    names = _find(memory, regions, CONFIG_CIPHER_NAME)
    patterns = [struct.pack("<QQ", address, len(CONFIG_CIPHER_NAME)) for address in names]
    seen: set[bytes] = set()
    for base, data in memory.chunks(regions, overlap=0x80):
        for pattern in patterns:
            position = data.find(pattern)
            while position >= 0:
                node_address = base + position - 0x10
                node = memory.read(node_address, 0x50)
                if node and _u64(node, 0x10) in names and _u64(node, 0x18) == len(CONFIG_CIPHER_NAME):
                    config_pointer = _u64(node, 0x28)
                    if 0x10000 <= config_pointer < MAX_USER_ADDRESS:
                        obj = memory.read(config_pointer + 0x88, 0x28)
                        data_pointer, data_length = (_u64(obj or b"", 0x8), _u64(obj or b"", 0x10))
                        if 0 < data_length <= 1024 and 0x10000 <= data_pointer < MAX_USER_ADDRESS:
                            blob = memory.read(data_pointer, int(data_length))
                            if blob and len(blob) == data_length:
                                for candidate in parse_candidate_literals(blob):
                                    if candidate not in seen:
                                        seen.add(candidate)
                                        yield candidate
                position = data.find(pattern, position + 1)


def find_image_template(account_dir: Path, limit: int = 100) -> tuple[bytes | None, int | None]:
    magic = b"\x07\x08V2\x08\x07"
    candidates: list[Path] = []
    for root_name in ("msg", "cache"):
        root = account_dir / root_name
        if not root.is_dir():
            continue
        for current, _, files in os.walk(root):
            for name in files:
                if name.casefold().endswith("_t.dat"):
                    candidates.append(Path(current) / name)
    candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    ciphertext = None
    tail_counts: dict[tuple[int, int], int] = {}
    for path in candidates[:limit]:
        try:
            with path.open("rb") as stream:
                data = stream.read()
        except OSError:
            continue
        if not data.startswith(magic):
            continue
        if ciphertext is None and len(data) >= 31:
            ciphertext = data[15:31]
        if len(data) >= 2:
            pair = (data[-2], data[-1])
            tail_counts[pair] = tail_counts.get(pair, 0) + 1
    xor_key = None
    for (first, second), _ in sorted(tail_counts.items(), key=lambda item: item[1], reverse=True):
        candidate = first ^ 0xFF
        if candidate == (second ^ 0xD9):
            xor_key = candidate
            break
    return ciphertext, xor_key


def _valid_image_block(key: bytes, ciphertext: bytes) -> bool:
    if len(key) < 16 or len(ciphertext) != 16:
        return False
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        decryptor = Cipher(algorithms.AES(key[:16]), modes.ECB()).decryptor()
        plain = decryptor.update(ciphertext) + decryptor.finalize()
    except Exception:
        return False
    return plain.startswith((b"\xff\xd8\xff", b"\x89PNG", b"RIFF", b"GIF", b"wxgf"))


def scan_image_aes_key(memory: ProcessMemory, ciphertext: bytes) -> bytes | None:
    ascii_pattern = re.compile(rb"(?<![A-Za-z0-9])([A-Za-z0-9]{32})(?![A-Za-z0-9])")
    utf16_pattern = re.compile(rb"((?:[A-Za-z0-9]\x00){32})")
    for _, data in memory.chunks(memory.regions(writable_only=True), overlap=66):
        for match in ascii_pattern.finditer(data):
            candidate = match.group(1)
            if _valid_image_block(candidate, ciphertext):
                return candidate[:16]
        for match in utf16_pattern.finditer(data):
            candidate = match.group(1)[::2]
            if _valid_image_block(candidate, ciphertext):
                return candidate[:16]
    return None


def derive_image_keys(code: int, account_directory_name: str) -> tuple[bytes, bytes]:
    parts = account_directory_name.split("_")
    cleaned = "_".join(parts[:2]) if len(parts) >= 2 else account_directory_name
    aes = hashlib.md5(f"{code}{cleaned}".encode("utf-8")).hexdigest()[:16].encode("ascii")
    return bytes([code & 0xFF]), aes


def authorize(account_dir: Path, store: KeyStore | None = None) -> dict[str, object]:
    if not is_admin():
        raise PermissionError("授权助手需要管理员权限")
    store = store or KeyStore()
    targets: list[tuple[Path, bytes]] = []
    critical_paths = database_files(account_dir)
    optional_paths = optional_database_files(account_dir)
    for path in [*critical_paths, *optional_paths]:
        with path.open("rb") as stream:
            page = stream.read(PAGE_SIZE)
        if len(page) == PAGE_SIZE:
            targets.append((path, page))
    account_id = stable_id(account_dir.name)
    remaining = {page[:16]: page for _, page in targets}
    critical_salts = {page[:16] for path, page in targets if path in critical_paths}
    avatar_salts = {page[:16] for path, page in targets if path in optional_paths}
    for salt, page in list(remaining.items()):
        existing = store.get_database_key(account_id, salt)
        if existing and validate_page_key(page, existing):
            remaining.pop(salt)
    matched = 0
    candidate_count = 0
    for pid in weixin_pids():
        try:
            with ProcessMemory(pid) as memory:
                for candidate in scan_candidates(memory):
                    candidate_count += 1
                    for salt, page in list(remaining.items()):
                        if validate_page_key(page, candidate):
                            store.put_database_key(account_id, salt, candidate)
                            remaining.pop(salt)
                            matched += 1
        except (PermissionError, OSError):
            continue
        if not remaining:
            break
    image_captured = False
    ciphertext, xor_key = find_image_template(account_dir)
    if ciphertext is not None and xor_key is not None:
        existing_image = store.get_image_key(account_id, "aes")
        if existing_image and _valid_image_block(existing_image, ciphertext):
            image_captured = True
        else:
            for pid in weixin_pids():
                try:
                    with ProcessMemory(pid) as memory:
                        image_key = scan_image_aes_key(memory, ciphertext)
                    if image_key:
                        store.put_image_key(account_id, "aes", image_key)
                        store.put_image_key(account_id, "xor", bytes([xor_key]))
                        image_captured = True
                        break
                except (PermissionError, OSError):
                    continue
    return {
        "matched": matched,
        "total": len(critical_salts),
        "candidate_count": candidate_count,
        "missing": len(set(remaining) & critical_salts),
        "image_key_captured": image_captured,
        "avatar_key_captured": bool(avatar_salts) and not bool(set(remaining) & avatar_salts),
    }


class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def run_elevated(account_dir: Path, result_path: Path) -> dict[str, object]:
    parameters = subprocess.list2cmdline([
        "-m", "chatwechat.key_capture", "--account", str(account_dir), "--result", str(result_path)
    ])
    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = parameters
    info.lpDirectory = str(Path.cwd())
    info.nShow = 0
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        raise ctypes.WinError()
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 120_000)
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        result_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    result: dict[str, object]
    try:
        result = {"ok": True, **authorize(args.account)}
    except Exception as error:
        result = {"ok": False, "error": type(error).__name__}
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
