#!/usr/bin/env bash

# Guarded Node-RED entry point for uNode test jobs.
#
# The dashboard may only select known profiles and bounded options. A shared
# flock protects the uNode/RP2040 fixture from concurrent jobs. Each test runner
# is placed in its own process group so `stop` can deliver SIGINT to pytest and
# still allow fixtures to restore the uNode configuration cleanly.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_FILE="${UNODE_TEST_JOB_LOCK_FILE:-/tmp/unode-test-job.lock}"
STATUS_FILE="${UNODE_TEST_JOB_STATUS_FILE:-/tmp/unode-test-job-status.json}"
CANCEL_FILE="${UNODE_TEST_JOB_CANCEL_FILE:-/tmp/unode-test-job-cancelled}"
MIN_SECONDS=60
MAX_SECONDS=86400
WORKER_PID=0

write_status() {
    local running="$1"
    local state="$2"
    local profile="$3"
    local duration="$4"
    local worker_pid="$5"
    local exit_code="$6"
    local started_at="$7"
    local finished_at="$8"
    local options="$9"
    local temp_file="${STATUS_FILE}.tmp"

    printf '{"running":%s,"state":"%s","profile":"%s","duration":%s,"pid":%s,"workerPid":%s,"exitCode":%s,"startedAt":"%s","finishedAt":"%s","options":"%s"}\n' \
        "$running" "$state" "$profile" "$duration" "$$" "$worker_pid" \
        "$exit_code" "$started_at" "$finished_at" "$options" > "$temp_file"
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
                -e 's/"state":"cancelling"/"state":"interrupted"/' \
                "$STATUS_FILE"
        fi
    else
        printf '{"running":%s,"state":"idle","profile":"","duration":0,"pid":0,"workerPid":0,"exitCode":null,"startedAt":"","finishedAt":"","options":""}\n' "$locked"
    fi
}

stop_job() {
    local worker_pid
    local pytest_pids=()

    if [[ ! -s "$STATUS_FILE" ]] || flock -n "$LOCK_FILE" -c true 2>/dev/null; then
        echo "No uNode test job is running"
        show_status
        return 0
    fi

    worker_pid="$(sed -n 's/.*"workerPid":\([0-9][0-9]*\).*/\1/p' "$STATUS_FILE")"
    if [[ -z "$worker_pid" || "$worker_pid" -le 1 ]]; then
        echo "Running test job has no valid worker PID" >&2
        return 1
    fi

    touch "$CANCEL_FILE"
    sed 's/"state":"running"/"state":"cancelling"/' "$STATUS_FILE" > "${STATUS_FILE}.tmp"
    mv "${STATUS_FILE}.tmp" "$STATUS_FILE"

    mapfile -t pytest_pids < <(
        pgrep -g "$worker_pid" -f 'python.*-m pytest' 2>/dev/null || true
    )
    if [[ "${#pytest_pids[@]}" -gt 0 ]]; then
        kill -INT "${pytest_pids[@]}" 2>/dev/null || true
    elif ! kill -INT -- "-$worker_pid" 2>/dev/null; then
        kill -INT "$worker_pid" 2>/dev/null || true
    fi
    echo "Cancellation requested for uNode test worker $worker_pid"
}

case "${1:-}" in
    status)
        show_status
        exit 0
        ;;
    stop)
        stop_job
        exit $?
        ;;
esac

# Force every started job into its own foreground session. `-f` also works when
# the caller (for example SSH) already made this shell a process-group leader;
# `-w` keeps the Node-RED exec node attached until the test has finished.
if [[ "${UNODE_TEST_JOB_SESSION:-}" != "1" ]]; then
    exec setsid -f -w env UNODE_TEST_JOB_SESSION=1 "$0" "$@"
fi

PROFILE="${1:-}"
VALUE="${2:-}"
DURATION=0
OPTIONS=""
STARTED_AT=""
CMD=()

