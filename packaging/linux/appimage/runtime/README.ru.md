<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="../../../../docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="../../../../docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../../../../README.ru.md" title="Главная"><img src="../../../../docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a>&nbsp;<a href="../../../../docs/README.ru.md" title="Документы"><img src="../../../../docs/assets/ui/buttons/ru-2ceca5a8917e.svg" alt="Документы" width="111" height="28"></a>
</p>

# Компонент запуска AppImage

<a id="russian"></a>
<a id="lang-ru"></a>

Runtime монтирует или распаковывает файловую систему внутри AppImage и запускает приложение. Он уже включён в Tokenlogue для Linux. Устанавливать или запускать его отдельно не нужно.

## 📦 Как изучить комплект исходников

[Опубликованный ZIP runtime](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) содержит компонент запуска и его исходные материалы. Стабильное имя указывает на существующий комплект. Это не пакет Android и не новый выпуск приложения Tokenlogue.

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

## 🔎 Компоненты и границы комплекта

Runtime Tokenlogue основан на [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Сохранены входы libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 и mimalloc2 2.1.7-r0. Комплект сохраняет оригинальные рецепты, патчи и тексты лицензий.

Материалы runtime не охватывают все зависимости приложения. Полная автономная пересборка Tokenlogue пока не подтверждена. Подробнее в <a href="../../../../docs/source-materials.ru.md#russian" title="руководстве по исходникам">руководстве по исходникам&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, <a href="../../../../docs/linux-appimage.ru.md#russian" title="установке для Linux">установке для Linux&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> и <a href="../notices.ru.md#russian" title="обзоре лицензий">обзоре лицензий&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
