#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
PATH='/usr/bin:/bin'
export PATH
CDPATH=''

die() {
    printf 'build_appimage: %s\n' "$*" >&2
    exit 1
}

reject_proxies() {
    local variable_name
    for variable_name in \
        HTTP_PROXY HTTPS_PROXY ALL_PROXY \
        http_proxy https_proxy all_proxy; do
        if [[ -n "${!variable_name-}" ]]; then
            die "proxy variable ${variable_name} must be unset"
        fi
    done
}

verify_sha256() {
    local path=$1
    local expected=$2
    local actual
    [[ -f "$path" && ! -L "$path" ]] || die "missing regular file: $path"
    actual="$(sha256sum -- "$path" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || die "SHA-256 mismatch: $path"
}

is_elf() {
    file -b -- "$1" | grep -q '^ELF '
}

remove_optional_jni() {
    local appdir=$1
    # Flutter's jni package may build this on JDK-equipped runners.
    # Tokenlogue does not use Java on Linux; remove only the staging copy.
    rm -f -- "$appdir/usr/lib/tokenlogue/lib/libdartjni.so"
}

reject_forbidden_staging_files() {
    local appdir=$1
    local forbidden
    forbidden="$(find "$appdir" \
        \( -name '.env' -o -name '.env.local' -o -name 'tokenlogue.sqlite3' \
        -o -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \
        -o -name 'libdartjni.so' -o -name 'libjvm.so' \
        -o -name '.git' -o -name '.flet' -o -name '__pycache__' \) -print)"
    [[ -z "$forbidden" ]] || die "forbidden files entered AppDir: $forbidden"
}

validate_symlinks() {
    local appdir=$1
    "$python_bin" - "$appdir" <<'PY'
from pathlib import Path
import os
import sys

appdir = Path(sys.argv[1]).resolve(strict=True)
for link in sorted(path for path in appdir.rglob("*") if path.is_symlink()):
    target_text = os.readlink(link)
    if Path(target_text).is_absolute():
        raise SystemExit(f"absolute AppDir symlink: {link} -> {target_text}")
    target = (link.parent / target_text).resolve(strict=True)
    if not target.is_relative_to(appdir):
        raise SystemExit(f"escaping AppDir symlink: {link} -> {target_text}")
print("AppDir symlinks are relative and contained")
PY
}

validate_runpaths() {
    local appdir=$1
    local elf_file
    local dynamic_paths
    local entry

    while IFS= read -r -d '' elf_file; do
        is_elf "$elf_file" || continue
        dynamic_paths="$(readelf -d "$elf_file" 2>/dev/null | \
            sed -n 's/.*\(RPATH\|RUNPATH\).*\[\([^]]*\)\].*/\2/p')"
        [[ "$dynamic_paths" != *'/home/'* ]] || \
            die "absolute home path in ELF: $elf_file"
        [[ "$dynamic_paths" != *'/tmp/'* ]] || \
            die "temporary path in ELF: $elf_file"
        [[ "$dynamic_paths" != *'build/flutter'* ]] || \
            die "source Flutter path in ELF: $elf_file"
        IFS=':' read -r -a runpath_entries <<< "$dynamic_paths"
        for entry in "${runpath_entries[@]}"; do
            [[ -z "$entry" || "$entry" == \$ORIGIN* ]] || \
                die "non-relocatable RUNPATH entry in $elf_file: $entry"
        done
    done < <(find "$appdir" -type f -print0)
}

normalize_permissions() {
    local appdir=$1
    find "$appdir" -type d -exec chmod 0755 {} +
    find "$appdir" -type f -exec chmod 0644 {} +
    chmod 0755 \
        "$appdir/AppRun" \
        "$appdir/usr/bin/tokenlogue" \
        "$appdir/usr/lib/tokenlogue/tokenlogue"
}

reject_proxies

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
[[ "$(git -C "$repo_root" rev-parse --show-toplevel)" == "$repo_root" ]] || \
    die "script is outside the Tokenlogue repository"
[[ -f "$repo_root/pyproject.toml" && -d "$repo_root/src" ]] || \
    die "unexpected Tokenlogue repository structure"
[[ "$(uname -m)" == 'x86_64' ]] || die "only Linux x86_64 is supported"

# shellcheck disable=SC1091
source "$script_dir/tools.lock"
[[ "$TOOLS_LOCK_VERSION" == '1' ]] || die "unsupported tools.lock version"

python_bin="$repo_root/.venv/bin/python"
[[ -x "$python_bin" ]] || die "project Python is missing; run uv sync --locked"
version="$("$python_bin" -c \
    'import sys,tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' \
    "$repo_root/pyproject.toml")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.+-][0-9A-Za-z.-]+)?$ ]] || \
    die "unsupported project version: $version"

