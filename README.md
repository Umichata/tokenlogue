<a name="english"></a>
<a name="lang-en"></a>
<a name="tokenlogue"></a>

<h1 align="center"><img src="docs/assets/tokenlogue-dart-en.svg" alt="Tokenlogue Dart for Android · OpenRouter + VSEGPT" width="100%"></h1>

<p align="left">
<a href="README.ru.md" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="README.md" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="https://github.com/Umichata/tokenlogue/tree/main" title="Home"><img src="docs/assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="docs/assets/ui/buttons//android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="docs/assets/ui/buttons//android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="docs/assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
<a href="docs/android-dart/README.md" title="Documentation map"><img src="docs/assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="docs/android-dart/README.md#chat" title="User guide"><img src="docs/assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="#features" title="Features"><img src="docs/assets/ui/buttons/v3-en-32eedba1fb28.svg" alt="Features" width="89" height="30"></a></p>

**Tokenlogue Dart** is an Android client for OpenRouter and VSEGPT. Choose a service and model for each conversation. Return to an unfinished draft after reviewing tokens or spending.

To install Dart, [build the ARM64 APK](apps/android_dart/README.md). Android installs it alongside Tokenlogue on Python and keeps a separate profile for each app.

<a name="en-features"></a>
<a name="features"></a>
<a name="what-you-can-do"></a>

## Features

- Each provider has its own saved credential. OpenRouter offers free and paid model choices. VSEGPT opens its model catalogue directly.
- The app stores chats and drafts on your device. Sending a message shares the selected conversation context with its provider. An app PIN unlocks the local profile.
- Statistics use the request journal. OpenRouter USD and VSEGPT RUB are shown separately.

<a name="en-screenshots"></a>
<a name="interface"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Android interface

The chat, daily token chart and budget dialog were captured on Android Dart 0.1.1+13.

<img src="docs/assets/ui/frame-top.svg" alt="" width="100%">

| Chat and draft | Tokens by day | Chat budget |
| --- | --- | --- |
| <a href="docs/android-dart/images/v13/chat-en.png"><img src="docs/android-dart/images/v13/chat-en.png" alt="English controls with a Russian sample conversation" width="215"></a> | <a href="docs/android-dart/images/v13/tokens-filled-en.png"><img src="docs/android-dart/images/v13/tokens-filled-en.png" alt="Daily token chart for the sample conversation" width="215"></a> | <a href="docs/android-dart/images/v13/budget-en.png"><img src="docs/android-dart/images/v13/budget-en.png" alt="Budget warning before sending a paid request in RUB" width="215"></a> |

<img src="docs/assets/ui/frame-bottom.svg" alt="" width="100%">

[Browse the app screens](docs/android-dart/gallery.md)

<a name="en-start"></a>
<a name="install-and-update"></a>

## Install and connect

Build the ARM64 APK with the [Android build guide](apps/android_dart/README.md). Android 7.0 or later is required. The launcher entry is **Tokenlogue Dart**. It can be installed alongside the Python edition. Each edition has its own PIN, keys and history. There is no automatic transfer between the two.

<a name="first-connection"></a>

Open the new profile, enter the key for the service you want to use and choose **Check key**. Set and repeat a four-digit PIN. To update, install a Dart APK with a higher build number and the same signing certificate over your existing Dart app.

<a name="know-what-the-numbers-mean"></a>

The budget applies to one chat. The provider balance belongs to the account, and an OpenRouter key can have its own limit. Local token and cost estimates are approximate. Keep your PIN. On Android 7–10 it is the only way to unlock an existing Dart profile.

<a name="en-docs"></a>
<a name="documentation"></a>

## Guides

| Guide | Contents |
| --- | --- |
| [Using the app](docs/android-dart/README.md) | Providers, chats, limits, statistics and recovery |
| [Android build](apps/android_dart/README.md) | Toolchain, signing and local package verification |
| [Download Tokenlogue on Python 0.1.1, APK56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) | Android ARM64 installer for the Python edition and its profile. |

<a name="sources-and-licenses"></a>

[Tokenlogue license](LICENSE)
