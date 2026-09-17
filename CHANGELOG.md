# Changelog

All notable changes documented here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-17
First public release.
### Added
- Local-first pre-commit secret & PII guardrail for every repo on a machine.
- `zerotrace install --global` (or `--system` for MDM/IT rollout) sets a managed `core.hooksPath`
  that chains every hook name; `uninstall` restores whatever was there before. There is
  deliberately no per-repo install mode: `zerotrace doctor --fix` only patches a repo-local
  override (e.g. husky) that would otherwise defeat the global install.
- One-command bootstrap installers (`install.sh`, `install.ps1`) that need no pre-existing
  pip/pipx/uv - they bootstrap Python itself via `ensurepip` and the OS package manager if needed.
- Interactive remediation inside `git commit` (terminal reattach); `pre-push` backstop for
  `--no-verify`; `scan --range/--all/--format json`; `init`; `doctor [--pin-model] [--warm] [--fix]`;
  `eval`.
- Detection layers: provider rule pack (26 formats incl. DB connection strings), hardcoded
  credential assignments across 10+ languages and config formats, sensitive files, PAN/Aadhaar/
  card/IBAN with checksums, detect-secrets, regex + NER PII.
- Layered config (org ← user ← repo) with org-locked keys.
- AI tie-break: shape features + fully masked windows, few-shot injection-hardened prompt,
  JSON-schema constrained decoding, escalation to BLOCK, concurrent + cached, digest pinning,
  Ollama and OpenAI-compatible runtimes (AWS-ready), remote-endpoint guardrails.
- Language-aware fixes (`os.environ[...]`, `process.env.X`, `os.Getenv`, `System.getenv`,
  `var.x`, `${X}`), `[U]nstage + .gitignore + .env.example`.
- WSL-aware environment detection (`platform_env.py`): classifies Windows/macOS/Linux/WSL1/WSL2
  and repo paths as native/DrvFs/`\\wsl$\`, guarding hook installs on DrvFs mounts.
- Demo kit for macOS/Linux and Windows sharing one fixture renderer; 170+ tests.
### Changed
- Fixes are applied to the index blob (unstaged edits are never staged).
- State moved into `.git/zerotrace/`; Presidio is an opt-in extra; the `ollama` SDK is no
  longer needed.
### Fixed
- Secrets other than AWS/PEM could reach the model unredacted.
- The interactive menu never appeared under the pre-commit framework.
