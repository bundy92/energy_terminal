#!/usr/bin/env bash
# =============================================================================
# start_terminal.sh — Start the Energy Terminal desktop UI
# =============================================================================
# Usage:
#   ./scripts/start_terminal.sh
#
# The terminal connects to the Erlang gateway at ws://localhost:8765/ws by
# default.  If the gateway is unreachable it falls back to direct yfinance
# polling (data will be delayed 15-20 minutes for most instruments).
#
# Override the gateway URL:
#   ET_GATEWAY_URL=ws://192.168.1.10:8765/ws ./scripts/start_terminal.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo ""
echo "  ⬡  Energy Terminal — Desktop UI"
echo "  ─────────────────────────────────"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED="3.11"
if [[ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]]; then
    echo "ERROR: Python $REQUIRED+ required (found $PYTHON_VERSION)"
    exit 1
fi

# Check package is installed
if ! python3 -c "import energy_terminal" &>/dev/null; then
    echo "▶ Installing energy_terminal package..."
    cd "$FRONTEND_DIR" && pip install -e ".[dev]" --quiet
fi

# Gateway ping (optional — UI handles reconnect itself)
GATEWAY_URL="${ET_GATEWAY_URL:-ws://localhost:8765/ws}"
HEALTH_URL="${GATEWAY_URL/ws:/http:}"
HEALTH_URL="${HEALTH_URL/\/ws//health}"

if curl -sf "$HEALTH_URL" &>/dev/null; then
    echo "  ✓  Erlang gateway reachable at $GATEWAY_URL"
else
    echo "  ⚠  Gateway not reachable — UI will use direct feed (delayed data)"
fi

echo ""
echo "▶ Starting Energy Terminal..."
echo ""

cd "$FRONTEND_DIR"
ET_GATEWAY_URL="$GATEWAY_URL" python3 -m energy_terminal.main
