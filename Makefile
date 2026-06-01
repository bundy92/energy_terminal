# ============================================================================
# Energy Terminal — Unified Makefile
# ============================================================================
# Targets:
#   make install        Install all Python dependencies (dev mode)
#   make test           Run all tests (Erlang + Python)
#   make test-erlang    Run Erlang eunit + proper tests
#   make test-python    Run Python pytest suite with coverage
#   make lint           Run ruff + mypy (Python) + erlfmt check (Erlang)
#   make fmt            Auto-format all code
#   make run-backend    Start the Erlang OTP gateway
#   make run-frontend   Start the Python terminal UI
#   make run            Start both (backend in background)
#   make build-release  Build Erlang release + Python wheel
#   make clean          Remove build artefacts
# ============================================================================

SHELL      := /bin/bash
PYTHON     := python3
PIP        := $(PYTHON) -m pip
PYTEST     := $(PYTHON) -m pytest
RUFF       := $(PYTHON) -m ruff
MYPY       := $(PYTHON) -m mypy
MIX        := /usr/bin/mix

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
SRC_DIR      := $(FRONTEND_DIR)/src/energy_terminal

.PHONY: all install test test-erlang test-python lint fmt \
        run-backend run-frontend run build-release clean \
        help check-deps

# ----------------------------------------------------------------------------
# Default
# ----------------------------------------------------------------------------

all: lint test

# ----------------------------------------------------------------------------
# Installation
# ----------------------------------------------------------------------------

install: check-deps
	@echo "▶ Installing Python dependencies..."
	cd $(FRONTEND_DIR) && $(PIP) install -e ".[dev]"
	@echo "▶ Installing pre-commit hooks..."
	cd $(FRONTEND_DIR) && pre-commit install
	@echo "▶ Fetching Elixir dependencies..."
	cd $(BACKEND_DIR) && $(MIX) deps.get
	@echo "✓ Installation complete"

check-deps:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
	@command -v $(MIX) >/dev/null 2>&1 || { echo "ERROR: mix not found — install Elixir"; exit 1; }
	@command -v elixir >/dev/null 2>&1 || { echo "ERROR: elixir not found — install Elixir"; exit 1; }

# ----------------------------------------------------------------------------
# Testing
# ----------------------------------------------------------------------------

test: test-elixir test-python
	@echo "✓ All tests passed"

test-elixir:
	@echo "▶ Running Elixir tests..."
	cd $(BACKEND_DIR) && $(MIX) test
	@echo "✓ Elixir tests complete"

test-python:
	@echo "▶ Running Python tests..."
	cd $(FRONTEND_DIR) && $(PYTEST) \
		--cov=energy_terminal \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=85 \
		-v
	@echo "✓ Python tests complete"

test-python-fast:
	@echo "▶ Running Python tests (no coverage)..."
	cd $(FRONTEND_DIR) && $(PYTEST) -x -q

# ----------------------------------------------------------------------------
# Linting & formatting
# ----------------------------------------------------------------------------

lint: lint-python lint-elixir
	@echo "✓ All lint checks passed"

lint-python:
	@echo "▶ Running ruff..."
	cd $(FRONTEND_DIR) && $(RUFF) check $(SRC_DIR) tests/
	@echo "▶ Running mypy..."
	cd $(FRONTEND_DIR) && $(MYPY) $(SRC_DIR)

lint-elixir:
	@echo "▶ Checking Elixir formatting..."
	cd $(BACKEND_DIR) && $(MIX) format --check

fmt: fmt-python fmt-elixir

fmt-python:
	@echo "▶ Formatting Python (ruff)..."
	cd $(FRONTEND_DIR) && $(RUFF) check --fix $(SRC_DIR) tests/
	cd $(FRONTEND_DIR) && $(RUFF) format $(SRC_DIR) tests/

fmt-elixir:
	@echo "▶ Formatting Elixir..."
	cd $(BACKEND_DIR) && $(MIX) format

# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------

run-backend:
	@echo "▶ Starting Elixir gateway on ws://localhost:8765/ws ..."
	cd $(BACKEND_DIR) && $(MIX) run --no-halt

run-frontend:
	@echo "▶ Starting Energy Terminal UI..."
	cd $(FRONTEND_DIR) && $(PYTHON) -m energy_terminal.main

run:
	@echo "▶ Starting full stack..."
	@bash ./scripts/start_full_stack.sh

build-macos:
	@echo "▶ Building macOS .app bundle..."
	cd $(FRONTEND_DIR) && pyinstaller \
		--name=EnergyTerminal \
		--onedir \
		--windowed \
		--icon=../docs/icon.icns \
		--add-data="src/energy_terminal:energy_terminal" \
		--hidden-import=PyQt6 \
		--hidden-import=qasync \
		--osx-bundle-identifier=com.energy-terminal.app \
		src/energy_terminal/main.py
	@echo "✓ macOS app bundle ready at dist/EnergyTerminal.app"

# ----------------------------------------------------------------------------
# Release build
# ----------------------------------------------------------------------------

build-release:
	@echo "▶ Building Elixir release..."
	cd $(BACKEND_DIR) && $(MIX) release
	@echo "▶ Building Python wheel..."
	cd $(FRONTEND_DIR) && $(PYTHON) -m build
	@echo "✓ Release artefacts ready"

# ----------------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------------

clean:
	@echo "▶ Cleaning Elixir artefacts..."
	cd $(BACKEND_DIR) && $(MIX) clean
	rm -rf $(BACKEND_DIR)/_build $(BACKEND_DIR)/deps $(BACKEND_DIR)/log
	@echo "▶ Cleaning Python artefacts..."
	find $(FRONTEND_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(FRONTEND_DIR) -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find $(FRONTEND_DIR) -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(FRONTEND_DIR) -type d -name "htmlcov"     -exec rm -rf {} + 2>/dev/null || true
	find $(FRONTEND_DIR) -name ".coverage"           -exec rm -f  {} + 2>/dev/null || true
	@echo "✓ Clean complete"

# ----------------------------------------------------------------------------
# Help
# ----------------------------------------------------------------------------

help:
	@echo ""
	@echo "  Energy Terminal — Makefile targets"
	@echo "  ─────────────────────────────────"
	@echo "  make install        Install all dependencies"
	@echo "  make test           Run full test suite"
	@echo "  make test-erlang    Erlang eunit + PropEr only"
	@echo "  make test-python    Python pytest with coverage"
	@echo "  make lint           Run all linters"
	@echo "  make fmt            Auto-format all code"
	@echo "  make run-backend    Start Erlang gateway"
	@echo "  make run-frontend   Start Python UI"
	@echo "  make run            Start full stack"
	@echo "  make build-release  Build distributable artefacts"
	@echo "  make clean          Remove build artefacts"
	@echo ""
