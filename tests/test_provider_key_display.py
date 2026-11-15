"""A menu label is a one-way view of a saved unlocked service credential."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from providers.credentials import masked_key_display, safe_key_display  # noqa: E402
from providers.models import ProviderId  # noqa: E402
from providers.session import ProviderProfiles  # noqa: E402
from storage.secure_credentials import (  # noqa: E402
    API_KEY_STORAGE_NAME,
    PROVIDER_KEY_STORAGE_NAMES,
    FletSecureCredentials,
)
from tests.test_provider_sessions import (  # noqa: E402
    FakeAPI,
    MemoryStorage,
    validation,
)


class MaskedKeyDisplayTests(unittest.TestCase):
    def test_no_key_and_insufficient_hidden_secret_never_show_tail(self):
        self.assertIsNone(masked_key_display(ProviderId.OPENROUTER, None))
        for prefix, provider in (
            ("sk-or-v1-", ProviderId.OPENROUTER),
            ("sk-or-vv-", ProviderId.VSEGPT),
            ("sk-or-vis", ProviderId.VSEGPT),
            ("sk-or-vis-", ProviderId.VSEGPT),
        ):
            for suffix in ("", "Ab3", "ABCDEFG7A2F"):
                with self.subTest(prefix=prefix, length=len(suffix)):
                    self.assertEqual(
                        masked_key_display(provider, prefix + suffix), "••••"
                    )

    def test_exact_boundary_hides_eight_secret_characters_and_preserves_tail_case(self):
        for prefix, provider in (
            ("sk-or-v1-", ProviderId.OPENROUTER),
            ("sk-or-vv-", ProviderId.VSEGPT),
            ("sk-or-vis", ProviderId.VSEGPT),
            ("sk-or-vis-", ProviderId.VSEGPT),
        ):
            key = prefix + "ABCDEFGH7a2F"
            display = masked_key_display(provider, " \t" + key + "\n")
            self.assertEqual(display, "•••• 7a2F")
            self.assertNotIn(key, str(display))
            self.assertNotIn("ABCDEFGH", str(display))

    def test_unknown_or_foreign_slot_and_arbitrary_ui_text_are_fully_hidden(self):
        self.assertEqual(
            masked_key_display(ProviderId.VSEGPT, "sk-or-v1-ABCDEFGH7A2F"), "••••"
        )
        for candidate in ("sk-or-vis-ABCDEFGH7A2F", "•••• abc\n", "•••• abcд"):
            self.assertEqual(safe_key_display(candidate), "••••")
        self.assertEqual(safe_key_display("•••• A-.!"), "•••• A-.!")


class ProviderKeyDisplaySessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_mask_follows_saved_key_only_and_lock_removes_it(self):
        old = "sk-or-v1-ABCDEFGH7A2F"
        other = "sk-or-vis-ABCDEFGH9b3C"
        new = "sk-or-v1-IJKLMNOP4D8E"
        storage = MemoryStorage()
        storage.values.update(
            {
                API_KEY_STORAGE_NAME: old,
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: other,
            }
        )
        api = FakeAPI()
        profiles = ProviderProfiles(FletSecureCredentials(storage), api)
        self.addCleanup(profiles.deactivate)
        await profiles.activate(old, KeyValidityState.VALID, KeyLimitInfo.unknown())
        before = dict(storage.values)
        self.assertEqual(profiles.state(ProviderId.OPENROUTER).key_display, "•••• 7A2F")
        self.assertEqual(profiles.key_display(ProviderId.VSEGPT), "•••• 9b3C")
        self.assertEqual(storage.values, before)
        for provider in ProviderId:
            self.assertNotIn(old, repr(profiles.state(provider)))
            self.assertNotIn(other, repr(profiles.state(provider)))
        api.results[new] = validation(new)
        await profiles.check(ProviderId.OPENROUTER, new)
        self.assertEqual(profiles.key_display(ProviderId.OPENROUTER), "•••• 7A2F")
        await profiles.save(ProviderId.OPENROUTER, new, allow_unverified=False)
        self.assertEqual(profiles.key_display(ProviderId.OPENROUTER), "•••• 4D8E")
        self.assertEqual(profiles.key_display(ProviderId.VSEGPT), "•••• 9b3C")
        profiles.deactivate()
        for provider in ProviderId:
            self.assertIsNone(profiles.key_display(provider))
            self.assertIsNone(profiles.state(provider).key_display)
