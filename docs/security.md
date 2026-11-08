<p align="left">
<a href="security.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="security.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="README.md" title="Docs"><img src="assets/ui/buttons/en-0fba477f99e0.svg" alt="Docs" width="61" height="28"></a>
</p>

# 🛡️ Conversation protection

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue protects access to locally stored conversations with an app PIN and a separate encryption key. This guide covers the current Linux and Android preview. Earlier published versions can store conversation content without this protection.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Protection element | What it does |
| --- | --- |
| App PIN | Controls access through Tokenlogue. It is not the encryption key. |
| Encryption key | Is stored separately and is needed to decrypt protected conversation fields. |
| Recovery method | Lets you replace a forgotten PIN when the original protected encryption key remains available. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

<a href="#en-pin" title="PIN"><img src="assets/ui/buttons/en-7195c33ea7af.svg" alt="PIN" width="77" height="34"></a> · <a href="#en-locking" title="Locking"><img src="assets/ui/buttons/en-9176886ca175.svg" alt="Locking" width="108" height="34"></a> · <a href="#en-recovery" title="Recovery"><img src="assets/ui/buttons/en-e965a7f9ec2e.svg" alt="Recovery" width="119" height="34"></a> · <a href="#en-encryption" title="Encryption"><img src="assets/ui/buttons/en-780abd498991.svg" alt="Encryption" width="130" height="34"></a> · <a href="#en-delete" title="Delete a profile"><img src="assets/ui/buttons/en-87bf12e93447.svg" alt="Delete a profile" width="165" height="34"></a>

<a id="en-pin"></a>

<a id="your-app-pin"></a>

### 🔑 Your app PIN

Choose four digits `0`–`9` and repeat them during setup. A leading zero is allowed. Save the PIN separately. The eye button can reveal it, but Tokenlogue never copies it automatically.

Three incorrect PIN checks block PIN entry for five minutes. Sign-in and PIN confirmation before issuing a recovery code share this limit. Restarting, sleeping or changing language does not reset it. Wait for the displayed countdown to finish. Recovery and local profile deletion remain available.

The app PIN is different from your Linux password and Android screen-lock PIN. It controls access through Tokenlogue. It is not the encryption key and is not a substitute for a protected OS account.

<a id="en-locking"></a>

<a id="lock-the-app-when-you-leave"></a>

### 🔒 Lock the app when you leave

Use the lock button in the header to close access to chats. Returning requires the app PIN. Locking saves the latest draft. A request already sent can still finish and record its response and cost. The app does not automatically send a draft when you return.

On Android, leaving the app for the background locks access and closes dialogs. Returning to the app or unlocking Android does not unlock Tokenlogue. Merely opening the keyboard or briefly losing focus is not the same as backgrounding.

On Linux, screen-lock and sleep monitoring depends on the desktop. The supported Cinnamon/X11 session can close access on screen lock, session switching and suspend. Minimizing or changing focus alone does not lock the app. Use manual app locking whenever monitoring is unavailable or unconfirmed. Other desktops, Wayland, additional displays and ambiguous sessions can limit automatic detection.

<a id="check-linux-screen-lock-and-sleep-protection"></a>

### 🖥️ Check Linux screen-lock and sleep protection

After saving a new protected Linux profile, `Check local protection` explains the check before opening chats. Your PIN is already saved. Only `Start check` requests the system screen lock. Unlock Linux normally, then enter that app PIN. Choose `Open chats` after reviewing the result. If interrupted, sign in with your saved PIN to resume. You can choose `Continue with manual locking` and check again later.

The shield in the app header opens the protection panel before or after sign-in. Opening it never locks or suspends the computer. While signed out, choosing a test first takes you through normal app PIN sign-in. `Start test` remains a separate action.

`Test screen lock` saves the draft and requests a normal system lock. `Test sleep protection` saves it and asks the computer to sleep. For the latter, wake the computer, unlock Linux normally and enter the app PIN. You do not need a successful screen test before testing sleep. The two checks have separate results.

The panel distinguishes remembered checks from monitoring available now. A previous successful check is not proof that a currently disconnected service works. Results belong to this device and OS account. A different desktop setup may need another check. A cancelled or refused check does not confirm protection. Do not change system security settings merely to make a test succeed.

Android uses background locking and has no desktop screen-lock or sleep tests in this panel.

<a id="en-recovery"></a>

<a id="recover-a-forgotten-app-pin"></a>

### 🛟 Recover a forgotten app PIN

Recovery lets you choose and save a new app PIN. It needs an existing valid recovery method and the original protected encryption key. It cannot rebuild a lost key or restore a database from a code alone.

Opening `Forgot PIN?` does not change the PIN. Your previous PIN keeps working until a new one is saved. A system lock, backgrounding or language change can cancel an unfinished attempt. Start again if needed. A new PIN already saved remains active.

<a id="linux-recovery-code"></a>

#### 🗝️ Linux recovery code

Save a code before you need it. After signing in, open `⋮` and choose `Recovery code`. Confirm your app PIN again. New profiles also offer this after the local-protection introduction.

The code has 32 Base32 characters, displayed in groups of four. Anyone with it can replace the app PIN. Save it separately in a password manager or on paper, then repeat the saved code to confirm. It is shown once. Copying is optional, and clipboard history may keep a copy.

A previous code remains valid until a replacement is confirmed. Cancelling or a failed save keeps the working code. You cannot reveal the same code later. Sign in and issue a replacement if you need a new one.

