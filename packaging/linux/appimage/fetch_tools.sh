#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
PATH='/usr/bin:/bin'
export PATH
CDPATH=''

die() {
    printf 'fetch_tools: %s\n' "$*" >&2
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

download_asset() {
    local label=$1
    local url=$2
    local expected=$3
    local destination=$4

    if [[ -e "$destination" ]]; then
        verify_sha256 "$destination" "$expected"
        printf '%s already present and verified\n' "$label"
        return
    fi

    partial_path="$(mktemp "${destination}.part.XXXXXX")"
    printf 'Downloading %s from pinned tagged release\n' "$label"
    curl --disable --noproxy '*' --proto '=https' --proto-redir '=https' \
        --tlsv1.2 --fail --show-error --location \
        --output "$partial_path" "$url"
    verify_sha256 "$partial_path" "$expected"
    mv -- "$partial_path" "$destination"
    partial_path=''
}

validate_archive_paths() {
    local archive=$1
    local member
    local normalized
    while IFS= read -r member; do
        normalized=${member#./}
        [[ -n "$normalized" ]] || continue
        [[ "$normalized" != /* ]] || die "absolute tar path: $member"
        [[ "/$normalized/" != *'/../'* ]] || die "parent tar path: $member"
        [[ "$normalized" != *\\* ]] || die "backslash tar path: $member"
    done < <(tar -tzf "$archive")

    if ! tar -tvzf "$archive" | awk '{type = substr($1, 1, 1); if (type != "-" && type != "d") exit 1}'; then
        die "patchelf archive contains links or special files"
    fi
}

extract_patchelf() {
    local archive=$1
    local destination=$2
    local candidate

    if [[ -e "$destination" ]]; then
        verify_sha256 "$destination" "$PATCHELF_BINARY_SHA256"
        [[ "$("$destination" --version)" == "patchelf ${PATCHELF_TAG}" ]] || \
            die "unexpected patchelf version"
        printf 'patchelf binary already present and verified\n'
        return
    fi

    validate_archive_paths "$archive"
    extract_dir="$(mktemp -d "$tools_dir/.patchelf-extract.XXXXXX")"
    tar -xzf "$archive" --no-same-owner -C "$extract_dir"
    candidate="$extract_dir/bin/patchelf"
    [[ -f "$candidate" && ! -L "$candidate" ]] || \
        die "patchelf binary missing from verified archive"
    /usr/bin/install -m 0755 "$candidate" "$destination"
    verify_sha256 "$destination" "$PATCHELF_BINARY_SHA256"
    [[ "$("$destination" --version)" == "patchelf ${PATCHELF_TAG}" ]] || \
        die "unexpected patchelf version"
    rm -rf -- "$extract_dir"
    extract_dir=''
}

extract_appimagetool_runtime() {
    local appimagetool=$1
    local destination=$2
    local reported_offset

    if [[ -e "$destination" ]]; then
        verify_sha256 "$destination" "$APPIMAGETOOL_RUNTIME_SHA256"
        [[ "$(stat -c %s "$destination")" == "$APPIMAGETOOL_RUNTIME_SIZE" ]] || \
            die "unexpected appimagetool runtime size"
        printf 'appimagetool tagged runtime already present and verified\n'
        return
    fi

    reported_offset="$("$appimagetool" --appimage-offset)"
    [[ "$reported_offset" == "$APPIMAGETOOL_RUNTIME_SIZE" ]] || \
        die "unexpected runtime offset in tagged appimagetool asset"
    partial_path="$(mktemp "${destination}.part.XXXXXX")"
    head -c "$APPIMAGETOOL_RUNTIME_SIZE" -- "$appimagetool" > "$partial_path"
    verify_sha256 "$partial_path" "$APPIMAGETOOL_RUNTIME_SHA256"
    chmod 0755 "$partial_path"
    mv -- "$partial_path" "$destination"
    partial_path=''
    printf 'Extracted and verified runtime embedded in tagged appimagetool asset\n'
}

reject_proxies

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
[[ "$(git -C "$repo_root" rev-parse --show-toplevel)" == "$repo_root" ]] || \
    die "script is outside the Tokenlogue repository"
[[ -f "$repo_root/pyproject.toml" && -d "$repo_root/src" ]] || \
    die "unexpected Tokenlogue repository structure"

# shellcheck disable=SC1091
source "$script_dir/tools.lock"
[[ "$TOOLS_LOCK_VERSION" == '1' ]] || die "unsupported tools.lock version"

tools_dir="$repo_root/build/appimage/tools"
download_dir="$tools_dir/downloads"
mkdir -p -- "$download_dir"

partial_path=''
extract_dir=''
cleanup() {
    if [[ -n "$partial_path" ]]; then
        rm -f -- "$partial_path"
    fi
    if [[ -n "$extract_dir" ]]; then
        rm -rf -- "$extract_dir"
    fi
}
trap cleanup EXIT INT TERM

download_asset \
    "linuxdeploy ${LINUXDEPLOY_TAG}" \
    "$LINUXDEPLOY_URL" \
    "$LINUXDEPLOY_SHA256" \
    "$download_dir/$LINUXDEPLOY_ASSET"
download_asset \
    "appimagetool ${APPIMAGETOOL_TAG}" \
    "$APPIMAGETOOL_URL" \
    "$APPIMAGETOOL_SHA256" \
    "$download_dir/$APPIMAGETOOL_ASSET"
download_asset \
    "patchelf ${PATCHELF_TAG}" \
    "$PATCHELF_URL" \
    "$PATCHELF_SHA256" \
    "$download_dir/$PATCHELF_ASSET"

chmod 0755 \
    "$download_dir/$LINUXDEPLOY_ASSET" \
    "$download_dir/$APPIMAGETOOL_ASSET"
extract_appimagetool_runtime \
    "$download_dir/$APPIMAGETOOL_ASSET" \
    "$tools_dir/appimagetool-runtime-x86_64"
extract_patchelf "$download_dir/$PATCHELF_ASSET" "$tools_dir/patchelf"

printf 'All pinned AppImage tools are present and verified.\n'
