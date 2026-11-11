<p align="left">
<a href="linux-appimage.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="linux-appimage.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# Tokenlogue for Linux

<a id="english"></a>
<a id="lang-en"></a>

Run Tokenlogue as an AppImage on a Linux desktop. Python, Flutter and build tools are included or unnecessary for normal use. The current preview has an English and Russian interface.

<img src="assets/ui/frame-top.svg" width="880" alt=""><br>
<img src="assets/screenshots/linux-chat.png" alt="Earlier Linux preview chat interface in English" width="880"><br>
<img src="assets/ui/frame-bottom.svg" width="880" alt="">

Linux interface from an earlier preview. This illustration uses English.

<p align="left"><a href="#en-requirements"><img src="assets/ui/buttons/en-54cd239b749b.svg" alt="Requirements" width="128" height="28"></a> <a href="#en-download"><img src="assets/ui/buttons/en-eb7306e41747.svg" alt="Download" width="98" height="28"></a> <a href="#en-run"><img src="assets/ui/buttons/en-ae7b8814a827.svg" alt="Run" width="54" height="28"></a> <a href="#en-updates"><img src="assets/ui/buttons/en-c94624d60136.svg" alt="Update" width="78" height="28"></a> <a href="#en-help"><img src="assets/ui/buttons/en-f0fa42aa9ee2.svg" alt="Troubleshooting" width="144" height="28"></a></p>

<a id="en-requirements"></a>

<a id="-requirements"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Requirements

- Linux x86_64 and an x86-64-v2 compatible processor. The system-library baseline is Ubuntu 22.04.
- A graphical desktop, GTK3 and its runtime dependencies. GTK4 alone does not replace GTK3.
- Working graphics drivers supplied by your distribution.
- A user D-Bus session and an available, unlocked Secret Service provider such as GNOME Keyring. The bundled libsecret client is not a key store by itself.
- FUSE for ordinary startup, or temporary disk space for extract-and-run.
- An OpenRouter API key and internet access to validate the key, load models and send messages.

Screen-lock and sleep protection is designed for the supported Cinnamon/X11 desktop session. Other desktops and Wayland can have limited automatic monitoring. Check the app's protection panel and use manual app locking when needed.

<a id="en-download"></a>

<a id="-download-and-verify"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Download and verify

The <a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9" title="Releases page">Releases page&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> provides the Tokenlogue 0.1.0 preview. Download the [AppImage](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) and [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS).

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Current preview file | Value |
| --- | --- |
| AppImage | [`Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) |
| SHA-256 | `247497d8f97aae0c16cab282edc1c6cbf47747c7b3597e3ba23b388558e40646` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Save the AppImage and `SHA256SUMS` in the same folder. Use Bash and SHA-256 tools to check only the selected package from that folder.
```bash
set -o pipefail
file='Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

The selected AppImage must report `OK`. A missing or duplicate manifest entry, a changed file or a missing file makes the command fail. A checksum detects changed bytes but does not replace a publisher's signature. This AppImage is unsigned. Do not replace an expected checksum with the hash of a file that failed verification.

The source archives and build tools are separate downloads. You do not need them to install or run Tokenlogue.


<a id="en-run"></a>

<a id="-start-tokenlogue"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Start Tokenlogue

Grant execute permission once, then start the verified AppImage as your normal user.
```bash
chmod u+x ./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
```

You can keep the file in a convenient folder. A file manager that supports program launching can open it after execute permission is set. The AppImage does not automatically add a menu entry. Do not run it with `sudo` or `pkexec`.

<a id="en-without-fuse"></a>

<a id="-run-without-fuse"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Run without FUSE

If your system cannot mount AppImages through FUSE, use extract-and-run.
```bash
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage --appimage-extract-and-run
```

This unpacks files to a temporary directory and starts the app without FUSE. Ensure that the temporary filesystem has enough space for the extracted files.

<a id="en-updates"></a>

<a id="-update-without-removing-your-profile"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Update without removing your profile

Close every older Tokenlogue copy before opening the replacement. Verify the new file and run it under the same OS account. There is no automatic updater. Replacing the AppImage does not remove the separately stored application data.

At the first successful sign-in, older unprotected conversation content is converted before chats open. Keep older copies closed throughout. Do not downgrade a profile without a compatible backup. Earlier versions may not understand the updated database or its protection.

The database alone is not a complete portable backup. Its encryption key stays in the system key store. Losing that key can make history unrecoverable. Read <a href="security.md#en-encryption" title="conversation protection">conversation protection&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> before moving data or changing keyring settings.

<a id="en-current-protection"></a>
<a id="en-system-recovery"></a>

<a id="-optional-recovery-through-your-linux-account"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Optional recovery through your Linux account

A saved <a href="security.md#en-recovery" title="recovery code">recovery code&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> is the usual Linux PIN-recovery method. It needs no administrator setup. The optional `Use Linux system recovery` action requires a Tokenlogue polkit policy and the desktop authentication agent.

If you choose this optional method, review the [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) and [installation helper](../packaging/linux/polkit/tokenlogue-polkit.py) from the source package matching your app. From the repository root, the one-time installation command is below. This installs the policy, not the application.
```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
```

Check the installed policy as your ordinary user.
```bash
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

The helper installs only the verified Tokenlogue policy. It refuses unexpected existing files and does not change Linux passwords, PAM or login settings. Tokenlogue is still run as your ordinary user. Each recovery attempt requires fresh confirmation of your own account in the system window. Enter the Linux password only there.

To remove only that policy later, use the following command. Application data stays in place.
```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="en-help"></a>

<a id="-troubleshoot-startup"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Troubleshoot startup

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Problem | What to check |
| --- | --- |
| Permission denied | Execute permission and a filesystem that permits launching programs. |
| FUSE mount error | Try extract-and-run above. |
| Missing GTK library | Repair GTK3 and its runtime dependencies through your distribution's package manager. |
| Key storage unavailable | Unlock the Secret Service provider and check your user D-Bus session. Keep the existing profile files. |
| Illegal instruction | Confirm that the CPU supports x86-64-v2. |
| Graphics error | Check system graphics drivers and GTK3. Terminal output may explain the failure. |
| Another copy is running | Close the other copy using the same data folder. Do not bypass the profile lock. |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

For <a href="https://github.com/Umichata/tokenlogue/issues" title="a support request">a support request&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, include the package filename, distribution, desktop session and relevant error. Remove API keys, private messages and personal paths before sharing.

<a id="en-delete"></a>

<p align="left"><a href="user-guide.md#english"><img src="assets/ui/buttons/en-79f288eb22b3.svg" alt="First connection and chat controls" width="277" height="28"></a> <a href="security.md#english"><img src="assets/ui/buttons/en-9a82d8d2cc30.svg" alt="PIN, recovery and profile deletion" width="273" height="28"></a></p>

<p align="left"><a href="source-materials.md#english"><img src="assets/ui/buttons/en-4c5f291c4b59.svg" alt="Sources and licenses" width="179" height="28"></a> <a href="../README.md#english"><img src="assets/ui/buttons/en-2e5a16e1977a.svg" alt="Tokenlogue" width="109" height="28"></a></p>
