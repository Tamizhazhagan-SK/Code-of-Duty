"""Load and validate .zerotrace.yml. Fail closed on a bad/missing config."""
import os
from dataclasses import dataclass, field

import yaml

_PLACEHOLDER_SHA256 = "REPLACE_WITH_PINNED_MODEL_HASH"


@dataclass(frozen=True)
class Config:
    model_enabled: bool = True
    model_runtime: str = "ollama"          # ollama | llama-cpp | off
    model_name: str = "qwen2.5-coder:3b-instruct-q4_K_M"
    model_sha256: str = _PLACEHOLDER_SHA256
    model_timeout_seconds: float = 4.0
    max_context_lines: int = 6
    block_severity: tuple[str, ...] = ("critical", "high")
    warn_severity: tuple[str, ...] = ("medium",)
    pii_locales: tuple[str, ...] = ("en", "en_IN")
    action_in_tests: str = "replace_synthetic"
    action_in_config: str = "env_reference"
    exceptions_ttl_days: int = 30
    ollama_host: str = field(default_factory=lambda: os.environ.get(
        "ZEROTRACE_OLLAMA_HOST", "http://localhost:11434",
    ))


def load_config(path: str = ".zerotrace.yml") -> "Config":
    if not os.path.exists(path):
        return Config()  # safe defaults; still model_enabled, still fail-closed
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return Config()  # unreadable/invalid config -> fail closed to defaults

    model = raw.get("model") or {}
    policy = raw.get("policy") or {}
    pii = policy.get("pii") or {}
    exceptions = raw.get("exceptions") or {}

    sha256 = model.get("sha256", _PLACEHOLDER_SHA256)
    if sha256 == _PLACEHOLDER_SHA256:
        print(
            "zerotrace: warning: model.sha256 in .zerotrace.yml is still the "
            "placeholder value; model integrity is not pinned.",
        )

    return Config(
        model_enabled=bool(model.get("enabled", True)) and model.get("runtime") != "off",
        model_runtime=model.get("runtime", "ollama"),
        model_name=model.get("name", Config.model_name),
        model_sha256=sha256,
        model_timeout_seconds=float(model.get("timeout_seconds", 4.0)),
        max_context_lines=int(model.get("max_context_lines", 6)),
        block_severity=tuple(policy.get("block_severity", ["critical", "high"])),
        warn_severity=tuple(policy.get("warn_severity", ["medium"])),
        pii_locales=tuple(pii.get("locales", ["en", "en_IN"])),
        action_in_tests=pii.get("action_in_tests", "replace_synthetic"),
        action_in_config=pii.get("action_in_config", "env_reference"),
        exceptions_ttl_days=int(exceptions.get("ttl_days", 30)),
    )
