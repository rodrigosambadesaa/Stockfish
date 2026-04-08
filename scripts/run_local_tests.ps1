param(
    [string]$MsysRoot = "C:\msys64",
    [switch]$SkipInstrumented
)

$ErrorActionPreference = "Stop"

$bash = Join-Path $MsysRoot "usr\bin\bash.exe"
if (-not (Test-Path $bash)) {
    throw "MSYS2 bash not found at $bash"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$script = @'
set -euo pipefail
export PATH=/ucrt64/bin:/usr/bin:$PATH
cd "__REPO_ROOT__/src"

# Required by tests/perft.sh and tests/reprosearch.sh
pacman -S --noconfirm --needed make expect >/dev/null

make -j4 build ARCH=x86-64 COMP=gcc
../tests/signature.sh
../tests/perft.sh
../tests/reprosearch.sh
'@

$msysRepoRoot = $repoRoot
if ($repoRoot -match '^([A-Za-z]):\\(.*)$') {
    $drive = $matches[1].ToLower()
    $tail = $matches[2] -replace '\\', '/'
    $msysRepoRoot = "/$drive/$tail"
}

$script = $script.Replace("__REPO_ROOT__", $msysRepoRoot)
& $bash -lc $script

if (-not $SkipInstrumented) {
    Push-Location (Join-Path $repoRoot "src")
    try {
        python ..\tests\instrumented.py --none .\stockfish.exe
    }
    finally {
        Pop-Location
    }
}

Write-Host "All local tests completed." -ForegroundColor Green
