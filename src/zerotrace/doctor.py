"""`zerotrace doctor`: is this machine/repo actually protected, and is the model trustworthy?

Each check is a small function that appends rows to a Report, so adding a check never grows one
big function.
"""
import os
import re
import sys
import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from . import __version__, gitutil, installer, platform_env
from .ui import glyphs
from .config import Config, load_config

# Status keys, not glyphs: Report.table() renders whatever the destination console can
# encode (a legacy cp437 console gets "+"/"x" instead of "✓"/"✗", not "?").
OK, WARN, FAIL = "ok", "warn", "fail"
_STATUS_STYLE = {"ok": "green", "warn": "yellow", "fail": "red"}
_MODEL_INTEGRITY = "model integrity"
_MODEL_AVAILABLE = "model available"


@dataclass
class Report:
    rows: list[tuple[str, str, str]] = field(default_factory=list)
    failures: int = 0

    def add(self, status: str, check: str, result: str) -> None:
        self.rows.append((status, check, result))
        self.failures += status == FAIL

    def table(self, console: Console | None = None) -> Table:
        marks = glyphs.for_console(console or Console())
        title = glyphs.sanitize(f"ZeroTrace doctor · v{__version__}", console or Console())
        table = Table(title=title, show_header=False, expand=False,
                      box=glyphs.box_for(console or Console()))
        table.add_column("", width=2)
        table.add_column("Check", style="bold")
        table.add_column("Result", overflow="fold")
        for status, check, result in self.rows:
            mark = f"[{_STATUS_STYLE.get(status, 'white')}]{marks.get(status, status)}[/]"
            table.add_row(mark, check, glyphs.sanitize(result, console or Console()))
        return table


def _pin_digest(root: str, digest: str) -> str:
    path = os.path.join(root, ".zerotrace.yml")
    if not os.path.exists(path):
        return "no .zerotrace.yml here (run `zerotrace init` first)"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if re.search(r"(?m)^(\s+)(digest|sha256):.*$", text):
        text = re.sub(r"(?m)^(\s+)(digest|sha256):.*$", rf'\1digest: "{digest}"', text, count=1)
    elif re.search(r"(?m)^model:\s*$", text):
        text = re.sub(r"(?m)^model:\s*$", f'model:\n  digest: "{digest}"', text, count=1)
    else:
        text += f'\nmodel:\n  digest: "{digest}"\n'
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return f"pinned {digest[:19]}… in .zerotrace.yml"


def _check_toolchain(report: Report) -> None:
    report.add(OK, "python", sys.executable)
    version = gitutil.git("--version", check=False).strip()
    report.add(OK if version else FAIL, "git", version or "git not found")


def _check_environment(report: Report) -> None:
    env = platform_env.detect()
    if env.kind == "wsl":
        label = f"WSL{env.wsl_version or '?'}" + (f" ({env.distro_name})" if env.distro_name else "")
        report.add(OK, "environment", label)
        if not env.interop_available:
            report.add(WARN, "WSL interop",
                       "disabled for this distro; the Windows side must be installed "
                       "separately (run `zerotrace install --global` there too)")
        if gitutil.in_repo():
            fs_class = platform_env.classify_path(gitutil.repo_root())
            if fs_class == "drvfs":
                report.add(WARN, "repo filesystem",
                           "this repo is on a Windows drive (/mnt/<drive>); performance and "
                           "hook install may be degraded. Consider cloning under $HOME instead")
    else:
        report.add(OK, "environment", env.kind)


def _check_install(report: Report) -> None:
    for scope in ("system", "global"):
        value = gitutil.config_get(installer.HOOKS_PATH_KEY, scope)
        if not value:
            report.add(WARN if scope == "global" else OK, f"{scope} hooksPath", "not set")
            continue
        managed = installer.is_managed(value)
        report.add(OK if managed else WARN, f"{scope} hooksPath",
                   f"{value} ({'ZeroTrace-managed' if managed else 'not ZeroTrace'})")

    for scope in ("system", "global"):
        value = gitutil.config_get(installer.TEMPLATE_DIR_KEY, scope)
        if not value:
            continue  # optional fallback; absent is fine as long as hooksPath is set
        managed = installer.is_managed(os.path.join(value, "hooks"))
        report.add(OK if managed else WARN, f"{scope} templateDir (fallback)",
                   f"{value} ({'ZeroTrace-managed' if managed else 'not ZeroTrace'})")


def _repo_runs_zerotrace(hooks_dir: str) -> bool:
    if installer.is_managed(hooks_dir):
        return True
    pre_commit = os.path.join(hooks_dir, "pre-commit")
    if not os.path.exists(pre_commit):
        return False
    with open(pre_commit, encoding="utf-8", errors="replace") as f:
        return "zerotrace" in f.read()


