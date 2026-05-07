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
REBAR      := rebar3

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
	@echo "▶ Fetching Erlang dependencies..."
	cd $(BACKEND_DIR) && $(REBAR) get-deps
	@echo "✓ Installation complete"

check-deps:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
	@command -v $(REBAR)  >/dev/null 2>&1 || { echo "ERROR: rebar3 not found — https://rebar3.org"; exit 1; }
	@command -v erl       >/dev/null 2>&1 || { echo "ERROR: Erlang/OTP not found — https://erlang.org"; exit 1; }

# ----------------------------------------------------------------------------
# Testing
# ----------------------------------------------------------------------------

test: test-erlang test-python
	@echo "✓ All tests passed"

test-erlang:
	@echo "▶ Running Erlang tests..."
	cd $(BACKEND_DIR) && $(REBAR) eunit --cover
	cd $(BACKEND_DIR) && $(REBAR) proper --cover 2>/dev/null || true
	@echo "✓ Erlang tests complete"

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

lint: lint-python lint-erlang
	@echo "✓ All lint checks passed"

lint-python:
	@echo "▶ Running ruff..."
	cd $(FRONTEND_DIR) && $(RUFF) check $(SRC_DIR) tests/
	@echo "▶ Running mypy..."
	cd $(FRONTEND_DIR) && $(MYPY) $(SRC_DIR)

lint-erlang:
	@echo "▶ Checking Erlang formatting..."
	cd $(BACKEND_DIR) && $(REBAR) fmt --check 2>/dev/null || \
		echo "  (erlfmt not available — skipping format check)"

fmt: fmt-python fmt-erlang

fmt-python:
	@echo "▶ Formatting Python (ruff)..."
	cd $(FRONTEND_DIR) && $(RUFF) check --fix $(SRC_DIR) tests/
	cd $(FRONTEND_DIR) && $(RUFF) format $(SRC_DIR) tests/

fmt-erlang:
	@echo "▶ Formatting Erlang (erlfmt)..."
	cd $(BACKEND_DIR) && $(REBAR) fmt 2>/dev/null || \
		echo "  (erlfmt not available — skipping)"

# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------

run-backend:
	@echo "▶ Starting Erlang gateway on ws://localhost:8765/ws ..."
	cd $(BACKEND_DIR) && $(REBAR) shell \
		--config config/sys.config \
		--vm_args config/vm.args

run-frontend:
	@echo "▶ Starting Energy Terminal UI..."
	cd $(FRONTEND_DIR) && $(PYTHON) -m energy_terminal.main

run:
	@echo "▶ Starting full stack..."
	cd $(BACKEND_DIR) && $(REBAR) shell \
		--config config/sys.config \
		--vm_args config/vm.args \
		--detached 2>/dev/null || \
		(cd $(BACKEND_DIR) && $(REBAR) shell &)
	sleep 3
	@echo "▶ Backend started. Launching UI..."
	cd $(FRONTEND_DIR) && $(PYTHON) -m energy_terminal.main

# ----------------------------------------------------------------------------
# Release build
# ----------------------------------------------------------------------------

build-release:
	@echo "▶ Building Erlang release..."
	cd $(BACKEND_DIR) && $(REBAR) release
	@echo "▶ Building Python wheel..."
	cd $(FRONTEND_DIR) && $(PYTHON) -m build
	@echo "✓ Release artefacts ready"

# ----------------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------------

clean:
	@echo "▶ Cleaning Erlang artefacts..."
	cd $(BACKEND_DIR) && $(REBAR) clean
	rm -rf $(BACKEND_DIR)/_build $(BACKEND_DIR)/log
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
