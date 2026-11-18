<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="providers.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="providers.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android"><img src="assets/ui/buttons/v3-en-4a0b64bd4ded.svg" alt="Android" width="83" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="user-guide.md" title="User guide"><img src="assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="providers.md" title="Providers"><img src="assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="analytics.md" title="Analytics"><img src="assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="provider-keys-and-balances"></a>

# Provider keys and balances


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** provides an Android ARM64 APK and a Linux x86_64 desktop bundle. Read the platform requirements and verify the downloaded file before installing.


<a id="choose-what-to-view"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Choose what to view

Use the **Provider** dropdown with **All**, **OpenRouter** and **VSEGPT** to show both service cards or one. The filter belongs to this page and is retained when you leave and return. It does not choose the provider of a chat.

| Linux | Android emulator |
| --- | --- |
| <a href="assets/screenshots/v011-55-linux-providers-en.png"><img src="assets/ui/frame-top.svg" alt="" width="560"><br><img src="assets/screenshots/v011-55-linux-providers-en.png" alt="Separate OpenRouter and VSEGPT cards and provider-view dropdown on Linux" width="560"><br><img src="assets/ui/frame-bottom.svg" alt="" width="560"></a> | <a href="assets/screenshots/v011-55-android-providers-en.png"><img src="assets/ui/frame-top.svg" alt="" width="300"><br><img src="assets/screenshots/v011-55-android-providers-en.png" alt="Separate provider forms in an Android emulator" width="300"><br><img src="assets/ui/frame-bottom.svg" alt="" width="300"></a> |

*Demonstration data. Android images show an emulator.*

<a id="check-or-replace-a-key"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Check or replace a key

After the first setup, each form belongs to its named service. OpenRouter accepts complete `sk-or-v1-` keys. VSEGPT accepts complete `sk-or-vv-` and `sk-or-vis` keys. The latter does not require an extra hyphen. All prefixes need a secret continuation.

1. Select the service or **All**.
2. Enter its key in that service's field. Saved secrets are never filled back into editors.
3. Choose **Check**. The app checks only the matching service through a free endpoint.
4. Choose **Save key** when authorized, or explicitly **Save unverified key** when offered.

One protected key is saved per service and shared by all its chats. Replacing it updates the connection shown in every chat of that provider. PIN, conversations, drafts and budgets are preserved.

A failed check or cancelled replacement keeps the saved key. Entering another service's key is rejected locally. It is not forwarded elsewhere. Prefix recognition alone does not prove authorization or funds.

Each card retains only its own unfinished candidate while unlocked. Changing the filter masks it. The reveal button shows your entered candidate only. Locking clears all cards, including hidden inputs. Do not share screenshots containing a key.

You can check an already saved key without re-entering it on the OpenRouter mode screen or the VSEGPT model list. Choose **Check key**. This is separate from refreshing the catalogue. The status changes only after a real check of the selected service. If VSEGPT does not allow balance access, the key stays unverified. See [Check the saved key](user-guide.md#en-check-saved-key).

<a id="choose-the-provider-for-new-chats"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Choose the provider for new chats

**Provider for new chats** is separate from the viewing filter and does not change existing chats. Choose **Choose each time** to select a service whenever you start a chat, or choose one service to use it directly. New profiles start with manual selection. Existing profiles retain their previous service choice, including the older default when no separate preference was saved. Choosing a service for one chat does not change this setting. If its key is missing, the app opens that service’s form. Cancel returns without creating an empty chat or losing the old draft. Use [Chat connection](user-guide.md#en-chat-connection) in a chat’s **⋮** menu to change that chat’s provider with an explicit model and budget review. Configure a missing key for the intended service before continuing. An error never moves history to another provider automatically.

<a id="read-balance-and-key-status"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Read balance and key status

| Value | Meaning |
| --- | --- |
| OpenRouter balance | Account credits minus account usage, in USD, when access is allowed. |
| Key limit remaining | The separate OpenRouter key's remaining spending cap. |
| VSEGPT balance | RUB credits accessible through that key. |
| Chat budget | A local limit for one conversation, shown on Home rather than as a provider balance. |

VSEGPT has no supported separate key-limit indicator. This does not make a working key invalid or prevent paid-model selection. OpenRouter keys can work for chats without access to account credits. Enable VSEGPT balance access in the service settings if it is disabled.

**Refresh balance** updates the named service. Loading, unavailable and outdated amounts stay distinct. A failed refresh keeps the last known amount marked as outdated. A known zero is shown as zero. Missing subscriptions, insufficient funds and authorization failures have their own states.

A free validation is not a paid generation. Saving an unverified key starts no chat request. Read [chat budgets](user-guide.md) and [data protection](security.md) before sending sensitive information.

If OpenRouter supplies a daily free-request count, its card shows the remaining allowance for the UTC day. This counts requests, separately from account credits, the key spending cap and chat tokens. An unavailable count is not replaced with zero.
