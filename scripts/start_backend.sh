#!/usr/bin/env bash
# =============================================================================
# start_backend.sh — Start the Elixir/OTP Energy Gateway
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

# Validate mix is available
if ! command -v mix &>/dev/null; then
    echo "ERROR: mix not found."
    echo "       Install Elixir: https://elixir-lang.org/install.html"
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
echo "  ⬡  Energy Terminal — Elixir Gateway"
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
/usr/bin/mix compile

echo "▶ Starting gateway on ws://localhost:8765/ws ..."
echo "   Health: http://localhost:8765/health"
echo ""

if [[ "${1:-}" == "detached" ]]; then
    /usr/bin/mix run --no-halt &
    echo "✓ Gateway started in background"
else
    /usr/bin/mix run --no-halt
fi
