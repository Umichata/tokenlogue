<p align="left">
<a href="user-guide.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="user-guide.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# 📘 Using Tokenlogue

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue lets you chat with OpenRouter models on Linux and Android. This guide describes version 0.2.0. Start with the <a href="linux-appimage.md#english" title="Linux installation guide">Linux installation guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> or <a href="android.md#english" title="Android installation guide">Android installation guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

<p align="left"><a href="#en-access"><img src="assets/ui/buttons/en-ca3dbec2e101.svg" alt="Get started" width="109" height="28"></a> <a href="#en-chats"><img src="assets/ui/buttons/en-474e166de580.svg" alt="Chats" width="67" height="28"></a> <a href="#en-drafts"><img src="assets/ui/buttons/en-1cd72768132b.svg" alt="Drafts" width="71" height="28"></a> <a href="#en-limits"><img src="assets/ui/buttons/en-d98731f70acd.svg" alt="Limits" width="70" height="28"></a> <a href="#en-chat-metrics"><img src="assets/ui/buttons/en-0ee613298d92.svg" alt="Costs" width="66" height="28"></a> <a href="security.md#english"><img src="assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a></p>

<a id="en-access"></a>
<a id="en-current"></a>

<a id="get-started"></a>

<a id="-get-started"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Get started

