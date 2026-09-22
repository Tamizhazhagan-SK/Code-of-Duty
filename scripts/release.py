"""Release helper for .github/workflows/release.yml, and for running by hand.

    python scripts/release.py bump minor           # 0.2.0 -> 0.3.0 everywhere, CHANGELOG cut
    python scripts/release.py bump 1.0.0           # an exact version
    python scripts/release.py plan                 # in CI: is there a version to release?
    python scripts/release.py notes v0.3.0         # that version's CHANGELOG section
    python scripts/release.py tag-message v0.3.0 <sha>

`bump` writes the new version into pyproject.toml, src/zerotrace/__init__.py,
skill/skill.json and marketplace/submission.json, and turns `## [Unreleased]` into
`## [X.Y.Z] - <date>`, with a fresh empty [Unreleased] above it and a compare link below.
It refuses a version that is not higher than the current one, and an empty [Unreleased]:
a release without notes is a mistake, not a formality. tests/test_version.py checks that
every declaration agrees afterwards.

Standard library only, so CI can run it before installing anything.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
# (file, pattern matching the version declaration, replacement with {} for the version)
_DECLARATIONS = (
    ("pyproject.toml", r'^version = "[^"]*"', 'version = "{}"'),
    ("src/zerotrace/__init__.py", r'^__version__ = "[^"]*"', '__version__ = "{}"'),
    ("skill/skill.json", r'"version": "[^"]*"', '"version": "{}"'),
    ("marketplace/submission.json", r'"version": "[^"]*"', '"version": "{}"'),
)
_UNRELEASED = "## [Unreleased]\n"


class ReleaseError(Exception):
    """A release step refused to go on; the message says why."""


def _project(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def current_version(root: Path = ROOT) -> str:
    return _project(root)["version"]


def _repo_url(root: Path) -> str:
    return _project(root)["urls"]["Repository"].rstrip("/")


def _parts(version: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(version)
    if match is None:
        raise ReleaseError(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def next_version(current: str, how: str) -> str:
    """patch / minor / major, or an exact version that must be higher than the current one."""
    major, minor, patch = _parts(current)
    if how == "major":
        return f"{major + 1}.0.0"
    if how == "minor":
        return f"{major}.{minor + 1}.0"
    if how == "patch":
        return f"{major}.{minor}.{patch + 1}"
    wanted = how.removeprefix("v")
    if _parts(wanted) <= (major, minor, patch):
        raise ReleaseError(f"{wanted} is not higher than the current version {current}")
    return wanted


def _unreleased_span(text: str) -> tuple[int, int]:
    """Where the [Unreleased] notes start and end (the next section or the link list)."""
    start = text.find(_UNRELEASED)
    if start < 0:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' section")
    body = start + len(_UNRELEASED)
    ends = [match.start() + body for match in
            (re.search(r"^## \[", text[body:], re.MULTILINE),
             re.search(r"^\[[^\]]+\]: ", text[body:], re.MULTILINE)) if match]
    return body, min(ends, default=len(text))


def _cut_changelog(text: str, old: str, new: str, today: str, repo: str) -> str:
    body, end = _unreleased_span(text)
    notes = text[body:end]
    if not notes.strip():
        raise ReleaseError("[Unreleased] in CHANGELOG.md is empty: write the release notes first")
    text = f"{text[:body]}\n## [{new}] - {today}\n{notes.lstrip(chr(10))}{text[end:]}"
    links = (f"[Unreleased]: {repo}/compare/v{new}...HEAD\n"
             f"[{new}]: {repo}/compare/v{old}...v{new}")
    text, replaced = re.subn(r"^\[Unreleased\]: .*$", links, text, count=1, flags=re.MULTILINE)
    if not replaced:
        text = f"{text.rstrip(chr(10))}\n\n{links}\n"
    return text


def bump(how: str, root: Path = ROOT, today: str | None = None) -> str:
    """Raise the version everywhere and cut the changelog section. Returns the new version.

    Every file is rewritten in memory first, so a refusal leaves nothing half-changed.
    """
    old = current_version(root)
    new = next_version(old, how)
    today = today or datetime.date.today().isoformat()
    changelog = root / "CHANGELOG.md"
    updated = {changelog: _cut_changelog(changelog.read_text(encoding="utf-8"), old, new,
                                         today, _repo_url(root))}
    for name, pattern, template in _DECLARATIONS:
        path = root / name
        text, count = re.subn(pattern, template.format(new), path.read_text(encoding="utf-8"),
                              count=1, flags=re.MULTILINE)
        if count != 1:
            raise ReleaseError(f"no version declaration found in {name}")
        updated[path] = text
    for path, text in updated.items():
        path.write_text(text, encoding="utf-8")
    return new


def notes(tag: str, root: Path = ROOT) -> str:
    """The CHANGELOG section for `tag`, which becomes the GitHub release notes."""
    version = re.escape(tag.removeprefix("v"))
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{version}\].*?(?=^## \[|^\[[^\]]+\]: |\Z)", text,
                      re.MULTILINE | re.DOTALL)
    if match is None:
        raise ReleaseError(f"CHANGELOG.md has no '## [{tag.removeprefix('v')}]' section")
    return match.group(0).strip() + "\n"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def plan(env: dict | os._Environ = os.environ, root: Path = ROOT) -> dict[str, str]:
    """Decide whether this CI run releases, from the version in pyproject.toml.

    A pushed tag must name exactly that version. Otherwise (a push to main, or the "Run
    workflow" button after `bump`) the version is released only if it has no tag yet, so an
    ordinary push is a no-op and a re-run never publishes twice.
    """
    version = current_version(root)
    tag = f"v{version}"
    if env.get("GITHUB_REF_TYPE") == "tag":
        if env.get("GITHUB_REF_NAME") != tag:
            raise ReleaseError(f"tag {env.get('GITHUB_REF_NAME')} does not match "
                               f"pyproject.toml version {version}")
        release = True
    else:
        release = _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode != 0
    if release:
        notes(tag, root)            # fail now, not after building three binaries
    return {"release": "true" if release else "false", "version": version, "tag": tag}


def tag_message(tag: str, sha: str, root: Path = ROOT) -> str:
    """`vX.Y.Z - <summary>`, the summary taken from a "chore: prepare vX.Y.Z - …" commit."""
    subject = _git(root, "log", "-1", "--format=%s", sha).stdout.strip()
    match = re.fullmatch(rf"chore: prepare {re.escape(tag)} - (.+)", subject)
    return f"{tag} - {match.group(1)}" if match else tag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bump", help="raise the version everywhere and cut the changelog")
    b.add_argument("how", help="patch, minor, major, or an exact X.Y.Z")
    sub.add_parser("plan", help="print release=/version=/tag= lines for $GITHUB_OUTPUT")
    n = sub.add_parser("notes", help="print a version's CHANGELOG section")
    n.add_argument("tag")
    t = sub.add_parser("tag-message", help="print the annotated tag message")
    t.add_argument("tag")
    t.add_argument("sha")
    args = parser.parse_args(argv)
    try:
        if args.command == "bump":
            print(bump(args.how))
        elif args.command == "plan":
            decision = plan()
            print("\n".join(f"{key}={value}" for key, value in decision.items()))
            if decision["release"] == "false":
                print(f"release: {decision['tag']} is already tagged; nothing to release",
                      file=sys.stderr)
        elif args.command == "notes":
            sys.stdout.write(notes(args.tag))
        else:
            print(tag_message(args.tag, args.sha))
    except ReleaseError as exc:
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") else "release: "
        print(f"{prefix}{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
