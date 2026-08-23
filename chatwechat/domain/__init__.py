"""Stable domain model imports for application and adapter layers."""

from ..errors import (
    AuthorizationRequired,
    ChatWechatError,
    CorruptDatabase,
    OperationCancelled,
    SnapshotChanged,
    UnsupportedWechatVersion,
)
from ..models import *  # noqa: F403 - compatibility surface during gradual extraction

__all__ = [
    "AuthorizationRequired",
    "ChatWechatError",
    "CorruptDatabase",
    "OperationCancelled",
    "SnapshotChanged",
    "UnsupportedWechatVersion",
]
