[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$darkRoot = Split-Path -Parent $PSScriptRoot
$darkFixtureDir = Join-Path $darkRoot '.tools\desktop-fixture'
New-Item -ItemType Directory -Path $darkFixtureDir -Force | Out-Null
$darkCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $darkCompiler)) { throw '.NET Framework C# compiler not found.' }
$darkFixture = Join-Path $darkFixtureDir 'DarkDesktopFixture.exe'
$darkExisting = Get-Process -Name DarkDesktopFixture -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $darkFixture }
if ($darkExisting) {
    Write-Output 'Dark Desktop Fixture is already running. Close it before rebuilding the fixture.'
    return
}
& $darkCompiler /nologo /target:winexe "/out:$darkFixture" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll (Join-Path $darkRoot 'examples\desktop\FixtureApp.cs')
if ($LASTEXITCODE -ne 0) { throw 'Fixture compilation failed.' }
# The visible window is the disposable desktop test target.
Start-Process -FilePath $darkFixture
Write-Output 'Opened Dark Desktop Fixture. It deliberately accepts negative quantities.'
