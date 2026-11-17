[English](THIRD_PARTY_NOTICES.md#english) · [Русский](THIRD_PARTY_NOTICES.ru.md#russian)

<a id="russian"></a>
<a id="lang-ru"></a>

# Сторонние уведомления

Код приложения Tokenlogue доступен по [лицензии MIT](LICENSE). Зависимости сохраняют собственные условия. Этот обзор не заменяет оригинальные уведомления.

## Компоненты

| Компонент | Версия | Условия и назначение |
| --- | --- | --- |
| Flet и Flet Secure Storage | 0.86.5 | Apache 2.0, интерфейс и защищённое хранилище |
| HTTPX | 0.28.1 | BSD 3-Clause, HTTPS-запросы провайдеров |
| PyCryptodomex | 3.23.0 | BSD 2-Clause и уведомления public domain, примитивы шифрования |
| CFFI | 2.0.0 | MIT, нативный интерфейс |
| libffi в собственной сборке CFFI | 3.4.4 | MIT, статически связанные нативные вызовы |
| pycparser | 3.11 | BSD 3-Clause, объявления C |
| tzdata | 2026.6 | Apache 2.0 и уведомление IANA об общественном достоянии, часовые пояса |

Защищённое хранилище Android использует flutter_secure_storage 10.3.1. Системное восстановление использует local_auth 3.0.2, local_auth_android 2.2.0 и local_auth_platform_interface 1.1.0. Эти пакеты Flutter распространяются по BSD 3-Clause. Реализации других платформ в графе не означают поставку версии Tokenlogue для них.

## Уведомления в пакете

Android включает уведомления Flutter и дополнение в `assets/third-party-notices/` внутри `assets/app.zip`. Сохранены оригинальные MIT-уведомления libffi среды Android и Dart bridge, полный OFL, авторские права KaTeX, декларация и авторство Material Icons и уведомления tzdata. См. [библиотеки и шрифты](packaging/notices/README.ru.md).

AppImage Linux содержит реестр и оригинальные лицензии в `usr/share/doc/tokenlogue/`. У настольного bundle собственные уведомления расположены рядом с приложением. Сверяйтесь с описью конкретного пакета, не предполагая одинаковые пути форматов. См. [руководство по уведомлениям AppImage](packaging/linux/appimage/notices.ru.md).

## Исходные материалы

[Исходные материалы](docs/source-materials.ru.md) описывают архивы, патчи и рецепты. [Руководство по нативным зависимостям Android](packaging/android/crypto/README.ru.md) объясняет их входы. Оригинальные тексты не переводятся и не редактируются. Наличие лицензии или архива подходящей версии само по себе не подтверждает производство определённого нативного бинарника.
