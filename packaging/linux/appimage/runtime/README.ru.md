<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="../../../../docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="../../../../docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../../../../README.ru.md" title="Главная"><img src="../../../../docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="../../../../docs/README.ru.md" title="Карта документации"><img src="../../../../docs/assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Компонент запуска AppImage

<a id="russian"></a>
<a id="lang-ru"></a>

Runtime монтирует или распаковывает файловую систему внутри AppImage и запускает приложение. Он уже включён в Tokenlogue для Linux. Устанавливать или запускать его отдельно не нужно.

<a id="-как-изучить-комплект-исходников"></a>
## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Как изучить комплект исходников

Текущий [отдельный рецепт](build_runtime.py) собирает этот компонент из точных исходников и пакетов, закреплённых в [runtime.lock.json](runtime.lock.json). Linux workflow собирает и проверяет его перед упаковкой Tokenlogue. Загрузка runtime из прежнего выпуска Tokenlogue или истекающего артефакта Actions не нужна. Полученный комплект содержит новый компонент запуска, его исходные материалы и результаты сборочных проверок.

<img src="../../../../docs/assets/ui/frame-top.svg" width="100%" alt="">

| Файл или каталог | Содержимое |
| --- | --- |
| `runtime-x86_64` | Компонент запуска |
| `runtime.lock.json` | Закреплённые версии и суммы исходников |
| `manifest.json` | Опись файлов и происхождение |
| `SHA256SUMS` | Суммы файлов комплекта |
| `materials/` | Исходники, рецепты, патчи, оригинальные пакеты и лицензии |
| `materials/linked-inputs/` | Сохранённые входы линковки |

<img src="../../../../docs/assets/ui/frame-bottom.svg" width="100%" alt="">

В корне распакованного комплекта проверьте файлы без выполнения runtime:
```bash
sha256sum --check SHA256SUMS
```

Суммы подтверждают целостность файлов, но не являются цифровой подписью.

Для сборки только текущего runtime из чистого снимка проекта нужны существующее окружение Python и Docker или Podman. Штатный helper проверяет подписи пакетов, выполняет две независимые компиляции без сети и сравнивает результаты перед проверкой запуска.

```bash
uv run --locked python packaging/linux/appimage/fetch_runtime.py \
  --run standalone-local \
  --report build/linux-release/reports/runtime-inputs.json
```

Имя попытки должно быть новым. Входы загружаются по закреплённым адресам и повторно проверяются при использовании кэша. [Карта получения входов](acquisition.lock.json) указывает точные байты пакетов, сохранённых в официальных установочных образах Alpine и небольшом отдельном архиве зависимостей. Архив содержит три пакета разработки Alpine вместе с оригинальными исходниками, рецептами и лицензиями. Старого приложения Tokenlogue или готового runtime в нём нет.

Архивы пакетов Alpine тоже имеют расширение `.apk`. Это входы сборки Linux, а не загрузки приложения для Android. Диапазоны образа принимаются только при точных HTTP-заголовках и совпадении суммы выбранного пакета. Чтение таких диапазонов не проверяет весь установочный образ. Полная сумма отдельного архива и каждый его член проверяются до использования. Проверки подписей пакетов, установленной описи и обе независимые компиляции остаются обязательными. Все выбранные пакеты устанавливаются из точных локальных APK с отключённой сетью. Изменяемые индексы репозиториев не участвуют в разрешении зависимостей и не являются обязательными входами сборки.

<a id="-компоненты-и-границы-комплекта"></a>
## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Компоненты и границы комплекта

Runtime Tokenlogue основан на [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Сохранены входы libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 и mimalloc2 2.1.7-r0. Комплект сохраняет оригинальные рецепты, патчи и тексты лицензий.

Материалы runtime не охватывают все зависимости приложения. Полная автономная пересборка Tokenlogue пока не подтверждена. Подробнее в <a href="../../../../docs/source-materials.ru.md#russian" title="руководстве по исходникам">руководстве по исходникам&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, <a href="../../../../docs/linux-appimage.ru.md#russian" title="установке для Linux">установке для Linux&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> и <a href="../notices.ru.md#russian" title="обзоре лицензий">обзоре лицензий&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
