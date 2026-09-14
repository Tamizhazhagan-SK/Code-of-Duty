"""Policy is pure -> the easiest and most important thing to test hard."""

from zerotrace.config import Config
from zerotrace.detectors import Finding
from zerotrace.policy.engine import decide


def _finding(severity: str, **overrides) -> Finding:
    defaults = dict(
        rule_id="Test Rule", kind="test_rule", severity=severity, confidence=0.8,
        path="app.py", line_no=1, file_class="code", line_text="SECRET = 'x'",
        matched_value="x",
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_high_secret_blocks_without_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def _boom(*args, **kwargs):
        raise AssertionError("the model must never be consulted for a HIGH finding")

    monkeypatch.setattr("zerotrace.classifier.llm.classify", _boom)
    decision = decide(_finding("high"), Config())
    assert decision.action == "block"


def test_medium_without_model_warns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    decision = decide(_finding("medium"), Config(model_enabled=False))
    assert decision.action == "warn"


def test_low_confidence_allows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    decision = decide(_finding("low"), Config())
    assert decision.action == "allow"


def test_error_fails_closed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def _raise(*args, **kwargs):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("zerotrace.classifier.llm.classify", _raise)
    decision = decide(_finding("medium"), Config(model_enabled=True))
    assert decision.action == "warn"  # never "allow" on an unhandled error


def test_active_exception_allows_any_severity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from zerotrace.audit import exceptions as audit_exceptions
    from zerotrace.audit.fingerprint import of_finding

    finding = _finding("high")
    audit_exceptions.add(of_finding(finding), "reviewed false positive", ttl_days=30)

    decision = decide(finding, Config())
    assert decision.action == "allow"


class _V:
    def __init__(self, classification, confidence, reason="r"):
        self.classification, self.confidence, self.reason = classification, confidence, reason


def test_model_may_escalate_medium_to_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    decision = decide(_finding("medium"), Config(), verdict=_V("REAL_SECRET", 0.9))
    assert decision.action == "block"


def test_escalation_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    decision = decide(_finding("medium"), Config(model_can_escalate=False),
                      verdict=_V("REAL_SECRET", 0.95))
    assert decision.action == "warn"


def test_low_confidence_placeholder_verdict_still_warns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    decision = decide(_finding("medium"), Config(),
                      verdict=_V("TEST_FIXTURE_OR_PLACEHOLDER", 0.4))
    assert decision.action == "warn"
