<p align="left">
<a href="source-materials.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="source-materials.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Исходные материалы

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **Начальная предварительная версия 0.1.0 — черновик.** Пока выпуск находится в черновике, пакеты приложения и их исходные архивы недоступны для публичного скачивания. Имена файлов и суммы ниже описывают подготовленный комплект.

Код приложения Tokenlogue доступен по [лицензии MIT](../LICENSE). Сторонние компоненты сохраняют собственные условия. Готовые APK и AppImage скачиваются отдельно. Для запуска приложения исходники и средства сборки не нужны.

<a id="-исходники-приложения"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники поставленного приложения

Выберите архив проекта для своей платформы из [`PROVENANCE.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/PROVENANCE.json). Пакеты Android и Linux собраны из разных ревизий упаковки с одинаковым общим ядром приложения. Commit, дерево и контрольные суммы связывают каждый пакет с его точными исходниками. Более поздняя версия репозитория или README платформенной ветки не меняют это происхождение.

В [черновике начального выпуска](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) указаны подготовленные файлы версии `0.1.0`. Сторонние исходные материалы собраны в одном архиве зависимостей с реестром. Файлы черновика станут публичными только после публикации выпуска.

<a id="-выбор-подходящего-комплекта"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Использование комплекта зависимостей

| Файл | Назначение |
| --- | --- |
| [Исходники проекта для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-eafb093-android-project-sources.tar.gz) | Точные отслеживаемые исходники приложения, lock-файлы и упаковка поставленного APK. |
| [Исходники проекта для Linux](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-project-sources.tar.gz) | Точные отслеживаемые исходники приложения, lock-файлы и упаковка поставленной AppImage. |
| [`Tokenlogue-0.1.0-dependency-sources.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-dependency-sources.tar.gz) | Идентифицированные сторонние исходники, оригинальные уведомления, изменения и рецепты без повторных копий одинаковых файлов. |
| [`SOURCE_MATERIALS.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SOURCE_MATERIALS.json) | Версии, связи компонентов, относительные пути, размеры и SHA-256 материалов. Также описывает границы подтверждения исходников и происхождения бинарников. |
| [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) | Контрольные суммы загрузок выпуска. |

В архиве зависимостей нет дополнительной внешней папки. Он содержит двуязычный `README.md`, `SOURCE_MATERIALS.json`, `BUILD_INPUTS.json`, `RECONSTRUCTION.json`, `SHA256SUMS` и оригинальные файлы в `materials/<SHA-256>/<исходное имя>`. Одинаковый файл хранится один раз и может относиться к нескольким компонентам. Если исходники или уведомление находятся внутри сохранённого архива, реестр указывает точный внутренний путь.

В `BUILD_INPUTS.json` сохранены закреплённые источники, размеры и суммы отдельно получаемых компиляторов, runtime и инструментов. Среди них официальные upstream-загрузки, выбранные файлы официальных ISO Alpine и [текущий контейнер сборочных входов Tokenlogue](https://github.com/Umichata/tokenlogue/releases/tag/runtime-build-inputs-20261110). Последний не является официальным контейнером Alpine. Для ISO проверяются выбранные байты, а не сумма всего образа. Контейнер зависимостей проверяется целиком и по членам. Получение внешних сборочных входов может потребовать интернет. Сборочные входы идентифицированы независимо от архивов пакетов приложения.

Сохраните архив зависимостей и `SHA256SUMS` выпуска в одной папке. Проверьте выбранный архив до распаковки. Для команды нужны Bash и средства SHA-256.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-dependency-sources.tar.gz'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Выбранный файл должен получить `OK`. Отсутствующая или повторная запись в манифесте, отсутствующий файл и несовпадение суммы вызывают ошибку. Затем распакуйте материалы в новую пустую папку и проверьте их собственный манифест.

```bash
mkdir tokenlogue-dependency-sources &&
tar --extract --gzip --file Tokenlogue-0.1.0-dependency-sources.tar.gz \
  --directory tokenlogue-dependency-sources --no-same-owner --no-same-permissions &&
(cd tokenlogue-dependency-sources && sha256sum --check SHA256SUMS)
```

Манифест выпуска проверяет скачанный архив. Внутренний манифест проверяет распакованные файлы. Сохраняйте исходные архивы и оригинальные юридические тексты без изменений.

<a id="ru-run-from-source"></a>
<a id="-запуск-из-исходников-в-linux"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Запуск из исходников в Linux

Установите Python 3.12 и [uv](https://docs.astral.sh/uv/). Откройте терминал в распакованном каталоге проекта с `pyproject.toml` и `uv.lock`. Также действуют [требования Linux к рабочему столу и хранилищу ключей](linux-appimage.ru.md#russian).

```bash
uv sync --locked
uv run --locked flet run
```

Эти команды запускают приложение из исходников и не создают APK или AppImage. Подготовка окружения и получение desktop-компонентов Flet могут потребовать интернет. Для упаковки используйте рецепты и точные lock-файлы подходящего архива проекта. [Руководство по упаковке Linux](../packaging/linux/appimage/README.ru.md#russian), [рецепт стартового runtime Linux](../packaging/linux/appimage/runtime/README.ru.md#russian) и [руководство по нативным зависимостям Android](../packaging/android/crypto/README.ru.md#russian) описывают соответствующие компоненты.

<a id="-что-подтверждают-материалы"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Границы подтверждения происхождения

Наличие целого исходного архива отличается от доказательства, что из него получен конкретный бинарник. Совпадение версии и контрольной суммы загрузки подтверждает идентичность архива, а не полную связь исходников с wheel.

Эта связь остаётся неполной для Android CFFI 2.0.0, PyCryptodomex 3.23.0 и msgpack 1.1.2, а также для Linux CFFI 2.0.0 и PyCryptodomex 3.23.0. Точная ревизия libffi и патчи внутри выбранных wheel CFFI определены не полностью. Библиотека libffi среды Python является отдельным компонентом и не определяет библиотеку CFFI.

Комплект сохраняет все идентифицированные материалы и указывает границы проверки в реестре. Он не подтверждает полностью автономную офлайн-сборку и независимое воспроизведение каждой нативной зависимости. Отсутствие подтверждения издателя само по себе не доказывает отсутствие исходников. Эти ограничения происхождения отделены от работы на конкретном устройстве, включая настоящий ARM64 с ядром 16 КиБ.

<a id="-лицензии-и-прежние-комплекты"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Оригинальные уведомления

[Руководство по лицензиям пакета](../packaging/linux/appimage/notices.ru.md#russian) и раздел [о библиотеках и шрифтах](../packaging/notices/README.ru.md#russian) объясняют уведомления, поставляемые с приложением. Оригинальные лицензии и сведения об авторских правах сохранены полностью и без изменений. Наличие исходников, текст лицензии и связь бинарника со сборочными входами проверяются отдельно.

<p align="left"><a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-b038324b5bbd.svg" alt="Tokenlogue" width="109" height="28"></a></p>
