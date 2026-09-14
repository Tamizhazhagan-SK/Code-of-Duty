"""Detection layers: provider rule pack, code assignments, sensitive files, PII, filters."""
import pytest

from zerotrace.collectors.staged_diff import Unit, classify_file
from zerotrace.config import Config
from zerotrace.detectors import code_assign, pii, rulepack, sensitive_files
from zerotrace.pipeline import postprocess

from .conftest import Fake, rand


def _unit(path: str, text: str) -> Unit:
    return Unit(path=path, file_class=classify_file(path), line_no=1, text=text, window=text)


def _scan(path: str, text: str):
    u = [_unit(path, text)]
    cfg = Config()
    return postprocess(rulepack.scan(u, cfg) + code_assign.scan(u, cfg) + pii.scan(u, cfg), cfg)


# --- provider rule pack -------------------------------------------------------------

@pytest.mark.parametrize("make, rule", [
    (Fake.aws_key_id, "aws-access-key-id"),
    (Fake.stripe_live, "stripe-live-key"),
    (Fake.github, "github-token"),
    (Fake.openai, "openai-api-key"),
    (Fake.anthropic, "anthropic-api-key"),
    (Fake.google, "google-api-key"),
    (Fake.slack, "slack-token"),
])
def test_provider_tokens_block_anywhere_in_code(make, rule):
    token = make()
    for path, line in [("app.py", f'client = Client("{token}")'),
                       ("src/x.js", f"// old key {token}"),
                       ("notebook.ipynb", f'    "api = \\"{token}\\"\\n",')]:
        rules = {f.rule_id: f for f in _scan(path, line)}
        assert rule in rules, (path, line)
        assert rules[rule].severity in ("critical", "high")
        assert rules[rule].matched_value == token


def test_connection_string_with_password():
    line = f'DB = "postgres://svc:{rand(14)}@db.internal:5432/app"'
    (f,) = _scan("db.py", line)
    assert f.rule_id == "connection-string-with-password" and f.severity == "high"


def test_connection_string_placeholder_password_is_ignored():
    assert _scan("db.py", 'DB = "postgres://svc:${DB_PASSWORD}@db.internal/app"') == []
    assert _scan("db.py", 'DB = "postgres://svc:<password>@db.internal/app"') == []


