# Tokenlogue - Linux AppImage

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

The Tokenlogue AppImage is an unsigned preview for Linux x86_64.
This page covers `Tokenlogue-0.1.0-1472c00-x86_64.AppImage`.
The [Linux guide](../../../docs/linux-appimage.md#lang-en) explains how to
download it, check the file and launch the application.

### What you need

The CPU must support x86-64-v2. The AppImage includes Python, Flutter and
application plugins. System GTK3, GLib/GIO, graphics drivers and desktop services
come from your Linux distribution. Ubuntu 22.04 is the system library baseline.
The bundled libsecret client requires
a working Secret Service in your user session. Java and a separate Python
installation are not needed.

Ordinary startup uses FUSE. An extract-and-run option is available when FUSE
cannot be used. The AppImage does not update automatically or add an entry
to the applications menu. Run the file as your normal user.

### Before you start

The file is distributed through GitHub Actions with limited retention.
It has no signature or automatic updater. Check its checksum before running
it. The [Linux guide](../../../docs/linux-appimage.md#lang-en) describes
the requirements, download verification and startup options.

Compatibility depends on the system libraries and graphics environment.
Wayland support has not been verified.

### Included licenses and available sources

The [license guide](notices.md#lang-en) explains where to find the list of
included components and their original license texts. The [runtime overview](runtime/README.md#lang-en)
describes the startup component and its separate source bundle.
For available application sources and the gaps in their collection, see
[source materials](../../../docs/source-materials.md#lang-en).

[Back to Tokenlogue](../../../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

AppImage Tokenlogue - неподписанная предварительная сборка
для Linux x86_64. На этой странице описан файл
`Tokenlogue-0.1.0-1472c00-x86_64.AppImage`.
В [руководстве для Linux](../../../docs/linux-appimage.md#lang-ru) объясняется,
как скачать его, проверить и запустить приложение.

### Что потребуется

Процессор должен поддерживать x86-64-v2. AppImage содержит Python, Flutter
и плагины приложения. GTK3, GLib/GIO, видеодрайверы и службы рабочего стола
предоставляет ваш дистрибутив Linux. Базовая среда системных библиотек - Ubuntu 22.04.
Для встроенного клиента libsecret нужен
работающий Secret Service в пользовательской сессии. Java и отдельная
установка Python не требуются.

Обычный запуск использует FUSE. Если FUSE недоступен, можно запустить приложение
с распаковкой. AppImage не обновляется автоматически
и не добавляет ярлык в меню приложений. Запускайте файл от обычного пользователя.

### Перед запуском

Файл распространяется через GitHub Actions с ограниченным сроком хранения.
Подписи и автоматического обновления нет. Перед запуском проверьте контрольную
сумму. В [руководстве для Linux](../../../docs/linux-appimage.md#lang-ru)
описаны требования, проверка загрузки и способы запуска.

Совместимость зависит от системных библиотек и графической среды.
Поддержка Wayland не проверена.

### Включённые лицензии и доступные исходники

[Руководство по лицензиям](notices.md#lang-ru) поможет найти список
включённых компонентов и оригинальные тексты их лицензий.
[Обзор runtime](runtime/README.md#lang-ru) объясняет компонент запуска
и его отдельный комплект исходников. Доступные исходники приложения
и недостающие части комплекта описаны на странице
[исходных материалов](../../../docs/source-materials.md#lang-ru).

[К Tokenlogue](../../../README.md#lang-ru)
