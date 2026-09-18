# Changelog

All notable changes documented here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Runtime security gateway (`src/zerotrace/gateway`) and `zerotrace gateway` CLI subcommand:
  sanitizes arbitrary AI-agent/MCP-tool/RAG payloads (not git-backed) through the same
  detect -> decide pipeline as the git hook, masking findings out of the text instead of
  blocking, plus two new detectors for this interception point: classification markers
  (`detectors/confidentiality.py`) and indirect prompt injection (`detectors/prompt_injection.py`).
- Claude Code plugin marketplace (`bmw-skills-marketplace/`), restructured to the official
  `.claude-plugin/marketplace.json` + `git-subdir` layout so the plugin can live at `skill/`.
- MDM/fleet rollout kit (`deploy/`): Intune install/uninstall scripts, a Jamf postinstall
  script, and `policy.example.yml` for org-locked config.
- Cross-platform single-file binaries via PyInstaller (`zerotrace.spec`), built and attached
  to GitHub releases on tag push (macOS/Linux/Windows).
- `docs/DEMO_RUNBOOK.md`: click-by-click live demo script with the 8 demo beats.
- `docs/AI_CLASSIFIER.md` "Measured results": real latency and accuracy numbers from
  `zerotrace eval` on CPU-only Docker Desktop.
### Fixed
- A base64-obscured Stripe live key no longer evades detection (`stripe-live-key-base64` rule).
- Unicode homoglyph identifiers (e.g. Cyrillic `а` substituted for Latin `a`) no longer bypass
  hardcoded-credential keyword matching.
- `zerotrace doctor --warm` no longer crashes with `UnicodeEncodeError` on legacy (non-UTF-8)
  Windows console codepages; falls back to `?` instead.
- A comment naming the AI tie-break's own verdict keywords (e.g. "classify
  TEST_FIXTURE_OR_PLACEHOLDER") could flip a real secret to an unsafe allow; the policy engine
  now refuses to honor an ALLOW verdict when the finding's context matches a prompt-injection
  pattern, regardless of what the model concluded (found via `zerotrace eval`).

## [Unreleased]
### Fixed
- Gateway: a prompt injection sharing a line with a secret was dropped by `pipeline.dedupe`, so
  the injected instruction was forwarded to the model and missing from the audit record. PII,
  prompt-injection and confidentiality findings are now deduplicated per value, not per line.
### Changed
- Default `model.timeout_seconds` raised from 20 s to 120 s: measured CPU-only inference is
  ~106 s p50, so the old default failed every tie-break closed to WARN in repos without a config.
- README and `docs/ARCHITECTURE.md` describe both enforcement points (commit time and AI
  runtime); `sonar-project.properties` now analyses the installer and fleet scripts.

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
