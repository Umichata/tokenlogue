# Tokenlogue - Third-party software / Сторонние компоненты

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

[English](#lang-en) | [Русский](#lang-ru)

Tokenlogue uses third-party software under its respective licenses.
Tokenlogue's own code is covered by the [MIT License](LICENSE).
The original third-party license texts retain their original language.

### Main application dependencies

| Component | Version | License | Role |
| --- | --- | --- | --- |
| [Flet](https://github.com/flet-dev/flet) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Application framework and user interface. |
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Platform storage for the API key and registration identifier. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | HTTPS communication with OpenRouter. |

### Licenses supplied with the AppImage

This table describes the direct application dependencies. The AppImage also
contains Python, Flutter, Dart plugins, native libraries, fonts and its startup
runtime. It includes a separate index for its actual components and the full
license texts in `usr/share/doc/tokenlogue/licenses/`, relative to the
AppImage's extracted root.

The [AppImage license guide](packaging/linux/appimage/notices.md#lang-en)
explains how to find those files. The index inside an already built preview
may have an older language layout. Its original license texts still apply.

License notices and source archives serve different purposes.
[Available source materials](docs/source-materials.md#lang-en) are described
separately, including gaps in the Flutter SDK source collection.

[Back to Tokenlogue](README.md#lang-en)

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-ru"></a>

## Русский

[English](#lang-en) | [Русский](#lang-ru)

Tokenlogue использует стороннее программное обеспечение на условиях его
собственных лицензий. На собственный код Tokenlogue распространяется
[лицензия MIT](LICENSE). Оригинальные тексты сторонних лицензий сохранены
на исходном языке.

### Основные зависимости приложения

| Компонент | Версия | Лицензия | Назначение |
| --- | --- | --- | --- |
| [Flet](https://github.com/flet-dev/flet) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Основа приложения и пользовательский интерфейс. |
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Платформенное хранилище API-ключа и идентификатора регистрации. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | Обмен с OpenRouter по HTTPS. |

### Лицензии внутри AppImage

Таблица описывает прямые зависимости приложения. AppImage также содержит
Python, Flutter, плагины Dart, нативные библиотеки, шрифты и компонент запуска
runtime. В нём есть отдельный индекс фактических компонентов и полные тексты
лицензий в `usr/share/doc/tokenlogue/licenses/` относительно корня
распакованного AppImage.

Найти эти файлы поможет [руководство по лицензиям AppImage](packaging/linux/appimage/notices.md#lang-ru).
Индекс в ранее собранной предварительной версии может иметь прежнее языковое
оформление. Его оригинальные тексты лицензий продолжают действовать.

Уведомления о лицензиях и архивы исходников имеют разное назначение.
[Доступные исходные материалы](docs/source-materials.md#lang-ru) описаны
отдельно, включая недостающие части комплекта исходников Flutter SDK.

[К Tokenlogue](README.md#lang-ru)

[English](#lang-en) | [Русский](#lang-ru)
