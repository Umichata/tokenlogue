[English](README.md) · [Русский](README.ru.md)

# Using Tokenlogue Dart

Install the Dart APK on Android ARM64. Android keeps the Dart and Python profiles in separate app directories. For a Dart update, keep the existing installation and use an APK signed with the same Dart certificate.

[App screens](gallery.md)

## Connect a service

Start with an OpenRouter key beginning with `sk-or-v1-`, or a VSEGPT key beginning with `sk-or-vv-` or `sk-or-vis`. Use **Check key**, then choose a four-digit app PIN. On the Providers page, each form belongs to one service. If VSEGPT restricts balance checks, you can explicitly save an unverified key. A successful catalogue refresh alone does not verify a key.

The default for new chats can be **Choose each time**, **OpenRouter** or **VSEGPT**. An existing chat keeps its own connection.

If the service times out or asks you to wait, retry the check later. To keep a VSEGPT key after an inconclusive check, choose **Save unverified key**. A rejected key must be replaced.

<a name="chat"></a>

## Use a chat

Choose **New chat**, a service, a model and the limits. OpenRouter offers free and paid modes. VSEGPT opens its paid catalogue directly. The free OpenRouter router uses zero price limits. Select **⋮** to view the chat connection or choose a different provider. Review the new model and budget before accepting the change.

Your draft belongs to its chat. The Send action passes the selected conversation context to the chosen service. Copy a message or a code block using its copy button. Deleting a chat also deletes its local history, draft and statistics.

## Limits and spending

An account balance, an OpenRouter key limit and a chat budget each describe a different amount. On the Providers page, OpenRouter can also report how many free requests remain for the UTC day. The count appears only when the service supplies it. Token and cost estimates are approximate. When a predicted remainder reaches the warning threshold, review the amounts, cancel, change the budget or explicitly send. Changing a budget does not submit the draft. If a dispatched request has an unknown outcome, review its local reservation before deciding to release it. Releasing a reservation does not refund a provider charge.

Open **Tokens** or **Spending** to filter the journal by provider, model and period. Select a day for details. OpenRouter uses USD and VSEGPT uses RUB. An unknown amount or missing date is shown separately.

## Protect and recover access

Use the app PIN when returning from the background. On supported Android 11 or newer devices, **Forgot PIN?** can use a fresh Android system credential check to choose a new app PIN. Cancel before saving to retain your current PIN. This method requires a configured screen lock. Recovery retains the data encryption key for your existing profile.

**Delete local profile** removes the Dart app's provider keys, protection material, chats and statistics. This operation is irreversible. To finish it, type the confirmation phrase displayed by the app. A compatible update does not require deleting the profile.

[Build instructions](../../apps/android_dart/README.md) · [Project](../../README.md)

After three incorrect app PINs, wait five minutes before trying again. Closing and reopening the app keeps the waiting period. If you have already confirmed profile deletion and it is interrupted, reopen Tokenlogue. If **Finish deletion** appears, tap it to complete removal.
