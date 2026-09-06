#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
export LC_ALL=C

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Generated during container preparation from exact existing smoke functions.
# shellcheck source=/dev/null
source "$script_dir/smoke-functions.sh"
reports_dir=/reports
failure_reason=''
smoke_root=''
runner_pid=''
xvfb_pid=''
smoke_status=NOT_RUN
elapsed_seconds=NOT_RUN
display=NOT_STARTED
window_check=NOT_RUN
window_id=NOT_RUN
window_map_state=NOT_RUN
# These two globals are consumed by the imported diagnostic functions.
# shellcheck disable=SC2034
window_attempts=NOT_RUN
inet_calls=NOT_RUN
inet_connects=NOT_RUN
fatal_count=NOT_RUN
# shellcheck disable=SC2034
isolation_status=NOT_RUN
hash_check=NOT_RUN
phase=BLOCKED
expected_hash=${1-}
os_id=${2-}
version_id=${3-}
mkdir -p "$reports_dir"

collect_matrix_diagnostics() {
    local extra_fatal
    collect_diagnostics
    [[ -n "$smoke_root" && "$fatal_count" =~ ^[0-9]+$ ]] || return 0
    extra_fatal=$(count_log_matches \
        'error while loading shared libraries|undefined symbol|\+\+\+ killed by SIG(SEGV|ABRT|BUS|ILL)' \
        "$smoke_root/logs/application.stderr" "$smoke_root/logs/sandbox.stderr" \
        "$smoke_root"/logs/trace.*)
    if [[ "$extra_fatal" =~ ^[0-9]+$ ]]; then
        fatal_count=$((fatal_count + extra_fatal))
    else
        fatal_count=UNAVAILABLE
    fi
}

# Invoked by the EXIT trap, including early environment failures.
# shellcheck disable=SC2317
finish() {
    local status=$1 cleanup_json result=$phase
    trap - EXIT ERR INT TERM
    set +e
    stop_owned_process "$runner_pid" || status=1
    stop_owned_process "$xvfb_pid" || status=1
    if ! cleanup_json="$(python3 "$script_dir/container_matrix.py" cleanup)"; then
        cleanup_json='{"cleanup":"UNAVAILABLE","remaining_processes":"UNAVAILABLE"}'
        status=1
    fi
    collect_matrix_diagnostics
    save_diagnostic_logs || status=1
    if [[ -f /input/Tokenlogue.AppImage && "$expected_hash" =~ ^[0-9a-f]{64}$ ]]; then
        local after
        after=$(sha256sum /input/Tokenlogue.AppImage)
        hash_check=FAIL
        [[ "${after%% *}" == "$expected_hash" ]] && hash_check=PASS
        if [[ -n "$smoke_root" && -f "$smoke_root/Tokenlogue.AppImage" ]]; then
            after=$(sha256sum "$smoke_root/Tokenlogue.AppImage")
            [[ "${after%% *}" == "$expected_hash" ]] || hash_check=FAIL
        else
            hash_check=NOT_RUN
        fi
    fi
    [[ "$hash_check" == PASS ]] || status=1
    [[ "$inet_calls" == 0 && "$inet_connects" == 0 && "$fatal_count" == 0 ]] || status=1
    [[ "$status" -eq 0 ]] && result=PASS
    # Only measured values are serialized; NOT_RUN/UNAVAILABLE stay explicit.
    if ! python3 - "$reports_dir/container-summary.json" "$result" \
        "${failure_reason:-completed}" "$status" "$smoke_status" "$elapsed_seconds" \
        "$window_check" "$window_id" "$window_map_state" "$inet_calls" \
        "$inet_connects" "$fatal_count" "$hash_check" "$cleanup_json" <<'PY'
import json
import sys
from pathlib import Path

keys = ("result", "reason", "script_exit_code", "exit_code", "elapsed_seconds",
        "window_check", "window_id", "window_map_state", "af_inet_socket_calls",
        "af_inet_connect_calls", "fatal_diagnostics", "hash_check")
report = dict(zip(keys, sys.argv[2:14]))
if report["elapsed_seconds"].isdigit():
    report["elapsed_seconds"] = int(report["elapsed_seconds"])
report.update(json.loads(sys.argv[14]))
if report["cleanup"] != "PASS":
    report.update(result="FAIL", reason="process cleanup not confirmed")
report["timeout_seconds"] = 20
Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if report["cleanup"] == "PASS" else 1)
PY
    then status=1; fi
    # Private data only; diagnostics were copied above. Never upload raw traces.
    if [[ -n "$smoke_root" && -d "$smoke_root" ]]; then
        rm -rf -- "$smoke_root" || status=1
    fi
    exit "$status"
}
trap 'finish "$?"' EXIT
trap 'failure_reason="container command failed at line $LINENO (status $?)"' ERR
trap 'failure_reason="interrupted"; exit 143' TERM
trap 'failure_reason="interrupted"; exit 130' INT

