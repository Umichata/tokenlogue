<p align="left">
<a href="README.ru.md" title="Русский"><img align="right" src="../../../../docs/assets/ui/buttons/en-0380058e71b5.svg" alt="Русский" width="46" height="28"></a>
<a href="README.md" title="English"><img align="right" src="../../../../docs/assets/ui/buttons/en-927deb529a3e.svg" alt="English" width="45" height="28"></a>
<a href="../../../../docs/README.md" title="Documentation map"><img src="../../../../docs/assets/ui/buttons/en-63f7d280c22c.svg" alt="Documentation map" width="195" height="38"></a> <a href="../../../../README.md" title="Home"><img src="../../../../docs/assets/ui/buttons/en-2c296d10dfa5.svg" alt="Home" width="34" height="28"></a>
</p>

# The AppImage runtime

<a id="english"></a>
<a id="lang-en"></a>

The runtime mounts or extracts the filesystem inside an AppImage and starts the application. It is already included in Tokenlogue for Linux. You do not need to install or launch it separately.

<a id="-inspect-the-source-bundle"></a>
## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Inspect the source bundle

The [published runtime ZIP](https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/appimage-runtime-34749438406-1.zip) contains the startup binary and its source materials. This stable filename identifies the existing bundle. It is not an Android package or a newer Tokenlogue application release.

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

<a id="-components-and-scope"></a>
## <img src="../../../../docs/assets/ui/section-mark.svg" alt="" width="20" height="20"> Components and scope

This Tokenlogue runtime is based on [AppImage type2-runtime](https://github.com/AppImage/type2-runtime/tree/caf24f9f712084686bfc24a70b75e50df0aefb9c). Its saved inputs include libfuse 3.15.0, squashfuse 0.5.2, musl 1.2.5-r11, GCC 14.2.0-r4, zlib 1.3.2-r0, zstd 1.5.6-r2 and mimalloc2 2.1.7-r0. The bundle preserves original recipes, patches and license texts.

Runtime materials do not cover every dependency of the full application. A complete offline rebuild of Tokenlogue is not established. See the <a href="../../../../docs/source-materials.md#english" title="source guide">source guide&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>, <a href="../../../../docs/linux-appimage.md#english" title="Linux installation">Linux installation&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a> and <a href="../notices.md#english" title="license collection">license collection&nbsp;<img src="../../../../docs/assets/ui/inline-link.svg" alt="" width="17" height="17"></a>.
