"""Collect only staged, ADDED lines with a small surrounding window."""
import subprocess
from dataclasses import dataclass

@dataclass(frozen=True)
class Unit:
    path: str
    file_class: str      # code | config | test | docs | generated
    line_no: int
    text: str
    window: str          # a few lines of context (also scanned/redacted)

def collect_staged() -> list["Unit"]:
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=3", "--no-color"],
        capture_output=True, text=True, check=True,
    ).stdout
    # TODO: parse hunks; keep '+' lines; classify file; build windows.
    return []
