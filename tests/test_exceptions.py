"""Exceptions: two stores, expiry, promotion into the reviewable file, pruning."""
import json
import subprocess
import sys

from zerotrace.audit import exceptions

from .conftest import write


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fingerprint(name: str = "abc") -> str:
    return name * 8


def test_local_exception_silences_a_finding(repo):
    fp = _fingerprint()
    assert not exceptions.is_active(fp)
    path = exceptions.add(fp, "reviewed false positive", ttl_days=30)
    assert path.endswith("exceptions.json") and ".git" in path      # local by default
    assert exceptions.is_active(fp)


def test_shared_file_lives_in_the_repo_and_is_committable(repo):
    fp = _fingerprint("shared")
    path = exceptions.add(fp, "vendored sample key", ttl_days=30, shared=True)
    assert path.endswith(exceptions.SHARED_FILE)
    payload = _read_json(path)
    assert "note" in payload and fp in payload["exceptions"]
    assert exceptions.is_active(fp)
    assert "reviewed" in payload["note"].lower() or "review" in payload["note"].lower()


def test_expired_exceptions_stop_applying(repo):
    fp = _fingerprint("old")
    exceptions.add(fp, "temporary", ttl_days=-1)
    assert not exceptions.is_active(fp)


def test_malformed_entry_is_not_an_exception(repo):
    path = exceptions.shared_path()
    write(path, json.dumps({"exceptions": {_fingerprint("bad"): {"reason": "no expiry"}}}))
    assert not exceptions.is_active(_fingerprint("bad"))


def test_promote_moves_local_entries_into_the_reviewable_file(repo):
    live, expired = _fingerprint("live"), _fingerprint("dead")
    exceptions.add(live, "still needed", ttl_days=10)
    exceptions.add(expired, "stale", ttl_days=-1)

    moved, path = exceptions.promote()
    assert moved == 1 and path.endswith(exceptions.SHARED_FILE)
    shared = _read_json(path)["exceptions"]
    assert live in shared and expired not in shared
    assert exceptions.is_active(live)
    assert live not in exceptions._read(exceptions.local_path())   # no longer duplicated


def test_prune_drops_only_expired_entries(repo):
    exceptions.add(_fingerprint("keep"), "current", ttl_days=5)
    exceptions.add(_fingerprint("drop"), "over", ttl_days=-1, shared=True)
    assert exceptions.prune() == 1
    assert exceptions.is_active(_fingerprint("keep"))


def test_listing_reports_both_scopes(repo):
    exceptions.add(_fingerprint("l"), "local one", ttl_days=5)
    exceptions.add(_fingerprint("s"), "shared one", ttl_days=5, shared=True)
    scopes = {row["scope"] for row in exceptions.listing()}
    assert scopes == {"local", "shared"}


def test_exceptions_cli_lists_and_promotes(repo):
    exceptions.add(_fingerprint("cli"), "needs review", ttl_days=7)
    listed = subprocess.run([sys.executable, "-m", "zerotrace", "exceptions"],
                            capture_output=True, text=True)
    assert "needs review" in listed.stdout

    promoted = subprocess.run([sys.executable, "-m", "zerotrace", "exceptions", "--promote"],
                              capture_output=True, text=True)
    assert "moved 1" in promoted.stdout
    assert (repo / exceptions.SHARED_FILE).exists()


def test_a_shared_exception_actually_allows_the_commit(repo, fake):
    """End to end: fingerprint the finding, record it as reviewed, watch the block clear."""
    from zerotrace import pipeline
    from zerotrace.audit.fingerprint import of_finding
    from zerotrace.collectors.staged_diff import collect_staged
    from zerotrace.config import load_config

    write("pay.py", f'KEY = "{fake.stripe_live()}"\n')
    subprocess.run(["git", "add", "-A"], check=True)
    cfg = load_config()
    (decision,) = pipeline.scan(collect_staged(), cfg, use_model=False)
    assert decision.action == "block"

    exceptions.add(of_finding(decision.finding), "vendor sample, rotated", 30, shared=True)
    (after,) = pipeline.scan(collect_staged(), cfg, use_model=False)
    assert after.action == "allow" and "exception" in after.reason