[[ -f /run/tokenlogue-matrix-container && "$(id -u)" == 10001 ]] || \
    die "requires the disposable unprivileged matrix container"
[[ "$expected_hash" =~ ^[0-9a-f]{64}$ ]] || die "invalid SHA-256"
ulimit -c 0
cp /etc/os-release "$reports_dir/os-release.txt"
if command -v dpkg-query >/dev/null; then
    dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > "$reports_dir/system-packages.txt"
else
    rpm -qa --qf '%{NAME}\t%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort > "$reports_dir/system-packages.txt"
fi
python3 - "$os_id" "$version_id" <<'PY'
import shlex
import sys
from pathlib import Path
values = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
assert shlex.split(values["ID"])[0] == sys.argv[1], "unexpected distribution"
assert shlex.split(values["VERSION_ID"])[0] == sys.argv[2], "unexpected distribution version"
PY
for tool in Xvfb xwininfo xprop timeout strace dbus-run-session gdbus gnome-keyring-daemon; do
    command -v "$tool" >/dev/null || die "missing diagnostic tool: $tool"
done
before=$(sha256sum /input/Tokenlogue.AppImage)
[[ "${before%% *}" == "$expected_hash" ]] || die "pre-test SHA-256 mismatch"
smoke_root=$(mktemp -d /tmp/tokenlogue-matrix.XXXXXX)
mkdir -m 0700 "$smoke_root"/{xdg-data,xdg-config,xdg-cache,runtime,storage,tmp,logs}
cp /input/Tokenlogue.AppImage "$smoke_root/Tokenlogue.AppImage"
chmod 0755 "$smoke_root/Tokenlogue.AppImage"
copied=$(sha256sum "$smoke_root/Tokenlogue.AppImage")
[[ "${copied%% *}" == "$expected_hash" ]] || die "copied AppImage SHA-256 mismatch"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
unset DBUS_SESSION_BUS_ADDRESS GNOME_KEYRING_CONTROL GNOME_KEYRING_PID SSH_AUTH_SOCK
unset OPENROUTER_API_KEY XAUTHORITY
export LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=x11
Xvfb -displayfd 3 -screen 0 1280x720x24 -nolisten tcp -ac \
    3> "$smoke_root/display" > /dev/null 2> "$smoke_root/logs/xvfb.stderr" &
xvfb_pid=$!
for _ in $(seq 1 40); do
    [[ -s "$smoke_root/display" ]] && break
    kill -0 "$xvfb_pid" 2>/dev/null || die "Xvfb exited early"
    sleep 0.1
done
[[ -s "$smoke_root/display" ]] || die "Xvfb unavailable"
display_number=$(tr -d '\r\n' < "$smoke_root/display")
[[ "$display_number" =~ ^[0-9]+$ ]] || die "invalid Xvfb display"
display=":$display_number"
export DISPLAY="$display"
phase=FAIL
started_at=$SECONDS
# The container replaces only the isolation boundary, not the application probe.
timeout --signal=TERM --kill-after=5s 20s dbus-run-session -- \
    bash "$script_dir/smoke_appimage.sh" --inner "$smoke_root" \
    > /dev/null 2> "$smoke_root/logs/sandbox.stderr" &
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
collect_matrix_diagnostics
[[ "$smoke_status" == 124 && "$elapsed_seconds" -ge 20 ]] || die "application exited before timeout"
[[ "$window_check" == PASS ]] || die "Tokenlogue window was not observed"
[[ "$inet_calls" == 0 && "$inet_connects" == 0 ]] || die "network activity detected or evidence unavailable"
[[ "$fatal_count" == 0 ]] || die "runtime failure or stderr unavailable"
exit 0
