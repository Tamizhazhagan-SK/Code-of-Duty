"""Local model call (Ollama / llama-cpp). No network beyond localhost. Timeout + seed."""
from . import prompt, schema, redact


def classify(candidate: str, kind: str, window: str, cfg) -> "schema.Verdict | None":
    if cfg.model_runtime != "ollama":
        return None  # llama-cpp/off not wired for this demo -> fail closed to WARN

    token = redact.redact(candidate, kind)
    safe_window = redact.scrub_window(window)
    user_prompt = prompt.build(token, safe_window)

    try:
        import ollama
    except ImportError:
        return None  # optional dependency not installed -> fail closed

    try:
        client = ollama.Client(host=cfg.ollama_host, timeout=cfg.model_timeout_seconds)
        response = client.chat(
            model=cfg.model_name,
            messages=[
                {"role": "system", "content": prompt.SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0, "seed": 0},
            format="json",
        )
        raw = response.message.content or ""
    except Exception:
        return None  # unreachable/timeout/missing model -> fail closed to WARN

    verdict = schema.parse(raw)
    if verdict is None:
        return None
    # Defense in depth: discard if the model echoed the real (unredacted) value.
    if candidate and len(candidate) >= 6 and candidate in verdict.reason:
        return None
    return verdict
