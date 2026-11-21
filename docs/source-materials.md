<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="source-materials.ru.md#russian" title="RU"><img align="right" src="assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="source-materials.md#english" title="EN"><img align="right" src="assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="assets/ui/buttons/android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="assets/ui/buttons/android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="user-guide.md" title="User guide"><img src="assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="providers.md" title="Providers"><img src="assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="analytics.md" title="Analytics"><img src="assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="source-code-and-dependencies"></a>

# Source code and dependencies


> **[0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1)** includes the [Python APK +56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) and [Dart APK +18](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk) for Android ARM64 and the [desktop bundle +56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz) for Linux x86_64. Check the platform requirements and checksum before installing.


<a id="choose-materials-for-your-package"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Choose materials for your package

For the [Python APK 0.1.1 (+56)](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk) and [Linux bundle 0.1.1+56](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz), use the index supplied with [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1). The [Android](android.md#en-install) and [Linux](linux-appimage.md#en-download) guides identify the exact packages and checksums.

For the Android Dart sources and build settings, see the [Dart build guide](https://github.com/Umichata/tokenlogue/blob/android-dart/apps/android_dart/README.md).

`Tokenlogue-0.1.1+56-build-sources.tar.gz` contains the shared sources and packaging for the Python APK and Linux bundle. Provenance records the exact commit, tree, actual dependency graphs and inputs. A later documentation revision does not become an input to an already built binary.

The application source archive, original dependency sources and evidence of binary production have different roles. Matching a version or source checksum does not prove that a particular wheel was compiled from it. Source availability is separate from complete binary provenance.

Tokenlogue's application code uses the [MIT License](../LICENSE). Third-party components keep their original terms. Ready-to-use APK and Linux bundle packages are separate downloads. You do not need source archives or build tools to run the application.

<a id="-application-sources"></a>
<a id="application-sources"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Application sources

On [0.1.1 Preview](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1), select [`Tokenlogue-0.1.1+56-build-sources.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-build-sources.tar.gz) and verify it against [the release manifest](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/SHA256SUMS). The archive contains application sources, locks, packaging recipes and the selected native wheel materials. It represents the sources of the delivered builds. Separate current documentation may have a newer revision.

To run the app, download the [Python APK](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-arm64-v8a-v56.apk), [Dart APK](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-android-dart-arm64-v8a-v18.apk) or [Linux bundle](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1%2B56-linux-x86_64-bundle.tar.gz). Dependency archives are for working with the sources.

<a id="-find-the-matching-collection"></a>
<a id="dependency-archive"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Dependency archive

| File | Purpose |
| --- | --- |
| [`Tokenlogue-0.1.0-dependency-sources.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-dependency-sources.tar.gz) | Identified third-party sources, original notices, modifications and recipes in a deduplicated collection. |
| [`SOURCE_MATERIALS.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/SOURCE_MATERIALS.json) | Versions, component mappings, relative material paths, sizes and SHA-256 values. It also records the scope of source and binary-provenance evidence. |
| [`Tokenlogue-0.1.1-source-additions.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/Tokenlogue-0.1.1-source-additions.tar.gz) | Six exact additional source archives, including tzdata 2026.6 and Android url_launcher_android 6.3.35. |
| Current release [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.1-preview.1/SHA256SUMS) | Checksums of the new downloads. Use the earlier manifest below for the reused base archive. |

The dependency archive has no extra outer directory. It contains a bilingual `README.md`, `SOURCE_MATERIALS.json`, `BUILD_INPUTS.json`, `RECONSTRUCTION.json`, `SHA256SUMS` and the original files under `materials/<SHA-256>/<original filename>`. An identical file is stored once and can be mapped to several components. The index identifies the exact archive member when a component's source or notice is inside a retained archive.

`BUILD_INPUTS.json` identifies separately obtained compilers, runtimes and tools by source, size and checksum. It includes upstream downloads, selected packages from official Alpine installation images and the [Linux runtime build inputs](https://github.com/Umichata/tokenlogue/releases/tag/runtime-build-inputs-20261110) packaged by Tokenlogue. Obtaining these inputs may require internet access.

The base archive is reused unchanged. Save it and the [earlier SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) from 0.1.0 together. Use the current release manifest for the new small supplement. Verify the selected archive before extracting it. This command requires Bash and SHA-256 tools.

```bash
set -o pipefail
file='Tokenlogue-0.1.0-dependency-sources.tar.gz'
awk -v wanted="$file" '$2 == wanted { entry = $0; count++ } END { if (count != 1) exit 1; print entry }' SHA256SUMS |
  sha256sum --check -
```

The selected file must report `OK`. A missing or duplicate manifest entry, missing file or checksum mismatch fails the check. Then extract into a new empty directory and verify the collection's own manifest.

```bash
mkdir tokenlogue-dependency-sources &&
tar --extract --gzip --file Tokenlogue-0.1.0-dependency-sources.tar.gz \
  --directory tokenlogue-dependency-sources --no-same-owner --no-same-permissions &&
(cd tokenlogue-dependency-sources && sha256sum --check SHA256SUMS)
```

The release manifest checks the downloaded archive. The inner manifest checks its extracted members. Keep original source archives and legal texts unchanged.

<a id="en-run-from-source"></a>
<a id="-run-from-source-on-linux"></a>
<a id="run-current-sources-on-linux"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Run current sources on Linux

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). Open a terminal in the extracted project directory containing `pyproject.toml` and `uv.lock`. The [Linux desktop and key-store requirements](linux-appimage.md#english) also apply.

```bash
uv sync --locked
uv run --locked flet run
```

These commands run the source application and do not create an APK or AppImage. Preparing the environment and downloading Flet desktop components may require internet access. For packaging, use the project recipes and exact locks from the matching project archive. The [Linux packaging guide](../packaging/linux/appimage/README.md#english), [AppImage startup runtime recipe](../packaging/linux/appimage/runtime/README.md#english) and [Android native dependency guide](../packaging/android/crypto/README.md#english) describe the corresponding components.

<a id="-what-the-available-materials-establish"></a>
<a id="component-provenance"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Component provenance

The current packaging recipe selects the project’s [source-built native wheels](../packaging/native_wheels/README.md#english). These cover Android CFFI 2.0.0, PyCryptodomex 3.23.0 and msgpack 1.1.2, plus Linux CFFI 2.0.0 and PyCryptodomex 3.23.0. Their registry binds the exact wheel bytes to the recorded recipe, source archives, build tools and patches. Both CFFI builds statically link libffi 3.4.4. Android’s two libffi patches and the unpatched Linux source are identified separately. The Python runtime’s libffi remains a distinct component.

The earlier APK55 and Linux bundle +55 used different wheels. Their incomplete producer links and unidentified CFFI libffi remain historical limitations of those files. Building replacements does not establish missing facts about the older binaries. Check the provenance accompanying your exact package to distinguish the inputs.

The component index describes both reusable source materials and package-specific additions. A matching source version and checksum identify an archive. Recorded builds and final-package checks establish the selected replacement files, but do not claim independent reproduction of every binary or a complete offline SDK distribution.

<a id="-licenses-and-older-collections"></a>
<a id="licenses-and-notices"></a>

## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Licenses and notices

The [package license guide](../packaging/linux/appimage/notices.md#english) and [libraries and fonts](../packaging/notices/README.md#english) explain the notices included with the application. Original licenses and copyright statements are preserved in their original language. Component sources and their build metadata are listed separately.
