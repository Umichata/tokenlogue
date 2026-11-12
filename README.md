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
> **0.1.0 Preview** · Packages are being prepared for publication. Downloads will appear in [Releases](https://github.com/Umichata/tokenlogue/releases).

<h3 align="left">Chat with OpenRouter models from your Linux desktop. Tokenlogue provides a compact conversation workspace with saved drafts, model selection and a live cost estimate.</h3>

<a id="en-screenshots"></a>

<a id="-a-look-inside"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Workspace

| Area | Features |
| --- | --- |
| Conversations | Separate chats, model selection and saved drafts. |
| Spending | OpenRouter balance, chat budgets and token and cost estimates. |
| Access | Application PIN, protected local fields and portable recovery. |

<a id="en-install"></a>
<a id="-download-and-launch"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Installation

Tokenlogue for Linux is distributed as an **unsigned x86_64 AppImage**. It requires an x86-64-v2 CPU, compatible desktop libraries and graphics drivers. Ubuntu 22.04 is the system-library baseline. FUSE is used for normal startup; extract-and-run is available as an alternative.

Package availability is listed in the <a href="docs/README.md#en-preview-status">download section&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Verify the AppImage with `SHA256SUMS`, allow execution and launch it as a normal user. Close running copies before replacing the file. Python, Flutter, Java and the source archives are not required to run the app.

<p align="left"><a href="docs/linux-appimage.md#english"><img src="docs/assets/ui/buttons/en-a84c3e89f687.svg" alt="Linux requirements, checksum and launch instructions" width="428" height="28"></a></p>

<a id="en-chat"></a>
<a id="-start-a-conversation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> First launch

1. Add an OpenRouter API key and complete its online check.
2. Set an application PIN and save the recovery information offered for the platform.
3. Create a chat, choose a model and write a message.

Each conversation keeps its draft and model selection. OpenRouter account balance refreshes after a sent request finishes and can also be refreshed from the key-status menu. The balance, API-key limit and chat budget remain separate values; a failed refresh is shown as stale or unavailable.

Before a paid request could leave 10% or less of the chat limit, a warning offers cancellation, one-time sending or a limit change. Cancellation keeps the draft. Saving a limit sends nothing, and one-time permission does not raise the saved limit. The warning remains active when ordinary paid confirmations are disabled. Token and cost estimates are approximate.

<p align="left"><a href="docs/user-guide.md#english"><img src="docs/assets/ui/buttons/en-389a1c880a5a.svg" alt="Chat and cost guide" width="172" height="28"></a></p>

<a id="-protect-the-local-profile"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Privacy and recovery

A working Secret Service in the desktop session stores protected key material. Save the portable recovery code when offered and keep it separate from the computer. PIN access and field encryption do not encrypt the entire device. Recovering encrypted conversations requires the relevant keys or recovery material.

Sending a message shares the selected conversation content with OpenRouter and the model provider. Source code, dependency materials and licenses are documented separately.

<p align="left"><a href="docs/security.md#english"><img src="docs/assets/ui/buttons/en-3dff553cc7d1.svg" alt="Protection and recovery" width="202" height="28"></a> <a href="docs/source-materials.md#english"><img src="docs/assets/ui/buttons/en-d66f7717e2f0.svg" alt="Sources" width="84" height="28"></a> <a href="packaging/linux/appimage/notices.md#english"><img src="docs/assets/ui/buttons/en-70a36bdd774c.svg" alt="AppImage licenses" width="163" height="28"></a> <a href="LICENSE"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></p>

<a id="en-docs"></a>

<a id="-find-your-document"></a>
<a id="find-your-document"></a>
<a id="-documentation"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Documentation

<table>
<tr><th align="left">Category</th><th align="left">Documents</th></tr>
<tr>
<td><a id="start-here"></a><strong>Installation</strong></td>
<td><a href="docs/README.md#en-preview-status" title="Downloads"><img src="docs/assets/ui/buttons/en-0af7fc63fbbe.svg" alt="Downloads" width="106" height="28"></a> <a href="docs/linux-appimage.md#en-download" title="Linux launch"><img src="docs/assets/ui/buttons/en-ce1db4f66563.svg" alt="Linux launch" width="118" height="28"></a> <a href="docs/android.md#en-install" title="Android install"><img src="docs/assets/ui/buttons/en-ec13da01a81e.svg" alt="Android install" width="133" height="28"></a></td>
</tr>
<tr>
<td><a id="use-and-protect"></a><strong>Chats and security</strong></td>
<td><a href="docs/user-guide.md#english" title="User guide"><img src="docs/assets/ui/buttons/en-4a1e7eca97e9.svg" alt="User guide" width="105" height="28"></a> <a href="docs/security.md#english" title="Protection"><img src="docs/assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a> <a href="https://github.com/Umichata/tokenlogue/issues" title="Help and issues"><img src="docs/assets/ui/buttons/en-b35e6ff4675a.svg" alt="Help and issues" width="141" height="28"></a></td>
</tr>
<tr>
<td><a id="sources-and-licenses"></a><strong>Sources and licenses</strong></td>
<td><a href="docs/source-materials.md#english" title="Source materials"><img src="docs/assets/ui/buttons/en-b63fdbc05df7.svg" alt="Source materials" width="150" height="28"></a> <a href="THIRD_PARTY_NOTICES.md#english" title="Third-party notices"><img src="docs/assets/ui/buttons/en-0ea52d246a12.svg" alt="Third-party notices" width="166" height="28"></a> <a href="LICENSE" title="MIT license"><img src="docs/assets/ui/buttons/en-35273ad53d41.svg" alt="MIT license" width="108" height="28"></a></td>
</tr>
</table>
