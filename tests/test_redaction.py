def test_redact_never_returns_raw():
    from sentinel.classifier.redact import redact
    assert "AKIA" not in redact("AKIAEXAMPLE1234567890", "aws_key")
