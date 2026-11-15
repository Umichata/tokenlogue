[English](README.md#english) · [Русский](README.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Tokenlogue

<p align="center"><img src="docs/assets/tokenlogue-logo-transparent.svg" alt="Tokenlogue logo" width="104"></p>

**OpenRouter and VSEGPT chats for Linux and Android.** Keep conversations and drafts together, choose a model for each chat and review tokens and spending.

[**Home**](https://github.com/Umichata/tokenlogue/tree/main) · [Android](https://github.com/Umichata/tokenlogue/tree/android) · [Linux](https://github.com/Umichata/tokenlogue/tree/linux)

[Features](#en-features) · [Interface](#en-screenshots) · [Install](#en-start) · [User guide](docs/user-guide.md) · [Documentation map](docs/README.md)

> **0.1.1 is local.** These instructions describe the current source and local builds. [Published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) is the earlier release. Its download links do not provide 0.1.1.


<a id="en-features"></a>
## What you can do

- Keep OpenRouter and VSEGPT keys separately in protected storage.
- Use **Home**, **Providers**, **Tokens** and **Spending** without losing the current chat or draft.
- View one service or both with **All · OpenRouter · VSEGPT**. The viewing filter does not change the provider of a chat.
- Track local token usage and daily costs by provider and model. USD and RUB remain separate.
- Review approximate costs and chat-budget warnings before sending a paid request.
- Use English or Russian, app PIN access and encryption of saved conversation fields.

<a id="en-screenshots"></a>
## Interface

| Linux | Android emulator |
| --- | --- |
| <a href="docs/assets/screenshots/v011-linux-home-en.png"><img src="docs/assets/screenshots/v011-linux-home-en.png" alt="Home with a conversation and saved draft on Linux" width="560"></a> | <a href="docs/assets/screenshots/v011-android-home-en.png"><img src="docs/assets/screenshots/v011-android-home-en.png" alt="Home with a conversation and saved draft in an Android emulator" width="300"></a> |

*Demonstration data. Android images show an emulator.*

<a id="en-start"></a>
## Install and update

| Platform | Current local version | Published package |
| --- | --- | --- |
| Android ARM64 | 0.1.1 APK, Android 7.0 / API 24 or later | [0.1.0 APK](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) · [Installation](docs/android.md) |
| Linux x86_64 | 0.1.1 desktop bundle | [0.1.0 AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) · [Installation](docs/linux-appimage.md) |

The [published release](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) provides [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS). Check the package before installing. AppImage is unsigned. You do not need Python, Flutter or source archives to run a packaged app.

Install a compatible Android update over the existing app with the same signature. Keep its data. On Linux, close old copies before starting a replacement under the same OS account.

### First connection

1. Enter a supported provider key and choose **Check key**. VSEGPT can be saved explicitly as unverified when a free check is unavailable.
2. Choose and repeat an app PIN. Save the recovery material offered for your platform.
3. Create a chat with **+**, choose its model and limits, then write a message.

See [chat instructions](docs/user-guide.md), [provider settings](docs/providers.md) and [token and spending statistics](docs/analytics.md).

## Know what the numbers mean

A service balance, the remaining OpenRouter key limit and a chat budget are different values. VSEGPT has no supported separate key-limit indicator. Unknown amounts stay unavailable. Local token and cost estimates are approximate.

PIN access and encryption protect selected local fields. They do not encrypt the entire device. Sending shares the necessary conversation content with the service assigned to that chat and its model provider. [Protection and recovery](docs/security.md) explains the requirements and the consequences of deleting a profile.

## Sources and licenses

Tokenlogue uses the [MIT license](LICENSE). [Source materials](docs/source-materials.md) and [third-party notices](THIRD_PARTY_NOTICES.md) describe the supplied components and the remaining limits of binary provenance. See [0.1.1 release notes](CHANGELOG.md).
