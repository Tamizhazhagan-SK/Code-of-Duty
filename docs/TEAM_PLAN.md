# Team plan: finishing ZeroTrace

Two of us, one codebase. This splits the remaining work so we never edit the same files at the
same time, and it says exactly what "done" means for each task.

- **Track A (engine & product)** — owner: Tamizh
- **Track B (validation, packaging & story)** — owner: teammate

Everything in `src/` that is listed below as Track A stays with Track A. Track B owns the model
measurements, Windows, packaging and the pitch. Where Track B needs an engine change, open an
issue or a PR rather than editing Track A's files directly.

## 0. Both of us, before anything else (15 minutes)

```bash
git pull
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"     # Windows: .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q          # expect: all tests pass
.venv/bin/zerotrace doctor
docker compose -f docker/docker-compose.yml up -d              # pulls Qwen2.5-Coder 3B once (~2 GB)
./demo/run_demo.sh --auto                                      # Windows: pwsh -File .\demo\run_demo.ps1 -Auto
```

Read, in this order: `README.md` → `docs/ARCHITECTURE.md` → `docs/AI_CLASSIFIER.md` →
`docs/DEPLOYMENT.md`. That is about 15 minutes of reading and covers the whole system.

**Working agreement**
- Branch per task: `feat/<short-name>`, `docs/<short-name>`, `fix/<short-name>`. PR into `main`.
- Commit style: short lowercase `type: subject`, no body (`feat:`, `fix:`, `docs:`, `test:`,
  `chore:`).
- Never commit a realistic-looking secret or real PII, not even in tests or fixtures. Build fake
  values at run time (`tests/conftest.py::Fake`, `demo/render_fixtures.py`).
- Before pushing: `pytest -q`, `ruff check src tests demo`, `mypy src`.
- Ping the other person before touching `src/zerotrace/policy/engine.py` or
  `src/zerotrace/classifier/` — those carry the security invariants.

---

## Track B: teammate's tasks, in priority order

### B1. Measure the AI tie-break with the real model  ⏱ ~2 h  🔴 highest value
Right now the AI path has been tested only against a fake model server. We have no real numbers,
and numbers are what make the demo credible.

```bash
docker compose -f docker/docker-compose.yml up -d
.venv/bin/zerotrace doctor --warm
.venv/bin/zerotrace eval                                     # 36 labelled cases, values generated at run time
.venv/bin/zerotrace eval --model qwen2.5-coder:1.5b-instruct --model qwen2.5-coder:3b-instruct-q4_K_M
.venv/bin/zerotrace eval --runs 3                            # stability across runs
```

**Done when:** a results table (unsafe allows, escalations, noise removed, no-verdict count,
p50/p95 latency per model) is pasted into `docs/AI_CLASSIFIER.md` under a new "Measured results"
heading, with the machine and model quantisation noted. If the unsafe-allow count is not 0, list
the failing case ids in the doc and tell Tamizh: thresholds
(`model.allow_threshold` / `escalate_threshold` in `.zerotrace.yml`) may need tuning.

**Stretch:** add 10–15 cases to `src/zerotrace/evals/classifier_cases.jsonl` from our own
languages and frameworks (label `real`, `placeholder` or `fixture`, and use the `gen:` helpers so
no literal secret is stored).

### B2. Windows dress rehearsal  ⏱ ~1.5 h  🔴 needed for the live demo
The Windows script has never been run. The company laptop is the likely demo machine.

```powershell
pwsh -File .\demo\run_demo.ps1            # interactive, in Windows Terminal (not a redirected shell)
```

Check each of these and note what happens:
1. Does `zerotrace install --global` work, and does `git config --global core.hooksPath` show the
   sandbox path (your real config must stay untouched)?
2. Does the commit get blocked in both demo repos?
3. **Does the `[V/R/U/E/A]` menu appear inside `git commit`?** Git for Windows may not give the
   hook a terminal. If it doesn't, the script falls back to `zerotrace review`, which is fine, but
   we need to know which one to show on stage.
4. Does the `--no-verify` push get blocked?
5. Do the paths survive the OneDrive folder with spaces in its name?

**Done when:** `docs/DEMO_RUNBOOK.md` (new file, yours) records the exact click-by-click demo
flow for Windows, plus anything that broke. File bugs as issues; small script fixes go straight
into `demo/run_demo.ps1` (that file is yours from now on).

### B3. Demo runbook and pitch  ⏱ ~3 h  🟠
The story, not the code. **Read `docs/RESEARCH.md` first** — it has the market numbers, the
"we already have a vault" rebuttal, and the ten scenarios mapped to our fixtures. Build it around the four beats the use-case document promises: detect →
explain → sanitize → prevent.

