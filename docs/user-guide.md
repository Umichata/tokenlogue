<p align="left">
<a href="user-guide.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="user-guide.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="README.md" title="Docs"><img src="assets/ui/buttons/en-0fba477f99e0.svg" alt="Docs" width="61" height="28"></a>
</p>

# 📘 Using Tokenlogue

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue lets you chat with OpenRouter models on Linux and Android. This guide describes the current preview. Earlier published previews can have fewer features. Start with the <a href="linux-appimage.md#english" title="Linux installation guide">Linux installation guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> or <a href="android.md#english" title="Android installation guide">Android installation guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

<a href="#en-access" title="Get started"><img src="assets/ui/buttons/en-c840c0639b46.svg" alt="Get started" width="135" height="34"></a> · <a href="#en-chats" title="Chats"><img src="assets/ui/buttons/en-e17c579b9a6d.svg" alt="Chats" width="93" height="34"></a> · <a href="#en-drafts" title="Drafts"><img src="assets/ui/buttons/en-0db65ae32e2b.svg" alt="Drafts" width="97" height="34"></a> · <a href="#en-limits" title="Limits"><img src="assets/ui/buttons/en-b9e511d82744.svg" alt="Limits" width="96" height="34"></a> · <a href="#en-chat-metrics" title="Costs"><img src="assets/ui/buttons/en-b239ee455553.svg" alt="Costs" width="92" height="34"></a> · <a href="security.md#english" title="Protection"><img src="assets/ui/buttons/en-c8aca5cd0ad1.svg" alt="Protection" width="128" height="34"></a>

<a id="en-access"></a>
<a id="en-current"></a>

<a id="get-started"></a>

### 🚀 Get started

