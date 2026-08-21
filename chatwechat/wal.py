from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .crypto import PAGE_SIZE
from .errors import CorruptDatabase


WAL_MAGIC_BIG = 0x377F0682
WAL_MAGIC_LITTLE = 0x377F0683


def _checksum(data: bytes, state: tuple[int, int], byteorder: str) -> tuple[int, int]:
    if len(data) % 8:
        raise ValueError("WAL checksum input must be a multiple of 8 bytes")
    s0, s1 = state
    fmt = ">II" if byteorder == "big" else "<II"
    for offset in range(0, len(data), 8):
        x0, x1 = struct.unpack_from(fmt, data, offset)
        s0 = (s0 + x0 + s1) & 0xFFFFFFFF
        s1 = (s1 + x1 + s0) & 0xFFFFFFFF
    return s0, s1


@dataclass(slots=True)
class WalFrame:
    page_number: int
    database_size: int
    page: bytes


@dataclass(slots=True)
class WalParseResult:
    page_size: int
    committed_frames: list[WalFrame]
    ignored_tail_frames: int


def parse_wal(data: bytes) -> WalParseResult:
    if len(data) < 32:
        raise CorruptDatabase("WAL 头不完整")
    magic, version, page_size, checkpoint, salt1, salt2, check1, check2 = struct.unpack(">8I", data[:32])
    if magic not in (WAL_MAGIC_BIG, WAL_MAGIC_LITTLE):
        raise CorruptDatabase("WAL magic 不正确")
    if page_size != PAGE_SIZE:
        raise CorruptDatabase(f"不支持的 WAL 页大小: {page_size}")
    byteorder = "little" if magic == WAL_MAGIC_BIG else "big"
    actual_header = _checksum(data[:24], (0, 0), byteorder)
    if actual_header != (check1, check2):
        raise CorruptDatabase("WAL header checksum 不正确")
    frame_size = 24 + page_size
    complete_count = (len(data) - 32) // frame_size
    state = actual_header
    frames: list[WalFrame] = []
    last_commit = -1
    for index in range(complete_count):
        offset = 32 + index * frame_size
        header = data[offset : offset + 24]
        page = data[offset + 24 : offset + frame_size]
        page_number, database_size, frame_salt1, frame_salt2, expected1, expected2 = struct.unpack(">6I", header)
        if (frame_salt1, frame_salt2) != (salt1, salt2):
            break
        state = _checksum(header[:8] + page, state, byteorder)
        if state != (expected1, expected2):
            break
        frames.append(WalFrame(page_number, database_size, page))
        if database_size:
            last_commit = len(frames) - 1
    committed = frames[: last_commit + 1] if last_commit >= 0 else []
    return WalParseResult(page_size, committed, max(0, complete_count - len(committed)))


def apply_committed_wal(database: bytes, wal: bytes) -> bytes:
    parsed = parse_wal(wal)
    result = bytearray(database)
    final_size = None
    for frame in parsed.committed_frames:
        offset = (frame.page_number - 1) * parsed.page_size
        needed = offset + parsed.page_size
        if len(result) < needed:
            result.extend(bytes(needed - len(result)))
        result[offset:needed] = frame.page
        if frame.database_size:
            final_size = frame.database_size * parsed.page_size
    return bytes(result[:final_size] if final_size is not None else result)