1. Choose English or Russian on the sign-in screen.
2. Enter an API key created in your [OpenRouter account](https://openrouter.ai/settings/keys) and choose `Check key`. This contacts OpenRouter. A connection error alone does not mean that the key is invalid.
3. Choose a four-digit PIN, repeat it and select `Save PIN`. Use digits `0`–`9`. A leading zero is allowed. `Suggest PIN` fills a random suggestion that you can change. Both fields must match before saving.
4. Keep the PIN somewhere safe. The eye button reveals it when needed. Tokenlogue does not copy it automatically.
5. On Linux, follow the local-protection introduction and save a recovery code when offered. You can choose to continue with manual app locking and check automatic protection later. See <a href="security.md#en-locking" title="protecting your conversations">protecting your conversations&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
6. Choose `+` to create a chat.

<img src="assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="assets/screenshots/android-start.png" alt="First-launch setup on Android" width="320"><br>
<img src="assets/ui/frame-bottom.svg" width="320" alt="">

*First-launch Android illustration from an earlier preview. The instructions above apply to both platforms.*

At later launches, enter your app PIN and choose `Sign in`. Updating a compatible installation preserves that PIN. Three incorrect checks temporarily block PIN entry for five minutes. Restarting does not clear the countdown. See <a href="security.md#en-pin" title="access and recovery">access and recovery&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

<a id="en-chats"></a>

<a id="create-and-manage-chats"></a>

<a id="-create-and-manage-chats"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Create and manage chats

Choose free or paid mode, search by model name or ID, then set the chat limits. Each chat keeps its mode and model. Create another chat to choose a different model.

Free mode includes automatic model selection and models whose applicable prices are all zero. Automatic selection lets OpenRouter choose the model for each request. Free availability and service request limits still apply. Paid mode needs a valid key and known model prices. OpenRouter checks account funds when processing requests.

Use the chat list to return to a conversation. `Rename` and `Delete chat` sit below its title when there is enough vertical space. Renaming preserves messages and the draft. Deletion asks for confirmation and removes that chat's local history and draft. It does not delete the whole profile. These actions and limit editing are unavailable while sending.

The `⋮` menu contains key status, model details, token prices, budget details and limit settings. It also provides language selection, key replacement and profile actions. Opening the menu does not send a message or automatically refresh the key. Scroll inside the menu if it does not fit.

<a id="en-workspace"></a>

<a id="arrange-the-workspace"></a>

<a id="-arrange-the-workspace"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Arrange the workspace

The top-left button hides or shows the chat list in a wide Linux window. Tokenlogue remembers that choice. On a narrow screen it opens a drawer. Choose a chat, tap outside, or use Back or Escape to close the drawer. Changing to a narrow layout does not overwrite the saved wide-window choice.

<img src="assets/ui/frame-top.svg" width="760" alt=""><br>
<img src="assets/screenshots/linux-chat.png" alt="Linux conversation workspace with demonstration data" width="760"><br>
<img src="assets/ui/frame-bottom.svg" width="760" alt="">

*An earlier Linux preview workspace with demonstration data. Your chat list, conversation and editor remain together.*

Choose `Interface language` in `⋮` to switch between English and Russian. The choice is remembered. Chat titles, your messages and model replies are not translated. Changing language preserves ordinary editor input and drafts. For safety, an unfinished recovery-code or profile-deletion confirmation must be started again in the selected language.

Long titles are shortened visually. When the keyboard or a short window leaves little room, the rename and delete shortcuts are hidden. Dismiss the keyboard or make the window taller to show them again. The conversation and editor use the remaining space.

<a id="en-drafts"></a>

<a id="send-messages-and-keep-drafts"></a>

<a id="-send-messages-and-keep-drafts"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Send messages and keep drafts

Type in `Message` and choose `Send`. With a keyboard, Enter sends and Shift+Enter inserts a line break. Empty messages cannot be sent. Tokenlogue sends the message and eligible conversation context to OpenRouter and the selected model provider.

Each chat saves its own draft locally. Switching chats, resizing, renaming, locking and restarting preserve the saved text. A draft is separate from message history. Typing does not send it, spend funds or add it to model context.

Once a message is accepted for sending, its submitted draft is cleared. You can start a new draft while waiting. Completion of the previous request will not erase the newer text. A failed pre-send check or cancelled paid confirmation keeps the original draft.

If a reply is incomplete or a request fails, read its status before retrying. Retrying a request that already reached the service can cause another charge.

<a id="en-limits"></a>

<a id="set-chat-limits"></a>

<a id="-set-chat-limits"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Set chat limits

Configure limits before the first request. Use `Set limits` or `Edit limits` in `⋮` to change them later.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Setting | What it controls |
| --- | --- |
| Total chat token limit | Input and response tokens across this chat's requests. Repeated conversation context also uses tokens. |
| Maximum tokens per response | The requested upper bound for each answer. An answer can be shorter. |
| Chat spending limit, USD | The local spending cap for a paid chat. Increasing it asks for confirmation. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Before sending, Tokenlogue reserves tokens and, in paid mode, money. The available chat budget subtracts actual use and active reservations. A local reservation is not an OpenRouter charge. Token, context, provider and API key limits still apply to every request. Unknown request accounting must be resolved before another request can use that chat's budget.

The chat budget is a local setting. The API key limit belongs to that key, while the OpenRouter account balance comes from the account API. Neither account balance nor key limit changes your saved chat spending limit.

<a id="en-budget-warning"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Review a chat-budget warning

A paid request triggers a warning when its upper cost estimate is positive and its projected chat remainder is 10% of the saved spending limit or less. The calculation subtracts actual costs, active monetary reservations and the planned request's upper estimate. It includes the history sent, model prices, fixed request costs and the response limit.

The risk is calculated before a chat-money cap could shorten the planned response and hide a possible overrun. Token, context, provider and API key restrictions remain in force. The warning is about the chat budget, not the account balance or API key limit. An exactly free request needs no monetary warning.

| Action | Result |
| --- | --- |
| Cancel | Sends nothing, creates no reserve and keeps the draft. Closing the dialog, Escape and Android Back cancel too. |
| Send | Confirms this exact request once. It can permit exceeding the local chat spending limit without raising that saved limit or disabling later warnings. |
| Change chat limit | Opens this chat's limits and preserves the draft. Saving a limit does not send anything. Review the new estimate before sending. |

A projected zero can exhaust the budget. A negative projection can exceed it, and the warning says so. After a confirmed overrun, the actual remaining chat amount can stay negative. It is not rounded up to zero or turned into a higher saved limit. Changing the draft, model, limits, prices or risk makes an earlier decision expire and can require a fresh warning.

<a id="en-paid-confirmation"></a>

<a id="choose-when-paid-requests-need-confirmation"></a>

<a id="-choose-when-paid-requests-need-confirmation"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Choose when paid requests need confirmation

New paid chats ask for confirmation before sending. Review the model, estimated input, response maximum and spending reserve. Cancel to leave the message unsent.

`Without confirmation` above the conversation turns off the ordinary paid-request dialog for the selected chat, including its first request and retries. It also accepts known current model prices for each send, including increases, without a separate new-price confirmation. Turn it off if you want to review price changes before sending. Chat-budget warnings, token limits, key checks, rejection of unknown or unsafe prices and unknown-accounting protection still apply. Enabling it sends nothing by itself. Raising the saved spending limit keeps its separate confirmation.

Turn the option off to require confirmation from the next request onward. The choice is saved per chat. Locking or changing this setting never submits a queued message automatically. Choose `Send` when ready.

<a id="en-balance"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Read your OpenRouter account balance

`OpenRouter balance` is the account amount returned for your current key by OpenRouter's credits API. Tokenlogue calculates `total_credits - total_usage` with decimal arithmetic. Positive, zero and negative results are valid. It does not estimate an account balance by subtracting local request costs.

The balance appears in free and paid chats. Loading, a current snapshot, an outdated snapshot and `Balance unavailable` are distinct states. A saved session snapshot includes its receipt time. If a refresh fails, a previous value is explicitly marked outdated. Without a successful snapshot, no artificial zero is shown.

The app refreshes after sign-in or unlock and after a sent request finishes, including a retry or an interrupted request that might have been charged. The reply is saved and shown without waiting for this read. A short delayed refresh allows for billing updates on the server. Switching chats does not cancel the account refresh. Locking, signing out or replacing the key discards the old session's balance.

Choose `Refresh key and balance` in `⋮` for a manual update. A denied balance read, including HTTP 403, does not by itself mean that the key cannot send model requests. Account access can vary between keys. Tokenlogue shows the read failure without deleting chats or changing your PIN.

<a id="en-chat-metrics"></a>

<a id="read-token-and-cost-information"></a>

<a id="-read-token-and-cost-information"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Read token and cost information

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Display | Meaning |
| --- | --- |
| Chat available | Paid-chat budget remaining after actual costs and active reservations. |
| Tokens remaining | Free-chat token budget remaining after use and active reservations. This is not OpenRouter's global free quota. |
| Last request | Confirmed cost for a paid chat or total input-and-response tokens for a free chat. Retries count as new attempts. |
| Key remaining | The current API key's known remaining spending limit, separate from the chat budget and account balance. |
| OpenRouter balance | The account snapshot received from OpenRouter, with its refresh state. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

`Key limit not set` means that the key has no separate cap. `Key data unavailable` means its remainder is unknown. An exhausted limit is shown explicitly. Hover or long-press a metric for details and the key-data receipt time when available. Use `Refresh key and balance` in `⋮` to request fresh data. Typing or reopening the display does not make old data fresh.

`No requests`, `In progress`, `Reconciling` and `Unknown` describe different states. An unknown result is not treated as zero cost.

The estimate under the editor changes as you type. It includes eligible history and the effective response maximum. It is a conservative local estimate based on UTF-8 text, not exact model tokenization or a prediction of reply length. The possible cost is an upper estimate for known prices before any chat-money cap could hide a budget risk. Missing or expired pricing produces `Cost unknown`. Actual usage and cost are determined after sending.

Calculating an estimate makes no network request and reserves no budget. The normal checks still run when you send.

<a id="handle-an-unknown-request-result"></a>

<a id="-handle-an-unknown-request-result"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Handle an unknown request result

A lost connection can leave uncertainty about whether OpenRouter processed a request. Tokenlogue keeps its protective reserve rather than treating it as free. Check the request and billing in your OpenRouter account before retrying.

After checking, `Release unknown reservation` returns that local reserve to the chat budget. It does not cancel a remote request or refund a charge. A retry can create another charge.

<a id="en-key-replacement"></a>

<a id="replace-an-openrouter-key"></a>

<a id="-replace-an-openrouter-key"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Replace an OpenRouter key

Sign in with your existing PIN, open `⋮` and choose `Replace OpenRouter key`. This works with or without a selected chat. Finish any current send or key check first.

The old key stays saved until the replacement passes validation and is stored. Cancellation or a failed check keeps it. Your PIN, encryption key, chats, drafts and budgets stay the same. This action neither recovers a forgotten PIN nor revokes the old key at OpenRouter. Revoke a key in your OpenRouter account if needed.

<a id="en-protection-check"></a>
<a id="en-pin-recovery"></a>
<a id="en-delete"></a>
<a id="en-data"></a>

<a id="protect-your-conversations"></a>

<a id="-protect-your-conversations"></a>
### <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Protect your conversations

Use the header lock button before leaving the device. On Android, moving the app to the background closes access. Linux screen-lock and sleep monitoring depends on the desktop session.

Read <a href="security.md#english" title="conversation protection and recovery">conversation protection and recovery&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> before relying on a PIN or changing device security. It explains encrypted fields, the Linux recovery code, Android system recovery, local-protection checks and irreversible profile deletion. Copying a database alone does not back up its separate encryption key.

<p align="left"><a href="../README.md#english"><img src="assets/ui/buttons/en-2e5a16e1977a.svg" alt="Tokenlogue" width="109" height="28"></a> <a href="linux-appimage.md#english"><img src="assets/ui/buttons/en-96c04f670a21.svg" alt="Linux" width="65" height="28"></a> <a href="android.md#english"><img src="assets/ui/buttons/en-46463edb13a7.svg" alt="Android" width="83" height="28"></a> <a href="source-materials.md#english"><img src="assets/ui/buttons/en-b63fdbc05df7.svg" alt="Source materials" width="150" height="28"></a></p>