1. Choose English or Russian on the sign-in screen.
2. Enter an API key created in your [OpenRouter account](https://openrouter.ai/settings/keys) and choose `Check key`. This contacts OpenRouter. A connection error alone does not mean that the key is invalid.
3. Choose a four-digit PIN, repeat it and select `Save PIN`. Use digits `0`–`9`. A leading zero is allowed. `Suggest PIN` fills a random suggestion that you can change. Both fields must match before saving.
4. Keep the PIN somewhere safe. The eye button reveals it when needed. Tokenlogue does not copy it automatically.
5. On Linux, follow the local-protection introduction and save a recovery code when offered. You can choose to continue with manual app locking and check automatic protection later. See <a href="security.md#en-locking" title="protecting your conversations">protecting your conversations&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
6. Choose `+` to create a chat.

<img src="assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="assets/screenshots/android-start.png" alt="First-launch setup on Android" width="320"><br>
<img src="assets/ui/frame-bottom.svg" width="320" alt="">

*First-launch setup on Android. The instructions above apply to both platforms.*

At later launches, enter your app PIN and choose `Sign in`. Updating a compatible installation preserves that PIN. Three incorrect checks temporarily block PIN entry for five minutes. Restarting does not clear the countdown. See <a href="security.md#en-pin" title="access and recovery">access and recovery&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

<a id="en-chats"></a>

<a id="create-and-manage-chats"></a>

### 💬 Create and manage chats

Choose free or paid mode, search by model name or ID, then set the chat limits. Each chat keeps its mode and model. Create another chat to choose a different model.

Free mode includes automatic model selection and models whose applicable prices are all zero. Automatic selection lets OpenRouter choose the model for each request. Free availability and service request limits still apply. Paid mode needs a valid key and known model prices. OpenRouter checks account funds when processing requests.

Use the chat list to return to a conversation. `Rename` and `Delete chat` sit below its title when there is enough vertical space. Renaming preserves messages and the draft. Deletion asks for confirmation and removes that chat's local history and draft. It does not delete the whole profile. These actions and limit editing are unavailable while sending.

The `⋮` menu contains key status, model details, token prices, budget details and limit settings. It also provides language selection, key replacement and profile actions. Opening the menu does not send a message or automatically refresh the key. Scroll inside the menu if it does not fit.

<a id="en-workspace"></a>

<a id="arrange-the-workspace"></a>

### 🧭 Arrange the workspace

The top-left button hides or shows the chat list in a wide Linux window. Tokenlogue remembers that choice. On a narrow screen it opens a drawer. Choose a chat, tap outside, or use Back or Escape to close the drawer. Changing to a narrow layout does not overwrite the saved wide-window choice.

<img src="assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="assets/screenshots/linux-chat.png" alt="Linux conversation workspace with demonstration data" width="760"><br>
<img src="assets/ui/frame-bottom.svg" width="760" alt="">

*The Linux workspace with demonstration data. Your chat list, conversation and editor remain together.*

Choose `Interface language` in `⋮` to switch between English and Russian. The choice is remembered. Chat titles, your messages and model replies are not translated. Changing language preserves ordinary editor input and drafts. For safety, an unfinished recovery-code or profile-deletion confirmation must be started again in the selected language.

Long titles are shortened visually. When the keyboard or a short window leaves little room, the rename and delete shortcuts are hidden. Dismiss the keyboard or make the window taller to show them again. The conversation and editor use the remaining space.

<a id="en-drafts"></a>

<a id="send-messages-and-keep-drafts"></a>

### ✍️ Send messages and keep drafts

Type in `Message` and choose `Send`. With a keyboard, Enter sends and Shift+Enter inserts a line break. Empty messages cannot be sent. Tokenlogue sends the message and eligible conversation context to OpenRouter and the selected model provider.

Each chat saves its own draft locally. Switching chats, resizing, renaming, locking and restarting preserve the saved text. A draft is separate from message history. Typing does not send it, spend funds or add it to model context.

Once a message is accepted for sending, its submitted draft is cleared. You can start a new draft while waiting. Completion of the previous request will not erase the newer text. A failed pre-send check or cancelled paid confirmation keeps the original draft.

If a reply is incomplete or a request fails, read its status before retrying. Retrying a request that already reached the service can cause another charge.

<a id="en-limits"></a>

<a id="set-chat-limits"></a>

### 🎚️ Set chat limits

Configure limits before the first request. Use `Set limits` or `Edit limits` in `⋮` to change them later.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Setting | What it controls |
| --- | --- |
| Total chat token limit | Input and response tokens across this chat's requests. Repeated conversation context also uses tokens. |
| Maximum tokens per response | The requested upper bound for each answer. An answer can be shorter. |
| Chat spending limit, USD | The local spending cap for a paid chat. Increasing it asks for confirmation. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Before sending, Tokenlogue reserves tokens and, in paid mode, money. The available chat budget excludes actual use and active reservations. A request can be refused when the remaining budget cannot cover its reserve. A local reservation is not an OpenRouter charge.

The chat budget, the spending limit of your OpenRouter key and your OpenRouter account balance are separate. Tokenlogue does not fetch the total account balance. A key without its own spending limit does not imply unlimited account funds.

<a id="en-paid-confirmation"></a>

<a id="choose-when-paid-requests-need-confirmation"></a>

### ✅ Choose when paid requests need confirmation

New paid chats ask for confirmation before sending. Review the model, estimated input, response maximum and spending reserve. Cancel to leave the message unsent.

`Without confirmation` above the conversation turns off that dialog for the selected chat, including its first request, retries and changed prices. Enabling it sends nothing by itself. Limits, key checks and price checks still apply. Raising the spending limit keeps its separate confirmation.

Turn the option off to require confirmation from the next request onward. The choice is saved per chat. Locking or changing this setting never submits a queued message automatically. Choose `Send` when ready.

<a id="en-chat-metrics"></a>

<a id="read-token-and-cost-information"></a>

### 💳 Read token and cost information

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Display | Meaning |
| --- | --- |
| Chat available | Paid-chat budget remaining after actual costs and active reservations. |
| Tokens remaining | Free-chat token budget remaining after use and active reservations. This is not OpenRouter's global free quota. |
| Last request | Confirmed cost for a paid chat or total input-and-response tokens for a free chat. Retries count as new attempts. |
| Key remaining | The current API key's known remaining spending limit, separate from the chat budget and account balance. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

`Key limit not set` means that the key has no separate cap. `Key data unavailable` means its remainder is unknown. An exhausted limit is shown explicitly. Hover or long-press a metric for details and the key-data receipt time when available. Use `Refresh key status` in `⋮` to request fresh data. Typing or reopening the display does not make old data fresh.

`No requests`, `In progress`, `Reconciling` and `Unknown` describe different states. An unknown result is not treated as zero cost.

The estimate under the editor changes as you type. It includes eligible history and the effective response maximum. It is a conservative local estimate based on UTF-8 text, not exact model tokenization or a prediction of reply length. The possible cost is an upper estimate for known prices. Missing or expired pricing produces `Cost unknown`. Actual usage and cost are determined after sending.

Calculating an estimate makes no network request and reserves no budget. The normal checks still run when you send.

<a id="handle-an-unknown-request-result"></a>

### ❔ Handle an unknown request result

A lost connection can leave uncertainty about whether OpenRouter processed a request. Tokenlogue keeps its protective reserve rather than treating it as free. Check the request and billing in your OpenRouter account before retrying.

After checking, `Release unknown reservation` returns that local reserve to the chat budget. It does not cancel a remote request or refund a charge. A retry can create another charge.

<a id="en-key-replacement"></a>

<a id="replace-an-openrouter-key"></a>

### 🔑 Replace an OpenRouter key

Sign in with your existing PIN, open `⋮` and choose `Replace OpenRouter key`. This works with or without a selected chat. Finish any current send or key check first.

The old key stays saved until the replacement passes validation and is stored. Cancellation or a failed check keeps it. Your PIN, encryption key, chats, drafts and budgets stay the same. This action neither recovers a forgotten PIN nor revokes the old key at OpenRouter. Revoke a key in your OpenRouter account if needed.

<a id="en-protection-check"></a>
<a id="en-pin-recovery"></a>
<a id="en-delete"></a>
<a id="en-data"></a>

<a id="protect-your-conversations"></a>

### 🛡️ Protect your conversations

Use the header lock button before leaving the device. On Android, moving the app to the background closes access. Linux screen-lock and sleep monitoring depends on the desktop session.

Read <a href="security.md#english" title="conversation protection and recovery">conversation protection and recovery&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> before relying on a PIN or changing device security. It explains encrypted fields, the Linux recovery code, Android system recovery, local-protection checks and irreversible profile deletion. Copying a database alone does not back up its separate encryption key.

<a href="../README.md#english" title="Tokenlogue"><img src="assets/ui/buttons/en-931ef4e6d14f.svg" alt="Tokenlogue" width="135" height="34"></a> · <a href="linux-appimage.md#english" title="Linux"><img src="assets/ui/buttons/en-411f244045b9.svg" alt="Linux" width="91" height="34"></a> · <a href="android.md#english" title="Android"><img src="assets/ui/buttons/en-5d10a1d077a6.svg" alt="Android" width="109" height="34"></a> · <a href="source-materials.md#english" title="Source materials"><img src="assets/ui/buttons/en-6c08d5ca10c9.svg" alt="Source materials" width="176" height="34"></a>