Suggested structure for `docs/DEMO_RUNBOOK.md` + slides:
1. **The problem** (30 s): a leaked key costs rotation, investigation, history rewriting. CI finds
   it after the code is already shared.
2. **One install, every repo** (60 s): `zerotrace install --global`, then two unrelated repos are
   protected. This is the differentiator, so say it early.
3. **Hardcoded secrets anywhere** (90 s): Stripe key in Python, DB URL with a password, Dockerfile
   `ENV`, Terraform password, `.env`, PII in a test fixture. Blocked in ~100 ms.
4. **The AI part, bounded** (60 s): ambiguous token → local model; show the redacted feature block
   (`docs/AI_CLASSIFIER.md`) and say plainly "the model never sees the value, and it can never
   unblock a high-confidence secret". Show the prompt-injection comment being ignored.
5. **Fix, don't just fail** (60 s): `[V]` rewrites to `os.environ[...]`, `[U]` unstages `.env` and
   writes `.env.example`.
6. **It survives bypasses** (30 s): `--no-verify` → pre-push block → CI backstop.
7. **Scale** (45 s): `docs/DEPLOYMENT.md` (MDM, locked org policy) and `docs/AWS_INFERENCE.md`.
8. **Honesty slide** (20 s): a client hook is advisory, a 3B model is not a security boundary,
   and here are our measured numbers from B1.

**Done when:** the runbook has exact commands and expected output per beat, a timing plan under
the pitch limit, and a fallback plan (pre-recorded terminal capture, e.g. `asciinema`, in case
Docker or the network misbehaves on the day).

### B4. Enterprise packaging (P5)  ⏱ ~3 h  🟡 nice to have, strong for judging
Pick these up in order; each is independent.
1. `.github/workflows/release.yml`: build single-file binaries with PyInstaller for
   macOS/Linux/Windows on tag push, and attach them to the release. Acceptance: the artifact runs
   `zerotrace --help` and `zerotrace doctor` on a machine with no Python.
2. Restructure `bmw-skills-marketplace/` into the `.claude-plugin/` layout
   (`marketplace.json` + `plugin.json`) pointing at `skill/`. Acceptance: documented install steps
   in the README.
3. A real egress-deny CI job replacing the `echo` stub in `.github/workflows/ci.yml`: run the test
   suite with networking disabled (`unshare -rn` on Linux runners) and fail on any outbound socket.
4. A sample org rollout kit: `deploy/policy.example.yml` (locked keys) plus an Intune/Jamf snippet
   that installs the tool and runs `zerotrace install --system`. Base it on `docs/DEPLOYMENT.md` §3.

### B5. Adversarial testing  ⏱ ~1 h  🟡
Try to get a secret past ZeroTrace and write up what works: base64-encoded keys, values split
across concatenation, secrets in `.ipynb` outputs, minified JS, unusual languages, a huge diff.
**Done when:** findings are listed in `docs/THREAT_MODEL.md` under "Known gaps", with the easy
ones turned into rule-pack additions (`src/zerotrace/detectors/rules/default.yml`) plus tests.

---

## Track A: Tamizh's tasks

- **A1.** Act on B1's numbers: tune thresholds, prompt or few-shot examples in
  `src/zerotrace/classifier/`.
- **A2.** Fix whatever B2 finds on Windows in `src/zerotrace/installer.py` (hook shims, TTY
  detection, paths with spaces).
- **A3.** Rule-pack and detector additions coming out of B5, each with a true-positive and a
  placeholder-negative test.
- **A4.** Exceptions as a committed, PR-reviewed file, and opt-in fleet metrics
  (counts and fingerprints only) — `docs/DEPLOYMENT.md` §7.
- **A5.** AWS inference endpoint when Cloud Room access arrives (`docs/AWS_INFERENCE.md`).
  Client-side it is config only.

---

## Shared, before submission

| Item | Owner | Done when |
|---|---|---|
| `LICENSE` is still a placeholder; confirm IP ownership with BMW TechWorks before publishing anywhere public | Tamizh | a real licence file, or an explicit internal-only note |
| `SECURITY.md` disclosure email is `security@<org>.example` | teammate | a real contact |
| `CHANGELOG.md` entry for the final version | Tamizh | tagged `v0.3.0` |
| Final `pytest`, `ruff`, `mypy`, and both demo scripts run clean | both | green on both machines |
| Repo scans clean under its own tool (dogfooding) | both | `zerotrace scan --all --no-model` reports nothing |

## If you have only one evening

Do **B1** and **B2**. Real model numbers and a rehearsed Windows demo are worth more than any
extra feature.
