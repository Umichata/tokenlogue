<a id="russian"></a>
<a id="lang-ru"></a>

<p align="left">
<a href="THIRD_PARTY_NOTICES.ru.md#russian" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-ru-1a85308e1a5a.svg" alt="RU" width="46" height="30"></a> <a href="THIRD_PARTY_NOTICES.md#english" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-ru-724a8b1ba967.svg" alt="EN" width="45" height="30"></a>
<a href="README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/v3-ru-3a2f7e4ed2ac.svg" alt="Главная" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.ru.md" title="Android Python"><img src="docs/assets/ui/buttons//android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.ru.md" title="Android Dart"><img src="docs/assets/ui/buttons//android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.ru.md" title="Linux"><img src="docs/assets/ui/buttons/v3-ru-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="docs/assets/tokenlogue-masthead-ru-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Скачать"><img src="docs/assets/ui/buttons/v3-ru-2a07d387e1cd.svg" alt="Скачать" width="86" height="30"></a> <a href="docs/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/v3-ru-69a0ba104f26.svg" alt="Карта документации" width="184" height="30"></a> <a href="docs/user-guide.ru.md" title="Руководство"><img src="docs/assets/ui/buttons/v3-ru-071f2a99d224.svg" alt="Руководство" width="121" height="30"></a> <a href="docs/providers.ru.md" title="Провайдеры"><img src="docs/assets/ui/buttons/v3-ru-75c2bb600681.svg" alt="Провайдеры" width="121" height="30"></a> <a href="docs/analytics.ru.md" title="Статистика"><img src="docs/assets/ui/buttons/v3-ru-dd604a9fe99c.svg" alt="Статистика" width="109" height="30"></a></p>

<a id="сторонние-уведомления"></a>

# Сторонние уведомления

Код приложения Tokenlogue доступен по [лицензии MIT](LICENSE). Зависимости сохраняют собственные условия. Этот обзор не заменяет оригинальные уведомления.

## Android Dart 0.1.1+18

Уведомления Flutter и пакетов Dart находятся в APK по пути `assets/flutter_assets/NOTICES.Z`. Версии зависимостей указаны в [pubspec.lock](apps/android_dart/pubspec.lock). Ниже перечислены компоненты поставок Tokenlogue на Python.

<a id="компоненты"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Компоненты

| Компонент | Версия | Условия и назначение |
| --- | --- | --- |
| Flet и Flet Secure Storage | 0.86.5 | Apache 2.0, интерфейс и защищённое хранилище |
| HTTPX | 0.28.1 | BSD 3-Clause, HTTPS-запросы провайдеров |
| PyCryptodomex | 3.23.0 | BSD 2-Clause и уведомления public domain, примитивы шифрования |
| CFFI | 2.0.0 | MIT, нативный интерфейс |
| libffi в собственной сборке CFFI | 3.4.4 | MIT, статически связанные нативные вызовы |
| pycparser | 3.11 | BSD 3-Clause, объявления C |
| tzdata | 2026.6 | Apache 2.0 и уведомление IANA об общественном достоянии, часовые пояса |

Защищённое хранилище Python-версии для Android использует flutter_secure_storage 10.3.1. Системное восстановление использует local_auth 3.0.2, local_auth_android 2.2.0 и local_auth_platform_interface 1.1.0. Эти пакеты Flutter распространяются по BSD 3-Clause. Реализации других платформ в графе не означают поставку версии Tokenlogue для них.

<a id="уведомления-в-пакете"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Уведомления в пакете

В APK Python-версии входят уведомления Flutter и дополнение в `assets/third-party-notices/` внутри `assets/app.zip`. Сохранены оригинальные MIT-уведомления libffi среды Android и Dart bridge, полный OFL, авторские права KaTeX, декларация и авторство Material Icons и уведомления tzdata. См. [библиотеки и шрифты](packaging/notices/README.ru.md).

AppImage Linux содержит реестр и оригинальные лицензии в `usr/share/doc/tokenlogue/`. У настольного bundle собственные уведомления расположены рядом с приложением. Сверяйтесь с описью конкретного пакета, не предполагая одинаковые пути форматов. См. [руководство по уведомлениям AppImage](packaging/linux/appimage/notices.ru.md).

<a id="исходные-материалы"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходные материалы

[Исходные материалы](docs/source-materials.ru.md) описывают архивы, патчи и рецепты. [Руководство по нативным зависимостям Android](packaging/android/crypto/README.ru.md) объясняет их входы. Оригинальные тексты не переводятся и не редактируются. Наличие лицензии или архива подходящей версии само по себе не подтверждает производство определённого нативного бинарника.
