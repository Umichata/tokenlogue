<p align="left">
<a href="source-materials.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="source-materials.md" title="English"><img align="right" src="assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../README.ru.md" title="Главная"><img src="assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="README.ru.md" title="Карта документации"><img src="assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Исходники и зависимости

<a id="russian"></a>
<a id="lang-ru"></a>

<a id="ru-preview-status"></a>
> **[0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9)** · Пакеты приложения и соответствующие архивы исходников доступны для скачивания.

Код приложения Tokenlogue доступен по [лицензии MIT](../LICENSE). Сторонние компоненты сохраняют собственные условия. Готовые APK и AppImage скачиваются отдельно. Для запуска приложения исходники и средства сборки не нужны.

<a id="-исходники-приложения"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники приложения

Выберите исходный архив каждого пакета по [`PROVENANCE.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/PROVENANCE.json). Android и Linux используют общее ядро приложения и отдельные ревизии упаковки. Манифест содержит точные commits, деревья исходников и контрольные суммы пакетов.

На странице [0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) доступны пакеты приложения и архивы исходников. Для установки скачайте [APK для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) или [AppImage для Linux](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) и следуйте руководству для [Android](android.ru.md#ru-install) или [Linux](linux-appimage.ru.md#ru-download). Сторонние исходники поставляются отдельно в архиве зависимостей с реестром компонентов.

<a id="-выбор-подходящего-комплекта"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Архив зависимостей

| Файл | Назначение |
| --- | --- |
| [Исходники проекта для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-eafb093-android-project-sources.tar.gz) | Точные отслеживаемые исходники приложения, lock-файлы и упаковка поставленного APK. |
| [Исходники проекта для Linux](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-project-sources.tar.gz) | Точные отслеживаемые исходники приложения, lock-файлы и упаковка поставленной AppImage. |
| [`Tokenlogue-0.1.0-dependency-sources.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-dependency-sources.tar.gz) | Идентифицированные сторонние исходники, оригинальные уведомления, изменения и рецепты без повторных копий одинаковых файлов. |
| [`SOURCE_MATERIALS.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SOURCE_MATERIALS.json) | Версии, связи компонентов, относительные пути, размеры и SHA-256 материалов. Также описывает границы подтверждения исходников и происхождения бинарников. |
| [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) | Контрольные суммы загрузок выпуска. |

В архиве зависимостей нет дополнительной внешней папки. Он содержит двуязычный `README.md`, `SOURCE_MATERIALS.json`, `BUILD_INPUTS.json`, `RECONSTRUCTION.json`, `SHA256SUMS` и оригинальные файлы в `materials/<SHA-256>/<исходное имя>`. Одинаковый файл хранится один раз и может относиться к нескольким компонентам. Если исходники или уведомление находятся внутри сохранённого архива, реестр указывает точный внутренний путь.

В `BUILD_INPUTS.json` указаны источники, размеры и суммы отдельно получаемых компиляторов, runtime и инструментов. Среди них upstream-загрузки, выбранные пакеты официальных установочных образов Alpine и [входы сборки Linux runtime](https://github.com/Umichata/tokenlogue/releases/tag/runtime-build-inputs-20261110), упакованные Tokenlogue. Для получения этих файлов может потребоваться интернет.

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
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Происхождение компонентов

Связь исходников с бинарниками документирована не полностью для Android CFFI 2.0.0, PyCryptodomex 3.23.0 и msgpack 1.1.2, а также для Linux CFFI 2.0.0 и PyCryptodomex 3.23.0. Точная ревизия libffi и патчи внутри выбранных wheels CFFI остаются неопределёнными; libffi среды Python — отдельный компонент.

Реестр компонентов описывает доступные исходные материалы. Совпадение версии и суммы исходного архива определяет его содержимое, но не подтверждает независимое воспроизведение каждого нативного бинарника или наличие полного автономного окружения сборки.

<a id="-лицензии-и-прежние-комплекты"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Лицензии и уведомления

[Руководство по лицензиям пакета](../packaging/linux/appimage/notices.ru.md#russian) и раздел [о библиотеках и шрифтах](../packaging/notices/README.ru.md#russian) объясняют уведомления, поставляемые с приложением. Оригинальные лицензии и уведомления об авторских правах сохранены на языке источника. Исходники компонентов и сведения об их сборке перечислены отдельно.

<p align="left"><a href="../README.ru.md#russian"><img src="assets/ui/buttons/ru-b038324b5bbd.svg" alt="Tokenlogue" width="109" height="28"></a></p>
