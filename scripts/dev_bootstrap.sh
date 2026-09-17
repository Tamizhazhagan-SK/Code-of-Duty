#!/usr/bin/env bash
# Internal contributor bootstrap for ZeroTrace (private/org-only repo).
#
# This repo is not public yet, so the curl-to-raw-URL one-liners in README.md
# don't work anonymously. Run this instead, from a checkout you already have
# access to via your own git credentials (SSH key or cached HTTPS token):
#
#   git clone https://github.com/Tamizhazhagan-SK/Code-of-Duty.git
#   cd Code-of-Duty
#   ./scripts/dev_bootstrap.sh
#
# Sets up .venv, installs zerotrace in editable dev+llm mode, enables the
# global git hook on this machine, runs doctor, then runs the full test
# suite - so both contributors can confirm a checkout is healthy the same way.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: no python3/python found. See docs/INSTALL.md" >&2; exit 1; }
info "Using $("$PY" --version)"

if [ ! -d ".venv" ]; then
  info "Creating .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

info "Installing zerotrace (editable, dev+llm extras)"
python -m pip install --upgrade pip --quiet
pip install -e ".[dev,llm]" --quiet

info "Enabling the global git hook"
zerotrace install --global || warn "install --global reported an issue, see output above"

info "Running doctor"
zerotrace doctor || true

info "Running the test suite"
pytest -q
