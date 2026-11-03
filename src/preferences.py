"""Несекретные предпочтения и отметка завершения первоначального шага."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class PreferencesStore:
    """Не хранит секреты или подтверждённый результат проверки защиты."""

    def __init__(self, path: Path | None = None) -> None:
        self._write_lock = threading.Lock()
        self.path = path
        self.language = "ru"
        self.wide_sidebar_visible = True
        self.local_protection_onboarding: str | None = None
        if path is not None:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    if value.get("language") in {"ru", "en"}:
                        self.language = value["language"]
                    if type(value.get("wide_sidebar_visible")) is bool:
                        self.wide_sidebar_visible = value["wide_sidebar_visible"]
                    if value.get("local_protection_onboarding") in {"pending", "done"}:
                        self.local_protection_onboarding = value[
                            "local_protection_onboarding"
                        ]
            except (OSError, ValueError, TypeError):
                pass

    def set_language(self, language: str) -> None:
        if language not in {"ru", "en"}:
            raise ValueError("Неподдерживаемый язык интерфейса")
        with self._write_lock:
            self._save(
                language, self.wide_sidebar_visible, self.local_protection_onboarding
            )
            self.language = language

    def set_wide_sidebar_visible(self, visible: bool) -> None:
        if type(visible) is not bool:
            raise TypeError("Ожидается логическое значение видимости панели")
        with self._write_lock:
            self._save(self.language, visible, self.local_protection_onboarding)
            self.wide_sidebar_visible = visible

    def set_local_protection_onboarding(self, state: str) -> None:
        """Done means the step was handled, including explicit manual continuation."""
        if state not in {"pending", "done"}:
            raise ValueError("Некорректное состояние первоначального шага")
        with self._write_lock:
            self._save(self.language, self.wide_sidebar_visible, state)
            self.local_protection_onboarding = state

    def _save(self, language: str, visible: bool, onboarding: str | None) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".preferences-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                values: dict[str, str | bool] = {
                    "language": language,
                    "wide_sidebar_visible": visible,
                }
                if onboarding is not None:
                    values["local_protection_onboarding"] = onboarding
                json.dump(
                    values,
                    stream,
                    ensure_ascii=False,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
