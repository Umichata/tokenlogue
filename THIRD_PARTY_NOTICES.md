# Tokenlogue - Third-party software / Сторонние компоненты

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

Tokenlogue uses third-party software under its respective licenses.
Tokenlogue's own code is covered by the [MIT License](LICENSE).
The original third-party license texts retain their original language.

### Main components

| Component | Version | License | Role |
| --- | --- | --- | --- |
| [Flet](https://github.com/flet-dev/flet) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Application framework and user interface. |
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Platform storage for the API key and registration identifier. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | HTTPS communication with OpenRouter. |

### Licenses supplied with the AppImage

The table above lists the application's direct dependencies. The AppImage
also contains Python, Flutter, Dart plugins, native libraries, fonts and a
startup component called the runtime. Its component index lists the licenses
for the software included in that build. The full texts are in
`usr/share/doc/tokenlogue/licenses/` inside the extracted AppImage.

The [AppImage license guide](packaging/linux/appimage/notices.md#lang-en)
explains how to find those files. Earlier previews may have an English-only index.
The license texts are kept in their original language.

To inspect the source code, use the [source materials guide](docs/source-materials.md#lang-en).
It explains which archives are available and which parts of the Flutter SDK
source collection are still missing.

[Back to Tokenlogue](README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Tokenlogue использует стороннее программное обеспечение на условиях его
собственных лицензий. На собственный код Tokenlogue распространяется
[лицензия MIT](LICENSE). Оригинальные тексты сторонних лицензий сохранены
на исходном языке.

### Основные компоненты

| Компонент | Версия | Лицензия | Назначение |
| --- | --- | --- | --- |
| [Flet](https://github.com/flet-dev/flet) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Основа приложения и пользовательский интерфейс. |
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Платформенное хранилище API-ключа и идентификатора регистрации. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | Обмен с OpenRouter по HTTPS. |

### Лицензии внутри AppImage

В таблице перечислены прямые зависимости приложения. В AppImage также
включены Python, Flutter, плагины Dart, нативные библиотеки, шрифты
и компонент запуска runtime. Внутри есть список компонентов со ссылками
на их лицензии. Полные тексты находятся в папке
`usr/share/doc/tokenlogue/licenses/` распакованного AppImage.

Найти эти файлы поможет [руководство по лицензиям AppImage](packaging/linux/appimage/notices.md#lang-ru).
В ранних сборках список может быть только на английском языке.
Тексты лицензий сохранены на языке оригинала.

Для изучения исходного кода откройте [руководство по исходным материалам](docs/source-materials.md#lang-ru).
В нём описаны доступные архивы и недостающие части комплекта исходников Flutter SDK.

[К Tokenlogue](README.md#lang-ru)
