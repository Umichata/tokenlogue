[English](README.md) · [Русский](README.ru.md)

# Android device tests

Use an Android emulator with a disposable profile. Set `FLUTTER_ROOT`, `ANDROID_HOME` and `JAVA_HOME` as described in the [build guide](../apps/android_dart/README.md). Set `QA_DEVICE` to that emulator's serial.

```bash
qa/android_dart_integration/run "$QA_DEVICE"
```

The runner stages the app in a temporary directory and runs the Flutter integration test in `io.github.umichata.tokenlogue.dart.qa`. Its initial key form accepts synthetic input. The test checks local service detection without a provider request.

To measure the installed release independently, build the external Android instrumentation package with the Android SDK, JDK 17, OpenSSL and zip. Install it on the same test emulator as the release APK.

```bash
mkdir -p out
qa/android_ui/build "$PWD/out/tokenlogue-ui-qa.apk"
adb -s "$QA_DEVICE" install out/tokenlogue-ui-qa.apk
adb -s "$QA_DEVICE" shell am instrument -w \
  -e package io.github.umichata.tokenlogue.dart -e measure size \
  io.github.umichata.tokenlogue.qa/.PublicWindowProbe
```

The system supplies the installed application size. For a foreground screen, the probe can also report the presence of known public controls. Normal system recovery requires device authentication in Android's own window. Enter personal credentials only in the app or system field intended for them.