case "$PROFILE" in
    host|dmx)
        DURATION="$VALUE"
        if [[ ! "$DURATION" =~ ^[0-9]+$ ]] \
            || (( DURATION < MIN_SECONDS || DURATION > MAX_SECONDS )); then
            echo "Duration must be an integer between $MIN_SECONDS and $MAX_SECONDS seconds" >&2
            exit 2
        fi
        ;;
    regression|reconnect)
        OPTIONS="${VALUE:-none}"
        ;;
    *)
        echo "Profile must be 'host', 'dmx', 'regression', or 'reconnect'" >&2
        exit 2
        ;;
esac

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Another uNode test job is already running" >&2
    exit 75
fi

rm -f "$CANCEL_FILE"
STARTED_AT="$(date --iso-8601=seconds)"
WORKER_PID=$$
write_status true running "$PROFILE" "$DURATION" "$WORKER_PID" null \
    "$STARTED_AT" "" "$OPTIONS"

finish() {
    local exit_code="$1"
    local state="failed"

    if [[ -f "$CANCEL_FILE" ]]; then
        state="cancelled"
    elif [[ "$exit_code" -eq 0 ]]; then
        state="passed"
    fi

    write_status false "$state" "$PROFILE" "$DURATION" "$WORKER_PID" \
        "$exit_code" "$STARTED_AT" "$(date --iso-8601=seconds)" "$OPTIONS"
    rm -f "$CANCEL_FILE"
}

mark_cancelled() {
    touch "$CANCEL_FILE"
}

trap 'finish $?' EXIT
trap 'mark_cancelled' INT TERM

cd "$PROJECT_ROOT"

case "$PROFILE" in
    host)
        CMD=(
            bash tools/test.sh
            --integration
            --path tests/integration/test_soak.py
            --soak-seconds "$DURATION"
        )
        ;;
    dmx)
        CMD=(
            bash tools/test.sh
            --integration
            --rp2040-port auto
            --path tests/integration/test_dmx_soak_hil.py
            --dmx-soak-seconds "$DURATION"
        )
        ;;
    regression)
        USE_RP2040=false
        USE_BUTTON=false
        USE_RESET=false
        INCLUDE_SOAK=false
        OTA_PROFILE=""

        IFS=',' read -r -a flags <<< "$OPTIONS"
        for flag in "${flags[@]}"; do
            case "$flag" in
                none|"") ;;
                rp2040) USE_RP2040=true ;;
                button) USE_BUTTON=true; USE_RP2040=true ;;
                reset) USE_RESET=true; USE_RP2040=true ;;
                soak) INCLUDE_SOAK=true ;;
                ota-normal) OTA_PROFILE="normal" ;;
                ota-legacy) OTA_PROFILE="legacy" ;;
                *)
                    echo "Unsupported regression option: $flag" >&2
                    exit 2
                    ;;
            esac
        done

        CMD=(bash tools/test.sh --integration --path tests/integration)
        [[ "$USE_RP2040" == true ]] && CMD+=(--rp2040-port auto)
        [[ "$USE_BUTTON" == true ]] && CMD+=(--button-gpio 8)
        [[ "$USE_RESET" == true ]] && CMD+=(--reset-gpio 7)
        if [[ -n "$OTA_PROFILE" ]]; then
            CMD+=(--ota --ota-profile "$OTA_PROFILE")
        fi

        PYTEST_EXTRA=()
        if [[ "$INCLUDE_SOAK" != true ]]; then
            PYTEST_EXTRA+=(
                --ignore=tests/integration/test_soak.py
                --ignore=tests/integration/test_dmx_soak_hil.py
            )
        fi
        [[ -n "$OTA_PROFILE" ]] && PYTEST_EXTRA+=(tests/ota/test_ota_safe.py)
        if [[ "${#PYTEST_EXTRA[@]}" -gt 0 ]]; then
            CMD+=(-- "${PYTEST_EXTRA[@]}")
        fi
        ;;
    reconnect)
        CMD=(
            bash tools/test.sh
            --integration
            --reconnection
            --path tests/integration/test_network_reconnection.py
        )
        ;;
esac

if [[ -f "$CANCEL_FILE" ]]; then
    exit 130
fi
write_status true running "$PROFILE" "$DURATION" "$WORKER_PID" null \
    "$STARTED_AT" "" "$OPTIONS"

set +e
"${CMD[@]}"
EXIT_CODE=$?
set -e
exit "$EXIT_CODE"
