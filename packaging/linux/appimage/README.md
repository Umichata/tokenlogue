<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="README.ru.md#russian" title="RU"><img align="right" src="../../../docs/assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="README.md#english" title="EN"><img align="right" src="../../../docs/assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../../../README.md" title="Home"><img src="../../../docs/assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android"><img src="../../../docs/assets/ui/buttons/v3-en-4a0b64bd4ded.svg" alt="Android" width="83" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="../../../docs/assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="../../../docs/assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="../../../docs/assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="../../../docs/README.md" title="Documentation map"><img src="../../../docs/assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="../../../docs/user-guide.md" title="User guide"><img src="../../../docs/assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="../../../docs/providers.md" title="Providers"><img src="../../../docs/assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="../../../docs/analytics.md" title="Analytics"><img src="../../../docs/assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="linux-packages"></a>

# Linux packages


<a id="choose-the-package"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Choose the package

The [Linux installation guide](../../../docs/linux-appimage.md) distinguishes the published 0.1.0 AppImage from the current local 0.1.1 desktop bundle. Python, Flutter and Java are not required to run packaged applications.

AppImage is unsigned. Verify its supplied checksum, grant execute permission and close older copies before opening a replacement. FUSE is needed for ordinary mounting, with extract-and-run available as an alternative. A desktop bundle keeps the executable, libraries and data together and uses no FUSE.

<a id="desktop-requirements"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Desktop requirements

The local desktop bundle needs Linux x86_64, compatible system libraries, GTK3, distribution graphics drivers and an available user D-Bus session. Ubuntu 22.04 is the build and library-compatibility baseline. This does not mean that every distribution has been tested.

The published 0.1.0 AppImage requires an x86-64-v2 CPU. The lowest CPU instruction level for the local 0.1.1 bundle has not been established by runtime tests.

A Secret Service provider such as GNOME Keyring stores protected keys. AppImage contains the application and is not a backup of conversations. Read [protection and recovery](../../../docs/security.md) before moving a profile or changing the key store.

<a id="sources-and-licenses"></a>

## <img src="../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Sources and licenses

The [notice collection](notices.md), [AppImage startup runtime](runtime/README.md) and [source-materials guide](../../../docs/source-materials.md) explain their separate roles. Building a new AppImage uses the existing producer and its source, ABI and notice checks. It is separate from obtaining a normal desktop bundle.
