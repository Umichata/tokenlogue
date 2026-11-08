<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="../../../docs/assets/ui/buttons/ru-1e800a389462.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="../../../docs/assets/ui/buttons/ru-ccbd7ff610ca.svg" alt="English" width="45" height="28"></a>
<a href="../../../README.ru.md" title="Главная"><img src="../../../docs/assets/ui/buttons/ru-461b9280bad5.svg" alt="Главная" width="34" height="28"></a>&nbsp;<a href="../../../docs/README.ru.md" title="Документы"><img src="../../../docs/assets/ui/buttons/ru-2ceca5a8917e.svg" alt="Документы" width="111" height="28"></a>
</p>

# Исходные материалы зависимостей

<a id="russian"></a>
<a id="lang-ru"></a>

Этот комплект позволяет изучить зависимости криптографии и системной аутентификации Android. Здесь находятся оригинальные архивы, лицензии и отдельные upstream-рецепты сборки. Для использования Tokenlogue устанавливать эти материалы не нужно.

## 📦 Включённые материалы

<img src="../../../docs/assets/ui/frame-top.svg" width="100%" alt="">

| Компонент | Версия | Исходники и лицензия |
| --- | --- | --- |
| PyCryptodomex | `3.23.0` | [Архив](sources/pycryptodomex-3.23.0.tar.gz), [лицензия и правовые уведомления](licenses/pycryptodomex/LICENSE.rst) |
| CFFI | `2.0.0` | [Архив](sources/cffi-2.0.0.tar.gz), <a href="licenses/cffi/LICENSE" title="лицензия MIT">лицензия MIT&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| pycparser | `3.11` | [Архив](sources/pycparser-3.11.tar.gz), <a href="licenses/pycparser/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| Mobile Forge | `0fadbfab0d63d11164030dfddc955ed980e32e2c` | [Архив](sources/mobile-forge-0fadbfab0d63d11164030dfddc955ed980e32e2c.tar.gz), [рецепты и патчи](recipes/recipes), <a href="recipes/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth | `3.0.2` | [Архив](sources/local_auth-3.0.2.tar.gz), <a href="licenses/local_auth/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_android | `2.2.0` | [Архив](sources/local_auth_android-2.2.0.tar.gz), <a href="licenses/local_auth_android/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_platform_interface | `1.1.0` | [Архив](sources/local_auth_platform_interface-1.1.0.tar.gz), <a href="licenses/local_auth_platform_interface/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_darwin | `2.0.4` | [Архив](sources/local_auth_darwin-2.0.4.tar.gz), <a href="licenses/local_auth_darwin/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| flutter_secure_storage | `10.3.1` | [Архив](sources/flutter_secure_storage-10.3.1.tar.gz), <a href="licenses/flutter_secure_storage/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_windows | `2.0.2` | [Архив](sources/local_auth_windows-2.0.2.tar.gz), <a href="licenses/local_auth_windows/LICENSE" title="лицензия BSD 3-Clause">лицензия BSD 3-Clause&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |

<img src="../../../docs/assets/ui/frame-bottom.svg" width="100%" alt="">

Пакеты Darwin и Windows входят в разрешённый граф зависимостей Flutter. Их платформенные реализации не используются для восстановления Android. Их наличие не означает, что Tokenlogue доступен для этих платформ.

## ✅ Проверка комплекта

Файл [sources.lock.json](sources.lock.json) содержит исходные URL, суммы архивов и выбранные имена Android wheels. [SHA256SUMS](SHA256SUMS) покрывает файлы комплекта. Выполните следующую команду из этого каталога.
```bash
sha256sum --check SHA256SUMS
```

[Платформенный адаптер](../recovery_bridge.dart) и [настройка шаблона](../recovery_template.py) относятся к собственным исходникам Tokenlogue. Они подключают системное восстановление Android к приложению. Flutter Secure Storage предоставляет реализацию защищённого хранилища Android, используемую через Flet Secure Storage.

## 🔎 Что подтверждают эти материалы

Оригинальные архивы и их суммы идентифицируют доступные исходные материалы. Сами по себе они не доказывают способ сборки конкретного нативного wheel. Комплект не является полным автономным окружением Android и не обещает побайтного воспроизведения сборки.

Рецепт CFFI из Mobile Forge указывает host-зависимость libffi без версии. Точная libffi внутри выбранного wheel CFFI пока не определена. Отдельно описанная libffi из Python runtime Android не идентифицирует библиотеку внутри CFFI. Оригинальные уведомления CFFI сохранены.

Общий комплект и границы подтверждённого происхождения описаны в <a href="../../../docs/source-materials.ru.md#russian" title="руководстве по исходным материалам">руководстве по исходным материалам&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. <a href="../../../THIRD_PARTY_NOTICES.ru.md#russian" title="Сторонние уведомления">Сторонние уведомления&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> объясняют лицензионные материалы. Изменение этого документа не меняет уведомления внутри уже собранного APK или AppImage.
