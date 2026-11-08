# Historical source collection / Исторический комплект исходников

[English](#english) · [Русский](#russian)

<a id="lang-en"></a>
<a id="english"></a>

## English

This collection was assembled on 10 September 2026 for the [earlier Linux preview](v0.1.0-linux-preview.1.md#english). It preserves that version's source materials. It is also retained inside the later [published baseline](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad), where selected unchanged dependencies can be reused.

### Identify the archive

| Archive detail | Value |
| --- | --- |
| File | `Tokenlogue-14b87ac-source-materials.zip` |
| Size | 440,966,310 bytes |
| SHA-256 | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| Application source | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| Corresponding AppImage SHA-256 | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

The application binary is not inside this archive. There is no separate ZIP download linked here. To obtain its retained copy, follow the [baseline restoration guide](../source-materials.md#english).

### Contents and integrity

The ZIP includes Tokenlogue sources, Ubuntu source packages and packaging, CPython 3.12.14, Python Build Standalone recipes, Python source distributions, Dart packages, Flet 0.86.5, Flutter 3.44.8, Dart bridge 1.9.0, font inputs and older runtime materials.

The recorded Flutter engine revision is `0cd610717bde95fd88343c64f81c11ba4e5c0010`. The included `source-materials.json` records file sizes and SHA-256 values. `coverage.json` maps materials to components.

After extracting the ZIP, open a terminal in `Tokenlogue-14b87ac-source-materials` and run its included checker with Python 3.

```bash
python3 verify_materials.py
```

The checker verifies the supplied files against the manifest. It does not establish that every file needed for a complete rebuild is present.

### Scope of this historical collection

The earlier Ubuntu libgcrypt20 sources have a [retained Launchpad publication](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640). The [historical type2-runtime source revision](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c) identifies the older upstream code. The ZIP contains Alpine recipes that may correspond to the older runtime, but no confirmed inventory of the packages used to build it.

The Flutter engine dependency inventory contains 109 entries. Some external Git and CIPD inputs are not included. Offline engine compilation, compiler bootstrap, relinking, font subsetting and a whole-application rebuild from this ZIP alone are not established.

Later packages have different application code, runtime inputs and some dependency versions. For example, the subsequent baseline replaces Dart `archive` 4.2.0 with 4.3.0, Dart `image` 4.9.2 with 4.10.1, `flutter_secure_storage_linux` 3.0.2 with 3.0.3 and Ubuntu `libgcrypt20` 1.9.4-3ubuntu3.2 with 1.9.4-3ubuntu3.3. The historical ZIP keeps its original versions.

Use the [source materials guide](../source-materials.md#english) and the index supplied with your package to select matching files.

<a id="lang-ru"></a>
<a id="russian"></a>

## Русский

Комплект собран 10 сентября 2026 года для [прежней Linux-сборки](v0.1.0-linux-preview.1.md#russian). Он сохраняет исходные материалы той версии. Его копия также включена в более поздний [опубликованный базовый набор](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad), откуда можно повторно использовать выбранные неизменившиеся зависимости.

### Данные архива

| Данные архива | Значение |
| --- | --- |
| Файл | `Tokenlogue-14b87ac-source-materials.zip` |
| Размер | 440 966 310 байт |
| SHA-256 | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| Исходники приложения | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| SHA-256 соответствующего AppImage | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

Бинарное приложение в архив не входит. Отдельной ссылки на скачивание ZIP здесь нет. Чтобы получить сохранённую копию, используйте [инструкцию восстановления базового набора](../source-materials.md#russian).

### Состав и целостность

ZIP содержит исходники Tokenlogue, исходные пакеты Ubuntu и правила упаковки, CPython 3.12.14, рецепты Python Build Standalone, исходные дистрибутивы Python-пакетов, пакеты Dart, Flet 0.86.5, Flutter 3.44.8, Dart bridge 1.9.0, исходные файлы шрифтов и материалы прежнего runtime.

Записанная ревизия Flutter engine равна `0cd610717bde95fd88343c64f81c11ba4e5c0010`. Файл `source-materials.json` содержит размеры и SHA-256. Файл `coverage.json` связывает материалы с компонентами.

Распакуйте ZIP, откройте терминал в папке `Tokenlogue-14b87ac-source-materials` и запустите включённый проверяющий скрипт с Python 3.

```bash
python3 verify_materials.py
```

Скрипт проверяет соответствие предоставленных файлов манифесту. Он не подтверждает наличие каждого файла, необходимого для полной пересборки.

### Границы исторического комплекта

Для прежних исходников Ubuntu libgcrypt20 сохранена [публикация Launchpad](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640). [Историческая ревизия type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c) указывает на прежний исходный код. В ZIP есть рецепты Alpine, которые могут соответствовать старому runtime, но нет подтверждённой описи пакетов его сборки.

Опись зависимостей Flutter engine содержит 109 записей. Часть внешних входов Git и CIPD не включена. Сборка engine без сети, начальная сборка компилятора, перелинковка, создание подмножеств шрифтов и пересборка всего приложения только из этого ZIP не подтверждены.

У более поздних пакетов другие исходники приложения, входы runtime и некоторые версии зависимостей. Например, следующий базовый набор заменяет Dart `archive` 4.2.0 на 4.3.0, Dart `image` 4.9.2 на 4.10.1, `flutter_secure_storage_linux` 3.0.2 на 3.0.3 и Ubuntu `libgcrypt20` 1.9.4-3ubuntu3.2 на 1.9.4-3ubuntu3.3. Исторический ZIP сохраняет первоначальные версии.

Чтобы выбрать соответствующие файлы, используйте [руководство по исходным материалам](../source-materials.md#russian) и индекс из вашего пакета.
