"""Транзакционный SQLite-репозиторий бюджетов и попыток генерации."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from chat.accounting import (
    AccountingStatus,
    BudgetReservation,
    BudgetState,
    ChatBudget,
    TurnRecord,
    TurnStatus,
)
from chat.budget_consent import (
    BudgetConsent,
    BudgetConsentBasis,
    BudgetConsentRevoked,
    budget_version,
    budget_warning,
    chat_prices,
    text_digest,
)
from chat.drafts import ChatDraft
from chat.errors import ChatErrorType
from chat.metrics import LastRequestMetrics, LastRequestState
from chat.models import ChatMode, Message, MessageRole, MessageStatus
from chat.paid_consent import PaidConsentRevoked
from i18n import tr
from providers.models import Currency, ProviderId
from storage.chat_monetary import (
    budget_row as _connection_budget_row,
)
from storage.chat_monetary import (
    refresh_active_projection,
    write_money,
)
from storage.chat_preferences import policy_from_read, with_new_prices
from storage.chat_repository import _chat_from_row
from storage.database_connections import (
    ContentAccess,
    encrypt_value,
)
from storage.database_connections import (
    connection as protected_connection,
)
from storage.provider_schema import ensure_provider_schema
from storage.request_attempts import (
    ensure_request_attempts,
    has_request_attempts,
    record_request_attempt,
    request_attempts_are_extended,
    synchronize_request_attempt,
)


class BudgetConflictError(RuntimeError):
    """Операция нарушает текущий бюджет или состояние другой транзакции."""


class SqliteMessageRepository:
    def __init__(
        self, database_path: str | Path, access: ContentAccess | None = None
    ) -> None:
        self.path = Path(database_path)
        self.access = access

    def get_chat_budget(
        self, chat_id: str, *, provider_id: ProviderId | None = None
    ) -> ChatBudget | None:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            row = _connection_budget_row(connection, chat_id, provider_id)
        return _budget_from_row(row) if row is not None else None

    def get_chat_mode(self, chat_id: str) -> ChatMode | None:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT mode FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
        return ChatMode(str(row["mode"])) if row is not None else None

    def set_chat_limits(
        self,
        chat_id: str,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit: Decimal | None = None,
        *,
        cost_limit_usd: Decimal | None = None,
        cost_increase_confirmed: bool,
        updated_at: datetime,
        expected_revision: int | None = None,
        currency: Currency | None = None,
    ) -> ChatBudget:
        cost_limit = cost_limit if cost_limit is not None else cost_limit_usd
        _require_identifier(chat_id, tr("service.label.chat"))
        _require_positive_int(token_limit, tr("service.label.token_budget"))
        _require_positive_int(max_completion_tokens, tr("service.label.completion"))
        _require_decimal(cost_limit, tr("service.label.money_budget"))
        assert isinstance(cost_limit, Decimal)
        _require_bool(cost_increase_confirmed, tr("service.label.money_confirmation"))
        with self._connection("write", chat_id=chat_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT b.*, c.mode
                FROM chat_budgets AS b
                JOIN chats AS c ON c.id = b.chat_id
                WHERE b.chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if row is None:
                raise KeyError(tr("service.chat_missing"))
            active = connection.execute(
                "SELECT connection_revision,currency FROM chats WHERE id=?", (chat_id,)
            ).fetchone()
            assert active is not None
            if (
                expected_revision is not None
                and active["connection_revision"] != expected_revision
            ) or (currency is not None and active["currency"] != currency.value):
                raise BudgetConflictError("chat_connection_changed")
            mode = ChatMode(str(row["mode"]))
            current_row = _connection_budget_row(connection, chat_id)
            assert current_row is not None
            current = _budget_from_row(current_row)
            minimum_tokens = current.total_tokens_used + current.reserved_tokens
            if token_limit < minimum_tokens:
                raise BudgetConflictError(tr("service.tokens_below_used"))
            minimum_cost = current.cost_used + current.cost_reserved
            if mode is ChatMode.PAID and cost_limit < minimum_cost:
                raise BudgetConflictError(tr("service.money_below_used"))
            if (
                mode is ChatMode.PAID
                and current.cost_limit is not None
                and cost_limit > current.cost_limit
                and not cost_increase_confirmed
            ):
                raise BudgetConflictError(tr("service.money_increase_confirmation"))
            state = _calculate_state(
                mode=mode,
                token_limit=token_limit,
                total_used=current.total_tokens_used,
                reserved_tokens=current.reserved_tokens,
                cost_limit=cost_limit,
                cost_used=current.cost_used,
                cost_reserved=current.cost_reserved,
                accounting_unknown=(current.state is BudgetState.ACCOUNTING_UNKNOWN),
            )
            connection.execute(
                """
                UPDATE chat_budgets
                SET limits_configured = 1,
                    token_limit = ?,
                    max_completion_tokens = ?,
                    cost_limit = ?,
                    state = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    token_limit,
                    max_completion_tokens,
                    _decimal_text(cost_limit),
                    state.value,
                    _datetime_text(updated_at),
                    chat_id,
                ),
            )
            write_money(
                connection,
                chat_id,
                current.provider_id,
                current.currency,
                cost_limit=(
                    current.cost_limit
                    if mode is ChatMode.FREE and current.cost_limit is not None
                    else cost_limit
                ),
                cost_used=current.cost_used,
                cost_reserved=current.cost_reserved,
                updated_at=_datetime_text(updated_at),
            )
            refresh_active_projection(connection, chat_id)
            updated = connection.execute(
                "SELECT * FROM chat_budgets WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            assert updated is not None
            return _budget_from_row(updated)

    def reserve_turn(
        self,
        reservation: BudgetReservation,
        *,
        content: str,
        requested_model_id: str,
        retry: bool,
        draft_revision: int | None = None,
        paid_policy_revision: str | None = None,
        budget_basis: BudgetConsentBasis | None = None,
        budget_consent: BudgetConsent | None = None,
        unknown_price_consent: BudgetConsent | None = None,
    ) -> ChatDraft | None:
        if not isinstance(reservation, BudgetReservation):
            raise ValueError(tr("service.reserve_object_invalid"))
        _require_identifier(reservation.turn_id, tr("service.label.turn"))
        _require_identifier(reservation.user_message_id, tr("service.label.message"))
        _require_identifier(reservation.chat_id, tr("service.label.chat"))
        _require_nonnegative_int(
            reservation.reserved_tokens, tr("service.label.token_reserve")
        )
        _require_decimal(reservation.reserved_cost, tr("service.label.money_reserve"))
        _require_text(content, tr("service.label.message_text"))
        _require_identifier(requested_model_id, tr("service.label.model"))
        _require_bool(retry, tr("service.label.retry"))
        if draft_revision is not None:
            _require_nonnegative_int(draft_revision, tr("service.label.draft_revision"))
        with self._connection(
            "reserve", chat_id=reservation.chat_id, record_id=reservation.turn_id
        ) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT b.*, c.mode, c.id, c.pricing_overrides_json
                FROM chat_budgets AS b
                JOIN chats AS c ON c.id = b.chat_id
                WHERE b.chat_id = ?
                """,
                (reservation.chat_id,),
            ).fetchone()
            if row is None:
                raise KeyError(tr("service.chat_missing"))
            budget_data = _connection_budget_row(connection, reservation.chat_id)
            assert budget_data is not None
            budget = _budget_from_row(budget_data)
            mode = ChatMode(str(row["mode"]))
            current_row = connection.execute(
                "SELECT * FROM chats WHERE id=?", (reservation.chat_id,)
            ).fetchone()
            assert current_row is not None
            current_chat = _chat_from_row(current_row)
            if (
                current_chat.connection_revision != reservation.connection_revision
                or (
                    reservation.provider_id is not None
                    and current_chat.provider_id is not reservation.provider_id
                )
                or current_chat.currency is not reservation.currency
                or current_chat.requested_model_id != requested_model_id
            ):
                raise BudgetConflictError("chat_connection_changed")
            if paid_policy_revision is not None:
                policy = policy_from_read(str(row["pricing_overrides_json"]))
                if (
                    mode is not ChatMode.PAID
                    or not policy.enabled
                    or policy.revision != paid_policy_revision
                ):
                    raise PaidConsentRevoked()
            if not budget.limits_configured:
                raise BudgetConflictError(tr("service.limits_unconfigured"))
            unknown_authorized = False
            if unknown_price_consent is not None:
                from chat.budget_consent import UnknownPriceConsent

                if (
                    not isinstance(unknown_price_consent, UnknownPriceConsent)
                    or budget_basis is None
                    or not budget_basis.unknown_pricing
                    or budget_consent is not None
                ):
                    raise BudgetConsentRevoked()
                unknown_authorized = True
            if reservation.currency != budget.currency:
                raise BudgetConflictError("reservation_currency_mismatch")
            if (
                budget.state is BudgetState.ACCOUNTING_UNKNOWN
                and not unknown_authorized
            ):
                raise BudgetConflictError(tr("service.previous_unknown"))
            if budget.token_limit is None:
                raise BudgetConflictError(tr("service.token_budget_missing"))
            token_remaining = (
                budget.token_limit - budget.total_tokens_used - budget.reserved_tokens
            )
            if reservation.reserved_tokens > token_remaining:
                raise BudgetConflictError(tr("service.token_budget_insufficient"))
            new_cost_reserved = budget.cost_reserved + reservation.reserved_cost
            if mode is ChatMode.PAID:
                if budget.cost_limit is None:
                    raise BudgetConflictError(tr("service.money_budget_missing"))
                current_warning = budget_warning(budget, reservation.reserved_cost)
                if budget_basis is not None:
                    chat_row = connection.execute(
                        "SELECT * FROM chats WHERE id = ?", (reservation.chat_id,)
                    ).fetchone()
                    assert chat_row is not None
                    current_chat = _chat_from_row(chat_row)
                    if (
                        budget_basis.chat_id != reservation.chat_id
                        or budget_basis.model_id != requested_model_id
                        or current_chat.requested_model_id != requested_model_id
                        or (
                            not current_chat.pricing_snapshot_complete
                            and not unknown_authorized
                        )
                        or budget_basis.text_sha256 != text_digest(content)
                        or budget_basis.draft_revision != draft_revision
                        or budget_basis.retry_turn_id
                        != (
                            (reservation.retry_of_turn_id or reservation.turn_id)
                            if retry
                            else None
                        )
                        or budget_basis.connection_revision
                        != current_chat.connection_revision
                        or budget_basis.limits_version != budget_version(budget)
                        or budget_basis.pricing != chat_prices(current_chat)
                        or (
                            not unknown_authorized
                            and getattr(
                                budget_basis,
                                "estimated_cost",
                                budget_basis.estimated_cost_usd,
                            )
                            != reservation.reserved_cost
                        )
                        or (
                            unknown_authorized
                            and reservation.reserved_cost
                            != max(
                                Decimal("0"),
                                budget.cost_limit
                                - budget.cost_used
                                - budget.cost_reserved,
                            )
                        )
                        or getattr(budget_basis, "provider_id", budget.provider_id)
                        != budget.provider_id
                        or getattr(budget_basis, "currency", budget.currency)
                        != budget.currency
                        or budget_basis.reserved_tokens != reservation.reserved_tokens
                        or (
                            not unknown_authorized
                            and getattr(
                                budget_basis,
                                "projected_remaining",
                                budget_basis.projected_remaining_usd,
                            )
                            != budget.cost_limit - budget.cost_used - new_cost_reserved
                        )
                    ):
                        raise BudgetConsentRevoked()
                    if draft_revision is not None:
                        draft_row = connection.execute(
                            "SELECT revision FROM chat_drafts WHERE chat_id = ?",
                            (reservation.chat_id,),
                        ).fetchone()
                        stored_revision = (
                            0 if draft_row is None else draft_row["revision"]
                        )
                        if stored_revision != draft_revision:
                            raise BudgetConsentRevoked()
                if unknown_price_consent is not None:
                    assert budget_basis is not None
                    unknown_price_consent.consume(budget_basis)
                elif budget_consent is not None:
                    if (
                        not isinstance(budget_consent, BudgetConsent)
                        or budget_basis is None
                    ):
                        raise BudgetConsentRevoked()
                    budget_consent.consume(budget_basis)
                elif current_warning is not None:
                    raise BudgetConsentRevoked()
                if (
                    budget.cost_used + new_cost_reserved > budget.cost_limit
                    and budget_consent is None
                    and not unknown_authorized
                ):
                    raise BudgetConflictError(tr("service.money_budget_insufficient"))
            elif reservation.reserved_cost != 0:
                raise BudgetConflictError(tr("service.free_cannot_reserve_money"))
            new_reserved_tokens = budget.reserved_tokens + reservation.reserved_tokens
            reservation_state = _calculate_state(
                mode=mode,
                token_limit=budget.token_limit,
                total_used=budget.total_tokens_used,
                reserved_tokens=new_reserved_tokens,
                cost_limit=budget.cost_limit,
                cost_used=budget.cost_used,
                cost_reserved=new_cost_reserved,
                accounting_unknown=budget.state is BudgetState.ACCOUNTING_UNKNOWN,
            )

            if retry:
                self._prepare_retry(connection, reservation, requested_model_id)
            else:
                connection.execute(
                    """
                    INSERT INTO turns (
                        id, chat_id, status, requested_model_id,
                        reserved_tokens, reserved_cost,provider_id,currency,connection_revision,
                        accounting_status, request_sent, created_at, updated_at
                    )
                    VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, 'reserved', 0, ?, ?)
                    """,
                    (
                        reservation.turn_id,
                        reservation.chat_id,
                        requested_model_id,
                        reservation.reserved_tokens,
                        _decimal_text(reservation.reserved_cost),
                        budget.provider_id.value,
                        budget.currency.value,
                        current_chat.connection_revision,
                        _datetime_text(reservation.created_at),
                        _datetime_text(reservation.created_at),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO messages (
                        id, chat_id, turn_id, role, content, status,
                        requested_model_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'user', ?, 'pending', ?, ?, ?)
                    """,
                    (
                        reservation.user_message_id,
                        reservation.chat_id,
                        reservation.turn_id,
                        encrypt_value(
                            connection,
                            content,
                            table="messages",
                            field="content",
                            record_id=reservation.user_message_id,
                            chat_id=reservation.chat_id,
                            role="user",
                        ),
                        requested_model_id,
                        _datetime_text(reservation.created_at),
                        _datetime_text(reservation.created_at),
                    ),
                )

            consumed_draft = None
            if not retry and draft_revision is not None:
                draft = connection.execute(
                    "SELECT chat_id,revision,content FROM chat_drafts WHERE chat_id=? AND revision=?",
                    (reservation.chat_id, draft_revision),
                ).fetchone()
                if draft is not None:
                    consumed_draft = ChatDraft(
                        reservation.chat_id, draft_revision, str(draft["content"])
                    )
                # Keep a revision tombstone: an in-flight stale save of the
                # consumed revision must never recreate its draft text.
                connection.execute(
                    "UPDATE chat_drafts SET content = ? WHERE chat_id = ? AND revision = ?",
                    (
                        encrypt_value(
                            connection,
                            "",
                            table="chat_drafts",
                            field="content",
                            record_id=reservation.chat_id,
                            chat_id=reservation.chat_id,
                            revision=draft_revision,
                        ),
                        reservation.chat_id,
                        draft_revision,
                    ),
                )

            connection.execute(
                """
                UPDATE chat_budgets
                SET reserved_tokens = reserved_tokens + ?,
                    cost_reserved = ?,
                    state = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    reservation.reserved_tokens,
                    _decimal_text(new_cost_reserved),
                    reservation_state.value,
                    _datetime_text(reservation.created_at),
                    reservation.chat_id,
                ),
            )
            write_money(
                connection,
                reservation.chat_id,
                budget.provider_id,
                budget.currency,
                cost_limit=budget.cost_limit,
                cost_used=budget.cost_used,
                cost_reserved=new_cost_reserved,
                updated_at=_datetime_text(reservation.created_at),
            )
        return consumed_draft

    def restore_unsent_draft(self, turn_id: str, draft: ChatDraft) -> None:
        """Finishes only this unsent turn, never overwriting a newer draft."""
        _require_identifier(turn_id, tr("service.label.turn"))
        if not isinstance(draft, ChatDraft) or not draft.text:
            return
        with self._connection(
            "finish", chat_id=draft.chat_id, record_id=turn_id
        ) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn = connection.execute(
                "SELECT chat_id,accounting_status,status FROM turns WHERE id=?",
                (turn_id,),
            ).fetchone()
            if (
                turn is None
                or turn["chat_id"] != draft.chat_id
                or turn["accounting_status"] != AccountingStatus.RELEASED.value
                or turn["status"] != TurnStatus.FAILED.value
            ):
                return
            current = connection.execute(
                "SELECT chat_id,revision,content FROM chat_drafts WHERE chat_id=?",
                (draft.chat_id,),
            ).fetchone()
            if (
                current is None
                or current["revision"] != draft.revision
                or current["content"] != ""
            ):
                return
            # This is rollback of an unsent reservation, not a new editor edit.
            # Reusing N lets a real dirty edit N+1 win even if not flushed yet.
            # Strict save_draft(>revision) and the empty-N CAS still reject stale N.
            revision = draft.revision
            connection.execute(
                "UPDATE chat_drafts SET revision=?,content=? WHERE chat_id=? AND revision=?",
                (
                    revision,
                    encrypt_value(
                        connection,
                        draft.text,
                        table="chat_drafts",
                        field="content",
                        record_id=draft.chat_id,
                        chat_id=draft.chat_id,
                        revision=revision,
                    ),
                    draft.chat_id,
                    draft.revision,
                ),
            )

    def mark_request_sent(self, turn_id: str, updated_at: datetime) -> int:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection("reserve", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            ensure_request_attempts(connection)
            cursor = connection.execute(
                """
                UPDATE turns
                SET request_sent = 1, updated_at = ?
                WHERE id = ? AND status = 'pending' AND request_sent = 0
                """,
                (_datetime_text(updated_at), turn_id),
            )
            if cursor.rowcount != 1:
                raise BudgetConflictError(tr("service.turn_inactive"))
            return record_request_attempt(
                connection, turn_id, _datetime_text(updated_at)
            )

    def finalize_known_turn(
        self,
        turn_id: str,
        *,
        assistant_message_id: str,
        content: str | None,
        successful: bool,
        requested_model_id: str,
        actual_model_id: str | None,
        generation_id: str | None,
        finish_reason: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        cost: Decimal | None = None,
        cost_usd: Decimal | None = None,
        usage_source: str = "api",
        cost_source: str = "api",
        cached_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        attempt_sequence: int | None = None,
        error_type: ChatErrorType | None,
        generated_title: str | None,
        updated_at: datetime,
    ) -> None:
        """Save known usage independently of money, once for this dispatch.

        A response without cost is still a response. Its monetary reservation
        stays held until explicit reconciliation; unknown never means free.
        """
        cost = cost if cost is not None else cost_usd
        _require_identifier(turn_id, tr("service.label.turn"))
        _require_identifier(assistant_message_id, tr("service.label.message"))
        _require_bool(successful, tr("service.label.result_status"))
        _require_identifier(requested_model_id, tr("service.label.model"))
        for value in (
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cached_tokens,
            reasoning_tokens,
        ):
            if value is not None:
                _require_nonnegative_int(value, tr("service.label.total_tokens"))
        if cost is not None:
            _require_decimal(cost, tr("service.label.result_cost"))
        if usage_source not in {"api", "estimated", "unknown"} or cost_source not in {
            "api",
            "estimated",
            "unknown",
        }:
            raise ValueError("accounting_source_invalid")
        if content is not None:
            _require_text(
                content, tr("service.label.assistant_response"), allow_empty=True
            )
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if attempt_sequence is not None:
                latest = connection.execute(
                    "SELECT MAX(sequence) FROM chat_request_attempts WHERE turn_id=?",
                    (turn_id,),
                ).fetchone()[0]
                if latest != attempt_sequence:
                    return
            existing = connection.execute(
                "SELECT status FROM turns WHERE id=?", (turn_id,)
            ).fetchone()
            if existing is not None and existing["status"] != TurnStatus.PENDING.value:
                return
            turn, budget, mode = self._load_active_turn(connection, turn_id)
            if cost_usd is not None and turn.currency is not Currency.USD:
                raise ValueError("usd_cost_for_non_usd_attempt")
            usage_complete = (
                all(
                    value is not None
                    for value in (prompt_tokens, completion_tokens, total_tokens)
                )
                and usage_source == "api"
            )
            cost_complete = cost is not None and cost_source == "api"
            new_reserved_tokens = budget.reserved_tokens - (
                turn.reserved_tokens if usage_complete else 0
            )
            new_reserved_cost = budget.cost_reserved - (
                turn.reserved_cost if cost_complete else Decimal("0")
            )
            if new_reserved_tokens < 0 or new_reserved_cost < 0:
                raise BudgetConflictError(tr("service.reserve_corrupt"))
            api_usage = usage_source == "api"
            new_prompt = budget.prompt_tokens_used + (
                (prompt_tokens or 0) if api_usage else 0
            )
            new_completion = budget.completion_tokens_used + (
                (completion_tokens or 0) if api_usage else 0
            )
            new_total = budget.total_tokens_used + (
                max(total_tokens or 0, (prompt_tokens or 0) + (completion_tokens or 0))
                if api_usage
                else 0
            )
            new_cost = budget.cost_used + (
                cost if cost_complete and cost is not None else Decimal("0")
            )
            accounting = (
                AccountingStatus.FINAL
                if usage_complete and cost_complete
                else AccountingStatus.UNKNOWN
            )
            other_unknown = (
                connection.execute(
                    "SELECT 1 FROM turns WHERE chat_id=? AND id!=? AND accounting_status='unknown' LIMIT 1",
                    (turn.chat_id, turn_id),
                ).fetchone()
                is not None
            )
            state = _calculate_state(
                mode=mode,
                token_limit=budget.token_limit,
                total_used=new_total,
                reserved_tokens=new_reserved_tokens,
                cost_limit=budget.cost_limit,
                cost_used=new_cost,
                cost_reserved=new_reserved_cost,
                accounting_unknown=accounting is AccountingStatus.UNKNOWN
                or other_unknown,
            )
            connection.execute(
                "UPDATE chat_budgets SET prompt_tokens_used=?,completion_tokens_used=?,total_tokens_used=?,reserved_tokens=?,cost_used=?,cost_reserved=?,state=?,updated_at=? WHERE chat_id=?",
                (
                    new_prompt,
                    new_completion,
                    new_total,
                    new_reserved_tokens,
                    _decimal_text(new_cost),
                    _decimal_text(new_reserved_cost),
                    state.value,
                    _datetime_text(updated_at),
                    turn.chat_id,
                ),
            )
            write_money(
                connection,
                turn.chat_id,
                turn.provider_id,
                turn.currency,
                cost_limit=budget.cost_limit,
                cost_used=new_cost,
                cost_reserved=new_reserved_cost,
                updated_at=_datetime_text(updated_at),
            )
            connection.execute(
                "UPDATE turns SET status=?,actual_model_id=?,generation_id=?,finish_reason=?,prompt_tokens=?,completion_tokens=?,total_tokens=?,cost=?,usage_source=?,cost_source=?,cached_tokens=?,reasoning_tokens=?,accounting_status=?,error_type=?,reserved_tokens=?,reserved_cost=?,updated_at=? WHERE id=?",
                (
                    TurnStatus.SENT.value if successful else TurnStatus.FAILED.value,
                    actual_model_id,
                    encrypt_value(
                        connection,
                        generation_id,
                        table="turns",
                        field="generation_id",
                        record_id=turn_id,
                        chat_id=turn.chat_id,
                    ),
                    encrypt_value(
                        connection,
                        finish_reason,
                        table="turns",
                        field="finish_reason",
                        record_id=turn_id,
                        chat_id=turn.chat_id,
                    ),
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    str(cost) if cost is not None else None,
                    usage_source
                    if any(
                        v is not None
                        for v in (prompt_tokens, completion_tokens, total_tokens)
                    )
                    else "unknown",
                    cost_source if cost is not None else "unknown",
                    cached_tokens,
                    reasoning_tokens,
                    accounting.value,
                    error_type.value if error_type else None,
                    0 if usage_complete else turn.reserved_tokens,
                    str(Decimal("0") if cost_complete else turn.reserved_cost),
                    _datetime_text(updated_at),
                    turn_id,
                ),
            )
            connection.execute(
                "UPDATE messages SET status=?,updated_at=? WHERE chat_id=? AND turn_id=? AND role='user'",
                (
                    MessageStatus.SENT.value
                    if successful
                    else MessageStatus.FAILED.value,
                    _datetime_text(updated_at),
                    turn.chat_id,
                    turn_id,
                ),
            )
            synchronize_request_attempt(connection, turn_id)
            if content is not None:
                self._upsert_assistant_message(
                    connection,
                    turn=turn,
                    message_id=assistant_message_id,
                    content=content,
                    successful=successful,
                    requested_model_id=requested_model_id,
                    actual_model_id=actual_model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    updated_at=updated_at,
                )
            if successful and generated_title:
                if getattr(connection, "cipher", None) is not None:
                    connection.execute(
                        "UPDATE chats SET title=?,title_origin='message',updated_at=? WHERE id=? AND title_origin='placeholder' AND title_is_manual=0",
                        (
                            encrypt_value(
                                connection,
                                generated_title,
                                table="chats",
                                field="title",
                                record_id=turn.chat_id,
                            ),
                            _datetime_text(updated_at),
                            turn.chat_id,
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE chats SET title=?,updated_at=? WHERE id=? AND title='Новый чат' AND title_is_manual=0",
                        (generated_title, _datetime_text(updated_at), turn.chat_id),
                    )
            else:
                connection.execute(
                    "UPDATE chats SET updated_at=? WHERE id=?",
                    (_datetime_text(updated_at), turn.chat_id),
                )

    def release_local_failure(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn, budget, mode = self._load_active_turn(connection, turn_id)
            if turn.request_sent:
                raise BudgetConflictError(tr("service.sent_cannot_release"))
            self._release_reservation(
                connection,
                turn,
                budget,
                mode,
                error_type,
                AccountingStatus.RELEASED,
                updated_at,
            )

    def release_known_failure(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn, budget, mode = self._load_active_turn(connection, turn_id)
            self._release_reservation(
                connection,
                turn,
                budget,
                mode,
                error_type,
                AccountingStatus.RELEASED,
                updated_at,
            )

    def release_unsent_dispatch(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None:
        """Void only a provisional dispatch that never reached the client.

        The sender marks immediately before its reservation callback and final
        guards. Cancellation or a rejected guard in that window is not an
        actual HTTP attempt and must leave the preceding actual usage intact.
        """
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn, budget, mode = self._load_active_turn(connection, turn_id)
            if not turn.request_sent:
                raise BudgetConflictError(tr("service.turn_inactive"))
            cursor = connection.execute(
                """
                DELETE FROM chat_request_attempts
                WHERE sequence=(SELECT MAX(sequence) FROM chat_request_attempts WHERE turn_id=?)
                  AND status='pending' AND chronology_known=1
                """,
                (turn_id,),
            )
            if cursor.rowcount != 1:
                raise BudgetConflictError(tr("service.turn_inactive"))
            connection.execute("UPDATE turns SET request_sent=0 WHERE id=?", (turn_id,))
            self._release_reservation(
                connection,
                turn,
                budget,
                mode,
                error_type,
                AccountingStatus.RELEASED,
                updated_at,
            )

    def mark_unknown_outcome(
        self,
        turn_id: str,
        *,
        assistant_message_id: str,
        partial_content: str | None,
        requested_model_id: str,
        actual_model_id: str | None,
        generation_id: str | None,
        finish_reason: str | None,
        error_type: ChatErrorType,
        updated_at: datetime,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        usage_source: str = "api",
        cost: Decimal | None = None,
        cost_source: str = "unknown",
        cached_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        attempt_sequence: int | None = None,
    ) -> None:
        self.finalize_known_turn(
            turn_id,
            assistant_message_id=assistant_message_id,
            content=partial_content,
            successful=False,
            requested_model_id=requested_model_id,
            actual_model_id=actual_model_id,
            generation_id=generation_id,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            usage_source=usage_source,
            cost_source=cost_source,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            attempt_sequence=attempt_sequence,
            error_type=error_type,
            generated_title=None,
            updated_at=updated_at,
        )

    def release_unknown_reservation(
        self,
        turn_id: str,
        updated_at: datetime,
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection("write", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM turns WHERE id = ?",
                (turn_id,),
            ).fetchone()
            if row is None:
                raise KeyError(tr("service.turn_missing"))
            turn = _turn_from_row(row)
            if turn.accounting_status is not AccountingStatus.UNKNOWN:
                raise BudgetConflictError(tr("service.reserve_not_unknown"))
            budget_row = _connection_budget_row(
                connection, turn.chat_id, turn.provider_id
            )
            assert budget_row is not None
            budget = _budget_from_row(budget_row)
            mode_row = connection.execute(
                "SELECT mode FROM chats WHERE id = ?",
                (turn.chat_id,),
            ).fetchone()
            assert mode_row is not None
            mode = ChatMode(str(mode_row["mode"]))
            self._release_reservation(
                connection,
                turn,
                budget,
                mode,
                turn.error_type or ChatErrorType.ACCOUNTING_UNKNOWN,
                AccountingStatus.RELEASED,
                updated_at,
            )

    def update_attempt_accounting(
        self,
        sequence: int,
        *,
        updated_at: datetime,
        actual_model_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost: Decimal | None = None,
        usage_source: str = "api",
        cost_source: str = "api",
        cached_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        """Refine one immutable dispatch, applying only its accounting delta.

        A delayed result for a previous retry cannot replace the current turn.
        Replaying the same refinement produces zero budget delta.
        """
        _require_positive_int(sequence, "attempt")
        for value in (
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cached_tokens,
            reasoning_tokens,
        ):
            if value is not None:
                _require_nonnegative_int(value, "usage")
        if cost is not None:
            _require_decimal(cost, "cost")
        if usage_source not in {"api", "estimated", "unknown"} or cost_source not in {
            "api",
            "estimated",
            "unknown",
        }:
            raise ValueError("accounting_source_invalid")
        with self._connection("write") as connection:
            connection.execute("BEGIN IMMEDIATE")
            ensure_request_attempts(connection)
            row = connection.execute(
                "SELECT * FROM chat_request_attempts WHERE sequence=?", (sequence,)
            ).fetchone()
            if row is None:
                raise KeyError("attempt_missing")
            if row["status"] == TurnStatus.PENDING.value:
                raise BudgetConflictError("attempt_still_active")
            prior = dict(row)
            newer = dict(row)
            for name, value in (
                ("actual_model_id", actual_model_id),
                ("prompt_tokens", prompt_tokens),
                ("completion_tokens", completion_tokens),
                ("total_tokens", total_tokens),
                ("cost", str(cost) if cost is not None else None),
                ("cached_tokens", cached_tokens),
                ("reasoning_tokens", reasoning_tokens),
            ):
                if value is not None:
                    if (
                        name == "cost"
                        and prior["cost_source"] == "api"
                        and cost_source != "api"
                    ):
                        continue
                    if (
                        name.endswith("tokens")
                        and prior["usage_source"] == "api"
                        and usage_source != "api"
                    ):
                        continue
                    newer[name] = value
            if any(
                value is not None
                for value in (prompt_tokens, completion_tokens, total_tokens)
            ) and (prior["usage_source"] != "api" or usage_source == "api"):
                newer["usage_source"] = usage_source
            if cost is not None and (
                prior["cost_source"] != "api" or cost_source == "api"
            ):
                newer["cost_source"] = cost_source
            complete_usage = newer["usage_source"] == "api" and all(
                newer[name] is not None
                for name in ("prompt_tokens", "completion_tokens", "total_tokens")
            )
            complete_cost = newer["cost_source"] == "api" and newer["cost"] is not None
            newer["accounting_status"] = (
                "final" if complete_usage and complete_cost else "unknown"
            )
            fields = (
                "actual_model_id",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cost",
                "usage_source",
                "cost_source",
                "cached_tokens",
                "reasoning_tokens",
                "accounting_status",
            )
            if all(prior[name] == newer[name] for name in fields):
                return
            connection.execute(
                "UPDATE chat_request_attempts SET "
                + ",".join(name + "=?" for name in fields)
                + " WHERE sequence=?",
                tuple(newer[name] for name in fields) + (sequence,),
            )
            budget_row = _connection_budget_row(
                connection, str(row["chat_id"]), ProviderId(str(row["provider_id"]))
            )
            assert budget_row is not None
            budget = _budget_from_row(budget_row)

            def token(record: dict, name: str) -> int:
                if record["usage_source"] != "api":
                    return 0
                if name == "total_tokens":
                    return max(
                        int(record[name] or 0),
                        int(record["prompt_tokens"] or 0)
                        + int(record["completion_tokens"] or 0),
                    )
                return int(record[name] or 0)

            delta_tokens = [
                token(newer, name) - token(prior, name)
                for name in ("prompt_tokens", "completion_tokens", "total_tokens")
            ]

            def amount(record: dict) -> Decimal:
                return (
                    Decimal(str(record["cost"]))
                    if record["cost_source"] == "api" and record["cost"] is not None
                    else Decimal("0")
                )

            used_cost = budget.cost_used + amount(newer) - amount(prior)
            held_tokens = budget.reserved_tokens
            held_cost = budget.cost_reserved
            latest = connection.execute(
                "SELECT MAX(sequence) FROM chat_request_attempts WHERE turn_id=?",
                (row["turn_id"],),
            ).fetchone()[0]
            turn_row = connection.execute(
                "SELECT * FROM turns WHERE id=?", (row["turn_id"],)
            ).fetchone()
            if latest == sequence and turn_row is not None and turn_row["request_sent"]:
                turn = _turn_from_row(turn_row)
                if complete_usage:
                    held_tokens -= turn.reserved_tokens
                if complete_cost:
                    held_cost -= turn.reserved_cost
                connection.execute(
                    "UPDATE turns SET "
                    + ",".join(name + "=?" for name in fields)
                    + ",reserved_tokens=?,reserved_cost=?,updated_at=? WHERE id=?",
                    tuple(newer[name] for name in fields)
                    + (
                        0 if complete_usage else turn.reserved_tokens,
                        str(Decimal("0") if complete_cost else turn.reserved_cost),
                        _datetime_text(updated_at),
                        turn.id,
                    ),
                )
            if held_tokens < 0 or held_cost < 0:
                raise BudgetConflictError(tr("service.reserve_corrupt"))
            unknown = (
                connection.execute(
                    "SELECT 1 FROM chat_request_attempts WHERE chat_id=? AND accounting_status='unknown' LIMIT 1",
                    (row["chat_id"],),
                ).fetchone()
                is not None
            )
            mode_row = connection.execute(
                "SELECT mode FROM chats WHERE id=?", (row["chat_id"],)
            ).fetchone()
            assert mode_row is not None
            state = _calculate_state(
                mode=ChatMode(str(mode_row["mode"])),
                token_limit=budget.token_limit,
                total_used=budget.total_tokens_used + delta_tokens[2],
                reserved_tokens=held_tokens,
                cost_limit=budget.cost_limit,
                cost_used=used_cost,
                cost_reserved=held_cost,
                accounting_unknown=unknown,
            )
            write_money(
                connection,
                str(row["chat_id"]),
                ProviderId(str(row["provider_id"])),
                Currency(str(row["currency"])),
                cost_limit=budget.cost_limit,
                cost_used=used_cost,
                cost_reserved=held_cost,
                updated_at=_datetime_text(updated_at),
            )
            connection.execute(
                "UPDATE chat_budgets SET prompt_tokens_used=?,completion_tokens_used=?,total_tokens_used=?,cost_used=?,reserved_tokens=?,cost_reserved=?,state=?,updated_at=? WHERE chat_id=?",
                (
                    budget.prompt_tokens_used + delta_tokens[0],
                    budget.completion_tokens_used + delta_tokens[1],
                    budget.total_tokens_used + delta_tokens[2],
                    str(used_cost),
                    held_tokens,
                    str(held_cost),
                    state.value,
                    _datetime_text(updated_at),
                    row["chat_id"],
                ),
            )

    def get_turn(self, turn_id: str) -> TurnRecord | None:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM turns WHERE id = ?",
                (turn_id,),
            ).fetchone()
        return _turn_from_row(row) if row is not None else None

    def list_turns(self, chat_id: str) -> list[TurnRecord]:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM turns
                WHERE chat_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (chat_id,),
            ).fetchall()
        return [_turn_from_row(row) for row in rows]

    def get_last_request(self, chat_id: str) -> LastRequestMetrics:
        """Read the latest dispatch, without deriving chronology from turns."""
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            if has_request_attempts(connection):
                row = connection.execute(
                    "SELECT * FROM chat_request_attempts WHERE chat_id=? "
                    "ORDER BY sequence DESC LIMIT 1",
                    (chat_id,),
                ).fetchone()
                if row is not None:
                    return _last_request_from_row(row)
            legacy = connection.execute(
                "SELECT 1 FROM turns WHERE chat_id=? AND request_sent=1 LIMIT 1",
                (chat_id,),
            ).fetchone()
        return LastRequestMetrics(
            LastRequestState.UNKNOWN if legacy else LastRequestState.NONE,
            chronology_known=legacy is None,
        )

    def get_user_message_for_turn(self, turn_id: str) -> Message | None:
        _require_identifier(turn_id, tr("service.label.turn"))
        with self._connection() as connection:
            seen: set[str] = set()
            while turn_id not in seen:
                seen.add(turn_id)
                row = connection.execute(
                    "SELECT * FROM messages WHERE turn_id=? AND role='user'", (turn_id,)
                ).fetchone()
                if row is not None:
                    return _message_from_row(row)
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(turns)")
                }
                if "retry_of_turn_id" not in columns:
                    return None
                parent = connection.execute(
                    "SELECT retry_of_turn_id FROM turns WHERE id=?", (turn_id,)
                ).fetchone()
                if parent is None or parent[0] is None:
                    return None
                turn_id = str(parent[0])
        return None

    def update_price_snapshot(
        self,
        chat_id: str,
        *,
        prompt_price: Decimal,
        completion_price: Decimal,
        request_price: Decimal,
        internal_reasoning_price: Decimal,
        cache_read_price: Decimal,
        cache_write_price: Decimal,
        overrides_json: str,
        updated_at: datetime,
        expected_connection_revision: int | None = None,
        expected_provider_id: ProviderId | None = None,
        expected_model_id: str | None = None,
    ) -> None:
        _require_identifier(chat_id, tr("service.label.chat"))
        for value, label in (
            (prompt_price, tr("service.label.prompt_price")),
            (completion_price, tr("service.label.completion_price")),
            (request_price, tr("service.label.request_price")),
            (internal_reasoning_price, tr("service.label.reasoning_price")),
            (cache_read_price, tr("service.label.cache_read_price")),
            (cache_write_price, tr("service.label.cache_write_price")),
        ):
            _require_decimal(value, label)
        _require_text(overrides_json, tr("service.label.overrides"))
        with self._connection("write", chat_id=chat_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM chats WHERE id=?", (chat_id,)
            ).fetchone()
            if current is None:
                raise KeyError(tr("service.chat_missing"))
            if (
                expected_connection_revision is not None
                and current["connection_revision"] != expected_connection_revision
                or expected_provider_id is not None
                and current["provider_id"] != expected_provider_id.value
                or expected_model_id is not None
                and current["requested_model_id"] != expected_model_id
            ):
                raise BudgetConflictError("chat_connection_changed")
            overrides_json = with_new_prices(connection, chat_id, overrides_json)
            cursor = connection.execute(
                """
                UPDATE chats
                SET prompt_price_per_token = ?, completion_price_per_token = ?,
                    request_price = ?, internal_reasoning_price_per_token = ?,
                    input_cache_read_price_per_token = ?,
                    input_cache_write_price_per_token = ?,
                    pricing_overrides_json = ?, pricing_snapshot_complete = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    _decimal_text(prompt_price),
                    _decimal_text(completion_price),
                    _decimal_text(request_price),
                    _decimal_text(internal_reasoning_price),
                    _decimal_text(cache_read_price),
                    _decimal_text(cache_write_price),
                    overrides_json,
                    _datetime_text(updated_at),
                    chat_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(tr("service.chat_missing"))

    def _prepare_retry(
        self,
        connection: sqlite3.Connection,
        reservation: BudgetReservation,
        requested_model_id: str,
    ) -> None:
        if reservation.retry_of_turn_id is not None:
            prior = connection.execute(
                "SELECT * FROM turns WHERE id=? AND chat_id=?",
                (reservation.retry_of_turn_id, reservation.chat_id),
            ).fetchone()
            if (
                prior is None
                or prior["status"] != "failed"
                or prior["accounting_status"] != "released"
            ):
                raise BudgetConflictError(tr("service.turn_not_ready"))
            if (
                connection.execute(
                    "SELECT 1 FROM turns WHERE retry_of_turn_id=? LIMIT 1",
                    (reservation.retry_of_turn_id,),
                ).fetchone()
                is not None
            ):
                raise BudgetConflictError(tr("service.turn_not_ready"))
            current = connection.execute(
                "SELECT provider_id,currency,connection_revision FROM chats WHERE id=?",
                (reservation.chat_id,),
            ).fetchone()
            assert current is not None
            connection.execute(
                "INSERT INTO turns(id,chat_id,status,requested_model_id,reserved_tokens,reserved_cost,provider_id,currency,connection_revision,retry_of_turn_id,accounting_status,request_sent,created_at,updated_at) VALUES(?,?,'pending',?,?,?,?,?,?,?,'reserved',0,?,?)",
                (
                    reservation.turn_id,
                    reservation.chat_id,
                    requested_model_id,
                    reservation.reserved_tokens,
                    str(reservation.reserved_cost),
                    current["provider_id"],
                    current["currency"],
                    current["connection_revision"],
                    reservation.retry_of_turn_id,
                    _datetime_text(reservation.created_at),
                    _datetime_text(reservation.created_at),
                ),
            )
            return
        row = connection.execute(
            "SELECT * FROM turns WHERE id = ? AND chat_id = ?",
            (reservation.turn_id, reservation.chat_id),
        ).fetchone()
        if row is None:
            raise KeyError(tr("service.turn_missing"))
        turn = _turn_from_row(row)
        if (
            turn.status is not TurnStatus.FAILED
            or turn.accounting_status is not AccountingStatus.RELEASED
        ):
            raise BudgetConflictError(tr("service.turn_not_ready"))
        connection.execute(
            """
            UPDATE turns
            SET status = 'pending', requested_model_id = ?,
                actual_model_id = NULL, generation_id = NULL,
                finish_reason = NULL, prompt_tokens = NULL,
                completion_tokens = NULL, total_tokens = NULL,
                cost = NULL, reserved_tokens = ?, reserved_cost = ?,
                usage_source='unknown',cost_source='unknown',cached_tokens=NULL,reasoning_tokens=NULL,
                accounting_status = 'reserved', error_type = NULL,
                request_sent = 0, updated_at = ?
            WHERE id = ?
            """,
            (
                requested_model_id,
                reservation.reserved_tokens,
                _decimal_text(reservation.reserved_cost),
                _datetime_text(reservation.created_at),
                reservation.turn_id,
            ),
        )
        connection.execute(
            """
            UPDATE messages
            SET status = 'pending', requested_model_id = ?, updated_at = ?
            WHERE chat_id = ? AND turn_id = ? AND role = 'user'
            """,
            (
                requested_model_id,
                _datetime_text(reservation.created_at),
                reservation.chat_id,
                reservation.turn_id,
            ),
        )

    def _load_active_turn(
        self,
        connection: sqlite3.Connection,
        turn_id: str,
    ) -> tuple[TurnRecord, ChatBudget, ChatMode]:
        row = connection.execute(
            "SELECT * FROM turns WHERE id = ?",
            (turn_id,),
        ).fetchone()
        if row is None:
            raise KeyError(tr("service.turn_missing"))
        turn = _turn_from_row(row)
        if self.access is not None:
            with self.access.authorize(
                "finish", chat_id=turn.chat_id, record_id=turn.id
            ):
                pass
        if turn.status is not TurnStatus.PENDING:
            raise BudgetConflictError(tr("service.turn_inactive"))
        budget_row = _connection_budget_row(connection, turn.chat_id, turn.provider_id)
        mode_row = connection.execute(
            "SELECT mode FROM chats WHERE id = ?",
            (turn.chat_id,),
        ).fetchone()
        assert budget_row is not None and mode_row is not None
        return (
            turn,
            _budget_from_row(budget_row),
            ChatMode(str(mode_row["mode"])),
        )

    def _release_reservation(
        self,
        connection: sqlite3.Connection,
        turn: TurnRecord,
        budget: ChatBudget,
        mode: ChatMode,
        error_type: ChatErrorType,
        accounting_status: AccountingStatus,
        updated_at: datetime,
    ) -> None:
        new_tokens = budget.reserved_tokens - turn.reserved_tokens
        new_cost = budget.cost_reserved - turn.reserved_cost
        if new_tokens < 0 or new_cost < 0:
            raise BudgetConflictError(tr("service.reserve_corrupt"))
        has_other_unknown = (
            connection.execute(
                """
            SELECT 1 FROM turns
            WHERE chat_id = ? AND id != ? AND accounting_status = 'unknown'
            LIMIT 1
            """,
                (turn.chat_id, turn.id),
            ).fetchone()
            is not None
        )
        state = _calculate_state(
            mode=mode,
            token_limit=budget.token_limit,
            total_used=budget.total_tokens_used,
            reserved_tokens=new_tokens,
            cost_limit=budget.cost_limit,
            cost_used=budget.cost_used,
            cost_reserved=new_cost,
            accounting_unknown=has_other_unknown,
        )
        connection.execute(
            """
            UPDATE chat_budgets
            SET reserved_tokens = ?, cost_reserved = ?,
                state = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (
                new_tokens,
                _decimal_text(new_cost),
                state.value,
                _datetime_text(updated_at),
                turn.chat_id,
            ),
        )
        write_money(
            connection,
            turn.chat_id,
            turn.provider_id,
            turn.currency,
            cost_limit=budget.cost_limit,
            cost_used=budget.cost_used,
            cost_reserved=new_cost,
            updated_at=_datetime_text(updated_at),
        )
        connection.execute(
            """
            UPDATE turns
            SET status = 'failed', accounting_status = ?,
                error_type = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                accounting_status.value,
                error_type.value,
                _datetime_text(updated_at),
                turn.id,
            ),
        )
        connection.execute(
            """
            UPDATE messages
            SET status = 'failed', updated_at = ?
            WHERE chat_id = ? AND turn_id = ? AND role = 'user'
            """,
            (_datetime_text(updated_at), turn.chat_id, turn.id),
        )
        synchronize_request_attempt(connection, turn.id)

    def _upsert_assistant_message(
        self,
        connection: sqlite3.Connection,
        *,
        turn: TurnRecord,
        message_id: str,
        content: str,
        successful: bool,
        requested_model_id: str,
        actual_model_id: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        updated_at: datetime,
    ) -> None:
        existing = connection.execute(
            """
            SELECT id FROM messages
            WHERE chat_id = ? AND turn_id = ? AND role = 'assistant'
            """,
            (turn.chat_id, turn.id),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO messages (
                    id, chat_id, turn_id, role, content, status,
                    requested_model_id, actual_model_id,
                    prompt_tokens, completion_tokens, total_tokens,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    turn.chat_id,
                    turn.id,
                    encrypt_value(
                        connection,
                        content,
                        table="messages",
                        field="content",
                        record_id=message_id,
                        chat_id=turn.chat_id,
                        role="assistant",
                    ),
                    MessageStatus.SENT.value
                    if successful
                    else MessageStatus.FAILED.value,
                    requested_model_id,
                    actual_model_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    _datetime_text(updated_at),
                    _datetime_text(updated_at),
                ),
            )
            return
        connection.execute(
            """
            UPDATE messages
            SET content = ?, status = ?, requested_model_id = ?,
                actual_model_id = ?, prompt_tokens = ?,
                completion_tokens = ?, total_tokens = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                encrypt_value(
                    connection,
                    content,
                    table="messages",
                    field="content",
                    record_id=str(existing["id"]),
                    chat_id=turn.chat_id,
                    role="assistant",
                ),
                MessageStatus.SENT.value if successful else MessageStatus.FAILED.value,
                requested_model_id,
                actual_model_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                _datetime_text(updated_at),
                str(existing["id"]),
            ),
        )

    @contextmanager
    def _connection(
        self, operation: str = "read", *, chat_id: str = "", record_id: str = ""
    ) -> Iterator[sqlite3.Connection]:
        with protected_connection(
            self.path, self.access, operation, chat_id=chat_id, record_id=record_id
        ) as connection:
            if operation != "read":
                connection.execute("BEGIN IMMEDIATE")
                ensure_provider_schema(connection)
                connection.commit()
            yield connection
            if operation != "read":
                _synchronize_legacy_money(
                    connection, chat_id=chat_id, record_id=record_id
                )
                affected = chat_id
                if not affected and record_id:
                    row = connection.execute(
                        "SELECT chat_id FROM turns WHERE id=?", (record_id,)
                    ).fetchone()
                    affected = str(row[0]) if row else ""
                for row in connection.execute(
                    "SELECT id FROM chats" + (" WHERE id=?" if affected else ""),
                    (affected,) if affected else (),
                ).fetchall():
                    refresh_active_projection(connection, str(row[0]))


def _synchronize_legacy_money(
    connection: sqlite3.Connection, *, chat_id: str = "", record_id: str = ""
) -> None:
    if not chat_id and record_id:
        row = connection.execute(
            "SELECT chat_id FROM turns WHERE id=?", (record_id,)
        ).fetchone()
        if row is not None:
            chat_id = str(row[0])
    where = " WHERE chat_id=?" if chat_id else ""
    parameters = (chat_id,) if chat_id else ()
    connection.execute(
        "UPDATE chat_budgets SET cost_limit_usd=CASE WHEN currency='USD' THEN cost_limit ELSE NULL END,cost_used_usd=CASE WHEN currency='USD' THEN cost_used ELSE '0' END,cost_reserved_usd=CASE WHEN currency='USD' THEN cost_reserved ELSE '0' END"
        + where,
        parameters,
    )
    turn_where = " WHERE id=?" if record_id else where
    turn_parameters = (record_id,) if record_id else parameters
    connection.execute(
        "UPDATE turns SET cost_usd=CASE WHEN currency='USD' THEN cost ELSE NULL END,reserved_cost_usd=CASE WHEN currency='USD' THEN reserved_cost ELSE '0' END"
        + turn_where,
        turn_parameters,
    )
    if has_request_attempts(connection) and request_attempts_are_extended(connection):
        attempt_where = (
            " WHERE sequence=(SELECT MAX(sequence) FROM chat_request_attempts WHERE turn_id=?)"
            if record_id
            else where
        )
        connection.execute(
            "UPDATE chat_request_attempts SET cost_usd=CASE WHEN currency='USD' THEN cost ELSE NULL END"
            + attempt_where,
            turn_parameters if record_id else parameters,
        )


def _budget_from_row(row: Mapping) -> ChatBudget:
    return ChatBudget(
        chat_id=str(row["chat_id"]),
        limits_configured=bool(row["limits_configured"]),
        token_limit=_optional_int(row["token_limit"]),
        max_completion_tokens=_optional_int(row["max_completion_tokens"]),
        prompt_tokens_used=int(row["prompt_tokens_used"]),
        completion_tokens_used=int(row["completion_tokens_used"]),
        total_tokens_used=int(row["total_tokens_used"]),
        reserved_tokens=int(row["reserved_tokens"]),
        cost_limit_usd=_optional_decimal(
            row["cost_limit"]
            if "cost_limit" in row.keys() and row["currency"] == "USD"
            else row["cost_limit_usd"]
        ),
        cost_used_usd=Decimal(
            str(
                row["cost_used"]
                if "cost_used" in row.keys() and row["currency"] == "USD"
                else row["cost_used_usd"]
            )
        ),
        cost_reserved_usd=Decimal(
            str(
                row["cost_reserved"]
                if "cost_reserved" in row.keys() and row["currency"] == "USD"
                else row["cost_reserved_usd"]
            )
        ),
        provider_id=ProviderId(str(row["provider_id"]))
        if "provider_id" in row.keys()
        else ProviderId.OPENROUTER,
        currency=Currency(str(row["currency"]))
        if "currency" in row.keys()
        else Currency.USD,
        cost_limit=_optional_decimal(
            row["cost_limit"] if "cost_limit" in row.keys() else row["cost_limit_usd"]
        ),
        cost_used=Decimal(
            str(row["cost_used"] if "cost_used" in row.keys() else row["cost_used_usd"])
        ),
        cost_reserved=Decimal(
            str(
                row["cost_reserved"]
                if "cost_reserved" in row.keys()
                else row["cost_reserved_usd"]
            )
        ),
        state=BudgetState(str(row["state"])),
        updated_at=_parse_datetime(str(row["updated_at"])),
    )


def _turn_from_row(row: sqlite3.Row) -> TurnRecord:
    raw_error = row["error_type"]
    error_type = ChatErrorType(str(raw_error)) if raw_error is not None else None
    return TurnRecord(
        id=str(row["id"]),
        chat_id=str(row["chat_id"]),
        status=TurnStatus(str(row["status"])),
        requested_model_id=str(row["requested_model_id"]),
        actual_model_id=_optional_str(row["actual_model_id"]),
        generation_id=_optional_str(row["generation_id"]),
        finish_reason=_optional_str(row["finish_reason"]),
        prompt_tokens=_optional_int(row["prompt_tokens"]),
        completion_tokens=_optional_int(row["completion_tokens"]),
        total_tokens=_optional_int(row["total_tokens"]),
        cost_usd=_optional_decimal(row["cost_usd"]),
        reserved_tokens=int(row["reserved_tokens"]),
        reserved_cost_usd=Decimal(str(row["reserved_cost_usd"])),
        connection_revision=int(row["connection_revision"])
        if "connection_revision" in row.keys()
        else 0,
        retry_of_turn_id=_optional_str(row["retry_of_turn_id"])
        if "retry_of_turn_id" in row.keys()
        else None,
        provider_id=ProviderId(str(row["provider_id"]))
        if "provider_id" in row.keys()
        else ProviderId.OPENROUTER,
        currency=Currency(str(row["currency"]))
        if "currency" in row.keys()
        else Currency.USD,
        cost=_optional_decimal(
            row["cost"] if "cost" in row.keys() else row["cost_usd"]
        ),
        reserved_cost=Decimal(
            str(
                row["reserved_cost"]
                if "reserved_cost" in row.keys()
                else row["reserved_cost_usd"]
            )
        ),
        usage_source=str(row["usage_source"])
        if "usage_source" in row.keys()
        else "unknown",
        cost_source=str(row["cost_source"])
        if "cost_source" in row.keys()
        else "unknown",
        accounting_status=AccountingStatus(str(row["accounting_status"])),
        error_type=error_type,
        request_sent=bool(row["request_sent"]),
        created_at=_parse_datetime(str(row["created_at"])),
        updated_at=_parse_datetime(str(row["updated_at"])),
    )


def _last_request_from_row(row: sqlite3.Row) -> LastRequestMetrics:
    known = bool(row["chronology_known"])
    sent_at = _parse_datetime(str(row["sent_at"])) if row["sent_at"] else None
    if not known:
        return LastRequestMetrics(LastRequestState.UNKNOWN, chronology_known=False)
    state = (
        LastRequestState.PENDING
        if row["status"] == TurnStatus.PENDING.value
        else LastRequestState.FINAL
        if row["accounting_status"] == AccountingStatus.FINAL.value
        else LastRequestState.UNKNOWN
    )
    final = state is LastRequestState.FINAL
    return LastRequestMetrics(
        state=state,
        connection_revision=int(row["connection_revision"])
        if "connection_revision" in row.keys()
        else 0,
        turn_id=str(row["turn_id"]),
        prompt_tokens=_optional_int(row["prompt_tokens"]),
        completion_tokens=_optional_int(row["completion_tokens"]),
        total_tokens=_optional_int(row["total_tokens"]),
        cost_usd=_optional_decimal(row["cost_usd"]),
        cost=_optional_decimal(
            row["cost"] if "cost" in row.keys() else row["cost_usd"]
        ),
        currency=Currency(str(row["currency"]))
        if "currency" in row.keys()
        else Currency.USD,
        provider_id=ProviderId(str(row["provider_id"]))
        if "provider_id" in row.keys()
        else ProviderId.OPENROUTER,
        usage_source=str(row["usage_source"])
        if "usage_source" in row.keys()
        else "api"
        if final
        else "unknown",
        cost_source=str(row["cost_source"])
        if "cost_source" in row.keys()
        else "api"
        if final
        else "unknown",
        sent_at=sent_at,
        attempt_sequence=int(row["sequence"]),
    )


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        id=str(row["id"]),
        chat_id=str(row["chat_id"]),
        turn_id=str(row["turn_id"]),
        role=MessageRole(str(row["role"])),
        content=str(row["content"]),
        status=MessageStatus(str(row["status"])),
        requested_model_id=_optional_str(row["requested_model_id"]),
        actual_model_id=_optional_str(row["actual_model_id"]),
        prompt_tokens=_optional_int(row["prompt_tokens"]),
        completion_tokens=_optional_int(row["completion_tokens"]),
        total_tokens=_optional_int(row["total_tokens"]),
        created_at=_parse_datetime(str(row["created_at"])),
    )


def _calculate_state(
    *,
    mode: ChatMode,
    token_limit: int | None,
    total_used: int,
    reserved_tokens: int,
    cost_limit: Decimal | None,
    cost_used: Decimal,
    cost_reserved: Decimal,
    accounting_unknown: bool,
) -> BudgetState:
    if accounting_unknown:
        return BudgetState.ACCOUNTING_UNKNOWN
    if token_limit is None:
        return BudgetState.UNCONFIGURED
    if total_used + reserved_tokens >= token_limit:
        return BudgetState.EXHAUSTED
    if mode is ChatMode.FREE and cost_used + cost_reserved > 0:
        return BudgetState.EXHAUSTED
    if (
        mode is ChatMode.PAID
        and cost_limit is not None
        and cost_used + cost_reserved >= cost_limit
    ):
        return BudgetState.EXHAUSTED
    return BudgetState.READY


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        raise ValueError(tr("service.decimal_invalid"))
    return str(value)


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(tr("service.integer_invalid"))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.identifier_invalid", field=label))


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(tr("service.field_invalid", field=label))


def _require_nonnegative_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(tr("service.field_invalid", field=label))


def _require_positive_int(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(tr("service.field_invalid", field=label))


def _require_decimal(value: object, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < Decimal("0"):
        raise ValueError(tr("service.field_invalid", field=label))


def _require_bool(value: object, label: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(tr("service.field_invalid", field=label))
