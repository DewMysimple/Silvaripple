class ChatWechatError(Exception):
    """Base error that is safe to present to the user."""


class AuthorizationRequired(ChatWechatError):
    pass


class UnsupportedWechatVersion(ChatWechatError):
    pass


class SnapshotChanged(ChatWechatError):
    pass


class CorruptDatabase(ChatWechatError):
    pass


class OperationCancelled(ChatWechatError):
    pass
