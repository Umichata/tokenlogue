# Standalone AppImage runtime x86_64

This recipe builds an unofficial runtime independently of Tokenlogue packaging.
It does not change the runtime extracted from appimagetool 1.9.1 by the existing
application workflow. No equality with that historical binary is claimed.
All downloads, working directories and reports live in `build/appimage/runtime/`.
Python helpers use only the standard library and support Python 3.10 and later.

## Locked inputs

`runtime.lock.json` records 152 files and the complete 77-package APK inventory,
including the 15 packages inherited from the selected image. Each APK has its
name, exact version, actual package architecture, repository, origin, aports
commit, size and SHA-256. `index_arch` records the repository index architecture
separately: Alpine publishes some `noarch` APKs in the x86_64 index. For an
unchanged inherited package the expected installed database retains the base
image's architecture field. Unexpected inventory entries fail verification.

| Input | Pin |
| --- | --- |
| type2-runtime | `caf24f9f712084686bfc24a70b75e50df0aefb9c` |
| libfuse | 3.15.0, archive SHA-256 `70589cfd5e1cff7ccd6ac91c86c01be340b227285c5e200baa284e401eea2ca0` |
| squashfuse | 0.5.2, archive SHA-256 `db0238c5981dabbd80ee09ae15387f390091668ca060a7bc38047912491443d3` |
| Alpine | `docker.io/library/alpine@sha256:f27cad9117495d32d067133afff942cb2dc745dfe9163e949f6bfe8a6a245339`, linux/amd64, observed as 3.21.7 |
| appimagetool | 1.9.1, SHA-256 `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0` |

The exact OCI manifest, config and layer are retained and checked. The image
config digest must also match the image loaded into the engine. APK signatures
are checked by the base image's native `apk verify`, with the public keys from
that pinned image, before offline installation. No untrusted-package option is
used. Both base and final installed inventories are checked.

The input observations were made on 2026-09-12 using the official Docker Hub
registry, Alpine v3.21 main/community repositories and the upstream source URLs
in the lock. SHA-256 values were calculated from downloaded bytes. The three
initial source hashes and appimagetool hash were checked against the existing
pins. The source archive SHA-256 for type2-runtime is
`944e9bb5c587818c54fec3231067ec03d67b8062c68278f4ca99d504216117be`.
The unmodified upstream libfuse patch has SHA-256
`1c7fd9e26717545a476b226b083a9f9d05676c180edbd71a04bbd8a73599dc44`.

APK `.PKGINFO` origin/version/commit fields select these aports recipes:

| Origin | Version | aports commit |
| --- | --- | --- |
| musl | 1.2.5-r11 | `21cafa1183cf7501d3f1744994d221c038436e45` |
| zlib | 1.3.2-r0 | `2b38f55109add14f4f99a974c2fdf421b6b9e9e9` |
| zstd | 1.5.6-r2 | `5c2ddf18f193dafdd25ae7391d96c7e30766eecd` |
| mimalloc2 | 2.1.7-r0 | `5a1a5dc3216a69e3cd66a57ee07cb5ef01b8be39` |
| gcc (libgcc and CRT) | 14.2.0-r4 | `1a03a2a9c9e77f1a07d48b6f6805e72c8c63c03f` |

Recipe files were read from the exact aports commit archives; their archive
hashes and URLs are retained as provenance in the lock. Normal fetching retrieves
the pinned individual recipe files. Every SHA-512 entry in each APKBUILD is
checked against the retained source archive or patch. APKBUILD is read as text,
never sourced on the host. Compiler bootstrap reconstruction is outside scope;
the complete binary tool inventory is retained. These observations provide
integrity and origin checks, not publisher attestations or a claim of rebuilding
the Alpine packages from source.

Changing the lock is an explicit review operation: inspect the chosen manifest
and signed APK metadata, collect the full dependency closure and inherited
inventory, collect aports recipes at those commits, verify all recipe source
checksums, then review the new lock diff. None of the ordinary commands updates
pins, resolves newer package versions or accepts a new checksum. Mutable Alpine
index URLs and retired APK versions can make a fresh fetch fail; retain the
verified input artifact. Do not replace a failed input automatically. Reused
cache files are hashed again, including before container builds.

## Run

Use an already available Docker daemon or Podman as a normal user. No host
packages, groups or permissions are changed by these helpers. Docker preparation
uses the legacy builder and an inspected local image tag to avoid BuildKit
registry metadata resolution; Podman uses `--pull=never`. If the engine does not
provide this mode, preparation fails rather than resolving another image.

From the repository root, with a new attempt name:

```bash
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py init --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py fetch --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py prepare --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py build-one --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py build-two --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py compare --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py verify --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py smoke --run manual-1
uv run --locked python packaging/linux/appimage/runtime/build_runtime.py bundle --run manual-1
```

