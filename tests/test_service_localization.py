"""Безопасные сервисные результаты сохраняют текущий язык и скрывают исключения."""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationStatus  # noqa: E402
from auth.models import KeyLimitInfo  # noqa: E402
from auth.service import (  # noqa: E402
    _locked_result,
    _validated_key_message,
    _validation_error,
)
from chat.accounting import parse_chat_limit_input  # noqa: E402
from chat.errors import ChatErrorType, safe_error_message  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from i18n import (  # noqa: E402
    LocalizedText,
    configure_localization,
    fresh_text,
    set_language,
    tr,
)
from preferences import PreferencesStore  # noqa: E402
from service_errors import localized_error_text  # noqa: E402
from tests import test_chat_view as fixtures  # noqa: E402


class ServiceLocalizationTests(unittest.TestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    def test_every_safe_request_error_uses_current_language(self):
        for category in ChatErrorType:
            russian = safe_error_message(category)
            self.assertIsInstance(russian, LocalizedText)
            set_language("en")
            english = safe_error_message(category)
            self.assertFalse(any("А" <= char <= "я" for char in english))
            self.assertEqual(fresh_text(russian), english)
            set_language("ru")

    def test_auth_results_keep_keys_across_late_language_switch(self):
        results = [_validation_error(status) for status in KeyValidationStatus]
        results.append(_locked_result(19))
        notices = [
            _validated_key_message(KeyLimitInfo.from_validated_remaining(value))
            for value in (None, Decimal("0"), Decimal("1.50"))
        ]
        set_language("en")
        for message in [*(r.message for r in results), *notices]:
            self.assertIsInstance(message, LocalizedText)
            self.assertFalse(any("А" <= char <= "я" for char in fresh_text(message)))
        self.assertIn("19", fresh_text(results[-1].message))

    def test_unknown_exception_never_discloses_its_text(self):
        secret = "SYNTHETIC_PROVIDER_SECRET_IN_EXCEPTION"
        for language in ("ru", "en"):
            set_language(language)
            for error in (ValueError(secret), RuntimeError(secret), KeyError(secret)):
                message = localized_error_text(error)
                self.assertNotIn(secret, message)
                self.assertEqual(message, tr("service.operation_failed"))

    def test_validation_parameters_retranslate_without_changing_values(self):
        with self.assertRaises(ValueError) as caught:
            parse_chat_limit_input(ChatMode.FREE, "abc", "16", None)
        original = caught.exception
        self.assertIsInstance(original.args[0], LocalizedText)
        set_language("en")
        self.assertEqual(
            localized_error_text(original),
            "“Total token limit” must be a positive integer",
        )
        self.assertEqual(fixtures._chat().requested_model_id, "openrouter/free")


if __name__ == "__main__":
    unittest.main()
