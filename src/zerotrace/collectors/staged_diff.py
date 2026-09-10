"""Collect only staged, ADDED lines with a small surrounding window."""
import re
import subprocess
from dataclasses import dataclass

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_DIFF_GIT_RE = re.compile(r"^diff --git a/.+ b/(.+)$")

_TEST_MARKERS = ("test", "tests", "spec", "specs", "fixture", "fixtures")
_CONFIG_EXTS = (".env", ".yml", ".yaml", ".json", ".ini", ".toml", ".cfg", ".conf")
_DOCS_EXTS = (".md", ".rst", ".txt")
_GENERATED_MARKERS = ("node_modules", "dist", "build", ".git", "generated", "vendor")

_WINDOW_RADIUS = 2  # lines of context on each side of an added line


@dataclass(frozen=True)
class Unit:
    path: str
    file_class: str      # code | config | test | docs | generated
    line_no: int
    text: str
    window: str          # a few lines of context (also scanned/redacted)


def classify_file(path: str) -> str:
    lower = path.lower()
    parts = re.split(r"[\\/]", lower)
    if any(marker in parts for marker in _TEST_MARKERS) or "fixture" in lower:
        return "test"
    if any(marker in parts for marker in _GENERATED_MARKERS):
        return "generated"
    basename = parts[-1] if parts else lower
    if basename.startswith(".env") or lower.endswith(_CONFIG_EXTS) or "config" in lower:
        return "config"
    if lower.endswith(_DOCS_EXTS):
        return "docs"
    return "code"


def collect_staged() -> list["Unit"]:
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=3", "--no-color"],
        capture_output=True, text=True, check=True,
    ).stdout

    path: str | None = None
    new_line_no = 0
    is_binary = False
    # every context/added line kept in new-file line order, for window building
    file_lines: dict[str, list[tuple[int, str]]] = {}
    added: list[tuple[str, int, str]] = []

    for raw_line in diff.splitlines():
        diff_git_match = _DIFF_GIT_RE.match(raw_line)
        if diff_git_match:
            path = diff_git_match.group(1)
            is_binary = False
            file_lines.setdefault(path, [])
            continue

        if raw_line.startswith("Binary files"):
            is_binary = True
            continue

        if path is None or is_binary:
            continue

        hunk_match = _HUNK_RE.match(raw_line)
        if hunk_match:
            new_line_no = int(hunk_match.group(1))
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue

        if raw_line.startswith("+"):
            text = raw_line[1:]
            file_lines[path].append((new_line_no, text))
            added.append((path, new_line_no, text))
            new_line_no += 1
        elif raw_line.startswith("-"):
            continue  # removed line, doesn't exist in the new file
        elif raw_line.startswith(" "):
            file_lines[path].append((new_line_no, raw_line[1:]))
            new_line_no += 1
        # anything else (e.g. "\ No newline at end of file") is ignored

    units: list[Unit] = []
    for path, line_no, text in added:
        lines = file_lines[path]
        idx = next(i for i, (ln, _) in enumerate(lines) if ln == line_no)
        lo = max(0, idx - _WINDOW_RADIUS)
        hi = min(len(lines), idx + _WINDOW_RADIUS + 1)
        window = "\n".join(t for _, t in lines[lo:hi])
        units.append(Unit(path=path, file_class=classify_file(path),
                           line_no=line_no, text=text, window=window))
    return units
