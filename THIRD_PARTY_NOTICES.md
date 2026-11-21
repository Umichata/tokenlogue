<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="THIRD_PARTY_NOTICES.ru.md#russian" title="RU"><img align="right" src="docs/assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="THIRD_PARTY_NOTICES.md#english" title="EN"><img align="right" src="docs/assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="README.md" title="Home"><img src="docs/assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="docs/assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="docs/assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="docs/assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="docs/assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="docs/assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="docs/README.md" title="Documentation map"><img src="docs/assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="docs/user-guide.md" title="User guide"><img src="docs/assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="docs/providers.md" title="Providers"><img src="docs/assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="docs/analytics.md" title="Analytics"><img src="docs/assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="third-party-notices"></a>

# Third-party notices

This page covers the Python Android APK and Linux desktop bundle. The [Android Dart dependency lock](https://github.com/Umichata/tokenlogue/blob/android-dart/apps/android_dart/pubspec.lock) lists the packages used by the separate Dart app.

Tokenlogue's application code uses the [MIT license](LICENSE). Dependencies retain their original terms. This overview does not replace original notices.

<a id="components"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Components

| Component | Version | Terms and role |
| --- | --- | --- |
| Flet and Flet Secure Storage | 0.86.5 | Apache 2.0, interface and platform secure storage |
| HTTPX | 0.28.1 | BSD 3-Clause, provider HTTPS requests |
| PyCryptodomex | 3.23.0 | BSD 2-Clause and public-domain notices, encryption primitives |
| CFFI | 2.0.0 | MIT, native interface |
| libffi in source-built CFFI | 3.4.4 | MIT, statically linked native calls |
| pycparser | 3.11 | BSD 3-Clause, C declarations |
| tzdata | 2026.6 | Apache 2.0 and IANA public-domain notice, time-zone rules |

Android secure storage uses flutter_secure_storage 10.3.1. System recovery uses local_auth 3.0.2, local_auth_android 2.2.0 and local_auth_platform_interface 1.1.0. These Flutter packages use BSD 3-Clause terms. Other platform implementations in the graph do not imply another distributed Tokenlogue platform.

<a id="notices-inside-a-package"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Notices inside a package

Android includes Flutter notices and a supplement under `assets/third-party-notices/` inside `assets/app.zip`. It preserves the Android runtime libffi and Dart bridge MIT notices, full OFL, KaTeX copyright, Material Icons declaration and attribution, and tzdata notices. See [libraries and fonts](packaging/notices/README.md).

Linux AppImage includes its index and original license collection under `usr/share/doc/tokenlogue/`. A desktop bundle includes its own notices alongside the application. Use the inventory supplied with your exact package rather than assuming both formats have identical paths. See the [AppImage notice guide](packaging/linux/appimage/notices.md).

<a id="source-materials"></a>

## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Source materials

[Source materials](docs/source-materials.md) describe archives, patches and recipes. The [Android native dependency guide](packaging/android/crypto/README.md) explains its source inputs. Original texts are not translated or edited. Availability of a license or a matching-version archive alone does not establish production of a particular native binary.
