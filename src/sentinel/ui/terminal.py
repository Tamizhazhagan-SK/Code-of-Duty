"""rich rendering + interaction, with a headless fallback."""
import sys

def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()

def present(decisions, cfg, interactive: bool = True) -> int:
    # Interactive: explain -> preview -> [R]eplace [V]ault [E]xception [A]bort.
    # Headless: print findings + how to remediate; return 1.
    return 1
