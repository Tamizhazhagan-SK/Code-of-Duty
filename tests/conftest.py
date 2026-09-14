"""Shared fixtures. Fake credentials are assembled at run time so this repo never contains a
realistic-looking secret (and neither ZeroTrace nor GitHub push protection trips on it)."""
import os
import secrets
import string
import subprocess

import pytest

from zerotrace import gitutil

ALNUM = string.ascii_letters + string.digits


def rand(n: int, alphabet: str = ALNUM) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


class Fake:
    """Format-valid fake tokens, built from parts at run time."""

    @staticmethod
    def aws_key_id() -> str:
        return "AK" + "IA" + rand(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

    @staticmethod
    def stripe_live() -> str:
        return "sk" + "_live_" + rand(24)

    @staticmethod
    def github() -> str:
        return "gh" + "p_" + rand(36)

    @staticmethod
    def openai() -> str:
        return "sk-" + "proj-" + rand(48)

    @staticmethod
    def anthropic() -> str:
        return "sk-" + "ant-api03-" + rand(90, ALNUM + "-_")

    @staticmethod
    def google() -> str:
        return "AI" + "za" + rand(35)

    @staticmethod
    def slack() -> str:
        return "xo" + "xb-" + rand(12, string.digits) + "-" + rand(24)


@pytest.fixture
def fake() -> type[Fake]:
    return Fake


def _clear_git_caches() -> None:
    gitutil._toplevel.cache_clear()
    gitutil._common_dir.cache_clear()


@pytest.fixture
def git_env(tmp_path, monkeypatch):
    """Isolate git + ZeroTrace config from the developer's machine."""
    home = tmp_path / "home"
    home.mkdir()
    gitconfig = home / "gitconfig"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("ZEROTRACE_HOME", str(home / ".zerotrace"))
    monkeypatch.setenv("ZEROTRACE_POLICY", str(home / "no-org-policy.yml"))
    monkeypatch.setenv("ZEROTRACE_MODEL_ENDPOINT", "http://127.0.0.1:9")  # nothing listens
    for key, value in (("user.email", "t@example.test"), ("user.name", "T"),
                       ("init.defaultBranch", "main")):
        subprocess.run(["git", "config", "--global", key, value], check=True)
    _clear_git_caches()
    yield home
    _clear_git_caches()


@pytest.fixture
def repo(git_env, tmp_path, monkeypatch):
    path = tmp_path / "repo"
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    monkeypatch.chdir(path)
    _clear_git_caches()
    return path


def write(path, text: str) -> None:
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def git(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, input=input_text)
