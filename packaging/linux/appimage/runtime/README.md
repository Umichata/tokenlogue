# The AppImage runtime / Компонент запуска AppImage

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

The runtime mounts or extracts the filesystem inside an AppImage and starts the application. It is already included in Tokenlogue for Linux. You do not need to install or launch it separately.

### Inspect the source bundle

The [published runtime ZIP](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) contains the startup binary and its source materials. This stable filename identifies the existing bundle. It is not an Android package or a newer Tokenlogue application release.

| File or directory | Contents |
| --- | --- |
| `runtime-x86_64` | Startup component |
| `runtime.lock.json` | Pinned versions and source checksums |
| `manifest.json` | File inventory and provenance |
| `SHA256SUMS` | Checksums within the bundle |
| `materials/` | Sources, recipes, patches, original packages and licenses |
| `materials/linked-inputs/` | Saved link inputs |

In the extracted bundle's root, check the supplied files without running the runtime:

```bash
sha256sum --check SHA256SUMS
```

Checksums establish file integrity, not a digital signature.

### Components and scope

This Tokenlogue runtime is based on [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Its saved inputs include libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 and mimalloc2 2.1.7-r0. The bundle preserves original recipes, patches and license texts.

Runtime materials do not cover every dependency of the full application. A complete offline rebuild of Tokenlogue is not established. See the [source guide](../../../../docs/source-materials.md#english), [Linux installation](../../../../docs/linux-appimage.md#english) and [license collection](../notices.md#english).

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Runtime монтирует или распаковывает файловую систему внутри AppImage и запускает приложение. Он уже включён в Tokenlogue для Linux. Устанавливать или запускать его отдельно не нужно.

### Как изучить комплект исходников

[Опубликованный ZIP runtime](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) содержит компонент запуска и его исходные материалы. Стабильное имя указывает на существующий комплект. Это не пакет Android и не новый выпуск приложения Tokenlogue.

| Файл или каталог | Содержимое |
| --- | --- |
| `runtime-x86_64` | Компонент запуска |
| `runtime.lock.json` | Закреплённые версии и суммы исходников |
| `manifest.json` | Опись файлов и происхождение |
| `SHA256SUMS` | Суммы файлов комплекта |
| `materials/` | Исходники, рецепты, патчи, оригинальные пакеты и лицензии |
| `materials/linked-inputs/` | Сохранённые входы линковки |

В корне распакованного комплекта проверьте файлы без выполнения runtime:

```bash
sha256sum --check SHA256SUMS
```

Суммы подтверждают целостность файлов, но не являются цифровой подписью.

### Компоненты и границы комплекта

Runtime Tokenlogue основан на [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Сохранены входы libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 и mimalloc2 2.1.7-r0. Комплект сохраняет оригинальные рецепты, патчи и тексты лицензий.

Материалы runtime не охватывают все зависимости приложения. Полная автономная пересборка Tokenlogue пока не подтверждена. Подробнее в [руководстве по исходникам](../../../../docs/source-materials.md#russian), [установке для Linux](../../../../docs/linux-appimage.md#russian) и [обзоре лицензий](../notices.md#russian).
