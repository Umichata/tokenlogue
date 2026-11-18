[English](android.md#english) · [Русский](android.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Tokenlogue for Android

[Home](../README.md) · [Documentation](../docs/README.md)

> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** provides an Android ARM64 APK and a Linux x86_64 desktop bundle. Read the platform requirements and verify the downloaded file before installing.


## Requirements

- Android 7.0 / API 24 or later and ARM64 `arm64-v8a` support.
- An OpenRouter or VSEGPT account key and internet access for models and messages.
- A supported device screen lock for optional Android system recovery on Android 11 or later.

The minimum API does not mean that every Android version has been tested. Static ELF and ZIP checks cover 4 KiB and 16 KiB alignment. Runtime operation on a native ARM64 device with a 16 KiB kernel remains untested.

<a id="en-install"></a>
<a id="en-local-package"></a>
## Install Android 0.1.1

Download `Tokenlogue-0.1.1-android-arm64-v8a-v56.apk` from [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1). The APK is the installer. Source archives are not required to run the app.

| Item | Value |
| --- | --- |
| File | `Tokenlogue-0.1.1-android-arm64-v8a-v56.apk` |
| Version | 0.1.1, versionCode 56 |
| Architecture | ARM64, `arm64-v8a` |
| Size | 56,543,774 bytes |
| SHA-256 | `df69735b56c5f4d5da73859aa5f276f39c73d9d43526226175643beae316d6ec` |
| Certificate SHA-256 | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

Verify the selected file in your download directory.

```bash
printf '%s  %s\n' \
  'df69735b56c5f4d5da73859aa5f276f39c73d9d43526226175643beae316d6ec' \
  'Tokenlogue-0.1.1-android-arm64-v8a-v56.apk' | sha256sum --check -
```

Continue only after the named APK reports `OK`. Open the verified file on Android and confirm installation. Allow installation from your selected browser or file manager only if you trust the package. You can disable that permission afterwards. If Play Protect reports a harmful application, stop and [report the warning](https://github.com/Umichata/tokenlogue/issues).

<a id="en-published-preview"></a>
## Earlier preview

[0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) remains a separate earlier release. Its APK is not the current version. Follow the compatible-update guidance below.

## Update without deleting data

Install a compatible newer APK over the existing app. It must keep the application identity and signing certificate, and use a higher versionCode.

Do not uninstall or clear data as an update step. That can destroy the keys needed to read encrypted conversations. If Android rejects a signature or version, keep the old installation and check the package rather than deleting your data.

## Start using 0.1.1

Follow [first connection](user-guide.md#en-first-connection) to add one provider and create an app PIN. [Providers](providers.md) lets you add the other key later. A VSEGPT-only profile needs no OpenRouter key.

Bottom navigation opens **Home**, **Providers**, **Tokens** and **Spending**. Back returns an auxiliary page to Home. The separate chat button opens the conversation drawer. Tap outside it or use Back to close it. Dismiss the keyboard when you need more room for header shortcuts.

## Access and recovery

Backgrounding locks the app. Return with your app PIN to restore the saved draft. Unlocking Android does not unlock Tokenlogue automatically.

On supported Android 11 or later devices, **Forgot PIN?** requests fresh device authentication before you save a replacement app PIN. Cancelling keeps the old PIN. See [protection and recovery](security.md#en-recovery).

Android backup is disabled. The app does not request microphone access. A database copy alone does not include its separate protected key.
