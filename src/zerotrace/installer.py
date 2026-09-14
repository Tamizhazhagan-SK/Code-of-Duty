"""Install ZeroTrace for every repo on the machine via a global/system core.hooksPath.

`core.hooksPath` replaces ALL hooks, so the managed directory contains a pass-through shim
for every hook name. Shims run the repo's own `.git/hooks/<name>` and any hooks dir that was
configured before us, so git-lfs, husky-style scripts and commit-msg linters keep working.
"""
import contextlib
import json
import os
import shlex
import stat
import subprocess
import sys

from . import gitutil
from .config import zerotrace_home

MARKER = ".zerotrace-managed"
HOOK_NAMES = (
    "applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
    "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout",
    "post-merge", "pre-push", "post-rewrite", "pre-auto-gc", "push-to-checkout",
    "sendemail-validate",
)

_HEADER = """#!/bin/sh
# Installed by ZeroTrace (`zerotrace install`). Do not edit: re-run install to regenerate.
ZT_PY={python}
PREV_HOOKS={prev}
hook_name=$(basename "$0")
git_dir=$(git rev-parse --git-common-dir 2>/dev/null) || exit 0

run_chained() {{
  # 1) the repo's own hook  2) a hooks dir configured before ZeroTrace
  if [ -x "$git_dir/hooks/$hook_name" ]; then "$git_dir/hooks/$hook_name" "$@" || return $?; fi
  if [ -n "$PREV_HOOKS" ] && [ -x "$PREV_HOOKS/$hook_name" ]; then "$PREV_HOOKS/$hook_name" "$@" || return $?; fi
  return 0
}}

zerotrace() {{
  if [ ! -x "$ZT_PY" ]; then
    echo "zerotrace: $ZT_PY not found. Blocking (fail closed). Reinstall ZeroTrace or run 'git config --global --unset core.hooksPath'." >&2
    return 1
  fi
  "$ZT_PY" -m zerotrace "$@"
}}
"""

_PASSTHROUGH = _HEADER + """
run_chained "$@"
"""

_PRE_COMMIT = _HEADER + """
run_chained "$@" || exit $?
# Repos that use the pre-commit framework can't `pre-commit install` while core.hooksPath is
# set, so run their config for them.
if [ ! -x "$git_dir/hooks/pre-commit" ] && [ -f .pre-commit-config.yaml ] \\
   && [ "${{ZEROTRACE_CHAIN_PRECOMMIT:-1}}" = "1" ] && command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --hook-stage pre-commit || exit $?
fi
# Reattach the terminal so the [V/R/U/E/A] menu works inside `git commit`.
# IDEs and GUI clients have no terminal: they get the headless report instead.
if [ -t 1 ] && {{ : </dev/tty; }} 2>/dev/null; then
  zerotrace run --hook </dev/tty
else
  zerotrace run --hook
fi
"""

_PRE_PUSH = _HEADER + """
input=$(cat)
if [ -x "$git_dir/hooks/pre-push" ]; then
  printf '%s\\n' "$input" | "$git_dir/hooks/pre-push" "$@" || exit $?
fi
if [ -n "$PREV_HOOKS" ] && [ -x "$PREV_HOOKS/pre-push" ]; then
  printf '%s\\n' "$input" | "$PREV_HOOKS/pre-push" "$@" || exit $?
fi
printf '%s\\n' "$input" | zerotrace pre-push "$@"
"""

_REPO_BLOCK = """# >>> zerotrace >>>
if [ -t 1 ] && {{ : </dev/tty; }} 2>/dev/null; then
  {python} -m zerotrace run --hook </dev/tty || exit $?
else
  {python} -m zerotrace run --hook || exit $?
fi
# <<< zerotrace <<<
"""


def _sh_path(path: str) -> str:
    return path.replace("\\", "/")


def _sh_quote(value: str) -> str:
    return shlex.quote(_sh_path(value)) if value else "''"


def python_path() -> str:
    return os.path.abspath(sys.executable)


def default_hooks_dir(scope: str) -> str:
    if scope == "system":
        if os.name == "nt":
            return os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "zerotrace", "hooks")
        return "/usr/local/share/zerotrace/hooks"
    return os.path.join(zerotrace_home(), "hooks")


def _state_path() -> str:
    return os.path.join(zerotrace_home(), "install-state.json")


def _load_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(zerotrace_home(), exist_ok=True)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


_USER_MODE = 0o700          # a per-user install: only the owner needs to run the hook
_SYSTEM_MODE = 0o755        # a machine-wide install: every user's git must read+execute it


def _write_script(path: str, content: str, mode: int = _USER_MODE) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.chmod(path, mode)


def is_managed(hooks_dir: str | None) -> bool:
    if not hooks_dir:
        return False
    return os.path.exists(os.path.join(os.path.expanduser(hooks_dir), MARKER))


