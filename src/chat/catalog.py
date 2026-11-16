"""Safe catalogue outcomes without credentials, response bodies or URLs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat.models import CatalogModel


class CatalogStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    KEY_MISMATCH = "key_mismatch"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    TLS_ERROR = "tls_error"
    HTTP_ERROR = "http_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class CatalogFetchResult:
    status: CatalogStatus
    models: tuple[CatalogModel, ...] = ()
    http_status: int | None = None
    retry_after: int | None = None

    @property
    def available(self) -> bool:
        return self.status in {CatalogStatus.SUCCESS, CatalogStatus.EMPTY}
