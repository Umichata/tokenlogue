<p align="left">
<a href="source-materials.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="source-materials.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-be11dde003f4.svg" alt="Карта документации" width="207" height="38"></a> <a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a>
</p>

# Исходные материалы

<a id="russian"></a>
<a id="lang-ru"></a>

Tokenlogue распространяется по <a href="../LICENSE" title="лицензии MIT">лицензии MIT&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Репозиторий содержит приложение, закреплённые зависимости и рецепты упаковки. Для сторонних компонентов действуют собственные лицензии.

<a id="-исходники-приложения"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники приложения

Используйте версию исходников, указанную в `PROVENANCE.json` вашего пакета. Более поздняя версия репозитория может содержать другой код или документацию. Архив исходников приложения и наборы зависимостей ниже выполняют разные задачи.

<a id="ru-run-from-source"></a>

<a id="-запуск-из-исходников-в-linux"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск из исходников в Linux

Установите Python 3.12 и [uv](https://docs.astral.sh/uv/). Получите исходники проекта и откройте терминал в папке с `pyproject.toml` и `uv.lock`. Также действуют <a href="linux-appimage.ru.md#russian" title="требования Linux к рабочему столу и хранилищу ключей">требования Linux к рабочему столу и хранилищу ключей&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
```bash
uv sync --locked
uv run --locked flet run
```

Команды запускают приложение из исходников. Они не создают AppImage или APK. Для подготовки окружения и загрузки настольных компонентов Flet может понадобиться интернет. Для запуска готовых пакетов отдельно устанавливать Python и Flutter не нужно.

<a id="-как-выбрать-соответствующий-комплект"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Как выбрать соответствующий комплект

Начните с `SOURCE_MATERIALS.md` и `SOURCE_MATERIALS.json`, которые поставляются с вашим пакетом. JSON связывает каждый идентифицированный компонент с точным файлом внутри архива, версией, размером и SHA-256. Сохраняйте указанные архивы без изменений. Общий набор зависимостей может подходить новой сборке, но это не делает старый снимок приложения актуальным.

На <a href="https://github.com/Umichata/tokenlogue/releases" title="странице Releases">странице Releases&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> находятся опубликованные файлы. Ниже перечислены существующие комплекты исходников.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Комплект | Содержимое |
| --- | --- |
| [Опубликованный базовый набор](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad) | Семь упорядоченных частей с общими зависимостями прежних версий, рецептами и комплектом runtime |
| [Опубликованное дополнение](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz) | Шесть обновлённых архивов Dart-зависимостей и снимок приложения того прежнего Linux-выпуска |
| Дополнения конкретного пакета | Дополнительные исходники, патчи и рецепты из индекса, приложенного к более новой сборке |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Дополнение имеет размер 745 485 байт и SHA-256 `66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`. Включённый снимок приложения относится к собственному выпуску дополнения. Он не заменяет исходную ревизию более нового пакета.

<a id="-восстановление-опубликованного-базового-набора"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Восстановление опубликованного базового набора

Скачайте все семь частей в одну папку. Сохраните точные имена. Общий размер частей составляет 12 338 636 800 байт. Предусмотрите не менее 30 ГБ для скачанных частей и распакованных материалов.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Часть | Байты |
| --- | --- |
| [1 · Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | 2,000,000,000 |
| [2 · Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | 2,000,000,000 |
| [3 · Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | 2,000,000,000 |
| [4 · Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | 2,000,000,000 |
| [5 · Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | 2,000,000,000 |
| [6 · Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | 2,000,000,000 |
| [7 · Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | 338,636,800 |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

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

<a id="-что-подтверждают-имеющиеся-материалы"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Что подтверждают имеющиеся материалы

Наличие целого исходного архива и связь конкретного бинарника с исходниками проверяются отдельно. Для следующих компонентов в текущих комплектах Android и Linux есть исходники и рецепты, но выбранные wheels не полностью связаны со всеми фактическими ревизиями исходников, патчами и входами сборки.

- Android CFFI 2.0.0, PyCryptodomex 3.23.0 и msgpack 1.1.2.
- Linux CFFI 2.0.0 и PyCryptodomex 3.23.0.

Точные исходники и патчи libffi в выбранных wheels CFFI установлены не полностью. Libffi 3.4.4 из Android runtime и libffi 3.4.8 из Linux Python runtime относятся к другим компонентам. В рецепте Linux CFFI указана libffi 3.4.6, но один рецепт не доказывает состав библиотеки внутри wheel.

Сохранённые бинарные компиляторы являются входами сборки, а не исходниками компилятора. Комплект не подтверждает полную пересборку без сети и независимое воспроизведение каждой нативной зависимости. Одинаковый номер версии исходного архива и совпадение его контрольной суммы сами по себе не устанавливают такую связь. Эти технические ограничения рассматриваются отдельно от работы приложения на конкретном устройстве.

<a id="-лицензии-и-прежние-комплекты"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Лицензии и прежние комплекты

<a href="../packaging/linux/appimage/notices.ru.md#russian" title="Руководство по лицензиям">Руководство по лицензиям&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> объясняет, где находятся оригинальные уведомления в пакетах. <a href="releases/14b87ac-source-materials.ru.md#russian" title="Исторический комплект исходников">Исторический комплект исходников&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> и <a href="releases/v0.1.0-linux-preview.1.ru.md#russian" title="описание прежней Linux-сборки">описание прежней Linux-сборки&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> относятся к собственным файлам. Их прежние версии и ограничения не переносятся автоматически на новые пакеты.

<p align="left"><a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-6382944424ac.svg" alt="К Tokenlogue" width="124" height="28"></a></p>
