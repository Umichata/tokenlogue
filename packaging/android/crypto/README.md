# Dependency source materials / Исходные материалы зависимостей

[English](#english) · [Русский](#russian)

<a id="english"></a>
<a id="lang-en"></a>

## English

This collection makes the cryptography and Android device-authentication dependencies available for inspection. It contains original archives, licenses and selected upstream build recipes. You do not need to install these materials to use Tokenlogue.

### Included materials

| Component | Version | Source and license |
| --- | --- | --- |
| PyCryptodomex | `3.23.0` | [Archive](sources/pycryptodomex-3.23.0.tar.gz), [license and legal notices](licenses/pycryptodomex/LICENSE.rst) |
| CFFI | `2.0.0` | [Archive](sources/cffi-2.0.0.tar.gz), [MIT license](licenses/cffi/LICENSE) |
| pycparser | `3.11` | [Archive](sources/pycparser-3.11.tar.gz), [BSD 3-Clause license](licenses/pycparser/LICENSE) |
| Mobile Forge | `0fadbfab0d63d11164030dfddc955ed980e32e2c` | [Archive](sources/mobile-forge-0fadbfab0d63d11164030dfddc955ed980e32e2c.tar.gz), [recipes and patches](recipes/recipes), [BSD 3-Clause license](recipes/LICENSE) |
| local_auth | `3.0.2` | [Archive](sources/local_auth-3.0.2.tar.gz), [BSD 3-Clause license](licenses/local_auth/LICENSE) |
| local_auth_android | `2.2.0` | [Archive](sources/local_auth_android-2.2.0.tar.gz), [BSD 3-Clause license](licenses/local_auth_android/LICENSE) |
| local_auth_platform_interface | `1.1.0` | [Archive](sources/local_auth_platform_interface-1.1.0.tar.gz), [BSD 3-Clause license](licenses/local_auth_platform_interface/LICENSE) |
| local_auth_darwin | `2.0.4` | [Archive](sources/local_auth_darwin-2.0.4.tar.gz), [BSD 3-Clause license](licenses/local_auth_darwin/LICENSE) |
| flutter_secure_storage | `10.3.1` | [Archive](sources/flutter_secure_storage-10.3.1.tar.gz), [BSD 3-Clause license](licenses/flutter_secure_storage/LICENSE) |
| local_auth_windows | `2.0.2` | [Archive](sources/local_auth_windows-2.0.2.tar.gz), [BSD 3-Clause license](licenses/local_auth_windows/LICENSE) |

The Darwin and Windows packages belong to the resolved Flutter dependency graph. Their platform implementations are not used for Android recovery. Their presence does not indicate an available Tokenlogue package for those platforms.

### Verify the collection

[sources.lock.json](sources.lock.json) records source URLs, archive hashes and the selected Android wheel filenames. [SHA256SUMS](SHA256SUMS) covers the files in this collection. From this directory, run the following command.

```bash
sha256sum --check SHA256SUMS
```

The [Tokenlogue device adapter](../recovery_bridge.dart) and [template configuration](../recovery_template.py) are Tokenlogue's own source. They connect Android system recovery to the application. Flutter Secure Storage supplies the Android secure-storage implementation used through Flet Secure Storage.

### What these materials establish

The original archives and their checksums identify the available source materials. They do not, by themselves, prove how a particular native wheel was built. The collection is not a complete offline Android build environment or a promise of byte-for-byte reproducibility.

The Mobile Forge CFFI recipe names a host libffi dependency without its version. The exact libffi incorporated in the selected CFFI wheel has not been identified. The separately documented libffi in the Android Python runtime does not identify the library inside CFFI. Original CFFI notices remain included.

See [source materials and remaining provenance limits](../../../docs/source-materials.md#english) for the wider collection. [Third-party notices](../../../THIRD_PARTY_NOTICES.md#english) explain the licensing materials. Documentation changes here do not change the notices inside an already built APK or AppImage.

<a id="russian"></a>
<a id="lang-ru"></a>

## Русский

Этот комплект позволяет изучить зависимости криптографии и системной аутентификации Android. Здесь находятся оригинальные архивы, лицензии и отдельные upstream-рецепты сборки. Для использования Tokenlogue устанавливать эти материалы не нужно.

### Включённые материалы

| Компонент | Версия | Исходники и лицензия |
| --- | --- | --- |
| PyCryptodomex | `3.23.0` | [Архив](sources/pycryptodomex-3.23.0.tar.gz), [лицензия и правовые уведомления](licenses/pycryptodomex/LICENSE.rst) |
| CFFI | `2.0.0` | [Архив](sources/cffi-2.0.0.tar.gz), [лицензия MIT](licenses/cffi/LICENSE) |
| pycparser | `3.11` | [Архив](sources/pycparser-3.11.tar.gz), [лицензия BSD 3-Clause](licenses/pycparser/LICENSE) |
| Mobile Forge | `0fadbfab0d63d11164030dfddc955ed980e32e2c` | [Архив](sources/mobile-forge-0fadbfab0d63d11164030dfddc955ed980e32e2c.tar.gz), [рецепты и патчи](recipes/recipes), [лицензия BSD 3-Clause](recipes/LICENSE) |
| local_auth | `3.0.2` | [Архив](sources/local_auth-3.0.2.tar.gz), [лицензия BSD 3-Clause](licenses/local_auth/LICENSE) |
| local_auth_android | `2.2.0` | [Архив](sources/local_auth_android-2.2.0.tar.gz), [лицензия BSD 3-Clause](licenses/local_auth_android/LICENSE) |
| local_auth_platform_interface | `1.1.0` | [Архив](sources/local_auth_platform_interface-1.1.0.tar.gz), [лицензия BSD 3-Clause](licenses/local_auth_platform_interface/LICENSE) |
| local_auth_darwin | `2.0.4` | [Архив](sources/local_auth_darwin-2.0.4.tar.gz), [лицензия BSD 3-Clause](licenses/local_auth_darwin/LICENSE) |
| flutter_secure_storage | `10.3.1` | [Архив](sources/flutter_secure_storage-10.3.1.tar.gz), [лицензия BSD 3-Clause](licenses/flutter_secure_storage/LICENSE) |
| local_auth_windows | `2.0.2` | [Архив](sources/local_auth_windows-2.0.2.tar.gz), [лицензия BSD 3-Clause](licenses/local_auth_windows/LICENSE) |

Пакеты Darwin и Windows входят в разрешённый граф зависимостей Flutter. Их платформенные реализации не используются для восстановления Android. Их наличие не означает, что Tokenlogue доступен для этих платформ.

### Проверка комплекта

Файл [sources.lock.json](sources.lock.json) содержит исходные URL, суммы архивов и выбранные имена Android wheels. [SHA256SUMS](SHA256SUMS) покрывает файлы комплекта. Выполните следующую команду из этого каталога.

```bash
sha256sum --check SHA256SUMS
```

[Платформенный адаптер](../recovery_bridge.dart) и [настройка шаблона](../recovery_template.py) относятся к собственным исходникам Tokenlogue. Они подключают системное восстановление Android к приложению. Flutter Secure Storage предоставляет реализацию защищённого хранилища Android, используемую через Flet Secure Storage.

### Что подтверждают эти материалы

Оригинальные архивы и их суммы идентифицируют доступные исходные материалы. Сами по себе они не доказывают способ сборки конкретного нативного wheel. Комплект не является полным автономным окружением Android и не обещает побайтного воспроизведения сборки.

Рецепт CFFI из Mobile Forge указывает host-зависимость libffi без версии. Точная libffi внутри выбранного wheel CFFI пока не определена. Отдельно описанная libffi из Python runtime Android не идентифицирует библиотеку внутри CFFI. Оригинальные уведомления CFFI сохранены.

Общий комплект и границы подтверждённого происхождения описаны в [руководстве по исходным материалам](../../../docs/source-materials.md#russian). [Сторонние уведомления](../../../THIRD_PARTY_NOTICES.md#russian) объясняют лицензионные материалы. Изменение этого документа не меняет уведомления внутри уже собранного APK или AppImage.
