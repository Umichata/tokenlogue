#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
CDPATH=''
export LC_ALL=C

die() {
    failure_reason=$*
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
    printf 'ready\n' > "$smoke_root/logs/isolation-ready"

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
        local status=$?
        trap - EXIT
        kill "$keyring_pid" 2>/dev/null || true
        wait "$keyring_pid" 2>/dev/null || true
        exit "$status"
    }
    trap cleanup_inner EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
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
    # Exit while the trap's local keyring_pid is still in scope.
    exit 0
}

find_tokenlogue_window() {
    local tree properties info candidate line title_pattern status
    if [[ "$window_attempts" == 'NOT_RUN' ]]; then
        window_attempts=0
    fi
    window_attempts=$((window_attempts + 1))
    window_check='NOT_FOUND'
    window_id='NOT_FOUND'
    window_map_state='NOT_OBSERVED'
    printf 'Search attempt %s on DISPLAY=%s\n' "$window_attempts" "$display" \
        >> "$smoke_root/logs/window-search.txt" || return 2

    status=0
    tree="$(LC_ALL=C DISPLAY="$display" XAUTHORITY=/dev/null \
        timeout 2s xwininfo -root -tree 2>&1)" || status=$?
    printf 'xwininfo -root -tree exit=%s\n%s\n' "$status" "$tree" \
        >> "$smoke_root/logs/window-search.txt" || return 2
    [[ "$status" -eq 0 ]] || return 1

    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*(0x[[:xdigit:]]+)[[:space:]] ]] || continue
        candidate=${BASH_REMATCH[1]}
        status=0
        properties="$(LC_ALL=C DISPLAY="$display" XAUTHORITY=/dev/null \
            timeout 2s xprop -id "$candidate" WM_CLASS _NET_WM_NAME WM_NAME 2>&1)" || status=$?
        printf 'Candidate %s: xprop exit=%s\n%s\n' "$candidate" "$status" "$properties" \
            >> "$smoke_root/logs/window-search.txt" || return 2
        [[ "$status" -eq 0 ]] || continue
        grep -Fxq 'WM_CLASS(STRING) = "tokenlogue", "Tokenlogue"' \
            <<< "$properties" || continue
        title_pattern='^WM_NAME\((UTF8_STRING|STRING)\) = "Tokenlogue"$'
        if grep -Eq '^_NET_WM_NAME\([^)]*\) =' <<< "$properties"; then
            title_pattern='^_NET_WM_NAME\((UTF8_STRING|STRING)\) = "Tokenlogue"$'
        fi
        grep -Eq "$title_pattern" <<< "$properties" || continue

        status=0
        info="$(LC_ALL=C DISPLAY="$display" XAUTHORITY=/dev/null \
            timeout 2s xwininfo -id "$candidate" 2>&1)" || status=$?
        printf 'Candidate %s: xwininfo exit=%s\n%s\n' "$candidate" "$status" "$info" \
            >> "$smoke_root/logs/window-search.txt" || return 2
        [[ "$status" -eq 0 ]] || continue
        grep -Eq '^[[:space:]]*Map State: IsViewable[[:space:]]*$' <<< "$info" || continue

        printf '%s\n' "$properties" > "$smoke_root/logs/window-properties.txt" || return 2
        printf '%s\n' "$info" > "$smoke_root/logs/window-state.txt" || return 2
        window_id=$candidate
        window_map_state='IsViewable'
        window_check='PASS'
        return 0
    done <<< "$tree"
    return 1
}

count_log_matches() {
    local pattern=$1 matches status=0
    shift
    matches="$(grep -Eih -- "$pattern" "$@" 2>/dev/null)" || status=$?
    if [[ "$status" -gt 1 ]]; then
        printf 'UNAVAILABLE\n'
    elif [[ -z "$matches" ]]; then
        printf '0\n'
    else
        printf '%s\n' "$matches" | wc -l | tr -d '[:space:]'
    fi
}

collect_diagnostics() {
    local trace_file
    local -a trace_files=()
    [[ -n "$smoke_root" ]] || return 0
    if [[ -f "$smoke_root/logs/isolation-ready" ]]; then
        isolation_status='yes'
    fi
    if [[ "$smoke_status" != 'NOT_RUN' ]]; then
        inet_calls='UNAVAILABLE'
        inet_connects='UNAVAILABLE'
        fatal_count='UNAVAILABLE'
    fi
    for trace_file in "$smoke_root"/logs/trace.*; do
        [[ -s "$trace_file" ]] && trace_files+=("$trace_file")
    done
    if [[ "${#trace_files[@]}" -gt 0 ]]; then
        inet_calls="$(count_log_matches 'socket\(AF_INET(6)?,' "${trace_files[@]}")"
        inet_connects="$(count_log_matches \
            'connect\([^)]*(sin_family=AF_INET|sin6_family=AF_INET6)' \
            "${trace_files[@]}")"
    fi
    if [[ -f "$smoke_root/logs/application.stderr" && -f "$smoke_root/logs/sandbox.stderr" ]]; then
        fatal_count="$(count_log_matches \
            'traceback|segmentation fault|symbol lookup error|loader error|core dumped|\[FATAL:' \
            "$smoke_root/logs/application.stderr" "$smoke_root/logs/sandbox.stderr")"
    fi
}

