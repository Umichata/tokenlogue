# Tokenlogue - Source materials / Исходные материалы

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This page describes sources for the
[published `0.1.0` Linux preview `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
To download the ready-to-use application, follow the [AppImage guide](linux-appimage.md#en-download).

### Application source

The [application source at 2b1f7d3](https://github.com/Umichata/tokenlogue/tree/2b1f7d30e612416d8d88adde18a44aa235a7fe25)
is available under the [MIT License](../LICENSE). Use that revision when
inspecting the code corresponding to this preview. A later repository revision
can contain different application code or documentation.

The application repository contains its own code and dependency descriptions.
It does not contain every third-party source and tool needed to recreate
the complete AppImage offline.

<a name="en-run-from-source"></a>

### Running from source on Linux

For a source launch, use Python 3.12 and [uv](https://docs.astral.sh/uv/).
The Linux desktop and key-storage requirements in the
[AppImage guide](linux-appimage.md#en-requirements) also apply.
Obtain the repository source and open a terminal in its root directory,
where `pyproject.toml` and `uv.lock` are located.

Install the locked environment.

```bash
uv sync --locked
```

After it completes, start Tokenlogue from that same directory.

```bash
uv run --locked flet run
```

The second command starts the application directly from the source files.
Setting up the environment and downloading Flet desktop components may require
an internet connection. These commands do not create an AppImage.
For use without a development environment, download the ready-to-use AppImage.

### Baseline and supplement

The current source materials use two collections together. The
[baseline release for `986c6ad`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad)
supplies unchanged components. The
[Tokenlogue-2b1f7d3-source-supplement.tar.gz](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz)
supplies the exact application snapshot and six updated dependency archives.
Source materials are optional for running the AppImage.

The supplement is `745485` bytes. Its SHA-256 is
`66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`.
The current release's
[SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS)
lists the five other release files, including the supplement. The baseline
parts have their own checksums and remain in the older release.
The [published SOURCE_MATERIALS.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md)
describes both collections and their exact checksums.

Download the supplement into a new directory. Open a terminal there and run
the following Bash block to verify the archive, extract it into its own
directory and verify every included file. Administrator privileges are not
required.

```bash
set -euo pipefail
printf '%s  %s\n' '66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e' 'Tokenlogue-2b1f7d3-source-supplement.tar.gz' | sha256sum --check -
test ! -e Tokenlogue-2b1f7d3-source-supplement
tar --extract --gzip --file Tokenlogue-2b1f7d3-source-supplement.tar.gz --no-same-owner --no-same-permissions
(cd Tokenlogue-2b1f7d3-source-supplement && sha256sum --check SHA256SUMS)
```

If you already have the verified baseline, reuse it unchanged. Otherwise,
download the following seven parts into the same directory beside the
extracted supplement. Keep their exact names and do not recompress them.
Allow at least 25 GB for the parts and the extracted baseline together.

| Order | Download | Bytes |
| --- | --- | --- |
| 1 | [Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | `2000000000` |
| 2 | [Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | `2000000000` |
| 3 | [Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | `2000000000` |
| 4 | [Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | `2000000000` |
| 5 | [Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | `2000000000` |
| 6 | [Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | `2000000000` |
| 7 | [Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | `338636800` |

The part checksums are in
`Tokenlogue-2b1f7d3-source-supplement/baseline/BASELINE_PARTS.SHA256SUMS`.
They match the baseline's published
[SOURCE_PARTS.SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.SHA256SUMS).
Run the following block from the directory containing the seven parts. It
checks each part and the combined stream before extraction. It uses an
explicit file list and does not create a second complete tar file.

```bash
set -euo pipefail
sha256sum --check Tokenlogue-2b1f7d3-source-supplement/baseline/BASELINE_PARTS.SHA256SUMS
tokenlogue_baseline_digest=$(cat \
  Tokenlogue-986c6ad-source-materials.tar.part001 \
  Tokenlogue-986c6ad-source-materials.tar.part002 \
  Tokenlogue-986c6ad-source-materials.tar.part003 \
  Tokenlogue-986c6ad-source-materials.tar.part004 \
  Tokenlogue-986c6ad-source-materials.tar.part005 \
  Tokenlogue-986c6ad-source-materials.tar.part006 \
  Tokenlogue-986c6ad-source-materials.tar.part007 | sha256sum)
test "$tokenlogue_baseline_digest" = 'd66c43a31d810431af18defdc1642f235d072bdec9c9c281b3ed3dc3a72d4cf2  -'
test ! -e Tokenlogue-986c6ad-source-materials
cat \
  Tokenlogue-986c6ad-source-materials.tar.part001 \
  Tokenlogue-986c6ad-source-materials.tar.part002 \
  Tokenlogue-986c6ad-source-materials.tar.part003 \
  Tokenlogue-986c6ad-source-materials.tar.part004 \
  Tokenlogue-986c6ad-source-materials.tar.part005 \
  Tokenlogue-986c6ad-source-materials.tar.part006 \
  Tokenlogue-986c6ad-source-materials.tar.part007 | tar --extract --file - --no-same-owner --no-same-permissions
```

Keep both extracted directories and the original archives unchanged. The
baseline already includes `Tokenlogue-14b87ac-source-materials.zip`, so it
does not need a separate download. Do not rename the old source parts as a
source distribution for `2b1f7d3`.

The supplement's `baseline.json` identifies the baseline files and checksums.
Its `manifest.json` describes the current application snapshot, dependency
archives and included files. Its `replacements.json` gives the exact paths
to select in place of older application and dependency archives.
Select `application/tokenlogue-2b1f7d3-source.tar` from the supplement as the
application source reference for commit
`2b1f7d30e612416d8d88adde18a44aa235a7fe25`. It replaces
`source-materials-986c6ad/application/tokenlogue-986c6ad.tar` from the baseline.
For the following packages, select the archives under `dart/` in the
supplement instead of the older archives inside the historical ZIP.

| Package | Baseline version | Supplement version |
| --- | --- | --- |
| `flutter_secure_storage_platform_interface` | `2.1.0` | `2.1.1` |
| `serious_python_android` | `4.7.0` | `4.7.2` |
| `serious_python_darwin` | `4.7.0` | `4.7.2` |
| `serious_python_linux` | `4.7.0` | `4.7.2` |
| `serious_python_platform_interface` | `4.7.0` | `4.7.2` |
| `serious_python_windows` | `4.7.0` | `4.7.2` |

The other 142 hosted packages keep their matching baseline versions.
Python/PBS, corresponding Ubuntu materials, the runtime bundle and other
previously matched inputs remain baseline references. The supplement does
not undo earlier baseline replacements or make old application and runtime
files current inputs.

The supplement also includes the embedded Flutter dependency lock, notices
inventory, original license texts, pub.dev metadata and
`license-comparison.json`. The six archive hashes match the lock and pub.dev
metadata. Their original LICENSE files match the previous versions and the
corresponding AppImage notice bodies byte for byte. No separate NOTICE or
COPYRIGHT files were found in these six archives.

### Runtime source bundle

The AppImage includes a small startup component called the runtime.
The baseline's [separate runtime source bundle](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip)
is available as `appimage-runtime-34749438406-1.zip` in the
[baseline preview for `986c6ad`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad).
No GitHub sign-in is needed. The ZIP contains the original runtime bundle.

The bundle contains the runtime binary, source archives, recipes, patches,
original Alpine packages, tool inventory, linked inputs, license texts and
checksums. The [runtime overview](../packaging/linux/appimage/runtime/README.md#lang-en)
explains its contents. The full bundle is separate from the AppImage.

### Which source materials are still missing

The source completeness status remains `REVIEW_REQUIRED`. Neither the
baseline nor the supplement establishes a complete source set for the full
AppImage. The recorded Flutter input collection contains 118 of 119 inputs.
The internal RBE package `flutter_internal/rbe/reclient_cfgs`, instance
`0vARzGeIZgIhW7zVfWuqIPQ_HXMLDccjAstykWZKjaEC`, remains absent. Its
`use_rbe` condition defaults to `false`.

A full offline rebuild, compiler bootstrap, complete sources of binary
toolchain components, hooks, relinking and font subsetting have not been
verified. CIPD and PBS/runtime reference binaries do not establish complete
source or build-material coverage. Verified file integrity and the six
updated packages do not close these wider checks.

### Historical source collections

A [historical source collection for 14b87ac](releases/14b87ac-source-materials.md#lang-en)
includes application, Ubuntu, Python, Dart, Flutter and font materials.
Its Flutter engine dependency list references external Git repositories and
CIPD assets that are not all archived. Compiler bootstrap, relinking,
font subsetting and a full application rebuild have not been verified.

The historical collection alone was not a complete source bundle for `986c6ad`.
The following dependency versions differ:

| Component | Collection for `14b87ac` | AppImage `986c6ad` |
| --- | --- | --- |
| Dart `archive` | `4.2.0` | `4.3.0` |
| Dart `image` | `4.9.2` | `4.10.1` |
| `flutter_secure_storage_linux` | `3.0.2` | `3.0.3` |
| Ubuntu `libgcrypt20` | `1.9.4-3ubuntu3.2` | `1.9.4-3ubuntu3.3` |

Matching source files for these newer versions were included in the
published baseline for `986c6ad`. Those earlier replacements still apply
when using the baseline with the current supplement. The historical archive
retains its original versions.

The [license guide](../packaging/linux/appimage/notices.md#lang-en) explains
where to find the original license texts supplied with the application.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Страница описывает исходники
[опубликованной предварительной Linux-сборки `0.1.0` версии `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
Готовое приложение можно скачать по
[инструкции для AppImage](linux-appimage.md#ru-download).

### Исходники приложения

[Исходный код приложения 2b1f7d3](https://github.com/Umichata/tokenlogue/tree/2b1f7d30e612416d8d88adde18a44aa235a7fe25)
доступен по [лицензии MIT](../LICENSE). Используйте эту версию для изучения кода
данной предварительной сборки. Более поздняя версия репозитория может
содержать другой код приложения или документацию.

Репозиторий содержит собственный код приложения и описание зависимостей.
В нём нет всех сторонних исходников и инструментов, необходимых для
воссоздания полного AppImage без сети.

<a name="ru-run-from-source"></a>

### Запуск из исходников в Linux

Для запуска из исходников нужны Python 3.12 и [uv](https://docs.astral.sh/uv/).
Также действуют требования к рабочему столу Linux и хранилищу ключа из
[руководства по AppImage](linux-appimage.md#ru-requirements).
Получите исходники репозитория и откройте терминал в его корневой папке,
где находятся `pyproject.toml` и `uv.lock`.

Установите окружение с закреплёнными зависимостями.

```bash
uv sync --locked
```

После завершения запустите Tokenlogue из той же папки.

```bash
uv run --locked flet run
```

Вторая команда запускает приложение непосредственно из исходных файлов.
Для подготовки окружения и загрузки настольных компонентов Flet может
потребоваться интернет. Эти команды не создают AppImage.
Для работы без среды разработки скачайте готовый AppImage.

### Базовый комплект и дополнение

Текущие исходные материалы используют два набора вместе.
[Базовый выпуск для `986c6ad`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad)
предоставляет неизменившиеся компоненты.
[Tokenlogue-2b1f7d3-source-supplement.tar.gz](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz)
содержит точный снимок приложения и шесть обновлённых архивов зависимостей.
Для запуска AppImage исходные материалы не обязательны.

Размер дополнения составляет `745485` байт. Его SHA-256 равен
`66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`.
Файл текущего выпуска
[SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SHA256SUMS)
содержит суммы пяти остальных файлов выпуска, включая дополнение.
У частей базового комплекта отдельные контрольные суммы. Они остаются
в прежнем выпуске.
[Опубликованный SOURCE_MATERIALS.md](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/SOURCE_MATERIALS.md)
описывает оба набора и их точные контрольные суммы.

Скачайте дополнение в новую папку. Откройте в ней терминал и выполните
следующий блок Bash. Он проверит архив, извлечёт его в собственную папку
и проверит каждый включённый файл. Права администратора не нужны.

```bash
set -euo pipefail
printf '%s  %s\n' '66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e' 'Tokenlogue-2b1f7d3-source-supplement.tar.gz' | sha256sum --check -
test ! -e Tokenlogue-2b1f7d3-source-supplement
tar --extract --gzip --file Tokenlogue-2b1f7d3-source-supplement.tar.gz --no-same-owner --no-same-permissions
(cd Tokenlogue-2b1f7d3-source-supplement && sha256sum --check SHA256SUMS)
```

Если проверенный базовый комплект уже есть, используйте его без изменений.
Иначе скачайте следующие семь частей в ту же папку рядом с распакованным
дополнением. Сохраните точные имена и не пересжимайте части. Предусмотрите
не менее 25 ГБ для частей и распакованного базового комплекта вместе.

| Порядок | Скачивание | Байты |
| --- | --- | --- |
| 1 | [Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | `2000000000` |
| 2 | [Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | `2000000000` |
| 3 | [Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | `2000000000` |
| 4 | [Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | `2000000000` |
| 5 | [Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | `2000000000` |
| 6 | [Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | `2000000000` |
| 7 | [Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | `338636800` |

Суммы частей находятся в
`Tokenlogue-2b1f7d3-source-supplement/baseline/BASELINE_PARTS.SHA256SUMS`.
Они совпадают с опубликованным файлом базового комплекта
[SOURCE_PARTS.SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.SHA256SUMS).
Выполните следующий блок из папки с семью частями. Он проверит каждую часть
и объединённый поток до распаковки. Блок использует явный список файлов
и не создаёт вторую полную копию tar.

```bash
set -euo pipefail
sha256sum --check Tokenlogue-2b1f7d3-source-supplement/baseline/BASELINE_PARTS.SHA256SUMS
tokenlogue_baseline_digest=$(cat \
  Tokenlogue-986c6ad-source-materials.tar.part001 \
  Tokenlogue-986c6ad-source-materials.tar.part002 \
  Tokenlogue-986c6ad-source-materials.tar.part003 \
  Tokenlogue-986c6ad-source-materials.tar.part004 \
  Tokenlogue-986c6ad-source-materials.tar.part005 \
  Tokenlogue-986c6ad-source-materials.tar.part006 \
  Tokenlogue-986c6ad-source-materials.tar.part007 | sha256sum)
test "$tokenlogue_baseline_digest" = 'd66c43a31d810431af18defdc1642f235d072bdec9c9c281b3ed3dc3a72d4cf2  -'
test ! -e Tokenlogue-986c6ad-source-materials
cat \
  Tokenlogue-986c6ad-source-materials.tar.part001 \
  Tokenlogue-986c6ad-source-materials.tar.part002 \
  Tokenlogue-986c6ad-source-materials.tar.part003 \
  Tokenlogue-986c6ad-source-materials.tar.part004 \
  Tokenlogue-986c6ad-source-materials.tar.part005 \
  Tokenlogue-986c6ad-source-materials.tar.part006 \
  Tokenlogue-986c6ad-source-materials.tar.part007 | tar --extract --file - --no-same-owner --no-same-permissions
```

Сохраните обе распакованные папки и оригинальные архивы без изменений.
Базовый комплект уже содержит `Tokenlogue-14b87ac-source-materials.zip`,
поэтому отдельно скачивать его не нужно. Не переименовывайте старые части
исходников в комплект для `2b1f7d3`.

Файл `baseline.json` дополнения указывает файлы базового комплекта и их
контрольные суммы. Файл `manifest.json` описывает текущий снимок приложения,
архивы зависимостей и включённые файлы. Файл `replacements.json` задаёт
точные пути, которые нужно выбирать вместо прежних архивов приложения
и зависимостей.
Выберите `application/tokenlogue-2b1f7d3-source.tar` из дополнения как
эталон исходников приложения из коммита
`2b1f7d30e612416d8d88adde18a44aa235a7fe25`. Он заменяет
`source-materials-986c6ad/application/tokenlogue-986c6ad.tar` базового комплекта.
Для следующих пакетов выберите архивы из `dart/` дополнения вместо прежних
архивов внутри исторического ZIP.

| Пакет | Версия базового комплекта | Версия дополнения |
| --- | --- | --- |
| `flutter_secure_storage_platform_interface` | `2.1.0` | `2.1.1` |
| `serious_python_android` | `4.7.0` | `4.7.2` |
| `serious_python_darwin` | `4.7.0` | `4.7.2` |
| `serious_python_linux` | `4.7.0` | `4.7.2` |
| `serious_python_platform_interface` | `4.7.0` | `4.7.2` |
| `serious_python_windows` | `4.7.0` | `4.7.2` |

Остальные 142 hosted-пакета сохраняют соответствующие версии базового набора.
Python/PBS, соответствующие материалы Ubuntu, комплект runtime и другие
ранее сопоставленные входы остаются ссылочными материалами базового набора.
Дополнение не отменяет прежние замены в базовом комплекте и не делает
старые файлы приложения и runtime текущими входами.

Дополнение также содержит встроенный Flutter lock, опись уведомлений,
оригинальные лицензии, метаданные pub.dev и `license-comparison.json`.
Хеши шести архивов совпадают с lock и метаданными pub.dev. Их оригинальные
файлы LICENSE побайтно совпадают с прежними версиями и телами
соответствующих уведомлений AppImage. Отдельных файлов NOTICE или COPYRIGHT
в этих шести архивах не найдено.

### Комплект исходников runtime

В AppImage есть небольшой компонент запуска, называемый runtime.
[Отдельный комплект исходников runtime из базового набора](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip)
доступен как `appimage-runtime-34749438406-1.zip` в
[базовом выпуске для `986c6ad`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad).
Вход в GitHub не нужен. ZIP содержит оригинальный комплект runtime.

В комплект входят исполняемый runtime, архивы исходников, рецепты, патчи,
оригинальные пакеты Alpine, список инструментов, файлы для линковки, тексты лицензий
и контрольные суммы. Содержимое описано в
[обзоре runtime](../packaging/linux/appimage/runtime/README.md#lang-ru).
Полный комплект поставляется отдельно от AppImage.

### Каких исходных материалов пока не хватает

Статус полноты исходников остаётся `REVIEW_REQUIRED`. Ни базовый комплект,
ни дополнение не подтверждают полноту исходников всего AppImage.
В сохранённом комплекте входов Flutter есть 118 из 119 входов. Внутренний
пакет RBE `flutter_internal/rbe/reclient_cfgs`, instance
`0vARzGeIZgIhW7zVfWuqIPQ_HXMLDccjAstykWZKjaEC`, по-прежнему отсутствует.
Его условие `use_rbe` по умолчанию равно `false`.

Полная пересборка без сети, начальная сборка компилятора, полнота исходников
бинарных инструментов, hooks, перелинковка и формирование подмножеств шрифтов
не проверены. Ссылочные бинарные файлы CIPD и PBS/runtime не подтверждают
полноту исходников или материалов для сборки. Проверенная целостность файлов
и обновление шести пакетов не закрывают эти более широкие проверки.

### Исторические комплекты исходников

[Исторический комплект для 14b87ac](releases/14b87ac-source-materials.md#lang-ru)
содержит материалы приложения, Ubuntu, Python, Dart, Flutter и шрифтов.
Список зависимостей Flutter engine ссылается на внешние Git-репозитории
и материалы CIPD, которые вложены не полностью. Начальная сборка компилятора,
повторная линковка, формирование подмножеств шрифтов и пересборка всего
приложения не проверены.

Исторический комплект сам по себе не содержал всех исходников для версии `986c6ad`.
Различаются версии следующих зависимостей:

| Компонент | Комплект для `14b87ac` | AppImage `986c6ad` |
| --- | --- | --- |
| Dart `archive` | `4.2.0` | `4.3.0` |
| Dart `image` | `4.9.2` | `4.10.1` |
| `flutter_secure_storage_linux` | `3.0.2` | `3.0.3` |
| Ubuntu `libgcrypt20` | `1.9.4-3ubuntu3.2` | `1.9.4-3ubuntu3.3` |

Исходные файлы этих новых версий включены в опубликованный базовый комплект
для `986c6ad`. Эти прежние замены продолжают действовать при использовании
базового комплекта с текущим дополнением. Исторический архив сохраняет
первоначальные версии.

[Руководство по лицензиям](../packaging/linux/appimage/notices.md#lang-ru)
поможет найти оригинальные тексты лицензий, включённые в приложение.

[К Tokenlogue](../README.md#lang-ru)
