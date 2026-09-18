#!/usr/bin/env bash
# ZeroTrace one-command bootstrap installer for macOS and Linux.
#
#   install:    curl -fsSL https://raw.githubusercontent.com/Tamizhazhagan-SK/Code-of-Duty/main/install.sh | bash
#   uninstall:  curl -fsSL https://raw.githubusercontent.com/Tamizhazhagan-SK/Code-of-Duty/main/install.sh | bash -s -- --uninstall
#   (from a clone: ./install.sh   /   ./install.sh --uninstall)
#
# Does NOT assume pip, pipx, uv or any Python packaging tool is already
# installed. The only hard prerequisite is git (ZeroTrace is a git hook
# manager, so a machine without git has nothing for it to protect anyway).
# If Python itself is missing, this script makes a best-effort attempt to
# install it with whatever OS package manager is present.
set -euo pipefail

REPO_URL="${ZEROTRACE_REPO_URL:-https://github.com/Tamizhazhagan-SK/Code-of-Duty.git}"
REF="${ZEROTRACE_REF:-main}"
EXTRAS="${ZEROTRACE_EXTRAS:-}"   # e.g. "llm,pii-ner" - passed through to pip's [extra] syntax
PY_MIN_MAJOR=3
PY_MIN_MINOR=11

UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --uninstall|--remove) UNINSTALL=1 ;;
    --with-llm) EXTRAS="${EXTRAS:+$EXTRAS,}llm" ;;
    --with-pii) EXTRAS="${EXTRAS:+$EXTRAS,}pii-ner" ;;
    --ref=*) REF="${arg#--ref=}" ;;
    *) echo "warn: ignoring unknown argument '$arg'" >&2 ;;
  esac
done

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mERROR\033[0m %s\n' "$1" >&2; exit 1; }

# Remove everything this script installs: git hooks first (so no repo is left pointing at a
# binary that is about to disappear), then the package, then the PATH lines and state dir.
do_uninstall() {
  local python bin_dir zerotrace_bin
  python="$(find_python || true)"
  [ -n "$python" ] || die "no Python found; nothing to uninstall (or remove ~/.zerotrace by hand)."

  zerotrace_bin="$(command -v zerotrace || true)"
  if [ -z "$zerotrace_bin" ]; then
    bin_dir="$("$python" -m site --user-base 2>/dev/null)/bin"
    [ -x "$bin_dir/zerotrace" ] && zerotrace_bin="$bin_dir/zerotrace"
  fi

  if [ -n "$zerotrace_bin" ]; then
    info "Removing the global git hook..."
    "$zerotrace_bin" uninstall --global || warn "uninstall --global reported an issue."
  else
    warn "zerotrace binary not found; skipping hook removal. Check 'git config --global core.hooksPath'."
  fi

  info "Uninstalling the package..."
  "$python" -m pip uninstall --yes --quiet zerotrace >/dev/null 2>&1 || warn "pip uninstall reported an issue."

  local marker="# added by ZeroTrace installer"
  for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [ -f "$rc" ] && grep -qF "$marker" "$rc" 2>/dev/null || continue
    info "Removing the PATH entry from $rc..."
    # Delete the marker line plus the export line that follows it.
    sed -i.zerotrace-bak "/$(printf '%s' "$marker" | sed 's/[][\/.*^$]/\\&/g')/,+1d" "$rc"
    rm -f "$rc.zerotrace-bak"
  done

  [ -d "$HOME/.zerotrace" ] && { info "Removing $HOME/.zerotrace..."; rm -rf "$HOME/.zerotrace"; }
  info "Uninstalled. Repos keep their history and files; only the hooks and the tool are gone."
  exit 0
}

os_name() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      echo "unknown" ;;
  esac
}

py_is_new_enough() {
  "$1" -c "import sys; sys.exit(0 if sys.version_info >= ($PY_MIN_MAJOR, $PY_MIN_MINOR) else 1)" 2>/dev/null
}

