"""Encrypted paid-request policy in the existing per-chat pricing record.

The legacy pricing list remains valid. No schema/table, sidecar or plaintext
per-chat preference is introduced. Invalid policy never enables paid dispatch.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from storage.field_cipher import FieldCipher


@dataclass(frozen=True)
class PaidPolicy:
    enabled: bool = False
    revision: str = ""


def _valid_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(c in "0123456789abcdef" for c in value)
    )


def split_document(value: str) -> tuple[list, object]:
    payload = json.loads(value)
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, dict) or not isinstance(payload.get("prices"), list):
        raise ValueError("invalid_pricing_document")
    policy = (
        payload.get("paid_confirmation")
        if type(payload.get("version")) is int and payload["version"] == 1
        else None
    )
    return payload["prices"], policy


def _policy(value: object) -> PaidPolicy:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "enabled", "revision"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["enabled"]) is not bool
        or not _valid_revision(value["revision"])
    ):
        return PaidPolicy()
    return PaidPolicy(value["enabled"], value["revision"])


def decode_stored(value: str, cipher: FieldCipher | None, chat_id: str) -> str:
    prices, encrypted = split_document(value)
    if encrypted is None and isinstance(json.loads(value), list):
        return value
    policy = PaidPolicy()
    if cipher is not None and isinstance(encrypted, str):
        try:
            clear = cipher.decrypt(
                encrypted, table="chats", field="paid_confirmation", record_id=chat_id
            )
            policy = _policy(json.loads(clear))
        except Exception:
            # A damaged/incompatible permission cannot suppress confirmation.
            policy = PaidPolicy()
    return json.dumps(
        {
            "version": 1,
            "prices": prices,
            "paid_confirmation": {
                "version": 1,
                "enabled": policy.enabled,
                "revision": policy.revision,
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def policy_from_read(value: str) -> PaidPolicy:
    _prices, policy = split_document(value)
    return _policy(policy)


def encode_stored(
    prices: list, policy: PaidPolicy, cipher: FieldCipher, chat_id: str
) -> str:
    if not _valid_revision(policy.revision) or type(policy.enabled) is not bool:
        raise ValueError("invalid_paid_policy")
    encrypted = cipher.encrypt(
        json.dumps(
            {"version": 1, "enabled": policy.enabled, "revision": policy.revision},
            separators=(",", ":"),
        ),
        table="chats",
        field="paid_confirmation",
        record_id=chat_id,
    )
    return json.dumps(
        {"version": 1, "prices": prices, "paid_confirmation": encrypted},
        separators=(",", ":"),
        sort_keys=True,
    )


def with_new_prices(connection: sqlite3.Connection, chat_id: str, value: str) -> str:
    prices, _unused = split_document(value)
    row = connection.execute(
        "SELECT id,pricing_overrides_json FROM chats WHERE id=?", (chat_id,)
    ).fetchone()
    if row is None:
        raise KeyError(chat_id)
    policy = policy_from_read(str(row["pricing_overrides_json"]))
    cipher = getattr(connection, "cipher", None)
    if isinstance(cipher, FieldCipher) and policy.revision:
        return encode_stored(prices, policy, cipher, chat_id)
    return json.dumps(prices, separators=(",", ":"), sort_keys=True)
