# Tokenlogue 14b87ac - Source archive / Архив исходников

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This collection was assembled on 10 September 2026 for the older AppImage
`14b87ac`. It is not the complete source bundle for preview `1472c00`.
See [current source materials](../source-materials.md#lang-en) for that version.

### Archive details

If you already have `Tokenlogue-14b87ac-source-materials.zip`, use the values
below to identify your copy. This page does not offer a download link for the ZIP.

| Property | Value |
| --- | --- |
| Application commit | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| Source archive | `Tokenlogue-14b87ac-source-materials.zip` |
| Archive size in bytes | `440966310` |
| Archive SHA-256 | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| Corresponding AppImage SHA-256 | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

The AppImage itself is not included in this archive. Its identity is described
in the [historical preview record](v0.1.0-linux-preview.1.md#lang-en).

### Included materials

The collection contains Tokenlogue sources, Ubuntu source packages and
packaging, CPython 3.12.14 with Python Build Standalone recipes, Python source
distributions, Dart packages, Flet 0.86.5, Flutter 3.44.8, Dart bridge 1.9.0,
font source files and materials for the older runtime.

The exact Flutter engine revision is
`0cd610717bde95fd88343c64f81c11ba4e5c0010`.
Its dependency inventory is included. The source manifest
`source-materials.json` records file sizes and SHA-256 values, and
`coverage.json` associates materials with components.

The older Ubuntu libgcrypt20 source package is linked to its
[retained Launchpad publication](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640).
The [historical type2-runtime sources](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c)
identify the upstream runtime code. They identify the sources used for those components. The limitations of
the full collection are described below.

### Checking a copy

After extracting the ZIP, open a terminal in its
`Tokenlogue-14b87ac-source-materials` folder, where `verify_materials.py`
is located. With Python 3 available, run the following command.

```bash
python3 verify_materials.py
```

The included checker compares the archive's files with its manifest.
It checks whether the supplied files are intact. It does not check that all
files needed to rebuild the application are present.

### What this archive cannot provide

The collection is incomplete. It contains Alpine recipes that may correspond
to the older runtime, but no confirmed list of the packages used to build it.
Version `1472c00` uses a different runtime with a separate source bundle.

The Flutter engine dependency inventory contains 109 entries. Not every
external Git repository or CIPD asset is archived, so an offline engine build
from this ZIP alone is not established. Compiler bootstrap, relinking, font
subsetting and a whole-application rebuild remain unverified.

The source archive is associated with `14b87ac`. It cannot be assumed to
cover newer application code, runtime inputs or dependency versions.

<a name="lang-ru"></a>

## Русский

Комплект собран 10 сентября 2026 года для прежнего AppImage `14b87ac`.
Он не является полным комплектом исходников предварительной сборки `1472c00`.
Для неё смотрите [текущие исходные материалы](../source-materials.md#lang-ru).

### Данные архива

Если у вас уже есть `Tokenlogue-14b87ac-source-materials.zip`, сверьте его
со значениями ниже. На этой странице нет ссылки для скачивания ZIP.

| Свойство | Значение |
| --- | --- |
| Коммит приложения | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| Архив исходников | `Tokenlogue-14b87ac-source-materials.zip` |
| Размер архива в байтах | `440966310` |
| SHA-256 архива | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| SHA-256 соответствующего AppImage | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

Сам AppImage в архив не включён. Его данные приведены в
[описании прежней сборки](v0.1.0-linux-preview.1.md#lang-ru).

### Включённые материалы

Комплект содержит исходники Tokenlogue, исходные пакеты Ubuntu и их правила
упаковки, CPython 3.12.14 с рецептами Python Build Standalone, исходные
дистрибутивы Python-пакетов, пакеты Dart, Flet 0.86.5, Flutter 3.44.8,
Dart bridge 1.9.0, исходные файлы шрифтов и материалы старого runtime.

Точная версия Flutter engine -
`0cd610717bde95fd88343c64f81c11ba4e5c0010`.
Список её зависимостей включён в комплект. В манифесте
`source-materials.json` записаны размеры файлов и SHA-256, а
`coverage.json` связывает материалы с компонентами.

Старый исходный пакет Ubuntu libgcrypt20 связан с
[сохранённой публикацией Launchpad](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640).
[Исторические исходники type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c)
указывают на исходный код runtime. По этим ссылкам можно найти исходники указанных компонентов.
Ограничения полного комплекта описаны ниже.

### Проверка копии

После распаковки ZIP откройте терминал в его папке
`Tokenlogue-14b87ac-source-materials`, где находится `verify_materials.py`.
При установленном Python 3 выполните следующую команду.

```bash
python3 verify_materials.py
```

Включённый проверяющий скрипт сопоставляет файлы архива с манифестом.
Он проверяет целостность включённых файлов. Наличие всех материалов,
необходимых для пересборки приложения, этот скрипт не проверяет.

### Чего не хватает в этом архиве

Комплект неполон. В нём есть рецепты Alpine, которые могут соответствовать
старому runtime, но точный список пакетов его сборки неизвестен.
Версия `1472c00` использует другой runtime с отдельным комплектом исходников.

Опись зависимостей Flutter engine содержит 109 записей. Внешние Git-репозитории
и материалы CIPD вложены не полностью, поэтому сборка engine без сети
только из этого ZIP не подтверждена. Начальная сборка компилятора, повторная
линковка, формирование подмножеств шрифтов и пересборка всего приложения
остаются непроверенными.

Архив относится к `14b87ac`. Для более новых версий приложения, runtime
и зависимостей потребуются соответствующие им исходники.
