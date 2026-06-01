#!/usr/bin/env bash
# =============================================================================
# start_full_stack.sh — Start the Energy Terminal backend and frontend together
# =============================================================================
# Usage:
#   ./scripts/start_full_stack.sh
#
# This script starts the Elixir gateway in the background (unless one is already
# running), then launches the PyQt6 desktop UI. When the UI exits or the script
# receives SIGINT/SIGTERM, it shuts down the backend it started.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
GATEWAY_URL="${ET_GATEWAY_URL:-ws://127.0.0.1:8765/ws}"
HEALTH_URL="${GATEWAY_URL/ws:/http:}"
HEALTH_URL="${HEALTH_URL/\/ws//health}"

BACKEND_STARTED=false
FRONTEND_STARTED=false

cleanup() {
    set +e
    if [[ "$FRONTEND_STARTED" = true && -n "${FRONTEND_PID:-}" ]]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [[ "$BACKEND_STARTED" = true && -n "${BACKEND_PID:-}" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

check_python() {
    if [[ -x "$FRONTEND_DIR/.venv/bin/python" ]]; then
        PYTHON_BIN="$FRONTEND_DIR/.venv/bin/python"
    elif command -v python3 &>/dev/null; then
        PYTHON_BIN="python3"
    else
        echo "ERROR: python3 not found. Install Python 3.11+ and try again."
        exit 1
    fi

    PYTHON_VERSION=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$(printf '%s\n' "3.11" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.11" ]]; then
        echo "ERROR: Python 3.11+ required (found $PYTHON_VERSION)."
        exit 1
    fi
}

ensure_frontend_package() {
    if ! "$PYTHON_BIN" -c 'import energy_terminal' &>/dev/null; then
        echo "▶ Installing frontend package into $PYTHON_BIN environment..."
        cd "$FRONTEND_DIR"
        "$PYTHON_BIN" -m pip install -e ".[dev]"
    fi
}

check_backend_available() {
    if command -v curl &>/dev/null && curl -sf "$HEALTH_URL" &>/dev/null; then
        echo "  ✓ Existing gateway detected at $GATEWAY_URL"
        return 0
    fi
    return 1
}

start_backend() {
    if check_backend_available; then
        echo "▶ Using existing backend at $GATEWAY_URL"
        return
    fi

    if ! command -v mix &>/dev/null; then
        echo "ERROR: mix not found. Install Elixir and ensure mix is on PATH."
        exit 1
    fi

    echo "▶ Compiling Elixir backend..."
    cd "$BACKEND_DIR"
    mix compile

    echo "▶ Starting backend gateway..."
    mix run --no-halt &
    BACKEND_PID=$!
    BACKEND_STARTED=true

    if command -v curl &>/dev/null; then
        echo "▶ Waiting for backend health endpoint..."
        for i in {1..15}; do
            if curl -sf "$HEALTH_URL" >/dev/null; then
                echo "  ✓ Backend health check passed"
                break
            fi
            sleep 1
        done
    fi

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "ERROR: backend process exited unexpectedly."
        exit 1
    fi
}

start_frontend() {
    echo "▶ Launching frontend UI..."
    cd "$FRONTEND_DIR"
    ET_GATEWAY_URL="$GATEWAY_URL" "$PYTHON_BIN" -m energy_terminal.main &
    FRONTEND_PID=$!
    FRONTEND_STARTED=true
}

check_python
ensure_frontend_package
start_backend
start_frontend

wait_args=()
if [[ -n "${BACKEND_PID:-}" ]]; then
    wait_args+=("$BACKEND_PID")
fi
if [[ -n "${FRONTEND_PID:-}" ]]; then
    wait_args+=("$FRONTEND_PID")
fi
if [[ ${#wait_args[@]} -gt 0 ]]; then
    wait -n "${wait_args[@]}" || true
fi
EXIT_CODE=$?

cleanup
exit "$EXIT_CODE"
