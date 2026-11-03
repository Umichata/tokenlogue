"""Формат случайного резервного секрета и привязанного проверочного хеша."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from enum import StrEnum

CODE_BYTES = 20
CODE_LENGTH = 32
MAX_INPUT_LENGTH = 128
PROOF_TTL_SECONDS = 300
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 30
_DOMAIN = b"io.github.umichata.tokenlogue/recovery-code/v1\x00"


class RecoveryProofKind(StrEnum):
    """Источник права назначить новый PIN указан отдельно от результата UI."""

    SYSTEM = "system"
    CODE = "code"


@dataclass(frozen=True)
class RecoveryCodeIssue:
    """Открытый секрет возвращается только для экрана однократной выдачи."""

    attempt_id: str
    code: str = field(repr=False)


def normalize_code(value: str) -> str | None:
    """Принимает ASCII-регистр, обычный пробел и дефис, но не Unicode-аналоги."""
    if not isinstance(value, str) or len(value) > MAX_INPUT_LENGTH:
        return None
    characters = []
    for character in value:
        if character in {" ", "-"}:
            continue
        if "a" <= character <= "z":
            character = chr(ord(character) - 32)
        if not ("A" <= character <= "Z" or "2" <= character <= "7"):
            return None
        characters.append(character)
    if len(characters) != CODE_LENGTH:
        return None
    return "".join(characters)


def generate_code() -> str:
    """Даёт 160 случайных бит и восемь читаемых групп без padding."""
    encoded = base64.b32encode(secrets.token_bytes(CODE_BYTES)).decode("ascii")
    return "-".join(encoded[index : index + 4] for index in range(0, CODE_LENGTH, 4))


def code_digest(
    normalized: str,
    *,
    database_id: str,
    key_id: str,
    registration_id: str,
    generation: int,
) -> str:
    """Разделяет домен, формат, профиль, ключ, регистрацию и поколение секрета."""
    context = json.dumps(
        {
            "version": 1,
            "database_id": database_id,
            "key_id": key_id,
            "registration_id": registration_id,
            "generation": generation,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(
        _DOMAIN + context + b"\x00" + normalized.encode("ascii")
    ).hexdigest()
