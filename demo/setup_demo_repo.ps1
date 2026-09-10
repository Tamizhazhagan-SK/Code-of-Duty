#!/usr/bin/env pwsh
<#
Builds a throwaway demo repo (outside OneDrive/this workspace) with an installed
ZeroTrace pre-commit hook, stages a few fixtures, and attempts a real `git commit`
so you can show it being blocked/warned/remediated live.

Run this from an actual interactive PowerShell terminal (not a redirected/piped
one) so the TUI's [R/V/E/A] prompts work.
#>
param(
    [string]$DemoDir = (Join-Path $env:TEMP "zerotrace-demo")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ZeroTraceExe = Join-Path $RepoRoot ".venv\Scripts\zerotrace.exe"
$PreCommitExe = Join-Path $RepoRoot ".venv\Scripts\pre-commit.exe"

if (-not (Test-Path $ZeroTraceExe)) {
    throw "zerotrace.exe not found at $ZeroTraceExe - run: pip install -e `".[dev,llm]`" in $RepoRoot\.venv first."
}

Write-Host "==> Rebuilding demo repo at $DemoDir" -ForegroundColor Cyan
if (Test-Path $DemoDir) {
    Get-ChildItem -Path $DemoDir -Recurse -Force | ForEach-Object { $_.Attributes = "Normal" }
    Remove-Item -Recurse -Force $DemoDir
}
New-Item -ItemType Directory -Path $DemoDir | Out-Null
Set-Location $DemoDir

git init -q
git config user.email "demo@example.test"
git config user.name "ZeroTrace Demo"

# Local hook: run the already-installed zerotrace binary directly (language:
# system so pre-commit does not try to create its own venv for this demo).
# Wrapped in literal double quotes (inside a single-quoted YAML scalar) so a
# repo root path containing spaces still parses as one command.
$zerotraceEntry = $ZeroTraceExe.Replace('\', '/')
$entryValue = "'`"$zerotraceEntry`" run'"
@"
repos:
  - repo: local
    hooks:
      - id: zerotrace
        name: ZeroTrace secret & PII sanitizer
        entry: $entryValue
        language: system
        pass_filenames: false
        always_run: true
"@ | Set-Content -Path ".pre-commit-config.yaml" -Encoding utf8

& $PreCommitExe install --config .pre-commit-config.yaml | Out-Null
Write-Host "==> pre-commit hook installed" -ForegroundColor Green

Copy-Item (Join-Path $RepoRoot ".zerotrace.yml") ".zerotrace.yml"

New-Item -ItemType Directory -Path "config" -Force | Out-Null
New-Item -ItemType Directory -Path "tests" -Force | Out-Null
New-Item -ItemType Directory -Path "src" -Force | Out-Null

# 1) HIGH severity secret -> deterministic block.
Set-Content -Path ".env" -Value "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE" -NoNewline
Add-Content -Path ".env" -Value ""

# 2) MEDIUM/ambiguous high-entropy token, no keyword context -> live Qwen tie-break.
Set-Content -Path "config/app.yml" -Value "token: zx8Qw3mPz9LrTq2VnBk7Ys5Fh1Cd0Ea4G" -NoNewline
Add-Content -Path "config/app.yml" -Value ""

# 3) HIGH severity internal PII (company email + internal QXID) in a test fixture.
@"
{
  "customer_email": "jane.doe@bmwtechworks.in",
  "employee_id": "QXZ7HDG",
  "note": "synthetic test fixture, not a real person"
}
"@ | Set-Content -Path "tests/customer_fixture.json" -Encoding utf8

# 4) Clean file -> control case, no findings.
@"
def format_notification(user_name: str, message: str) -> str:
    return f"{user_name}: {message}"
"@ | Set-Content -Path "src/notification.py" -Encoding utf8

git add -A
Write-Host "`n==> Staged files:" -ForegroundColor Cyan
git diff --cached --stat

Write-Host "`n==> Warming up the local Qwen model (first call loads it into RAM)..." -ForegroundColor Cyan
try {
    docker exec zerotrace-ollama ollama run qwen2.5-coder:3b-instruct-q4_K_M "ready" | Out-Null
} catch {
    Write-Host "    (docker/ollama not reachable - the MEDIUM finding below will fail closed to WARN)" -ForegroundColor Yellow
}

Write-Host "`n==> Attempting commit (this is where ZeroTrace steps in)...`n" -ForegroundColor Cyan
git commit -m "Add notification configuration"
