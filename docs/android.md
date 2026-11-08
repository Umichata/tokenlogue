<p align="left">
<a href="android.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="android.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="README.md" title="Docs"><img src="assets/ui/buttons/en-0fba477f99e0.svg" alt="Docs" width="61" height="28"></a>
</p>

# Tokenlogue for Android

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue brings OpenRouter chats to an ARM64 Android phone or tablet. The interface supports English and Russian, saved per-chat drafts and layouts that adapt to the available space.

<a href="#en-requirements" title="Requirements"><img src="assets/ui/buttons/en-dc416f56b423.svg" alt="Requirements" width="154" height="34"></a> · <a href="#en-install" title="Install"><img src="assets/ui/buttons/en-005861163dc4.svg" alt="Install" width="97" height="34"></a> · <a href="#en-update" title="Update"><img src="assets/ui/buttons/en-b99119964e0c.svg" alt="Update" width="104" height="34"></a> · <a href="#en-first-launch" title="First launch"><img src="assets/ui/buttons/en-450d767394ee.svg" alt="First launch" width="138" height="34"></a> · <a href="security.md#english" title="Protection"><img src="assets/ui/buttons/en-c8aca5cd0ad1.svg" alt="Protection" width="128" height="34"></a>

<a id="en-requirements"></a>

## 🧩 Requirements and compatibility

- Android 7.0 or later, API 24 or newer.
- An ARM64 device that supports the `arm64-v8a` ABI.
- An OpenRouter API key and internet access for key validation, models and messages.
- A supported device screen lock for optional system PIN recovery on Android 11 or later.

The minimum API level does not mean that every Android version or device has been tested. The current package passed static ELF and ZIP alignment checks for 4 KiB and 16 KiB pages. Running it on a native ARM64 device with a 16 KiB kernel has not been checked. An earlier package's launch through ARM translation is not such a check for this package.

<a id="en-install"></a>

## 📦 Obtain and install the APK

The <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases page">Releases page&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> lists publicly available downloads. For this preview, download the APK identified below and `RELEASE_SHA256SUMS`. If this preview is not listed, its downloads are not public yet. The earlier published Linux release is a separate package.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Current Android preview | Value |
| --- | --- |
| APK | `Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk` |
| Version | `0.1.0`, versionCode `41` |
| Size | 56,160,490 bytes |
| SHA-256 | `2f7c699960e3967220f526245ca2acbf4335104a141ccf3fa2b8a04dae4709d9` |
| Signing certificate SHA-256 | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Before installation, check only the selected APK against `RELEASE_SHA256SUMS`. Save both files in the same folder. On your computer, use Bash and SHA-256 tools to run this command from that folder.
```bash
set -o pipefail
file='Tokenlogue-0.1.0-65aa62f-arm64-v8a-v41-test.apk'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' RELEASE_SHA256SUMS |
  sha256sum --check -
```

The selected APK must report `OK`. A missing or duplicate manifest entry, a changed file or a missing file makes the command fail. A checksum detects changed bytes and does not replace a publisher signature.

The original preview bundle has an internal `SHA256SUMS` for checking the complete extracted bundle. You do not need that bundle or the source archives to install or run Tokenlogue.

Transfer the verified APK to the device, open it and follow Android's installer. Android may ask to allow installations from the file manager or browser you used. Grant that permission only if you trust the package. You can turn it off again afterwards.

<a id="en-update"></a>

## 🔄 Update a compatible installation

Install the new APK over the compatible existing installation with the same application identity and signing certificate. Keep the existing application data. Uninstalling or clearing data is not an ordinary update step and can make encrypted conversations unrecoverable.

If Android refuses the update, check the package version, architecture and signing identity. Do not remove the old app just to bypass a signature error. Keep the existing data and <a href="https://github.com/Umichata/tokenlogue/issues" title="ask for help">ask for help&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Include the package filename, Android version and relevant error. Remove API keys, private messages and personal paths before sharing.

<a id="en-first-launch"></a>

## 💬 Connect and start chatting

<img src="assets/ui/frame-top.svg" width="320" alt=""><br>
<img src="assets/screenshots/android-start.png" alt="First launch on Android" width="320"><br>
<img src="assets/ui/frame-bottom.svg" width="320" alt="">

First launch on Android.

Choose a language, enter your OpenRouter API key and select `Check key`. Choose and repeat a four-digit app PIN, then save it. Use `+` to choose free or paid mode, a model and limits. The <a href="user-guide.md#english" title="user guide">user guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explains chats, drafts and cost information.

The top-left button opens the chat drawer. Select a chat, tap outside or press Back to close it. The keyboard can reduce the space for header actions. Dismiss it to show the rename and delete shortcuts again.

<img src="assets/ui/frame-top.svg" width="360" alt=""><br>
<img src="assets/screenshots/android-chat-en.png" alt="The Android chat workspace" width="360"><br>
<img src="assets/ui/frame-bottom.svg" width="360" alt="">

The Android chat workspace.

## 🔒 Protect the local profile

Moving Tokenlogue to the background closes access. Enter the app PIN when returning. Your saved draft is restored. Unlocking Android does not unlock Tokenlogue automatically.

On supported Android 11 or later devices, `Forgot PIN?` requests fresh system verification before letting you save a new app PIN. The old PIN and conversations remain if you cancel. See <a href="security.md#en-recovery" title="recovery and encryption">recovery and encryption&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Android application backup is disabled. The app uses internet access and system authentication capabilities. It does not request microphone access. Changing device security, uninstalling or clearing data can affect the keys needed to read protected conversations. A copied database alone is not a portable backup.

<a href="user-guide.md#english" title="User guide"><img src="assets/ui/buttons/en-546470010fac.svg" alt="User guide" width="131" height="34"></a> · <a href="security.md#english" title="Protection"><img src="assets/ui/buttons/en-c8aca5cd0ad1.svg" alt="Protection" width="128" height="34"></a> · <a href="source-materials.md#english" title="Source materials"><img src="assets/ui/buttons/en-6c08d5ca10c9.svg" alt="Source materials" width="176" height="34"></a> · <a href="../README.md#english" title="Tokenlogue"><img src="assets/ui/buttons/en-931ef4e6d14f.svg" alt="Tokenlogue" width="135" height="34"></a>
