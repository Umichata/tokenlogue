<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="https://github.com/Umichata/tokenlogue/blob/main/README.md" title="Home"><img src="docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android/README.md" title="Android"><img src="docs/assets/ui/buttons/en-46463edb13a7.svg" alt="Android" width="83" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/blob/linux/README.md" title="Linux"><img src="docs/assets/ui/buttons/en-885ac52495d2.svg" alt="Linux" width="65" height="28"></a>
</p>

<h1 align="center">
  <img src="docs/assets/tokenlogue-banner-en-v2.png" alt="Tokenlogue" width="100%">
</h1>

<p align="left"><a href="docs/README.md#en-preview-status"><img src="docs/assets/ui/buttons/en-dd8bbfdbdd63.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/linux-appimage.md#english"><img src="docs/assets/ui/buttons/en-455f22ec11f5.svg" alt="Guide" width="68" height="28"></a> <a href="docs/README.md"><img src="docs/assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a> <a href="#en-install"><img src="docs/assets/ui/buttons/en-c1a92da25825.svg" alt="Install" width="71" height="28"></a> <a href="#en-chat"><img src="docs/assets/ui/buttons/en-6147e3abd016.svg" alt="First chat" width="96" height="28"></a> <a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a></p>

<a id="english"></a>
<a id="lang-en"></a>

<a id="en-preview-status"></a>
> **Initial preview 0.1.0 — draft.** Application packages are not publicly available while the release is a draft. Publication requires the project owner's explicit instruction.

<h3 align="left">Chat with OpenRouter models from your Linux desktop. Tokenlogue provides a compact conversation workspace with saved drafts, model selection and a live cost estimate.</h3>

<a id="en-screenshots"></a>

<a id="-a-look-inside"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> A look inside

<a href="docs/assets/screenshots/linux-chat.png"><img src="docs/assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="docs/assets/screenshots/linux-chat.png" alt="Linux chat with local demonstration messages" width="760"><br>
<img src="docs/assets/ui/frame-bottom.svg" width="760" alt=""></a>

Linux chat with local demonstration messages.

<a id="en-install"></a>
<a id="-download-and-launch"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Download and launch

The package is an **unsigned x86_64 AppImage**. You need an x86-64-v2 CPU, compatible desktop libraries and graphics drivers. Ubuntu 22.04 is the system-library baseline. Normal startup uses FUSE, with an extract-and-run option when FUSE is unavailable.

The draft prepares [`Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) and [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS). These links are available to repository maintainers while the release is a draft. Illustrative chat workspace with demonstration data. The exact controls depend on the selected chat and available space.

The initial preview series uses the displayed application version `0.1.0` until a separately designated official release. Unique tags and increasing build numbers identify prepared packages.

Check only the selected AppImage against its entry in `SHA256SUMS` as explained in the Linux guide below, make it executable and run it as a normal user. For updates, close earlier copies before starting the replacement file. No separate Python, Flutter or Java installation or source archives are needed.

<p align="left"><a href="docs/linux-appimage.md#english"><img src="docs/assets/ui/buttons/en-a84c3e89f687.svg" alt="Linux requirements, checksum and launch instructions" width="428" height="28"></a></p>

<a id="en-chat"></a>
<a id="-start-a-conversation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Start a conversation

1. Add your OpenRouter key and let the application check it.
2. Set an application PIN.
3. Create a chat and choose a model.

Drafts stay with each chat. Rename and delete controls are available beneath the conversation title.

OpenRouter balance comes from the account API and appears in free and paid chats. Its refresh state shows whether the value is current. A failed refresh leaves it explicitly stale or unavailable, rather than replacing it with a local calculation. Choose `Refresh key and balance` in `⋮` for a manual update. The API key limit and the saved chat budget remain separate values.

Before a paid request could leave 10% or less of its chat spending limit according to the upper estimate, Tokenlogue asks whether to cancel, send this request once or change the chat limit. Cancel keeps the draft, and saving a new limit sends nothing. A one-off overrun does not raise the saved limit. Ordinary paid confirmations can be disabled from the first request in the selected chat, while the budget warning and other restrictions remain active. Cost and token estimates remain approximate.

<p align="left"><a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-389a1c880a5a.svg" alt="Chat and cost guide" width="172" height="28"></a></p>

<a id="-protect-the-local-profile"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Protect the local profile

A working Secret Service in your desktop session stores protected key material. Save the portable recovery code when offered and keep it separate from your computer. PIN and local field encryption do not encrypt the entire device. Without the required keys or recovery material, the application cannot promise to restore encrypted conversations.

Ready-to-use packages are separate downloads from sources. The project archive identified in `PROVENANCE.json` matches the delivered build, while `Tokenlogue-0.1.0-dependency-sources.tar.gz` collects identified third-party materials. The source guide explains its contents and the remaining gaps in linking some native binaries to their sources. An archive or license alone does not establish a wheel's build provenance.

<p align="left"><a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-3dff553cc7d1.svg" alt="Protection and recovery" width="202" height="28"></a> <a href="docs/source-materials.md#english"><img src="docs/assets/ui/buttons/en-d66f7717e2f0.svg" alt="Sources" width="84" height="28"></a> <a href="packaging/linux/appimage/notices.md#english"><img src="docs/assets/ui/buttons/en-70a36bdd774c.svg" alt="AppImage licenses" width="163" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></p>

<a id="en-docs"></a>

<a id="-find-your-document"></a>
<a id="find-your-document"></a>
<a id="-documentation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Documentation

<table>
<tr><th align="left">Category</th><th align="left">Documents</th></tr>
<tr>
<td><a id="start-here"></a><strong>Start here</strong></td>
<td><a href="docs/README.md#en-preview-status" title="Downloads"><img src="docs/assets/ui/buttons/en-0af7fc63fbbe.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/linux-appimage.md#en-download" title="Linux launch"><img src="docs/assets/ui/buttons/en-ce1db4f66563.svg" alt="Linux launch" width="118" height="28"></a> <a href="docs/android.md#en-install" title="Android install"><img src="docs/assets/ui/buttons/en-ec13da01a81e.svg" alt="Android install" width="133" height="28"></a></td>
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
