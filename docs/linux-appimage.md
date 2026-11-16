[English](linux-appimage.md#english) · [Русский](linux-appimage.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Tokenlogue for Linux

[Home](../README.md) · [Documentation](../docs/README.md)

> **0.1.1 is local.** These instructions describe the current source and local builds. [Published 0.1.0 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-preview.a981db9) is the earlier release. Its download links do not provide 0.1.1.


## Requirements

Use Linux x86_64 with a graphical desktop, GTK3 and distribution graphics drivers. Ubuntu 22.04 is the system-library baseline. The published AppImage requires an x86-64-v2 CPU. The local bundle has not been tested on older CPUs. You also need a user D-Bus session and an unlocked Secret Service provider, such as GNOME Keyring. The bundled libsecret client is not a key store.

Online model use needs a key for the chat's provider. Cinnamon/X11 is the supported screen-lock and sleep-monitoring session. Other desktops and Wayland can limit automatic monitoring. Use manual app locking when monitoring is unavailable.

<a id="en-download"></a>
<a id="en-local-bundle"></a>
## Local desktop bundle 0.1.1

The current desktop build is supplied as a separate archive. There is no ready AppImage 0.1.1. This file is not among the published 0.1.0 downloads and does not require FUSE.

| Item | Value |
| --- | --- |
| File | `Tokenlogue-0.1.1+55-9117edc-linux-x86_64-bundle.tar.gz` |
| Version | 0.1.1+55 |
| Architecture | Linux x86_64 |
| Size | 35,606,991 bytes |
| SHA-256 | `59675e0369298fee0007ce057000f105a3c6af3b09b7b2fdf4ae03a086b8b2e2` |
| Extracted directory | `Tokenlogue-0.1.1+55-linux-x86_64/` |

Close earlier Tokenlogue copies. In the directory containing the supplied archive, verify its checksum.

```bash
printf '%s  %s\n' \
  '59675e0369298fee0007ce057000f105a3c6af3b09b7b2fdf4ae03a086b8b2e2' \
  'Tokenlogue-0.1.1+55-9117edc-linux-x86_64-bundle.tar.gz' | sha256sum --check -
```

After `OK`, extract the entire bundle into a new directory and run it as your ordinary user. This example assumes `tokenlogue-local` does not already exist. Stop if a command reports an error.

```bash
mkdir tokenlogue-local &&
tar --extract --gzip --file 'Tokenlogue-0.1.1+55-9117edc-linux-x86_64-bundle.tar.gz' \
  --directory tokenlogue-local --no-same-owner &&
./tokenlogue-local/Tokenlogue-0.1.1+55-linux-x86_64/tokenlogue
```

Keep the executable with its libraries and data folders. Use the same OS account and existing unlocked secure storage. Replacing the application directory does not require deleting your profile. See [safe updates](#update-safely).

<a id="en-published-appimage"></a>
## Published AppImage

This public file is **0.1.0**. Local 0.1.1 is supplied as a separate desktop bundle. An archive of project sources is not an installed application.

| File | Value |
| --- | --- |
| [AppImage x86_64](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage) | `Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage` |
| Version | 0.1.0+43 |
| SHA-256 | `247497d8f97aae0c16cab282edc1c6cbf47747c7b3597e3ba23b388558e40646` |
| Manifest | [SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) |

Save the AppImage and manifest together. Check only the selected file with Bash and SHA-256 tools.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

Continue only if the selected AppImage reports `OK`. The AppImage is unsigned. Checksums confirm integrity and do not establish a publisher signature.

## Launch an AppImage

Grant execute permission and run the verified file as your ordinary user.

```bash
chmod u+x ./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage
```

If FUSE is unavailable, use the following option with enough temporary disk space.

```bash
./Tokenlogue-0.1.0-a981db9-linux-x86_64.AppImage --appimage-extract-and-run
```

## Launch a local desktop bundle

Use the [local bundle instructions](#en-local-bundle) above for its exact file, checksum and extraction steps. Keep the whole application directory together. AppImage options do not apply to this format.

## Update safely

Close every old copy before starting a replacement under the same OS account and with access to the same system key store. Verify the new package. Replacing the application files keeps the separately stored profile. There is no automatic updater.

The first successful sign-in protects any supported unencrypted conversation fields before opening chats. Do not let incompatible versions write to the same profile. A database copy alone is not a portable backup because the encryption key is stored separately. See [data protection](security.md).

## Optional Linux system recovery

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

## Startup help

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
