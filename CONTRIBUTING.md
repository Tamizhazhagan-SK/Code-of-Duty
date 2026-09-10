# Contributing

## Ground rules
1. **Never commit a real secret or real PII, even as a test case.** Fixtures use
   synthetic values only. The repo dogfoods its own hook (`pre-commit install`).
2. Deterministic detection is the source of truth. LLM code paths must remain
   *optional* and must never be able to weaken a deterministic block.
3. Any code that touches a candidate value must go through `redaction` first if
   it can reach a log, a prompt, or disk.

## Dev setup
```bash
uv sync --extra dev
pre-commit install
uv run pytest
```

## Tests you must add for a new detector
- a true-positive fixture, a placeholder false-positive fixture, and a policy test
  asserting the block/warn/allow decision.

## Commit / PR
- Conventional Commits. One ADR per non-trivial design decision in `docs/ADR/`.
- CI must pass: lint, type-check, tests, and the **egress-deny** and
  **no-plaintext-secret-in-artifacts** gates.

## IP & Licensing
Confirm who owns this code before adding a license or publishing. If it started as
a company hackathon project, the employer likely owns it; get written sign-off
before open-sourcing or publishing to any public marketplace.
