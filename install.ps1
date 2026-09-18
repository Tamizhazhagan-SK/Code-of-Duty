#requires -Version 5.1
<#
.SYNOPSIS
  ZeroTrace one-command bootstrap installer for Windows.

.DESCRIPTION
  Does NOT assume pip, pipx or uv is already installed. The only hard
  prerequisite is git (ZeroTrace is a git hook manager, so a machine
  without git has nothing for it to protect anyway). If Python itself is
  missing, this script makes a best-effort attempt to install it via
  winget (ships with modern Windows 10/11).

.EXAMPLE
  # install
  iwr https://raw.githubusercontent.com/Tamizhazhagan-SK/Code-of-Duty/main/install.ps1 -useb | iex

.EXAMPLE
  # uninstall (one line; the &{...} wrapper is how you pass a switch to a piped script)
  &([scriptblock]::Create((iwr https://raw.githubusercontent.com/Tamizhazhagan-SK/Code-of-Duty/main/install.ps1 -useb))) -Uninstall

.EXAMPLE
  # from a clone
  pwsh -File .\install.ps1              # install
  pwsh -File .\install.ps1 -Uninstall   # uninstall
#>
[CmdletBinding()]
param(
    [string]$RepoUrl = $(if ($env:ZEROTRACE_REPO_URL) { $env:ZEROTRACE_REPO_URL } else { "https://github.com/Tamizhazhagan-SK/Code-of-Duty.git" }),
    [string]$Ref = $(if ($env:ZEROTRACE_REF) { $env:ZEROTRACE_REF } else { "main" }),
    [string]$Extras = $(if ($env:ZEROTRACE_EXTRAS) { $env:ZEROTRACE_EXTRAS } else { "" }),
    [switch]$WithLlm,
    [switch]$WithPii,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
# Don't let a probed candidate's non-zero exit / stderr (e.g. "py -3.13" when
# only 3.11 is installed) turn into a terminating error on PS 7.3+.
$PSNativeCommandUseErrorActionPreference = $false
$PyMinMajor = 3
$PyMinMinor = 11

if ($WithLlm) { $Extras = if ($Extras) { "$Extras,llm" } else { "llm" } }
if ($WithPii) { $Extras = if ($Extras) { "$Extras,pii-ner" } else { "pii-ner" } }

function Write-Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "!! $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "ERROR $msg" -ForegroundColor Red; exit 1 }

function Remove-ZeroTrace($python) {
    # Hooks first, so no repo is left pointing at a binary that is about to disappear.
    $exe = (Get-Command zerotrace -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        $scripts = (Invoke-Py $python @("-c", "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))")) | Select-Object -Last 1
        $candidate = Join-Path $scripts "zerotrace.exe"
        if (Test-Path $candidate) { $exe = $candidate }
    }
    if ($exe) {
        Write-Info "Removing the global git hook..."
        try { & $exe uninstall --global } catch { Write-Warn "uninstall --global reported an issue." }
    } else {
        Write-Warn "zerotrace.exe not found; skipping hook removal. Check 'git config --global core.hooksPath'."
    }

    Write-Info "Uninstalling the package..."
    try { Invoke-Py $python @("-m", "pip", "uninstall", "--yes", "--quiet", "zerotrace") | Out-Null }
    catch { Write-Warn "pip uninstall reported an issue." }

    $home_ = Join-Path $env:USERPROFILE ".zerotrace"
    if (Test-Path $home_) { Write-Info "Removing $home_..."; Remove-Item -Recurse -Force $home_ }

    Write-Info "Uninstalled. Repos keep their history and files; only the hooks and the tool are gone."
    Write-Warn "The PATH entry this installer added is left in place; remove it from User PATH if you want it gone."
}

function Find-Python {
    $candidates = @(
        @("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3"),
        @("python3"), @("python")
    )
    foreach ($c in $candidates) {
        $exe = $c[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $verArg = if ($c.Length -gt 1) { $c[1] } else { $null }
        $checkArgs = @()
        if ($verArg) { $checkArgs += $verArg }
        $checkArgs += @("-c", "import sys; sys.exit(0 if sys.version_info >= ($PyMinMajor, $PyMinMinor) else 1)")
        try { & $exe @checkArgs 2>$null 1>$null } catch { continue }
        if ($LASTEXITCODE -eq 0) {
            if ($verArg) { return "$exe $verArg" } else { return $exe }
        }
    }
    return $null
}

function Invoke-Py([string]$pyCmd, [string[]]$pyArgs) {
    $parts = $pyCmd.Split(" ")
    & $parts[0] @($parts[1..($parts.Length - 1)] + $pyArgs)
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is required (ZeroTrace protects git repos) - install it first: https://git-scm.com/download/win"
}

$python = Find-Python
# Uninstalling must never trigger a Python *install*: handle it before the bootstrap below.
if ($Uninstall) {
    if (-not $python) { Fail "No Python found; nothing to uninstall (remove %USERPROFILE%\.zerotrace by hand)." }
    Remove-ZeroTrace $python
    exit 0
}
if (-not $python) {
    Write-Warn "No Python >= $PyMinMajor.$PyMinMinor found - attempting a best-effort install via winget."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Fail "winget not found. Install Python $PyMinMajor.$PyMinMinor+ manually from https://python.org, or install winget, then re-run this script. See docs/INSTALL.md."
    }
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    # winget updates the registered PATH but not this process; refresh from the machine+user env vars.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $python = Find-Python
    if (-not $python) { Fail "Python install attempted but no suitable interpreter was found afterwards. Open a new terminal and re-run this script." }
}
Write-Info "Using $python ($(Invoke-Py $python @('--version')))"

# ensurepip ships inside the stdlib of every CPython build, so this works
# even when pip/pipx were never installed on this machine.
try { Invoke-Py $python @("-m", "ensurepip", "--upgrade") | Out-Null } catch {}
try { Invoke-Py $python @("-m", "pip", "install", "--user", "--quiet", "--upgrade", "pip") | Out-Null } catch {}

$scriptDir = $PSScriptRoot
if ($scriptDir -and (Test-Path (Join-Path $scriptDir "pyproject.toml"))) {
    $srcDir = $scriptDir
} else {
    $srcDir = Join-Path $env:TEMP "zerotrace-src"
    if (Test-Path $srcDir) { Remove-Item -Recurse -Force $srcDir }
    Write-Info "Cloning $RepoUrl (ref: $Ref)..."
    git clone --depth 1 --branch $Ref $RepoUrl $srcDir
}

$packageSpec = $srcDir
if ($Extras) { $packageSpec = "$srcDir[$Extras]" }

Write-Info "Installing zerotrace (pip install --user)..."
Invoke-Py $python @("-m", "pip", "install", "--user", "--quiet", $packageSpec)

# On Windows, pip's user scheme nests scripts under a version-specific
# folder (e.g. %APPDATA%\Python\Python312\Scripts), unlike POSIX's flat
# {userbase}/bin - ask sysconfig directly instead of guessing the path.
$scriptsDir = (Invoke-Py $python @("-c", "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))")) | Select-Object -Last 1
$zerotraceExe = Join-Path $scriptsDir "zerotrace.exe"
if (-not (Test-Path $zerotraceExe)) { Fail "Install finished but $zerotraceExe was not found." }

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $scriptsDir) {
    [System.Environment]::SetEnvironmentVariable("Path", "$userPath;$scriptsDir", "User")
    Write-Warn "$scriptsDir was added to your User PATH - open a new terminal to pick it up."
}
$env:Path = "$env:Path;$scriptsDir"

Write-Info "Enabling the global git hook..."
try { & $zerotraceExe install --global } catch { Write-Warn "install --global reported an issue, see output above." }

Write-Info "Running doctor..."
try { & $zerotraceExe doctor } catch {}

Write-Info "Done. Open a new terminal so 'zerotrace' is on PATH."