find_python() {
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && py_is_new_enough "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

install_python_linux() {
  local sudo_cmd=""
  [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && sudo_cmd="sudo"

  if command -v apt-get >/dev/null 2>&1; then
    info "Installing Python 3 via apt-get..."
    $sudo_cmd apt-get update -y && $sudo_cmd apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    info "Installing Python 3 via dnf..."
    $sudo_cmd dnf install -y python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    info "Installing Python 3 via yum..."
    $sudo_cmd yum install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    info "Installing Python 3 via pacman..."
    $sudo_cmd pacman -Sy --noconfirm python python-pip
  elif command -v zypper >/dev/null 2>&1; then
    info "Installing Python 3 via zypper..."
    $sudo_cmd zypper install -y python3 python3-pip
  elif command -v apk >/dev/null 2>&1; then
    info "Installing Python 3 via apk..."
    $sudo_cmd apk add --no-cache python3 py3-pip
  else
    return 1
  fi
}

install_python_macos() {
  if command -v brew >/dev/null 2>&1; then
    info "Installing Python 3 via Homebrew..."
    brew install python@3.12
  else
    return 1
  fi
}

OS="$(os_name)"
[ "$OS" = "unknown" ] && die "Unsupported OS: $(uname -s). See docs/INSTALL.md."

command -v git >/dev/null 2>&1 || die "git is required (ZeroTrace protects git repos) - install it first."

# Uninstalling must never trigger a Python *install*: do it before the bootstrap below.
[ "$UNINSTALL" = 1 ] && do_uninstall

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
  warn "No Python >= $PY_MIN_MAJOR.$PY_MIN_MINOR found - attempting a best-effort install."
  if [ "$OS" = "linux" ]; then
    install_python_linux || die "Could not find a supported package manager. Install Python $PY_MIN_MAJOR.$PY_MIN_MINOR+ manually, see docs/INSTALL.md."
  else
    install_python_macos || die "Homebrew not found. Install it (https://brew.sh) or Python $PY_MIN_MAJOR.$PY_MIN_MINOR+ manually, see docs/INSTALL.md."
  fi
  PYTHON="$(find_python || true)"
  [ -n "$PYTHON" ] || die "Python install attempted but no suitable interpreter was found afterwards."
fi
info "Using $PYTHON ($("$PYTHON" --version 2>&1))"

# ensurepip ships inside the stdlib of every CPython build, so this works
# even when pip/pipx were never installed on this machine.
"$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON" -m pip install --user --quiet --upgrade pip >/dev/null 2>&1 || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
  SRC_DIR="$SCRIPT_DIR"
else
  SRC_DIR="${TMPDIR:-/tmp}/zerotrace-src"
  rm -rf "$SRC_DIR"
  info "Cloning $REPO_URL (ref: $REF)..."
  git clone --depth 1 --branch "$REF" "$REPO_URL" "$SRC_DIR"
fi

PACKAGE_SPEC="$SRC_DIR"
[ -n "$EXTRAS" ] && PACKAGE_SPEC="$SRC_DIR[$EXTRAS]"

info "Installing zerotrace (pip install --user)..."
"$PYTHON" -m pip install --user --quiet "$PACKAGE_SPEC"

USER_BASE="$("$PYTHON" -m site --user-base)"
BIN_DIR="$USER_BASE/bin"
ZEROTRACE_BIN="$BIN_DIR/zerotrace"
[ -x "$ZEROTRACE_BIN" ] || die "Install finished but $ZEROTRACE_BIN was not found."

if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
  MARKER="# added by ZeroTrace installer"
  for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [ -f "$rc" ] || continue
    grep -qF "$MARKER" "$rc" 2>/dev/null && continue
    { echo ""; echo "$MARKER"; echo "export PATH=\"$BIN_DIR:\$PATH\""; } >> "$rc"
  done
  warn "$BIN_DIR was added to PATH in your shell rc files - restart your shell to pick it up."
fi

info "Enabling the global git hook..."
"$ZEROTRACE_BIN" install --global || warn "install --global reported an issue, see output above."

info "Running doctor..."
"$ZEROTRACE_BIN" doctor || true

info "Done. Open a new shell (or 'source' your rc file) so 'zerotrace' is on PATH."
