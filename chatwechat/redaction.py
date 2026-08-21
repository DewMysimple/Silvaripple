from __future__ import annotations

import hashlib
import logging
import re


WXID = re.compile(r"wxid_[A-Za-z0-9_-]+", re.IGNORECASE)
HEX_KEY = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{64,192}(?![0-9a-f])")


def stable_id(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:length]


def fingerprint(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()[:12]


def redact(value: object) -> str:
    text = str(value)
    text = WXID.sub(lambda match: f"account:{stable_id(match.group(0))}", text)
    return HEX_KEY.sub("[secret]", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
