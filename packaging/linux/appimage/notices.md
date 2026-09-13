# Tokenlogue - AppImage licenses / Лицензии AppImage

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

[English](#lang-en) | [Русский](#lang-ru)

The `1472c00` Linux preview includes the original notices and license texts
for its packaged components. This guide explains where a recipient can read
them. The [repository overview](../../../THIRD_PARTY_NOTICES.md#lang-en)
lists the direct application dependencies.

### Finding the notices

After extracting the AppImage, open these paths relative to its extracted root:

| Path | Contents |
| --- | --- |
| `LICENSE` | Tokenlogue's MIT license. |
| `THIRD_PARTY_NOTICES.md` | Index of components and their notice paths. |
| `usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md` | Another copy of that index. |
| `usr/share/doc/tokenlogue/licenses/` | Original license and copyright texts. |
| `usr/share/doc/tokenlogue/notices.json` | Component-to-file associations, checksums and source-material status. |

If you want to read the notices without starting Tokenlogue, use an installed
`unsquashfs` tool. Open a terminal in the folder containing the verified
AppImage. Choose a destination name that does not already exist.

```bash
unsquashfs -no-xattrs -o 678280 -d "./tokenlogue-notices" "./Tokenlogue-0.1.0-1472c00-x86_64.AppImage"
```

This extracts the filesystem to `tokenlogue-notices` without executing the
AppImage runtime or the application. The offset `678280` applies only to
this exact file. Confirm its [name and checksum](../../../docs/linux-appimage.md#en-download)
before using the command. Other AppImages can have different offsets.

### Reading the license collection

The collection includes notices for Ubuntu libraries, the Python runtime and
packages, Flutter and its plugins, Dart bridge, fonts and the AppImage runtime.
The runtime license set includes GCC's runtime exception and the applicable
texts for libfuse and its other components.

A Debian copyright file can describe source-package files that are absent
from this AppImage. Python's license collection can include optional modules
that are not shipped here. Read the component association together with its
license text. An upstream license collection alone is not a list of enabled
application features.

The original license and copyright texts are preserved in their original
language. This bilingual explanation does not replace their terms.
An already downloaded preview can have an English-only generated index.
The language layout of documentation does not alter that artifact.

### Corresponding sources

The collection is a set of notices, not a complete source archive.
[Available source materials](../../../docs/source-materials.md#lang-en)
include the application's source and a separate runtime bundle, while
Flutter SDK completeness and full application rebuild coverage remain limited.

[Back to the AppImage overview](README.md#lang-en)

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-ru"></a>

## Русский

[English](#lang-en) | [Русский](#lang-ru)

Предварительная Linux-сборка `1472c00` содержит оригинальные уведомления
и тексты лицензий упакованных компонентов. Это руководство объясняет,
где получатель приложения может их прочитать.
[Обзор в репозитории](../../../THIRD_PARTY_NOTICES.md#lang-ru)
перечисляет прямые зависимости приложения.

### Как найти лицензии

После распаковки AppImage откройте следующие пути относительно его корня:

| Путь | Содержимое |
| --- | --- |
| `LICENSE` | Лицензия MIT для Tokenlogue. |
| `THIRD_PARTY_NOTICES.md` | Индекс компонентов и путей к их уведомлениям. |
| `usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md` | Ещё одна копия индекса. |
| `usr/share/doc/tokenlogue/licenses/` | Оригинальные тексты лицензий и copyright. |
| `usr/share/doc/tokenlogue/notices.json` | Связи компонентов с файлами, контрольные суммы и статус исходных материалов. |

Чтобы прочитать лицензии без запуска Tokenlogue, используйте установленную
утилиту `unsquashfs`. Откройте терминал в папке с проверенным AppImage.
Выберите ещё не существующее имя каталога назначения.

```bash
unsquashfs -no-xattrs -o 678280 -d "./tokenlogue-notices" "./Tokenlogue-0.1.0-1472c00-x86_64.AppImage"
```

Команда извлекает файловую систему в `tokenlogue-notices`, не выполняя
runtime AppImage или приложение. Смещение `678280` относится только к
этому файлу. Перед выполнением сверьте его
[имя и контрольную сумму](../../../docs/linux-appimage.md#ru-download).
У других AppImage смещение может отличаться.

### Как читать комплект лицензий

Комплект содержит уведомления для библиотек Ubuntu, среды и пакетов Python,
Flutter и его плагинов, Dart bridge, шрифтов и runtime AppImage.
Лицензии runtime включают исключение GCC для библиотек времени выполнения,
а также применимые тексты для libfuse и остальных компонентов.

Copyright-файл Debian может описывать файлы исходного пакета, которых нет
в этом AppImage. Комплект лицензий Python может включать необязательные модули,
не вошедшие в приложение. Читайте связь с конкретным компонентом вместе
с текстом лицензии. Сам по себе комплект лицензий разработчика зависимости
не является перечнем включённых возможностей приложения.

Оригинальные тексты лицензий и copyright сохранены на исходном языке.
Это двуязычное пояснение не заменяет их условия. В уже скачанной
предварительной сборке сгенерированный индекс может быть только на английском.
Языковое оформление документации не меняет этот артефакт.

### Соответствующие исходники

Комплект является набором уведомлений, а не полным архивом исходников.
[Доступные исходные материалы](../../../docs/source-materials.md#lang-ru)
включают код приложения и отдельный комплект runtime. Полнота Flutter SDK
и охват пересборки всего приложения остаются ограниченными.

[К обзору AppImage](README.md#lang-ru)

[English](#lang-en) | [Русский](#lang-ru)
