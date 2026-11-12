<p align="left">
<a href="THIRD_PARTY_NOTICES.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="THIRD_PARTY_NOTICES.md" title="English"><img align="right" src="docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="README.ru.md" title="Главная"><img src="docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a> <a href="docs/README.ru.md" title="Карта документации"><img src="docs/assets/ui/buttons/ru-b4e89d854289.svg" alt="Карта документации" width="184" height="28"></a>
</p>

# Лицензии сторонних компонентов

<a id="russian"></a>
<a id="lang-ru"></a>

Собственный код Tokenlogue распространяется по <a href="LICENSE" title="лицензии MIT">лицензии MIT&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Зависимости сохраняют свои оригинальные лицензии. Их тексты не переводятся и не заменяются этим обзором.

<a id="-библиотеки-приложения"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Компоненты

<img src="docs/assets/ui/frame-top.svg" width="100%" alt="">

| Компонент | Версия | Лицензия | Назначение |
| --- | --- | --- | --- |
| Flet и Flet Secure Storage | 0.86.5 | Apache 2.0 | Интерфейс и платформенное защищённое хранилище |
| HTTPX | 0.28.1 | BSD 3-Clause | HTTPS-запросы OpenRouter |
| PyCryptodomex | 3.23.0 | BSD 2-Clause и уведомления public domain | Примитивы локального шифрования |
| CFFI | 2.0.0 | MIT | Нативный интерфейс |
| pycparser | 3.11 | BSD 3-Clause | Разбор объявлений C |

<img src="docs/assets/ui/frame-bottom.svg" width="100%" alt="">

Защищённое хранилище Android использует flutter_secure_storage 10.3.1. Для системного восстановления применяются local_auth 3.0.2, local_auth_android 2.2.0 и local_auth_platform_interface 1.1.0. Эти пакеты Flutter имеют лицензии BSD 3-Clause. Реализации других платформ в графе зависимостей не означают поставку версии для Windows или Apple.

<a id="-уведомления-внутри-пакета"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Уведомления в пакетах

Android содержит уведомления Flutter и дополнительный комплект внутри `assets/app.zip`, в каталоге `assets/third-party-notices/`. В нём сохранены оригинальные MIT-уведомления libffi среды Android и Dart bridge, полный OFL, авторские права KaTeX, декларация и авторство Material Icons. См. <a href="packaging/notices/README.ru.md#russian" title="тексты библиотек и шрифтов">тексты библиотек и шрифтов&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Linux содержит список компонентов, оригинальные лицензии и дополнение для шрифтов в `usr/share/doc/tokenlogue/`. <a href="packaging/linux/appimage/notices.ru.md#russian" title="Руководство по лицензиям AppImage">Руководство по лицензиям AppImage&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> объясняет их состав и отдельные материалы runtime. Определяйте фактические компоненты по списку, поставленному именно с вашим пакетом.

<a id="-исходники-и-происхождение"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Исходники компонентов

<a href="docs/source-materials.ru.md#russian" title="Руководство по исходным материалам">Руководство по исходным материалам&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> описывает доступные архивы, патчи и рецепты. <a href="packaging/android/crypto/README.ru.md#russian" title="Обзор нативных библиотек Android">Обзор нативных библиотек Android&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> объясняет нативные входы. Связь части исходников с бинарниками подтверждена не полностью, включая фактическую libffi внутри CFFI. Наличие лицензии или архива исходников с подходящей версией само по себе не доказывает происхождение конкретного бинарника.

<p align="left"><a href="README.ru.md#russian"><img src="docs/assets/ui/buttons/ru-6382944424ac.svg" alt="К Tokenlogue" width="124" height="28"></a></p>
