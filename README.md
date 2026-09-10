# ZeroTrace — Pre-Commit Secret & PII Sanitizer Agent

> Stop sensitive data before it leaves the developer's machine.

ZeroTrace is a **local-first** Git pre-commit guardrail. On every commit it inspects
*only the staged diff*, detects likely secrets and PII with deterministic scanners,
optionally disambiguates the *uncertain* findings with a **local** small LLM
(never the cloud), explains the risk, and proposes a human-approved remediation
before anything enters Git history.

**Design contract:** deterministic-first. The LLM can never *unblock* a
high-confidence secret. If the model is missing or errors, ZeroTrace fails **closed**.

## Quick start

```bash
pipx install zerotrace                 # or: uv tool install zerotrace
zerotrace init                         # writes .secrets.baseline + .zerotrace.yml
pre-commit install                     # register the git hook
```

From then on `git commit` runs ZeroTrace automatically on staged changes.

## Live demo (prototype)

Runs a real, staged `git commit` against a throwaway repo and blocks it live.

```powershell
# 1. Install the project locally (once)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,llm]"

# 2. Start the local Qwen2.5-Coder inference service (used for MEDIUM/ambiguous findings)
cd docker
docker compose up -d   # first run pulls the model, a couple of GB

# 3. Build the demo repo and attempt a commit
cd ..
pwsh -File .\demo\setup_demo_repo.ps1
```

The demo stages a fake AWS key, an ambiguous high-entropy token, an internal
employee email + internal ID in a test fixture, and one clean file. The commit
is blocked; run `zerotrace review` in the same terminal to see the guided
[R]eplace / [V]ault-ref / [E]xception / [A]bort flow and re-commit once resolved.

See `docs/ARCHITECTURE.md` for the full design and `docs/THREAT_MODEL.md` for the
security model. ZeroTrace is a **helpful guardrail, not a security boundary**
(`--no-verify` bypasses any client hook) — pair it with server-side push protection.

## License / IP

See `LICENSE` and the IP note in `CONTRIBUTING.md`. If this originated in a
company hackathon, confirm ownership before open-sourcing.