source_bundle="$repo_root/build/linux"
source_executable="$source_bundle/tokenlogue"
[[ -x "$source_executable" ]] || die "existing build/linux bundle is missing"
source_hash_before="$(sha256sum -- "$source_executable" | awk '{print $1}')"

work_root="$repo_root/build/appimage"
tools_dir="$work_root/tools"
download_dir="$tools_dir/downloads"
linuxdeploy="$download_dir/$LINUXDEPLOY_ASSET"
appimagetool="$download_dir/$APPIMAGETOOL_ASSET"
appimagetool_runtime="$tools_dir/appimagetool-runtime-x86_64"
patchelf="$tools_dir/patchelf"

verify_sha256 "$linuxdeploy" "$LINUXDEPLOY_SHA256"
verify_sha256 "$appimagetool" "$APPIMAGETOOL_SHA256"
verify_sha256 "$appimagetool_runtime" "$APPIMAGETOOL_RUNTIME_SHA256"
[[ "$(stat -c %s "$appimagetool_runtime")" == \
    "$APPIMAGETOOL_RUNTIME_SIZE" ]] || \
    die "unexpected appimagetool runtime size"
verify_sha256 "$download_dir/$PATCHELF_ASSET" "$PATCHELF_SHA256"
verify_sha256 "$patchelf" "$PATCHELF_BINARY_SHA256"
[[ "$("$patchelf" --version)" == "patchelf ${PATCHELF_TAG}" ]] || \
    die "unexpected patchelf version"

mkdir -p -- "$work_root"
staging_root="$(mktemp -d "$work_root/.stage.XXXXXX")"
appdir="$staging_root/Tokenlogue.AppDir"
partial_image="$staging_root/Tokenlogue-${version}-x86_64.AppImage"
final_appdir="$work_root/Tokenlogue.AppDir"
final_image="$work_root/Tokenlogue-${version}-x86_64.AppImage"
tool_home="$staging_root/tool-home"

cleanup() {
    if [[ -n "${staging_root-}" && -d "$staging_root" ]]; then
        rm -rf -- "$staging_root"
    fi
}
trap cleanup EXIT INT TERM

mkdir -p \
    "$appdir/usr/lib/tokenlogue" \
    "$appdir/usr/bin" \
    "$appdir/usr/share/applications" \
    "$appdir/usr/share/metainfo" \
    "$appdir/usr/share/icons/hicolor" \
    "$appdir/usr/share/doc/tokenlogue" \
    "$tool_home/cache" \
    "$tool_home/config" \
    "$tool_home/data"

cp -a -- "$source_bundle/." "$appdir/usr/lib/tokenlogue/"
remove_optional_jni "$appdir"
cp -- "$script_dir/AppRun" "$appdir/AppRun"

cat > "$appdir/usr/bin/tokenlogue" <<'LAUNCHER'
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

CDPATH=''
launcher_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
appdir="$(cd -- "$launcher_dir/../.." && pwd -P)"
bundle_dir="$appdir/usr/lib/tokenlogue"
cd -- "$bundle_dir"
exec ./tokenlogue "$@"
LAUNCHER

desktop_source="$repo_root/packaging/linux/io.github.umichata.tokenlogue.desktop"
desktop_staged="$appdir/usr/share/applications/io.github.umichata.tokenlogue.desktop"
grep -Fxq 'Exec=/usr/bin/tokenlogue' "$desktop_source" || \
    die "unexpected source desktop Exec"
grep -Fxq 'TryExec=/usr/bin/tokenlogue' "$desktop_source" || \
    die "unexpected source desktop TryExec"
# desktop-file-utils 0.26 rejects the optional spec Version=1.5.
sed \
    -e 's|^Exec=/usr/bin/tokenlogue$|Exec=tokenlogue|' \
    -e '/^TryExec=\/usr\/bin\/tokenlogue$/d' \
    -e '/^\[Desktop Entry\][[:space:]]*$/,/^\[/ { /^[[:space:]]*Version[[:space:]]*=/d; }' \
    "$desktop_source" > "$desktop_staged"
[[ "$(grep -c '^Exec=' "$desktop_staged")" == '1' ]] || \
    die "staged desktop must contain exactly one Exec field"
grep -Fxq 'Exec=tokenlogue' "$desktop_staged" || \
    die "unexpected staged desktop Exec"
if grep -q '^TryExec=' "$desktop_staged"; then
    die "TryExec must be absent from AppImage desktop entry"
fi
if grep -Fq '/usr/bin/tokenlogue' "$desktop_staged"; then
    die "system launcher path leaked into AppImage desktop entry"
fi

cp -- \
    "$repo_root/packaging/linux/io.github.umichata.tokenlogue.metainfo.xml" \
    "$appdir/usr/share/metainfo/io.github.umichata.tokenlogue.metainfo.xml"
