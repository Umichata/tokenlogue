# Diagnostic AppImage infrastructure

This directory builds an unsigned diagnostic AppImage from the existing
`build/linux/` Flet bundle. It never rebuilds the Flet application and performs
all transformations on a staging copy under `build/appimage/`.

The staged desktop entry omits the optional `Version` key in `[Desktop Entry]`
because Ubuntu 22.04's desktop-file-utils 0.26 rejects `Version=1.5`.
The system desktop source is unchanged; AppImage keeps `Exec=tokenlogue`,
`Icon=tokenlogue`, localized metadata, and no `TryExec`. Staging conversion
runs before linuxdeploy, and desktop-file-validate remains mandatory.

## Host desktop runtime

The AppImage uses the distribution's GTK3, GLib/GIO, GdkPixbuf, Pango/Cairo
and accessibility runtime. `desktop_runtime.py` owns the shared exclusion
policy, including core GLib/GIO/D-Bus dependencies. linuxdeploy does not copy
these libraries, and packaged verification rejects matching names and SONAMEs.
The target system must provide GTK3 and its runtime dependencies. Flutter,
Python, application plugins and the bundled libsecret client remain packaged.
Ubuntu 22.04 remains the build baseline; the existing ABI limits are unchanged.

This avoids loading newer host GVfs/IBus modules against the old private
GLib 2.72 runtime. Input methods, GVfs and accessibility are not disabled in
AppRun. Host GTK also uses the distribution's module paths, including Fedora's
lib64 layout and Linux Mint's XApp module when installed.

The userspace matrix installs GVfs, IBus GTK3 and dconf. Before launching the
application it checks eager symbol resolution (`dlopen` with `RTLD_NOW`) under
AppRun's library paths, requires the GVfs and IBus modules, and records loaded
desktop library paths in `desktop-modules.json`. The existing application
smoke then explicitly selects IBus. Missing modules, private desktop runtime
copies, symbol errors, or failed IM-module loading fail the job. This checks
module loading; complete input-method interaction still needs a desktop test.

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
The older local Linux Mint bundle required GLIBC 2.38 and its bundled `anyio`
differed from `uv.lock`. These observations describe that old local bundle,
not subsequent Ubuntu CI artifacts. For the earlier `7c3976a` artifact, matrix
run `34011565339` passed and manual FUSE mounting and two ordinary Linux Mint
launches were reported successful. Those launches exposed host desktop-module
symbol errors. The revised desktop runtime requires a new build and matrix run;
the earlier results do not validate this revision. Tool provenance includes TOFU.

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

`.github/workflows/build-linux.yml` is a manual-only workflow which has completed
successfully on GitHub-hosted Ubuntu 22.04 x86_64, including its automatic
isolated launch check. The pipeline exports production-only pip constraints directly from
`uv.lock`, creates a separate locked production environment, supplies the
constraints to Flet through command-scoped `PIP_CONSTRAINT`, and rejects any
package inventory mismatch.

The resulting bundle, AppDir, and extracted AppImage must not require a GLIBC
version newer than `GLIBC_2.35`. The workflow also records ELF, RUNPATH, ldd,
toolchain, metadata, and isolated headless smoke-test reports. Its artifact is
unsigned, remains diagnostic only, and is not promoted to a release.

## Headless smoke diagnostics

The isolated Xvfb smoke test discovers windows through `xwininfo -root -tree`
and `xprop` on the same display with `LC_ALL=C`. It requires the exact
`WM_CLASS` pair `"tokenlogue", "Tokenlogue"`, the title `"Tokenlogue"`, and
`Map State: IsViewable`; no window manager or EWMH client list is required.

On success and failure, an exit handler stops the owned processes, saves
application/sandbox/Xvfb stderr, window search output, matched properties and
map state, and a PASS/FAIL summary before deleting temporary data. Checks that
have not run are marked `NOT_RUN`; missing evidence is `UNAVAILABLE` or
`NOT_CAPTURED`. Report failures cannot turn a failed test into a success or
skip cleanup. Only these diagnostic files are copied to the reports directory;
temporary HOME, storage, databases, keyring and raw traces are excluded.

## Cross-distribution userspace matrix

`test-linux-appimage.yml` is a separate manual-only workflow. Matrix run
`34011565339` passed for the earlier `7c3976a` artifact. Manual draft restoration
across chat switches and application restarts was also confirmed on Linux Mint.
This is separate evidence from Ubuntu 22.04's automated launch check.

Supply a specific successful `build-linux.yml` run ID and full application
commit SHA. `source_artifact.py` checks the repository, workflow ID/path,
completion, conclusion, commit, unique artifact name, expiry and artifact run
association through GitHub's API. It downloads by artifact ID, audits ZIP paths
and types, and reads only the single AppImage and checksum manifest. It does
not execute the source archive. The verified file is renamed, without changing
bytes, to `Tokenlogue-<version>-<short-source-sha>-x86_64.AppImage`. Its checksum
manifest references that exact name. Application and test-infrastructure commits
are recorded separately; checkout always stays on the infrastructure commit.

Every matrix job downloads the same verified copy and checks SHA-256 before
and after testing. The three official Docker Hub base images and their verified
linux/amd64 manifest digests are recorded in `container-images.lock.json`:
Ubuntu 22.04, Ubuntu 24.04 and Fedora 44. The manifest bytes were SHA-256 checked
against the registry response. This is registry/TLS provenance, not a signature.
Installed runtime package repositories remain mutable: a pinned base does not
make the complete environment bit-for-bit reproducible. Each test records the
complete installed package inventory and `/etc/os-release`.

`Containerfile.matrix` adds runtime GTK/GLib, graphics, libsecret, D-Bus and
diagnostic tools, not Flet/Flutter SDKs, compilers or development packages.
No runner libraries are copied into the image. The container is the explicit
isolation boundary: an unprivileged UID, a private disposable home/filesystem,
`--network none`, a separate D-Bus/keyring, Xvfb without TCP, software GL and
20-second extract-and-run timeout. It has no host HOME or Docker socket mount.
All capabilities are dropped except `SYS_PTRACE`, needed for strace of child
processes under Docker's default seccomp policy; `no-new-privileges` remains on.
No privileged or network fallback is provided. libsecret still needs a Secret
Service provider; the test supplies a disposable one without a real key.

The new probe reuses the exact inner launch, window discovery and diagnostic
functions of `smoke_appimage.sh`. Function extraction is checked by tests and
`bash -n`; the existing bubblewrap workflow and script are unchanged. Missing
evidence is NOT_RUN/UNAVAILABLE, never a numeric zero or a successful check.
Process cleanup and diagnostic copying run on failures too, followed by removal
of the disposable container. Raw traces, temporary home/storage/keyring/caches
are never included in artifacts. Diagnostic artifacts are retained for 14 days.

Runtime/environment failures fail their jobs. `fail-fast: false` allows other
distributions to finish. Reports and Step Summary identify the source run,
artifact, both commits, file hash/size, image digest and measured outcomes.
The automatic GitHub token is limited to retrieval steps and is never passed
to containers. There is no signing, release, automatic source-run selection,
or per-distribution application rebuild.

Each newly built candidate must pass module and launch checks in all three
userspaces. These container checks do not establish
ordinary FUSE launch, Wayland compatibility, hardware GPU drivers, or complete
desktop-session integration. They do not make an unsigned diagnostic AppImage
a general-distribution release.
