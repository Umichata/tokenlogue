"""Доступ по эпохе и узкие разрешения завершения начатой операции."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from i18n import tr

if TYPE_CHECKING:
    from storage.field_cipher import FieldCipher


class DataAccessError(RuntimeError):
    """Закрытый или устаревший доступ без раскрытия содержимого."""

    def __init__(self) -> None:
        super().__init__(tr("protection.access_closed"))


@dataclass
class CompletionLease:
    """Разрешает только завершение одной отправки или одной ревизии черновика."""

    owner: DataAccess = field(repr=False)
    cipher: FieldCipher | None = field(repr=False)
    kind: str
    chat_id: str
    record_id: str
    epoch: int
    closed: bool = False

    def close(self) -> None:
        with self.owner._mutex:
            if not self.closed:
                self.closed = True
                self.cipher = None
                self.owner._leases -= 1

    @contextmanager
    def use(self) -> Iterator[None]:
        if self.closed:
            raise DataAccessError()
        token = self.owner._lease.set(self)
        try:
            yield
        finally:
            self.owner._lease.reset(token)


class DataAccess:
    """Хранит ключ только для открытой сессии и незавершённых узких leases."""

    def __init__(self) -> None:
        self._mutex = threading.RLock()
        self._cipher: FieldCipher | None = None
        self._epoch = 0
        self._leases = 0
        self._session: ContextVar[int | None] = ContextVar(
            f"tokenlogue_session_{id(self)}", default=None
        )
        self._lease: ContextVar[CompletionLease | None] = ContextVar(
            f"tokenlogue_completion_{id(self)}", default=None
        )

    @property
    def unlocked(self) -> bool:
        with self._mutex:
            return self._cipher is not None

    @property
    def epoch(self) -> int:
        with self._mutex:
            return self._epoch

    @property
    def active_leases(self) -> int:
        with self._mutex:
            return self._leases

    def open(self, cipher: FieldCipher) -> None:
        with self._mutex:
            self._epoch += 1
            self._cipher = cipher

    def lock(self) -> None:
        with self._mutex:
            self._epoch += 1
            self._cipher = None

    def assert_current(self) -> None:
        with self._mutex:
            captured = self._session.get()
            if self._cipher is None or (
                captured is not None and captured != self._epoch
            ):
                raise DataAccessError()

    @contextmanager
    def provenance(self) -> Iterator[None]:
        """Сохраняет эпоху вызова до ожидания, не выдавая разрешение на доступ."""
        with self._mutex:
            captured = self._session.get()
            token = self._session.set(self._epoch if captured is None else captured)
        try:
            yield
        finally:
            self._session.reset(token)

    @contextmanager
    def session(self) -> Iterator[None]:
        """Захватывается сервисом до первого await и переносится в to_thread."""
        with self._mutex:
            self.assert_current()
            captured = self._session.get()
            token = self._session.set(self._epoch if captured is None else captured)
        try:
            yield
            self.assert_current()
        finally:
            self._session.reset(token)

    def completion(self, kind: str, chat_id: str, record_id: str) -> CompletionLease:
        if kind not in {"send", "draft"} or not chat_id or not record_id:
            raise DataAccessError()
        with self._mutex:
            self.assert_current()
            self._leases += 1
            return CompletionLease(
                self, self._cipher, kind, chat_id, record_id, self._epoch
            )

    @contextmanager
    def authorize(
        self, operation: str, *, chat_id: str = "", record_id: str = ""
    ) -> Iterator[FieldCipher]:
        """Проверяет право перед SQL и повторно перед возвратом прочитанного."""
        if operation not in {"read", "write", "reserve", "finish", "draft"}:
            raise DataAccessError()
        with self._mutex:
            lease = self._lease.get()
            leased = bool(
                lease is not None
                and lease.owner is self
                and not lease.closed
                and lease.cipher is not None
                and (
                    (
                        operation == "finish"
                        and lease.kind == "send"
                        and record_id == lease.record_id
                        and (not chat_id or chat_id == lease.chat_id)
                    )
                    or (
                        operation == "draft"
                        and lease.kind == "draft"
                        and record_id == lease.record_id
                        and chat_id == lease.chat_id
                    )
                )
            )
            if leased:
                assert lease is not None and lease.cipher is not None
                cipher = lease.cipher
                epoch = lease.epoch
            else:
                if lease is not None:
                    raise DataAccessError()
                self.assert_current()
                assert self._cipher is not None
                cipher, epoch = self._cipher, self._epoch
        yield cipher
        if operation == "read":
            with self._mutex:
                if self._cipher is not cipher or epoch != self._epoch:
                    raise DataAccessError()
