[English](README.md#english) · [Русский](README.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Linux packages

[Home](../../../README.md) · [Documentation](../../../docs/README.md)

## Choose the package

The [Linux installation guide](../../../docs/linux-appimage.md) distinguishes the published 0.1.0 AppImage from the current local 0.1.1 desktop bundle. Python, Flutter and Java are not required to run packaged applications.

AppImage is unsigned. Verify its supplied checksum, grant execute permission and close older copies before opening a replacement. FUSE is needed for ordinary mounting, with extract-and-run available as an alternative. A desktop bundle keeps the executable, libraries and data together and uses no FUSE.

## Desktop requirements

Use an x86-64-v2 CPU, compatible system libraries, GTK3, distribution graphics drivers and an available user D-Bus session. Ubuntu 22.04 is the system-library baseline.

A Secret Service provider such as GNOME Keyring stores protected keys. AppImage contains the application and is not a backup of conversations. Read [protection and recovery](../../../docs/security.md) before moving a profile or changing the key store.

## Sources and licenses

The [notice collection](notices.md), [startup runtime](runtime/README.md) and [source-materials guide](../../../docs/source-materials.md) explain their separate roles. Building a new AppImage uses the existing producer and its source, ABI and notice checks. It is separate from obtaining a normal desktop bundle.
