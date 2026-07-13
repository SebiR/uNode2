#!/usr/bin/env bash

# Linux test runner for development PCs and the Raspberry Pi production rig.
# Run tools/bootstrap_test_host.sh once before using this script.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${UNODE_TEST_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"

INTEGRATION=0
NODE_IP=""
BASE_URL=""
PASSWORD=""
RP2040_PORT=""
TEST_PATH=""
PYTEST_EXTRA=()

usage() {
    cat <<'EOF'
Usage: tools/test.sh [options] [-- pytest-args]

  --integration                 Run tests against a real uNode
  --node-ip ADDRESS             Target node, otherwise discover with ArtPoll
  --base-url URL                Override the HTTP base URL
  --password PASSWORD           Web/API password
  --rp2040-port PORT            Serial device or "auto"
  --button-gpio PIN             RP2040 GPIO wired to the uNode button
  --reset-gpio PIN              RP2040 GPIO wired to the uNode reset input
  --path PATH                   Test file/directory (default depends on mode)
  --soak-seconds N              Host/network soak duration
  --dmx-soak-seconds N          RP2040 DMX soak duration
  --latency-samples N           Latency samples per profile
  --dropout-samples N           Dropout samples per profile
  --report-json PATH            Explicit JSON report path
  -h, --help                    Show this help

Additional tuning can be supplied with the existing UNODE_* environment
variables. Arguments after -- are passed directly to pytest.
EOF
}

require_value() {
    if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for $1" >&2
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --integration) INTEGRATION=1; shift ;;
        --node-ip) require_value "$@"; NODE_IP="$2"; shift 2 ;;
        --base-url) require_value "$@"; BASE_URL="$2"; shift 2 ;;
        --password) require_value "$@"; PASSWORD="$2"; shift 2 ;;
        --rp2040-port) require_value "$@"; RP2040_PORT="$2"; shift 2 ;;
        --button-gpio) require_value "$@"; export UNODE_BUTTON_GPIO_PIN="$2"; shift 2 ;;
        --reset-gpio) require_value "$@"; export UNODE_RESET_GPIO_PIN="$2"; shift 2 ;;
        --path) require_value "$@"; TEST_PATH="$2"; shift 2 ;;
        --soak-seconds) require_value "$@"; export UNODE_SOAK_SECONDS="$2"; shift 2 ;;
        --dmx-soak-seconds) require_value "$@"; export UNODE_DMX_SOAK_SECONDS="$2"; shift 2 ;;
        --latency-samples) require_value "$@"; export UNODE_LATENCY_SAMPLES="$2"; shift 2 ;;
        --dropout-samples) require_value "$@"; export UNODE_DROPOUT_SAMPLES="$2"; shift 2 ;;
        --report-json) require_value "$@"; export UNODE_TEST_REPORT_JSON="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; PYTEST_EXTRA+=("$@"); break ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ ! -x "$PYTHON" ]]; then
    echo "Python environment not found: $PYTHON" >&2
    echo "Run tools/bootstrap_test_host.sh first." >&2
    exit 2
fi

cd "$PROJECT_ROOT"

if [[ "$INTEGRATION" -eq 1 ]]; then
    if [[ -z "$NODE_IP" && -z "$BASE_URL" ]]; then
        echo "Discover : ArtPoll on available IPv4 interfaces"
        if NODE_IP="$($PYTHON tools/discover_unode.py --first-ip --timeout 1.5)"; then
            echo "Found    : $NODE_IP"
        else
            NODE_IP="2.0.0.1"
            echo "Found    : none, falling back to $NODE_IP"
        fi
    fi

    if [[ -z "$NODE_IP" ]]; then
        NODE_IP="$($PYTHON -c 'import sys, urllib.parse; print(urllib.parse.urlparse(sys.argv[1]).hostname)' "$BASE_URL")"
    fi
    if [[ -z "$BASE_URL" ]]; then
        BASE_URL="http://$NODE_IP"
    fi

    export UNODE_RUN_INTEGRATION=1
    export UNODE_IP="$NODE_IP"
    export UNODE_BASE_URL="$BASE_URL"
    unset UNODE_PASSWORD UNODE_RP2040_PORT
    [[ -n "$PASSWORD" ]] && export UNODE_PASSWORD="$PASSWORD"
    [[ -n "$RP2040_PORT" ]] && export UNODE_RP2040_PORT="$RP2040_PORT"
    TEST_PATH="${TEST_PATH:-tests/integration}"
    PYTEST_ARGS=(-s -vv "$TEST_PATH")
    MODE="integration"
else
    unset UNODE_RUN_INTEGRATION
    TEST_PATH="${TEST_PATH:-tests/unit}"
    PYTEST_ARGS=("$TEST_PATH")
    MODE="unit/offline"
fi

echo "uNode test runner"
echo "Project : $PROJECT_ROOT"
echo "Python  : $($PYTHON --version 2>&1)"
echo "pytest  : $($PYTHON -m pytest --version)"
echo "Mode    : $MODE"
if [[ "$INTEGRATION" -eq 1 ]]; then
    echo "Node IP : $UNODE_IP"
    echo "Base URL: $UNODE_BASE_URL"
    [[ -n "${UNODE_RP2040_PORT:-}" ]] && echo "RP2040  : $UNODE_RP2040_PORT"
fi
echo "Tests   : $TEST_PATH"
echo

LOG_DIR="$PROJECT_ROOT/artifacts/test_reports"
LATEST_LOG="$LOG_DIR/latest-run.log"
mkdir -p "$LOG_DIR"

set +e
PYTHONUNBUFFERED=1 "$PYTHON" -m pytest \
    "${PYTEST_ARGS[@]}" "${PYTEST_EXTRA[@]}" 2>&1 | tee "$LATEST_LOG"
EXIT_CODE=${PIPESTATUS[0]}
set -e

echo
echo "Cleaning pytest caches"
find "$PROJECT_ROOT" -type d \( -name __pycache__ -o -name .pytest_cache \) \
    -prune -exec rm -rf {} +

exit "$EXIT_CODE"
