# ADR 0002: Deterministic-first, fail-closed, bounded LLM

**Status:** accepted

**Decision:** The LLM is never on the blocking path for HIGH findings and can
never turn a BLOCK into an ALLOW. On any error the system fails closed.

**Rationale:** a local 3B model is not a security boundary; treating it as advisory
keeps correctness bounded by the deterministic layer while still cutting false
positives on ambiguous MEDIUM findings.