cp -a -- \
    "$repo_root/packaging/icons/linux/hicolor/." \
    "$appdir/usr/share/icons/hicolor/"
cp -- "$repo_root/LICENSE" "$appdir/LICENSE"
cp -- "$repo_root/THIRD_PARTY_NOTICES.md" "$appdir/THIRD_PARTY_NOTICES.md"
cp -- "$repo_root/LICENSE" "$appdir/usr/share/doc/tokenlogue/LICENSE"
cp -- \
    "$repo_root/THIRD_PARTY_NOTICES.md" \
    "$appdir/usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md"

ln -s \
    'usr/share/applications/io.github.umichata.tokenlogue.desktop' \
    "$appdir/io.github.umichata.tokenlogue.desktop"
ln -s \
    'usr/share/icons/hicolor/256x256/apps/tokenlogue.png' \
    "$appdir/tokenlogue.png"
ln -s 'tokenlogue.png' "$appdir/.DirIcon"

mapfile -d '' -t tkinter_extensions < <(
    find "$appdir/usr/lib/tokenlogue/python3.12/lib-dynload" \
        -maxdepth 1 -type f -name '_tkinter.cpython-312-*.so' -print0
)
[[ "${#tkinter_extensions[@]}" -eq 1 ]] || \
    die "expected exactly one staged _tkinter extension"
rm -- "${tkinter_extensions[0]}"
printf 'Removed unused extension: %s\n' "${tkinter_extensions[0]#$appdir/}"

plugins=(
    libflutter_secure_storage_linux_plugin.so
    libpasteboard_plugin.so
    libscreen_retriever_linux_plugin.so
    libserious_python_linux_plugin.so
    liburl_launcher_linux_plugin.so
    libwindow_manager_plugin.so
)
printf 'Original plugin RUNPATH values:\n'
for plugin_name in "${plugins[@]}"; do
    plugin_path="$appdir/usr/lib/tokenlogue/lib/$plugin_name"
    [[ -f "$plugin_path" ]] || die "missing staged plugin: $plugin_name"
    printf '%s=%s\n' "$plugin_name" "$("$patchelf" --print-rpath "$plugin_path")"
    "$patchelf" --set-rpath "\$ORIGIN:\$ORIGIN/../.." "$plugin_path"
done

"$python_bin" "$script_dir/sanitize_paths.py" "$appdir" "$repo_root"

linuxdeploy_args=(
    --appimage-extract-and-run
    --appdir="$appdir"
    --deploy-deps-only="$appdir/usr/lib/tokenlogue"
    --exclude-library='libc.so.*'
    --exclude-library='ld-linux*.so*'
    --exclude-library='libpthread.so.*'
    --exclude-library='libm.so.*'
    --exclude-library='libdl.so.*'
    --exclude-library='librt.so.*'
    --exclude-library='libGL*.so*'
    --exclude-library='libEGL*.so*'
    --exclude-library='libGLES*.so*'
    --exclude-library='libOpenGL*.so*'
    --exclude-library='libnvidia*.so*'
    --exclude-library='libcuda*.so*'
    --exclude-library='libdrm*.so*'
    --exclude-library='libgbm*.so*'
    --exclude-library='libdart_bridge.so'
    --exclude-library='libflutter_linux_gtk.so'
    --exclude-library='libflutter_secure_storage_linux_plugin.so'
    --exclude-library='libpasteboard_plugin.so'
    --exclude-library='libpython3.so'
    --exclude-library='libpython3.12.so.1.0'
    --exclude-library='libscreen_retriever_linux_plugin.so'
    --exclude-library='libserious_python_linux_plugin.so'
    --exclude-library='liburl_launcher_linux_plugin.so'
    --exclude-library='libwindow_manager_plugin.so'
)

printf 'Deploying runtime dependencies with linuxdeploy %s\n' "$LINUXDEPLOY_TAG"
env \
    HOME="$tool_home" \
    XDG_CACHE_HOME="$tool_home/cache" \
    XDG_CONFIG_HOME="$tool_home/config" \
    XDG_DATA_HOME="$tool_home/data" \
    NO_STRIP=1 \
    LD_LIBRARY_PATH="$appdir/usr/lib/tokenlogue/lib" \
    "$linuxdeploy" "${linuxdeploy_args[@]}"

# linuxdeploy may select a smaller icon for its AppDir root integration.
# Restore the project's deterministic root links after dependency deployment.
rm -f -- \
    "$appdir/io.github.umichata.tokenlogue.desktop" \
    "$appdir/tokenlogue.png" \
    "$appdir/.DirIcon"
ln -s \
    'usr/share/applications/io.github.umichata.tokenlogue.desktop' \
    "$appdir/io.github.umichata.tokenlogue.desktop"
ln -s \
    'usr/share/icons/hicolor/256x256/apps/tokenlogue.png' \
    "$appdir/tokenlogue.png"
