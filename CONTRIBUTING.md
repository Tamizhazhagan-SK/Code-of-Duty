# Contributing

## Ground rules

1. **Never commit a real secret or real PII, even as a test case.** Fixtures use
   synthetic values only. The repo dogfoods its own hook (`pre-commit install`).
2. Deterministic detection is the source of truth. LLM code paths must remain
   *optional* and must never be able to weaken a deterministic block.
3. Any code that touches a candidate value must go through `redaction` first if
   it can reach a log, a prompt, or disk.

## Dev setup

This repo is currently private, so clone it with your own git credentials first, then
either run the bootstrap script or set up manually.

```bash
git clone https://github.com/Tamizhazhagan-SK/Code-of-Duty.git && cd Code-of-Duty
./scripts/dev_bootstrap.sh          # macOS/Linux - venv, editable install, hook, doctor, tests
.\scripts\dev_bootstrap.ps1         # Windows, same steps
```

Or manually, with the same locked install CI runs:

```bash
python3 -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes --only-binary :all: -r requirements/dev.txt
python -m pip install --no-deps --no-build-isolation --no-index --only-binary :all: -e .
zerotrace install --global                             # also runs .pre-commit-config.yaml
pytest -q
```

## Dependencies

Every install — CI, the bootstrap scripts, the release build — uses the hash-pinned locks in
`requirements/`: `runtime.txt` (the package + its build backend), `dev.txt` (+ the dev and tui
extras) and `release.txt` (+ PyInstaller). Each package is a wheel whose hash is known in
advance, so nothing runs setup code while installing. After changing dependencies in
`pyproject.toml` (or `requirements/*.in`), regenerate them and commit the result:

```bash
python scripts/lock_deps.py              # needs uv: pipx install uv
python scripts/lock_deps.py --upgrade    # move every pin to the newest allowed version
```

`tests/test_locks.py` fails when a lock no longer satisfies `pyproject.toml`, so a forgotten
re-lock shows up in CI rather than as a silently older dependency.

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
