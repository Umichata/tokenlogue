# Source materials / Исходные материалы

[English](#english) · [Русский](#russian)

<a id="lang-en"></a>
<a id="english"></a>

## English

Tokenlogue is available under the [MIT License](../LICENSE). The repository contains the application, its dependency locks and packaging recipes. Third-party components retain their own licenses.

### Application sources

Use the source revision identified in your package's `PROVENANCE.json`. A later repository revision may include different code or documentation. The application source archive is distinct from the dependency collections below.

<a id="en-run-from-source"></a>

### Run from source on Linux

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). Download the project sources and open a terminal in the directory containing `pyproject.toml` and `uv.lock`. The [Linux desktop and key-store requirements](linux-appimage.md#english) also apply.

```bash
uv sync --locked
uv run --locked flet run
```

These commands run the source application. They do not create an AppImage or APK. Preparing the environment and downloading Flet desktop components may require internet access. Ready-to-use packages do not require a separate Python or Flutter installation.

### Find the matching collection

Start with the `SOURCE_MATERIALS.md` and `SOURCE_MATERIALS.json` supplied with your package. The JSON index maps each identified component to an exact archive member, version, size and SHA-256. Keep the named archives unchanged. A shared dependency collection can remain useful for a newer package without making its old application snapshot current.

The [Releases page](https://github.com/Umichata/tokenlogue/releases) contains published downloads. The established source collections are listed below.

| Collection | What it provides |
| --- | --- |
| [Published baseline](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad) | Seven ordered parts with earlier shared dependencies, source recipes and the runtime bundle |
| [Published supplement](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz) | Six updated Dart dependency archives and the application snapshot of that historical Linux release |
| Package-specific additions | The additional source archives, patches and recipes identified by the index supplied with a newer package |

The supplement is 745,485 bytes. Its SHA-256 is `66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`. Its application snapshot describes its own release. It does not replace the source revision named by a newer package.

### Restore the published baseline

Download all seven parts into the same directory. Keep their exact names. Their total size is 12,338,636,800 bytes. Allow at least 30 GB for the downloaded parts and extracted materials.

| Part | Bytes |
| --- | --- |
| [1 · Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | 2,000,000,000 |
| [2 · Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | 2,000,000,000 |
| [3 · Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | 2,000,000,000 |
| [4 · Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | 2,000,000,000 |
| [5 · Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | 2,000,000,000 |
| [6 · Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | 2,000,000,000 |
| [7 · Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | 338,636,800 |

Save [SOURCE_PARTS.SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.SHA256SUMS) and [SOURCE_PARTS.json](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.json) beside the parts. Check the individual files and the combined stream before extracting.

```bash
sha256sum --check SOURCE_PARTS.SHA256SUMS
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | sha256sum
```

The second command requires Bash. Its result must be `d66c43a31d810431af18defdc1642f235d072bdec9c9c281b3ed3dc3a72d4cf2`. After both checks succeed, extract into a new directory without creating another complete tar file.

```bash
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | tar --extract --file - --no-same-owner --no-same-permissions
```

The baseline already contains the historical source ZIP and `appimage-runtime-34749438406-1.zip`. The [separate runtime ZIP](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) is an alternative download of the same member. It is 391,916,671 bytes with SHA-256 `a9869ba745218ea8b0e2dec0c3da6af15b4d28fbd6e1ec1170afcadb758b06c9`. You do not need to download it twice.

### What the available materials establish

Identifying an intact source archive is different from establishing which sources produced a particular binary. The current Android and Linux collections include source archives and recipes for the following components, but their exact selected wheel bytes are not fully linked to all actual source revisions, patches and build inputs.

- Android CFFI 2.0.0, PyCryptodomex 3.23.0 and msgpack 1.1.2.
- Linux CFFI 2.0.0 and PyCryptodomex 3.23.0.

The exact libffi source and patches inside the selected CFFI wheels are not fully identified. Android runtime libffi 3.4.4 and Linux Python runtime libffi 3.4.8 are separate components. The Linux CFFI recipe names libffi 3.4.6, which alone does not prove the library in the wheel.

Retained compiler binaries are build inputs rather than compiler source. The collection does not establish a complete offline rebuild or independent reproduction of every native dependency. An archive with the same version number and matching download checksum does not establish that connection by itself. These technical limits are separate from whether the application runs on a particular device.

### Licenses and older collections

The [license guide](../packaging/linux/appimage/notices.md#english) explains where to find the original notices included in the packages. The [historical source collection](releases/14b87ac-source-materials.md#english) and [older Linux preview record](releases/v0.1.0-linux-preview.1.md#english) describe their own files. Their earlier versions and limitations do not automatically describe newer packages.

[Back to Tokenlogue](../README.md#english)

<a id="lang-ru"></a>
<a id="russian"></a>

## Русский

Tokenlogue распространяется по [лицензии MIT](../LICENSE). Репозиторий содержит приложение, закреплённые зависимости и рецепты упаковки. Для сторонних компонентов действуют собственные лицензии.

### Исходники приложения

Используйте версию исходников, указанную в `PROVENANCE.json` вашего пакета. Более поздняя версия репозитория может содержать другой код или документацию. Архив исходников приложения и наборы зависимостей ниже выполняют разные задачи.

<a id="ru-run-from-source"></a>

### Запуск из исходников в Linux

Установите Python 3.12 и [uv](https://docs.astral.sh/uv/). Получите исходники проекта и откройте терминал в папке с `pyproject.toml` и `uv.lock`. Также действуют [требования Linux к рабочему столу и хранилищу ключей](linux-appimage.md#russian).

```bash
uv sync --locked
uv run --locked flet run
```

Команды запускают приложение из исходников. Они не создают AppImage или APK. Для подготовки окружения и загрузки настольных компонентов Flet может понадобиться интернет. Для запуска готовых пакетов отдельно устанавливать Python и Flutter не нужно.

### Как выбрать соответствующий комплект

Начните с `SOURCE_MATERIALS.md` и `SOURCE_MATERIALS.json`, которые поставляются с вашим пакетом. JSON связывает каждый идентифицированный компонент с точным файлом внутри архива, версией, размером и SHA-256. Сохраняйте указанные архивы без изменений. Общий набор зависимостей может подходить новой сборке, но это не делает старый снимок приложения актуальным.

На [странице Releases](https://github.com/Umichata/tokenlogue/releases) находятся опубликованные файлы. Ниже перечислены существующие комплекты исходников.

| Комплект | Содержимое |
| --- | --- |
| [Опубликованный базовый набор](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad) | Семь упорядоченных частей с общими зависимостями прежних версий, рецептами и комплектом runtime |
| [Опубликованное дополнение](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz) | Шесть обновлённых архивов Dart-зависимостей и снимок приложения того прежнего Linux-выпуска |
| Дополнения конкретного пакета | Дополнительные исходники, патчи и рецепты из индекса, приложенного к более новой сборке |

Дополнение имеет размер 745 485 байт и SHA-256 `66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`. Включённый снимок приложения относится к собственному выпуску дополнения. Он не заменяет исходную ревизию более нового пакета.

### Восстановление опубликованного базового набора

Скачайте все семь частей в одну папку. Сохраните точные имена. Общий размер частей составляет 12 338 636 800 байт. Предусмотрите не менее 30 ГБ для скачанных частей и распакованных материалов.

| Часть | Байты |
| --- | --- |
| [1 · Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | 2,000,000,000 |
| [2 · Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | 2,000,000,000 |
| [3 · Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | 2,000,000,000 |
| [4 · Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | 2,000,000,000 |
| [5 · Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | 2,000,000,000 |
| [6 · Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | 2,000,000,000 |
| [7 · Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | 338,636,800 |

Сохраните [SOURCE_PARTS.SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.SHA256SUMS) и [SOURCE_PARTS.json](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.json) рядом с частями. До распаковки проверьте отдельные файлы и объединённый поток.

```bash
sha256sum --check SOURCE_PARTS.SHA256SUMS
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | sha256sum
```

Вторая команда требует Bash. Её результат должен равняться `d66c43a31d810431af18defdc1642f235d072bdec9c9c281b3ed3dc3a72d4cf2`. После успешной проверки обеими командами распакуйте материалы в новую папку без создания ещё одного полного tar.

```bash
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | tar --extract --file - --no-same-owner --no-same-permissions
```

Базовый набор уже содержит исторический ZIP исходников и `appimage-runtime-34749438406-1.zip`. [Отдельный runtime ZIP](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) является альтернативной загрузкой того же файла. Его размер составляет 391 916 671 байт, SHA-256 равен `a9869ba745218ea8b0e2dec0c3da6af15b4d28fbd6e1ec1170afcadb758b06c9`. Повторная загрузка не нужна.

### Что подтверждают имеющиеся материалы

Наличие целого исходного архива и связь конкретного бинарника с исходниками проверяются отдельно. Для следующих компонентов в текущих комплектах Android и Linux есть исходники и рецепты, но выбранные wheels не полностью связаны со всеми фактическими ревизиями исходников, патчами и входами сборки.

- Android CFFI 2.0.0, PyCryptodomex 3.23.0 и msgpack 1.1.2.
- Linux CFFI 2.0.0 и PyCryptodomex 3.23.0.

Точные исходники и патчи libffi в выбранных wheels CFFI установлены не полностью. Libffi 3.4.4 из Android runtime и libffi 3.4.8 из Linux Python runtime относятся к другим компонентам. В рецепте Linux CFFI указана libffi 3.4.6, но один рецепт не доказывает состав библиотеки внутри wheel.

Сохранённые бинарные компиляторы являются входами сборки, а не исходниками компилятора. Комплект не подтверждает полную пересборку без сети и независимое воспроизведение каждой нативной зависимости. Одинаковый номер версии исходного архива и совпадение его контрольной суммы сами по себе не устанавливают такую связь. Эти технические ограничения рассматриваются отдельно от работы приложения на конкретном устройстве.

### Лицензии и прежние комплекты

[Руководство по лицензиям](../packaging/linux/appimage/notices.md#russian) объясняет, где находятся оригинальные уведомления в пакетах. [Исторический комплект исходников](releases/14b87ac-source-materials.md#russian) и [описание прежней Linux-сборки](releases/v0.1.0-linux-preview.1.md#russian) относятся к собственным файлам. Их прежние версии и ограничения не переносятся автоматически на новые пакеты.

[К Tokenlogue](../README.md#russian)