ln -s 'tokenlogue.png' "$appdir/.DirIcon"

for plugin_name in "${plugins[@]}"; do
    "$patchelf" --set-rpath "\$ORIGIN:\$ORIGIN/../.." \
        "$appdir/usr/lib/tokenlogue/lib/$plugin_name"
done
"$patchelf" --set-rpath "\$ORIGIN/lib:\$ORIGIN/.." \
    "$appdir/usr/lib/tokenlogue/tokenlogue"

"$python_bin" "$script_dir/sanitize_paths.py" "$appdir" "$repo_root"
reject_forbidden_staging_files "$appdir"
validate_runpaths "$appdir"

if find "$appdir" -type f -exec readelf -d {} \; 2>/dev/null | \
    grep -Eq 'libtcl9tk9\.0\.so|libtcl9\.0\.so'; then
    die "Tcl/Tk dependency remains after exact _tkinter removal"
fi

for forbidden_library in \
    'libc.so.' 'ld-linux' 'libGL.so.' 'libEGL.so.' 'libGLES' \
    'libOpenGL' 'libnvidia' 'libcuda' 'libdrm' 'libgbm'; do
    if find "$appdir/usr/lib" -maxdepth 1 -type f -name "${forbidden_library}*" \
        -print -quit | grep -q .; then
        die "forbidden host library was bundled: $forbidden_library"
    fi
done

normalize_permissions "$appdir"
validate_symlinks "$appdir"

desktop-file-validate "$desktop_staged"
appstreamcli validate --no-net \
    "$appdir/usr/share/metainfo/io.github.umichata.tokenlogue.metainfo.xml"
bash -n "$appdir/AppRun" "$appdir/usr/bin/tokenlogue"

if rg -uuu -a -q -F "$repo_root" "$appdir"; then
    die "repository path remains in AppDir"
fi
if rg -uuu -a -q \
    -e '/tmp/serious_python_temp' \
    -e 'build/flutter' \
    "$appdir"; then
    die "build-specific temporary path remains in AppDir"
fi

mapfile -d '' -t secret_files < <(
    {
        rg -uuu -a -l -0 \
            -e 'sk-or-v1-[A-Za-z0-9_-]{20,}' \
            -e 'gh[pousr]_[A-Za-z0-9]{20,}' \
            -e 'AKIA[0-9A-Z]{16}' \
            "$appdir" 2>/dev/null || true
        while IFS= read -r -d '' candidate; do
            is_elf "$candidate" && continue
            if rg -a -q -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
                "$candidate" 2>/dev/null; then
                printf '%s\0' "$candidate"
            fi
        done < <(find "$appdir" -type f -print0)
    } | sort -zu
)
if [[ "${#secret_files[@]}" -ne 0 ]]; then
    printf 'Secret-like pattern found in staged files (values omitted):\n' >&2
    for secret_file in "${secret_files[@]}"; do
        printf '  %s\n' "${secret_file#"$appdir"/}" >&2
    done
    die "secret-like data detected in AppDir"
fi

source_date_epoch="$(git -C "$repo_root" show -s --format=%ct HEAD)"
export SOURCE_DATE_EPOCH="$source_date_epoch"
find "$appdir" -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +

printf 'Creating unsigned diagnostic AppImage with appimagetool %s\n' \
    "$APPIMAGETOOL_TAG"
env \
    HOME="$tool_home" \
    XDG_CACHE_HOME="$tool_home/cache" \
    XDG_CONFIG_HOME="$tool_home/config" \
    XDG_DATA_HOME="$tool_home/data" \
    ARCH=x86_64 \
    SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
    "$appimagetool" --appimage-extract-and-run \
    --runtime-file "$appimagetool_runtime" \
    "$appdir" "$partial_image"

[[ -f "$partial_image" ]] || die "appimagetool did not create an artifact"
chmod 0755 "$partial_image"

[[ "$final_appdir" == "$work_root/Tokenlogue.AppDir" ]] || \
    die "unsafe final AppDir path"
[[ "$final_image" == "$work_root/Tokenlogue-${version}-x86_64.AppImage" ]] || \
    die "unsafe final AppImage path"
rm -rf -- "$final_appdir"
rm -f -- "$final_image"
mv -- "$appdir" "$final_appdir"
mv -- "$partial_image" "$final_image"

source_hash_after="$(sha256sum -- "$source_executable" | awk '{print $1}')"
[[ "$source_hash_before" == "$source_hash_after" ]] || \
    die "source build/linux executable was modified"

printf 'AppDir: %s\n' "$final_appdir"
printf 'AppImage: %s\n' "$final_image"
printf 'AppImage SHA-256: %s\n' \
    "$(sha256sum -- "$final_image" | awk '{print $1}')"
printf 'AppImage bytes: %s\n' "$(stat -c %s "$final_image")"
