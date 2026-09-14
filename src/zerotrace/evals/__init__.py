"""`zerotrace eval`: measure the AI tie-break on labelled synthetic cases.

Values are generated at run time, so the repo holds no realistic-looking secrets.
Labels: real (must not be allowed), placeholder / fixture (ideally allowed).
"""
import json
import os
import secrets
import statistics
import string
import time
from dataclasses import replace
from importlib import resources

from rich.console import Console
from rich.table import Table

from ..config import load_config
from ..detectors import Finding
from ..collectors.staged_diff import classify_file

_WORDS = ["blue", "falcon", "river", "stone", "maple", "orbit", "cedar", "lunar", "quartz"]


def _gen(spec: str) -> str:
    kind, _, arg = spec.partition(":")
    if kind == "lit":
        return arg
    n = int(arg)
    alphabet = {
        "base62": string.ascii_letters + string.digits,
        "hex": "0123456789abcdef",
        "b64": string.ascii_letters + string.digits + "+/",
        "digits": string.digits,
    }.get(kind)
    if alphabet:
        return "".join(secrets.choice(alphabet) for _ in range(n))
    if kind == "pw":
        core = [secrets.choice(string.ascii_lowercase), secrets.choice(string.ascii_uppercase),
                secrets.choice(string.digits), secrets.choice("!@#%^*-_")]
        core += [secrets.choice(string.ascii_letters + string.digits + "!@#%^*-_")
                 for _ in range(n - 4)]
        secrets.SystemRandom().shuffle(core)
        return "".join(core)
    if kind == "words":
        return "-".join(secrets.choice(_WORDS) for _ in range(n))
    raise ValueError(f"unknown generator {spec}")


def load_cases(path: str | None) -> list[dict]:
    if path:
        resolved = os.path.realpath(os.path.expanduser(path))
        if not os.path.isfile(resolved):
            raise SystemExit(f"zerotrace eval: no such cases file: {path}")
        with open(resolved, encoding="utf-8") as f:
            text = f.read()
    else:
        text = resources.files("zerotrace.evals").joinpath("classifier_cases.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _finding(case: dict) -> Finding:
    value = _gen(case["gen"])
    text = case["line"].replace("{v}", value)
    line = text.splitlines()[-1]
    return Finding(
        rule_id="hardcoded-secret", kind="hardcoded_secret", severity="medium", confidence=0.6,
        path=case["path"], line_no=1, file_class=classify_file(case["path"]), line_text=line,
        context_snippet=text, identifier=case.get("identifier", ""), source="code_assign",
        matched_value=value,
    )


def run_eval(cases_path: str | None, models: list[str], runs: int = 1) -> int:
    from ..classifier import llm
    console = Console()
    base = load_config()
    cases = load_cases(cases_path)
    models = models or [base.model_name]
    table = Table(title=f"AI tie-break eval · {len(cases)} cases × {runs} run(s)")
    for col in ("model", "unsafe allows (real→allow)", "escalated real→block",
                "noise removed (placeholder/fixture→allow)", "no verdict", "p50 ms", "p95 ms"):
        table.add_column(col, justify="right" if col != "model" else "left")
    worst = 0
    for model in models:
        cfg = replace(base, model_name=model)
        warm = llm.warm(cfg)
        if warm is None:
            table.add_row(model, "-", "-", "-", "unreachable", "-", "-")
            continue
        real = benign = unsafe = escalated = allowed_benign = failed = 0
        latencies: list[float] = []
        misses: list[str] = []
        for _ in range(runs):
            for case in cases:
                finding = _finding(case)
                start = time.monotonic()
                verdict = llm.classify(finding, cfg)
                latencies.append((time.monotonic() - start) * 1000)
                is_real = case["label"] == "real"
                real += is_real
                benign += not is_real
                if verdict is None:
                    failed += 1
                    continue
                allow = verdict.classification == "TEST_FIXTURE_OR_PLACEHOLDER" and \
                    verdict.confidence >= cfg.model_allow_threshold
                block = verdict.classification == "REAL_SECRET" and \
                    verdict.confidence >= cfg.model_escalate_threshold
                if is_real and allow:
                    unsafe += 1
                    misses.append(f"{case['id']}: {verdict.reason}")
                if is_real and block:
                    escalated += 1
                if not is_real and allow:
                    allowed_benign += 1
        p50 = statistics.median(latencies) if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0
        worst = max(worst, unsafe)
        table.add_row(model, f"{unsafe}/{real}", f"{escalated}/{real}",
                      f"{allowed_benign}/{benign}", str(failed), f"{p50:.0f}", f"{p95:.0f}")
        for miss in misses:
            console.print(f"[red]unsafe allow[/] {model}: {miss}")
    console.print(table)
    console.print("[dim]Unsafe allows are the metric that matters: a MEDIUM finding the model "
                  "let through that was actually real. HIGH findings never reach the model.[/]")
    return 1 if worst else 0


__all__ = ["run_eval", "load_cases"]
