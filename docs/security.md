<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="security.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="security.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="assets/ui/buttons//android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="assets/ui/buttons//android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="user-guide.md" title="User guide"><img src="assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="providers.md" title="Providers"><img src="assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="analytics.md" title="Analytics"><img src="assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="protect-conversations-and-recover-access"></a>

# Protect conversations and recover access


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** provides the Python edition for Android ARM64 (APK56) and Linux x86_64. Read the platform requirements and verify the downloaded file before installing.


<a id="pin-and-app-locking"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> PIN and app locking

Choose four digits `0`–`9` and repeat them during setup. A leading zero is allowed. The app PIN is separate from your operating-system password and from the encryption key.

Three incorrect PIN checks block entry for five minutes. Restarting does not reset the countdown. The same limit applies when confirming a PIN to issue a recovery code.

Use the lock button before leaving the device. Locking saves the draft and closes all private pages. Entered provider candidates and visible analytics are cleared, including hidden cards. An already dispatched request can finish and record its response once. Unlocking never sends a draft.

![The ordinary Tokenlogue PIN sign-in screen on Linux](assets/screenshots/v011-55-linux-pin-lock-en.png)

*Separate demonstration profile. No PIN or recovery secret is shown.*

Android backgrounding closes access. Returning or unlocking Android still requires the app PIN. On Linux, supported Cinnamon/X11 monitoring can lock the app on a screen lock, session change or suspend. Minimizing alone does not lock it. Other desktops and Wayland can limit monitoring, so use manual app locking when needed.

<a id="check-linux-protection"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Check Linux protection

After first setup, **Check local protection** introduces the check. The PIN is already saved. **Start check** requests a normal system lock. Unlock Linux, then enter your app PIN and review the result. You can continue with manual app locking and check later.

The shield opens the protection panel without locking or suspending the computer. Screen-lock and sleep checks have separate results. A saved result does not prove that current monitoring remains available. Enter your Linux password only in the operating system's authentication window.

<a href="assets/screenshots/v011-55-linux-local-protection-en.png"><img src="assets/ui/frame-top.svg" alt="" width="640"><br><img src="assets/screenshots/v011-55-linux-local-protection-en.png" alt="Linux protection panel with separate screen-lock and sleep results" width="640"><br><img src="assets/ui/frame-bottom.svg" alt="" width="640"></a>

*This example has no confirmed system monitoring. Use manual app locking when monitoring is unavailable.*

<a id="en-recovery"></a>
<a id="recover-a-forgotten-pin"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Recover a forgotten PIN

Recovery replaces an app PIN while keeping the original protected encryption key. It cannot rebuild a lost key or restore a database from a code alone. Cancelling before saving keeps the old PIN.

<a id="en-linux-code"></a>
<a id="linux-recovery-code"></a>

### Linux recovery code

After signing in, choose **Recovery code** in **⋮** and confirm your app PIN. Save the displayed 32-character code separately and repeat it to confirm storage. Anyone with the code can replace the app PIN. Clipboard history can keep a copied code.

The old code remains valid until a replacement is confirmed. You cannot reveal the same code later. Choose **Forgot PIN?**, enter your saved code, then choose and save a new PIN. Letter case, ordinary spaces and hyphens are accepted. Five wrong code checks block code entry for 30 seconds.

Saving a replacement PIN consumes the used code. Save and confirm the replacement offered afterwards. If you close the app first, sign in with the new PIN and issue another code. Creating a code for an already locked profile requires valid access first.

<a href="assets/screenshots/v011-55-linux-recovery-verified-en.png"><img src="assets/ui/frame-top.svg" alt="" width="420"><br><img src="assets/screenshots/v011-55-linux-recovery-verified-en.png" alt="Linux recovery code verified before choosing a new PIN" width="420"><br><img src="assets/ui/frame-bottom.svg" alt="" width="420"></a>

*Separate demonstration profile. No recovery code or PIN is shown.*