To use it, choose `Forgot PIN?`, enter the saved code, then choose, repeat and save a new app PIN. ASCII letter case, ordinary spaces and hyphens are accepted. All 32 characters are required. Five incorrect code checks block code entry for 30 seconds, separately from the app PIN limit. Restarting does not bypass the delay.

Saving the new PIN consumes the code. Save and confirm the replacement offered afterwards. If you close the app first, sign in with the new PIN and create another code from `⋮`.

Code recovery needs no Linux password, administrator rights or system policy. It keeps your API key, encryption key, conversations, drafts and budgets. It cannot be enrolled while a profile is already locked with a forgotten PIN. A new API key or an unlocked keyring does not prove access to that profile.

<a id="optional-linux-system-recovery"></a>

#### 🖥️ Optional Linux system recovery

`Use Linux system recovery` is a separate choice. It requests fresh confirmation of your own Linux account through the desktop authentication window. Enter your Linux password only in that system window, never into Tokenlogue. A different administrator account or an already unlocked keyring does not replace this check.

This option needs the separately installed Tokenlogue policy and a working desktop authentication agent. Without them, conversations stay closed. The <a href="linux-appimage.md#en-system-recovery" title="Linux guide">Linux guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explains the optional setup. Recovery codes work without it.

<a id="android-system-recovery"></a>

#### 📱 Android system recovery

On Android 11 or later, `Forgot PIN?` can request a separate system check of the device PIN, pattern or password. Supported biometrics may also be offered. A fingerprint is not required. A supported screen lock must be configured. Simply unlocking the device does not complete this fresh check.

After verification, choose a new app PIN, repeat it and select `Save new PIN`. Cancelling before saving keeps the previous PIN and conversations. If verification is unavailable or refused, use your existing app PIN. Android 7–10 can run the app but do not provide this recovery method.

<a id="en-encryption"></a>

<a id="what-is-encrypted"></a>

### 🔐 What is encrypted

Tokenlogue encrypts saved chat titles, user and model messages, and drafts. A random encryption key is stored separately in platform secure storage. It is not derived from the four-digit PIN or OpenRouter key. Linux needs an available, unlocked Secret Service such as GNOME Keyring.

Dates, model identifiers, chat modes, token counts, budgets and accounting states remain readable. This is encryption of selected database fields. It does not encrypt the whole database or device, and it is not end-to-end encryption with OpenRouter. Sending transmits the necessary messages and context to OpenRouter and the selected model provider. Check their data policies before sending private information.

If secure storage or the encryption key is unavailable, conversations stay closed. After a temporary storage failure, restore access to the system key store and retry the existing PIN. Do not delete the database or reset device security to dismiss the error.

When upgrading older local data, the first successful sign-in protects its content before opening chats. History, drafts, models and accounting are preserved. Close all older Linux copies first and keep them closed. Current builds allow one process per data folder, but earlier versions do not follow that rule.

Copying the database alone does not back up its encryption key. Android application backup is disabled. Uninstalling, clearing app data, losing secure storage or invalidating Android Keystore can make conversations unrecoverable. Changes to device security can affect key availability on some devices. A new PIN, recovery code or API key cannot recreate a lost encryption key.

Locking clears the visible workspace and closes new access. It does not promise immediate erasure of every plaintext or key copy from process memory. It cannot protect an already compromised operating system. Old external backups, storage blocks, swap or snapshots may retain earlier content.

<a id="en-delete"></a>

<a id="delete-a-local-profile"></a>

### 🗑️ Delete a local profile

**Deletion is irreversible within Tokenlogue.** To keep conversations, use a valid recovery method instead.

`Delete local profile` is available on the PIN screen and at the bottom of `⋮` after sign-in, even without a selected chat. It remains available during PIN lockout. It does not require the old PIN, a recovery code, Linux password or network access. Anyone who can use this screen can confirm it.

Read the dialog, type the displayed phrase `DELETE PROFILE` exactly, then choose `Delete profile`. `Keep profile` cancels before acceptance. The phrase confirms intent, not identity. Changing language or closing an unconfirmed dialog cancels it.

Deletion removes the profile's local API key, PIN, recovery code, encryption key, chats, messages, drafts, limits and spending records. The new profile cannot recover the old conversations. Language and panel layout choices remain. External exports and backups are untouched. Secure physical erasure of all device copies is not guaranteed.

On Linux, Tokenlogue may first make its own supported data folder private. A failure before deletion starts keeps the profile. If permissions were already restricted, the folder stays private. Do not manually remove files or change permissions to bypass an error.

Once deletion has begun, it must finish. If storage fails, chats stay closed. Use `Finish deletion` or restart to continue. New setup opens only after removal is complete. Enter a key and choose a new PIN for the empty profile.

Deleting locally does not revoke your key at OpenRouter, delete that account, cancel submitted requests or refund charges. Use `Replace OpenRouter key` after sign-in when you want to change keys and keep conversations.

<a href="user-guide.md#english" title="User guide"><img src="assets/ui/buttons/en-546470010fac.svg" alt="User guide" width="131" height="34"></a> · <a href="linux-appimage.md#english" title="Linux"><img src="assets/ui/buttons/en-411f244045b9.svg" alt="Linux" width="91" height="34"></a> · <a href="android.md#english" title="Android"><img src="assets/ui/buttons/en-5d10a1d077a6.svg" alt="Android" width="109" height="34"></a> · <a href="../README.md#english" title="Tokenlogue"><img src="assets/ui/buttons/en-931ef4e6d14f.svg" alt="Tokenlogue" width="135" height="34"></a>
