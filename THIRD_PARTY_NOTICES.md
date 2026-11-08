<p align="left">
<a href="THIRD_PARTY_NOTICES.ru.md" title="Русский"><img align="right" src="docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="THIRD_PARTY_NOTICES.md" title="English"><img align="right" src="docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="README.md" title="Home"><img src="docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="docs/README.md" title="Documentation map"><img src="docs/assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# Third-party software

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue's own code uses the <a href="LICENSE" title="MIT license">MIT license&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. Its dependencies retain their respective original licenses. The original texts are not translated or replaced by this overview.

<a id="-application-libraries"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Application libraries

<img src="docs/assets/ui/frame-top.svg" width="100%" alt="">

| Component | Version | License | Purpose |
| --- | --- | --- | --- |
| Flet and Flet Secure Storage | 0.86.5 | Apache 2.0 | Interface and platform secure storage |
| HTTPX | 0.28.1 | BSD 3-Clause | OpenRouter HTTPS requests |
| PyCryptodomex | 3.23.0 | BSD 2-Clause and public-domain notices | Local encryption primitives |
| CFFI | 2.0.0 | MIT | Native interface |
| pycparser | 3.11 | BSD 3-Clause | C declaration parsing |

<img src="docs/assets/ui/frame-bottom.svg" width="100%" alt="">

Android secure storage uses flutter_secure_storage 10.3.1. Device recovery uses local_auth 3.0.2, local_auth_android 2.2.0 and local_auth_platform_interface 1.1.0. These Flutter packages use BSD 3-Clause licenses. Other platform implementations in the dependency graph do not imply that a Windows or Apple version is distributed.

<a id="-notices-inside-your-package"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Notices inside your package

Android includes Flutter's notices and a supplemental bundle inside `assets/app.zip`, under `assets/third-party-notices/`. It contains the original Android runtime libffi and Dart bridge MIT notices, complete OFL, KaTeX copyright and Material Icons declaration and attribution. See the <a href="packaging/notices/README.md#english" title="library and font texts">library and font texts&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

Linux includes its component index, original license collection and font supplement under `usr/share/doc/tokenlogue/`. The <a href="packaging/linux/appimage/notices.md#english" title="AppImage license guide">AppImage license guide&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explains these files and the separate runtime materials. Always use the index supplied with your particular package to identify its actual components.

<a id="-sources-and-provenance"></a>
## <img src="docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Sources and provenance

The <a href="docs/source-materials.md#english" title="source guide">source guide&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> identifies the available archives, patches and recipes. The <a href="packaging/android/crypto/README.md#english" title="Android native-library overview">Android native-library overview&nbsp;<img src="docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explains native inputs. Some source-to-binary links remain incomplete, including the actual libffi inside CFFI. The presence of a license or a matching-version source archive alone does not prove how a particular binary was produced.

<p align="left"><a href="README.md#english"><img src="docs/assets/ui/buttons/en-e3d813162a8e.svg" alt="Back to Tokenlogue" width="168" height="28"></a></p>
