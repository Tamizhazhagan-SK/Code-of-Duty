# Rolling ZeroTrace out to every developer

The goal is that every commit on every managed machine goes through ZeroTrace, with no
per-repo setup and no reliance on developers remembering to opt in.

## 1. How one install covers every repo

`zerotrace install --global` (or `--system`) points git's `core.hooksPath` at a
ZeroTrace-managed directory. Git then runs those hooks for **every** repository: existing clones,
new clones, `git init`, and commits made by IDEs, GUI clients and AI coding agents.
`ggshield install --mode global` and Talisman use the same mechanism.

`core.hooksPath` *replaces* `.git/hooks`, so the managed directory contains a shim for every
hook name, and each shim chains:

1. the repo's own `.git/hooks/<name>` (git-lfs, legacy custom hooks, `pre-commit install`ed
   hooks),
2. any hooks directory that was configured before ZeroTrace (a company-wide hooks dir is kept
   and restored by `zerotrace uninstall`),
3. for `pre-commit`: the repo's `.pre-commit-config.yaml` (the pre-commit framework refuses to
   `install` while `core.hooksPath` is set, so the shim runs it; opt out with
   `ZEROTRACE_CHAIN_PRECOMMIT=0`),
4. ZeroTrace itself, with the terminal reattached so the fix menu works inside `git commit`.

**Known override:** a repo-local `core.hooksPath` (husky v9 sets `.husky/_`) wins over
global/system. `zerotrace doctor` flags these repos and `zerotrace install --repo` adds ZeroTrace
to `.husky/pre-commit`. The server-side backstop (§5) covers anything that slips through.

## 2. Packaging

| Channel | Command |
|---|---|
| Internal PyPI (Artifactory/Nexus) | `pipx install zerotrace` or `uv tool install zerotrace`, then `zerotrace install --global` |
| No Python on laptops | signed single-file builds (PyInstaller) for Windows/macOS/Linux, wrapped as a winget/Intune package, Homebrew tap, Jamf script or apt/rpm |
| Dev containers / Codespaces / VDI | bake `pip install zerotrace && zerotrace install --system` into the golden image or a devcontainer feature |

The base install is intentionally light: `detect-secrets`, `rich` and `pyyaml`. The model client
uses only the standard library. Presidio/spaCy NER is an opt-in extra (`zerotrace[pii-ner]`).

## 3. Fleet rollout with MDM (Intune / Jamf / SCCM / Ansible)

```bash
pipx install --global zerotrace==<pinned>      # or deploy the signed binary
zerotrace install --system                     # machine-wide core.hooksPath
install -m 0644 policy.yml /etc/zerotrace/policy.yml   # %ProgramData%\zerotrace\policy.yml on Windows
```

Example org policy. Keys listed under `locked` can't be weakened by user or repo config:

```yaml
locked: [enabled, policy.block_severity, model.endpoint, model.allow_remote]
enabled: true
policy:
  block_severity: [critical, high]
model:
  runtime: openai                       # or ollama for per-laptop inference
  endpoint: https://zerotrace-inference.internal.example
  allow_remote: true
  auth_env: ZEROTRACE_MODEL_TOKEN
  digest: "sha256:…"
rules:
  extra: [/etc/zerotrace/rules-acme.yml] # internal token formats, employee-ID patterns
```

The layer order is built-in defaults ← org policy ← `~/.zerotrace/config.yml` ← repo
`.zerotrace.yml`, and org-locked keys win. A `critical` finding can never be configured to pass.

## 4. The model tier

| Tier | When | Notes |
|---|---|---|
| Off | minimal installs | MEDIUM findings WARN (fail closed); everything deterministic still blocks |
| Local Ollama (Docker or native) | today, per laptop | loopback only; native Ollama uses the GPU (Metal on macOS) |
| Company inference endpoint (AWS) | target | laptops need no Docker and no model download; see `docs/AWS_INFERENCE.md` |

Only redacted shape features and masked code reach any model (see `docs/AI_CLASSIFIER.md`).

## 5. Server-side backstop (client hooks are advisory)

`--no-verify`, a husky override, or a machine without ZeroTrace can all bypass a client hook.
Enforce on the server as well:

- An org-wide GitHub ruleset or required workflow running `zerotrace scan --range
  ${{ github.event.pull_request.base.sha }}..${{ github.sha }} --no-model` (see
  `.github/workflows/secret-scan.yml`), plus Gitleaks as a second, independent engine.
- GitHub Secret Scanning push protection, GitLab secret push protection, or pre-receive hooks.
- Credential rotation runbooks. A blocked push still means the secret exists on a laptop.

## 6. AI coding agents

Agents commit through git, so the global hook covers them automatically. The `skill/`
directory packages ZeroTrace as an Agent Skill (scan, explain, propose, never auto-apply) for
Claude Code style marketplaces.

## 7. Governance and metrics (roadmap)

- Commit exceptions as a reviewed file (fingerprints only) so they go through PR review.
- Opt-in fleet telemetry: counts of blocked/fixed findings by rule, never values, for a
  "leaks prevented" dashboard.
- Signed releases and hash-locked dependencies, because a tool that reads every commit is itself
  a supply-chain target.
