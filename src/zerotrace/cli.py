"""CLI / hook entrypoint. The global pre-commit hook runs `zerotrace run --hook`."""
import argparse
import contextlib
import json
import os
import re
import sys
import time

from . import __version__, gitutil, pipeline
from .audit import log as audit_log
from .audit.fingerprint import of_finding
from .collectors import staged_diff
from .config import load_config

COMMANDS = ("run", "review", "scan", "pre-push", "init", "install", "uninstall", "doctor", "ui",
            "exceptions",
            "eval", "gateway", "version")
_MAX_PUSH_COMMITS = 300
_SHA_RE = re.compile(r"\A[0-9a-f]{40,64}\Z")


def audit_exceptions_file() -> str:
    from .audit.exceptions import SHARED_FILE
    return SHARED_FILE


def _record_decision(decision, extra: dict | None = None) -> None:
    finding = decision.finding
    event = {
        "fingerprint": of_finding(finding),
        "path": finding.path,
        "line_no": finding.line_no,
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "action": decision.action,
        "reason": decision.reason,
    }
    if extra:
        event.update(extra)
    # An unwritable log must never turn into an allow; the decisions stand regardless.
    with contextlib.suppress(OSError):
        audit_log.append(event)


def _blocking(decisions) -> list:
    return [d for d in decisions if d.action in ("block", "warn")]


def _ok_line(changeset, started: float) -> None:
    ms = (time.monotonic() - started) * 1000
    from rich.console import Console as _Console

    from .ui.glyphs import for_console
    tick = for_console(_Console())["ok"]
    print(f"zerotrace: {tick} {len(changeset.units)} added lines in {len(changeset.paths)} files, "
          f"no blocking findings ({ms:.0f} ms)")


def run(args) -> int:
    from .ui.terminal import is_interactive, present
    cfg = load_config()
    if not cfg.enabled:
        return 0
    started = time.monotonic()
    interactive = is_interactive() or getattr(args, "force_interactive", False)
    for attempt in range(5):  # re-scan after interactive fixes until the index is clean
        changeset = staged_diff.collect_staged()
        decisions = pipeline.scan(changeset, cfg)
        for decision in decisions:
            _record_decision(decision)
        blocking = _blocking(decisions)
        if not blocking:
            if attempt or getattr(args, "hook", False) or getattr(args, "force_interactive", False):
                _ok_line(changeset, started)
            return 0
        if not interactive:
            present(blocking, cfg, interactive=False)
            ms = (time.monotonic() - started) * 1000
            print(f"\nzerotrace: commit blocked ({ms:.0f} ms). Run `zerotrace review` in a "
                  "terminal to fix it interactively.", file=sys.stderr)
            return 1
        if present(blocking, cfg, interactive=True) != 0:
            return 1
    return 1


def review(args) -> int:
    args.force_interactive = True
    return run(args)


def _decisions_to_json(decisions, commit: str = "") -> list[dict]:
    out = []
    for d in decisions:
        f = d.finding
        out.append({
            "commit": commit or None, "path": f.path, "line": f.line_no, "rule": f.rule_id,
            "severity": f.severity, "action": d.action, "reason": d.reason,
            "fingerprint": of_finding(f), "detector": f.source,
        })
    return out


def _commits_in_range(rev_range: str) -> list[str]:
    out = gitutil.git("rev-list", "--reverse", "--no-merges",
                      gitutil.checked_rev(rev_range)).split()
    return out[-_MAX_PUSH_COMMITS:]


def _scan_targets(args, cfg) -> list[tuple[str, list]]:
    """(commit sha, decisions) pairs for whichever target the user asked for."""
    use_model = not args.no_model
    if args.range:
        return [(sha, pipeline.scan(staged_diff.collect_commit(sha), cfg, use_model=use_model))
                for sha in _commits_in_range(args.range)]
    if args.all:
        tree = staged_diff.collect_tree(gitutil.checked_rev(args.rev))
        return [("", pipeline.scan(tree, cfg, use_model=use_model))]
    return [("", pipeline.scan(staged_diff.collect_staged(), cfg, use_model=use_model))]


def _render_scan(results: list[tuple[str, list]], cfg) -> None:
    from .ui.terminal import banner, headless_report
    shown = False
    for sha, decisions in results:
        relevant = [d for d in decisions if d.action != "allow"]
        if not relevant:
            continue
        if not shown:
            banner()
            shown = True
        if sha:
            print(f"\ncommit {sha[:12]}")
        headless_report(relevant, cfg)
    if not shown:
        print("zerotrace: no findings.")


