#!/usr/bin/env bash
# =============================================================================
# start_backend.sh — Start the Erlang/OTP Energy Gateway
# =============================================================================
# Usage:
#   ./scripts/start_backend.sh          # interactive shell
#   ./scripts/start_backend.sh detached # background daemon
#
# Required environment variables (optional but recommended):
#   EIA_API_KEY    US Energy Information Administration API key
#                  Register at: https://www.eia.gov/opendata/register.php
#   FRED_API_KEY   Federal Reserve FRED API key
#                  Register at: https://fred.stlouisfed.org/docs/api/api_key.html
#   IEA_API_KEY    IEA Open Data API key
#                  Register at: https://www.iea.org/data-and-statistics/data-tools
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

# Validate rebar3 is available
if ! command -v rebar3 &>/dev/null; then
    echo "ERROR: rebar3 not found."
    echo "       Install: https://rebar3.org or 'brew install rebar3' on macOS"
    exit 1
fi

# Validate Erlang is available
if ! command -v erl &>/dev/null; then
    echo "ERROR: Erlang/OTP not found."
    echo "       Install: https://erlang.org/downloads or 'brew install erlang'"
    exit 1
fi

# Environment variable hints
warn_missing_key() {
    local var="$1"
    local url="$2"
    if [[ -z "${!var:-}" ]]; then
        echo "  ⚠  $var not set — feed will run in limited mode"
        echo "     Register at: $url"
    else
        echo "  ✓  $var is set"
    fi
}

echo ""
echo "  ⬡  Energy Terminal — Erlang Gateway"
echo "  ────────────────────────────────────"
warn_missing_key EIA_API_KEY  "https://www.eia.gov/opendata/register.php"
warn_missing_key FRED_API_KEY "https://fred.stlouisfed.org/docs/api/api_key.html"
warn_missing_key IEA_API_KEY  "https://www.iea.org/data-and-statistics"
echo ""

# Create log directory
mkdir -p "$BACKEND_DIR/log"

cd "$BACKEND_DIR"

# Compile first
echo "▶ Compiling..."
rebar3 compile

echo "▶ Starting gateway on ws://localhost:8765/ws ..."
echo "   Health: http://localhost:8765/health"
echo ""

if [[ "${1:-}" == "detached" ]]; then
    ERL_FLAGS="-detached" rebar3 shell \
        --config config/sys.config \
        --vm_args config/vm.args
    echo "✓ Gateway started in background (PID written to backend/log/)"
else
    rebar3 shell \
        --config config/sys.config \
        --vm_args config/vm.args
fi