stop_owned_process() {
    local pid=$1
    [[ -n "$pid" ]] || return 0
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    fi
    wait "$pid" 2>/dev/null || true
    ! kill -0 "$pid" 2>/dev/null
}

check_remaining_processes() {
    local pattern status
    [[ "$runner_started" == 'yes' ]] || return 0
    remaining_processes=0
    for pattern in \
        '^/mnt/(Tokenlogue\.AppImage|tmp/appimage_extracted_)' \
        '^gnome-keyring-daemon .*--control-directory=/mnt/runtime'; do
        status=0
        pgrep -f "$pattern" >/dev/null || status=$?
        if [[ "$status" -eq 0 ]]; then
            remaining_processes='DETECTED'
            return 1
        elif [[ "$status" -ne 1 ]]; then
            remaining_processes='UNAVAILABLE'
            return 1
        fi
    done
}

save_diagnostic_logs() {
    local source_name target_name failed=0
    # Explicit allowlist: no storage, keyring, HOME, environment dump or raw trace.
    for source_name in \
        application.stderr sandbox.stderr xvfb.stderr \
        window-search.txt window-properties.txt window-state.txt; do
        case "$source_name" in
            application.stderr) target_name='smoke-application.stderr.txt' ;;
            sandbox.stderr) target_name='smoke-sandbox.stderr.txt' ;;
            xvfb.stderr) target_name='smoke-xvfb.stderr.txt' ;;
            *) target_name="smoke-$source_name" ;;
        esac
        if [[ -n "$smoke_root" && -f "$smoke_root/logs/$source_name" ]]; then
            cp -- "$smoke_root/logs/$source_name" "$reports_dir/$target_name" || failed=1
        else
            printf 'NOT_CAPTURED: %s\n' "$source_name" > "$reports_dir/$target_name" || failed=1
        fi
    done
    return "$failed"
}

write_summary() {
    local status=$1 result='FAIL'
    [[ "$status" -eq 0 ]] && result='PASS'
    {
        printf 'result=%s\n' "$result"
        printf 'reason=%s\n' "${failure_reason:-completed}"
        printf 'script_exit_code=%s\n' "$status"
        printf 'exit_code=%s\n' "$smoke_status"
        printf 'timeout_seconds=20\n'
        printf 'elapsed_seconds=%s\n' "$elapsed_seconds"
        printf 'display=%s\n' "$display"
        printf 'window_check=%s\n' "$window_check"
        printf 'window_id=%s\n' "$window_id"
        printf 'window_map_state=%s\n' "$window_map_state"
        printf 'window_search_attempts=%s\n' "$window_attempts"
        printf 'af_inet_socket_calls=%s\n' "$inet_calls"
        printf 'af_inet_connect_calls=%s\n' "$inet_connects"
        printf 'fatal_diagnostics=%s\n' "$fatal_count"
        printf 'remaining_processes=%s\n' "$remaining_processes"
        printf 'owned_process_cleanup=%s\n' "$process_cleanup"
        printf 'report_logs=%s\n' "$report_logs"
        printf 'home_environment_reassigned=no\n'
        printf 'home_filesystem_isolated=%s\n' "$isolation_status"
        printf 'network_namespace=%s\n' "$isolation_status"
    } > "$reports_dir/smoke-test-summary.txt"
}

finish_outer() {
    local status=$1
    trap - EXIT ERR INT TERM
    set +e
    if [[ "$status" -ne 0 && -z "$failure_reason" ]]; then
        failure_reason="command failed with status $status"
    fi
    process_cleanup='NOT_NEEDED'
    if [[ -n "$runner_pid" || -n "$xvfb_pid" ]]; then process_cleanup='PASS'; fi
    if ! stop_owned_process "$runner_pid"; then process_cleanup='FAIL'; fi
    if ! stop_owned_process "$xvfb_pid"; then process_cleanup='FAIL'; fi
    if [[ "$process_cleanup" == 'FAIL' ]]; then
        failure_reason="${failure_reason:-owned process cleanup failed}"
        [[ "$status" -ne 0 ]] || status=1
    fi
    collect_diagnostics
    if ! check_remaining_processes; then
        failure_reason="${failure_reason:-processes remain or process check failed}"
        [[ "$status" -ne 0 ]] || status=1
    fi
    report_logs='PASS'
    if ! save_diagnostic_logs; then
        report_logs='FAIL'
        failure_reason="${failure_reason:-could not save diagnostic logs}"
        [[ "$status" -ne 0 ]] || status=1
    fi
    if ! write_summary "$status"; then
        printf 'smoke_appimage: could not save summary\n' >&2
        [[ "$status" -ne 0 ]] || status=1
    fi
    if [[ -n "$smoke_root" && -d "$smoke_root" ]]; then
        if ! rm -rf -- "$smoke_root"; then
            failure_reason="${failure_reason:-temporary data cleanup failed}"
            [[ "$status" -ne 0 ]] || status=1
            write_summary "$status" || true
        fi
    fi
    if [[ "$status" -eq 0 ]]; then printf 'Isolated AppImage smoke test: PASS\n'; fi
    exit "$status"
}

