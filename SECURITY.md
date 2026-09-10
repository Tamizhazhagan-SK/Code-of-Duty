# Security Policy

Sentinel runs on every commit with read access to your staged code, and can
optionally invoke a local model. It is a piece of security-critical tooling,
so its own supply chain matters as much as what it detects.

## Reporting a vulnerability
Email security@<org>.example with details. Do **not** open a public issue for
anything exploitable. We aim to acknowledge within 3 business days.

## Guarantees this tool tries to keep
- **No egress.** Core detection and the optional local model never make network
  calls. `detect-secrets` online verification is disabled. CI verifies this with
  a sandbox that fails the build on any outbound socket.
- **No plaintext secret persistence.** Nothing writes a raw candidate to disk or
  logs. Baselines and exceptions store salted fingerprints only.
- **Fail closed.** Scanner crash, model timeout, or unparseable model output ->
  block/warn, never silently allow.
- **Pinned integrity.** Dependencies are hash-locked; the local model file is
  verified against a pinned SHA-256 before load.

## Non-guarantees (be honest)
- A client-side hook can be bypassed (`git commit --no-verify`, direct plumbing).
- A 3B local model is **not** a security boundary and can be wrong both ways.
- Detection is best-effort; this is not a compliance certification.
