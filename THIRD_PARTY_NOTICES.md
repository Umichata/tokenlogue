# Third-party software / Сторонние компоненты

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

Tokenlogue's own code uses the [MIT license](LICENSE). Its dependencies retain their respective original licenses. The original texts are not translated or replaced by this overview.

### Application libraries

| Component | Version | License | Purpose |
| --- | --- | --- | --- |
| Flet and Flet Secure Storage | 0.86.5 | Apache 2.0 | Interface and platform secure storage |
| HTTPX | 0.28.1 | BSD 3-Clause | OpenRouter HTTPS requests |
| PyCryptodomex | 3.23.0 | BSD 2-Clause and public-domain notices | Local encryption primitives |
| CFFI | 2.0.0 | MIT | Native interface |
| pycparser | 3.11 | BSD 3-Clause | C declaration parsing |

Android secure storage uses flutter_secure_storage 10.3.1. Device recovery uses local_auth 3.0.2, local_auth_android 2.2.0 and local_auth_platform_interface 1.1.0. These Flutter packages use BSD 3-Clause licenses. Other platform implementations in the dependency graph do not imply that a Windows or Apple version is distributed.

### Notices inside your package

Android includes Flutter's notices and a supplemental bundle inside `assets/app.zip`, under `assets/third-party-notices/`. It contains the original Android runtime libffi and Dart bridge MIT notices, complete OFL, KaTeX copyright and Material Icons declaration and attribution. See the [library and font texts](packaging/notices/README.md#english).

Linux includes its component index, original license collection and font supplement under `usr/share/doc/tokenlogue/`. The [AppImage license guide](packaging/linux/appimage/notices.md#english) explains these files and the separate runtime materials. Always use the index supplied with your particular package to identify its actual components.

### Sources and provenance

The [source guide](docs/source-materials.md#english) identifies the available archives, patches and recipes. The [Android native-library overview](packaging/android/crypto/README.md#english) explains native inputs. Some source-to-binary links remain incomplete, including the actual libffi inside CFFI. The presence of a license or a matching-version source archive alone does not prove how a particular binary was produced.

[Back to Tokenlogue](README.md#english)

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Собственный код Tokenlogue распространяется по [лицензии MIT](LICENSE). Зависимости сохраняют свои оригинальные лицензии. Их тексты не переводятся и не заменяются этим обзором.

### Библиотеки приложения

| Компонент | Версия | Лицензия | Назначение |
| --- | --- | --- | --- |
| Flet и Flet Secure Storage | 0.86.5 | Apache 2.0 | Интерфейс и платформенное защищённое хранилище |
| HTTPX | 0.28.1 | BSD 3-Clause | HTTPS-запросы OpenRouter |
| PyCryptodomex | 3.23.0 | BSD 2-Clause и уведомления public domain | Примитивы локального шифрования |
| CFFI | 2.0.0 | MIT | Нативный интерфейс |
| pycparser | 3.11 | BSD 3-Clause | Разбор объявлений C |

Защищённое хранилище Android использует flutter_secure_storage 10.3.1. Для системного восстановления применяются local_auth 3.0.2, local_auth_android 2.2.0 и local_auth_platform_interface 1.1.0. Эти пакеты Flutter имеют лицензии BSD 3-Clause. Реализации других платформ в графе зависимостей не означают поставку версии для Windows или Apple.

### Уведомления внутри пакета

Android содержит уведомления Flutter и дополнительный комплект внутри `assets/app.zip`, в каталоге `assets/third-party-notices/`. В нём сохранены оригинальные MIT-уведомления libffi среды Android и Dart bridge, полный OFL, авторские права KaTeX, декларация и авторство Material Icons. См. [тексты библиотек и шрифтов](packaging/notices/README.md#russian).

Linux содержит список компонентов, оригинальные лицензии и дополнение для шрифтов в `usr/share/doc/tokenlogue/`. [Руководство по лицензиям AppImage](packaging/linux/appimage/notices.md#russian) объясняет их состав и отдельные материалы runtime. Определяйте фактические компоненты по списку, поставленному именно с вашим пакетом.

### Исходники и происхождение

[Руководство по исходным материалам](docs/source-materials.md#russian) описывает доступные архивы, патчи и рецепты. [Обзор нативных библиотек Android](packaging/android/crypto/README.md#russian) объясняет нативные входы. Связь части исходников с бинарниками подтверждена не полностью, включая фактическую libffi внутри CFFI. Наличие лицензии или архива исходников с подходящей версией само по себе не доказывает происхождение конкретного бинарника.

[К Tokenlogue](README.md#russian)