The [code-entry form](assets/screenshots/v011-55-linux-recovery-en.png).

<a id="linux-system-recovery"></a>

### Linux system recovery

The separate **Use Linux system recovery** option needs the Tokenlogue polkit policy and desktop authentication agent. It requests fresh confirmation of your own Linux account. An already unlocked keyring or another administrator does not replace this proof. See [optional Linux setup](linux-appimage.md).

<a id="android-system-recovery"></a>

### Android system recovery

On supported Android 11 or later devices, **Forgot PIN?** requests fresh system verification with the device PIN, pattern, password or supported biometrics. Fingerprint is not required. Android 7–10 can run the app but do not provide this recovery method. Set an Android screen lock before using it.

After confirmation, choose and repeat a new app PIN and save it. Cancelling before saving keeps the old PIN and conversations. If the device check is unavailable, use the current app PIN.

<a href="assets/screenshots/v011-55-android-recovery-new-pin-en.png"><img src="assets/ui/frame-top.svg" alt="" width="420"><br><img src="assets/screenshots/v011-55-android-recovery-new-pin-en.png" alt="Android device verification completed before choosing a new app PIN" width="420"><br><img src="assets/ui/frame-bottom.svg" alt="" width="420"></a>

*Android emulator after normal device verification. Both new-PIN fields are empty. Availability depends on the device and its screen lock.*

<a id="encryption-and-separate-storage"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Encryption and separate storage

Saved chat titles, messages and drafts are encrypted. A random key is stored separately in platform secure storage. It is not derived from the four-digit PIN or provider key. Linux needs an available Secret Service such as GNOME Keyring.

Provider and model identifiers, dates, currencies, token counts, budgets and accounting states remain readable. This protects selected fields rather than the entire database or device. It is not end-to-end encryption with a provider. Sending shares the required content with the service assigned to the chat and its selected model provider.

Changing a chat’s provider requires an explicit review of the new service, model and budget. No history is sent while configuring. The next ordinary send shares only the new message and completed pairs that fit the model context with that service. Cancel before confirming to keep the existing connection. Changing the connection preserves local encryption and does not change the PIN or encryption key.

OpenRouter and VSEGPT keys occupy separate protected entries. Preferences and conversation fields do not store them. Matching a prefix does not confirm authorization. A key is never retried on the other service, forwarded to another host on redirect or used for an automatic paid check.

When storage or its key is unavailable, conversations remain closed. Restore the system key store and retry your PIN rather than deleting files. A supported plaintext profile is encrypted during the first successful sign-in without discarding its chats or accounting. Keep other copies closed.

A database copy does not contain its separate encryption key. Android backup is disabled. Uninstalling, clearing data, losing the key store or invalidating Android Keystore can make conversations unrecoverable. PIN recovery cannot recover a lost encryption key. Locking also cannot protect an already compromised OS or promise erasure of every copy from memory, swap or old backups.

<a id="delete-a-local-profile"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Delete a local profile

**Deletion is irreversible in Tokenlogue.** Use recovery if you want to keep the conversations.

**Delete local profile** is available from the PIN screen or **⋮**, including during PIN lockout. It needs no old PIN or network access. Anyone able to use this screen can confirm it. Read the warning, type **DELETE PROFILE** exactly and choose **Delete profile**. **Keep profile** cancels before acceptance.

![Local-profile deletion warning before confirmation](assets/screenshots/v011-55-linux-delete-profile-en.png)

*Separate demonstration profile. The typed confirmation is an intent check, not an identity check.*

Deletion removes both local provider keys, PIN, recovery material, encryption key, chats, drafts, limits and statistics. Language and layout preferences remain. External copies remain too, and secure physical erasure is not guaranteed.

If accepted deletion is interrupted, use **Finish deletion** or restart to continue. Chats remain closed until removal finishes. Deletion does not revoke remote keys, cancel dispatched requests or refund charges. Use [Providers](providers.md) to replace a key while keeping the profile.
