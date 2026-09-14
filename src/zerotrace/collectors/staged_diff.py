"""Turn a git diff into ADDED-line units (with a small window). Staged diff, commit, or tree."""
import re
from dataclasses import dataclass, field

from .. import gitutil

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_PLUS_PATH_RE = re.compile(r'^\+\+\+ (?:"b/(.+)"|b/(.+))$')

_TEST_MARKERS = ("test", "tests", "spec", "specs", "fixture", "fixtures", "__tests__", "testdata")
_CONFIG_EXTS = (".env", ".yml", ".yaml", ".json", ".ini", ".toml", ".cfg", ".conf",
                ".properties", ".tfvars", ".xml")
_DOCS_EXTS = (".md", ".rst", ".txt", ".adoc")
_GENERATED_MARKERS = ("node_modules", "dist", "build", ".git", "generated", "vendor")

_WINDOW_RADIUS = 2  # lines of context on each side of an added line


@dataclass(frozen=True)
class Unit:
    path: str
    file_class: str      # code | config | test | docs | generated
    line_no: int
    text: str
    window: str          # a few lines of context (also scanned/redacted)
    rev: str = ""        # "" = index (staged); otherwise the commit that added the line


@dataclass
class Changeset:
    units: list[Unit] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)   # every added/modified path, incl. binary
    rev: str = ""                                     # "" = index


def classify_file(path: str) -> str:
    lower = path.lower()
    parts = re.split(r"[\\/]", lower)
    basename = parts[-1] if parts else lower
    stem = basename.split(".")[0]
    if any(marker in parts for marker in _TEST_MARKERS) or "fixture" in lower \
            or stem.startswith("test_") or stem.endswith(("_test", "_spec")) \
            or ".test." in basename or ".spec." in basename:
        return "test"
    if any(marker in parts for marker in _GENERATED_MARKERS):
        return "generated"
    if basename.startswith(".env") or lower.endswith(_CONFIG_EXTS) or "config" in lower \
            or basename in ("dockerfile", "docker-compose.yml") or lower.endswith(".tf"):
        return "config"
    if lower.endswith(_DOCS_EXTS):
        return "docs"
    return "code"


def _unquote(path: str) -> str:
    """git quotes paths with unusual chars as C strings: "a\\tb" -> a<TAB>b."""
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        return path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape") \
            .encode("latin-1").decode("utf-8", "replace")
    return path


def parse_diff(diff: str, rev: str = "") -> Changeset:
    path: str | None = None
    new_line_no = 0
    in_hunk = False
    file_lines: dict[str, list[tuple[int, str]]] = {}
    added: list[tuple[str, int, str]] = []
    paths: list[str] = []

    for raw_line in diff.splitlines():
        if raw_line.startswith("diff --git "):
            path, in_hunk = None, False
            continue
        if not in_hunk:
            plus = _PLUS_PATH_RE.match(raw_line)
            if plus:
                quoted, bare = plus.groups()
                path = _unquote(f'"{quoted}"') if quoted else bare.rstrip("\t")
                file_lines.setdefault(path, [])
                paths.append(path)
                continue
            if raw_line.startswith("Binary files ") and " and b/" in raw_line:
                bin_path = raw_line.split(" and b/", 1)[1].rsplit(" differ", 1)[0]
                paths.append(_unquote(bin_path))
                continue
            if raw_line.startswith("+++ /dev/null"):
                path = None  # deletion
                continue

        hunk_match = _HUNK_RE.match(raw_line)
        if hunk_match:
            new_line_no = int(hunk_match.group(1))
            in_hunk = path is not None
            continue
        if not in_hunk or path is None:
            continue

        if raw_line.startswith("+"):
            text = raw_line[1:]
            file_lines[path].append((new_line_no, text))
            added.append((path, new_line_no, text))
            new_line_no += 1
        elif raw_line.startswith(" "):
            file_lines[path].append((new_line_no, raw_line[1:]))
            new_line_no += 1
        # "-" lines don't exist in the new file; "\ No newline" is ignored

    units: list[Unit] = []
    for p, line_no, text in added:
        lines = file_lines[p]
        idx = next(i for i, (ln, _) in enumerate(lines) if ln == line_no)
        lo = max(0, idx - _WINDOW_RADIUS)
        hi = min(len(lines), idx + _WINDOW_RADIUS + 1)
        window = "\n".join(t for _, t in lines[lo:hi])
        units.append(Unit(path=p, file_class=classify_file(p), line_no=line_no,
                          text=text, window=window, rev=rev))
    return Changeset(units=units, paths=list(dict.fromkeys(paths)), rev=rev)


_DIFF_FLAGS = ("--unified=3", "--no-color", "--no-ext-diff", "--no-renames", "--diff-filter=ACMRT")


def collect_staged() -> Changeset:
    diff = gitutil.git("-c", "core.quotepath=false", "diff", "--cached", *_DIFF_FLAGS)
    return parse_diff(diff, rev="")


def collect_commit(sha: str) -> Changeset:
    """Lines introduced by one commit (vs. its first parent; root commits vs. empty tree)."""
    diff = gitutil.git("-c", "core.quotepath=false", "diff-tree", "-p", "-r", "--root",
                       "--no-commit-id", "--first-parent", *_DIFF_FLAGS, sha)
    return parse_diff(diff, rev=sha)


def collect_tree(rev: str = "HEAD") -> Changeset:
    """Every line of every tracked file at `rev`, as if newly added (onboarding / --all)."""
    diff = gitutil.git("-c", "core.quotepath=false", "diff",
                       "4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # the empty tree
                       rev, *_DIFF_FLAGS)
    return parse_diff(diff, rev=rev)


