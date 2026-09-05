#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
CDPATH=''

die() {
    printf 'build_linux_bundle: %s\n' "$*" >&2
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

sha256_of() {
    sha256sum -- "$1" | awk '{print $1}'
}

verify_inputs_unchanged() {
    [[ "$(sha256_of "$repo_root/pyproject.toml")" == "$pyproject_hash_before" ]] || \
        die "pyproject.toml changed during Linux build"
    [[ "$(sha256_of "$repo_root/uv.lock")" == "$lock_hash_before" ]] || \
        die "uv.lock changed during Linux build"
}

on_exit() {
    local status=$?
    trap - EXIT
    if ! verify_inputs_unchanged; then
        exit 1
    fi
    exit "$status"
}

prepare_constraints() {
    uv export \
        --locked \
        --no-default-groups \
        --no-dev \
        --no-emit-project \
        --no-emit-local \
        --format requirements.txt \
        --no-hashes \
        --no-header \
        --no-annotate \
        --output-file "$constraints"
    uv run --locked python "$verify_script" constraints \
        --constraints "$constraints"
}

prepare_reference_environment() {
    [[ -f "$constraints" ]] || die "production constraints have not been generated"
    [[ "$reference_env" == "$release_root/reference-venv" ]] || \
        die "unsafe reference environment path"
    rm -rf -- "$reference_env"
    uv venv \
        --clear \
        --managed-python \
        --no-project \
        --python "$python_version" \
        "$reference_env"
    VIRTUAL_ENV="$reference_env" uv sync \
        --active \
        --locked \
        --no-default-groups \
        --no-dev \
        --no-install-project
    uv pip list \
        --python "$reference_env/bin/python" \
        --format json \
        --exclude-editable \
        > "$expected_raw"
}

build_flet_bundle() {
    [[ -f "$constraints" && -f "$expected_raw" ]] || \
        die "production reference environment is incomplete"
    [[ ! -e "$repo_root/build/linux" ]] || \
        die "build/linux already exists; refusing to reuse or delete it"
    printf 'Building Flet Linux bundle with PIP_CONSTRAINT=%s\n' "$constraints"
    PIP_CONSTRAINT="$constraints" \
        uv run --locked flet build linux -v --yes 2>&1 | \
        tee "$reports_dir/flet-build.log"
    [[ -x "$repo_root/build/linux/tokenlogue" ]] || \
        die "Flet did not create build/linux/tokenlogue"
}

verify_package_inventory() {
    [[ -f "$expected_raw" ]] || die "expected package inventory is missing"
    uv run --locked python "$verify_script" inventory \
        --constraints "$constraints" \
        --expected-json "$expected_raw" \
        --bundle "$repo_root/build/linux" \
        --reports-dir "$reports_dir"
}

verify_bundle_abi() {
    uv run --locked python "$verify_script" abi \
        --root "bundle=$repo_root/build/linux" \
        --reports-dir "$reports_dir" \
        --workspace "$repo_root"
}

reject_proxies

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
[[ "$(git -C "$repo_root" rev-parse --show-toplevel)" == "$repo_root" ]] || \
    die "script is outside the Tokenlogue repository"
[[ -f "$repo_root/pyproject.toml" && -f "$repo_root/uv.lock" ]] || \
    die "unexpected Tokenlogue repository structure"
[[ "$(uname -s)" == 'Linux' && "$(uname -m)" == 'x86_64' ]] || \
    die "Ubuntu-compatible Linux x86_64 is required"

command -v uv >/dev/null || die "uv is not installed"
[[ "$(uv --version)" == 'uv 0.12.8 '* ]] || die "uv 0.12.8 is required"
python_version="$(tr -d '\r\n' < "$repo_root/.python-version")"
[[ "$python_version" == '3.12' ]] || die ".python-version must contain 3.12"
export UV_MANAGED_PYTHON=1

pyproject_hash_before="$(sha256_of "$repo_root/pyproject.toml")"
lock_hash_before="$(sha256_of "$repo_root/uv.lock")"
trap on_exit EXIT
uv lock --check

release_root="$repo_root/build/linux-release"
reports_dir="$release_root/reports"
reference_env="$release_root/reference-venv"
constraints="$release_root/production-constraints.txt"
expected_raw="$reports_dir/expected-packages.raw.json"
verify_script="$script_dir/verify_bundle.py"
mkdir -p -- "$reports_dir"

phase=${1:-all}
case "$phase" in
    constraints)
        prepare_constraints
        ;;
    reference)
        prepare_reference_environment
        ;;
    build)
        build_flet_bundle
        ;;
    inventory)
        verify_package_inventory
        ;;
    abi)
        verify_bundle_abi
        ;;
    all)
        prepare_constraints
        prepare_reference_environment
        build_flet_bundle
        verify_package_inventory
        verify_bundle_abi
        ;;
    *)
        die "usage: $0 [constraints|reference|build|inventory|abi|all]"
        ;;
esac

verify_inputs_unchanged
printf 'Linux bundle phase completed: %s\n' "$phase"