Pass `--engine podman` to the commands that use the engine if needed. Only
`fetch` accesses public network inputs or pulls an image. `fetch --inputs-only`
and `verify-inputs` allow host-side integrity/source checks without an engine;
they explicitly leave native APK signature verification and all runtime tests
NOT_RUN. They cannot produce a successful runtime bundle.

`prepare` installs only the supplied, signature-verified APKs with no network
and no APK repositories. Both compilations use separate fresh work directories
and unprivileged containers with read-only roots, no network, no extra
capabilities and only input/recipe/output mounts. Object files are not shared.
The fixed epoch is `1762559451` (the upstream commit's committer time), locale C,
timezone UTC and umask 022. The recipe sets x86-64 baseline compiler flags and
prefix maps; it does not use `-march=native`. Alpine's binary libraries remain
separate, recorded inputs; their ISA choices are those of the pinned APKs.

Libfuse and squashfuse are built into a private prefix. The upstream Makefile
patch only adds explicit include/link/reproducibility flags. The version is
`tokenlogue-unofficial-<full upstream commit>-recipe-<recipe SHA-256>` and does
not depend on a `.git` directory in the source archive. The upstream debug
split, strip, debuglink and final AppImage magic operations are retained.

The checker parses ELF headers, program/dynamic/section tables, entry point,
PIE flags, interpreter/library/version requirements and embedded paths. The
link map records every `LOAD`, including libc, GCC CRT, compiler support
archives and empty archives. Linked APK files are compared byte for byte with
the owning locked package's payload. Unknown ownership/source coverage remains
an explicit `REVIEW_REQUIRED` item. The known required component set must still
be present. Link maps, linked input copies/hashes, installed inventory, compiler
and other tool versions, flags, readelf output and version output are saved.
The runtime's preprocessed translation unit and compiler header dependency file
are also retained; exact system headers are available in the original dev APKs.

`smoke` uses the pinned appimagetool with an explicit `--runtime-file`. It checks
that the generated AppImage contains the new runtime, allowing only the normal
16-byte `.digest_md5` update. It then checks extraction and executes the test
AppImage with `--appimage-extract-and-run`, verifies arguments including an empty
argument and Unicode, and requires the test marker. All this happens offline in
temporary test data. FUSE is NOT_RUN in this container because it has no FUSE
device/mount setup; extract-and-run is not a FUSE test. Ordinary FUSE launch
requires a separate suitable environment and is not enabled by granting the
build container additional privileges.

## Artifacts and the next integration

The manual workflow `build-appimage-runtime.yml` uses the project's existing
full checkout/upload action SHA pins. It publishes only Actions artifacts with
14-day retention. It does not create releases/tags, sign files, access application
data, or run the application workflows. Reports and both available runtimes are
uploaded on failure unless the run was cancelled. All mandatory stages must
actually pass before the final artifact is assembled; a missing stage fails.

Each attempt has its own `runs/<name>/` directory. Existing attempts and results
are preserved; use a new name after any recipe or Git state change. On mismatch
both binaries, their SHA-256 values, ELF reports and a readelf diff remain there.
Logs preserve the failed command's exit status; a report/cleanup failure must
not hide the primary failure. Source/object caches and unrelated host files are
not included in artifacts.

The final `artifact/` contains `runtime-x86_64`, `runtime.lock.json`, `SHA256SUMS`,
`manifest.json`, reports, source archives, licenses, the exact upstream patch,
aports recipes/patches, original APKs and metadata, OCI inputs, and copies of
linked archives/CRT objects. SHA256SUMS covers every file except itself. The
manifest inventories payload files; its own checksum is in SHA256SUMS.

For the next integration, verify all checksums, require all mandatory check
records to be PASS for the same recipe hash, and use `runtime.sha256` and
`runtime.size` from this actual artifact. Notices should refer to
`upstream_source_commit`, `tokenlogue_recipe` (HEAD **plus** dirty status and
individual recipe hashes), the locked components and `runtime_source_materials`.
An uncommitted recipe is never represented as clean HEAD. Do not carry over the
old runtime's size/hash. Do not clear global `source_materials: REVIEW_REQUIRED`:
the Flutter SDK remains outside this work. Historical candidate reports are
unchanged.

No runtime binary hash or successful CI result is part of this source change.
The initial development host had neither Docker nor Podman. The first real
container build, native APK signature/inventory check, binary comparison and
minimal AppImage execution therefore require the manual run. After the reviewed
workflow is available on the remote main branch, an operator can invoke it with:

```bash
gh workflow run build-appimage-runtime.yml --ref main
gh run list --workflow build-appimage-runtime.yml --limit 1
```
