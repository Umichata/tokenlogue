<p align="left">
<a href="android.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="android.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# Tokenlogue for Android

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue brings OpenRouter chats to an ARM64 Android phone or tablet. The interface supports English and Russian, saved per-chat drafts and layouts that adapt to the available space.

<p align="left"><a href="#en-requirements"><img src="assets/ui/buttons/en-54cd239b749b.svg" alt="Requirements" width="128" height="28"></a> <a href="#en-install"><img src="assets/ui/buttons/en-c1a92da25825.svg" alt="Install" width="71" height="28"></a> <a href="#en-update"><img src="assets/ui/buttons/en-c94624d60136.svg" alt="Update" width="78" height="28"></a> <a href="#en-first-launch"><img src="assets/ui/buttons/en-1de6f9fc48e6.svg" alt="First launch" width="112" height="28"></a> <a href="security.md#english"><img src="assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a></p>

<a id="en-requirements"></a>

<a id="-requirements-and-compatibility"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Requirements and compatibility

- Android 7.0 or later, API 24 or newer.
- An ARM64 device that supports the `arm64-v8a` ABI.
- An OpenRouter API key and internet access for key validation, models and messages.
- A supported device screen lock for optional system PIN recovery on Android 11 or later.

The minimum API level does not mean that every Android version or device has been tested. Consult the package provenance for its static ELF and ZIP alignment results. Static 16 KiB alignment does not prove runtime compatibility. Native ARM64 operation with a 16 KiB kernel has not been checked.

<a id="en-install"></a>

<a id="-obtain-and-install-the-apk"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Obtain and install the APK

The <a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.2.0-preview.52a834d" title="Releases page">Releases page&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> provides the Tokenlogue 0.2.0 preview. Download the [APK](https://github.com/Umichata/tokenlogue/releases/download/v0.2.0-preview.52a834d/Tokenlogue-0.2.0-android-arm64-v8a-v42.apk) and [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.2.0-preview.52a834d/SHA256SUMS).

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Current Android preview | Value |
| --- | --- |
| APK | [`Tokenlogue-0.2.0-android-arm64-v8a-v42.apk`](https://github.com/Umichata/tokenlogue/releases/download/v0.2.0-preview.52a834d/Tokenlogue-0.2.0-android-arm64-v8a-v42.apk) |
| Version | `0.2.0`, versionCode `42` |
| SHA-256 | `378d8fbaea3ba0faa5aff81cd564e260dece4e25dff23519647e7db3812b28ea` |
| Signing certificate SHA-256 | `927292ad5a76ff049059d1c5d8e9497a42c03f3e995a5d9ca935c59ad8d0b09e` |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Before installation, check only the selected APK against `SHA256SUMS`. Save both files in the same folder. On your computer, use Bash and SHA-256 tools to run this command from that folder.
```bash
set -o pipefail
file='Tokenlogue-0.2.0-android-arm64-v8a-v42.apk'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

The selected APK must report `OK`. A missing or duplicate manifest entry, a changed file or a missing file makes the command fail. A checksum detects changed bytes and does not replace a publisher signature.

The source archives and build tools are separate downloads. You do not need them to install or run Tokenlogue.

Transfer the verified APK to the device, open it and follow Android's installer. Android may ask to allow installations from the file manager or browser you used. Grant that permission only if you trust the package. You can turn it off again afterwards.

<a id="en-update"></a>

<a id="-update-a-compatible-installation"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Update a compatible installation

Install the new APK over the compatible existing installation with the same application identity and signing certificate. Keep the existing application data. Uninstalling or clearing data is not an ordinary update step and can make encrypted conversations unrecoverable.

If Android refuses the update, check the package version, architecture and signing identity. Do not remove the old app just to bypass a signature error. Keep the existing data and <a href="https://github.com/Umichata/tokenlogue/issues" title="ask for help">ask for help&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Include the package filename, Android version and relevant error. Remove API keys, private messages and personal paths before sharing.

<a id="en-first-launch"></a>

<a id="-connect-and-start-chatting"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Connect and start chatting

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

<a id="-protect-the-local-profile"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Protect the local profile

Moving Tokenlogue to the background closes access. Enter the app PIN when returning. Your saved draft is restored. Unlocking Android does not unlock Tokenlogue automatically.

On supported Android 11 or later devices, `Forgot PIN?` requests fresh system verification before letting you save a new app PIN. The old PIN and conversations remain if you cancel. See <a href="security.md#en-recovery" title="recovery and encryption">recovery and encryption&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Android application backup is disabled. The app uses internet access and system authentication capabilities. It does not request microphone access. Changing device security, uninstalling or clearing data can affect the keys needed to read protected conversations. A copied database alone is not a portable backup.

<p align="left"><a href="user-guide.md#english"><img src="assets/ui/buttons/en-4a1e7eca97e9.svg" alt="User guide" width="105" height="28"></a> <a href="security.md#english"><img src="assets/ui/buttons/en-9c2e33444d68.svg" alt="Protection" width="102" height="28"></a> <a href="source-materials.md#english"><img src="assets/ui/buttons/en-b63fdbc05df7.svg" alt="Source materials" width="150" height="28"></a> <a href="../README.md#english"><img src="assets/ui/buttons/en-2e5a16e1977a.svg" alt="Tokenlogue" width="109" height="28"></a></p>
