param([int]$Port = 4175, [switch]$SkipAI)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$flavoPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $flavoPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $SkipAI) {
    & $flavoPython scripts/setup_ai.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $flavoPython scripts/build.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "FLAVO: http://127.0.0.1:$Port" -ForegroundColor Green
& $flavoPython serve.py --port $Port
