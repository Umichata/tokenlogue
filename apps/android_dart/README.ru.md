[English](README.md) · [Русский](README.ru.md)

# Tokenlogue Dart для Android

У Tokenlogue Dart собственные идентификатор Android, PIN, ключи провайдеров и история чатов. Его можно установить рядом с Tokenlogue на Python. Каждое приложение открывает свой профиль.

Для сборки нужны Flutter 3.44.8, Dart 3.12.2, JDK 17, Android SDK 36 и NDK 28.2.13676358. Укажите пути к инструментам в `FLUTTER_ROOT`, `JAVA_HOME` и `ANDROID_HOME`. В `TOKENLOGUE_DART_SIGNING_PROPERTIES` укажите путь к приватному файлу Java properties с полями `storeFile`, `storePassword`, `keyAlias` и `keyPassword`. Для обновлений сохраните тот же keystore.

Из этого каталога выполните `tool/build-release /абсолютный/путь/Tokenlogue-Dart.apk` с новым именем выходного файла. Для проверок используйте `flutter pub get --enforce-lockfile`, `flutter analyze` и `flutter test`.
