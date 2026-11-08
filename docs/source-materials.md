<p align="left">
<a href="source-materials.ru.md" title="Русский"><img align="right" src="assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="source-materials.md" title="English"><img align="right" src="assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../README.md" title="Home"><img src="assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a> <a href="README.md" title="Documentation map"><img src="assets/ui/buttons/en-992f2873a82b.svg" alt="Documentation map" width="174" height="28"></a>
</p>

# Source materials

<a id="english"></a>
<a id="lang-en"></a>

Tokenlogue is available under the <a href="../LICENSE" title="MIT License">MIT License&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a>. The repository contains the application, its dependency locks and packaging recipes. Third-party components retain their own licenses.

<a id="-application-sources"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Application sources

Use the source revision identified in your package's `PROVENANCE.json`. A later repository revision may include different code or documentation. The application source archive is distinct from the dependency collections below.

<a id="en-run-from-source"></a>

<a id="-run-from-source-on-linux"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Run from source on Linux

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). Download the project sources and open a terminal in the directory containing `pyproject.toml` and `uv.lock`. The <a href="linux-appimage.md#english" title="Linux desktop and key-store requirements">Linux desktop and key-store requirements&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> also apply.
```bash
uv sync --locked
uv run --locked flet run
```

These commands run the source application. They do not create an AppImage or APK. Preparing the environment and downloading Flet desktop components may require internet access. Ready-to-use packages do not require a separate Python or Flutter installation.

<a id="-find-the-matching-collection"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Find the matching collection

Start with the `SOURCE_MATERIALS.md` and `SOURCE_MATERIALS.json` supplied with your package. The JSON index maps each identified component to an exact archive member, version, size and SHA-256. Keep the named archives unchanged. A shared dependency collection can remain useful for a newer package without making its old application snapshot current.

The <a href="https://github.com/Umichata/tokenlogue/releases" title="Releases page">Releases page&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> contains published downloads. The established source collections are listed below.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Collection | What it provides |
| --- | --- |
| [Published baseline](https://github.com/Umichata/tokenlogue/releases/tag/v0.1.0-linux-preview.986c6ad) | Seven ordered parts with earlier shared dependencies, source recipes and the runtime bundle |
| [Published supplement](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.2b1f7d3/Tokenlogue-2b1f7d3-source-supplement.tar.gz) | Six updated Dart dependency archives and the application snapshot of that historical Linux release |
| Package-specific additions | The additional source archives, patches and recipes identified by the index supplied with a newer package |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

The supplement is 745,485 bytes. Its SHA-256 is `66b6f130c47f4a58d7708fc7c528574040c6c27d5511b8bbe1865d1412abc29e`. Its application snapshot describes its own release. It does not replace the source revision named by a newer package.

<a id="-restore-the-published-baseline"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Restore the published baseline

Download all seven parts into the same directory. Keep their exact names. Their total size is 12,338,636,800 bytes. Allow at least 30 GB for the downloaded parts and extracted materials.

<img src="assets/ui/frame-top.svg" width="100%" alt="">

| Part | Bytes |
| --- | --- |
| [1 · Tokenlogue-986c6ad-source-materials.tar.part001](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part001) | 2,000,000,000 |
| [2 · Tokenlogue-986c6ad-source-materials.tar.part002](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part002) | 2,000,000,000 |
| [3 · Tokenlogue-986c6ad-source-materials.tar.part003](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part003) | 2,000,000,000 |
| [4 · Tokenlogue-986c6ad-source-materials.tar.part004](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part004) | 2,000,000,000 |
| [5 · Tokenlogue-986c6ad-source-materials.tar.part005](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part005) | 2,000,000,000 |
| [6 · Tokenlogue-986c6ad-source-materials.tar.part006](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part006) | 2,000,000,000 |
| [7 · Tokenlogue-986c6ad-source-materials.tar.part007](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/Tokenlogue-986c6ad-source-materials.tar.part007) | 338,636,800 |

<img src="assets/ui/frame-bottom.svg" width="100%" alt="">

Save [SOURCE_PARTS.SHA256SUMS](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.SHA256SUMS) and [SOURCE_PARTS.json](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/SOURCE_PARTS.json) beside the parts. Check the individual files and the combined stream before extracting.
```bash
sha256sum --check SOURCE_PARTS.SHA256SUMS
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | sha256sum
```

The second command requires Bash. Its result must be `d66c43a31d810431af18defdc1642f235d072bdec9c9c281b3ed3dc3a72d4cf2`. After both checks succeed, extract into a new directory without creating another complete tar file.
```bash
cat Tokenlogue-986c6ad-source-materials.tar.part00{1..7} | tar --extract --file - --no-same-owner --no-same-permissions
```

The baseline already contains the historical source ZIP and `appimage-runtime-34749438406-1.zip`. The [separate runtime ZIP](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) is an alternative download of the same member. It is 391,916,671 bytes with SHA-256 `a9869ba745218ea8b0e2dec0c3da6af15b4d28fbd6e1ec1170afcadb758b06c9`. You do not need to download it twice.

<a id="-what-the-available-materials-establish"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> What the available materials establish

Identifying an intact source archive is different from establishing which sources produced a particular binary. The current Android and Linux collections include source archives and recipes for the following components, but their exact selected wheel bytes are not fully linked to all actual source revisions, patches and build inputs.

- Android CFFI 2.0.0, PyCryptodomex 3.23.0 and msgpack 1.1.2.
- Linux CFFI 2.0.0 and PyCryptodomex 3.23.0.

The exact libffi source and patches inside the selected CFFI wheels are not fully identified. Android runtime libffi 3.4.4 and Linux Python runtime libffi 3.4.8 are separate components. The Linux CFFI recipe names libffi 3.4.6, which alone does not prove the library in the wheel.

Retained compiler binaries are build inputs rather than compiler source. The collection does not establish a complete offline rebuild or independent reproduction of every native dependency. An archive with the same version number and matching download checksum does not establish that connection by itself. These technical limits are separate from whether the application runs on a particular device.

<a id="-licenses-and-older-collections"></a>
## <img src="assets/ui/section-mark.svg" alt="" width="20" height="20"> Licenses and older collections

The <a href="../packaging/linux/appimage/notices.md#english" title="license guide">license guide&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> explains where to find the original notices included in the packages. The <a href="releases/14b87ac-source-materials.md#english" title="historical source collection">historical source collection&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> and <a href="releases/v0.1.0-linux-preview.1.md#english" title="older Linux preview record">older Linux preview record&nbsp;<img src="assets/ui/inline-link.svg" alt="" width="17" height="17"></a> describe their own files. Their earlier versions and limitations do not automatically describe newer packages.

<p align="left"><a href="../README.md#english"><img src="assets/ui/buttons/en-e3d813162a8e.svg" alt="Back to Tokenlogue" width="168" height="28"></a></p>
