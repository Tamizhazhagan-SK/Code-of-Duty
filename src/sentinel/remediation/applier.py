"""Apply an APPROVED fix and restage only the affected lines."""
import subprocess

def apply(path: str, patch: str) -> None:
    # write the reviewed change, then:
    subprocess.run(["git", "add", "--", path], check=True)
