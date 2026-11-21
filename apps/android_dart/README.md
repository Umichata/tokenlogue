[English](README.md) · [Русский](README.ru.md)

# Tokenlogue Dart for Android

[Download Tokenlogue Dart 0.1.1+18 for Android ARM64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk) · [Verify and install the APK](../../docs/android-dart/README.md#apk)

Android can install the Dart package `io.github.umichata.tokenlogue.dart` alongside [Tokenlogue on Python](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) (`io.github.umichata.tokenlogue`). Their distinct package IDs give each app its own storage for its PIN, provider keys and chat history.

To build the Android app, use Flutter 3.44.8, Dart 3.12.2, JDK 17, Android SDK 36 and NDK 28.2.13676358. Set `FLUTTER_ROOT`, `JAVA_HOME` and `ANDROID_HOME` to those installations. Set `TOKENLOGUE_DART_SIGNING_PROPERTIES` to a private Java properties file with `storeFile`, `storePassword`, `keyAlias` and `keyPassword`. Use the same keystore for future updates.

From the repository root, enter the app directory. For your first local build, create an Android signing key using Android Studio or the JDK’s `keytool`. Use the absolute keystore path for `storeFile`. Keep the properties file and keystore outside the project.

```sh
cd apps/android_dart
```

From this directory, choose an output directory and build the ARM64 release APK. The wrapper pins Gradle 8.14. The Android project uses AGP 8.13.2 and Kotlin 2.2.20. Linux hosts also need `rsync`.

```bash
mkdir -p "$PWD/../../out/android-dart"
tool/build-release "$PWD/../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk"
sha256sum "$PWD/../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk"
```

Use a fresh output filename for each build. Compare the certificate fingerprint as well as the file checksum when distributing an update. A separately signed local build needs its own update sequence.

```bash
"$FLUTTER_ROOT/bin/flutter" pub get --enforce-lockfile
"$FLUTTER_ROOT/bin/dart" format --output=none --set-exit-if-changed lib test
"$FLUTTER_ROOT/bin/dart" analyze --fatal-infos
"$FLUTTER_ROOT/bin/flutter" test --no-pub
```

The release includes Flutter, Material icons, SQLite integration and Dart packages including cryptography and markdown. Their notices are in `assets/flutter_assets/NOTICES.Z` in the APK. Release checks use the Android SDK tools. With `buildTools` pointing to Android Build Tools 36.0.0 and `cert` set to the signing certificate's SHA-256, run the following command.

```bash
python3 tool/check_apk.py ../../out/android-dart/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk \
  --build-tools "$buildTools" --certificate "$cert" --build-number 18 --output apk-check.json
```

After verification, open the APK on Android and confirm installation. Choose **Tokenlogue Dart** in the app list. You can keep Tokenlogue on Python installed on the same device. Sign updates to your local Dart build with the same key.

Static ELF and ZIP checks cover 4 KiB and 16 KiB alignment. Native ARM64 operation with a 16 KiB kernel still needs a matching device. [Using the app](../../docs/android-dart/README.md) · [Project](../../README.md)
