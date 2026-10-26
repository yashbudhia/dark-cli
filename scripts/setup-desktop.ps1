# Install a pinned Windows MCP binary into this checkout, with SHA-256 verification.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$darkRoot = Split-Path -Parent $PSScriptRoot
$darkVersion = '1.3.28'
$darkAsset = "windows-mcp-server-$darkVersion-win-x64.zip"
$darkExpectedHash = '9ca69685222d3c4934680218b4a2b3b7ae5bd0c8d2ce8bc2220925f4bd924fe4'
$darkToolDir = Join-Path $darkRoot ".tools\windows-mcp-v$darkVersion"
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'This setup script pins the Windows x64 build. Set DARK_WINDOWS_MCP_PATH for another architecture.'
}
New-Item -ItemType Directory -Path $darkToolDir -Force | Out-Null
$darkZip = Join-Path $darkToolDir $darkAsset
if (-not (Test-Path -LiteralPath $darkZip)) {
    Invoke-WebRequest -Uri "https://github.com/sbroenne/mcp-windows/releases/download/v$darkVersion/$darkAsset" -OutFile $darkZip
}
$darkActualHash = (Get-FileHash -LiteralPath $darkZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($darkActualHash -ne $darkExpectedHash) { throw 'Windows MCP download failed SHA-256 verification.' }
$darkServerDir = Join-Path $darkToolDir 'server'
Expand-Archive -LiteralPath $darkZip -DestinationPath $darkServerDir -Force
Write-Output "Desktop server ready: $(Join-Path $darkServerDir 'Sbroenne.WindowsMcp.exe')"
Write-Output 'Next: .\.venv\Scripts\dark.exe desktop doctor'
