# The optional local classifier

## When it runs
Only for **MEDIUM-confidence** findings the deterministic layer can't settle
(e.g. "realistic-looking key" vs "obvious placeholder"). HIGH findings block
without ever calling the model. If the model is `off`/missing, MEDIUM findings
degrade to WARN (fail-closed), not ALLOW.

## Contract (strict)
Input: a **redacted** candidate token + a small code window (also scanned for
secrets and redacted). Output: JSON only.
```json
{ "classification": "REAL_SECRET|PII|TEST_FIXTURE_OR_PLACEHOLDER|UNKNOWN",
  "confidence": 0.0, "reason": "under 20 words, no value echoed" }
```
Runtime: `temperature=0`, fixed seed -> reproducible, auditable verdicts.
Validated by `classifier/schema.py` (pydantic). Any of: parse failure, echoed
value, out-of-enum, timeout -> discard verdict, fall back to WARN/BLOCK.

## Why the model can't be a hole
The engine only *lowers* friction on MEDIUM. It never receives a HIGH finding, so
a jailbroken/poisoned model can't unblock a real leak — the worst it can do to a
MEDIUM is force a WARN, which is already the safe default. See `docs/THREAT_MODEL.md`.
