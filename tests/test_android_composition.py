"""Android использует барьер записи даже без доступного восстановления PIN."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as composition  # noqa: E402
from app import AppController  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests.test_app_lifecycle import AndroidPage  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
)
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402


class AndroidCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_disk_ack_is_required_when_device_recovery_is_unavailable(self):
        for acknowledgement in (False, True):
            with self.subTest(acknowledgement=acknowledgement):
                with tempfile.TemporaryDirectory() as directory:
                    page = AndroidPage()
                    backend = FakeSecureStorage()
                    sync = AsyncMock(
                        side_effect=None
                        if acknowledgement
                        else OSError("SYNTHETIC_DISK_COMMIT_FAILURE")
                    )
                    bridge = SimpleNamespace(
                        supports_recovery=AsyncMock(return_value=False),
                        sync_secure_storage=sync,
                        authenticate=AsyncMock(),
                    )
                    controllers: list[AppController] = []

                    def capture(*args, **kwargs):
                        controller = AppController(*args, **kwargs)
                        controllers.append(controller)
                        return controller

                    with (
                        patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}),
                        patch.object(ft.Control, "update"),
                        patch.object(
                            composition,
                            "FletSecureCredentials",
                            return_value=FletSecureCredentials(backend),
                        ),
                        patch.object(
                            composition, "DeviceRecovery", return_value=bridge
                        ),
                        patch.object(
                            composition,
                            "OpenRouterClient",
                            return_value=FakeKeyValidator(),
                        ),
                        patch.object(
                            composition,
                            "ModelCatalogClient",
                            return_value=FakeCatalogClient(()),
                        ),
                        patch.object(
                            composition,
                            "ChatCompletionsClient",
                            return_value=FakeCompletionClient([]),
                        ),
                        patch.object(composition, "AppController", side_effect=capture),
                    ):
                        await composition.main(cast(ft.Page, page))
                        controller = controllers[0]
                        try:
                            await controller.submit_key("SYNTHETIC_API_KEY")
                            token = controller._pending_setup_token
                            assert token is not None
                            await controller.confirm_pin_setup("0123", token)
                            self.assertGreater(sync.await_count, 0)
                            bridge.authenticate.assert_not_awaited()
                            self.assertFalse(
                                controller._auth_service.recovery_available
                            )
                            self.assertEqual(
                                controller._chat_controller.session_active,
                                acknowledgement,
                            )
                            with sqlite3.connect(
                                Path(directory) / "tokenlogue.sqlite3"
                            ) as database:
                                self.assertEqual(
                                    database.execute("PRAGMA user_version").fetchone()[
                                        0
                                    ],
                                    7 if acknowledgement else 6,
                                )
                        finally:
                            controller.prepare_close()
                            await controller.flush_drafts()
                            controller.dispose()


if __name__ == "__main__":
    unittest.main()
