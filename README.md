<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="docs/README.md" title="Documentation map"><img src="docs/assets/ui/buttons/en-63f7d280c22c.svg" alt="Documentation map" width="195" height="38"></a> <a href="https://github.com/Umichata/tokenlogue/blob/main/README.md" title="Home"><img src="docs/assets/ui/buttons/en-2d0a42236dec.svg" alt="Home" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.md" title="Android"><img src="docs/assets/ui/buttons/en-46463edb13a7.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.md" title="Linux"><img src="docs/assets/ui/buttons/en-96c04f670a21.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-en-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/en-dd8bbfdbdd63.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-4a1e7eca97e9.svg" alt="User guide" width="105" height="28"></a> <a href="#en-features"><img src="docs/assets/ui/buttons/en-f6b7b37e8509.svg" alt="Features" width="90" height="28"></a> <a href="#en-screenshots"><img src="docs/assets/ui/buttons/en-fcdfafa3f3ee.svg" alt="Screenshots" width="116" height="28"></a> <a href="#en-start"><img src="docs/assets/ui/buttons/en-ca3dbec2e101.svg" alt="Get started" width="109" height="28"></a></p>

<a id="english"></a>
<a id="lang-en"></a>

Chat with OpenRouter models on **Linux and Android**. Keep conversations and drafts together, choose a model for each chat and see an estimate before sending a paid request.

<a id="en-features"></a>
<a id="-your-chat-workspace"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Your chat workspace

- Separate chats, model selection and drafts that stay with the conversation.
- English and Russian interface with a compact layout for desktop and mobile.
- Free and paid models, per-chat budgets and a live estimate while you write.
- PIN access and local protection for supported conversation fields, with platform-specific recovery options.

<a id="en-screenshots"></a>
<a id="-a-look-inside"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> A look inside

<table>
<tr><th align="center">Linux</th><th align="center">Android</th></tr>
<tr>
<td align="center"><a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/ui/frame-top.svg" width="520" alt=""><br>
<img src="docs/assets/screenshots/linux-chat.png" alt="Linux chat with local demonstration messages" width="520"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="520" alt=""></a></td>
<td align="center"><a href="docs/assets/screenshots/android-chat-en.png"><img src="docs/assets/ui/frame-top.svg" width="260" alt=""><br>
<img src="docs/assets/screenshots/android-chat-en.png" alt="Tokenlogue chat on an Android tablet" width="260"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="260" alt=""></a></td>
</tr>
<tr><td>Linux chat with local demonstration messages</td><td>Tokenlogue chat on an Android tablet</td></tr>
</table>

Screenshots show the current interface with demonstration data. Earlier downloads retain their own release notes.

<a id="en-start"></a>
<a id="-get-started"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Get started

<img src="docs/assets/ui/frame-top.svg" width="100%" alt="">

| Platform | Package and requirements | Installation |
| --- | --- | --- |
| Linux | x86_64 AppImage, x86-64-v2 CPU, compatible desktop libraries | <a href="docs/linux-appimage.md#english" title="Linux guide">Linux guide&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> <a href="https://github.com/Umichata/tokenlogue/releases" title="Available downloads">Available downloads&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| Android | ARM64 APK, Android 7.0 / API 24 or later | <a href="docs/android.md#english" title="Android guide">Android guide&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> <a href="https://github.com/Umichata/tokenlogue/releases" title="Available downloads">Available downloads&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |

<img src="docs/assets/ui/frame-bottom.svg" width="100%" alt="">

Choose the package for your platform and download `RELEASE_SHA256SUMS` with it. The platform guide explains how to check only your selected package.

- Android — `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk`.
- Linux — `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage`.

<a href="https://github.com/Umichata/tokenlogue/releases" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> lists publicly available files. If this preview is not listed, its downloads are not public yet. The [earlier Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) remains a historical package with its own release notes.

You do not need a separate Python or Flutter installation or the source archives to run Tokenlogue. The Linux AppImage is unsigned.

For Linux updates, close earlier copies before launching the new file. For Android, install a compatible APK with the same signing certificate over the existing application. Removing the application or clearing its data is not an update step.

1. Add your own OpenRouter API key and let the application check it.
2. Set a PIN. Read the recovery options for your platform before you need them.
3. Create a chat, choose a model and write your first message.

See <a href="docs/user-guide.md#english" title="first connection and chat controls">first connection and chat controls&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> for the full walkthrough.

<a id="en-docs"></a>

<a id="-find-your-document"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Find your document

<a id="start-here"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Start here

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases"><img src="docs/assets/ui/buttons/en-dd8bbfdbdd63.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/android.md#en-install"><img src="docs/assets/ui/buttons/en-ec13da01a81e.svg" alt="Android install" width="133" height="28"></a> <a href="docs/linux-appimage.md#en-download"><img src="docs/assets/ui/buttons/en-ce1db4f66563.svg" alt="Linux launch" width="118" height="28"></a></p>

<a id="use-and-protect"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Use and protect

<p align="left"><a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-4a1e7eca97e9.svg" alt="User guide" width="105" height="28"></a> <a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues"><img src="docs/assets/ui/buttons/en-b35e6ff4675a.svg" alt="Help and issues" width="141" height="28"></a></p>

<a id="sources-and-licenses"></a>
### <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Sources and licenses

<p align="left"><a href="docs/source-materials.md#english"><img src="docs/assets/ui/buttons/en-b63fdbc05df7.svg" alt="Source materials" width="150" height="28"></a> <a href="THIRD_PARTY_NOTICES.md#english"><img src="docs/assets/ui/buttons/en-0ea52d246a12.svg" alt="Third-party notices" width="166" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></p>

The full documentation map also includes packaging documents and historical release records.

<a id="-costs-and-local-protection"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Costs and local protection

A chat budget, an OpenRouter key limit and your account balance are different amounts. The local token and price estimate is approximate. It is not the model's exact tokenizer or a promise of the final charge. Disabling paid-request confirmation applies from the first request in that chat, while the limits remain in effect.

PIN and encryption protect access and selected local fields. They do not encrypt your whole device. Recovery depends on the saved keys and the configured platform method. When you send a message, the selected conversation content goes to OpenRouter and the chosen model provider. Tokenlogue is independent of OpenRouter.

<p align="left"><a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-c6cc0af96e1c.svg" alt="Using chats and estimates" width="220" height="28"></a> <a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-5098cef88c2b.svg" alt="Protecting your conversations" width="247" height="28"></a></p>

<a id="-sources-and-licenses"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Sources and licenses

Tokenlogue's code uses the <a href="LICENSE" title="MIT license">MIT license&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. <a href="docs/source-materials.md#english" title="Source materials">Source materials&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explain the available archives and the remaining gaps in linking some native binaries to their sources. <a href="THIRD_PARTY_NOTICES.md#english" title="Third-party notices">Third-party notices&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> preserve the original terms for libraries and fonts.
