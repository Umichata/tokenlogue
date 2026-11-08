<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.md" title="Home"><img src="docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="https://github.com/Umichata/tokenlogue/blob/android/README.md" title="Android"><img src="docs/assets/ui/buttons/en-46463edb13a7.svg" alt="Android" width="83" height="28"></a>&nbsp;<a href="https://github.com/Umichata/tokenlogue/blob/linux/README.md" title="Linux"><img src="docs/assets/ui/buttons/en-885ac52495d2.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner.png" alt="Tokenlogue" width="100%">
</h1>

<a id="english"></a>
<a id="lang-en"></a>

Chat with OpenRouter models from your Linux desktop. Tokenlogue provides a compact conversation workspace with saved drafts, model selection and a live cost estimate.

**<a href="https://github.com/Umichata/tokenlogue/releases" title="Downloads"><img src="docs/assets/ui/buttons/en-a89567006163.svg" alt="Downloads" width="132" height="34"></a>** · **<a href="docs/linux-appimage.md#english" title="Linux guide"><img src="docs/assets/ui/buttons/en-527b5846b7e6.svg" alt="Linux guide" width="137" height="34"></a>** · **<a href="docs/README.md#english" title="All documents"><img src="docs/assets/ui/buttons/en-18cb00e4af42.svg" alt="All documents" width="156" height="34"></a>**

<a href="#en-install" title="Install"><img src="docs/assets/ui/buttons/en-005861163dc4.svg" alt="Install" width="97" height="34"></a> · <a href="#en-chat" title="First chat"><img src="docs/assets/ui/buttons/en-f58b07631535.svg" alt="First chat" width="122" height="34"></a> · <a href="docs/security.md#english" title="Protection"><img src="docs/assets/ui/buttons/en-c8aca5cd0ad1.svg" alt="Protection" width="128" height="34"></a>

<p align="center">
  <img src="docs/assets/ui/feature-panel-en.svg" alt="Chats and drafts · local estimates · conversation protection" width="100%">
</p>

<a id="en-screenshots"></a>

## 🖼️ A look inside

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="docs/assets/screenshots/linux-chat.png" alt="Linux chat with local demonstration messages" width="760"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="760" alt=""></a>

Linux chat with local demonstration messages.

<a id="en-install"></a>
## 🚀 Download and launch

The package is an **unsigned x86_64 AppImage**. You need an x86-64-v2 CPU, compatible desktop libraries and graphics drivers. Ubuntu 22.04 is the system-library baseline. Normal startup uses FUSE, with an extract-and-run option when FUSE is unavailable.

For this preview, choose `Tokenlogue-0.1.0-65aa62f-linux-x86_64.AppImage` and `RELEASE_SHA256SUMS` from <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases">Releases&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. If this preview is not listed, its downloads are not public yet. The [earlier published Linux preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3) remains a historical package with its own release notes. The screenshot above shows the current interface.

Check only the selected AppImage against its entry in `RELEASE_SHA256SUMS` as explained in the Linux guide below, make it executable and run it as a normal user. For updates, close earlier copies before starting the replacement file. No separate Python, Flutter or Java installation or source archives are needed.

<a href="docs/linux-appimage.md#english" title="Linux requirements, checksum and launch instructions"><img src="docs/assets/ui/buttons/en-75aa0a1d2360.svg" alt="Linux requirements, checksum and launch instructions" width="277" height="50"></a>

<a id="en-chat"></a>
## 💬 Start a conversation

<p align="center">
  <img src="docs/assets/ui/onboarding-en.svg" alt="Check your OpenRouter key, set a PIN and create a chat" width="100%">
</p>

Add your OpenRouter key, let the application check it and set a PIN. Create a chat and choose a model. Drafts stay with each chat. Rename and delete controls are available beneath the conversation title.

The local estimate is approximate. A per-chat budget, an OpenRouter key limit and the account balance are different values. Disabling paid-request confirmation applies from the first request in that chat, while limits remain active.

<a href="docs/user-guide.md#english" title="Chat and cost guide"><img src="docs/assets/ui/buttons/en-5a35014bcf7f.svg" alt="Chat and cost guide" width="198" height="34"></a>

## 🛡️ Protect the local profile

A working Secret Service in your desktop session stores protected key material. Save the portable recovery code when offered and keep it separate from your computer. PIN and local field encryption do not encrypt the entire device. Without the required keys or recovery material, the application cannot promise to restore encrypted conversations.

<a href="docs/security.md#english" title="Protection and recovery"><img src="docs/assets/ui/buttons/en-6172cd5c4df4.svg" alt="Protection and recovery" width="228" height="34"></a> · <a href="docs/source-materials.md#english" title="Sources"><img src="docs/assets/ui/buttons/en-2c8e53481ff1.svg" alt="Sources" width="110" height="34"></a> · <a href="packaging/linux/appimage/notices.md#english" title="AppImage licenses"><img src="docs/assets/ui/buttons/en-73ce0511f6fe.svg" alt="AppImage licenses" width="189" height="34"></a> · <a href="LICENSE" title="MIT license"><img src="docs/assets/ui/buttons/en-3e22b4aa274c.svg" alt="MIT license" width="134" height="34"></a>

<a id="en-docs"></a>

## 🧭 Find your document

- **Start here**
  - <a href="https://github.com/Umichata/tokenlogue/releases" title="Available downloads"><img src="docs/assets/ui/buttons/en-eca4d42b3b1a.svg" alt="Available downloads" width="202" height="34"></a>.
  - <a href="docs/linux-appimage.md#en-download" title="Run on Linux"><img src="docs/assets/ui/buttons/en-cf8a40db25e0.svg" alt="Run on Linux" width="147" height="34"></a>.
  - <a href="docs/android.md#en-install" title="Install on Android"><img src="docs/assets/ui/buttons/en-02eafac0c082.svg" alt="Install on Android" width="182" height="34"></a>.
- **Use and protect**
  - <a href="docs/user-guide.md#english" title="Chats, drafts and limits"><img src="docs/assets/ui/buttons/en-82d34d8a31dd.svg" alt="Chats, drafts and limits" width="224" height="34"></a>.
  - <a href="docs/security.md#english" title="PIN, encryption and recovery"><img src="docs/assets/ui/buttons/en-5e63fb088ae2.svg" alt="PIN, encryption and recovery" width="265" height="34"></a>.
  - <a href="https://github.com/Umichata/tokenlogue/issues" title="Help and issues"><img src="docs/assets/ui/buttons/en-08a227adfa99.svg" alt="Help and issues" width="167" height="34"></a>.
- **Sources and licenses**
  - <a href="docs/source-materials.md#english" title="Source materials"><img src="docs/assets/ui/buttons/en-6c08d5ca10c9.svg" alt="Source materials" width="176" height="34"></a>.
  - <a href="THIRD_PARTY_NOTICES.md#english" title="Third-party notices"><img src="docs/assets/ui/buttons/en-d83f57f8188d.svg" alt="Third-party notices" width="192" height="34"></a>.
  - <a href="LICENSE" title="MIT license"><img src="docs/assets/ui/buttons/en-3e22b4aa274c.svg" alt="MIT license" width="134" height="34"></a>.

<a href="docs/README.md#english" title="Full documentation map">Full documentation map&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> includes packaging documents and historical release records.
