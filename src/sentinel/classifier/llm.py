"""Local model call (Ollama / llama-cpp). No network beyond localhost. Timeout + seed."""
from . import prompt, schema, redact

def classify(candidate: str, kind: str, window: str, cfg) -> "schema.Verdict | None":
    token = redact.redact(candidate, kind)
    safe_window = redact.scrub_window(window)
    _ = prompt.build(token, safe_window)
    # TODO: call ollama at temperature=0, fixed seed, cfg.timeout; then schema.parse.
    return None
