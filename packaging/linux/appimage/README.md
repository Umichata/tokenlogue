# Diagnostic AppImage infrastructure

This directory builds an unsigned diagnostic AppImage from the existing
`build/linux/` Flet bundle. It never rebuilds the Flet application and performs
all transformations on a staging copy under `build/appimage/`.

The staged desktop entry omits the optional `Version` key in `[Desktop Entry]`
because Ubuntu 22.04's desktop-file-utils 0.26 rejects `Version=1.5`.
The system desktop source is unchanged; AppImage keeps `Exec=tokenlogue`,
`Icon=tokenlogue`, localized metadata, and no `TryExec`. Staging conversion
runs before linuxdeploy, and desktop-file-validate remains mandatory.

## Pinned tools

`tools.lock` pins exact tagged Linux x86_64 release assets for linuxdeploy,
appimagetool, and patchelf. Each asset is verified with SHA-256 before use.
The digests were obtained from the GitHub Releases API, but the releases do not
publish artifact attestations or separately signed checksums. Initial publisher
provenance is therefore trust-on-first-use (TOFU).

The appimagetool asset is downloaded from the exact `1.9.1` tag URL. Its
embedded `--version` text calls itself a continuous build; this infrastructure
does not use the mutable `/continuous/` download URL and relies on the pinned
tag, asset name, and digest.

AppImage creation uses the runtime embedded at the start of that same tagged
appimagetool asset. `fetch_tools.sh` verifies its reported offset, extracts the
exact `944632`-byte prefix, and checks its separately pinned SHA-256. The build
passes this file through `--runtime-file`, so appimagetool cannot fetch the
mutable continuous runtime while packaging.

## Usage

Run from any working directory with all HTTP, HTTPS, and ALL proxy variables
unset:

```bash
packaging/linux/appimage/fetch_tools.sh
packaging/linux/appimage/build_appimage.sh
```

Outputs:

```text
build/appimage/Tokenlogue.AppDir/
build/appimage/Tokenlogue-<version>-x86_64.AppImage
```

The generated artifact is diagnostic, unsigned, and has no update metadata.
It is not a release artifact because the source bundle was built on Linux Mint
with a GLIBC 2.38 requirement, bundled `anyio` differs from `uv.lock`, ordinary
FUSE execution and cross-distribution testing are pending, and tool provenance
currently includes TOFU.

## Optional JNI library

The Flutter dependency package `jni` may produce `lib/libdartjni.so` on runners
with a JDK installed. Tokenlogue does not use a JVM on Linux. Source-bundle
verification permits the observed Temurin 11 server RUNPATH only for that exact
file and retains its ABI and ldd diagnostics. `build_appimage.sh` removes only
`usr/lib/tokenlogue/lib/libdartjni.so` from the AppDir staging copy before
linuxdeploy; an absent file is allowed. The source bundle and `libdart_bridge.so`
are preserved. Final AppDir and AppImage verification rejects `libdartjni.so`,
`libjvm.so`, and JDK/JRE paths: the AppImage must not depend on Java.

## Ubuntu 22.04 baseline workflow

`.github/workflows/build-linux.yml` is a manual-only workflow for a future
clean build on a GitHub-hosted Ubuntu 22.04 x86_64 runner. It has not yet been
run. The pipeline exports production-only pip constraints directly from
`uv.lock`, creates a separate locked production environment, supplies the
constraints to Flet through command-scoped `PIP_CONSTRAINT`, and rejects any
package inventory mismatch.

The resulting bundle, AppDir, and extracted AppImage must not require a GLIBC
version newer than `GLIBC_2.35`. The workflow also records ELF, RUNPATH, ldd,
toolchain, metadata, and isolated headless smoke-test reports. Its artifact is
unsigned, remains diagnostic only, and is not promoted to a release.
