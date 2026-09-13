# Tokenlogue - Source materials / Исходные материалы

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This page describes sources for the `0.1.0` Linux preview `1472c00`.
To download the ready-to-use application, follow the [AppImage guide](linux-appimage.md#en-download).

### Application source

The [application source at 1472c00](https://github.com/Umichata/tokenlogue/tree/1472c00d38a87dddfa33cdb8c9c0d3b6aadb02f6)
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

### Runtime source bundle

The AppImage includes a small startup component called the runtime.
Its [separate source bundle](https://github.com/Umichata/tokenlogue/actions/runs/34749438406)
is the Actions artifact `appimage-runtime-34749438406-1`. You may need to sign in to GitHub to download it.
Artifact retention is limited, so keep a local copy if you need the bundle.

The bundle contains the runtime binary, source archives, recipes, patches,
original Alpine packages, tool inventory, linked inputs, license texts and
checksums. The [runtime overview](../packaging/linux/appimage/runtime/README.md#lang-en)
explains its contents. The full bundle is separate from the AppImage.

### Which source materials are still missing

The source collection for the full application is not yet complete.
The runtime bundle covers the startup component. Additional Flutter SDK
materials are needed, and an offline rebuild of the full application has
not been verified.

A [historical source collection for 14b87ac](releases/14b87ac-source-materials.md#lang-en)
includes application, Ubuntu, Python, Dart, Flutter and font materials.
Its Flutter engine dependency list references external Git repositories and
CIPD assets that are not all archived. Compiler bootstrap, relinking,
font subsetting and a full application rebuild have not been verified.

The older collection is not a complete source bundle for
`1472c00`. In particular, the new preview uses
`flutter_secure_storage_linux` `3.0.3`, while the old collection records
`3.0.2`. Ubuntu's `libgcrypt20` also changed from `1.9.4-3ubuntu3.2` to
`1.9.4-3ubuntu3.3`. These dependency versions need their own matching source files.

The [license guide](../packaging/linux/appimage/notices.md#lang-en) explains
where to find the original license texts supplied with the application.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Страница описывает исходники предварительной Linux-сборки `0.1.0` версии
`1472c00`. Готовое приложение можно скачать по
[инструкции для AppImage](linux-appimage.md#ru-download).

### Исходники приложения

[Исходный код приложения 1472c00](https://github.com/Umichata/tokenlogue/tree/1472c00d38a87dddfa33cdb8c9c0d3b6aadb02f6)
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

### Комплект исходников runtime

В AppImage есть небольшой компонент запуска, называемый runtime.
Его [отдельный комплект исходников](https://github.com/Umichata/tokenlogue/actions/runs/34749438406)
находится в артефакте Actions `appimage-runtime-34749438406-1`. Для скачивания
может потребоваться вход в GitHub. Срок хранения артефакта ограничен, поэтому
сохраните локальную копию, если комплект вам нужен.

В комплект входят исполняемый runtime, архивы исходников, рецепты, патчи,
оригинальные пакеты Alpine, список инструментов, файлы для линковки, тексты лицензий
и контрольные суммы. Содержимое описано в
[обзоре runtime](../packaging/linux/appimage/runtime/README.md#lang-ru).
Полный комплект поставляется отдельно от AppImage.

### Каких исходных материалов пока не хватает

Комплект исходников всего приложения пока неполон. Комплект runtime охватывает
компонент запуска. Нужны дополнительные материалы Flutter SDK, а пересборка
всего приложения без сети не проверена.

[Исторический комплект для 14b87ac](releases/14b87ac-source-materials.md#lang-ru)
содержит материалы приложения, Ubuntu, Python, Dart, Flutter и шрифтов.
Список зависимостей Flutter engine ссылается на внешние Git-репозитории
и материалы CIPD, которые вложены не полностью. Начальная сборка компилятора,
повторная линковка, формирование подмножеств шрифтов и пересборка всего
приложения не проверены.

Старый комплект не содержит всех исходников для версии
`1472c00`. В частности, новая сборка использует
`flutter_secure_storage_linux` `3.0.3`, а старый комплект описывает
`3.0.2`. Версия Ubuntu-пакета `libgcrypt20` также изменилась с
`1.9.4-3ubuntu3.2` на `1.9.4-3ubuntu3.3`. Для этих версий зависимостей нужны соответствующие им исходные файлы.

[Руководство по лицензиям](../packaging/linux/appimage/notices.md#lang-ru)
поможет найти оригинальные тексты лицензий, включённые в приложение.

[К Tokenlogue](../README.md#lang-ru)
