# Architecture

## One question, layered answer
> *Is this staged change safe to add to history, and if not, what is the safest fix?*

Detection runs cheap-and-deterministic first; the LLM is a last-resort tie-breaker.

```
git commit
   -> pre-commit hook -> `zerotrace run`
        1. collectors/staged_diff.py     git diff --cached (added lines only)
        2. detectors/secrets.py          detect-secrets (regex + entropy + keyword)
           detectors/pii.py              Presidio (NER + regex + context)
        3. policy/engine.py              severity x confidence -> BLOCK/WARN/ALLOW
        4. classifier/*  (only MEDIUM)   redact -> local Qwen -> validated JSON
        5. remediation/proposer.py       build a diff preview
        6. ui/terminal.py                explain + ask for approval (TTY)
        7. remediation/applier.py        edit + `git add` only approved lines
        8. audit/*                       fingerprinted, redacted record
```

## Module map
- `collectors/` — turns the staged diff into `(file, line, hunk-context)` units.
- `detectors/` — each returns `Finding(rule_id, kind, severity, confidence, span)`.
  Detectors never see approval logic; they only find.
- `policy/engine.py` — the *only* place that decides block/warn/allow. Pure,
  testable, deterministic. Consumes findings + config + (optional) LLM verdict.
- `classifier/` — optional. `redact.py` runs **before** anything else here.
- `remediation/` — proposes and (after approval) applies fixes; never auto-applies.
- `audit/` — fingerprints + append-only redacted log; exceptions store.
- `ui/` — `rich` rendering + interaction, with a non-interactive fallback.

## Why detect-secrets + Presidio
detect-secrets is a *Python library* (not a separate binary), so it drops straight
into the policy engine, emits JSON, supports a hashed `.secrets.baseline`, runs
offline, and lets you add custom filters/plugins. Presidio gives NER-based PII with
pluggable recognizers (add Aadhaar/PAN for India). Gitleaks/trufflehog remain great
for the *server-side* defense-in-depth layer (see `docs/ADR/0001`).

## The hard practical detail: interactivity
pre-commit hooks do **not** reliably get a TTY (IDE/GUI git clients run them
headless). So ZeroTrace has two modes:
- **Interactive (TTY present):** explain -> preview -> `[R/V/E/A]` -> apply.
- **Non-interactive (no TTY):** block with the explanation + exact command to run
  (`zerotrace review`) to remediate. Never guess an approval.

## Performance budget (< 2s typical)
- Scan staged diff only, added lines only.
- Cache by blob hash (`sha256` of staged content) in `.zerotrace-cache/`.
- **Lazy-load the model** — never load the 3B model unless at least one MEDIUM
  finding exists. Most commits never touch the LLM.
