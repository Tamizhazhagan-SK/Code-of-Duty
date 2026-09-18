# Supported platforms

Versions below were verified against primary sources (Wikipedia release history pages,
cross-checked with vendor release notes where linked) on **2026-09-17**. Re-verify at
the next update rather than reusing this table unchanged — these will drift.

Floors: Python `>=3.11` (see `pyproject.toml`), git `>=2.9` (`core.hooksPath`'s
introduction).

## macOS

| Release | Version | Released | Notes |
|---|---|---|---|
| Golden Gate (current) | 27 | 2026-09-14 | **Apple Silicon only** — drops Intel entirely. Last release with full Rosetta 2. |
| Tahoe (current − 1) | 26 | 2025-09-15 | Last release with Intel support. Verify Intel-Mac support against this release, not Golden Gate. |

Never depend on a system Python — `python3` may be only a Command Line Tools stub;
Homebrew Python (or the standalone binary) is the real dependency.

## Windows

| Release | Released | Notes |
|---|---|---|
| 11, version 25H2 (current) | 2025-09-30 | Ships as an enablement package on the 24H2 servicing branch. |
| 11, version 24H2 (current − 1) | 2024-10-01 | First version to require an x86-64-v2 CPU (POPCNT + SSE4.2) at the kernel level — it will not boot otherwise. |

Version 26H1 (2026-02-10) is an ARM64-only platform release, not a general floor.
Version 26H2 was not yet GA as of 2026-09-17. Git for Windows is required (its
bundled `sh.exe` is what runs the POSIX hook shims); a bare `git.exe` without it is
not a supported target.

## Linux

| Distro | Current | Current − 1 | Notes |
|---|---|---|---|
| Ubuntu | 26.04 LTS "Resolute Raccoon" (2026-04-23) | 24.04 LTS (2024-04-25) | 26.10 not GA yet. |
| Debian | 13 "Trixie" (2025-08-09) | 12 "Bookworm" (oldstable) | |
| Fedora | 44 (2026-04-28) | 43 (2025-10-28) | |
| Arch | rolling | n/a | Always "current" by definition. |
| openSUSE | Leap 16 (2025-10-01) | Leap 15.6 | Leap 16 replaced YaST with Agama/Cockpit/Myrlyn. |

PEP 668 (externally-managed environments) is standard on all of the above as of
these releases: `pipx`/`uv tool install`/the standalone binary are the documented
install path; a bare `pip install` is expected to refuse.

### Immutable / atomic distros

Fedora Atomic Desktops (Silverblue = GNOME, Kinoite = KDE; versioned with Fedora),
openSUSE Aeon/Kalpa (Tumbleweed-based, rolling), NixOS (26.05 stable / rolling
unstable), and SteamOS 3.x (Arch-based, e.g. 3.8.16) all have a read-only `/usr`.
Install must land under `~/.local` or `~/.zerotrace` and never touch a system path.
NixOS additionally has no FHS, so a prebuilt glibc-linked binary will not run
unmodified there without `nix-ld`; a proper `flake.nix` packaging is tracked as
separate, not-yet-scoped work.

### musl / Alpine

Best-effort only. The standalone binary is glibc-linked; `pipx`/`pip` is the real
answer on Alpine when a Python interpreter is present.

## WSL

Treated as its own install target, not as Windows: Git for Windows and each WSL
distro run separate git installs with separate global config, so `zerotrace install`
must be run once **in each environment** that will commit. See
`docs/DEPLOYMENT.md` for the detection and bootstrap design.

## Uninstall

The installer removes what it installed, in the order that keeps a machine consistent: git
hooks first (so no repo points at a binary that is about to vanish), then the package, the
PATH entry and `~/.zerotrace`. Repos, history and files are never touched.

```bash
./install.sh --uninstall            # macOS / Linux (also: curl … | bash -s -- --uninstall)
pwsh -File .\install.ps1 -Uninstall # Windows
```

Re-installing is the same one line as a first install, so install/uninstall cycles are a
reasonable way to test a machine. After each cycle:

```bash
zerotrace doctor      # is this repo actually protected? which hooks path won?
git config --global core.hooksPath   # empty after an uninstall
```

## Checking the terminal you will demo from

Consoles differ in what they can draw. `zerotrace ui` renders every screen — logo, findings
report, fix preview, progress bar, panels and status glyphs — through the same code paths the
real commands use:

```bash
zerotrace ui                 # auto-detect this console
zerotrace ui --tier ascii    # what a legacy cmd.exe / cp437 console sees
zerotrace ui --tier all      # every tier in one pass
```

What ZeroTrace does automatically:

| Console | Behaviour |
|---|---|
| Windows Terminal, iTerm2, GNOME Terminal, VS Code, JetBrains | shaded Unicode mark, colour, rounded box borders |
| Kitty, WezTerm, iTerm2 | inline PNG logo via the terminal's image protocol |
| legacy `cmd.exe`, PowerShell 5.1 (cp437/cp1252) | ASCII mark, ASCII box borders, `+`/`x` instead of `✓`/`✗` |
| redirected output, CI logs, `NO_COLOR` | no colour, no image escapes, no in-place redraw |
| narrow terminals (< 60 columns) | smaller mark, then wordmark only |

If something still looks wrong, `zerotrace ui` prints the detected capabilities (encoding,
colour system, size, relevant environment variables) — include that output in a bug report.
