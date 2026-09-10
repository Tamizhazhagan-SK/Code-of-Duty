# Sentinel — Pre-Commit Secret & PII Sanitizer Agent

> Stop sensitive data before it leaves the developer's machine.

Sentinel is a **local-first** Git pre-commit guardrail. On every commit it inspects
*only the staged diff*, detects likely secrets and PII with deterministic scanners,
optionally disambiguates the *uncertain* findings with a **local** small LLM
(never the cloud), explains the risk, and proposes a human-approved remediation
before anything enters Git history.

**Design contract:** deterministic-first. The LLM can never *unblock* a
high-confidence secret. If the model is missing or errors, Sentinel fails **closed**.

## Quick start
```bash
pipx install sentinel-sanitizer        # or: uv tool install sentinel-sanitizer
sentinel init                          # writes .secrets.baseline + .sentinel.yml
pre-commit install                     # register the git hook
```
From then on `git commit` runs Sentinel automatically on staged changes.

See `docs/ARCHITECTURE.md` for the full design and `docs/THREAT_MODEL.md` for the
security model. Sentinel is a **helpful guardrail, not a security boundary**
(`--no-verify` bypasses any client hook) — pair it with server-side push protection.

## License / IP
See `LICENSE` and the IP note in `CONTRIBUTING.md`. If this originated in a
company hackathon, confirm ownership before open-sourcing.
