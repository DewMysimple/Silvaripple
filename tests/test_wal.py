import struct

import pytest

from chatwechat.crypto import PAGE_SIZE
from chatwechat.errors import CorruptDatabase
from chatwechat.wal import WAL_MAGIC_BIG, _checksum, apply_committed_wal, parse_wal


def make_wal(frames, tail=b""):
    salt1, salt2 = 11, 22
    prefix = struct.pack(">6I", WAL_MAGIC_BIG, 3007000, PAGE_SIZE, 0, salt1, salt2)
    state = _checksum(prefix, (0, 0), "little")
    output = bytearray(prefix + struct.pack(">2I", *state))
    for page_number, database_size, page in frames:
        frame_prefix = struct.pack(">4I", page_number, database_size, salt1, salt2)
        state = _checksum(frame_prefix[:8] + page, state, "little")
        output.extend(frame_prefix + struct.pack(">2I", *state) + page)
    return bytes(output) + tail


def test_wal_applies_only_through_last_commit():
    main = b"A" * PAGE_SIZE * 2
    page1, page2, uncommitted = b"B" * PAGE_SIZE, b"C" * PAGE_SIZE, b"D" * PAGE_SIZE
    wal = make_wal([(1, 0, page1), (2, 2, page2), (1, 0, uncommitted)])
    parsed = parse_wal(wal)
    assert len(parsed.committed_frames) == 2
    assert parsed.ignored_tail_frames == 1
    assert apply_committed_wal(main, wal) == page1 + page2


def test_wal_ignores_incomplete_tail():
    wal = make_wal([(1, 1, b"B" * PAGE_SIZE)], b"short tail")
    assert len(parse_wal(wal).committed_frames) == 1


def test_wal_rejects_bad_checksum():
    wal = bytearray(make_wal([(1, 1, b"B" * PAGE_SIZE)]))
    wal[12] ^= 1
    with pytest.raises(CorruptDatabase):
        parse_wal(bytes(wal))
