# Tokenlogue - User guide / Руководство пользователя

[English](#lang-en) | [Русский](#lang-ru)

<a name="lang-en"></a>

## English

This guide describes the current [published `0.1.0` preview `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
The [current-source section](#en-current) describes newer setup, system locking,
Linux PIN recovery, local profile deletion, chat panel controls and language selection. Those changes are not
part of the published Linux preview. The published preview has a Russian
interface, so its instructions use Russian control labels. Current builds
also offer English. The current-build instructions below use English labels
when English is selected.
For installation of the published preview, use the
[Linux AppImage guide](linux-appimage.md#lang-en).

[Key and PIN in the Linux preview](#en-access) | [Current builds](#en-current) |
[Delete local profile](#en-delete) | [Panel and language](#en-workspace) |
[Chats and menu](#en-chats) | [Metrics and estimate](#en-chat-metrics) |
[Messages and drafts](#en-drafts) | [Limits](#en-limits) | [Data](#en-data)

<a name="en-access"></a>

### First launch and signing in to the published Linux preview

On first launch, enter your API key in `OpenRouter API-ключ` and choose
`Проверить ключ` (check key). Obtain a key through your OpenRouter account.
Checking it requires access to OpenRouter. A network error does not by itself
mean that the key is invalid.

After successful validation, Tokenlogue generates a four-digit PIN and shows
it once. Save all four digits, including any leading zero, then choose
`Я сохранил PIN` (I saved the PIN). The key is stored only after this
confirmation. At later launches, enter the PIN and choose `Войти` (sign in).
Five incorrect attempts cause a 30-second lockout.

Use the lock button in the header to return to the PIN screen. If you forget
the PIN or need to reset access, use `Сбросить ключ` (reset key) on that screen
and confirm. This removes the saved API key, PIN verification data and lockout
state. Existing chats and drafts remain. The next setup requires the key again
and generates a new PIN. This local reset does not revoke the key at OpenRouter.

After unlocking, check the key status through `⋮`. The panel shows whether the key is valid
and its remaining spending limit, if available. Depending on the key status, it offers
`Повторить проверку ключа` (check again) or `Заменить ключ` (replace key).
Opening the menu alone does not recheck the key or send a model request.
The key's spending limit is separate from the local limit of each chat.

<a name="en-current"></a>

### Choosing a PIN and locking in current builds

This section applies to builds made from the current source, including new
Android builds. The published Linux preview `2b1f7d3` keeps the setup described
[above](#en-access).

After your OpenRouter key has been checked, the `Choose a PIN` screen opens with an empty `PIN` field. Choose exactly four digits from `0`
to `9`. Leading zeros are allowed. Repeat the value in `Repeat PIN`. Spaces, other characters and digits from other writing systems
are not accepted.

You can choose `Suggest PIN` to fill the first field with a
random value. You can edit that value before saving. Any change to the first
field or a new suggestion clears the repeat field, even if the suggested
number happens to be the same. `Save PIN` is available only
when both fields contain the same valid PIN and no operation is in progress.
A suggestion alone does not complete setup.

Both fields hide their contents. Use the eye button to reveal the PIN when
you need to check or save it somewhere safe. Tokenlogue does not copy it to
the clipboard automatically. The checked key and PIN verification data are
saved when you confirm setup. If you leave an unfinished Android setup in
the background, enter the key again when you return and choose a PIN again.

On Android, moving Tokenlogue to the background locks access to chats and
closes open dialogs. Returning to the app or unlocking Android does not
unlock Tokenlogue. Enter your PIN to continue with the selected chat,
history and draft. Opening the keyboard or briefly losing focus alone does
not lock the app. The header lock button remains available on every platform.

On Linux Mint 22.3 Cinnamon/X11, the screen locker becoming active, a session
switch or suspend closes the workspace and cancels an unfinished recovery
attempt. Your latest draft is saved. A request already sent keeps its reserve
and may still save its response and accounting. Unlocking the desktop or
returning from sleep does not open chats. Enter your app PIN or start a fresh
recovery check. Minimizing the window, changing focus or opening the polkit
prompt alone does not lock Tokenlogue.

<a name="en-protection-check"></a>

#### Local protection checks

On Linux, saving the checked key and chosen PIN for a new protected profile
automatically opens `Check local protection` before chats. The saved PIN is
already active. The screen explains what will happen and waits for your
explicit `Start check`. Saving a key or PIN does not unexpectedly lock the OS.
The test does not need a selected chat or a previous manual screen lock.

`Start check` first prepares the supported desktop screen-locking service.
A service that has not started yet is not a reason to disable the button
forever. Preparation has a time limit and shows its outcome. If it cannot
finish, read the explanation and retry. Do not change desktop lock settings
or install system policy just to start the check.

The OS then locks through its normal screen locker. Unlock it normally and
enter your saved Tokenlogue PIN. You do not need to enter your API key or
create a profile again. A confirmed result belongs to that same check and
remains visible after sign-in. Choose `Open chats` to finish the step.
The offer to create a recovery code follows this step and can be left for
later. Replacing an existing key does not restart this first-run step.

If you restart before finishing the step, sign in with your saved PIN to
resume it. You may instead choose `Continue with manual locking`. This keeps
the result explicitly unconfirmed and opens the profile for normal use.
Lock Tokenlogue manually until the screen check is confirmed. Remembering
that this setup step was handled is separate from the saved check history.

The shield at the far right of the PIN screen's app header opens the same
`Local protection` panel as the chat shield. The language selector remains
available in the header. Protection no longer takes a permanent line beneath
the PIN instruction. Opening the panel leaves any digits already entered
unchanged and does not unlock conversations or request an OS action.

Choose `Test screen lock` or `Test sleep protection` while locked to continue
through your ordinary PIN sign-in. Incorrect PIN and the existing countdown
still apply. You can cancel the choice from the PIN form or reopen the panel
and close it. After successful sign-in the selected test has an explicit
`Start test` action. Entering PIN alone never locks or suspends the OS.
A choice expires and is cancelled by recovery, deletion, another system lock
or restart. Choose the test again if needed.

In an open profile, the shield beside the far-right `⋮` opens `Local protection`
immediately. The menu also opens that same panel. `Test screen lock` is available
with an empty chat list and in a new desktop session before its first screen lock. It uses the same check
as the setup step, saves the current draft and waits for your explicit action.
A short conflicting operation or another running check can temporarily make
it busy. Finish that operation and retry.

Screen locking and sleep have separate histories with the time of their last
completed checks. Green means the real OS cycle and Tokenlogue's normal
protection were confirmed. A screen check does not confirm sleep. Testing
one mechanism leaves the other result intact.

`Test sleep protection` is available beside `Test screen lock` after sign-in,
including an empty chat list. Read its explanation before pressing it.
The computer will sleep. Your draft is saved first. Wake the computer,
unlock the OS normally and enter your app PIN. Unlocking the OS never opens
Tokenlogue automatically or sends a draft. A previous screen test is not
required. The two tests cannot run together. Opening the menu or saving
registration never starts sleep. Ordinary sleep from the OS menu still
protects the app and does not erase the screen result.

Results survive restarting Tokenlogue, rebooting this device, normal sleep,
PIN sign-in, language changes and menu rebuilding. A temporary reconnect
shows the previous check separately from a warning about current monitoring.
Once trusted compatible monitoring returns, the saved confirmation becomes
current without another manual test. A changed protection contract or an
unsupported locker can require a new check. A different computer or OS
account has its own history. Copying a chat profile or preferences does not
copy device confirmation. Device check history is not part of chat exports.
Deleting a chat profile leaves this device history in place.

A denied request, cancellation or an attempt without proven sleep does not
create a new success or erase a previous check. A real failure is red for
the affected mechanism and keeps the time of its previous success in details.
Emergency closure protects data but never makes a failed test pass.
A save error means a current result may be correct but has not been remembered
for the next launch. Never treat old green history as proof that unavailable
monitoring is working now. Use manual app locking while a warning remains.

Use one active local Cinnamon/X11 desktop and one display. Additional displays,
ambiguous sessions, other desktops and Wayland can limit monitoring. The OS
must permit ordinary suspend for the sleep button. Do not change system
security policies just to run a test. Current Windows builds are not provided.
Android keeps its existing background locking. Its protection panel explains
the available device protection and has no desktop tests.

<a name="en-key-replacement"></a>

#### Signing in and replacing the key

Updating an existing installation keeps its PIN, including a PIN generated
by an older version. You do not need to reset access to use the update.
Three incorrect app PIN checks lock PIN entry for five minutes, or 300 seconds.
The first two failures show the attempts remaining. Sign-in and PIN confirmation
before creating a recovery code share this limit. A correct PIN cannot bypass
an active lockout. The countdown shows minutes and seconds and continues across
restart, sleep, backgrounding and language changes. Recovery and profile deletion
remain available. After the lockout ends, a new cycle of attempts is available.
An update preserves recorded failures and an active lockout.

To replace any saved OpenRouter API key, first sign in with your current app
PIN. Open `⋮` and choose `Replace OpenRouter key`. This action is available for
valid, invalid, restricted and unknown key status, with or without a selected
chat. It stays visible while a key check or send operation is running and
becomes available when that operation finishes or is cancelled.

You can cancel the confirmation and continue with your current key and draft.
If you confirm, enter another API key and check it. The saved key stays in
place until the new key passes validation and is saved. If checking or saving
fails, you can try again. Your app PIN, encryption key, conversations, drafts
and budgets stay the same. There is no new PIN setup. `Refresh key status`
remains a separate action and keeps the menu open. Replacing an API key does
not recover a forgotten PIN or revoke the previous key at OpenRouter.

<a name="en-paid-confirmation"></a>

#### Paid requests without confirmation

In a paid chat, use `Without confirmation` in the strip above the conversation.
It is available before the first message and starts off in new chats.
An existing chat keeps its saved choice after an update. Enabling it sends
nothing by itself. It allows requests
to be sent immediately and spend funds within the chat's current limits.

With it on, the first request, later requests and retries have no paid-request
warning, notification or confirmation dialog. Price changes also need no
separate paid-request confirmation. Current prices and the required reserve
are recalculated before sending. A request that fails key, budget or other
checks is not sent. Increasing the spending limit still requires its own
confirmation. The setting does not increase limits or hide actual errors.

Turn the checkbox off to require confirmation for the next request and every
later request. The choice is saved only for this chat and profile. It survives
language changes, locking, switching chats and restarting. If saving fails,
the checkbox returns to the saved choice and an error is shown.
Changing the choice, navigating or locking does not submit a queued request.
After unlocking, choose Send again when you are ready. Hover over or long-press
the checkbox for its explanation. The adjacent help button also opens it
from the keyboard without changing the setting.

<a name="en-chat-metrics"></a>

#### Chat metrics and the estimate while typing

Above a paid conversation, `Chat available` is the remaining spending
budget after actual costs and active reserves. `Last request` is the confirmed
cost of the latest sent attempt, including a retry of an older message.
`Key remaining` is visible directly in the paid-chat strip when the current
API key has a known positive remaining spending limit. It is a separate value
from the chat budget and the OpenRouter account balance.

`Key limit exhausted` shows zero or a negative remainder as exhausted.
A negative remainder does not add funds to the chat. Small positive amounts
remain distinct from zero. `Key limit not set` means that this key has no
separate spending limit. It is not an invalid key or an infinite account
balance. `Key data unavailable` means that a reliable remainder is unknown,
rather than a confirmed zero.

Hover over or long-press the key metric for its explanation and the actual
receipt time when known. Use the existing `Refresh key status` action to
refresh it. A failed background refresh can keep an older snapshot with its
original date. Redrawing the strip does not make those data fresh. Typing
uses the local estimate and does not refresh the key metadata.

A standard request key cannot use the documented management-key source for
account totals. Tokenlogue does not request a management key or derive an
account balance from usage or the chat budget. If no key limit is set, its
numeric remainder is unavailable by design. The tooltip explains this
distinction without keeping an account-balance warning in the main strip.

For free chats, `Tokens remaining` belongs to the chat budget, including active
reserves. `Last request` is its authoritative input-and-response total. It is
not the server's global free quota. New chats show `No requests`. A sent attempt
with unresolved accounting shows `Reconciling` or `Unknown`, rather than zero
or the previous attempt's cost. A local cancellation before sending keeps the
previous actual result. Older histories with unrecoverable dispatch order can
show `Unknown` until a new request is sent. Their messages and accounting stay
in place.

Under the editor, the estimate changes as you type, delete, paste or replace
text. It includes the same eligible history and effective response maximum
used by sending. Token counts are a conservative local UTF-8-based estimate,
not exact model tokenization. The response maximum and possible cost are upper
bounds for the known configuration, not predicted actual usage or a charge.
A free configuration can show $0. Incomplete or expired paid-model information
shows `Cost unknown`. Very small positive amounts remain distinct from zero.

The estimate makes no request, reserve or paid decision. It does not change
your budgets or confirmation setting. Real checks still run when you send.
An empty or oversized draft is not presented as a ready request. Changing
chats, locking or deleting a profile discards an old calculation.

When the keyboard or a short window leaves little room, the rename and delete
shortcuts and the bottom reminder are tucked away. Close the keyboard or make
the window taller to show them again. The editor stays in place while the
history and estimate use the available space.

<a name="en-pin-recovery"></a>

#### Recovering a PIN

Opening `Forgot PIN?` does not change your PIN. Locking the OS or suspending
cancels an unfinished recovery and clears entered values. Until the new PIN
has been saved, the previous PIN still works. Passing a device check only
lets you choose a new PIN and does not save it. A new PIN already saved before
the lock stays active when you return. Start a fresh recovery attempt if needed.

On Android 11 or later, `Forgot PIN?` starts a separate system check of the device PIN,
pattern or password. Supported biometrics may be offered as an alternative.
A fingerprint is not required. The device needs to have a supported screen
lock configured. Merely unlocking the screen does not complete this new check.
After successful verification, choose a new four-digit app PIN, repeat it
and select `Save new PIN`. `Suggest PIN` remains available. The workspace
stays closed until the new PIN is saved. Cancelling before that confirmation
keeps the previous PIN and conversations. If the system check fails or is
cancelled, sign in with your previous PIN or start a new check.

On Linux, save a recovery code before you forget your PIN. Current builds offer
one after the local-protection setup step is handled. In an existing unlocked profile, open `⋮` and
choose `Recovery code`. Enter your current app PIN again to issue or replace
it. You must be signed in to create a code.

The code has 32 Base32 characters shown in groups of four. Anyone who has it
can replace your app PIN. Save it separately in a password manager or on paper,
then enter that saved code to confirm. It is shown only on that screen.
The app does not copy it automatically. If you choose to copy it, a clipboard
manager may retain its own copy. Closing the screen hides the full code and
you cannot reveal that same code again. You can issue another after sign-in
and another app PIN confirmation.

A previous working code remains valid until you confirm its replacement.
Cancelling issuance or a failed save keeps the working code and app PIN.
A successfully replaced code stops working.

`Forgot PIN?` opens code entry as the main Linux method. It needs no
administrator rights, system policy or Linux password. Enter the code saved
for this profile. Uppercase and lowercase ASCII letters, ASCII spaces and
hyphens are accepted. The code must contain all 32 Base32 characters. Tabs,
line breaks, Unicode lookalikes and partial codes are not accepted. Failed
Five incorrect code checks cause a separate 30-second lockout, including
after restarting the app. This does not change the app PIN limit.

After the code is verified, choose and repeat a new four-digit PIN and select
`Save new PIN`. Conversations stay closed until saving completes. Cancelling
before the change is accepted keeps the working PIN and code. The saved new
PIN consumes the used code. It cannot recover the profile again. Save and
confirm the new code offered afterwards. If you close the app first, the new
PIN still works. Sign in with it and use `Recovery code` in `⋮` to issue another.

If a code was never issued for this profile, Tokenlogue explains that it
cannot create one while the profile is locked. You need the previous app PIN,
a previously issued code or a working trusted system recovery method.
Installing this update does not recover an already forgotten PIN retroactively.
Your data is kept. A new OpenRouter key, an unlocked keyring or an Android
profile from another device does not authorize opening the Linux conversations.

`Use Linux system recovery` remains a separate, explicitly selected
method. On Linux Mint 22.3 Cinnamon/X11 it uses a fresh polkit confirmation of
your own Linux account. Enter your Linux password only in that system prompt,
never into Tokenlogue. A different administrator account does not replace
confirmation of your account. It needs a separately installed Tokenlogue policy
and a working desktop agent. An unavailable or refused check keeps chats
closed and explains the failure. Code recovery does not require this setup.
See [the Linux guide](linux-appimage.md#en-current-protection) for this optional
method. Normal PIN sign-in remains available. Android 7–10 has no system recovery.

Keep your app PIN somewhere safe. Entering a valid OpenRouter key and choosing
another PIN cannot open an existing protected conversation database. Recovery
on either platform also needs the original protected encryption key. It cannot
recreate a missing key for data that is already encrypted. A recovery code is
an additional sign-in method, not a backup of the encryption key or database.

In current builds, `Rename` and `Delete chat`
appear directly below the selected chat's title, even when the menu is closed.
A name you save here stays unchanged after later messages and restarts.
Renaming preserves the conversation and draft. Deletion asks for confirmation
and removes only that chat's local history and draft. Key status, model
information and limits remain in `⋮`. The separate `Delete local profile` action
at the bottom removes the whole profile after confirmation.

<a name="en-delete"></a>

### Delete a local profile and start again

This action exists in current Linux and Android builds. It is separate from
PIN recovery and from `Replace OpenRouter key` after sign-in. Recovery keeps
conversations when you can provide an existing valid proof and the original
encryption key is available. Deletion gives up the selected local profile.
It does not read, decrypt or recover its old conversations.

After sign-in, open `⋮` and choose `Delete local profile` at the bottom of the
menu. It is available with a selected chat and with an empty workspace. If a
send or another dialog is active, finish or cancel it first. Cancelling deletion
returns to the same chat and keeps your saved draft. Refreshing the key status
does not replace the confirmation.

On the PIN screen, choose `Delete local profile`. It remains available during
a PIN lockout and when recovery codes or system recovery cannot be used.
The forgotten PIN, recovery code, Linux password, administrator rights and
network access are not required. The actions appear in this order:

1. `Sign in`.
2. `Delete local profile`.
3. `Forgot PIN?`.

Key replacement is available only after sign-in through `⋮`. Entering a new
API key is still part of setting up a newly created profile.

Confirm deletion separately:

1. Read the dialog about losing local conversations, access settings, limits
   and spending records.
2. To keep the profile, choose `Keep profile`. To proceed, enter the shown
   phrase `DELETE PROFILE` exactly, including its space.
3. Choose `Delete profile` only when you intend to give up
   this local history. An incorrect phrase does not enable that button.

For a supported existing Linux data folder, the dialog also explains that
Tokenlogue will make its own folder private before checking the profile again.
This uses the same confirmation and needs no administrator rights. Merely
opening or cancelling the dialog changes neither permissions nor profile data.
Shared folders, network storage and folders whose ownership cannot be safely
confirmed are refused. Do not change permissions or remove files manually.

If preparation or checking fails before data deletion, the message says that
deletion has not started and tells you how to retry or ask for help. If the
folder was already made private, it stays private and the profile is kept.
Return to the PIN screen and open a new confirmation. This state is different
from accepted deletion that still needs `Finish deletion`.

Anyone who can use this screen can confirm deletion. The phrase prevents an
accidental click and confirms intent. It does not establish identity or protect
against someone deliberately deleting the local profile.

Before deletion has been accepted, changing language, closing the dialog or
a system lock cancels the confirmation. An old dialog or a second click cannot
start another deletion. Once data deletion has started, it must finish. Closing the app
at that point does not turn a partly deleted profile into a new working one.
On restart Tokenlogue continues the accepted deletion. If storage cannot
complete or verify it, chats stay closed and new setup remains unavailable.
Choose `Finish deletion` to retry without the forgotten PIN.

After success, enter an API key again and choose a new PIN. You may save your
still-valid OpenRouter key again. Linux then offers a new recovery code to
save and confirm. The new profile has new registration and encryption keys,
an empty chat list and no old selected chat or draft. Former PINs, recovery
codes and unfinished recovery attempts cannot open or modify it. Language
and chat-panel layout choices are kept.

Only this profile's active local data and its associated keys are removed.
Other applications, external exports and backups remain in place. Physical
erasure of SSD blocks, swap, system snapshots or external copies is not
promised. This action does not revoke your key at OpenRouter, delete your
account or cancel requests already sent and their cost. It makes no remote
key-revocation request.

`Replace OpenRouter key` continues to require sign-in and keeps the PIN,
encryption key and conversations. Use the recovery route if you want to keep
old history. A newly entered API key alone cannot unlock that history.

<a name="en-workspace"></a>

### Language and chat panel in current builds

Choose `Русский / English` before signing in. The selector is also available
while choosing a PIN or when storage is unavailable. After signing in, open
`⋮` and change `Interface language`. Russian is used until you choose English.
Your choice is remembered after restarting, locking and updating the app or
replacing the OpenRouter key.

The new language applies immediately to the current screen and open dialogs.
Your typed PIN, chat title, limit values and draft remain in place. Switching
language does not repeat a key check or send a message. Messages, model
responses and your chat titles are not translated. The built-in label for
a new unnamed chat follows the interface language. Existing titles stay as
saved when their origin is uncertain. A title taken from your first message
also stays in its original language.

While issuing a recovery code or recovering a PIN on Linux, changing language
cancels the unfinished attempt. A language change also cancels an unconfirmed
profile-deletion dialog on either platform. Start again in the selected language.
A new PIN that has already been saved remains valid.

The button at the top left is always available. In a wide window it hides
or shows the chat list. With the list hidden, the conversation and editor
use the freed space. The app remembers the wide-window choice when you
switch chats, refresh key status, lock, sign in again or restart.

In a narrow window the same button opens a drawer. Select a chat, press
Escape or Back, or tap outside the drawer to close it. Switching language
keeps an explicitly opened drawer open. A narrow window does not change
your saved wide-window choice. That choice returns when the window becomes
wide again. The selected chat, reading position, draft and pending request
are preserved when you toggle the panel or language.

`Rename` and `Delete chat` remain below the selected title. The `+` and lock
buttons stay at the right, with `⋮` at the far right. On Linux, the compact
protection shield sits next to `⋮` and opens its protection details. If the menu
contains more information than fits on screen, scroll inside it.

<a name="en-chats"></a>

### Creating and managing chats

Choose `+` with the tooltip `Новый чат` (new chat). Select free or paid mode,
find a model by name or ID in `Поиск модели`, then configure the chat limits.
Paid mode includes a warning about possible charges.

Free mode offers automatic model selection through `openrouter/free` and
models whose applicable prices are all zero. Tokenlogue checks the prices
reported by OpenRouter, rather than relying on the model name or `:free` suffix.
Free requests are still subject to the service's availability and request limits.
Paid mode also requires a valid key and available model information.
OpenRouter checks your account balance when processing a paid request.

Each chat keeps its selected mode and model. To use another mode or model,
create another chat. The menu shows the model selected for the chat.
If you choose automatic model selection, this is the router's name.
OpenRouter then chooses the model that processes each request.

In a wide window, use the chat list on the left. In a narrow window, the
left header button `Открыть список чатов` opens that list. Select a chat to
restore its conversation and draft. A long chat title is shortened visually
in the header and remains available through its tooltip.

The `⋮` button, labelled `Параметры чата` (chat settings), is on the right
after the new-chat and lock buttons. Its scrollable panel opens over the
conversation. Activate the focused button with Enter or Space. Close the panel
with Escape, its close button or a click outside it.

| Menu area | What it contains |
| --- | --- |
| `Ключ OpenRouter` | Key status, known key limit and the actions available for that state. |
| `Чат` | Free or paid mode, model name and ID, and token prices for paid chats. |
| `Токены и бюджет` | Used, reserved and remaining tokens, response maximum, and costs for paid chats. |
| `Настроить лимиты` or `Изменить лимиты` | Configure or change the active chat's limits. |
| `Переименовать` | Change the active chat's title. |
| `Удалить чат` | Delete the active chat after confirmation. |

Opening or closing the menu does not send the draft or erase it. The editor
stays at the bottom. Renaming preserves the conversation and draft.
Deleting a chat removes its local history and draft. Cancel the confirmation
to keep it. Renaming, deletion and limit changes are disabled while sending.

<a name="en-drafts"></a>

### Sending messages and saving drafts

Type in `Сообщение` (message). Press Enter to send or use `Отправить` (send).
Shift+Enter inserts a new line. Empty or whitespace-only messages cannot be sent.
While a response is pending, the editor displays its waiting state.
In current builds, longer drafts scroll vertically inside the editor on narrow screens.

Each chat automatically saves its own draft locally. Switching chats,
resizing the window, renaming a chat and restarting restore the saved text,
including text in any language, spaces and line breaks. Drafts are separate from message
history. They are not sent as context and do not use tokens or money.

After Tokenlogue adds your message to the conversation and starts sending it,
the submitted draft is cleared. The reply may arrive later. If you begin a new
draft, completion of the previous request will not erase it. A failed check
before sending or a cancelled paid request leaves the original draft in place.

Sending transmits the message and conversation context to OpenRouter.
Long histories therefore affect both the input size and the budget needed for
the next request. View the response or request status in the conversation.

<a name="en-limits"></a>

### How token and spending limits work

Configure limits before the first send. Tokenlogue distinguishes these settings:

| Setting | Meaning |
| --- | --- |
| `Общий лимит токенов чата` | Total input and output token budget for the chat's requests. |
| `Максимум токенов одного ответа` | Maximum output tokens requested for the next response. |
| `Денежный лимит чата, USD` | Local spending cap for a paid chat. |

The total budget also accounts for conversation context sent again with later
messages. The response maximum sets an upper limit. The actual response can be shorter. Before sending, Tokenlogue reserves tokens and, for paid chats,
money. It can refuse a request when the available budget cannot cover that reserve.

Open `⋮` to see how much of the budget has been used, reserved or remains
available. Reserved amounts are set aside for requests that are still pending
or have an unknown result. They cannot be used for a new request until
released. An unknown cost is not treated as zero. A reservation is a local
budget limit, not a charge to your OpenRouter account. Check that account
for the service's actual billing records.

In the published preview, every paid request asks for confirmation with the
model and preliminary reserve. A price change requires another confirmation.
Current builds keep this default and offer the [per-chat setting](#en-paid-confirmation)
to send without paid-request confirmation. Increasing the chat's spending
limit still needs confirmation. Cancel the dialog to leave the request unsent or keep the previous limit.

#### If a request's result is unknown

If a connection fails after a request may have reached OpenRouter, Tokenlogue
keeps a protective reserve. The conversation shows that the result is unknown.
The service may still have processed and billed the request.

Check the request and usage in your OpenRouter account before sending again.
After checking the request, you can choose `Освободить резерв` (release reserve)
and confirm if you want to make that budget available again. It releases the local reservation. It does not
cancel a remote request or refund a charge. Retrying can create another charge.

<a name="en-data"></a>

### Data storage and access

In the published Linux preview `2b1f7d3`, chats, messages, drafts, budget state
and PIN verification data are stored in the local application database without
additional content encryption. The PIN is not stored as plain text, but it only restricts access
through Tokenlogue's interface. Someone with access to your OS account or
database files may be able to read the history and drafts.

The API key and registration identifier are stored separately in platform
SecureStorage. On Linux this requires a working Secret Service.
Resetting the key preserves chats and drafts, while deleting a chat removes
that chat's local content. Neither action deletes records held by OpenRouter
or a model provider. Replacing the AppImage file does not remove application data.


#### Local content protection in current builds

Current builds encrypt saved chat titles, user and model messages, and drafts.
The encryption key is randomly generated and kept separately in platform secure
storage. It is not derived from your four-digit app PIN or OpenRouter key.
Your PIN controls access to that key through Tokenlogue. On Linux, a working
Secret Service is required. If secure storage or the encryption key is
unavailable, the app keeps conversations closed rather than saving their
contents without protection.

On the first successful sign-in after updating older local data, Tokenlogue
protects the existing content before opening the chat workspace. History,
drafts and their revisions, chat IDs, model choices and financial accounting
are preserved. If the conversion cannot finish, the app reports an error and
keeps the data. Do not delete the database or reset device security to dismiss
that error.

If a temporary secure storage error interrupts the initial setup of protection,
try signing in again with your existing app PIN after storage becomes available.
Tokenlogue can finish a confirmed incomplete setup while keeping your data.
This does not recreate a lost key for conversations that are already encrypted.

On Linux, close all older Tokenlogue copies that use this data folder before
the first protected sign-in. Keep them closed during conversion and while using
the updated app. Current builds allow one process per data folder and ask a
second process to close the other copy. Older versions do not follow that rule.

This is encryption of selected content fields. Structural information remains
readable, including dates, model IDs, chat modes, token counts, budgets and
accounting status. It is not encryption of the whole SQLite database and is
not end-to-end encryption with OpenRouter. Sending still transmits the required
message content and context to OpenRouter and the chosen model provider.

Locking clears the visible workspace and blocks new access. A request already
sent may still finish and save its response and accounting in protected form.
This does not guarantee instant erasure of every plaintext or key copy from
a running process. It does not protect an already compromised operating system.

Protection applies to the app's current accessible files after conversion.
Older external copies and previously written flash or SSD blocks may retain
older content. Android application backup remains disabled. Copying the database
to another device does not transfer its protected key. Uninstalling the app,
resetting its data, losing secure storage or invalidating Android Keystore can
make protected history unrecoverable. Changes to device security can affect
key availability on some devices. A new app PIN or API key cannot recreate a
lost encryption key.

Tokenlogue is a client of the separate OpenRouter service and is not affiliated
with it. Review the service's and model provider's data terms before sending
private content.

[Back to Tokenlogue](../README.md#lang-en)

<a name="lang-ru"></a>

## Русский

Руководство описывает текущую [опубликованную предварительную сборку `0.1.0` версии `2b1f7d3`](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.2b1f7d3).
[Раздел о текущих исходниках](#ru-current) описывает новую настройку PIN,
системную блокировку и восстановление PIN в Linux, удаление локального профиля,
панель чатов и выбор языка.
Эти изменения не входят
в опубликованную сборку для Linux. Интерфейс на русском языке. Ниже используются
названия элементов, которые видны в приложении. Установка опубликованной
сборки описана в [руководстве по AppImage для Linux](linux-appimage.md#lang-ru).

[Ключ и PIN в сборке Linux](#ru-access) | [Текущие сборки](#ru-current) |
[Удаление локального профиля](#ru-delete) | [Панель и язык](#ru-workspace) |
[Чаты и меню](#ru-chats) | [Статистика и оценка](#ru-chat-metrics) |
[Сообщения и черновики](#ru-drafts) | [Лимиты](#ru-limits) | [Данные](#ru-data)

<a name="ru-access"></a>

### Первый запуск и вход в опубликованную сборку для Linux

При первом запуске введите свой ключ в поле `OpenRouter API-ключ` и нажмите
`Проверить ключ`. Получить ключ можно в своей учётной записи OpenRouter.
Для проверки нужен доступ к OpenRouter. Сетевая ошибка сама по себе не
означает, что ключ недействителен.

После успешной проверки Tokenlogue создаёт четырёхзначный PIN и показывает
его один раз. Сохраните все четыре цифры, включая начальный ноль, если он есть,
затем нажмите `Я сохранил PIN`. Ключ записывается в хранилище только после
этого подтверждения. При следующих запусках введите PIN и нажмите `Войти`.
После пяти неверных попыток вход блокируется на 30 секунд.

Кнопка блокировки в шапке возвращает на экран PIN. Если PIN забыт или нужно
сбросить доступ, нажмите на этом экране `Сбросить ключ` и подтвердите действие.
Сохранённый API-ключ, проверочные данные PIN и состояние блокировки будут
удалены. Существующие чаты и черновики останутся. При повторной настройке
нужно снова ввести ключ и сохранить новый PIN. Локальный сброс не отзывает
ключ в OpenRouter.

После входа откройте `⋮`, чтобы проверить состояние ключа. В меню видно, действителен ли ключ
и сколько средств осталось в его расходном лимите, если эти данные доступны.
В зависимости от состояния ключа можно выбрать `Повторить проверку ключа` или `Заменить ключ`.
Само открытие меню не проверяет ключ заново и не отправляет запрос модели.
Расходный лимит ключа отделён от локального лимита каждого чата.

<a name="ru-current"></a>

### Выбор PIN и блокировка в текущих сборках

Этот раздел относится к сборкам из текущих исходников, включая новые сборки
Android. В опубликованной версии для Linux `2b1f7d3` остаётся настройка,
описанная [выше](#ru-access).

После проверки ключа OpenRouter открывается экран `Выберите PIN` с пустым
полем `PIN`. Выберите ровно четыре цифры от `0` до `9`. Начальные нули
допустимы. Повторите значение в поле `Повторите PIN`. Пробелы, другие символы
и цифры из других систем письма не принимаются.

Кнопка `Предложить PIN` заполняет первое поле случайным значением. Его можно
изменить до сохранения. Любая правка первого поля или новое предложение
очищают поле повторного ввода, даже если предложенное число совпало
с предыдущим. Кнопка `Сохранить PIN` доступна только при совпадении двух
корректных значений и отсутствии текущей операции. Одно предложение PIN
не завершает настройку.

Оба поля скрывают содержимое. Кнопка с глазом позволяет показать PIN,
чтобы проверить его или сохранить в безопасном месте. Tokenlogue не копирует
его в буфер обмена автоматически. Проверенный ключ и проверочные данные PIN
сохраняются после подтверждения настройки. Если незавершённая настройка
в Android прервана переходом в фон, после возврата нужно снова ввести ключ
и выбрать PIN.

В Android переход Tokenlogue в фон блокирует доступ к чатам и закрывает
открытые диалоги. Возврат в приложение или разблокировка Android не открывают
Tokenlogue. Введите PIN, чтобы продолжить работу с выбранным чатом,
историей и черновиком. Открытие клавиатуры или краткая потеря фокуса сами
по себе не блокируют приложение. Кнопка блокировки в шапке остаётся доступной
на всех платформах.

В Linux Mint 22.3 Cinnamon/X11 включение экранной блокировки, смена сессии
или переход в сон закрывают переписку и отменяют незавершённое восстановление.
Последний черновик сохраняется. Уже отправленный запрос сохраняет резерв
и может завершить запись ответа и учёт расходов. Разблокировка рабочего стола
и возврат из сна не открывают чаты. Введите PIN приложения или начните новую
проверку восстановления. Сворачивание окна, смена фокуса и открытие запроса
polkit сами по себе не блокируют Tokenlogue.

<a name="ru-protection-check"></a>

#### Проверки локальной защиты

В Linux после сохранения проверенного ключа и выбранного PIN нового
защищённого профиля автоматически открывается `Проверка локальной защиты`
до перехода к чатам. Сохранённый PIN уже действует. Экран объясняет дальнейшие
действия и ждёт явного нажатия `Начать проверку`. Сохранение ключа или PIN
не блокирует ОС неожиданно. Выбранный чат и прежняя ручная блокировка
экрана для теста не нужны.

`Начать проверку` сначала подготавливает поддерживаемую экранную службу
рабочего стола. Ещё не запущенная служба не делает кнопку недоступной
навсегда. Подготовка ограничена по времени и показывает результат.
Если она не завершилась, прочитайте объяснение и повторите попытку.
Не меняйте настройки блокировки рабочего стола и не устанавливайте
системную policy только ради запуска проверки.

Затем ОС блокируется обычным экранным механизмом. Разблокируйте её обычным
способом и введите сохранённый PIN Tokenlogue. Повторно вводить API-ключ
или создавать профиль не нужно. Подтверждённый результат относится к тому
же тесту и остаётся видимым после входа. Нажмите `Перейти к чатам`, чтобы
завершить шаг. После него предлагается создание резервного кода,
которое можно отложить. Замена существующего ключа не повторяет этот шаг.

Если приложение перезапущено до завершения шага, войдите с сохранённым PIN
и продолжите его. Можно выбрать `Продолжить с ручной блокировкой`.
Результат остаётся явно неподтверждённым, а профиль доступен для обычной
работы. Пока экранная проверка не подтверждена, блокируйте Tokenlogue
вручную. Отметка завершения шага хранится отдельно от истории проверок.

Щит крайним справа в шапке экрана PIN открывает ту же панель
`Локальная защита`, что и щит в чате. Выбор языка остаётся в шапке.
Постоянной строки защиты под инструкцией PIN больше нет. Открытие панели
сохраняет уже введённые цифры, не открывает переписку и не запрашивает
действие ОС.

Выберите `Тест блокировки` или `Тест перехода в сон` на закрытом экране,
чтобы продолжить обычный вход по PIN. Неверный PIN и действующий отсчёт
по-прежнему учитываются. Выбор можно отменить в форме PIN либо вновь
открыть и закрыть панель. После успешного входа у выбранной проверки
появляется явная кнопка `Начать тест`. Один ввод PIN не блокирует
и не усыпляет ОС. Выбор истекает и отменяется при восстановлении, удалении,
новой системной блокировке или перезапуске. При необходимости выберите
тест заново.

В открытом профиле щит рядом с крайним правым `⋮` сразу открывает
`Локальная защита`. Меню также открывает эту же панель. `Тест блокировки` доступен при пустом
списке чатов и в новой сессии рабочего стола до первой блокировки экрана. Он использует ту же проверку,
что и шаг настройки, сохраняет текущий черновик и ждёт явного действия.
Короткая конфликтующая операция или другая выполняющаяся проверка временно
занимает управление. Завершите эту операцию и повторите попытку.

Экранная блокировка и сон имеют отдельную историю со временем последних
завершённых проверок. Зелёный результат означает подтверждение настоящего
цикла ОС и штатной защиты Tokenlogue. Экранная проверка не подтверждает сон.
Проверка одного механизма сохраняет результат другого.

`Тест перехода в сон` доступен рядом с `Тест блокировки` после входа,
в том числе при пустом списке чатов. Перед нажатием прочитайте объяснение.
Компьютер перейдёт в сон. Сначала сохранится черновик. Пробудите компьютер,
разблокируйте ОС обычным способом и введите PIN приложения. Разблокировка
ОС не открывает Tokenlogue автоматически и не отправляет черновик.
Предварительная экранная проверка не нужна. Оба теста не выполняются
одновременно. Открытие меню и сохранение регистрации не запускают сон.
Обычный сон из меню ОС по-прежнему защищает приложение и не стирает
результат экранной проверки.

Результаты сохраняются при перезапуске Tokenlogue, перезагрузке этого
устройства, обычном сне, входе по PIN, смене языка и перестроении меню.
Временное переподключение показывает прежнюю проверку отдельно от
предупреждения о текущем наблюдении. После восстановления доверенного
совместимого наблюдения сохранённое подтверждение снова становится
актуальным без нового ручного теста. Изменение контракта защиты или
неподдерживаемая экранная служба могут потребовать новой проверки.
Другой компьютер или учётная запись ОС имеют свою историю. Копирование
профиля чатов или предпочтений не переносит подтверждение устройства.
История защиты не входит в экспорт чатов. Удаление профиля чатов оставляет
историю устройства на месте.

Отказ запроса, отмена или попытка без доказанного сна не создают новый
успех и не стирают прежнюю проверку. Настоящий отказ отмечается красным
только у соответствующего механизма. Время его прежнего успеха остаётся
в подробностях. Аварийное закрытие защищает данные, но не делает тест
успешным. Ошибка записи означает, что текущий результат может быть верным,
но не запомнен для следующего запуска. Прежняя зелёная история не доказывает
работу недоступного наблюдения сейчас. Пока предупреждение остаётся,
блокируйте приложение вручную.

Используйте один активный локальный Cinnamon/X11 desktop и один экран.
Дополнительные экраны, неоднозначная сессия, другие рабочие столы и Wayland
могут ограничивать наблюдение. Для кнопки сна ОС должна разрешать обычный
suspend. Не меняйте системные политики безопасности ради теста.
Сборки Windows сейчас не предоставляются. Android сохраняет прежнюю
блокировку при переходе в фон. Его панель объясняет доступную защиту
устройства и не содержит desktop-тестов.

<a name="ru-key-replacement"></a>

#### Вход и замена ключа

Обновление установленного приложения сохраняет прежний PIN, в том числе
созданный старой версией. Для использования обновления не нужен сброс доступа.
Три неверные проверки PIN приложения блокируют ввод на пять минут, или
300 секунд. Первые две ошибки показывают остаток попыток. Вход и подтверждение
PIN перед созданием резервного кода используют общее ограничение. Правильный
PIN не обходит действующую блокировку. Отсчёт в минутах и секундах продолжается
после перезапуска, сна, перехода в фон и смены языка. Восстановление и удаление
профиля остаются доступными. После окончания срока доступен новый цикл попыток.
Обновление сохраняет записанные ошибки и действующую блокировку.

Чтобы заменить любой сохранённый API-ключ OpenRouter, сначала войдите
с действующим PIN приложения. Откройте `⋮` и выберите `Заменить ключ OpenRouter`.
Действие доступно при действительном, недействительном, ограниченном
и неизвестном статусе ключа, в том числе без выбранного чата. Во время проверки
ключа или отправки оно остаётся видимым и становится доступным после
завершения или отмены операции.

Можно отменить подтверждение и продолжить работу с текущим ключом и черновиком.
Если подтвердите замену, введите другой API-ключ и проверьте его. Сохранённый
ключ останется на месте до успешной проверки и сохранения нового. Если
проверка или сохранение не удались, можно повторить попытку. PIN приложения,
ключ шифрования, переписка, черновики и бюджеты сохранятся. Заново выбирать
PIN не нужно. `Обновить статус ключа` остаётся отдельным действием и оставляет
меню открытым. Замена API-ключа не восстанавливает забытый PIN и не отзывает
прежний ключ в OpenRouter.

<a name="ru-paid-confirmation"></a>

#### Платные запросы без подтверждения

В платном чате используйте `Без подтверждений` в полосе над перепиской.
Настройка доступна до первого сообщения и изначально выключена в новых чатах.
Прежний чат сохраняет свой выбор после обновления. Само включение ничего
не отправляет. Оно разрешает отправлять запросы сразу
и расходовать средства в пределах текущих лимитов этого чата.

При включении первый запрос, следующие запросы и повторы проходят без
предупреждения, уведомления или диалога подтверждения платного запроса.
Изменение цены также не требует отдельного подтверждения платного запроса.
До отправки пересчитываются текущие цены и необходимый резерв. Запрос,
не прошедший проверку ключа, бюджета или другие проверки, не отправляется.
Увеличение денежного лимита по-прежнему требует отдельного подтверждения.
Настройка не повышает лимиты и не скрывает действительные ошибки.

Снимите флажок, чтобы вернуть подтверждение для следующего и каждого
последующего запроса. Выбор сохраняется только для этого чата и профиля.
Он переживает смену языка, блокировку, переход в другой чат и перезапуск.
При ошибке записи флажок возвращается к сохранённому выбору и показывается
ошибка. Смена выбора, переход или блокировка не отправляют ожидавший запрос.
После разблокировки снова выберите отправку, когда будете готовы. Подсказка
доступна при наведении или долгом нажатии на флажок. Соседняя кнопка справки
открывает пояснение с клавиатуры без изменения настройки.

<a name="ru-chat-metrics"></a>

#### Статистика чата и оценка во время ввода

Над платной перепиской `В чате доступно` показывает остаток денежного бюджета
после фактических расходов и активных резервов. `Последний запрос` показывает
подтверждённую стоимость последней отправленной попытки, включая повтор
старого сообщения. `Осталось по ключу` видно прямо в полосе платного чата,
когда известен положительный остаток расходного лимита текущего API-ключа.
Это отдельное значение от бюджета чата и баланса OpenRouter.

`Лимит ключа исчерпан` показывает нулевой или отрицательный остаток
как исчерпанный. Отрицательный остаток не добавляет средства чату.
Малые положительные суммы отличаются от нуля. `Лимит ключа не установлен`
означает отсутствие отдельного расходного лимита этого ключа. Это не ошибка
ключа и не бесконечный баланс аккаунта. `Данные ключа недоступны` означает,
что надёжный остаток неизвестен, а не подтверждённый ноль.

Наведите указатель на метрику ключа или нажмите её длительно, чтобы увидеть
пояснение и время фактического получения, когда оно известно. Для обновления
используйте прежнее действие `Обновить статус ключа`. После ошибки фонового
обновления может остаться более старый снимок с прежней датой. Перерисовка
полосы не делает эти данные свежими. Ввод текста использует локальную оценку
и не обновляет метаданные ключа.

Обычный ключ запросов не даёт доступа к документированному источнику итоговых
средств аккаунта с управленческим ключом. Tokenlogue не просит такой ключ
и не вычисляет баланс аккаунта из расходов или бюджета чата. Если отдельный
лимит ключа не задан, остаток этого лимита не определён. Подсказка объясняет
это различие без постоянного предупреждения о балансе аккаунта в полосе.

В бесплатном чате `Осталось токенов` относится к бюджету чата с активными
резервами. `Последний запрос` показывает итог токенов входа и ответа.
Это не общая серверная квота бесплатных запросов. В новых чатах указано
`Нет запросов`. Отправленная попытка с неуточнённым учётом показывает
`Уточняется` или `Неизвестно`, а не ноль или стоимость прежней попытки.
Локальная отмена до отправки сохраняет прежний фактический результат.
В старой истории с невосстановимым порядком отправок возможно `Неизвестно`
до новой отправки. Прежние сообщения и учёт остаются на месте.

Под редактором оценка меняется при вводе, удалении, вставке или замене текста.
Она учитывает ту же подходящую историю и эффективный максимум ответа,
что и отправка. Токены оцениваются консервативно по UTF-8, без точной
токенизации модели. Максимум ответа и возможная стоимость являются верхней
оценкой известной конфигурации, а не предсказанием расхода или списанием.
Бесплатная конфигурация может показывать $0. При неполных или устаревших
данных платной модели указано `Стоимость неизвестна`. Очень маленькие
положительные суммы отличаются от нуля.

Оценка не делает запросов, не создаёт резервов и не принимает платных решений.
Она не меняет бюджеты или настройку подтверждений. Настоящие проверки
выполняются при отправке. Пустой или слишком длинный черновик не показан
как готовый запрос. Переход в другой чат, блокировка или удаление профиля
отбрасывают прежний расчёт.

Когда клавиатура или низкое окно оставляют мало места, кнопки переименования
и удаления и нижняя памятка временно скрываются. Закройте клавиатуру или
увеличьте высоту окна, чтобы вернуть их. Редактор остаётся на месте,
а переписка и оценка используют доступное пространство.

<a name="ru-pin-recovery"></a>

#### Восстановление PIN

Нажатие `Забыли PIN?` не меняет PIN. Блокировка ОС или сон отменяют
незавершённое восстановление и очищают введённые значения. До сохранения
нового PIN прежний продолжает работать. Успешная системная проверка разрешает
выбрать новый PIN, но сама его не сохраняет. Если новый уже сохранился
до блокировки, после возврата действует он. При необходимости начните
новую попытку восстановления.

В Android 11 или новее кнопка `Забыли PIN?` запускает отдельную системную проверку PIN,
графического ключа или пароля устройства. Поддерживаемая биометрия может
предлагаться как другой способ. Отпечаток пальца не обязателен. На устройстве
должна быть настроена поддерживаемая блокировка экрана. Обычная разблокировка
экрана не завершает эту новую проверку. После успешного подтверждения выберите
новый четырёхзначный PIN приложения, повторите его и нажмите
`Сохранить новый PIN`. Кнопка `Предложить PIN` остаётся доступной.
Переписка закрыта до сохранения нового PIN. Отмена до этого подтверждения
сохраняет прежний PIN и переписку. Если системная проверка не прошла или
отменена, войдите с прежним PIN либо начните новую проверку.

В Linux сохраните резервный код до потери PIN. Текущие сборки предлагают его
после завершения шага локальной защиты. В существующем открытом профиле откройте `⋮`
и выберите `Резервный код`. Повторно введите действующий PIN приложения
для выдачи или перевыпуска. Для создания кода нужно войти в приложение.

Код состоит из 32 символов Base32, показанных группами по четыре. Обладающий
им сможет заменить PIN приложения. Сохраните код отдельно в менеджере
паролей или на бумаге, затем подтвердите сохранение повторным вводом. Он
показывается только на этом экране. Приложение не копирует его автоматически.
Если вы решите скопировать код, менеджер буфера обмена может сохранить свою
копию. Закрытие экрана скрывает полный код. Показать тот же код заново нельзя.
После входа и нового подтверждения PIN приложения можно выпустить другой.

Прежний действующий код сохраняется до подтверждения замены. Отмена выдачи
или ошибка сохранения оставляют действующий код и PIN приложения.
Успешно заменённый код перестаёт работать.

Кнопка `Забыли PIN?` открывает ввод кода как основной способ в Linux. Права
администратора, системная policy и пароль Linux не нужны. Введите код,
сохранённый для этого профиля. Допустимы заглавные и строчные ASCII-буквы,
ASCII-пробелы и дефисы. Код должен содержать все 32 символа Base32.
Табуляция, переносы строк, похожие Unicode-символы и неполные коды не
принимаются. Пять неверных проверок кода включают отдельную блокировку
на 30 секунд, в том числе после перезапуска приложения. Это не меняет
ограничение PIN приложения.

После проверки кода выберите и повторите новый четырёхзначный PIN, затем
нажмите `Сохранить новый PIN`. Переписка закрыта до завершения сохранения.
Отмена до принятия изменения сохраняет действующий PIN и код. Сохранение
нового PIN погашает использованный код. Восстановить профиль им ещё раз нельзя.
Сохраните и подтвердите новый код, предложенный затем. Если закрыть приложение
раньше, новый PIN продолжит работать. Войдите с ним и выпустите другой код
через `Резервный код` в `⋮`.

Если код для этого профиля никогда не выдавался, Tokenlogue объяснит, что
создать его при закрытом профиле нельзя. Нужен прежний PIN приложения,
заранее выданный код или работающий доверенный системный способ восстановления.
Установка обновления не восстанавливает уже забытый PIN задним числом.
Данные сохраняются. Новый ключ OpenRouter, разблокированная связка ключей
и профиль Android с другого устройства не разрешают открыть переписку Linux.

Действие `Системное восстановление Linux` остаётся отдельным
явно выбранным способом. В Linux Mint 22.3 Cinnamon/X11 оно запрашивает новое
подтверждение собственной учётной записи Linux через polkit. Вводите пароль
Linux только в системном окне, а не в Tokenlogue. Другая учётная запись
администратора не заменяет подтверждение вашей записи. Нужны отдельно
установленная policy Tokenlogue и работающий агент рабочего стола. Недоступная
или отклонённая проверка оставляет чаты закрытыми с объяснением. Для кода
эта настройка не нужна. Дополнительный способ описан в
[руководстве Linux](linux-appimage.md#ru-current-protection).
Обычный вход по PIN остаётся доступным. В Android 7–10 системного восстановления нет.

Сохраните PIN приложения в надёжном месте. Ввод действительного ключа
OpenRouter и выбор другого PIN не открывают существующую защищённую базу
переписки. На обеих платформах для восстановления нужен прежний защищённый
ключ шифрования. Создать заново потерянный ключ уже зашифрованных данных нельзя. Резервный код
даёт дополнительный способ входа, а не копию ключа шифрования или базы.

В текущих сборках кнопки `Переименовать` и `Удалить чат` находятся прямо
под названием выбранного чата и видны при закрытом меню. Сохранённое здесь
название не меняется после новых сообщений и перезапуска. Переименование
сохраняет переписку и черновик. Удаление требует подтверждения и убирает
только локальную историю и черновик этого чата. Состояние ключа, сведения
о модели и лимиты остаются в `⋮`. Отдельное действие
`Удалить локальный профиль` внизу меню после подтверждения удаляет весь профиль.

<a name="ru-delete"></a>

### Удаление локального профиля и начало заново

Это действие есть в текущих сборках Linux и Android. Оно отделено от
восстановления PIN и от `Заменить ключ OpenRouter` после входа.
Восстановление сохраняет переписку при действующем подтверждении и доступном
прежнем ключе шифрования. Удаление означает отказ от выбранного локального
профиля. Оно не читает, не расшифровывает и не восстанавливает прежние чаты.

После входа откройте `⋮` и выберите `Удалить локальный профиль` внизу меню.
Действие доступно с выбранным чатом и при пустой переписке. Если выполняется
отправка или открыт другой диалог, сначала завершите или отмените его. Отмена
удаления возвращает тот же чат с сохранённым черновиком. Обновление статуса
ключа не заменяет подтверждение.

На экране PIN выберите `Удалить локальный профиль`. Действие остаётся
доступным при временной блокировке ввода PIN и недоступности резервного кода
или системного восстановления. Забытый PIN, резервный код, пароль Linux,
права администратора и сеть не нужны. Действия расположены в таком порядке:

1. `Войти`.
2. `Удалить локальный профиль`.
3. `Забыли PIN?`.

Замена ключа доступна только после входа через `⋮`. Ввод API-ключа остаётся
частью первоначальной настройки нового профиля.

Подтвердите удаление отдельно:

1. Прочитайте предупреждение о потере локальной переписки, настроек доступа,
   лимитов и учёта расходов.
2. Чтобы сохранить профиль, нажмите `Сохранить профиль`. Для продолжения
   введите показанную фразу `УДАЛИТЬ ПРОФИЛЬ` точно, включая пробел.
3. Нажмите `Удалить профиль` только при намерении отказаться
   от этой локальной истории. Неверная фраза не включает эту кнопку.

Для поддерживаемого существующего каталога данных Linux диалог также
объясняет, что Tokenlogue ограничит доступ к своему каталогу перед повторной
проверкой профиля. Используется то же подтверждение без прав администратора.
Открытие и отмена диалога не меняют ни права, ни данные профиля. Общие каталоги,
сетевые хранилища и каталоги без безопасно подтверждённого владения отклоняются.
Не меняйте права и не удаляйте файлы вручную.

Если подготовка или проверка отказала до удаления данных, сообщение говорит,
что удаление не началось, и подсказывает повторную попытку или обращение
за помощью. Если доступ к каталогу уже ограничен, он останется таким,
а профиль сохранится. Вернитесь к экрану PIN и откройте новое подтверждение.
Это отличается от принятого удаления, для которого нужно действие
`Завершить удаление`.

Подтвердить удаление может любой с доступом к этому экрану. Фраза защищает
от случайного нажатия и подтверждает намерение. Она не устанавливает личность
и не защищает от человека, намеренно удаляющего локальный профиль.

До принятия удаления смена языка, закрытие диалога или системная блокировка
отменяют подтверждение. Старый диалог и повторное нажатие не запускают вторую
операцию. После начала удаления данных его нужно завершить. Закрытие приложения
в этот момент не превращает частично удалённый профиль в новый рабочий.
После перезапуска Tokenlogue продолжает принятое удаление. Если хранилище
не позволяет его завершить или проверить, чаты остаются закрытыми, а новая
настройка недоступна. Нажмите `Завершить удаление`, чтобы повторить
без забытого PIN.

После успеха снова введите API-ключ и выберите новый PIN. Можно заново
сохранить прежний действующий ключ OpenRouter. В Linux затем предлагается
сохранить и подтвердить новый резервный код. У нового профиля новые
регистрация и ключи шифрования, пустой список чатов и нет прежнего выбранного
чата или черновика. Старые PIN, резервные коды и незавершённые попытки
восстановления его не открывают и не меняют. Язык и расположение панели
чатов сохраняются.

Удаляются только активные локальные данные этого профиля и связанные с ним
ключи. Другие приложения, внешние экспорты и резервные копии остаются
на месте. Физическое стирание блоков SSD, swap, снимков системы и внешних
копий не обещается. Действие не отзывает ключ в OpenRouter, не удаляет аккаунт
и не отменяет уже отправленные запросы или их стоимость. Удалённый запрос
отзыва ключа не выполняется.

`Заменить ключ OpenRouter` по-прежнему требует входа и сохраняет PIN,
ключ шифрования и переписку. Если хотите сохранить историю, используйте
восстановление. Одного нового API-ключа недостаточно для её открытия.

<a name="ru-workspace"></a>

### Язык и панель чатов в текущих сборках

Выберите `Русский / English` до входа. Переключатель также доступен при выборе
PIN и на экране недоступного хранилища. После входа откройте `⋮` и измените
`Язык интерфейса`. Пока вы не выбрали английский, используется русский.
Выбор сохраняется после перезапуска, блокировки, обновления приложения
и замены ключа OpenRouter.

Новый язык сразу применяется к текущему экрану и открытым диалогам.
Введённый PIN, название чата, значения лимитов и черновик остаются на месте.
Смена языка не повторяет проверку ключа и не отправляет сообщение.
Сообщения, ответы модели и ваши названия чатов не переводятся. Служебная
подпись нового чата без названия следует языку интерфейса. Старые названия
сохраняются как записаны, если их происхождение неизвестно. Название,
полученное из первого сообщения, также остаётся на исходном языке.

При выдаче резервного кода или восстановлении PIN в Linux смена языка
отменяет незавершённую попытку. На обеих платформах смена языка также отменяет
неподтверждённый диалог удаления профиля. Начните заново на выбранном языке.
Уже сохранённый новый PIN остаётся действительным.

Кнопка слева в шапке доступна постоянно. В широком окне она скрывает
и показывает список чатов. Когда список скрыт, переписка и редактор
занимают освободившееся место. Приложение запоминает выбор для широкого
окна при смене чата, обновлении состояния ключа, блокировке, повторном
входе и перезапуске.

В узком окне та же кнопка открывает выдвижную панель. Выберите чат,
нажмите Escape или Back либо коснитесь области за панелью, чтобы закрыть её.
Смена языка сохраняет явно открытую панель. Узкое окно не меняет
сохранённый выбор для широкого режима. Этот выбор возвращается,
когда окно снова становится широким. Выбранный чат, позиция чтения,
черновик и текущая отправка сохраняются при переключении панели и языка.

`Переименовать` и `Удалить чат` остаются под выбранным названием.
Кнопки `+` и блокировки находятся справа, а `⋮` занимает крайнее правое
место. В Linux рядом с `⋮` расположен компактный щит, открывающий подробности
защиты. Если сведения меню не помещаются на экран, прокрутите его.

<a name="ru-chats"></a>

### Создание чатов и управление ими

Нажмите `+` с подсказкой `Новый чат`. Выберите бесплатный или платный режим,
найдите модель по названию или ID в поле `Поиск модели`, затем настройте
лимиты чата. При выборе платного режима показывается предупреждение о расходах.

В бесплатном режиме доступны автоматический выбор модели через
`openrouter/free` и модели с нулевой стоимостью всех применимых услуг.
Tokenlogue проверяет цены, полученные от OpenRouter. Одного названия модели
или суффикса `:free` для этого недостаточно. Бесплатные запросы также зависят
от доступности сервиса и ограничений на число запросов. Для платного режима
нужны действующий ключ и сведения о моделях. OpenRouter проверяет баланс
вашей учётной записи при обработке платного запроса.

Чат сохраняет выбранные режим и модель. Для другого режима или модели
создайте новый чат. В меню указана выбранная для чата модель.
При автоматическом выборе здесь отображается название маршрутизатора.
Модель для обработки каждого запроса в этом случае выбирает OpenRouter.

В широком окне список чатов находится слева. В узком окне он открывается
левой кнопкой шапки с подсказкой `Открыть список чатов`. Выберите чат, чтобы
восстановить его переписку и черновик. Длинное название сокращается в шапке
только визуально и остаётся доступным во всплывающей подсказке.

Кнопка `⋮` с подсказкой `Параметры чата` находится справа после кнопок
нового чата и блокировки. Прокручиваемая панель открывается поверх переписки.
Кнопку в фокусе можно активировать клавишей Enter или Space. Закрыть панель
можно по Escape, кнопкой закрытия или нажатием вне панели.

| Область меню | Содержимое |
| --- | --- |
| `Ключ OpenRouter` | Состояние ключа, известный лимит ключа и доступные при этом состоянии действия. |
| `Чат` | Бесплатный или платный режим, название и ID модели, цены токенов для платного чата. |
| `Токены и бюджет` | Использованные, зарезервированные и оставшиеся токены, максимум ответа, расходы платного чата. |
| `Настроить лимиты` или `Изменить лимиты` | Настройка или изменение лимитов активного чата. |
| `Переименовать` | Изменение названия активного чата. |
| `Удалить чат` | Удаление активного чата после подтверждения. |

Открытие и закрытие меню не отправляют и не стирают черновик. Редактор остаётся
внизу. Переименование сохраняет переписку и черновик. При удалении чата
удаляются его локальная история и черновик. Отмените подтверждение, чтобы
сохранить чат. Во время отправки переименование, удаление и изменение лимитов
недоступны.

<a name="ru-drafts"></a>

### Отправка сообщений и сохранение черновиков

Введите текст в поле `Сообщение`. Для отправки нажмите Enter или кнопку
`Отправить`. Shift+Enter добавляет перенос строки. Пустое сообщение или
сообщение только из пробелов отправить нельзя. Пока ответ не получен,
редактор показывает состояние ожидания.
В текущих сборках на узком экране длинный черновик можно прокручивать вверх и вниз внутри редактора.

Каждый чат автоматически сохраняет свой черновик локально. При переключении
чатов, изменении размера окна, переименовании и перезапуске восстанавливается
сохранённый текст на любом языке, включая пробелы и переносы строк. Черновики
отделены от истории сообщений. Они не передаются в контекст и не расходуют
токены или деньги.

Когда Tokenlogue добавляет ваше сообщение в переписку и начинает отправку,
отправленный черновик очищается. Ответ может прийти позже. Если вы начнёте
новый черновик, завершение предыдущего запроса его не сотрёт. Если проверка
перед отправкой завершится ошибкой или вы отмените платный запрос, исходный
черновик останется в поле ввода.

Отправка передаёт сообщение и контекст переписки в OpenRouter. Поэтому длинная
история влияет и на объём входных данных, и на бюджет следующего запроса.
Ответ или состояние запроса отображается в переписке.

<a name="ru-limits"></a>

### Как работают лимиты токенов и расходов

Настройте лимиты до первой отправки. В Tokenlogue различаются следующие параметры:

| Параметр | Значение |
| --- | --- |
| `Общий лимит токенов чата` | Общий бюджет входных и выходных токенов всех запросов чата. |
| `Максимум токенов одного ответа` | Максимум выходных токенов, запрашиваемых для следующего ответа. |
| `Денежный лимит чата, USD` | Локальный предел расходов платного чата. |

Общий бюджет учитывает и контекст переписки, который повторно передаётся
со следующими сообщениями. Максимум ответа задаёт верхнюю границу.
Сам ответ может быть короче. До отправки Tokenlogue резервирует токены, а
в платном чате также деньги. Если доступного бюджета недостаточно для резерва,
запрос может быть отклонён.

Откройте `⋮`, чтобы узнать, сколько бюджета использовано, зарезервировано
и осталось. Резерв удерживается для запросов, которые ещё выполняются или
имеют неизвестный результат. Пока резерв не освобождён, его нельзя использовать
для нового запроса. Неизвестный расход не считается нулевым. Резерв ограничивает
доступный бюджет в приложении и сам по себе не списывает деньги с учётной записи
OpenRouter. Фактические списания проверяйте в этой учётной записи.

В опубликованной сборке перед каждым платным запросом показывается
подтверждение с моделью и предварительным резервом. При изменении цен нужно
ещё одно подтверждение. Текущие сборки сохраняют это поведение по умолчанию и предлагают
[настройку конкретного чата](#ru-paid-confirmation) для отправки без таких
подтверждений. Увеличение денежного лимита по-прежнему требует подтверждения. Если отменить диалог, запрос не будет отправлен или прежний лимит останется
без изменений.

#### Если результат запроса неизвестен

Если соединение прервалось после возможного получения запроса OpenRouter,
Tokenlogue сохраняет защитный резерв. В переписке появляется сообщение
о неизвестном результате. Сервис мог обработать и тарифицировать запрос.

Перед повторной отправкой проверьте запрос и расход в своём аккаунте OpenRouter.
После проверки можно нажать `Освободить резерв` и подтвердить действие,
если вы хотите снова использовать эту часть бюджета. Оно снимает локальный резерв, но не отменяет
удалённый запрос и не возвращает списанные средства. Повторная отправка
может привести к ещё одному списанию.

<a name="ru-data"></a>

### Хранение данных и защита доступа

В опубликованной сборке для Linux `2b1f7d3` чаты, сообщения, черновики,
состояние бюджета и проверочные данные PIN хранятся в локальной базе
приложения без дополнительного шифрования содержимого. PIN не хранится открытым текстом, но ограничивает только доступ
через интерфейс Tokenlogue. Человек с доступом к вашей учётной записи ОС
или файлам базы может прочитать историю и черновики.

API-ключ и идентификатор регистрации хранятся отдельно в платформенном
SecureStorage. В Linux для этого нужен работающий Secret Service.
Сброс ключа сохраняет чаты и черновики, а удаление чата стирает его локальное
содержимое. Оба действия не удаляют записи у OpenRouter или поставщика
модели. Замена файла AppImage не удаляет данные приложения.


#### Защита локального содержимого в текущих сборках

Текущие сборки шифруют сохранённые названия чатов, сообщения пользователя
и модели, а также черновики. Ключ шифрования создаётся случайно и хранится
отдельно в платформенном защищённом хранилище. Он не выводится из
четырёхзначного PIN приложения или ключа OpenRouter. PIN управляет доступом
к этому ключу через Tokenlogue. В Linux нужен работающий Secret Service.
Если защищённое хранилище или ключ шифрования недоступны, приложение оставляет
переписку закрытой и не сохраняет её содержимое без защиты.

При первом успешном входе после обновления прежних локальных данных
Tokenlogue защищает существующее содержимое до открытия рабочего
пространства. История, черновики и их ревизии, ID чатов, выбор моделей
и финансовый учёт сохраняются. Если преобразование не удалось завершить,
приложение сообщает об ошибке и сохраняет данные. Не удаляйте базу и
не сбрасывайте защиту устройства, чтобы убрать это сообщение.

Если временная ошибка защищённого хранилища прервала первоначальную настройку
защиты, после восстановления хранилища повторите вход с прежним PIN приложения.
Tokenlogue может завершить подтверждённую незавершённую настройку с сохранением
данных. Это не создаёт заново потерянный ключ уже зашифрованной переписки.

В Linux перед первым входом с защитой переписки закройте все прежние копии
Tokenlogue, использующие этот каталог данных. Оставьте их закрытыми во время
преобразования и работы с обновлённым приложением. Текущие сборки допускают один
процесс на каталог данных и предлагают второй копии закрыть другую.
Прежние версии это правило не соблюдают.

Шифруются отдельные поля содержимого. Структурные сведения остаются
читаемыми, включая даты, ID моделей, режимы чатов, количество токенов,
бюджеты и состояния учёта. Это не шифрование всей базы SQLite и не сквозное
шифрование с OpenRouter. При отправке нужные сообщения и контекст по-прежнему
передаются в OpenRouter и выбранному поставщику модели.

Блокировка очищает видимое рабочее пространство и закрывает новый доступ.
Уже отправленный запрос может завершиться и сохранить ответ и учёт расходов
в защищённом виде. Это не гарантирует мгновенного удаления каждой копии
открытого текста и ключа из памяти работающего процесса. Защита не рассчитана
на уже скомпрометированную операционную систему.

После преобразования защита относится к текущим доступным файлам приложения.
Прежние внешние копии и ранее записанные блоки flash или SSD могут сохранять
старое содержимое. Резервное копирование приложения в Android остаётся
отключённым. Копирование базы на другое устройство не переносит защищённый
ключ. Удаление приложения, сброс его данных, потеря защищённого хранилища
или признание ключей Android Keystore недействительными могут сделать
переписку невосстановимой.
Изменение защиты устройства на некоторых устройствах влияет на доступность
ключа. Новый PIN приложения или API-ключ не создают заново потерянный
ключ шифрования.

Tokenlogue разрабатывается независимо от OpenRouter.
Перед отправкой личных сведений ознакомьтесь с условиями обработки данных
сервиса и поставщика модели.

[К Tokenlogue](../README.md#lang-ru)
