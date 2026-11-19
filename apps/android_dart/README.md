[English](README.md) · [Русский](README.ru.md)

# Tokenlogue Dart for Android

Tokenlogue Dart has a separate Android identity, PIN, provider keys and chat history. Install it alongside Tokenlogue for Python. Each app opens its own profile.

To build the Android app, use Flutter 3.44.8, Dart 3.12.2, JDK 17, Android SDK 36 and NDK 28.2.13676358. Set `FLUTTER_ROOT`, `JAVA_HOME` and `ANDROID_HOME` to those installations. Set `TOKENLOGUE_DART_SIGNING_PROPERTIES` to a private Java properties file with `storeFile`, `storePassword`, `keyAlias` and `keyPassword`. Use the same keystore for future updates.

From this directory run `tool/build-release /absolute/output/path/Tokenlogue-Dart.apk` with a new output filename. For source checks use `flutter pub get --enforce-lockfile`, `flutter analyze` and `flutter test`.
