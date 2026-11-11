<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.md" title="Home"><img src="docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.md" title="Android"><img src="docs/assets/ui/buttons/en-467730e73fe1.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.md" title="Linux"><img src="docs/assets/ui/buttons/en-96c04f670a21.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-en-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9"><img src="docs/assets/ui/buttons/en-dd8bbfdbdd63.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/android.md#english"><img src="docs/assets/ui/buttons/en-455f22ec11f5.svg" alt="Guide" width="68" height="28"></a> <a href="docs/README.md"><img src="docs/assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a> <a href="#en-install"><img src="docs/assets/ui/buttons/en-c1a92da25825.svg" alt="Install" width="71" height="28"></a> <a href="#en-chat"><img src="docs/assets/ui/buttons/en-6147e3abd016.svg" alt="First chat" width="96" height="28"></a> <a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a></p>

<a id="english"></a>
<a id="lang-en"></a>

<h3 align="left">Use OpenRouter models from your Android phone or tablet. Tokenlogue keeps your chats, drafts and model choices in one mobile workspace.</h3>

<a id="en-screenshots"></a>

<a id="-a-look-inside"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> A look inside

<table>
<tr><th>🔑 First connection</th><th>💬 Your conversation</th></tr>
<tr>
<td align="center"><a href="docs/assets/screenshots/android-start.png"><img src="docs/assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="docs/assets/screenshots/android-start.png" alt="Connect your OpenRouter key on Android" width="320"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="320" alt=""></a></td>
<td align="center"><a href="docs/assets/screenshots/android-chat-en.png"><img src="docs/assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="docs/assets/screenshots/android-chat-en.png" alt="Tokenlogue chat on an Android tablet" width="320"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="320" alt=""></a></td>
</tr>
</table>

Illustrations from an earlier Tokenlogue preview on an Android tablet. Available controls in newer builds can differ.

New previews keep the displayed application version `0.1.0` until a separately designated official release. Unique tags and increasing build numbers distinguish individual previews.

<a id="en-install"></a>
<a id="-install-or-update"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Install or update

You need **ARM64 Android 7.0 / API 24 or later**. This minimum does not mean every Android version has been tested. Static 16 KiB checks passed, while operation on a native ARM64 device with a 16 KiB kernel has not yet been checked.

For Tokenlogue 0.1.0, download [`Tokenlogue-0.1.0-android-arm64-v8a-v43.apk`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-android-arm64-v8a-v43.apk) and [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) from <a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Check only the APK against its manifest entry as explained in the Android guide below. You do not need a separate Python or Flutter installation or the source archives to run Tokenlogue.

Allow installation from your chosen file manager or browser, open the verified APK and follow Android's prompts. For an update, install over a compatible previous version with the same signing certificate. Do not uninstall or clear application data as a routine update step.

<p align="left"><a href="docs/android.md#english"><img src="docs/assets/ui/buttons/en-375893c76b90.svg" alt="Full Android installation guide" width="247" height="28"></a></p>

<a id="en-chat"></a>
<a id="-start-a-conversation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Start a conversation

1. Add your own OpenRouter key and complete its online check.
2. Set an application PIN.
3. Create a chat and select a model.

The draft and model choice remain with that conversation. Open the chat actions to rename or delete it.

OpenRouter balance comes from the account API and appears in free and paid chats. Its refresh state shows whether the value is current. A failed refresh leaves it explicitly stale or unavailable, rather than replacing it with a local calculation. Choose `Refresh key and balance` in `⋮` for a manual update. The API key limit and the saved chat budget remain separate values.

Before a paid request could leave 10% or less of its chat spending limit according to the upper estimate, Tokenlogue asks whether to cancel, send this request once or change the chat limit. Cancel keeps the draft, and saving a new limit sends nothing. A one-off overrun does not raise the saved limit. Ordinary paid confirmations can be disabled from the first request in the selected chat, while the budget warning and other restrictions remain active. Cost and token estimates remain approximate.

<p align="left"><a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-8f1e54380ecd.svg" alt="Chat guide" width="105" height="28"></a> <a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-a8359f9bf2b5.svg" alt="PIN, encryption and Android recovery" width="302" height="28"></a></p>

<a id="-know-what-is-protected"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Know what is protected

Selected local conversation fields are encrypted, not the whole device. System recovery needs a supported and configured Android screen lock and access to the original protected encryption key. Deleting the local profile is irreversible and does not refund or delete your OpenRouter account.

Ready-to-use packages are separate downloads from sources. The project archive identified in `PROVENANCE.json` matches the delivered build, while `Tokenlogue-0.1.0-dependency-sources.tar.gz` collects identified third-party materials without a chain of older releases. The source guide explains its contents and the remaining gaps in linking some native binaries to their sources. An archive or license alone does not establish a wheel's build provenance.

<p align="left"><a href="docs/source-materials.md#english"><img src="docs/assets/ui/buttons/en-81e7eddd2b57.svg" alt="Sources and provenance limits" width="251" height="28"></a> <a href="THIRD_PARTY_NOTICES.md#english"><img src="docs/assets/ui/buttons/en-2ac361b561de.svg" alt="Third-party licenses" width="172" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></p>

<a id="en-docs"></a>

<a id="-find-your-document"></a>
<a id="find-your-document"></a>
<a id="-documentation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Documentation

<table>
<tr><th align="left">Category</th><th align="left">Documents</th></tr>
<tr>
<td><a id="start-here"></a><strong>Start here</strong></td>
<td><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Downloads"><img src="docs/assets/ui/buttons/en-0af7fc63fbbe.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/android.md#en-install" title="Android install"><img src="docs/assets/ui/buttons/en-ec13da01a81e.svg" alt="Android install" width="133" height="28"></a> <a href="docs/linux-appimage.md#en-download" title="Linux launch"><img src="docs/assets/ui/buttons/en-ce1db4f66563.svg" alt="Linux launch" width="118" height="28"></a></td>
</tr>
<tr>
<td><a id="use-and-protect"></a><strong>Use and protect</strong></td>
<td><a href="docs/user-guide.md#english" title="User guide"><img src="docs/assets/ui/buttons/en-4a1e7eca97e9.svg" alt="User guide" width="105" height="28"></a> <a href="docs/security.md#english" title="Protection"><img src="docs/assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues" title="Help and issues"><img src="docs/assets/ui/buttons/en-b35e6ff4675a.svg" alt="Help and issues" width="141" height="28"></a></td>
</tr>
<tr>
<td><a id="sources-and-licenses"></a><strong>Sources and licenses</strong></td>
<td><a href="docs/source-materials.md#english" title="Source materials"><img src="docs/assets/ui/buttons/en-b63fdbc05df7.svg" alt="Source materials" width="150" height="28"></a> <a href="THIRD_PARTY_NOTICES.md#english" title="Third-party notices"><img src="docs/assets/ui/buttons/en-0ea52d246a12.svg" alt="Third-party notices" width="166" height="28"></a> <a href="LICENSE" title="MIT license"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></td>
</tr>
</table>

The full documentation map also includes packaging documents and the current source-materials guide.