if [[ "${1-}" == '--inner' ]]; then
    [[ $# -eq 2 ]] || die "invalid inner invocation"
    run_inner "$2"
fi

[[ $# -eq 2 ]] || die "usage: $0 APPIMAGE REPORTS_DIR"
reports_dir="$(realpath -m -- "$2")"
mkdir -p -- "$reports_dir"
failure_reason=''
smoke_root=''
xvfb_pid=''
runner_pid=''
runner_started='no'
smoke_status='NOT_RUN'
elapsed_seconds='NOT_RUN'
display='NOT_STARTED'
window_check='NOT_RUN'
window_id='NOT_RUN'
window_map_state='NOT_RUN'
window_attempts='NOT_RUN'
inet_calls='NOT_RUN'
inet_connects='NOT_RUN'
fatal_count='NOT_RUN'
remaining_processes='NOT_RUN'
isolation_status='NOT_RUN'
process_cleanup='NOT_RUN'
report_logs='NOT_RUN'
trap 'finish_outer "$?"' EXIT
trap 'failure_reason="command failed at line $LINENO (status $?)"' ERR
trap 'failure_reason="interrupted by INT"; exit 130' INT
trap 'failure_reason="interrupted by TERM"; exit 143' TERM

reject_proxies
ulimit -c 0

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
[[ "$(git -C "$repo_root" rev-parse --show-toplevel)" == "$repo_root" ]] || \
    die "script is outside the Tokenlogue repository"
[[ "$(uname -s)" == 'Linux' && "$(uname -m)" == 'x86_64' ]] || \
    die "Linux x86_64 is required"

appimage="$(realpath -- "$1")"
[[ -x "$appimage" && -f "$appimage" ]] || die "AppImage is not executable"

for command_name in \
    bwrap dbus-run-session gdbus gnome-keyring-daemon pgrep \
    strace timeout xwininfo xprop Xvfb; do
    command -v "$command_name" >/dev/null || die "missing command: $command_name"
done

[[ -n "${HOME-}" && "$HOME" == /* && "$HOME" != '/' && -d "$HOME" ]] || \
    die "existing HOME must be an absolute user directory"
smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/tokenlogue-appimage-smoke.XXXXXX")"

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
if ! bwrap --unshare-net --ro-bind / / --proc /proc --dev /dev /usr/bin/true \
    2> "$smoke_root/logs/sandbox.stderr"; then
    die "bubblewrap user/network namespace is unavailable; no fallback is allowed"
fi
cp -p -- "$appimage" "$smoke_root/Tokenlogue.AppImage"
cp -p -- "$script_dir/smoke_appimage.sh" "$smoke_root/smoke_appimage.sh"
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

started_at=$SECONDS
runner_started='yes'
isolation_status='NOT_CONFIRMED'
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
    2>> "$smoke_root/logs/sandbox.stderr" &
runner_pid=$!

for _ in $(seq 1 80); do
    if find_tokenlogue_window; then break; fi
    kill -0 "$runner_pid" 2>/dev/null || break
    sleep 0.25
done
smoke_status=0
wait "$runner_pid" || smoke_status=$?
elapsed_seconds=$((SECONDS - started_at))
runner_pid=''
collect_diagnostics

[[ "$smoke_status" -eq 124 ]] || die "application exited before timeout: $smoke_status"
[[ "$window_check" == 'PASS' ]] || die "Tokenlogue window was not observed"
[[ "$inet_calls" != 'UNAVAILABLE' && "$inet_connects" != 'UNAVAILABLE' ]] || \
    die "network trace is unavailable"
[[ "$inet_calls" == '0' && "$inet_connects" == '0' ]] || \
    die "AF_INET or AF_INET6 activity detected"
[[ "$fatal_count" != 'UNAVAILABLE' ]] || die "runtime stderr is unavailable"
[[ "$fatal_count" == '0' ]] || die "fatal runtime diagnostics detected"
finish_outer 0