def scan(args) -> int:
    cfg = load_config()
    results = _scan_targets(args, cfg)
    fail_on = ("block", "warn") if args.fail_on == "warn" else ("block",)
    failed = any(d.action in fail_on for _, decisions in results for d in decisions)
    if args.format == "json":
        print(json.dumps([row for sha, decisions in results
                          for row in _decisions_to_json(decisions, sha)], indent=2))
    else:
        _render_scan(results, cfg)
    return 1 if failed else 0


def _commits_for_ref(local_sha: str, remote_sha: str, remote: str) -> list[str]:
    """Commits this ref would publish: everything not already on the remote."""
    if set(remote_sha) != {"0"} and gitutil.ok("cat-file", "-e", remote_sha):
        try:
            return _commits_in_range(f"{remote_sha}..{local_sha}")
        except gitutil.GitError:
            pass
    return gitutil.git("rev-list", "--reverse", "--no-merges",
                       local_sha, "--not", f"--remotes={remote}").split()


def _commits_being_pushed(stdin_text: str, remote: str) -> list[str]:
    commits: list[str] = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if not _SHA_RE.match(local_sha) or not _SHA_RE.match(remote_sha):
            continue  # git only ever writes object ids here
        if set(local_sha) == {"0"}:
            continue  # branch deletion
        commits += _commits_for_ref(local_sha, remote_sha, remote)
    return list(dict.fromkeys(commits))[-_MAX_PUSH_COMMITS:]


def _report_blocked_push(blocked: list[tuple[str, list]], cfg) -> None:
    from .ui.terminal import banner, headless_report
    banner()
    for sha, hits in blocked:
        subject = gitutil.git("log", "-1", "--format=%s", sha).strip()
        print(f"\ncommit {sha[:12]}  {subject}")
        headless_report(hits, cfg)
    print("\nzerotrace: push blocked. These commits put secrets into history (probably via "
          "`--no-verify`).\n  1. Rotate the exposed credentials.\n  2. Rewrite the commits "
          "(`git reset --soft <base>` or `git rebase -i <base>`), then fix and re-commit.",
          file=sys.stderr)


def pre_push(args) -> int:
    """Backstop for `git commit --no-verify`: scan every commit about to leave the machine.
    Deterministic only (no model) and blocks only on BLOCK-level findings."""
    cfg = load_config()
    if not cfg.enabled:
        return 0
    remote = gitutil.checked_rev(args.remote or "origin")
    blocked: list[tuple[str, list]] = []
    for sha in _commits_being_pushed(sys.stdin.read(), remote):
        decisions = pipeline.scan(staged_diff.collect_commit(sha), cfg, use_model=False)
        hits = [d for d in decisions if d.action == "block"]
        for decision in hits:
            _record_decision(decision, {"stage": "pre-push", "commit": sha})
        if hits:
            blocked.append((sha, hits))
    if not blocked:
        return 0
    _report_blocked_push(blocked, cfg)
    return 1


_CONFIG_TEMPLATE = """# ZeroTrace policy for this repo (checked in, reviewed like code).
# Layers: built-in defaults <- org policy <- ~/.zerotrace/config.yml <- this file.
version: 1
enabled: true
model:
  enabled: true
  runtime: ollama              # ollama | openai (vLLM, gateways, AWS-hosted) | off
  name: qwen2.5-coder:3b-instruct-q4_K_M
  endpoint: http://localhost:11434
  # allow_remote: false        # required (with https) for a non-localhost endpoint
  # auth_env: ZEROTRACE_MODEL_TOKEN
  digest: ""                   # pin with: zerotrace doctor --pin-model
  timeout_seconds: 120         # CPU inference is slow; lower it for a GPU/hosted endpoint
  keep_alive: 30m
policy:
  block_severity: [critical, high]
  warn_severity: [medium]
  pii:
    locales: [en, en_IN]
exceptions:
  ttl_days: 30
# rules:
#   extra: [.zerotrace/rules.yml]   # org/team-specific token formats
"""


