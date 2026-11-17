[English](THIRD_PARTY_NOTICES.md#english) · [Русский](THIRD_PARTY_NOTICES.ru.md#russian)

<a id="english"></a>
<a id="lang-en"></a>

# Third-party notices

Tokenlogue's application code uses the [MIT license](LICENSE). Dependencies retain their original terms. This overview does not replace original notices.

## Components

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

## Notices inside a package

Android includes Flutter notices and a supplement under `assets/third-party-notices/` inside `assets/app.zip`. It preserves the Android runtime libffi and Dart bridge MIT notices, full OFL, KaTeX copyright, Material Icons declaration and attribution, and tzdata notices. See [libraries and fonts](packaging/notices/README.md).

Linux AppImage includes its index and original license collection under `usr/share/doc/tokenlogue/`. A desktop bundle includes its own notices alongside the application. Use the inventory supplied with your exact package rather than assuming both formats have identical paths. See the [AppImage notice guide](packaging/linux/appimage/notices.md).

## Source materials

[Source materials](docs/source-materials.md) describe archives, patches and recipes. The [Android native dependency guide](packaging/android/crypto/README.md) explains its source inputs. Original texts are not translated or edited. Availability of a license or a matching-version archive alone does not establish production of a particular native binary.
