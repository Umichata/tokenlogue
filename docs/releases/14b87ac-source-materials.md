<p align="left">
<a href="14b87ac-source-materials.ru.md" title="Русский"><img align="right" src="../assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="14b87ac-source-materials.md" title="English"><img align="right" src="../assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../../README.md" title="Home"><img src="../assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>&nbsp;<a href="../README.md" title="Docs"><img src="../assets/ui/buttons/en-0fba477f99e0.svg" alt="Docs" width="61" height="28"></a>
</p>

# Historical source collection

<a id="english"></a>
<a id="lang-en"></a>

This collection was assembled on 10 September 2026 for the <a href="v0.1.0-linux-preview.1.md#english" title="earlier Linux preview">earlier Linux preview&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. It preserves that version's source materials. It is also retained inside the later [published baseline](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad), where selected unchanged dependencies can be reused.

## 🗂️ Identify the archive

<img src="../assets/ui/frame-top.svg" width="100%" alt="">

| Archive detail | Value |
| --- | --- |
| File | `Tokenlogue-14b87ac-source-materials.zip` |
| Size | 440,966,310 bytes |
| SHA-256 | `744b0e7a6d82566324ff9555be2f33bcc1c732ef99caf55d1ff841b7d0870e54` |
| Application source | `14b87ac03e5c03c2ed9c4acf6caae29daa39d20e` |
| Corresponding AppImage SHA-256 | `edbdaf7c10ecd336b6c9896a893be55e9d70f241c2e16eb987ea7eeb82c3f483` |

<img src="../assets/ui/frame-bottom.svg" width="100%" alt="">

The application binary is not inside this archive. There is no separate ZIP download linked here. To obtain its retained copy, follow the <a href="../source-materials.md#english" title="baseline restoration guide">baseline restoration guide&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.

## 🔍 Contents and integrity

The ZIP includes Tokenlogue sources, Ubuntu source packages and packaging, CPython 3.12.14, Python Build Standalone recipes, Python source distributions, Dart packages, Flet 0.86.5, Flutter 3.44.8, Dart bridge 1.9.0, font inputs and older runtime materials.

The recorded Flutter engine revision is `0cd610717bde95fd88343c64f81c11ba4e5c0010`. The included `source-materials.json` records file sizes and SHA-256 values. `coverage.json` maps materials to components.

After extracting the ZIP, open a terminal in `Tokenlogue-14b87ac-source-materials` and run its included checker with Python 3.
```bash
python3 verify_materials.py
```

The checker verifies the supplied files against the manifest. It does not establish that every file needed for a complete rebuild is present.

## 📌 Scope of this historical collection

The earlier Ubuntu libgcrypt20 sources have a [retained Launchpad publication](https://api.launchpad.net/1.0/ubuntu/+archive/primary/+sourcepub/18430640). The [historical type2-runtime source revision](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c) identifies the older upstream code. The ZIP contains Alpine recipes that may correspond to the older runtime, but no confirmed inventory of the packages used to build it.

The Flutter engine dependency inventory contains 109 entries. Some external Git and CIPD inputs are not included. Offline engine compilation, compiler bootstrap, relinking, font subsetting and a whole-application rebuild from this ZIP alone are not established.

Later packages have different application code, runtime inputs and some dependency versions. For example, the subsequent baseline replaces Dart `archive` 4.2.0 with 4.3.0, Dart `image` 4.9.2 with 4.10.1, `flutter_secure_storage_linux` 3.0.2 with 3.0.3 and Ubuntu `libgcrypt20` 1.9.4-3ubuntu3.2 with 1.9.4-3ubuntu3.3. The historical ZIP keeps its original versions.

Use the <a href="../source-materials.md#english" title="source materials guide">source materials guide&nbsp;<img src="../assets/ui/inline-link.svg" alt="" width="17" height="17"></a> and the index supplied with your package to select matching files.
