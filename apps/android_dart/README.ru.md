[English](README.md) · [Русский](README.ru.md)

# Tokenlogue Dart для Android

[Скачать Tokenlogue Dart 0.1.1+18 для Android ARM64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk) · [Проверка и установка APK](../../docs/android-dart/README.ru.md#apk)

Пакет Dart `io.github.umichata.tokenlogue.dart` можно установить рядом с [Tokenlogue на Python](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) (`io.github.umichata.tokenlogue`). Благодаря разным идентификаторам Android выделяет каждому приложению собственное хранилище для PIN, ключей провайдеров и истории чатов.

Для сборки нужны Flutter 3.44.8, Dart 3.12.2, JDK 17, Android SDK 36 и NDK 28.2.13676358. Укажите пути к инструментам в `FLUTTER_ROOT`, `JAVA_HOME` и `ANDROID_HOME`. В `TOKENLOGUE_DART_SIGNING_PROPERTIES` укажите путь к приватному файлу Java properties с полями `storeFile`, `storePassword`, `keyAlias` и `keyPassword`. Для обновлений сохраните тот же keystore.

Из корня репозитория перейдите в каталог приложения. Для собственной первой сборки создайте ключ подписи Android в Android Studio или с помощью JDK `keytool`. Укажите абсолютный путь к этому хранилищу в `storeFile`. Храните файл свойств и хранилище вне проекта.

```sh
cd apps/android_dart
```

Из этого каталога выберите выходную папку и соберите release APK для ARM64. Wrapper закрепляет Gradle 8.14. Проект Android использует AGP 8.13.2 и Kotlin 2.2.20. На Linux также нужен `rsync`.

```bash
mkdir -p "$PWD/../../out/android-dart"
tool/build-release "$PWD/../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk"
sha256sum "$PWD/../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk"
```

Для каждой сборки выбирайте новое выходное имя. При передаче обновления проверяйте отпечаток сертификата и контрольную сумму файла. Храните четыре параметра подписи и keystore вне дерева исходников. У локальных сборок с собственной подписью отдельная последовательность обновлений.

```bash
"$FLUTTER_ROOT/bin/flutter" pub get --enforce-lockfile
"$FLUTTER_ROOT/bin/dart" format --output=none --set-exit-if-changed lib test
"$FLUTTER_ROOT/bin/dart" analyze --fatal-infos
"$FLUTTER_ROOT/bin/flutter" test --no-pub
```

В release входят Flutter, значки Material, интеграция SQLite и пакеты Dart, включая cryptography и markdown. Уведомления находятся внутри APK в `assets/flutter_assets/NOTICES.Z`. Для проверки пакета нужны инструменты Android SDK. Укажите путь к Android Build Tools 36.0.0 в `buildTools`, а SHA-256 сертификата подписи в `cert`, затем выполните команду.

```bash
python3 tool/check_apk.py ../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk \
  --build-tools "$buildTools" --certificate "$cert" --build-number 18 --output apk-check.json
```

После проверки откройте APK на Android и подтвердите установку. В списке приложений выберите **Tokenlogue Dart**. Установленный Tokenlogue на Python можно оставить на устройстве. Для обновления своей Dart-сборки используйте прежний ключ подписи.

Статические проверки ELF и ZIP охватывают выравнивание для страниц 4 и 16 КиБ. Для проверки нативного запуска ARM64 с ядром 16 КиБ требуется соответствующее устройство. [Работа с приложением](../../docs/android-dart/README.ru.md) · [Проект](../../README.ru.md)
