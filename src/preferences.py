"""Отдельные несекретные предпочтения языка и широкой панели."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class PreferencesStore:
    """Сохраняет только два разрешённых поля без доступа к переписке и ключам."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.language = "ru"
        self.wide_sidebar_visible = True
        if path is not None:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    if value.get("language") in {"ru", "en"}:
                        self.language = value["language"]
                    if type(value.get("wide_sidebar_visible")) is bool:
                        self.wide_sidebar_visible = value["wide_sidebar_visible"]
            except (OSError, ValueError, TypeError):
                pass

    def set_language(self, language: str) -> None:
        if language not in {"ru", "en"}:
            raise ValueError("Неподдерживаемый язык интерфейса")
        self._save(language, self.wide_sidebar_visible)
        self.language = language

    def set_wide_sidebar_visible(self, visible: bool) -> None:
        if type(visible) is not bool:
            raise TypeError("Ожидается логическое значение видимости панели")
        self._save(self.language, visible)
        self.wide_sidebar_visible = visible

    def _save(self, language: str, visible: bool) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".preferences-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {"language": language, "wide_sidebar_visible": visible},
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
