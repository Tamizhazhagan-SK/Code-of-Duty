"""`zerotrace doctor`: is this machine/repo actually protected, and is the model trustworthy?"""
import os
import re
import sys
import time

from rich.console import Console
from rich.table import Table

from . import __version__, gitutil, installer
from .config import load_config

OK, WARN, FAIL = "[green]✓[/]", "[yellow]![/]", "[red]✗[/]"


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


def doctor(pin_model: bool = False, warm: bool = False) -> int:
    console = Console()
    table = Table(title=f"ZeroTrace doctor · v{__version__}", show_header=False, expand=False)
    table.add_column("", width=2)
    table.add_column("Check", style="bold")
    table.add_column("Result", overflow="fold")
    failures = 0

    def row(status: str, check: str, result: str) -> None:
        nonlocal failures
        failures += status == FAIL
        table.add_row(status, check, result)

    row(OK, "python", sys.executable)
    git_version = gitutil.git("--version", check=False).strip()
    row(OK if git_version else FAIL, "git", git_version or "git not found")

    for scope in ("system", "global"):
        value = gitutil.config_get("core.hooksPath", scope)
        if value:
            managed = installer.is_managed(value)
            row(OK if managed else WARN, f"{scope} hooksPath",
                f"{value} ({'ZeroTrace-managed' if managed else 'not ZeroTrace'})")
        else:
            row(WARN if scope == "global" else OK, f"{scope} hooksPath", "not set")

    in_repo = gitutil.in_repo()
    if in_repo:
        os.chdir(gitutil.repo_root())
        local = gitutil.config_get("core.hooksPath", "local")
        effective = installer.effective_hooks_dir()
        pre_commit = os.path.join(effective, "pre-commit")
        runs_zt = installer.is_managed(effective)
        if not runs_zt and os.path.exists(pre_commit):
            with open(pre_commit, encoding="utf-8", errors="replace") as f:
                runs_zt = "zerotrace" in f.read()
        if local and not installer.is_managed(local):
            row(OK if runs_zt else FAIL, "repo override",
                f"local core.hooksPath={local} overrides global"
                + ("" if runs_zt else ". Not protected: run `zerotrace install --repo`"))
        row(OK if runs_zt else FAIL, "this repo protected",
            f"yes (hooks: {effective})" if runs_zt else
            "no. Run `zerotrace install --global` (or `--repo`)")
    else:
        row(OK, "repo", "not inside a git repo (repo checks skipped)")

    cfg = load_config()
    row(OK, "config layers", ", ".join(cfg.sources) or "built-in defaults")
    if cfg.locked:
        row(OK, "org-locked keys", ", ".join(cfg.locked))
    from .detectors import rulepack
    rules = rulepack.load_rules(cfg.rules_extra, cfg.repo_root)
    row(OK, "rule pack", f"{len(rules)} provider rules + code-assignment, sensitive-file, "
                         "detect-secrets and PII detectors")

    if not cfg.model_enabled:
        row(OK, "AI tie-break", "disabled; MEDIUM findings will WARN (fail closed)")
    else:
        from .classifier import llm
        where = "REMOTE" if cfg.model_is_remote else "local"
        try:
            llm.check_endpoint(cfg)
            row(OK, "model endpoint", f"{cfg.model_runtime} @ {cfg.model_endpoint} ({where})")
        except llm.EndpointRefused as exc:
            row(FAIL, "model endpoint", str(exc))
        start = time.monotonic()
        digest = llm.model_digest(cfg)
        latency = (time.monotonic() - start) * 1000
        if digest is None:
            row(WARN, "model available",
                f"{cfg.model_name} not reachable/served ({latency:.0f} ms). MEDIUM findings will WARN. "
                "Start it: `docker compose -f docker/docker-compose.yml up -d`")
        else:
            row(OK, "model available", f"{cfg.model_name} · {digest[:19]}… ({latency:.0f} ms)")
            if warm:
                took = llm.warm(cfg)
                row(OK if took is not None else WARN, "model warm-up",
                    f"loaded and pinned in memory for {cfg.model_keep_alive} ({took:.1f} s)"
                    if took is not None else "warm-up failed; the first MEDIUM finding will be slow")
            if cfg.model_digest:
                match = digest.startswith(cfg.model_digest.removeprefix("sha256:"))
                row(OK if match else FAIL, "model integrity",
                    "served model matches the pinned digest" if match else
                    f"MISMATCH: pinned {cfg.model_digest[:19]}…, served {digest[:19]}…")
            elif pin_model and in_repo:
                row(OK, "model integrity", _pin_digest(cfg.repo_root, digest))
            else:
                row(WARN, "model integrity", "digest not pinned (`zerotrace doctor --pin-model`)")
        if cfg.model_is_remote:
            row(OK, "egress", "only redacted shape features are sent (no raw values), over TLS")
        else:
            row(OK, "egress", "localhost only; proxy env vars bypassed for model calls")

    console.print(table)
    return 1 if failures else 0
