#!/usr/bin/env bash

# Safe Node-RED entry point for long-running uNode soak profiles.
#
# The dashboard may only select a known profile and a bounded duration. flock
# protects the shared uNode/RP2040 fixture from concurrent test runs, including
# tests started manually through this wrapper in a second shell.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_FILE="${UNODE_SOAK_LOCK_FILE:-/tmp/unode-soak.lock}"
STATUS_FILE="${UNODE_SOAK_STATUS_FILE:-/tmp/unode-soak-status.json}"
MIN_SECONDS=60
MAX_SECONDS=86400

write_status() {
    local running="$1"
    local state="$2"
    local profile="$3"
    local duration="$4"
    local exit_code="$5"
    local started_at="$6"
    local finished_at="$7"
    local temp_file="${STATUS_FILE}.tmp"

    printf '{"running":%s,"state":"%s","profile":"%s","duration":%s,"pid":%s,"exitCode":%s,"startedAt":"%s","finishedAt":"%s"}\n' \
        "$running" "$state" "$profile" "$duration" "$$" "$exit_code" \
        "$started_at" "$finished_at" > "$temp_file"
    mv "$temp_file" "$STATUS_FILE"
}

show_status() {
    local locked=false
    if ! flock -n "$LOCK_FILE" -c true 2>/dev/null; then
        locked=true
    fi

    if [[ -s "$STATUS_FILE" ]]; then
        if [[ "$locked" == true ]]; then
            sed 's/"running":false/"running":true/' "$STATUS_FILE"
        else
            sed \
                -e 's/"running":true/"running":false/' \
                -e 's/"state":"running"/"state":"interrupted"/' \
                "$STATUS_FILE"
        fi
    else
        printf '{"running":%s,"state":"idle","profile":"","duration":0,"pid":0,"exitCode":null,"startedAt":"","finishedAt":""}\n' "$locked"
    fi
}

if [[ "${1:-}" == "status" ]]; then
    show_status
    exit 0
fi

PROFILE="${1:-}"
DURATION="${2:-}"

case "$PROFILE" in
    host|dmx) ;;
    *)
        echo "Profile must be 'host' or 'dmx'" >&2
        exit 2
        ;;
esac

if [[ ! "$DURATION" =~ ^[0-9]+$ ]] \
    || (( DURATION < MIN_SECONDS || DURATION > MAX_SECONDS )); then
    echo "Duration must be an integer between $MIN_SECONDS and $MAX_SECONDS seconds" >&2
    exit 2
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Another uNode soak test is already running" >&2
    exit 75
fi

STARTED_AT="$(date --iso-8601=seconds)"
write_status true running "$PROFILE" "$DURATION" null "$STARTED_AT" ""

finish() {
    local exit_code="$1"
    local state="failed"
    [[ "$exit_code" -eq 0 ]] && state="passed"
    write_status false "$state" "$PROFILE" "$DURATION" "$exit_code" \
        "$STARTED_AT" "$(date --iso-8601=seconds)"
}
trap 'finish $?' EXIT

cd "$PROJECT_ROOT"

case "$PROFILE" in
    host)
        bash tools/test.sh \
            --integration \
            --path tests/integration/test_soak.py \
            --soak-seconds "$DURATION"
        ;;
    dmx)
        bash tools/test.sh \
            --integration \
            --rp2040-port auto \
            --path tests/integration/test_dmx_soak_hil.py \
            --dmx-soak-seconds "$DURATION"
        ;;
esac
