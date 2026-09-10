"""Build a human-readable fix PREVIEW. Never edits files here."""
def propose(decision) -> str:
    # env-reference | synthetic PII | .env move | vault URI | reviewed exception
    return "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