def test_aws_documentation_example_key_is_a_placeholder():
    assert not [f for f in _scan(".env", "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
                if f.rule_id == "aws-access-key-id"]


# --- hardcoded assignments across languages ------------------------------------------

@pytest.mark.parametrize("path, template", [
    ("app.py", 'API_KEY = "{v}"'),
    ("app.py", 'api_key: str = "{v}"'),
    ("app.py", 'client = Client(api_key="{v}")'),
    ("src/a.ts", 'const clientSecret = "{v}";'),
    ("src/a.js", 'headers = {{ "X-Api-Key": "{v}" }}'),
    ("main.go", 'apiToken := "{v}"'),
    ("Main.java", 'private static final String AUTH_TOKEN = "{v}";'),
    ("Program.cs", 'var accessToken = "{v}";'),
    ("svc.rb", "  ACCESS_TOKEN = '{v}'"),
    ("svc.php", "    $apiKey = '{v}';"),
    ("lib.rs", 'const API_KEY: &str = "{v}";'),
    ("main.tf", '  master_password = "{v}"'),
    ("config/app.yml", "  client_secret: {v}"),
    ("deploy/.env.prod", "WEBHOOK_SECRET={v}"),
    ("Dockerfile", "ENV API_TOKEN={v}"),
    ("app.properties", "spring.datasource.password={v}"),
])
def test_hardcoded_random_credentials_block(path, template):
    value = rand(20) + "9aZ"
    findings = _scan(path, template.format(v=value))
    assert findings, template
    assert findings[0].severity == "high"
    assert findings[0].source == "code_assign"


@pytest.mark.parametrize("line", [
    'password = os.environ["DB_PASSWORD"]',
    'api_key = os.getenv("API_KEY")',
    "const token = process.env.TOKEN;",
    'token = f"Bearer {token}"',
    'API_KEY = "your-api-key-here"',
    'password = "changeme"',
    'const passwordLabel = "Enter your password";',
    'PASSWORD_MIN_LENGTH = "12"',
    'token_url = "https://auth.example.test/oauth/token"',
    'error = t("errors.password.tooShort")',
    'secret_name = "prod/db/password"',
    'api_key = "${API_KEY}"',
    'password = "{{ vault_db_password }}"',
    'key_path = "/etc/ssl/private/server.key"',
])
def test_benign_assignments_are_not_flagged(line):
    assert _scan("app.py", line) == []


def test_medium_values_go_to_the_ai_tie_break():
    (f,) = _scan("app.py", 'session_secret = "k9s-dev-2024"')
    assert f.severity == "medium"


def test_test_paths_downgrade_heuristic_findings():
    value = rand(24) + "9aZ"
    (f,) = _scan("tests/test_client.py", f'api_key = "{value}"')
    assert f.severity == "medium"  # high in code, medium in a test fixture


def test_provider_token_in_test_file_still_blocks():
    token = Fake.stripe_live()
    findings = _scan("tests/test_pay.py", f'KEY = "{token}"')
    assert findings[0].rule_id == "stripe-live-key" and findings[0].severity == "critical"


def test_env_name_from_identifier():
    assert code_assign.env_name_of("clientSecret") == "CLIENT_SECRET"
    assert code_assign.env_name_of("spring.datasource.password") == "PASSWORD"
    assert code_assign.env_name_of("$apiKey") == "API_KEY"
    assert code_assign.env_name_of("APIKey") == "API_KEY"


# --- sensitive files ------------------------------------------------------------------

@pytest.mark.parametrize("path, content, expected", [
    (".env", "A=1", "high"),
    ("services/api/.env.production", "A=1", "high"),
    (".env.example", "A=", None),
    ("deploy/id_rsa", "x", "critical"),
    ("deploy/id_rsa.pub", "ssh-rsa AAAA", None),
    ("certs/server.pem", "-----BEGIN CERTIFICATE-----", None),
    ("certs/server.pem", "-----BEGIN " + "PRIVATE KEY-----", "critical"),
    ("infra/terraform.tfstate", "{}", "critical"),
    (".npmrc", "//registry.npmjs.org/:_auth" + "Token=abc123", "high"),
    (".npmrc", "//registry.npmjs.org/:_auth" + "Token=${NPM_TOKEN}", None),
    ("keys/release.jks", None, "critical"),
])
def test_sensitive_files(path, content, expected):
    hit = sensitive_files.match(path, content)
    assert (hit[0] if hit else None) == expected


# --- PII (values generated at run time so this file itself stays clean) ---------------

def _luhn_complete(prefix: str, length: int) -> str:
    body = prefix + rand(length - len(prefix) - 1, "0123456789")
    for d in "0123456789":
        if pii.luhn_valid(body + d):
            return body + d
    raise AssertionError


def _verhoeff_complete(body: str) -> str:
    for d in "0123456789":
        if pii.verhoeff_valid(body + d):
            return body + d
    raise AssertionError


def test_checksums():
    card = _luhn_complete("4539", 16)
    assert pii.luhn_valid(card)
    assert not pii.luhn_valid(card[:-1] + str((int(card[-1]) + 1) % 10))
    aadhaar = _verhoeff_complete("2" + rand(10, "0123456789"))
    assert pii.verhoeff_valid(aadhaar)
    assert not pii.verhoeff_valid(aadhaar[:-1] + str((int(aadhaar[-1]) + 1) % 10))
    assert pii.iban_valid("GB82" + " WEST 1234 5698 7654 32")  # the published example IBAN


def test_pii_findings():
    email = "jane.doe" + "@" + "bmwtechworks.in"
    rules = {f.rule_id for f in _scan("src/users.py", f'owner = "{email}"')}
    assert "pii_email_internal" in rules
    aadhaar = _verhoeff_complete("2" + rand(10, "0123456789"))
    pan = "ABC" + "PE" + "1234" + "F"
    spaced = f"{aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}"
    rules = {f.rule_id for f in _scan("src/kyc.py", f'pan = "{pan}"  # aadhaar {spaced}')}
    assert {"pii_pan_india", "pii_aadhaar"} <= rules
    card = _luhn_complete("4539", 16)
    assert "pii_payment_card" in {f.rule_id for f in _scan("src/p.py", f'card = "{card}"')}


def test_pii_non_person_emails_are_ignored():
    assert _scan("README.md", "git clone git@github.com:acme/repo.git") == []
    assert _scan("src/mail.py", 'sender = "noreply@acme.io"') == []
    assert _scan("db.py", 'DB = "mysql://root:${PW}@db.internal/app"') == []


def test_known_test_card_is_low_and_allowed():
    (f,) = _scan("tests/test_pay.py", 'card = "' + "4242" * 4 + '"')
    assert f.severity == "low"


def test_synthetic_replacements_never_retrigger():
    """[R] must converge: every synthetic value we write passes the scanner."""
    from zerotrace.remediation.proposer import _PII_SYNTHETIC
    for kind, value in _PII_SYNTHETIC.items():
        blocking = [f for f in _scan("src/app.py", f'x = "{value}"') if f.severity != "low"]
        assert blocking == [], (kind, value)


def test_prose_and_format_placeholders_are_not_secrets():
    assert _scan("app.py", '"password": "A password is required for this action.",') == []
    assert _scan("t.py", 'DB = f"postgres://svc:{pw}@db.internal/app"') == []


def test_stored_hashes_are_not_treated_as_secrets():
    digest = rand(40, "0123456789abcdef")
    assert _scan(".secrets.baseline", f'    "hashed_secret": "{digest}",') == []
    assert _scan("app.py", f'password_digest = "{digest}"') == []
    assert _scan("lock.json", f'  "integrity": "{digest}"') == []
    # ...but the same shape bound to a live credential name still blocks.
    findings = _scan("app.py", f'api_key = "{digest}"')
    assert findings and findings[0].severity == "high"
