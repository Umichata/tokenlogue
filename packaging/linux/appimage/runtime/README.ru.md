<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="README.ru.md#russian" title="RU"><img align="right" src="../../../../docs/assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="README.md#english" title="EN"><img align="right" src="../../../../docs/assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="../../../../README.ru.md" title="Главная"><img src="../../../../docs/assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android"><img src="../../../../docs/assets/ui/buttons/v3-ru-4a0b64bd4ded.svg" alt="Android" width="83" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="../../../../docs/assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="../../../../docs/assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="../../../../docs/assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="../../../../docs/README.ru.md" title="Карта документации"><img src="../../../../docs/assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="../../../../docs/user-guide.ru.md" title="Руководство"><img src="../../../../docs/assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="../../../../docs/providers.ru.md" title="Провайдеры"><img src="../../../../docs/assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="../../../../docs/analytics.ru.md" title="Статистика"><img src="../../../../docs/assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="компонент-запуска-appimage"></a>

# Компонент запуска AppImage

Этот runtime монтирует или распаковывает файловую систему AppImage и запускает приложение. Он включён в пакеты Tokenlogue формата AppImage. Обычный настольный bundle 0.1.1 не использует этот компонент. Для запуска AppImage устанавливать runtime отдельно не нужно.

<a id="-как-изучить-комплект-исходников"></a>
<a id="-состав-комплекта"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Состав комплекта

[Рецепт сборки](build_runtime.py) использует upstream-исходники и пакеты, закреплённые в [runtime.lock.json](runtime.lock.json). Workflow упаковки AppImage собирает runtime перед созданием AppImage Tokenlogue. Комплект содержит компонент запуска, исходные материалы и сведения о сборке.

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

<a id="-сборка-компонента"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Сборка компонента

Для сборки runtime из чистого снимка проекта нужны окружение Python проекта и Docker или Podman. Helper получает закреплённые входы и выполняет сборку с отключённой сетью.

```bash
uv run --locked python packaging/linux/appimage/fetch_runtime.py \
  --run standalone-local \
  --report build/linux-release/reports/runtime-inputs.json
```

Используйте новое имя сборки. [Карта получения входов](acquisition.lock.json) указывает закреплённые пакеты официальных установочных образов Alpine и отдельного архива зависимостей. Архив содержит три пакета разработки Alpine с оригинальными исходниками, рецептами и лицензиями.

Пакеты Alpine тоже имеют расширение `.apk`. Это входы сборки Linux, которые нельзя установить как приложения Android. Перед использованием проверяются подписи и суммы пакетов. Сборка устанавливает точные локальные пакеты без изменяемых индексов репозиториев.

<a id="-компоненты-и-границы-комплекта"></a>
<a id="-зависимости"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Зависимости

Runtime Tokenlogue основан на [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Сохранены входы libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 и mimalloc2 2.1.7-r0. Комплект сохраняет оригинальные рецепты, патчи и тексты лицензий.

Этот комплект runtime содержит компонент запуска и не предоставляет полного автономного окружения сборки Tokenlogue. Подробнее в <a href="../../../../docs/source-materials.ru.md#russian" title="руководстве по исходникам">руководстве по исходникам&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, <a href="../../../../docs/linux-appimage.ru.md#russian" title="установке для Linux">установке для Linux&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> и <a href="../notices.ru.md#russian" title="обзоре лицензий">обзоре лицензий&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
