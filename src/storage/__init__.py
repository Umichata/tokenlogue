"""Хранилища с отложенным импортом, независимым от порядка загрузки домена."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .chat_repository import SqliteChatRepository
    from .database import AuthDatabase
    from .message_repository import SqliteMessageRepository
    from .secure_credentials import FletSecureCredentials, SecureCredentialsError

__all__ = [
    "AuthDatabase",
    "FletSecureCredentials",
    "SecureCredentialsError",
    "SqliteChatRepository",
    "SqliteMessageRepository",
]

_MODULES = {
    "AuthDatabase": "database",
    "FletSecureCredentials": "secure_credentials",
    "SecureCredentialsError": "secure_credentials",
    "SqliteChatRepository": "chat_repository",
    "SqliteMessageRepository": "message_repository",
}


def __getattr__(name: str):
    module = _MODULES.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{module}"), name)
