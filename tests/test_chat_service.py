"""Тесты политики расходов и сервисного слоя чатов."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    ModelCatalog,
    PriceComponents,
)
from chat.service import (  # noqa: E402
    ChatPolicyError,
    ChatService,
    PaidConfirmationRequired,
)


class MemoryChatRepository:
    def __init__(self) -> None:
        self.chats: dict[str, Chat] = {}
        self.limits: dict[str, tuple[int, int, Decimal]] = {}

    def create_chat(self, chat: Chat) -> None:
        self.chats[chat.id] = chat

    def create_chat_with_limits(
        self,
        chat: Chat,
        *,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal,
    ) -> None:
        self.chats[chat.id] = chat
        self.limits[chat.id] = (
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )

    def list_chats(self) -> list[Chat]:
        return list(self.chats.values())

    def get_chat(self, chat_id: str) -> Chat | None:
        return self.chats.get(chat_id)

    def rename_chat(self, chat_id: str, title: str, updated_at: datetime) -> bool:
        chat = self.chats.get(chat_id)
        if chat is None:
            return False
        self.chats[chat_id] = Chat(
            id=chat.id,
            title=title,
            mode=chat.mode,
            requested_model_id=chat.requested_model_id,
            requested_model_name=chat.requested_model_name,
            prompt_price_per_token=chat.prompt_price_per_token,
            completion_price_per_token=chat.completion_price_per_token,
            created_at=chat.created_at,
            updated_at=updated_at,
        )
        return True

    def touch_chat(self, chat_id: str, updated_at: datetime) -> bool:
        chat = self.chats.get(chat_id)
        if chat is None:
            return False
        return self.rename_chat(chat_id, chat.title, updated_at)

    def delete_chat(self, chat_id: str) -> bool:
        return self.chats.pop(chat_id, None) is not None

    def list_messages(self, chat_id: str) -> list[Message]:
        _ = chat_id
        return []


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.free_model = _model("vendor/zero-price", "Zero price", "0", "0")
        self.paid_model = _model(
            "vendor/paid",
            "Paid model",
            "0.0000012",
            "0.0000034",
        )
        self.paid_model = replace(
            self.paid_model,
            request_price=Decimal("0.01"),
            internal_reasoning_price_per_token=Decimal("0.000004"),
            pricing_overrides=(
                PriceComponents(
                    prompt=Decimal("0.000002"),
                    completion=Decimal("0.000005"),
                    request=Decimal("0.02"),
                ),
            ),
        )
        self.catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL, self.free_model),
            paid_models=(self.paid_model,),
            available=True,
        )
        self.repository = MemoryChatRepository()
        self.available_limit = KeyLimitInfo.from_validated_remaining(Decimal("5"))
        self.exhausted_limit = KeyLimitInfo.from_validated_remaining(Decimal("0"))
        self.no_individual_limit = KeyLimitInfo.from_validated_remaining(None)
        self.valid_key = KeyValidityState.VALID
        self.timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        self.service = ChatService(
            self.repository,
            now=lambda: self.timestamp,
            uuid_factory=lambda: UUID("12345678-1234-5678-1234-567812345678"),
        )

    async def test_creates_free_chat_with_model_snapshot(self) -> None:
        chat = await self.service.create_chat(
            ChatMode.FREE,
            self.free_model,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.available_limit,
        )

        self.assertEqual(chat.id, "12345678-1234-5678-1234-567812345678")
        self.assertEqual(chat.title, "Новый чат")
        self.assertEqual(chat.mode, ChatMode.FREE)
        self.assertEqual(chat.requested_model_id, self.free_model.id)
        self.assertEqual(chat.requested_model_name, self.free_model.name)
        self.assertEqual(chat.prompt_price_per_token, Decimal("0"))
        self.assertEqual(chat.created_at, self.timestamp)
        self.assertEqual(self.repository.chats[chat.id], chat)

    async def test_creates_free_chat_with_limits_in_one_repository_call(self) -> None:
        chat = await self.service.create_chat_with_limits(
            ChatMode.FREE,
            self.free_model,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.available_limit,
            token_limit=8192,
            max_completion_tokens=1024,
            cost_limit_usd=None,
        )

        self.assertEqual(
            self.repository.limits[chat.id],
            (8192, 1024, Decimal("0")),
        )

    async def test_creates_paid_chat_only_with_limits_and_confirmation(self) -> None:
        with self.assertRaises(PaidConfirmationRequired):
            await self.service.create_chat_with_limits(
                ChatMode.PAID,
                self.paid_model,
                catalog=self.catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
                token_limit=8192,
                max_completion_tokens=1024,
                cost_limit_usd=Decimal("1.25"),
            )
        self.assertEqual(self.repository.chats, {})

        chat = await self.service.create_chat_with_limits(
            ChatMode.PAID,
            self.paid_model,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.available_limit,
            token_limit=8192,
            max_completion_tokens=1024,
            cost_limit_usd=Decimal("1.25"),
            paid_confirmed=True,
        )

        self.assertEqual(
            self.repository.limits[chat.id],
            (8192, 1024, Decimal("1.25")),
        )

    async def test_free_router_is_only_fallback_when_catalog_unavailable(self) -> None:
        unavailable = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(),
            available=False,
        )

        chat = await self.service.create_chat(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=unavailable,
            key_validity=self.valid_key,
            key_limit=self.exhausted_limit,
        )

        self.assertEqual(chat.requested_model_id, FREE_ROUTER_MODEL.id)
        self.assertEqual(chat.prompt_price_per_token, Decimal("0"))
        self.assertEqual(chat.completion_price_per_token, Decimal("0"))

    async def test_same_free_router_id_cannot_inject_paid_prices(self) -> None:
        forged = _model("openrouter/free", "Forged", "1", "2")

        chat = await self.service.create_chat(
            ChatMode.FREE,
            forged,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.available_limit,
        )

        self.assertEqual(chat.requested_model_name, FREE_ROUTER_MODEL.name)
        self.assertEqual(chat.prompt_price_per_token, Decimal("0"))
        self.assertEqual(chat.completion_price_per_token, Decimal("0"))

    async def test_paid_model_cannot_be_used_in_free_mode(self) -> None:
        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.FREE,
                self.paid_model,
                catalog=self.catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
            )

    async def test_free_suffix_does_not_override_nonzero_prices(self) -> None:
        suffix_model = _model("vendor/model:free", "Suffix", "0.01", "0")
        catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL, suffix_model),
            paid_models=(),
            available=True,
        )

        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.FREE,
                suffix_model,
                catalog=catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
            )

    async def test_paid_chat_requires_current_explicit_confirmation(self) -> None:
        with self.assertRaises(PaidConfirmationRequired):
            await self.service.create_chat(
                ChatMode.PAID,
                self.paid_model,
                catalog=self.catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
            )

        chat = await self.service.create_chat(
            ChatMode.PAID,
            self.paid_model,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.available_limit,
            paid_confirmed=True,
        )

        self.assertEqual(chat.mode, ChatMode.PAID)
        self.assertEqual(
            chat.prompt_price_per_token,
            self.paid_model.prompt_price_per_token,
        )
        self.assertEqual(
            chat.completion_price_per_token,
            self.paid_model.completion_price_per_token,
        )
        self.assertEqual(chat.request_price, self.paid_model.request_price)
        self.assertEqual(
            chat.internal_reasoning_price_per_token,
            self.paid_model.internal_reasoning_price_per_token,
        )
        self.assertEqual(chat.pricing_overrides, self.paid_model.pricing_overrides)

    async def test_paid_mode_fails_closed_without_catalog(self) -> None:
        unavailable = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(self.paid_model,),
            available=False,
        )

        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.PAID,
                self.paid_model,
                catalog=unavailable,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
                paid_confirmed=True,
            )

    async def test_free_router_id_cannot_be_used_for_paid_chat(self) -> None:
        forged = _model("openrouter/free", "Forged paid router", "1", "2")
        catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(forged,),
            available=True,
        )

        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.PAID,
                forged,
                catalog=catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
                paid_confirmed=True,
            )

    async def test_model_must_belong_to_current_catalog_snapshot(self) -> None:
        other_paid = _model("vendor/other", "Other", "0.1", "0.2")

        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.PAID,
                other_paid,
                catalog=self.catalog,
                key_validity=self.valid_key,
                key_limit=self.available_limit,
                paid_confirmed=True,
            )

    async def test_zero_limit_keeps_free_mode_available(self) -> None:
        chat = await self.service.create_chat(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.exhausted_limit,
        )

        self.assertEqual(chat.mode, ChatMode.FREE)
        self.assertEqual(chat.requested_model_id, FREE_ROUTER_MODEL.id)

    async def test_zero_limit_closes_paid_mode(self) -> None:
        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.PAID,
                self.paid_model,
                catalog=self.catalog,
                key_validity=self.valid_key,
                key_limit=self.exhausted_limit,
                paid_confirmed=True,
            )

    async def test_null_limit_is_not_zero_and_allows_paid_mode(self) -> None:
        self.assertEqual(self.no_individual_limit.state, KeyLimitState.NOT_SET)
        self.assertNotEqual(
            self.no_individual_limit.state,
            self.exhausted_limit.state,
        )

        chat = await self.service.create_chat(
            ChatMode.PAID,
            self.paid_model,
            catalog=self.catalog,
            key_validity=self.valid_key,
            key_limit=self.no_individual_limit,
            paid_confirmed=True,
        )

        self.assertEqual(chat.mode, ChatMode.PAID)

    async def test_free_mode_allows_valid_unknown_and_restricted_states(self) -> None:
        for key_validity in (
            KeyValidityState.VALID,
            KeyValidityState.UNKNOWN,
            KeyValidityState.RESTRICTED,
        ):
            with self.subTest(key_validity=key_validity):
                chat = await self.service.create_chat(
                    ChatMode.FREE,
                    FREE_ROUTER_MODEL,
                    catalog=self.catalog,
                    key_validity=key_validity,
                    key_limit=KeyLimitInfo.unknown(),
                )
                self.assertEqual(chat.mode, ChatMode.FREE)

    async def test_invalid_key_blocks_new_free_chat(self) -> None:
        with self.assertRaises(ChatPolicyError):
            await self.service.create_chat(
                ChatMode.FREE,
                FREE_ROUTER_MODEL,
                catalog=self.catalog,
                key_validity=KeyValidityState.INVALID,
                key_limit=KeyLimitInfo.unknown(),
            )

    async def test_paid_mode_requires_valid_key_state(self) -> None:
        for key_validity in (
            KeyValidityState.UNKNOWN,
            KeyValidityState.INVALID,
            KeyValidityState.RESTRICTED,
        ):
            with self.subTest(key_validity=key_validity):
                with self.assertRaises(ChatPolicyError):
                    await self.service.create_chat(
                        ChatMode.PAID,
                        self.paid_model,
                        catalog=self.catalog,
                        key_validity=key_validity,
                        key_limit=self.available_limit,
                        paid_confirmed=True,
                    )


def _model(model_id: str, name: str, prompt: str, completion: str) -> CatalogModel:
    return CatalogModel(
        id=model_id,
        name=name,
        prompt_price_per_token=Decimal(prompt),
        completion_price_per_token=Decimal(completion),
    )


if __name__ == "__main__":
    unittest.main()
