# Changelog

All notable changes documented here (Keep a Changelog format).

## [0.2.0] - 2026-09-11
### Added
- `zerotrace install --global | --system | --repo` with chaining shims for every hook name,
  plus `uninstall` that restores the previous `core.hooksPath`.
- Interactive remediation inside `git commit` (terminal reattach); `pre-push` backstop for
  `--no-verify`; `scan --range/--all/--format json`; `init`; `doctor [--pin-model] [--warm]`; `eval`.
- Detection layers: provider rule pack (26 formats incl. DB connection strings), hardcoded
  credential assignments across 10+ languages and config formats, sensitive files, PAN/Aadhaar/
  card/IBAN with checksums.
- Layered config (org ← user ← repo) with org-locked keys.
- AI tie-break v2: shape features + fully masked windows, few-shot injection-hardened prompt,
  JSON-schema constrained decoding, escalation to BLOCK, concurrent + cached, digest pinning,
  Ollama and OpenAI-compatible runtimes (AWS-ready), remote-endpoint guardrails.
- Language-aware fixes (`os.environ[...]`, `process.env.X`, `os.Getenv`, `System.getenv`,
  `var.x`, `${X}`), `[U]nstage + .gitignore + .env.example`.
- Demo kit for macOS/Linux and Windows sharing one fixture renderer; 100+ tests.
### Changed
- Fixes are applied to the index blob (unstaged edits are never staged).
- State moved into `.git/zerotrace/`; Presidio is an opt-in extra; the `ollama` SDK is no
  longer needed.
### Fixed
- Secrets other than AWS/PEM could reach the model unredacted.
- The interactive menu never appeared under the pre-commit framework.

## [0.1.0]
- Initial scaffold.
