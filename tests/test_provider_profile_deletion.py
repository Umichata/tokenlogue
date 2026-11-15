"""Provider aliases extend the existing durable profile-deletion procedure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from providers.models import ProviderId  # noqa: E402
from storage.profile_deletion import (  # noqa: E402
    LEGACY_PROFILE_ALIASES,
    PROFILE_ALIASES,
    ProfileDeletion,
)
from storage.secure_credentials import (  # noqa: E402
    DEFAULT_PROVIDER_STORAGE_NAME,
    PROVIDER_KEY_STORAGE_NAMES,
    PROVIDER_VALIDATION_STORAGE_NAMES,
)
from tests.test_data_protection import ProtectionFixture  # noqa: E402


class ProviderProfileDeletionTests(ProtectionFixture):
    async def test_every_provider_alias_is_removed_before_registration(self):
        await self.enroll()
        for provider, alias in PROVIDER_KEY_STORAGE_NAMES.items():
            self.storage.values[alias] = (
                "sk-or-v1-fake"
                if provider is ProviderId.OPENROUTER
                else "sk-or-vv-fake"
            )
        for alias in PROVIDER_VALIDATION_STORAGE_NAMES.values():
            self.storage.values[alias] = "unverified"
        self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME] = "vsegpt"
        self.storage.values["foreign.application.secret"] = "preserve"
        deletion = ProfileDeletion(self.database.path, self.storage)
        scope = await deletion.capture()
        await deletion.accept(scope)
        await deletion.finish()
        self.assertFalse(any(alias in self.storage.values for alias in PROFILE_ALIASES))
        self.assertEqual(self.storage.values["foreign.application.secret"], "preserve")
        self.assertFalse(self.database.path.exists())

    async def test_old_complete_alias_ack_intent_resumes_under_expanded_scope(self):
        await self.enroll()
        deletion = ProfileDeletion(self.database.path, self.storage)
        scope = await deletion.capture()
        await deletion.accept(scope)
        intent = json.loads(deletion.intent_path.read_text())
        intent["removed"] = list(LEGACY_PROFILE_ALIASES)
        for alias in LEGACY_PROFILE_ALIASES:
            await self.storage.remove(alias)
        deletion.intent_path.write_text(json.dumps(intent), encoding="utf-8")
        await deletion.finish()
        self.assertFalse(self.database.path.exists())
        self.assertFalse(deletion.pending())
