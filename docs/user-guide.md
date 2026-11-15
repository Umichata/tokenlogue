[English](user-guide.md#english) · [Русский](user-guide.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Chat guide

[Home](../README.md) · [Documentation](../docs/README.md)

> **0.1.1 is local.** These instructions describe the current source and local builds. [Published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) is the earlier release. Its download links do not provide 0.1.1.


<a id="en-first-connection"></a>
<a id="en-local-flow"></a>
## First connection

1. Select English or Russian and enter a provider key. OpenRouter begins with `sk-or-v1-`. VSEGPT begins with `sk-or-vv-` or `sk-or-vis`. A secret continuation is required. `sk-or-vis` does not require an extra hyphen.
2. Choose **Check key**. Recognition happens locally and checking uses a free endpoint. If VSEGPT cannot confirm authorization, explicitly choose **Save unverified key** when offered. No chat message is sent during setup.
3. Choose four digits, repeat them and save your app PIN. A leading zero is allowed. Keep it safe.
4. On Linux, follow the local-protection introduction and save a recovery code when offered. Manual locking remains available.
5. Create a chat with **+**.

A VSEGPT-only profile needs no OpenRouter key. Add the second service later through [Providers](providers.md). Subsequent sign-ins and recovery use your existing protected profile rather than opening a new registration.

<a href="assets/screenshots/v011-android-first-run-en.png"><img src="assets/screenshots/v011-android-first-run-en.png" alt="First provider connection in an Android emulator" width="320"></a>

*Demonstration setup with a masked synthetic key.*

[Choosing an app PIN](assets/screenshots/v011-android-pin-setup-en.png) shows the next step without displaying a PIN.

## Navigate without losing your place

**Home**, **Providers**, **Tokens** and **Spending** belong to the whole app. On wide Linux windows they appear in a dark navigation rail. Android and narrow windows use bottom navigation. The separate chat panel belongs to Home.

Switching pages saves the draft and keeps the current chat. Android Back returns to Home from an auxiliary page. A dispatched request can finish once while another page is open. Navigation never sends the draft.

## Create and manage a chat

Use **+** to choose free or paid mode, an available model and limits. The default provider applies only to new chats. Use **Chat connection** to change the service of an existing chat explicitly. To use a different model within the same service, create another chat.

OpenRouter free mode can use automatic model selection or models whose applicable prices are all zero. VSEGPT pricing can use other billing units. An unknown price is not a free model.

Use the conversation list to reopen a chat. **Rename** preserves its history and draft. **Delete chat** asks for confirmation and removes that chat, its draft and its local statistics. Header shortcuts can hide when the keyboard leaves too little height. The **⋮** menu holds model details, limits, key information and profile actions.

[New chat and model choice](assets/screenshots/v011-android-models-en.png) · [Rename](assets/screenshots/v011-android-rename-en.png) · [Delete chat](assets/screenshots/v011-android-delete-chat-en.png) · [Chat limits](assets/screenshots/v011-android-chat-limits-en.png)

*Demonstration conversation actions in an Android emulator. Model names come from the service catalogue.*

<a id="en-chat-connection"></a>
## Chat connection and provider changes

Open **⋮** in the selected chat. **Chat connection** shows its provider and key status, with a masked reference when a key is saved. Each provider has one protected key shared by all its chats. A sufficiently long key shows only its last four characters, otherwise it stays fully masked. **Configure OpenRouter key** or **Configure VSEGPT key** opens the matching service card.

1. Choose **Change provider**, then select OpenRouter or VSEGPT. The current provider is marked.
2. If the target key is missing, configure it in the offered service card. Return to Home and explicitly choose the provider again to continue.
3. Choose an available free or paid mode, select a model from that service and review its limits. A paid model needs a budget in its own currency. A matching model ID from another service is not selected automatically.
4. Choose **Review change**. Check the provider, model, currency, amount already spent and remaining chat budget, then choose **Change provider**.

The app checks the catalogue again at confirmation. If it is unavailable or the selected model has changed, the previous connection stays in place. Try later or review the current model before confirming again.

Configuration sends no message. Your next ordinary **Send** shares the new message and completed conversation pairs that fit the selected model’s context with the new service.

The chat title, messages, draft and protection stay intact. Its token limit and tokens already used remain shared across services. The shared token limit is read-only during this change. USD and RUB money limits, spending and reserves stay separate. Returning to a provider restores its existing money state. **Without confirmation** is turned off after a change, so the new service needs fresh paid-request consent.

Before final confirmation, Cancel or Back leaves the stored connection unchanged. Selecting the current provider changes nothing. Other chats and the default for new chats stay as they were. Wait for an active request to finish and resolve unsettled accounting before changing a connection. An error never switches the chat to another service automatically.

<a id="en-chat-connection-examples"></a>

| Connection | Linux | Android |
| --- | --- | --- |
| OpenRouter | <a href="assets/screenshots/v011-linux-chat-connection-openrouter-en.png"><img src="assets/screenshots/v011-linux-chat-connection-openrouter-en.png" alt="OpenRouter chat connection and masked test key on Linux" width="320"></a> | <a href="assets/screenshots/v011-android-chat-connection-openrouter-en.png"><img src="assets/screenshots/v011-android-chat-connection-openrouter-en.png" alt="OpenRouter chat connection and key status in an Android emulator" width="220"></a> |
| VSEGPT | <a href="assets/screenshots/v011-linux-chat-connection-vsegpt-en.png"><img src="assets/screenshots/v011-linux-chat-connection-vsegpt-en.png" alt="VSEGPT chat connection and masked test key on Linux" width="320"></a> | <a href="assets/screenshots/v011-android-chat-connection-vsegpt-en.png"><img src="assets/screenshots/v011-android-chat-connection-vsegpt-en.png" alt="VSEGPT chat connection and masked test key in an Android emulator" width="220"></a> |

*Demonstration profiles with sample keys in the Linux app and an Android emulator. Sending requires a valid key for the chosen service. Changing the interface language does not translate existing messages.*

- Linux examples show [provider choice](assets/screenshots/v011-linux-chat-provider-picker-en.png), [the final review](assets/screenshots/v011-linux-chat-connection-review-en.png) and [the chat after a change](assets/screenshots/v011-linux-chat-after-switch-en.png).
- Android examples show [provider choice](assets/screenshots/v011-android-chat-provider-picker-en.png), [the final review](assets/screenshots/v011-android-chat-connection-review-en.png) and [the chat after a change](assets/screenshots/v011-android-chat-after-switch-en.png).

## Messages and drafts

Type a message and select **Send**. With a keyboard, Enter sends and Shift+Enter inserts a line break. Sending shares the message and relevant history with the service assigned to that chat and its selected model provider.

Each chat saves its own draft. Switching chats or pages, resizing, locking and restarting keep it. Drafts do not count as sent messages, context or spending. A successfully submitted draft is cleared. Text entered while an earlier request is waiting remains after its response arrives.

If a pre-send check fails or you cancel a confirmation, the original draft stays. Check the status of an interrupted request before retrying because another dispatch can incur another charge.

## Set chat limits

Open **Set limits** or **Edit limits** in **⋮**.

| Setting | Meaning |
| --- | --- |
| Chat token limit | Input and answer tokens used across this chat’s providers, including repeated context. |
| Response maximum | The requested answer-token ceiling. The answer can be shorter. |
| Chat spending limit | A separate local limit for this chat’s current provider in USD or RUB. An increase needs confirmation. |

Available chat budget subtracts used tokens or money and active reservations. Reservations protect the local budget while accounting is pending. They are not a separate provider charge. Provider restrictions and OpenRouter key limits still apply.

## Review a budget warning

A paid request that could leave 10% or less of the chat's spending limit shows a warning. A zero remainder can exhaust the chat budget. A negative remainder can exceed it. This calculation uses the chat limit, its costs, active reserves and the planned request estimate.

| Action | Result |
| --- | --- |
| Cancel | Keeps the draft and sends nothing. Back, Escape or closing the dialog also cancel. |
| Send | Approves only this reviewed request. It can permit an overrun without increasing the saved chat limit. |
| Change chat limit | Opens this chat's settings. Saving does not send the draft. Review it again before sending. |

Unknown pricing requires explicit review too. A changed draft, model, price or budget can require new consent. An estimate cannot guarantee the final charge.


<a href="assets/screenshots/v011-android-budget-warning-en.png"><img src="assets/screenshots/v011-android-budget-warning-en.png" alt="Unknown model-price review with three actions" width="320"></a>

*Demonstration data in an Android emulator. This example asks for review because the model price is unavailable. The displayed remainder belongs to the chat budget.*

## Ordinary paid confirmation

Paid chats normally request confirmation before sending. **Without confirmation** disables that ordinary dialog for the selected chat from its first request, including retries. Known current model prices can then be accepted without another price-change dialog.

Chat-budget warnings, token limits, key checks and unknown-price protection continue to apply. Switching the option does not send anything. Turn it off to review the next paid request again.

## Read tokens and money

The full-width metrics strip shows values for the open chat and its provider. Hover or long-press for details.

| Display | Source |
| --- | --- |
| Chat budget remaining | Local spending limit minus recorded costs and current reserves. |
| Tokens remaining | This chat's token budget, not a provider-wide free quota. |
| Last request | Its recorded cost or tokens and accounting status. |
| OpenRouter balance | The account amount returned by OpenRouter credits. |
| VSEGPT balance | The RUB amount returned through VSEGPT balance access. |
| Key limit remaining | The remaining separate OpenRouter key cap. VSEGPT has no supported separate key cap. |

The last request keeps its original currency after a provider change.

A known zero, negative remainder, unset key cap and unavailable value are different states. An unset cap does not promise available funds. Stale service balances keep their last amount and are marked as outdated.

The estimate below the editor includes eligible history and the response limit. It is local and approximate. It is not exact model tokenization. Missing prices produce an unavailable cost estimate. Calculating it sends no request and reserves no money.

## Refresh or replace a key

Use **Refresh key and balance** in **⋮** for current provider data. A completed chat request also starts its own balance refresh. The answer does not wait for that refresh. Failed balance access does not replace the answer or turn an unknown amount into zero.

Use [Providers](providers.md) to check or replace the correct service's key. The old saved key remains until the replacement is accepted and saved. This keeps the PIN, chats, drafts and budgets. Revoke an old key in the service account if needed.

## Interrupted requests

Retrying after a connection change uses a new attempt with the current provider and model. Check that destination before retrying. The previous attempt keeps its original service and accounting.

A lost connection can leave the provider charge uncertain. The protective reserve stays in the chat budget. Check the provider request and billing before retrying. **Release unknown reservation** releases only that local reserve. It does not cancel the remote request or refund a charge.

## Statistics and protection

[Tokens and Spending](analytics.md) show saved activity on this device. Deleting a chat removes its statistics. [Protection and recovery](security.md) explains locking, PIN recovery and irreversible profile deletion. A database copy alone cannot preserve its separately stored encryption key.