def write_hooks(hooks_dir: str, prev_hooks: str = "", scope: str = "global") -> None:
    mode = _SYSTEM_MODE if scope == "system" else _USER_MODE
    os.makedirs(hooks_dir, mode=0o755 if scope == "system" else 0o700, exist_ok=True)
    fmt = {"python": _sh_quote(python_path()), "prev": _sh_quote(prev_hooks)}
    for name in HOOK_NAMES:
        template = {"pre-commit": _PRE_COMMIT, "pre-push": _PRE_PUSH}.get(name, _PASSTHROUGH)
        _write_script(os.path.join(hooks_dir, name), template.format(**fmt), mode)
    with open(os.path.join(hooks_dir, MARKER), "w", encoding="utf-8") as f:
        f.write("This directory is generated by `zerotrace install`.\n")


def _git_config(scope: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "config", f"--{scope}", *args], capture_output=True, text=True)


def _checked_hooks_dir(hooks_dir: str) -> str:
    """Resolve the target and refuse to write into a directory holding unrelated files."""
    resolved = os.path.realpath(os.path.expanduser(hooks_dir))
    if os.path.isdir(resolved) and not is_managed(resolved):
        unexpected = sorted(set(os.listdir(resolved)) - set(HOOK_NAMES) - {MARKER})
        if unexpected:
            raise PermissionError(
                f"{resolved} already contains {', '.join(unexpected[:3])}"
                f"{'…' if len(unexpected) > 3 else ''}; refusing to write hook scripts there. "
                "Point --hooks-dir at a dedicated directory.")
    elif os.path.exists(resolved):
        raise PermissionError(f"{resolved} exists and is not a directory")
    return resolved


def install(scope: str = "global", hooks_dir: str | None = None) -> list[str]:
    """scope: global | system. Returns human-readable log lines."""
    hooks_dir = _checked_hooks_dir(hooks_dir or default_hooks_dir(scope))
    log: list[str] = []
    current = gitutil.config_get("core.hooksPath", scope)
    state = _load_state()
    prev = ""
    if current and not is_managed(current):
        prev = os.path.abspath(os.path.expanduser(current))
        state[f"{scope}_previous_hooks_path"] = current
        log.append(f"existing {scope} core.hooksPath {current} will still run (chained)")
    elif current and is_managed(current):
        prev = state.get(f"{scope}_previous_hooks_path", "")
        if prev:
            prev = os.path.abspath(os.path.expanduser(prev))

    write_hooks(hooks_dir, prev, scope)
    log.append(f"wrote {len(HOOK_NAMES)} hook shims to {hooks_dir}")
    result = _git_config(scope, "core.hooksPath", _sh_path(hooks_dir))
    if result.returncode != 0:
        raise PermissionError(result.stderr.strip() or f"could not set {scope} core.hooksPath")
    state[f"{scope}_hooks_dir"] = hooks_dir
    _save_state(state)
    log.append(f"git config --{scope} core.hooksPath {_sh_path(hooks_dir)}")
    return log


def uninstall(scope: str = "global") -> list[str]:
    log: list[str] = []
    state = _load_state()
    current = gitutil.config_get("core.hooksPath", scope)
    prev = state.pop(f"{scope}_previous_hooks_path", "")
    hooks_dir = state.pop(f"{scope}_hooks_dir", current or "")
    if current and is_managed(current):
        if prev:
            _git_config(scope, "core.hooksPath", prev)
            log.append(f"restored {scope} core.hooksPath -> {prev}")
        else:
            _git_config(scope, "--unset", "core.hooksPath")
            log.append(f"unset {scope} core.hooksPath")
    else:
        log.append(f"{scope} core.hooksPath is not managed by ZeroTrace; left unchanged")
    if hooks_dir and is_managed(hooks_dir):
        for name in (*HOOK_NAMES, MARKER):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(hooks_dir, name))
        with contextlib.suppress(OSError):
            os.rmdir(hooks_dir)
        log.append(f"removed {hooks_dir}")
    _save_state(state)
    return log


def install_repo() -> list[str]:
    """Per-repo install, e.g. for repos whose local core.hooksPath (husky) overrides global."""
    root = gitutil.repo_root()
    local = gitutil.config_get("core.hooksPath", "local")
    if not local and is_managed(gitutil.config_get("core.hooksPath")):
        return ["this repo is already covered by the global/system ZeroTrace install"]
    if local and os.path.basename(local.rstrip("/\\")) == "_" and \
            os.path.basename(os.path.dirname(local.rstrip("/\\"))) == ".husky":
        target = os.path.join(root, ".husky", "pre-commit")      # husky v9 user hook file
    else:
        target = os.path.join(effective_hooks_dir(), "pre-commit")
    block = _REPO_BLOCK.format(python=_sh_quote(python_path()))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        with open(target, encoding="utf-8") as f:
            content = f.read()
        if "# >>> zerotrace >>>" in content:
            return [f"{target} already runs ZeroTrace"]
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(("\n" if not content.endswith("\n") else "") + block)
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR)  # keep the repo's own bits
        return [f"appended ZeroTrace to existing hook {target}"]
    _write_script(target, "#!/bin/sh\n" + block)
    return [f"wrote {target}"]


def effective_hooks_dir() -> str:
    path = gitutil.git("rev-parse", "--git-path", "hooks").strip()
    return os.path.abspath(path)
