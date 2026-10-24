param([string]$Iscc = "", [switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$pythonExe = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = "python" }
if (-not $SkipTests) {
    & $pythonExe -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}
& $pythonExe -m PyInstaller --noconfirm PLStudio.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
if (-not $Iscc) {
    $candidates = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "${env:ProgramFiles}\Inno Setup 7\ISCC.exe", ".build-tools\InnoSetup\ISCC.exe")
    $Iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw "Install Inno Setup or provide -Iscc with the path to ISCC.exe. The portable build is ready in dist\PL-Studio." }
$appVersion = & $pythonExe -c "from plstudio import __version__; print(__version__)"
& $Iscc "/DAppVersion=$appVersion" "installer\PLStudio.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed" }
Write-Host "Installer ready: release\PL-Studio-Setup.exe"
