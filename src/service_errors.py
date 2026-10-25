"""Показывает только явное безопасное сообщение приложения без сырого исключения."""

from i18n import LocalizedText, tr


def localized_error_text(error: Exception) -> str:
    if error.args and isinstance(error.args[0], LocalizedText):
        return error.args[0].refresh()
    return tr("service.operation_failed")