def init(args) -> int:
    root = gitutil.repo_root()
    path = os.path.join(root, ".zerotrace.yml")
    if os.path.exists(path) and not args.force:
        print(f"zerotrace: {path} exists (use --force to overwrite)")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_CONFIG_TEMPLATE)
        print(f"zerotrace: wrote {path}")
    from detect_secrets.core import baseline
    from detect_secrets.settings import default_settings
    with default_settings():
        secrets = baseline.create(".", should_scan_all_files=False, root=root)
        baseline.save_to_file(secrets, os.path.join(root, ".secrets.baseline"))
    count = sum(len(v) for v in secrets.data.values())
    print(f"zerotrace: wrote .secrets.baseline ({count} existing findings, stored as hashes, "
          "so pre-existing findings won't block new work)")
    print("zerotrace: next: `zerotrace install --global` protects every repo on this machine.")
    return 0


def install_cmd(args) -> int:
    from . import installer
    from .ui.progress import Bar
    from .ui.terminal import banner
    banner()
    bar = Bar(len(installer.INSTALL_STEPS))
    try:
        lines = installer.install("system" if args.system else "global", args.hooks_dir,
                                  on_step=bar.step)
    except (PermissionError, gitutil.GitError) as exc:
        bar.finish()
        print(f"zerotrace: install failed: {exc}", file=sys.stderr)
        return 1
    bar.finish()
    for line in lines:
        print(f"zerotrace: {line}")
    print("zerotrace: every repo on this machine now runs ZeroTrace on commit and push.")
    return 0


def uninstall_cmd(args) -> int:
    from . import installer
    for line in installer.uninstall("system" if args.system else "global"):
        print(f"zerotrace: {line}")
    return 0


def doctor_cmd(args) -> int:
    if args.fix:
        from . import installer
        for line in installer.install_repo():
            print(f"zerotrace: {line}")
        return 0
    from .doctor import doctor
    return doctor(pin_model=args.pin_model, warm=args.warm)


def exceptions_cmd(args) -> int:
    from rich.console import Console
    from rich.table import Table

    from .audit import exceptions as audit_exceptions
    from .ui.glyphs import box_for
    console = Console()

    if args.promote:
        moved, path = audit_exceptions.promote()
        print(f"zerotrace: moved {moved} exception(s) into {os.path.basename(path)} - "
              "commit it so a reviewer sees the reason and the expiry.")
        return 0
    if args.prune:
        print(f"zerotrace: removed {audit_exceptions.prune()} expired exception(s).")
        return 0

    rows = audit_exceptions.listing()
    if not rows:
        print("zerotrace: no exceptions recorded.")
        return 0
    table = Table(title="Exceptions", box=box_for(console))
    for column in ("scope", "fingerprint", "expires", "state", "reason"):
        table.add_column(column, overflow="fold")
    for row in rows:
        state = "[green]active[/]" if row["active"] else "[dim]expired[/]"
        table.add_row(row["scope"], row["fingerprint"][:12], row["expires_at"][:10], state,
                      row["reason"])
    console.print(table)
    console.print("[dim]`--promote` moves local exceptions into the committed, reviewable "
                  "file; `--prune` drops expired ones.[/]")
    return 0


def ui_cmd(args) -> int:
    from .ui.preview import run
    return run(args.tier)


def eval_cmd(args) -> int:
    from .evals import run_eval
    return run_eval(args.cases, args.model or [], args.runs)


