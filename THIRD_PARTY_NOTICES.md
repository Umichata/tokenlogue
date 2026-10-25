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
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Platform secure storage. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | HTTPS communication with OpenRouter. |
| [PyCryptodomex](https://www.pycryptodome.org/) | `3.23.0` | BSD 2-Clause and public-domain notices | AES-GCM primitives used by local-content protection. |
| [CFFI](https://cffi.readthedocs.io/) | `2.0.0` | MIT, with bundled libffi notices | Connection to the native cryptographic routines. |
| [pycparser](https://github.com/eliben/pycparser) | `3.11` | BSD 3-Clause License | C declaration parser used by CFFI. |

Current Android builds use `flutter_secure_storage 10.3.1` as the platform
backend for Flet Secure Storage. It uses the BSD 3-Clause license. Its
[source archive and license](packaging/android/crypto/README.md#lang-en) are
included in the additional source collection.

### Android device authentication

The Android bridge uses Flutter's `local_auth 3.0.2`,
`local_auth_android 2.2.0` and `local_auth_platform_interface 1.1.0`.
These packages use the BSD 3-Clause license. The resolved Flutter dependency
graph also includes `local_auth_darwin 2.0.4` and `local_auth_windows 2.0.2`.
Their implementations do not provide Android recovery.

The [additional source collection](packaging/android/crypto/README.md#lang-en)
contains the original package archives, licenses, Mobile Forge build recipes
and patches. It also records the exact Android wheel inputs. The version of
libffi statically linked into the CFFI Android wheel remains unconfirmed.
The collection does not establish a complete offline native rebuild.

### Licenses supplied with the AppImage

The table above describes the current application source. Previously published
AppImages retain the dependencies recorded in their own component index. The AppImage
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
| [Flet Secure Storage](https://github.com/flet-dev/flet/tree/main/sdk/python/packages/flet-secure-storage) | `0.86.5` | Apache License 2.0, `Apache-2.0` | Платформенное защищённое хранилище. |
| [HTTPX](https://github.com/encode/httpx) | `0.28.1` | BSD 3-Clause License, `BSD-3-Clause` | Обмен с OpenRouter по HTTPS. |
| [PyCryptodomex](https://www.pycryptodome.org/) | `3.23.0` | BSD 2-Clause и уведомления о public domain | Примитивы AES-GCM для защиты локального содержимого. |
| [CFFI](https://cffi.readthedocs.io/) | `2.0.0` | MIT и уведомления включённого libffi | Обращение к нативным криптографическим функциям. |
| [pycparser](https://github.com/eliben/pycparser) | `3.11` | BSD 3-Clause License | Разбор объявлений C для CFFI. |

Текущие сборки Android используют `flutter_secure_storage 10.3.1` как
платформенную реализацию Flet Secure Storage. Она распространяется по лицензии
BSD 3-Clause. Её [исходный архив и лицензия](packaging/android/crypto/README.md#lang-ru)
входят в дополнительный комплект исходников.

### Системная аутентификация Android

Платформенный адаптер Android использует пакеты Flutter `local_auth 3.0.2`,
`local_auth_android 2.2.0` и `local_auth_platform_interface 1.1.0`.
Они распространяются по лицензии BSD 3-Clause. Разрешённый граф зависимостей
Flutter также включает `local_auth_darwin 2.0.4` и `local_auth_windows 2.0.2`.
Их реализации не обеспечивают восстановление Android.

[Дополнительный комплект исходников](packaging/android/crypto/README.md#lang-ru)
содержит оригинальные архивы пакетов, лицензии, рецепты сборки Mobile Forge
и патчи. В нём также указаны точные входные Android wheels. Версия libffi,
статически включённой в Android wheel CFFI, пока не подтверждена.
Комплект не доказывает полноту автономной нативной сборки.

### Лицензии внутри AppImage

В таблице описаны текущие исходники приложения. Прежние опубликованные AppImage
сохраняют зависимости, перечисленные в их собственном списке компонентов. В AppImage также
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
