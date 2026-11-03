"""Транзакционный SQLite-репозиторий бюджетов и попыток генерации."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
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
from chat.drafts import ChatDraft
from chat.errors import ChatErrorType
from chat.metrics import LastRequestMetrics, LastRequestState
from chat.models import ChatMode, Message, MessageRole, MessageStatus
from chat.paid_consent import PaidConsentRevoked
from i18n import tr
from storage.chat_preferences import policy_from_read, with_new_prices
from storage.database_connections import (
    ContentAccess,
    encrypt_value,
)
from storage.database_connections import (
    connection as protected_connection,
)
from storage.request_attempts import (
    ensure_request_attempts,
    has_request_attempts,
    record_request_attempt,
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

    def get_chat_budget(self, chat_id: str) -> ChatBudget | None:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_budgets WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
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
        cost_limit_usd: Decimal,
        *,
        cost_increase_confirmed: bool,
        updated_at: datetime,
    ) -> ChatBudget:
        _require_identifier(chat_id, tr("service.label.chat"))
        _require_positive_int(token_limit, tr("service.label.token_budget"))
        _require_positive_int(max_completion_tokens, tr("service.label.completion"))
        _require_decimal(cost_limit_usd, tr("service.label.money_budget"))
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
            mode = ChatMode(str(row["mode"]))
            current = _budget_from_row(row)
            minimum_tokens = current.total_tokens_used + current.reserved_tokens
            if token_limit < minimum_tokens:
                raise BudgetConflictError(tr("service.tokens_below_used"))
            minimum_cost = current.cost_used_usd + current.cost_reserved_usd
            if cost_limit_usd < minimum_cost:
                raise BudgetConflictError(tr("service.money_below_used"))
            if (
                mode is ChatMode.PAID
                and current.cost_limit_usd is not None
                and cost_limit_usd > current.cost_limit_usd
                and not cost_increase_confirmed
            ):
                raise BudgetConflictError(tr("service.money_increase_confirmation"))
            state = _calculate_state(
                mode=mode,
                token_limit=token_limit,
                total_used=current.total_tokens_used,
                reserved_tokens=current.reserved_tokens,
                cost_limit=cost_limit_usd,
                cost_used=current.cost_used_usd,
                cost_reserved=current.cost_reserved_usd,
                accounting_unknown=(current.state is BudgetState.ACCOUNTING_UNKNOWN),
            )
            connection.execute(
                """
                UPDATE chat_budgets
                SET limits_configured = 1,
                    token_limit = ?,
                    max_completion_tokens = ?,
                    cost_limit_usd = ?,
                    state = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    token_limit,
                    max_completion_tokens,
                    _decimal_text(cost_limit_usd),
                    state.value,
                    _datetime_text(updated_at),
                    chat_id,
                ),
            )
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
    ) -> ChatDraft | None:
        if not isinstance(reservation, BudgetReservation):
            raise ValueError(tr("service.reserve_object_invalid"))
        _require_identifier(reservation.turn_id, tr("service.label.turn"))
        _require_identifier(reservation.user_message_id, tr("service.label.message"))
        _require_identifier(reservation.chat_id, tr("service.label.chat"))
        _require_nonnegative_int(
            reservation.reserved_tokens, tr("service.label.token_reserve")
        )
        _require_decimal(
            reservation.reserved_cost_usd, tr("service.label.money_reserve")
        )
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
            budget = _budget_from_row(row)
            mode = ChatMode(str(row["mode"]))
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
            if budget.state is BudgetState.ACCOUNTING_UNKNOWN:
                raise BudgetConflictError(tr("service.previous_unknown"))
            if budget.token_limit is None:
                raise BudgetConflictError(tr("service.token_budget_missing"))
            token_remaining = (
                budget.token_limit - budget.total_tokens_used - budget.reserved_tokens
            )
            if reservation.reserved_tokens > token_remaining:
                raise BudgetConflictError(tr("service.token_budget_insufficient"))
            new_cost_reserved = budget.cost_reserved_usd + reservation.reserved_cost_usd
            if mode is ChatMode.PAID:
                if budget.cost_limit_usd is None:
                    raise BudgetConflictError(tr("service.money_budget_missing"))
                if budget.cost_used_usd + new_cost_reserved > budget.cost_limit_usd:
                    raise BudgetConflictError(tr("service.money_budget_insufficient"))
            elif reservation.reserved_cost_usd != 0:
                raise BudgetConflictError(tr("service.free_cannot_reserve_money"))
            new_reserved_tokens = budget.reserved_tokens + reservation.reserved_tokens
            reservation_state = _calculate_state(
                mode=mode,
                token_limit=budget.token_limit,
                total_used=budget.total_tokens_used,
                reserved_tokens=new_reserved_tokens,
                cost_limit=budget.cost_limit_usd,
                cost_used=budget.cost_used_usd,
                cost_reserved=new_cost_reserved,
                accounting_unknown=False,
            )

            if retry:
                self._prepare_retry(connection, reservation, requested_model_id)
            else:
                connection.execute(
                    """
                    INSERT INTO turns (
                        id, chat_id, status, requested_model_id,
                        reserved_tokens, reserved_cost_usd,
                        accounting_status, request_sent, created_at, updated_at
                    )
                    VALUES (?, ?, 'pending', ?, ?, ?, 'reserved', 0, ?, ?)
                    """,
                    (
                        reservation.turn_id,
                        reservation.chat_id,
                        requested_model_id,
                        reservation.reserved_tokens,
                        _decimal_text(reservation.reserved_cost_usd),
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
                    cost_reserved_usd = ?,
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

    def mark_request_sent(self, turn_id: str, updated_at: datetime) -> None:
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
            record_request_attempt(connection, turn_id, _datetime_text(updated_at))

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
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: Decimal,
        error_type: ChatErrorType | None,
        generated_title: str | None,
        updated_at: datetime,
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        _require_identifier(assistant_message_id, tr("service.label.message"))
        if content is not None:
            _require_text(
                content, tr("service.label.assistant_response"), allow_empty=True
            )
        _require_bool(successful, tr("service.label.result_status"))
        _require_identifier(requested_model_id, tr("service.label.model"))
        for value, label in (
            (prompt_tokens, tr("service.label.prompt_tokens")),
            (completion_tokens, tr("service.label.completion_tokens")),
            (total_tokens, tr("service.label.total_tokens")),
        ):
            _require_nonnegative_int(value, label)
        _require_decimal(cost_usd, tr("service.label.result_cost"))
        safe_total = max(total_tokens, prompt_tokens + completion_tokens)
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn, budget, mode = self._load_active_turn(connection, turn_id)
            new_reserved_tokens = budget.reserved_tokens - turn.reserved_tokens
            new_reserved_cost = budget.cost_reserved_usd - turn.reserved_cost_usd
            if new_reserved_tokens < 0 or new_reserved_cost < 0:
                raise BudgetConflictError(tr("service.reserve_corrupt"))
            new_prompt = budget.prompt_tokens_used + prompt_tokens
            new_completion = budget.completion_tokens_used + completion_tokens
            new_total = budget.total_tokens_used + safe_total
            new_cost = budget.cost_used_usd + cost_usd
            state = _calculate_state(
                mode=mode,
                token_limit=budget.token_limit,
                total_used=new_total,
                reserved_tokens=new_reserved_tokens,
                cost_limit=budget.cost_limit_usd,
                cost_used=new_cost,
                cost_reserved=new_reserved_cost,
                accounting_unknown=False,
            )
            connection.execute(
                """
                UPDATE chat_budgets
                SET prompt_tokens_used = ?, completion_tokens_used = ?,
                    total_tokens_used = ?, reserved_tokens = ?,
                    cost_used_usd = ?, cost_reserved_usd = ?,
                    state = ?, updated_at = ?
                WHERE chat_id = ?
                """,
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
            connection.execute(
                """
                UPDATE turns
                SET status = ?, actual_model_id = ?, generation_id = ?,
                    finish_reason = ?, prompt_tokens = ?, completion_tokens = ?,
                    total_tokens = ?, cost_usd = ?, accounting_status = 'final',
                    error_type = ?, updated_at = ?
                WHERE id = ?
                """,
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
                    safe_total,
                    _decimal_text(cost_usd),
                    error_type.value if error_type else None,
                    _datetime_text(updated_at),
                    turn_id,
                ),
            )
            connection.execute(
                """
                UPDATE messages
                SET status = ?, updated_at = ?
                WHERE chat_id = ? AND turn_id = ? AND role = 'user'
                """,
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
                    total_tokens=safe_total,
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
                    "UPDATE chats SET updated_at = ? WHERE id = ?",
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
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        _require_identifier(assistant_message_id, tr("service.label.message"))
        if partial_content is not None:
            _require_text(
                partial_content, tr("service.label.partial_response"), allow_empty=True
            )
        _require_identifier(requested_model_id, tr("service.label.model"))
        with self._connection("finish", record_id=turn_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn, _budget, _mode = self._load_active_turn(connection, turn_id)
            connection.execute(
                """
                UPDATE turns
                SET status = 'failed', actual_model_id = ?, generation_id = ?,
                    finish_reason = ?, accounting_status = 'unknown',
                    error_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (
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
                    error_type.value,
                    _datetime_text(updated_at),
                    turn_id,
                ),
            )
            connection.execute(
                """
                UPDATE messages
                SET status = 'failed', updated_at = ?
                WHERE chat_id = ? AND turn_id = ? AND role = 'user'
                """,
                (_datetime_text(updated_at), turn.chat_id, turn_id),
            )
            if partial_content is not None:
                self._upsert_assistant_message(
                    connection,
                    turn=turn,
                    message_id=assistant_message_id,
                    content=partial_content,
                    successful=False,
                    requested_model_id=requested_model_id,
                    actual_model_id=actual_model_id,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    updated_at=updated_at,
                )
            connection.execute(
                """
                UPDATE chat_budgets
                SET state = 'accounting_unknown', updated_at = ?
                WHERE chat_id = ?
                """,
                (_datetime_text(updated_at), turn.chat_id),
            )
            connection.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                (_datetime_text(updated_at), turn.chat_id),
            )
            synchronize_request_attempt(connection, turn_id)

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
            budget_row = connection.execute(
                "SELECT * FROM chat_budgets WHERE chat_id = ?",
                (turn.chat_id,),
            ).fetchone()
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
            row = connection.execute(
                """
                SELECT * FROM messages
                WHERE turn_id = ? AND role = 'user'
                """,
                (turn_id,),
            ).fetchone()
        return _message_from_row(row) if row is not None else None

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
                cost_usd = NULL, reserved_tokens = ?, reserved_cost_usd = ?,
                accounting_status = 'reserved', error_type = NULL,
                request_sent = 0, updated_at = ?
            WHERE id = ?
            """,
            (
                requested_model_id,
                reservation.reserved_tokens,
                _decimal_text(reservation.reserved_cost_usd),
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
        budget_row = connection.execute(
            "SELECT * FROM chat_budgets WHERE chat_id = ?",
            (turn.chat_id,),
        ).fetchone()
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
        new_cost = budget.cost_reserved_usd - turn.reserved_cost_usd
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
            cost_limit=budget.cost_limit_usd,
            cost_used=budget.cost_used_usd,
            cost_reserved=new_cost,
            accounting_unknown=has_other_unknown,
        )
        connection.execute(
            """
            UPDATE chat_budgets
            SET reserved_tokens = ?, cost_reserved_usd = ?,
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
            yield connection


def _budget_from_row(row: sqlite3.Row) -> ChatBudget:
    return ChatBudget(
        chat_id=str(row["chat_id"]),
        limits_configured=bool(row["limits_configured"]),
        token_limit=_optional_int(row["token_limit"]),
        max_completion_tokens=_optional_int(row["max_completion_tokens"]),
        prompt_tokens_used=int(row["prompt_tokens_used"]),
        completion_tokens_used=int(row["completion_tokens_used"]),
        total_tokens_used=int(row["total_tokens_used"]),
        reserved_tokens=int(row["reserved_tokens"]),
        cost_limit_usd=_optional_decimal(row["cost_limit_usd"]),
        cost_used_usd=Decimal(str(row["cost_used_usd"])),
        cost_reserved_usd=Decimal(str(row["cost_reserved_usd"])),
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
        turn_id=str(row["turn_id"]),
        prompt_tokens=_optional_int(row["prompt_tokens"]) if final else None,
        completion_tokens=_optional_int(row["completion_tokens"]) if final else None,
        total_tokens=_optional_int(row["total_tokens"]) if final else None,
        cost_usd=_optional_decimal(row["cost_usd"]) if final else None,
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
