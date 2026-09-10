"""Apply an APPROVED fix and restage only the affected lines."""
import subprocess


def apply(path: str, line_no: int, new_text: str) -> None:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    ending = "\n" if (line_no <= len(lines) and lines[line_no - 1].endswith("\n")) else ""
    lines[line_no - 1] = new_text.rstrip("\n") + ending

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    subprocess.run(["git", "add", "--", path], check=True)
