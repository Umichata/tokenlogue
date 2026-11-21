<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="linux-appimage.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="linux-appimage.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="assets/ui/buttons//android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="assets/ui/buttons//android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="user-guide.md" title="User guide"><img src="assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="providers.md" title="Providers"><img src="assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="analytics.md" title="Analytics"><img src="assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="tokenlogue-for-linux"></a>

# Tokenlogue for Linux


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** provides the Python edition for Android ARM64 (APK56) and Linux x86_64. Read the platform requirements and verify the downloaded file before installing.


<a id="requirements"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Requirements

Use Linux x86_64 with a graphical desktop, glibc 2.34 or later, libstdc++ providing `GLIBCXX_3.4.29`, GTK3 and distribution graphics drivers. Ubuntu 22.04 is the system-library baseline. The earlier 0.1.0 AppImage requires an x86-64-v2 CPU. The 0.1.1 bundle has not been tested on older CPUs. You also need a user D-Bus session and an unlocked Secret Service provider, such as GNOME Keyring. The bundled libsecret client is not a key store.

Online model use needs a key for the chat's provider. Cinnamon/X11 is the supported screen-lock and sleep-monitoring session. Other desktops and Wayland can limit automatic monitoring. Use manual app locking when monitoring is unavailable.

<a id="en-download"></a>
<a id="en-local-bundle"></a>
<a id="desktop-bundle-011"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Desktop bundle 0.1.1

Download the complete bundle from [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1). It contains the application and its libraries. It is not an AppImage, does not require FUSE and is unsigned.

| Item | Value |
| --- | --- |
| File | `Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz` |
| Version | 0.1.1+56 |
| Architecture | Linux x86_64 |
| Size | 34,974,386 bytes |
| SHA-256 | `6ab4f7525ea9ec7287b6d4d3c53e95089d590e856874c9695e793186149e03d9` |
| Extracted directory | `Tokenlogue-0.1.1+56-linux-x86_64/` |

Close earlier Tokenlogue copies. In the directory containing the supplied archive, verify its checksum.

```bash
printf '%s  %s\n' \
  '6ab4f7525ea9ec7287b6d4d3c53e95089d590e856874c9695e793186149e03d9' \
  'Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz' | sha256sum --check -
```

After `OK`, extract the entire bundle into a new directory and run it as your ordinary user. This example assumes `tokenlogue-local` does not already exist. Stop if a command reports an error.

```bash
mkdir tokenlogue-local &&
tar --extract --gzip --file 'Tokenlogue-0.1.1+56-linux-x86_64-bundle.tar.gz' \
  --directory tokenlogue-local --no-same-owner &&
./tokenlogue-local/Tokenlogue-0.1.1+56-linux-x86_64/tokenlogue
```

Keep the executable with its libraries and data folders. Use the same OS account and existing unlocked secure storage. Replacing the application directory does not require deleting your profile. See [safe updates](#update-safely).

<a id="en-published-appimage"></a>
<a id="published-appimage"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Published AppImage

This earlier public file is **0.1.0**. Version 0.1.1 is supplied as a desktop bundle. An archive of project sources is not an installed application.

| File | Value |
| --- | --- |
| <a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage" title="AppImage x86_64"><img src="assets/ui/buttons/v3-en-6c1977e489d0.svg" alt="AppImage x86_64" width="155" height="30"></a> | `Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage` |
| Version | 0.1.0+43 |
| SHA-256 | `247497d8f97aae0c16cab282edc1c6cbf47747c7b3597e3ba23b388558e40646` |
| Manifest | <a href="https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS" title="SHA256SUMS"><img src="assets/ui/buttons/v3-en-f1ce47c3a95b.svg" alt="SHA256SUMS" width="125" height="30"></a> |

Save the AppImage and manifest together. Check only the selected file with Bash and SHA-256 tools.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Continue only if the selected AppImage reports `OK`. The AppImage is unsigned. Checksums confirm integrity and do not establish a publisher signature.

<a id="launch-an-appimage"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Launch an AppImage

Grant execute permission and run the verified file as your ordinary user.

```bash
chmod u+x ./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
```

If FUSE is unavailable, use the following option with enough temporary disk space.

```bash
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage --appimage-extract-and-run
```

<a id="launch-a-local-desktop-bundle"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Launch the desktop bundle

Use the [desktop bundle instructions](#en-local-bundle) above for its exact file, checksum and extraction steps. Keep the whole application directory together. AppImage options do not apply to this format.

<a id="update-safely"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Update safely

Close every old copy before starting a replacement under the same OS account and with access to the same system key store. Verify the new package. Replacing the application files keeps the separately stored profile. There is no automatic updater.

The first successful sign-in protects any supported unencrypted conversation fields before opening chats. Do not let incompatible versions write to the same profile. A database copy alone is not a portable backup because the encryption key is stored separately. See [data protection](security.md).

<a id="optional-linux-system-recovery"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Optional Linux system recovery

A previously saved [recovery code](security.md#en-linux-code) is the usual PIN-recovery method. The separate system-recovery option needs Tokenlogue's polkit policy and a desktop authentication agent.

Review the [policy](../packaging/linux/polkit/io.github.umichata.tokenlogue.policy) and [installation helper](../packaging/linux/polkit/tokenlogue-polkit.py) from the source package matching your app. From the source directory, install the policy once, then check it as an ordinary user.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py install
/usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py check
```

This installs the policy only. It does not change Linux passwords, PAM or login settings. Enter your OS password only in the system authentication window. Tokenlogue itself runs without `sudo` or `pkexec`.

Remove only that policy later with the following command. Your application data remains.

```bash
sudo /usr/bin/python3 -I packaging/linux/polkit/tokenlogue-polkit.py uninstall
```

<a id="startup-help"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Startup help

| Symptom | Action |
| --- | --- |
| Execute permission denied | Check the file permission and whether the filesystem permits execution. |
| FUSE mount failed | Use extract-and-run for AppImage. |
| Missing GTK library | Restore GTK3 and dependencies through your distribution. |
| Key storage unavailable | Unlock Secret Service and check the user D-Bus session. Keep the profile files. |
| Illegal instruction | Check the package’s CPU requirements. The published AppImage requires x86-64-v2. |
| Graphics failure | Check distribution graphics drivers. |
| Profile already in use | Close the copy using it. Do not bypass its lock. |

[Report an issue](https://github.com/Umichata/tokenlogue/issues) with the version, distribution and desktop. Remove private messages, keys and personal paths.
