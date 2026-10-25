"""Аутентифицированные поля SQLite с явным контекстом каждой записи."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes

from i18n import tr

MAX_CONTENT_BYTES = 16 * 1024 * 1024
FORMAT_VERSION = 1


class CiphertextError(RuntimeError):
    """Содержимое или его связь с разрешённой базой повреждены."""

    def __init__(self) -> None:
        self.code = "content_protection_failed"
        super().__init__(tr("protection.unavailable"))


@dataclass(frozen=True, repr=False)
class FieldCipher:
    """Удерживает ключ только на время разрешённой сессии или операции."""

    key: bytes = dataclass_field(repr=False)
    database_id: str
    key_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != 32:
            raise CiphertextError()
        if not self.database_id or not self.key_id:
            raise CiphertextError()

    def _aad(
        self,
        *,
        table: str,
        field: str,
        record_id: str,
        chat_id: str = "",
        role: str = "",
        revision: int = 0,
    ) -> bytes:
        values = (self.database_id, self.key_id, table, field, record_id, chat_id, role)
        if any(not isinstance(v, str) or len(v) > 4096 for v in values):
            raise CiphertextError()
        if type(revision) is not int or revision < 0:
            raise CiphertextError()
        return json.dumps(
            ["tokenlogue-field", FORMAT_VERSION, *values, revision],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")

    def encrypt(
        self,
        value: str,
        *,
        table: str,
        field: str,
        record_id: str,
        chat_id: str = "",
        role: str = "",
        revision: int = 0,
    ) -> str:
        if not isinstance(value, str):
            raise CiphertextError()
        try:
            raw = value.encode("utf-8")
            if len(raw) > MAX_CONTENT_BYTES:
                raise CiphertextError()
            nonce = get_random_bytes(12)
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce, mac_len=16)
            cipher.update(
                self._aad(
                    table=table,
                    field=field,
                    record_id=record_id,
                    chat_id=chat_id,
                    role=role,
                    revision=revision,
                )
            )
            ciphertext, tag = cipher.encrypt_and_digest(raw)
            return json.dumps(
                [
                    "TLG",
                    FORMAT_VERSION,
                    self.key_id,
                    base64.b64encode(nonce).decode("ascii"),
                    base64.b64encode(ciphertext).decode("ascii"),
                    base64.b64encode(tag).decode("ascii"),
                ],
                separators=(",", ":"),
            )
        except (ValueError, TypeError, UnicodeError):
            raise CiphertextError() from None

    def decrypt(
        self,
        value: str,
        *,
        table: str,
        field: str,
        record_id: str,
        chat_id: str = "",
        role: str = "",
        revision: int = 0,
    ) -> str:
        try:
            if (
                not isinstance(value, str)
                or len(value) > MAX_CONTENT_BYTES * 4 // 3 + 8192
            ):
                raise CiphertextError()
            envelope = json.loads(value)
            if (
                not isinstance(envelope, list)
                or len(envelope) != 6
                or envelope[0] != "TLG"
                or type(envelope[1]) is not int
                or envelope[1] != FORMAT_VERSION
                or envelope[2] != self.key_id
                or any(not isinstance(v, str) for v in envelope[3:])
            ):
                raise CiphertextError()
            nonce, ciphertext, tag = (
                base64.b64decode(v, validate=True) for v in envelope[3:]
            )
            if (
                len(nonce) != 12
                or len(tag) != 16
                or len(ciphertext) > MAX_CONTENT_BYTES
            ):
                raise CiphertextError()
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce, mac_len=16)
            cipher.update(
                self._aad(
                    table=table,
                    field=field,
                    record_id=record_id,
                    chat_id=chat_id,
                    role=role,
                    revision=revision,
                )
            )
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            raise CiphertextError() from None
