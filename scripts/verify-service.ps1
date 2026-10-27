$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Run .\scripts\setup-service.ps1 -Dev first.'
}

Push-Location $projectRoot
try {
    & $pythonExe -m pytest backend/tests cli/tests scripts/tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed. Install development dependencies with setup-service.ps1 -Dev if needed.' }
    & $pythonExe -m ruff check backend cli scripts/service.py scripts/tests
    if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        foreach ($npmScript in @('lint', 'typecheck', 'build')) {
            npm run $npmScript
            if ($LASTEXITCODE -ne 0) { throw "Frontend $npmScript failed." }
        }
    } finally { Pop-Location }
    Write-Host 'Automated verification passed. Tests do not send email or use a live MongoDB.'
} finally { Pop-Location }
