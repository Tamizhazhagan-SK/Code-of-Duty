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

## License
ZeroTrace is licensed under [Apache-2.0](LICENSE). By submitting a contribution
you agree it is licensed under the same terms (see `LICENSE` section 5).

## Code of Conduct
This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
