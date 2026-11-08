<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="../../../docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="../../../docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../../../README.md" title="Home"><img src="../../../docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="../../../docs/README.md" title="Docs"><img src="../../../docs/assets/ui/buttons/en-0fba477f99e0.svg" alt="Docs" width="61" height="28"></a>
</p>

# Dependency source materials

<a id="english"></a>
<a id="lang-en"></a>

This collection makes the cryptography and Android device-authentication dependencies available for inspection. It contains original archives, licenses and selected upstream build recipes. You do not need to install these materials to use Tokenlogue.

## 📦 Included materials

<img src="../../../docs/assets/ui/frame-top.svg" width="100%" alt="">

| Component | Version | Source and license |
| --- | --- | --- |
| PyCryptodomex | `3.23.0` | [Archive](sources/pycryptodomex-3.23.0.tar.gz), [license and legal notices](licenses/pycryptodomex/LICENSE.rst) |
| CFFI | `2.0.0` | [Archive](sources/cffi-2.0.0.tar.gz), <a href="licenses/cffi/LICENSE" title="MIT license">MIT license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| pycparser | `3.11` | [Archive](sources/pycparser-3.11.tar.gz), <a href="licenses/pycparser/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| Mobile Forge | `0fadbfab0d63d11164030dfddc955ed980e32e2c` | [Archive](sources/mobile-forge-0fadbfab0d63d11164030dfddc955ed980e32e2c.tar.gz), [recipes and patches](recipes/recipes), <a href="recipes/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth | `3.0.2` | [Archive](sources/local_auth-3.0.2.tar.gz), <a href="licenses/local_auth/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_android | `2.2.0` | [Archive](sources/local_auth_android-2.2.0.tar.gz), <a href="licenses/local_auth_android/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_platform_interface | `1.1.0` | [Archive](sources/local_auth_platform_interface-1.1.0.tar.gz), <a href="licenses/local_auth_platform_interface/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_darwin | `2.0.4` | [Archive](sources/local_auth_darwin-2.0.4.tar.gz), <a href="licenses/local_auth_darwin/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| flutter_secure_storage | `10.3.1` | [Archive](sources/flutter_secure_storage-10.3.1.tar.gz), <a href="licenses/flutter_secure_storage/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |
| local_auth_windows | `2.0.2` | [Archive](sources/local_auth_windows-2.0.2.tar.gz), <a href="licenses/local_auth_windows/LICENSE" title="BSD 3-Clause license">BSD 3-Clause license&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> |

<img src="../../../docs/assets/ui/frame-bottom.svg" width="100%" alt="">

The Darwin and Windows packages belong to the resolved Flutter dependency graph. Their platform implementations are not used for Android recovery. Their presence does not indicate an available Tokenlogue package for those platforms.

## ✅ Verify the collection

[sources.lock.json](sources.lock.json) records source URLs, archive hashes and the selected Android wheel filenames. [SHA256SUMS](SHA256SUMS) covers the files in this collection. From this directory, run the following command.
```bash
sha256sum --check SHA256SUMS
```

The [Tokenlogue device adapter](../recovery_bridge.dart) and [template configuration](../recovery_template.py) are Tokenlogue's own source. They connect Android system recovery to the application. Flutter Secure Storage supplies the Android secure-storage implementation used through Flet Secure Storage.

## 🔎 What these materials establish

The original archives and their checksums identify the available source materials. They do not, by themselves, prove how a particular native wheel was built. The collection is not a complete offline Android build environment or a promise of byte-for-byte reproducibility.

The Mobile Forge CFFI recipe names a host libffi dependency without its version. The exact libffi incorporated in the selected CFFI wheel has not been identified. The separately documented libffi in the Android Python runtime does not identify the library inside CFFI. Original CFFI notices remain included.

See <a href="../../../docs/source-materials.md#english" title="source materials and remaining provenance limits">source materials and remaining provenance limits&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> for the wider collection. <a href="../../../THIRD_PARTY_NOTICES.md#english" title="Third-party notices">Third-party notices&nbsp;<img src="../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explain the licensing materials. Documentation changes here do not change the notices inside an already built APK or AppImage.
