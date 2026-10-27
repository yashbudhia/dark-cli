param(
    [switch]$Production,
    [switch]$AllowUnconfigured,
    [int]$FrontendPort = 0,
    [int]$BackendPort = 0
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Run .\scripts\setup-service.ps1 first.'
}
$serviceArguments = @((Join-Path $PSScriptRoot 'service.py'), 'start')
if ($FrontendPort -ne 0) { $serviceArguments += @('--frontend-port', "$FrontendPort") }
if ($Production) { $serviceArguments += '--production' }
if ($AllowUnconfigured) { $serviceArguments += '--allow-unconfigured' }
if ($BackendPort -ne 0) { $serviceArguments += @('--backend-port', "$BackendPort") }
& $pythonExe @serviceArguments
exit $LASTEXITCODE
