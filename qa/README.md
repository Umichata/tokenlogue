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

The provider scenario checks account states and quotas in both interface languages using controlled responses. Run it on the same disposable emulator.

```bash
qa/android_dart_integration/run "$QA_DEVICE" providers
```

## PIN rotation across a process restart

Use a fresh API 30 or newer Android emulator with device credential support and no configured screen lock. The test sets a temporary screen PIN and installs a separate app with the ID `io.github.umichata.tokenlogue.dart.qa.vaultrotation`. It generates its own fixture values. At the end it removes its app and screen credential. The build uses the Android debug signing configuration and the locally cached dependencies.

```bash
mkdir -p out
qa/android_vault_rotation/build "$PWD/out/vault-qa.apk" 4288b33
python3 qa/android_vault_rotation/run.py "$QA_DEVICE" "$PWD/out/vault-qa.apk" "$PWD/out/vault-qa.json"
```

The fixture runs the revision’s `ProfileVault`, Android Keystore channel and encrypted chat store. After system confirmation and PIN replacement, the driver stops the process and waits for a new one. The new process checks which PIN matches the stored verifier and opens the original draft using the replacement PIN. The driver sends a checksummed fixture through hardware key events. Both processes verify the fixture, and the writer reads back the new verifier before it is stopped. The receipt records checks and process IDs. The sign-in screen of the distributed app has its own acceptance results.
