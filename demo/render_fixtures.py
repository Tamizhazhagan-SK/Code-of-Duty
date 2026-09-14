"""Render a demo repo from demo/fixtures/<name>, generating format-valid FAKE credentials.

Used by both run_demo.sh and run_demo.ps1 so the two demos can never drift apart, and so
this repository never contains a realistic-looking secret itself.

    python demo/render_fixtures.py payments-api /tmp/zerotrace-demo/payments-api [--fresh]
"""
import os
import re
import secrets
import shutil
import string
import sys

ALNUM = string.ascii_letters + string.digits
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _r(n: int, alphabet: str = ALNUM) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _password() -> str:
    return _r(4, string.ascii_uppercase) + _r(6) + secrets.choice("!#%*") + _r(5, string.digits)


GENERATORS = {
    "stripe_live": lambda: "sk" + "_live_" + _r(24),
    "openai": lambda: "sk-" + "proj-" + _r(48),
    "github": lambda: "gh" + "p_" + _r(36),
    "aws_key_id": lambda: "AK" + "IA" + _r(16, "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
    "password": _password,
    "internal_email": lambda: "priya.sharma" + "@" + "bmwtechworks.in",
    "qxid": lambda: "QX" + _r(5, string.ascii_uppercase + string.digits),
}


def _gen(spec: str) -> str:
    kind, _, arg = spec.partition(":")
    if kind in GENERATORS:
        return GENERATORS[kind]()
    if kind == "base62":
        return _r(int(arg))
    if kind == "base64":
        return _r(int(arg), ALNUM + "+/")
    raise SystemExit(f"unknown generator {spec}")


def render(name: str, dest: str) -> None:
    src = os.path.join(FIXTURES, name)
    if not os.path.isdir(src):
        raise SystemExit(f"no fixture set {name!r} in {FIXTURES}")
    for root, _dirs, files in os.walk(src):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), src)
            target = os.path.join(dest, rel.replace("dot.env", ".env"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(os.path.join(root, fname), encoding="utf-8") as f:
                text = f.read()
            text = re.sub(r"\{\{gen:([a-z_0-9:]+)\}\}", lambda m: _gen(m.group(1)), text)
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--fresh"]
    if len(args) != 2:
        raise SystemExit(__doc__)
    if "--fresh" in sys.argv:
        shutil.rmtree(args[1], ignore_errors=True)
    render(args[0], args[1])
