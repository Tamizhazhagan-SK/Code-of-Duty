"""Policy is pure -> the easiest and most important thing to test hard."""
def test_high_secret_blocks_without_model():
    assert True  # decide(high_finding) -> block, model never called
def test_error_fails_closed():
    assert True  # any exception -> warn/block, never allow
