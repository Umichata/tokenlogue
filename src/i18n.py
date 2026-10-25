"""Явные ключи перевода и обновление существующих элементов интерфейса."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from decimal import Decimal
from pathlib import Path
from string import Formatter
from typing import Any

from preferences import PreferencesStore


def _load_catalogues() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for language in ("ru", "en"):
        catalogue: dict[str, str] = {}
        for path in sorted(
            (Path(__file__).parent / "locales").glob(f"{language}*.json")
        ):
            values = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(values, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in values.items()
            ):
                raise ValueError("Некорректный каталог переводов")
            if set(catalogue) & set(values):
                raise ValueError("Повторяющийся ключ перевода")
            catalogue.update(values)
        result[language] = catalogue
    if result["ru"].keys() != result["en"].keys():
        raise ValueError("Наборы ключей перевода не совпадают")
    for key in result["ru"]:
        if _parameters(result["ru"][key]) != _parameters(result["en"][key]):
            raise ValueError("Параметры переводов не совпадают")
    return result


def _parameters(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name is not None}


CATALOGUES = _load_catalogues()
_preferences = PreferencesStore()
_language = "ru"
_on_change: Callable[[], None] | None = None


class LocalizedText(str):
    """Хранит явный ключ и параметры без их раскрытия в диагностическом repr."""

    key: str
    parameters: dict[str, object]

    def __new__(cls, key: str, **parameters: object) -> LocalizedText:
        template = CATALOGUES[_language][key]
        if _parameters(template) != parameters.keys():
            raise ValueError("Параметры не соответствуют ключу перевода")
        rendered = {
            name: value.refresh() if isinstance(value, LocalizedText) else value
            for name, value in parameters.items()
        }
        result = super().__new__(cls, template.format(**rendered))
        result.key = key
        result.parameters = parameters
        return result

    def __repr__(self) -> str:
        return f"LocalizedText(key={self.key!r}, parameters=<hidden>)"

    def __getnewargs_ex__(self) -> tuple[tuple[str], dict[str, object]]:
        return (self.key,), self.parameters

    def refresh(self) -> LocalizedText:
        return LocalizedText(self.key, **self.parameters)


def tr(key: str, **parameters: object) -> LocalizedText:
    return LocalizedText(key, **parameters)


def fresh_text(value: str) -> str:
    """Применяет текущий язык к безопасному запоздавшему результату."""
    return value.refresh() if isinstance(value, LocalizedText) else value


def get_language() -> str:
    return _language


def get_preferences() -> PreferencesStore:
    return _preferences


def configure_localization(
    preferences: PreferencesStore,
    on_change: Callable[[], None] | None = None,
) -> None:
    """Загружает несекретный выбор до построения экранов и доступа к чатам."""
    global _preferences, _language, _on_change
    _preferences = preferences
    _language = preferences.language
    _on_change = on_change


def set_language(language: str) -> None:
    global _language
    if language == _language:
        return
    _preferences.set_language(language)
    _language = language
    if _on_change is not None:
        _on_change()


def localize_tree(root: object) -> None:
    """Обновляет только помеченные значения без событий ввода и замены controls."""
    seen: set[int] = set()

    def visit(value: Any) -> Any:
        if isinstance(value, LocalizedText):
            return value.refresh()
        if value is None or isinstance(value, (str, bytes, int, float, bool, Decimal)):
            return value
        if id(value) in seen:
            return value
        seen.add(id(value))
        if isinstance(value, list):
            for index, item in enumerate(value):
                value[index] = visit(item)
        elif isinstance(value, tuple):
            return tuple(visit(item) for item in value)
        elif isinstance(value, dict):
            for name, item in value.items():
                value[name] = visit(item)
        elif is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                if (
                    field.name.startswith("_") and field.name != "_dialogs"
                ) or field.metadata.get("skip"):
                    continue
                before = getattr(value, field.name, None)
                after = visit(before)
                if after is not before:
                    setattr(value, field.name, after)
            synchronize = getattr(value, "sync_language", None)
            if callable(synchronize):
                synchronize()
        return value

    visit(root)


def display_chat_title(chat: object) -> str:
    """Старые и пользовательские заголовки сохраняются без анализа их текста."""
    if getattr(chat, "title_origin", "legacy") == "placeholder":
        return tr("chat.untitled")
    return str(getattr(chat, "title"))


def number(value: Decimal | int | str) -> LocalizedText:
    """Локализует представление числа без изменения значения расчёта."""
    return tr("number.value", value=_Number(value))


class _Number:
    def __init__(self, value: Decimal | int | str) -> None:
        self.value = value

    def __format__(self, _specification: str) -> str:
        text = (
            format(self.value, "f")
            if isinstance(self.value, Decimal)
            else str(self.value)
        )
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text.replace(".", ",") if _language == "ru" else text


def money(value: Decimal | int | str) -> LocalizedText:
    return tr("money.value", amount=_Number(value))


def display_model_name(model_id: str, name: str) -> str:
    """Переводит встроенную подпись маршрутизатора, сохраняя имена провайдеров."""
    return tr("model.free_router") if model_id == "openrouter/free" else name
