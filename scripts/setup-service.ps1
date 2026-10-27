param([switch]$Dev)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'

foreach ($commandName in @('uv', 'npm', 'node')) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Install $commandName and run setup-service.ps1 again."
    }
}

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        uv venv .venv --python 3.11
        if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed.' }
    }
    $backendPackage = if ($Dev) { './backend[dev]' } else { './backend' }
    $cliPackage = if ($Dev) { './cli[dev]' } else { './cli' }
    uv pip install --python $pythonExe -e $backendPackage -e $cliPackage
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    } finally { Pop-Location }

    & $pythonExe scripts/service.py init
    if ($LASTEXITCODE -ne 0) { throw 'Service configuration initialization failed.' }
    Write-Host 'Next: fill the missing values in .env, then run .\scripts\start-service.ps1.'
} finally { Pop-Location }