def _check_repo(report: Report) -> None:
    if not gitutil.in_repo():
        report.add(OK, "repo", "not inside a git repo (repo checks skipped)")
        return
    dubious = gitutil.git_stderr("status")
    if "dubious ownership" in dubious.lower():
        report.add(FAIL, "repo ownership",
                   "git refuses this repo (root-owned repo, network share, or `sudo`): run "
                   "`git config --global --add safe.directory <path>` or the hook will never run")
        return
    os.chdir(gitutil.repo_root())
    hooks_dir = installer.effective_hooks_dir()
    runs = _repo_runs_zerotrace(hooks_dir)
    local = gitutil.config_get(installer.HOOKS_PATH_KEY, "local")
    if local and not installer.is_managed(local):
        report.add(OK if runs else FAIL, "repo override",
                   f"local {installer.HOOKS_PATH_KEY}={local} overrides global"
                   + ("" if runs else ". Not protected: run `zerotrace doctor --fix`"))
    report.add(OK if runs else FAIL, "this repo protected",
               f"yes (hooks: {hooks_dir})" if runs else
               "no. Run `zerotrace install --global`")


def _check_policy(report: Report, cfg: Config) -> None:
    report.add(OK, "config layers", ", ".join(cfg.sources) or "built-in defaults")
    if cfg.locked:
        report.add(OK, "org-locked keys", ", ".join(cfg.locked))
    from .detectors import rulepack
    rules = rulepack.load_rules(cfg.rules_extra, cfg.repo_root)
    report.add(OK, "rule pack", f"{len(rules)} provider rules + code-assignment, sensitive-file, "
                                "detect-secrets and PII detectors")


def _check_endpoint(report: Report, cfg: Config) -> None:
    from .classifier import llm
    where = "REMOTE" if cfg.model_is_remote else "local"
    try:
        llm.check_endpoint(cfg)
        report.add(OK, "model endpoint", f"{cfg.model_runtime} @ {cfg.model_endpoint} ({where})")
    except llm.EndpointRefused as exc:
        report.add(FAIL, "model endpoint", str(exc))


def _check_integrity(report: Report, cfg: Config, digest: str, pin_model: bool) -> None:
    if cfg.model_digest:
        match = digest.startswith(cfg.model_digest.removeprefix("sha256:"))
        report.add(OK if match else FAIL, _MODEL_INTEGRITY,
                   "served model matches the pinned digest" if match else
                   f"MISMATCH: pinned {cfg.model_digest[:19]}…, served {digest[:19]}…")
    elif pin_model and gitutil.in_repo():
        report.add(OK, _MODEL_INTEGRITY, _pin_digest(cfg.repo_root, digest))
    else:
        report.add(WARN, _MODEL_INTEGRITY, "digest not pinned (`zerotrace doctor --pin-model`)")


def _check_warm(report: Report, cfg: Config) -> None:
    from .classifier import llm
    took = llm.warm(cfg)
    report.add(OK if took is not None else WARN, "model warm-up",
               f"loaded and pinned in memory for {cfg.model_keep_alive} ({took:.1f} s)"
               if took is not None else "warm-up failed; the first MEDIUM finding will be slow")


def _check_model(report: Report, cfg: Config, pin_model: bool, warm: bool) -> None:
    if not cfg.model_enabled:
        report.add(OK, "AI tie-break", "disabled; MEDIUM findings will WARN (fail closed)")
        return
    from .classifier import llm
    _check_endpoint(report, cfg)

    start = time.monotonic()
    digest = llm.model_digest(cfg)
    latency = (time.monotonic() - start) * 1000
    if digest is None:
        report.add(WARN, _MODEL_AVAILABLE,
                   f"{cfg.model_name} not reachable/served ({latency:.0f} ms). MEDIUM findings "
                   "will WARN. Start it: `docker compose -f docker/docker-compose.yml up -d`")
    else:
        report.add(OK, _MODEL_AVAILABLE, f"{cfg.model_name} · {digest[:19]}… ({latency:.0f} ms)")
        if warm:
            _check_warm(report, cfg)
        _check_integrity(report, cfg, digest, pin_model)

    report.add(OK, "egress",
               "only redacted shape features are sent (no raw values), over TLS"
               if cfg.model_is_remote else
               "localhost only; proxy env vars bypassed for model calls")


def doctor(pin_model: bool = False, warm: bool = False) -> int:
    report = Report()
    _check_toolchain(report)
    _check_environment(report)
    _check_install(report)
    _check_repo(report)
    cfg = load_config()
    _check_policy(report, cfg)
    _check_model(report, cfg, pin_model, warm)
    console = Console()
    console.print(report.table(console))
    return 1 if report.failures else 0
