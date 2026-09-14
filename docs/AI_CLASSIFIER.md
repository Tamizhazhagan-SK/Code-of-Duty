# The AI tie-break (Qwen2.5-Coder 3B)

## When it runs
Only for **MEDIUM** findings the deterministic layers can't settle. Examples: a short random
token bound to `analyticsToken`, a `session_secret` that might be a dev default, or a random
key in a test fixture. HIGH/CRITICAL findings block without ever calling the model. If the
model is off, missing, slow, or serving the wrong digest, MEDIUM findings **WARN**.

## Asymmetric trust
| Verdict | Effect on a MEDIUM finding |
|---|---|
| `TEST_FIXTURE_OR_PLACEHOLDER` ≥ `allow_threshold` (0.6) | ALLOW (less friction) |
| `REAL_SECRET` ≥ `escalate_threshold` (0.8) | **BLOCK** (escalation; `can_escalate: false` disables it) |
| anything else / no verdict | WARN |

A jailbroken model can at most turn one ambiguous finding into an allow. It can never touch a
deterministic block. `zerotrace eval` measures exactly that risk as the **unsafe-allow rate**.

## What the model sees: shape, never value
```json
{"identifier": "analyticsToken", "language": "javascript", "file_class": "code",
 "known_public_prefix": "(none)",
 "value_shape": {"length": 12, "charset": "base62/64", "entropy_bits_per_char": 3.58,
                 "skeleton": "aA9aaAA9aaAa", "dictionary_word_ratio": 0.0,
                 "most_common_char_ratio": 0.08},
 "env_lookup_nearby": false}
```
Plus a code window where every string literal, unquoted config value, high-entropy token and
provider-format match is masked, and the candidate is shown as `<CANDIDATE>`. The client refuses
to send a prompt that still contains any detected value (property-tested).

## Prompt and decoding
- A system prompt plus three few-shot examples, including two prompt-injection attempts. File
  content sits in `<untrusted>` and is treated as data.
- Constrained decoding: the JSON schema (enum, number 0–1, short reason) is passed as Ollama
  `format` or OpenAI `response_format`. `schema.parse` still validates everything.
- `temperature=0`, `seed=0`, `num_predict=96`, `keep_alive=30m`.
- If the verdict echoes the candidate, it is discarded.

## Runtime and performance
- Plain stdlib HTTP (no SDK), so it works in any venv, pipx install or single-file binary.
- `runtime: ollama` (`/api/chat`) or `runtime: openai` (`/v1/chat/completions`: vLLM,
  LiteLLM, SageMaker/Bedrock gateways). See `docs/AWS_INFERENCE.md`.
- Local endpoints bypass `HTTP(S)_PROXY`. Remote endpoints require `allow_remote: true` and
  `https://`. The bearer token comes from `$ZEROTRACE_MODEL_TOKEN`.
- MEDIUM findings are classified concurrently (`max_parallel`, one overall deadline), and
  verdicts are cached in `.git/zerotrace/cache/`.
- Model integrity: `zerotrace doctor --pin-model` records the served digest. On a mismatch the
  model is not used.

## Measuring it
```bash
zerotrace eval                                   # bundled 36 labelled cases, values generated at run time
zerotrace eval --model qwen2.5-coder:1.5b-instruct --model qwen2.5-coder:3b-instruct-q4_K_M
```
The report covers unsafe allows (real → allow), escalations, noise removed (placeholder/fixture →
allow), failures, and p50/p95 latency per model.
