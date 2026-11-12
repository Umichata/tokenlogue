<p align="left">
<a href="source-materials.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="source-materials.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# Source code and dependencies

<a id="english"></a>
<a id="lang-en"></a>

<a id="en-preview-status"></a>
> **0.1.0 Preview.** Source archives accompany the application packages in Releases. Downloads are unavailable while the release remains a draft.

Tokenlogue's application code uses the [MIT License](../LICENSE). Third-party components keep their original terms. Ready-to-use APK and AppImage packages are separate downloads. You do not need source archives or build tools to run the application.

<a id="-application-sources"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Application sources

Use [`PROVENANCE.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/PROVENANCE.json) to select the source archive for each package. Android and Linux share the application core and use separate packaging revisions. The manifest records the exact commits, source trees and package checksums.

The [Releases page](https://github.com/Umichata/tokenlogue/releases) lists application packages and source archives. Third-party sources are supplied separately in a dependency archive with a component index.

<a id="-find-the-matching-collection"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Dependency archive

| File | Purpose |
| --- | --- |
| [Android project sources](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-eafb093-android-project-sources.tar.gz) | Exact tracked application sources, locks and packaging for the supplied APK. |
| [Linux project sources](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-a981db9-linux-project-sources.tar.gz) | Exact tracked application sources, locks and packaging for the supplied AppImage. |
| [`Tokenlogue-0.1.0-dependency-sources.tar.gz`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/Tokenlogue-0.1.0-dependency-sources.tar.gz) | Identified third-party sources, original notices, modifications and recipes in a deduplicated collection. |
| [`SOURCE_MATERIALS.json`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SOURCE_MATERIALS.json) | Versions, component mappings, relative material paths, sizes and SHA-256 values. It also records the scope of source and binary-provenance evidence. |
| [`SHA256SUMS`](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-preview.a981db9/SHA256SUMS) | Checksums of the release downloads. |

The dependency archive has no extra outer directory. It contains a bilingual `README.md`, `SOURCE_MATERIALS.json`, `BUILD_INPUTS.json`, `RECONSTRUCTION.json`, `SHA256SUMS` and the original files under `materials/<SHA-256>/<original filename>`. An identical file is stored once and can be mapped to several components. The index identifies the exact archive member when a component's source or notice is inside a retained archive.

`BUILD_INPUTS.json` identifies separately obtained compilers, runtimes and tools by source, size and checksum. It includes upstream downloads, selected packages from official Alpine installation images and the [Linux runtime build inputs](https://github.com/Umichata/tokenlogue/releases/tag/runtime-build-inputs-20261110) packaged by Tokenlogue. Obtaining these inputs may require internet access.

Save the dependency archive and the release's `SHA256SUMS` in one directory. Verify the selected archive before extracting it. This command requires Bash and SHA-256 tools.

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
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Run from source on Linux

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). Open a terminal in the extracted project directory containing `pyproject.toml` and `uv.lock`. The [Linux desktop and key-store requirements](linux-appimage.md#english) also apply.

```bash
uv sync --locked
uv run --locked flet run
```

These commands run the source application and do not create an APK or AppImage. Preparing the environment and downloading Flet desktop components may require internet access. For packaging, use the project recipes and exact locks from the matching project archive. The [Linux packaging guide](../packaging/linux/appimage/README.md#english), [Linux startup runtime recipe](../packaging/linux/appimage/runtime/README.md#english) and [Android native dependency guide](../packaging/android/crypto/README.md#english) describe the corresponding components.

<a id="-what-the-available-materials-establish"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Component provenance

Source-to-binary correspondence is not fully documented for Android CFFI 2.0.0, PyCryptodomex 3.23.0 and msgpack 1.1.2, or for Linux CFFI 2.0.0 and PyCryptodomex 3.23.0. The exact libffi revision and patches inside the selected CFFI wheels remain unidentified; the libffi in the Python runtime is a separate component.

The component index describes the available source materials. A matching source version and checksum identify an archive, but do not establish independent reproduction of every native binary or a complete offline build environment.

<a id="-licenses-and-older-collections"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Licenses and notices

The [package license guide](../packaging/linux/appimage/notices.md#english) and [libraries and fonts](../packaging/notices/README.md#english) explain the notices included with the application. Original licenses and copyright statements are preserved in their original language. Component sources and their build metadata are listed separately.

<p align="left"><a href="../README.md#english"><img src="assets/ui/buttons/en-e3d813162a8e.svg" alt="Back to Tokenlogue" width="168" height="28"></a></p>
