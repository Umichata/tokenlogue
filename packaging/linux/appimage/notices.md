# Tokenlogue - AppImage licenses / Лицензии AppImage

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

The `1472c00` Linux preview includes the original notices and license texts
for its packaged components. This guide explains how to find and read
those files. The [repository overview](../../../THIRD_PARTY_NOTICES.md#lang-en)
lists the direct application dependencies.

### Finding the notices

After extracting the AppImage, open these paths relative to its extracted root:

| Path | Contents |
| --- | --- |
| `LICENSE` | Tokenlogue's MIT license. |
| `THIRD_PARTY_NOTICES.md` | Index of components and their notice paths. |
| `usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md` | Another copy of that index. |
| `usr/share/doc/tokenlogue/licenses/` | Original license and copyright texts. |
| `usr/share/doc/tokenlogue/notices.json` | Component files, checksums and information about their sources. |

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
that are not shipped here. Use the component index to find the relevant
license text. A mention of a module in a license file does not mean that
Tokenlogue includes that module or its features.

License and copyright texts are kept unchanged in their original language.
The explanations in this guide do not replace those terms.
Earlier previews may have an English-only component index.

### Where to find the source code

Source code is provided separately from these license texts. The
[source materials guide](../../../docs/source-materials.md#lang-en) links to
the application source and runtime bundle. It also describes the missing
Flutter SDK materials that prevent the collection from being complete.
Rebuilding the full application from the available materials has not been verified.

[Back to the AppImage overview](README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Предварительная Linux-сборка `1472c00` содержит оригинальные уведомления
и тексты лицензий упакованных компонентов. В этом руководстве объясняется,
как найти и прочитать эти файлы.
[Обзор в репозитории](../../../THIRD_PARTY_NOTICES.md#lang-ru)
перечисляет прямые зависимости приложения.

### Как найти лицензии

После распаковки AppImage откройте следующие пути относительно его корня:

| Путь | Содержимое |
| --- | --- |
| `LICENSE` | Лицензия MIT для Tokenlogue. |
| `THIRD_PARTY_NOTICES.md` | Список компонентов и файлов с их лицензиями. |
| `usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md` | Ещё одна копия списка компонентов. |
| `usr/share/doc/tokenlogue/licenses/` | Оригинальные тексты лицензий и уведомлений об авторских правах. |
| `usr/share/doc/tokenlogue/notices.json` | Файлы компонентов, контрольные суммы и сведения об их исходниках. |

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
не вошедшие в приложение. Сверяйтесь со списком компонентов, чтобы найти нужную лицензию.
Упоминание модуля в тексте лицензии ещё не означает, что этот модуль
или его функции включены в Tokenlogue.

Тексты лицензий и уведомлений об авторских правах сохранены без изменений
на языке оригинала. Пояснения в этом руководстве не заменяют их условия.
В ранних сборках список компонентов может быть только на английском языке.

### Где найти исходный код

Исходный код предоставляется отдельно от текстов лицензий.
[Руководство по исходным материалам](../../../docs/source-materials.md#lang-ru)
содержит ссылки на код приложения и комплект runtime. В нём также описаны
недостающие материалы Flutter SDK, из-за которых комплект остаётся неполным.
Пересборка всего приложения из доступных материалов не проверена.

[К обзору AppImage](README.md#lang-ru)
