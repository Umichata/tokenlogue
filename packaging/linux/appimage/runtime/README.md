# Tokenlogue - AppImage runtime

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

The runtime is the small executable at the beginning of an AppImage. It mounts
or extracts the contained filesystem and starts Tokenlogue. It is already
included in the [Linux preview](../../../../docs/linux-appimage.md#lang-en).
You do not need to install or launch a separate runtime binary.

### Source bundle

Previews `2b1f7d3` and `986c6ad` use the same runtime. Download
[appimage-runtime-34749438406-1.zip](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip)
from the [previous preview 986c6ad](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad).
No GitHub sign-in is needed. This is the original runtime bundle from
producer run `34749438406`, attempt `1`.

| File or directory | Contents |
| --- | --- |
| `runtime-x86_64` | The standalone startup component. |
| `runtime.lock.json` | Versions and checksums of source files and packages. |
| `manifest.json` | File inventory and component provenance. |
| `SHA256SUMS` | Checksums of the supplied files. |
| `materials/` | Source archives, recipes, patches, original packages and licenses. |
| `materials/linked-inputs/` | Saved inputs used to link the runtime. |

To check an extracted bundle, open a terminal in its root folder containing
`SHA256SUMS` and run the following command.

```bash
sha256sum --check SHA256SUMS
```

All listed files should pass. This checks their integrity without executing
the runtime. Checksums are not a digital signature.

### What the bundle covers

This is an unofficial Tokenlogue runtime based on
[type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c).
Its components include libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11,
GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 and mimalloc2 2.1.7-r0.

The AppImage carries the corresponding runtime license texts. The separate
bundle includes the original sources, Alpine inputs and linked materials.
Use the recipes and versions in this bundle when rebuilding this runtime.
Changing them can produce a different binary.

Completeness of the full application source collection remains unconfirmed.
Its status remains `REVIEW_REQUIRED`. A full offline rebuild has not been verified.
See [available sources and limitations](../../../../docs/source-materials.md#lang-en)
and the [license guide](../notices.md#lang-en).

<a name="lang-ru"></a>

## Русский

Runtime - небольшой исполняемый компонент в начале AppImage. Он монтирует
или распаковывает вложенную файловую систему и запускает Tokenlogue.
Runtime уже включён в [сборку для Linux](../../../../docs/linux-appimage.md#lang-ru).
Устанавливать или запускать его отдельный исполняемый файл не нужно.

### Комплект исходников

В предварительных сборках `2b1f7d3` и `986c6ad` используется один runtime. Скачайте
[appimage-runtime-34749438406-1.zip](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip)
из [прежнего выпуска 986c6ad](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad).
Вход в GitHub не нужен. Это оригинальный комплект runtime из запуска
производителя `34749438406`, попытка `1`.

| Файл или каталог | Содержимое |
| --- | --- |
| `runtime-x86_64` | Отдельный компонент запуска. |
| `runtime.lock.json` | Версии и контрольные суммы исходников и пакетов. |
| `manifest.json` | Опись файлов и сведения о происхождении компонентов. |
| `SHA256SUMS` | Контрольные суммы файлов комплекта. |
| `materials/` | Архивы исходников, рецепты, патчи, оригинальные пакеты и лицензии. |
| `materials/linked-inputs/` | Библиотеки и другие файлы, использованные при линковке runtime. |

Для проверки распакованного комплекта откройте терминал в его корневой папке
с `SHA256SUMS` и выполните следующую команду.

```bash
sha256sum --check SHA256SUMS
```

Все перечисленные файлы должны пройти проверку. Команда проверяет целостность
без выполнения runtime. Контрольные суммы не являются цифровой подписью.

### Состав и назначение комплекта

Это неофициальный runtime Tokenlogue на основе
[type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c).
В его состав входят libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11,
GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 и mimalloc2 2.1.7-r0.

В AppImage находятся тексты лицензий компонентов runtime. В отдельном
комплекте сохранены оригинальные исходники, пакеты Alpine и файлы для линковки.
Для пересборки этого runtime используйте рецепты и версии из комплекта.
Их изменение может привести к созданию другого исполняемого файла.

Полнота комплекта исходников всего приложения остаётся неподтверждённой.
Статус остаётся `REVIEW_REQUIRED`. Полная пересборка без сети не проверена.
Подробнее на страницах [доступных материалов и ограничений](../../../../docs/source-materials.md#lang-ru)
и [лицензий](../notices.md#lang-ru).
