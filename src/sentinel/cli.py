"""CLI / hook entrypoint. `sentinel run` is what pre-commit invokes."""
import sys
from .config import load_config
from .collectors.staged_diff import collect_staged
from .detectors import secrets as secret_det, pii as pii_det
from .policy.engine import decide
from .ui.terminal import present, is_interactive

def run(argv=None) -> int:
    cfg = load_config()
    units = collect_staged()                       # only added lines
    findings = secret_det.scan(units, cfg) + pii_det.scan(units, cfg)
    decisions = [decide(f, cfg) for f in findings]

    blocking = [d for d in decisions if d.action in ("block", "warn")]
    if not blocking:
        return 0                                    # commit proceeds

    if is_interactive():
        return present(blocking, cfg)               # explain -> preview -> apply
    # Headless (IDE/GUI): never guess approval. Block with instructions.
    present(blocking, cfg, interactive=False)
    print("\nRun `sentinel review` in a terminal to remediate.", file=sys.stderr)
    return 1

def main() -> None:
    raise SystemExit(run(sys.argv[1:]))
