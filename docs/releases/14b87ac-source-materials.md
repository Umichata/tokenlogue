# Tokenlogue 14b87ac - Historical sources / Исторические исходники

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

[English](#lang-en) | [Русский](#lang-ru)

This collection was assembled on 10 September 2026 for the older AppImage
`14b87ac`. It is not the complete source bundle for preview `1472c00`.
See [current source materials](../source-materials.md#lang-en) for that version.

### Identifying a retained archive

The following values help recipients who already have the collection identify
it. A public download URL for this source ZIP is not established.

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
font inputs and historical runtime materials.

The exact Flutter engine revision is
`0cd610717bde95fd88343c64f81c11ba4e5c0010`.
Its dependency inventory is included. The source manifest
`source-materials.json` records file sizes and SHA-256 values, and
`coverage.json` associates materials with components.

The older Ubuntu libgcrypt20 source package is linked to its
[retained Launchpad publication](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640).
The [historical type2-runtime sources](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c)
identify the upstream runtime code. These links are not substitutes for a
complete corresponding-source archive.

### Checking a copy

After extracting the ZIP, open a terminal in its
`Tokenlogue-14b87ac-source-materials` folder, where `verify_materials.py`
is located. With Python 3 available, run the following command.

```bash
python3 verify_materials.py
```

The included checker compares the archive's files with its manifest.
A successful integrity check does not change the source-completeness status
or prove a rebuild.

### Historical limitations

The collection is incomplete. The Alpine recipes for the old runtime
are historical candidates without a confirmed original package
inventory. This limitation describes the old runtime, not the separate
runtime now used by `1472c00`.

The Flutter engine dependency inventory contains 109 entries. Not every
external Git repository or CIPD asset is archived, so an offline engine build
from this ZIP alone is not established. Compiler bootstrap, relinking, font
subsetting and a whole-application rebuild remain unverified.

The source archive is associated with `14b87ac`. It cannot be assumed to
cover newer application code, runtime inputs or dependency versions.

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-ru"></a>

## Русский

[English](#lang-en) | [Русский](#lang-ru)

Комплект собран 10 сентября 2026 года для прежнего AppImage `14b87ac`.
Он не является полным комплектом исходников предварительной сборки `1472c00`.
Для неё смотрите [текущие исходные материалы](../source-materials.md#lang-ru).

### Как определить сохранённый архив

Эти значения помогают определить комплект тем, у кого он уже есть.
Публичная ссылка для скачивания этого ZIP с исходниками не подтверждена.

| Свойство | Значение |
| --- | --- |
| Коммит приложения | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| Архив исходников | `Tokenlogue-14b87ac-source-materials.zip` |
| Размер архива в байтах | `440966310` |
| SHA-256 архива | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| SHA-256 соответствующего AppImage | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

Сам AppImage в архив не включён. Его данные приведены в
[исторической карточке сборки](v0.1.0-linux-preview.1.md#lang-ru).

### Включённые материалы

Комплект содержит исходники Tokenlogue, исходные пакеты Ubuntu и их правила
упаковки, CPython 3.12.14 с рецептами Python Build Standalone, исходные
дистрибутивы Python-пакетов, пакеты Dart, Flet 0.86.5, Flutter 3.44.8,
Dart bridge 1.9.0, входы шрифтов и исторические материалы runtime.

Точная версия Flutter engine -
`0cd610717bde95fd88343c64f81c11ba4e5c0010`.
Её опись зависимостей включена в комплект. В манифесте
`source-materials.json` записаны размеры файлов и SHA-256, а
`coverage.json` связывает материалы с компонентами.

Старый исходный пакет Ubuntu libgcrypt20 связан с
[сохранённой публикацией Launchpad](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640).
[Исторические исходники type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c)
указывают на исходный код runtime. Эти ссылки не заменяют полного архива
соответствующих исходников.

### Проверка копии

После распаковки ZIP откройте терминал в его папке
`Tokenlogue-14b87ac-source-materials`, где находится `verify_materials.py`.
При установленном Python 3 выполните следующую команду.

```bash
python3 verify_materials.py
```

Включённый проверяющий скрипт сопоставляет файлы архива с манифестом.
Успешная проверка целостности не меняет статус полноты исходников
и не подтверждает пересборку.

### Исторические ограничения

Комплект неполон. Рецепты Alpine для старого
runtime являются историческими кандидатами без подтверждённой описи
пакетов исходной сборки. Это ограничение относится к старому runtime,
а не к отдельному runtime, который теперь используется в `1472c00`.

Опись зависимостей Flutter engine содержит 109 записей. Внешние Git-репозитории
и материалы CIPD вложены не полностью, поэтому сборка engine без сети
только из этого ZIP не подтверждена. Начальная сборка компилятора, повторная
линковка, формирование подмножеств шрифтов и пересборка всего приложения
остаются непроверенными.

Архив связан с `14b87ac`. Нельзя автоматически считать, что он покрывает
более новый код приложения, входы runtime или версии зависимостей.

[English](#lang-en) | [Русский](#lang-ru)
