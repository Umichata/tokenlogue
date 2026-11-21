<a id="english"></a>
<a id="lang-en"></a>

<p align="left">
<a href="README.ru.md#russian" title="RU"><img align="right" src="../../../../docs/assets/ui/buttons/v3-en-10762eaa75fd.svg" alt="RU" width="46" height="30"></a> <a href="README.md#english" title="EN"><img align="right" src="../../../../docs/assets/ui/buttons/v3-en-2022af2877c8.svg" alt="EN" width="45" height="30"></a>
<a href="../../../../README.md" title="Home"><img src="../../../../docs/assets/ui/buttons/v3-en-4e7a793b89e3.svg" alt="Home" width="36" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/android" title="Android Python"><img src="../../../../docs/assets/ui/buttons//android-python.svg" alt="Android Python" width="142" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/blob/android-dart/README.md" title="Android Dart"><img src="../../../../docs/assets/ui/buttons//android-dart.svg" alt="Android Dart" width="126" height="30"></a> <a href="https://github.com/Umichata/tokenlogue/tree/linux" title="Linux"><img src="../../../../docs/assets/ui/buttons/v3-en-e31c456bd05c.svg" alt="Linux" width="65" height="30"></a>
</p>

<p align="center"><img src="../../../../docs/assets/tokenlogue-masthead-en-v3.svg" alt="Tokenlogue · OpenRouter + VSEGPT · Linux &amp; Android" width="100%"></p>

<p align="left"><a href="https://github.com/Umichata/tokenlogue/releases/tag/v0.1.1-preview.1" title="Downloads"><img src="../../../../docs/assets/ui/buttons/v3-en-126f5327c4ab.svg" alt="Downloads" width="105" height="30"></a> <a href="../../../../docs/README.md" title="Documentation map"><img src="../../../../docs/assets/ui/buttons/v3-en-2e9bcfa8f92e.svg" alt="Documentation map" width="173" height="30"></a> <a href="../../../../docs/user-guide.md" title="User guide"><img src="../../../../docs/assets/ui/buttons/v3-en-896461d1c049.svg" alt="User guide" width="104" height="30"></a> <a href="../../../../docs/providers.md" title="Providers"><img src="../../../../docs/assets/ui/buttons/v3-en-6aead91ab18a.svg" alt="Providers" width="95" height="30"></a> <a href="../../../../docs/analytics.md" title="Analytics"><img src="../../../../docs/assets/ui/buttons/v3-en-2a1d3373ceeb.svg" alt="Analytics" width="92" height="30"></a></p>

<a id="appimage-runtime"></a>

# AppImage runtime

This runtime mounts or extracts an AppImage filesystem and starts the application. It is included in Tokenlogue packages in AppImage format. The ordinary 0.1.1 desktop bundle does not use this component. You do not need to install the runtime separately to launch an AppImage.

<a id="-inspect-the-source-bundle"></a>
<a id="-source-bundle"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Source bundle

The [build recipe](build_runtime.py) uses the upstream sources and packages pinned in [runtime.lock.json](runtime.lock.json). The AppImage packaging workflow builds the runtime before creating Tokenlogue’s AppImage. Its bundle contains the startup binary, source materials and build metadata.

<img src="../../../../docs/assets/ui/frame-top.svg" width="100%" alt="">

| File or directory | Contents |
| --- | --- |
| `runtime-x86_64` | Startup component |
| `runtime.lock.json` | Pinned versions and source checksums |
| `manifest.json` | File inventory and provenance |
| `SHA256SUMS` | Checksums within the bundle |
| `materials/` | Sources, recipes, patches, original packages and licenses |
| `materials/linked-inputs/` | Saved link inputs |

<img src="../../../../docs/assets/ui/frame-bottom.svg" width="100%" alt="">

In the extracted bundle's root, check the supplied files without running the runtime:
```bash
sha256sum --check SHA256SUMS
```

Checksums establish file integrity, not a digital signature.

<a id="-build-the-runtime"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Build the runtime

Use the project Python environment and Docker or Podman to build the runtime from a clean checkout. The helper obtains pinned inputs and builds with networking disabled.

```bash
uv run --locked python packaging/linux/appimage/fetch_runtime.py \
  --run standalone-local \
  --report build/linux-release/reports/runtime-inputs.json
```

Use a new build name. The [acquisition map](acquisition.lock.json) identifies the pinned packages in official Alpine installation images and a separate dependency archive. The archive supplies three Alpine development packages with their original sources, recipes and licenses.

Alpine packages also use the `.apk` suffix. These files are Linux build inputs and cannot be installed as Android applications. Package signatures and checksums are verified before use. The build installs exact local packages without using mutable repository indexes.

<a id="-components-and-scope"></a>
<a id="-dependencies"></a>

## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Dependencies

This Tokenlogue runtime is based on [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Its saved inputs include libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 and mimalloc2 2.1.7-r0. The bundle preserves original recipes, patches and license texts.

This runtime bundle covers the startup component. It does not provide the complete offline build environment for Tokenlogue. See the <a href="../../../../docs/source-materials.md#english" title="source guide">source guide&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, <a href="../../../../docs/linux-appimage.md#english" title="Linux installation">Linux installation&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> and <a href="../notices.md#english" title="license collection">license collection&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