def gateway_cmd(args) -> int:
    """Sanitize an AI-agent/MCP-tool/RAG payload read from stdin."""
    from .gateway import sanitize
    result = sanitize(sys.stdin.read())
    if args.format == "json":
        print(json.dumps({"verdict": result.verdict, "sanitized_text": result.sanitized_text},
                         indent=2))
    else:
        print(result.sanitized_text)
        if result.verdict != "allow":
            print(f"\nzerotrace: gateway verdict: {result.verdict}", file=sys.stderr)
    return 0 if result.verdict == "allow" else 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zerotrace", description=__doc__)
    sub = p.add_subparsers(dest="command")

    r = sub.add_parser("run", help="scan the staged diff (what the pre-commit hook runs)")
    r.add_argument("--hook", action="store_true", help=argparse.SUPPRESS)
    r.add_argument("files", nargs="*", help=argparse.SUPPRESS)  # pre-commit passes filenames
    sub.add_parser("review", help="interactively fix blocking findings in the staged diff")

    s = sub.add_parser("scan", help="scan staged changes, a commit range, or the whole tree")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="staged diff (default)")
    g.add_argument("--range", metavar="A..B", help="every commit in a range (CI / PRs)")
    g.add_argument("--all", action="store_true", help="every tracked line (onboarding)")
    s.add_argument("--rev", default="HEAD", help="tree to scan with --all")
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--no-model", action="store_true", help="deterministic only")
    s.add_argument("--fail-on", choices=["block", "warn"], default="block")

    pp = sub.add_parser("pre-push", help=argparse.SUPPRESS)
    pp.add_argument("remote", nargs="?")
    pp.add_argument("url", nargs="?")

    i = sub.add_parser("init", help="write .zerotrace.yml and a hashed .secrets.baseline")
    i.add_argument("--force", action="store_true")

    ins = sub.add_parser("install", help="protect every repo on this machine (global hooksPath)")
    scope = ins.add_mutually_exclusive_group()
    scope.add_argument("--global", dest="global_", action="store_true", help="current user (default)")
    scope.add_argument("--system", action="store_true", help="all users; for MDM/IT rollout")
    ins.add_argument("--hooks-dir", help="custom location for the managed hooks")

    un = sub.add_parser("uninstall", help="remove the global/system hooks, restoring the previous hooksPath")
    un_scope = un.add_mutually_exclusive_group()
    un_scope.add_argument("--global", dest="global_", action="store_true")
    un_scope.add_argument("--system", action="store_true")

    d = sub.add_parser("doctor", help="check install, config layers and the model endpoint")
    d.add_argument("--pin-model", action="store_true", help="pin the served model digest in .zerotrace.yml")
    d.add_argument("--warm", action="store_true", help="load the model into memory now")
    d.add_argument("--fix", action="store_true",
                   help="patch this repo's local hook override (e.g. husky) that defeats the global install")

    x = sub.add_parser("exceptions", help="list, promote or prune approved exceptions")
    x_group = x.add_mutually_exclusive_group()
    x_group.add_argument("--promote", action="store_true",
                         help=f"move local exceptions into {audit_exceptions_file()} for review")
    x_group.add_argument("--prune", action="store_true", help="drop expired exceptions")

    u = sub.add_parser("ui", help="render every screen so you can check this terminal")
    u.add_argument("--tier", choices=["auto", "unicode", "ascii", "text", "all"], default="auto",
                   help="force a logo/render tier (default: auto-detect)")

    e = sub.add_parser("eval", help="measure the AI tie-break on labelled synthetic cases")
    e.add_argument("--cases", help="JSONL cases file (default: bundled set)")
    e.add_argument("--model", action="append", help="model name(s) to compare")
    e.add_argument("--runs", type=int, default=1)

    gw = sub.add_parser("gateway", help="sanitize an AI-agent/MCP-tool/RAG payload from stdin")
    gw.add_argument("--format", choices=["text", "json"], default="text")

    sub.add_parser("version", help="print version")
    return p


def main(argv: list[str] | None = None) -> None:
    # Legacy Windows consoles default to a non-UTF-8 codepage; the ✓/✗ glyphs we print would
    # otherwise crash with UnicodeEncodeError instead of just displaying as '?'.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError):
                reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        argv = ["run", *argv]
    args = _parser().parse_args(argv)

    if args.command == "version":
        print(f"zerotrace {__version__}")
        raise SystemExit(0)
    repo_commands = {"run", "review", "scan", "pre-push", "init", "exceptions"}
    if args.command in repo_commands:
        if not gitutil.in_repo():
            print("zerotrace: not inside a git repository", file=sys.stderr)
            raise SystemExit(0 if args.command in ("run", "pre-push") else 2)
        os.chdir(gitutil.repo_root())

    handlers = {
        "run": run, "review": review, "scan": scan, "pre-push": pre_push, "init": init,
        "install": install_cmd, "uninstall": uninstall_cmd, "doctor": doctor_cmd, "ui": ui_cmd,
        "exceptions": exceptions_cmd,
        "eval": eval_cmd, "gateway": gateway_cmd,
    }
    try:
        code = handlers[args.command](args)
    except KeyboardInterrupt:
        print("\nzerotrace: interrupted. Nothing was committed.", file=sys.stderr)
        code = 1
    except Exception as exc:  # fail closed: an internal error blocks, never allows
        if os.environ.get("ZEROTRACE_DEBUG"):
            raise
        print(f"zerotrace: internal error, blocking to stay safe: {exc!r}", file=sys.stderr)
        code = 1
    raise SystemExit(code)
