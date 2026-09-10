# Policy engine

Deterministic mapping from findings to an action. Pure function, fully unit-tested.

| Finding | Confidence | Action |
|---|---|---|
| Private key / clear API key / cloud credential | High | **Block** |
| Password in config / connection string | High | **Block** |
| Likely customer PII in code/config | Medium | **Warn** (confirm or replace) |
| Realistic-looking value, ambiguous | Medium | -> LLM tie-break, else Warn |
| Placeholder / public example / seeded fixture | Low | Allow (auditable exception) |

Inputs: `rule_id`, `kind`, `entropy`, `file_class`, `confidence`, config
thresholds, optional LLM verdict. Output: `Decision(action, severity, reason)`.
The engine is the single source of the pass/fail signal; nothing else decides.
