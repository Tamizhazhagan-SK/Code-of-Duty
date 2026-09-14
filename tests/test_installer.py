"""Global install: every repo protected, existing hooks keep working, uninstall restores."""
import os
import subprocess

import pytest

from zerotrace import installer

from .conftest import git, write

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX hook scripts")


def _new_repo(tmp_path, name):
    path = tmp_path / name
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def _commit(path, *args):
    return subprocess.run(["git", "-C", str(path), "commit", "-qm", "c", *args],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


def test_global_install_protects_every_repo(git_env, tmp_path, fake):
    installer.install("global")
    assert installer.is_managed(git("config", "--global", "core.hooksPath").stdout.strip())
    for name in ("api", "web"):
        repo = _new_repo(tmp_path, name)
        write(repo / "app.py", f'KEY = "{fake.stripe_live()}"\n')
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        result = _commit(repo)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "stripe-live-key" in result.stdout + result.stderr


def test_clean_commit_passes(git_env, tmp_path):
    installer.install("global")
    repo = _new_repo(tmp_path, "clean")
    write(repo / "ok.py", "def f():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode == 0


def test_repo_local_hooks_still_run(git_env, tmp_path):
    installer.install("global")
    repo = _new_repo(tmp_path, "lfs")
    marker = tmp_path / "local-hook-ran"
    for name in ("pre-commit", "post-commit"):
        hook = repo / ".git" / "hooks" / name
        write(hook, f"#!/bin/sh\necho {name} >> '{marker}'\n")
        os.chmod(hook, 0o755)
    write(repo / "ok.py", "x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode == 0
    assert marker.read_text().split() == ["pre-commit", "post-commit"]


def test_failing_local_hook_still_blocks(git_env, tmp_path):
    installer.install("global")
    repo = _new_repo(tmp_path, "lint")
    hook = repo / ".git" / "hooks" / "pre-commit"
    write(hook, "#!/bin/sh\necho lint failed; exit 3\n")
    os.chmod(hook, 0o755)
    write(repo / "ok.py", "x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode != 0


def test_previous_global_hooks_are_chained_and_restored(git_env, tmp_path):
    prev = tmp_path / "company-hooks"
    marker = tmp_path / "company-hook-ran"
    write(prev / "commit-msg", f"#!/bin/sh\necho yes > '{marker}'\n")
    os.chmod(prev / "commit-msg", 0o755)
    git("config", "--global", "core.hooksPath", str(prev))

    installer.install("global")
    repo = _new_repo(tmp_path, "chained")
    write(repo / "ok.py", "x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode == 0
    assert marker.exists()

    installer.uninstall("global")
    assert git("config", "--global", "core.hooksPath").stdout.strip() == str(prev)


def test_uninstall_unsets_when_nothing_before(git_env):
    installer.install("global")
    installer.uninstall("global")
    assert git("config", "--global", "core.hooksPath").returncode != 0


def test_husky_style_local_hookspath_gets_repo_install(git_env, tmp_path, monkeypatch, fake):
    installer.install("global")
    repo = _new_repo(tmp_path, "husky")
    husky = repo / ".husky"
    write(husky / "pre-commit", "#!/bin/sh\necho husky lint ok\n")
    os.chmod(husky / "pre-commit", 0o755)
    write(husky / "_" / "pre-commit", '#!/bin/sh\nsh "$(dirname "$0")/../pre-commit"\n')
    os.chmod(husky / "_" / "pre-commit", 0o755)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".husky/_"], check=True)
    monkeypatch.chdir(repo)
    from zerotrace import gitutil
    gitutil._toplevel.cache_clear()

    write(repo / "app.py", f'KEY = "{fake.stripe_live()}"\n')
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode == 0  # husky overrides the global hook: unprotected

    subprocess.run(["git", "-C", str(repo), "update-ref", "-d", "HEAD"], check=True)
    (line,) = installer.install_repo()
    assert ".husky" in line
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert _commit(repo).returncode != 0
