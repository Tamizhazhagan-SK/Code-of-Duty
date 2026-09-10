"""The ONLY place that decides block/warn/allow. Pure + deterministic."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Decision:
    action: str          # block | warn | allow
    severity: str
    reason: str
    finding: object

def decide(finding, cfg) -> "Decision":
    # HIGH secret -> block (never calls the model).
    # MEDIUM ambiguous -> optional LLM tie-break (bounded), else warn.
    # LOW placeholder -> allow with auditable exception.
    # On any uncertainty/error -> fail closed (warn/block).
    return Decision("warn", "medium", "placeholder", finding)
