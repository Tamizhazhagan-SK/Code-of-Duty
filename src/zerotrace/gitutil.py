"""Thin, dependency-free git helpers. Every path ZeroTrace touches is repo-root relative."""
import functools
import os
import re
import subprocess

# Revisions reach a git command line, and they come from argv (`scan --range`) or from the
# pre-push hook's stdin. Allow only the characters git revision syntax actually needs, and
# never a leading "-" (which git would read as an option).
_REV_RE = re.compile(r"\A(?!-)[A-Za-z0-9._/^~@{}\-]{1,255}\Z")


class GitError(RuntimeError):
    pass


def checked_rev(rev: str) -> str:
    """Return `rev` if it is a plausible revision/range, else raise."""
    if not _REV_RE.match(rev or ""):
        raise GitError(f"refusing to run git with an unexpected revision: {rev!r}")
    return rev


def checked_path(path: str) -> str:
    """Repo-relative path from a diff. No option-like or parent-escaping paths."""
    if not path or path.startswith("-") or os.path.isabs(path) \
            or ".." in path.replace("\\", "/").split("/"):
        raise GitError(f"refusing to run git with an unexpected path: {path!r}")
    return path


def git(*args: str, input_bytes: bytes | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], input=input_bytes, capture_output=True,
    )
    if check and result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8", "replace")


def git_bytes(*args: str, check: bool = True) -> bytes | None:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode != 0:
        if check:
            raise GitError(result.stderr.decode("utf-8", "replace").strip())
        return None
    return result.stdout


@functools.cache
def _toplevel(cwd: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=cwd,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def repo_root() -> str:
    """Top of the current work tree; falls back to CWD outside a repo (e.g. unit tests)."""
    cwd = os.getcwd()
    return _toplevel(cwd) or cwd


def in_repo() -> bool:
    return _toplevel(os.getcwd()) is not None


def blob_text(rev: str, path: str) -> str | None:
    """File content at `rev` ("" = the index). Raw bytes, no textconv/filters."""
    checked_path(path)
    if rev:
        checked_rev(rev)
    data = git_bytes("cat-file", "blob", f"{rev}:{path}", check=False)
    if data is None:
        return None
    return data.decode("utf-8", "replace")


def config_get(key: str, scope: str | None = None) -> str | None:
    args = ["config"]
    if scope:
        args.append(f"--{scope}")
    result = subprocess.run(
        ["git", *args, "--get", key], capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


@functools.cache
def _common_dir(cwd: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, cwd=cwd,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def state_dir() -> str:
    """Where audit log, exceptions and cache live: inside .git, so global installs never
    leave untracked files in a developer's work tree. Outside a repo: ./.zerotrace."""
    cwd = os.getcwd()
    common = _common_dir(cwd)
    return os.path.join(common, "zerotrace") if common else os.path.join(cwd, ".zerotrace")


def ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0
