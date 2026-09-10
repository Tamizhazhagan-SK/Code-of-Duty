"""Load and validate .sentinel.yml. Fail closed on a bad/missing config."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    model_enabled: bool = True
    # ... thresholds, locales, ttl, model sha256, etc.

def load_config(path: str = ".sentinel.yml") -> "Config":
    # TODO: parse YAML, validate against schema, verify model sha256 pin.
    return Config()
