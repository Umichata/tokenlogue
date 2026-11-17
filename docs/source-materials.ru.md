[English](source-materials.md#english) · [Русский](source-materials.ru.md#russian)

<a id="russian"></a>
<a id="lang-ru"></a>

# Исходники и зависимости

[Главная](../README.ru.md) · [Документация](../docs/README.ru.md)

> **0.1.1 доступна локально.** Руководство описывает текущие исходники и локальные сборки. [Опубликованный 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) — прежний выпуск. По его ссылкам нельзя скачать 0.1.1.


## Материалы для выбранного пакета

Ссылки ниже относятся к опубликованным пакетам 0.1.0. Текущие локальные APK55 и Linux bundle 0.1.1+55 используют общее ядро с двумя провайдерами и аналитикой. Их точные файлы и суммы указаны в руководствах [Android](android.ru.md#ru-local-package) и [Linux](linux-appimage.ru.md#ru-local-bundle). Это отдельные файлы, не загрузки прежнего выпуска.

Точные commit, дерево, lock-файлы и входы берите из provenance своего локального пакета. В опубликованный комплект 0.1.0 не входит архив проекта для этих сборок 0.1.1. Архивы 0.1.0 ниже не являются их точными исходниками. Изменение одной документации не меняет уже собранный бинарник.

Архив приложения, оригинальные сторонние исходники и доказательства производства бинарника имеют разные роли. Подходящая версия или сумма исходников не доказывают сборку определённого wheel из них. Наличие исходников отличается от полноты происхождения бинарника.

Код приложения Tokenlogue доступен по [лицензии MIT](../LICENSE). Сторонние компоненты сохраняют собственные условия. Готовые APK и AppImage скачиваются отдельно. Для запуска приложения исходники и средства сборки не нужны.

<a id="-исходники-приложения"></a>
## Исходники приложения

Выберите исходный архив каждого пакета по [`PROVENANCE.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/PROVENANCE.json). Опубликованные Android и Linux используют общее ядро приложения и отдельные ревизии упаковки. Манифест содержит точные commits, деревья исходников и контрольные суммы пакетов.

На странице [0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) доступны пакеты приложения и архивы исходников. Для установки скачайте [APK для Android](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) или [AppImage для Linux](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) и следуйте руководству для [Android](android.ru.md#ru-published-preview) или [Linux](linux-appimage.ru.md#ru-published-appimage). Сторонние исходники поставляются отдельно в архиве зависимостей с реестром компонентов.

<a id="-выбор-подходящего-комплекта"></a>
## Архив зависимостей

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
## Запуск текущих исходников в Linux

Установите Python 3.12 и [uv](https://docs.astral.sh/uv/). Откройте терминал в распакованном каталоге проекта с `pyproject.toml` и `uv.lock`. Также действуют [требования Linux к рабочему столу и хранилищу ключей](linux-appimage.ru.md#russian).

```bash
uv sync --locked
uv run --locked flet run
```

Эти команды запускают приложение из исходников и не создают APK или AppImage. Подготовка окружения и получение desktop-компонентов Flet могут потребовать интернет. Для упаковки используйте рецепты и точные lock-файлы подходящего архива проекта. [Руководство по упаковке Linux](../packaging/linux/appimage/README.ru.md#russian), [рецепт стартового runtime AppImage](../packaging/linux/appimage/runtime/README.ru.md#russian) и [руководство по нативным зависимостям Android](../packaging/android/crypto/README.ru.md#russian) описывают соответствующие компоненты.

<a id="-что-подтверждают-материалы"></a>
## Происхождение компонентов

Текущий рецепт упаковки выбирает [собственные сборки нативных wheels](../packaging/native_wheels/README.md#russian). Это CFFI 2.0.0, PyCryptodomex 3.23.0 и msgpack 1.1.2 для Android, а также CFFI 2.0.0 и PyCryptodomex 3.23.0 для Linux. Реестр связывает точные байты wheels с выполненным рецептом, исходными архивами, инструментами сборки и патчами. Обе сборки CFFI статически связываются с libffi 3.4.4. Два патча libffi для Android и исходники без патчей для Linux указаны отдельно. Libffi среды Python остаётся самостоятельным компонентом.

Прежние APK55 и Linux bundle +55 использовали другие wheels. Неполные связи с производителем и неопределённая libffi внутри CFFI остаются историческими ограничениями тех файлов. Сборка замен не устанавливает отсутствующие факты о старых бинарниках. Различайте входы по provenance своего точного пакета.

Реестр компонентов описывает повторно используемые исходные материалы и дополнения конкретного пакета. Совпадение версии и суммы определяет архив. Записанные сборки и проверки конечного пакета устанавливают выбранные файлы замены, но не заявляют независимое воспроизведение каждого бинарника или полный автономный дистрибутив SDK.

<a id="-лицензии-и-прежние-комплекты"></a>
## Лицензии и уведомления

[Руководство по лицензиям пакета](../packaging/linux/appimage/notices.ru.md#russian) и раздел [о библиотеках и шрифтах](../packaging/notices/README.ru.md#russian) объясняют уведомления, поставляемые с приложением. Оригинальные лицензии и уведомления об авторских правах сохранены на языке источника. Исходники компонентов и сведения об их сборке перечислены отдельно.
