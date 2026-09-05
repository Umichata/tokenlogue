#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
CDPATH=''

die() {
    printf 'smoke_appimage: %s\n' "$*" >&2
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

run_inner() {
    local smoke_root=$1
    export XDG_DATA_HOME="$smoke_root/xdg-data"
    export XDG_CONFIG_HOME="$smoke_root/xdg-config"
    export XDG_CACHE_HOME="$smoke_root/xdg-cache"
    export XDG_RUNTIME_DIR="$smoke_root/runtime"
    export FLET_APP_STORAGE_DATA="$smoke_root/storage"
    export TMPDIR="$smoke_root/tmp"
    unset \
        HTTP_PROXY HTTPS_PROXY ALL_PROXY \
        http_proxy https_proxy all_proxy \
        GNOME_KEYRING_CONTROL GNOME_KEYRING_PID SSH_AUTH_SOCK \
        OPENROUTER_API_KEY

    local keyring_control="$XDG_RUNTIME_DIR/keyring"
    local keyring_pid
    mkdir -p -- "$keyring_control"
    chmod 0700 "$keyring_control"
    gnome-keyring-daemon \
        --foreground \
        --components=secrets \
        --control-directory="$keyring_control" \
        > "$smoke_root/logs/keyring.log" 2>&1 &
    keyring_pid=$!

    # Invoked indirectly by the trap below.
    # shellcheck disable=SC2317
    cleanup_inner() {
        kill "$keyring_pid" 2>/dev/null || true
        wait "$keyring_pid" 2>/dev/null || true
    }
    trap cleanup_inner EXIT INT TERM
    gdbus wait --session --timeout=5 org.freedesktop.secrets

    strace \
        -ff \
        -qq \
        -s 160 \
        -e trace=%file,socket,connect,bind,listen,accept,accept4,getsockname,getpeername,execve,clone,clone3,fork,vfork \
        -o "$smoke_root/logs/trace" \
        "$smoke_root/Tokenlogue.AppImage" \
        --appimage-extract-and-run \
        > "$smoke_root/logs/application.stdout" \
        2> "$smoke_root/logs/application.stderr"
}

if [[ "${1-}" == '--inner' ]]; then
    [[ $# -eq 2 ]] || die "invalid inner invocation"
    run_inner "$2"
    exit 0
fi

reject_proxies
[[ $# -eq 2 ]] || die "usage: $0 APPIMAGE REPORTS_DIR"
ulimit -c 0

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
[[ "$(git -C "$repo_root" rev-parse --show-toplevel)" == "$repo_root" ]] || \
    die "script is outside the Tokenlogue repository"
[[ "$(uname -s)" == 'Linux' && "$(uname -m)" == 'x86_64' ]] || \
    die "Linux x86_64 is required"

appimage="$(realpath -- "$1")"
reports_dir="$(realpath -m -- "$2")"
[[ -x "$appimage" && -f "$appimage" ]] || die "AppImage is not executable"
mkdir -p -- "$reports_dir"

for command_name in \
    bwrap dbus-run-session gdbus gnome-keyring-daemon pgrep \
    strace timeout wmctrl Xvfb; do
    command -v "$command_name" >/dev/null || die "missing command: $command_name"
done

[[ -n "${HOME-}" && "$HOME" == /* && "$HOME" != '/' && -d "$HOME" ]] || \
    die "existing HOME must be an absolute user directory"
if ! bwrap --unshare-net --ro-bind / / --proc /proc --dev /dev /usr/bin/true; then
    die "bubblewrap user/network namespace is unavailable; no fallback is allowed"
fi

smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/tokenlogue-appimage-smoke.XXXXXX")"
xvfb_pid=''
runner_pid=''
cleanup_outer() {
    if [[ -n "$runner_pid" ]] && kill -0 "$runner_pid" 2>/dev/null; then
        kill "$runner_pid" 2>/dev/null || true
        wait "$runner_pid" 2>/dev/null || true
    fi
    if [[ -n "$xvfb_pid" ]] && kill -0 "$xvfb_pid" 2>/dev/null; then
        kill "$xvfb_pid" 2>/dev/null || true
        wait "$xvfb_pid" 2>/dev/null || true
    fi
    if [[ -n "${smoke_root-}" && -d "$smoke_root" ]]; then
        rm -rf -- "$smoke_root"
    fi
}
trap cleanup_outer EXIT INT TERM

mkdir -p \
    "$smoke_root/home" \
    "$smoke_root/xdg-data" \
    "$smoke_root/xdg-config" \
    "$smoke_root/xdg-cache" \
    "$smoke_root/storage" \
    "$smoke_root/runtime" \
    "$smoke_root/tmp" \
    "$smoke_root/logs"
chmod 0700 \
    "$smoke_root/home" \
    "$smoke_root/xdg-data" \
    "$smoke_root/xdg-config" \
    "$smoke_root/xdg-cache" \
    "$smoke_root/storage" \
    "$smoke_root/runtime" \
    "$smoke_root/tmp" \
    "$smoke_root/logs"
cp -p -- "$appimage" "$smoke_root/Tokenlogue.AppImage"
cp -p -- "$0" "$smoke_root/smoke_appimage.sh"
chmod 0755 "$smoke_root/smoke_appimage.sh"

display_number_file="$smoke_root/display-number"
Xvfb \
    -displayfd 3 \
    -screen 0 1280x720x24 \
    -nolisten tcp \
    -ac \
    > "$smoke_root/logs/xvfb.stdout" \
    2> "$smoke_root/logs/xvfb.stderr" \
    3> "$display_number_file" &
xvfb_pid=$!
for _ in $(seq 1 40); do
    [[ -s "$display_number_file" ]] && break
    kill -0 "$xvfb_pid" 2>/dev/null || die "Xvfb exited before initialization"
    sleep 0.1
done
[[ -s "$display_number_file" ]] || die "Xvfb did not publish a display number"
display_number="$(tr -d '\r\n' < "$display_number_file")"
[[ "$display_number" =~ ^[0-9]+$ ]] || die "invalid Xvfb display number"
display=":$display_number"

bwrap_args=(
    --die-with-parent
    --new-session
    --unshare-net
    --unshare-pid
    --ro-bind / /
    --bind "$smoke_root" /mnt
    --bind "$smoke_root/home" "$HOME"
    --tmpfs /tmp
    --dir /tmp/.X11-unix
    --ro-bind /tmp/.X11-unix /tmp/.X11-unix
    --proc /proc
    --dev-bind /dev /dev
    --chdir /mnt
    --setenv DISPLAY "$display"
    --setenv TOKENLOGUE_SMOKE_ROOT /mnt
    --setenv XDG_DATA_HOME /mnt/xdg-data
    --setenv XDG_CONFIG_HOME /mnt/xdg-config
    --setenv XDG_CACHE_HOME /mnt/xdg-cache
    --setenv XDG_RUNTIME_DIR /mnt/runtime
    --setenv FLET_APP_STORAGE_DATA /mnt/storage
    --setenv TMPDIR /mnt/tmp
    --setenv LIBGL_ALWAYS_SOFTWARE 1
    --setenv GDK_BACKEND x11
)
host_runtime="/run/user/$(id -u)"
if [[ -d "$host_runtime" ]]; then
    bwrap_args+=(--tmpfs "$host_runtime")
fi

set +e
env \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    -u DBUS_SESSION_BUS_ADDRESS \
    -u GNOME_KEYRING_CONTROL -u GNOME_KEYRING_PID -u SSH_AUTH_SOCK \
    -u XAUTHORITY \
    timeout --signal=TERM --kill-after=5s 20s \
    bwrap "${bwrap_args[@]}" \
    /usr/bin/dbus-run-session -- /mnt/smoke_appimage.sh --inner /mnt \
    > "$smoke_root/logs/sandbox.stdout" \
    2> "$smoke_root/logs/sandbox.stderr" &
runner_pid=$!

window_line=''
for _ in $(seq 1 80); do
    current_windows="$(DISPLAY="$display" wmctrl -lx 2>/dev/null || true)"
    window_line="$(
        grep -E 'tokenlogue\.Tokenlogue[[:space:]].*[[:space:]]Tokenlogue$' \
            <<< "$current_windows" || true
    )"
    [[ -n "$window_line" ]] && break
    kill -0 "$runner_pid" 2>/dev/null || break
    sleep 0.25
done
wait "$runner_pid"
smoke_status=$?
runner_pid=''
set -e

trace_files=("$smoke_root"/logs/trace.*)
[[ -e "${trace_files[0]}" ]] || die "strace output is missing"
inet_calls="$(
    (grep -hE 'socket\(AF_INET(6)?,' "${trace_files[@]}" 2>/dev/null || true) | \
        wc -l
)"
inet_connects="$(
    (grep -hE 'connect\([^)]*(sin_family=AF_INET|sin6_family=AF_INET6)' \
        "${trace_files[@]}" 2>/dev/null || true) | wc -l
)"
fatal_count="$(
    (grep -Eih \
        'traceback|segmentation fault|symbol lookup error|loader error|core dumped|\[FATAL:' \
        "$smoke_root/logs/application.stderr" \
        "$smoke_root/logs/sandbox.stderr" 2>/dev/null || true) | wc -l
)"

[[ "$smoke_status" -eq 124 ]] || die "application exited before timeout: $smoke_status"
[[ -n "$window_line" ]] || die "Tokenlogue window was not observed"
[[ "$inet_calls" -eq 0 && "$inet_connects" -eq 0 ]] || \
    die "AF_INET or AF_INET6 activity detected"
[[ "$fatal_count" -eq 0 ]] || die "fatal runtime diagnostics detected"
if pgrep -f '^/mnt/(Tokenlogue\.AppImage|tmp/appimage_extracted_)' >/dev/null; then
    die "AppImage process remains after timeout"
fi
if pgrep -f '^gnome-keyring-daemon .*--control-directory=/mnt/runtime' >/dev/null; then
    die "temporary keyring process remains after timeout"
fi

kill "$xvfb_pid" 2>/dev/null || true
wait "$xvfb_pid" 2>/dev/null || true
xvfb_pid=''

cp -- "$smoke_root/logs/application.stderr" \
    "$reports_dir/smoke-application.stderr.txt"
cp -- "$smoke_root/logs/sandbox.stderr" \
    "$reports_dir/smoke-sandbox.stderr.txt"
{
    printf 'result=PASS\n'
    printf 'exit_code=%s\n' "$smoke_status"
    printf 'timeout_seconds=20\n'
    printf 'window=%s\n' "$window_line"
    printf 'af_inet_socket_calls=%s\n' "$inet_calls"
    printf 'af_inet_connect_calls=%s\n' "$inet_connects"
    printf 'fatal_diagnostics=%s\n' "$fatal_count"
    printf 'home_environment_reassigned=no\n'
    printf 'home_filesystem_isolated=yes\n'
    printf 'network_namespace=yes\n'
} > "$reports_dir/smoke-test-summary.txt"

printf 'Isolated AppImage smoke test: PASS\n'
