[English](android.md#english) · [Русский](android.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Tokenlogue for Android

[Home](../README.md) · [Documentation](../docs/README.md)

> **0.1.1 is local.** These instructions describe the current source and local builds. [Published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) is the earlier release. Its download links do not provide 0.1.1.


## Requirements

- Android 7.0 / API 24 or later and ARM64 `arm64-v8a` support.
- An OpenRouter or VSEGPT account key and internet access for models and messages.
- A supported device screen lock for optional Android system recovery on Android 11 or later.

The minimum API does not mean that every Android version has been tested. Static ELF and ZIP checks cover 4 KiB and 16 KiB alignment. Runtime operation on a native ARM64 device with a 16 KiB kernel remains untested.

<a id="en-install"></a>
<a id="en-local-package"></a>
## Local Android package 0.1.1

The current local package is supplied separately. This file is not available on the published 0.1.0 release page. If you already have the APK, verify it in your download directory.

| Item | Value |
| --- | --- |
| File | `Tokenlogue-0.1.1-android-arm64-v8a-v55.apk` |
| Version | 0.1.1, versionCode 55 |
| Architecture | ARM64, `arm64-v8a` |
| Size | 56,571,846 bytes |
| SHA-256 | `eba164999093157e1b8fc35a6296b515686a40876843ccf60ab9d3ac28a4aea0` |
| Certificate SHA-256 | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

```bash
printf '%s  %s\n' \
  'eba164999093157e1b8fc35a6296b515686a40876843ccf60ab9d3ac28a4aea0' \
  'Tokenlogue-0.1.1-android-arm64-v8a-v55.apk' | sha256sum --check -
```

Continue only after the named APK reports `OK`. Open the verified file on Android and confirm installation. A compatible update installs over the previous Tokenlogue with the same signature. Keep the app and its data. The [safe update instructions](#update-without-deleting-data) also apply to this package.

<a id="en-published-preview"></a>
## Install the published preview

The public download below is **0.1.0**, not local 0.1.1. APK is the installer. GitHub source archives are not Android applications.

| File | Value |
| --- | --- |
| [Android APK](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) | `Tokenlogue-0.1.0-android-arm64-v8a-v43.apk` |
| Version | 0.1.0, versionCode 43 |
| SHA-256 | `1e3ec65aaf1863eb50257aa4c090ca5fdf0b6b2c637c415d5b02056a2cf941f5` |
| Manifest | [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) |

Save the APK and manifest together. On a computer with Bash and SHA-256 tools, verify the selected file.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-android-arm64-v8a-v43.apk'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Continue only if the APK reports `OK`. Missing or duplicate manifest entries fail this check. A checksum confirms integrity and does not replace a signing certificate.

Open the verified APK on your device and follow the installer. Allow installation from your selected browser or file manager only if you trust the package. You can disable that permission afterwards. If Play Protect reports a harmful application, stop and [report the warning](https://github.com/Umichata/tokenlogue/issues).

## Update without deleting data

Install a compatible newer APK over the existing app. It must keep the application identity and signing certificate, and use a higher versionCode. Local 0.1.1 is a separate package from the published download.

Do not uninstall or clear data as an update step. That can destroy the keys needed to read encrypted conversations. If Android rejects a signature or version, keep the old installation and check the package rather than deleting your data.

## Start using 0.1.1

Follow [first connection](user-guide.md#en-first-connection) to add one provider and create an app PIN. [Providers](providers.md) lets you add the other key later. A VSEGPT-only profile needs no OpenRouter key.

Bottom navigation opens **Home**, **Providers**, **Tokens** and **Spending**. Back returns an auxiliary page to Home. The separate chat button opens the conversation drawer. Tap outside it or use Back to close it. Dismiss the keyboard when you need more room for header shortcuts.

## Access and recovery

Backgrounding locks the app. Return with your app PIN to restore the saved draft. Unlocking Android does not unlock Tokenlogue automatically.

On supported Android 11 or later devices, **Forgot PIN?** requests fresh device authentication before you save a replacement app PIN. Cancelling keeps the old PIN. See [protection and recovery](security.md#en-recovery).

Android backup is disabled. The app does not request microphone access. A database copy alone does not include its separate protected key.
