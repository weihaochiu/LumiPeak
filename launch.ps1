param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$plPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $plPython)) {
    throw 'The project environment is missing. Run setup.ps1 first.'
}
$plScript = Join-Path $PSScriptRoot 'main.py'
$plArguments = @('"' + $plScript + '"')
if ($Demo) {
    $plDemoPath = Join-Path $PSScriptRoot 'examples\PL_reference_demo.plproj'
    if (-not (Test-Path -LiteralPath $plDemoPath)) {
        $plConsolePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        & $plConsolePython (Join-Path $PSScriptRoot 'tools\create_synthetic_demo.py')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the synthetic demo.' }
        $plDemoPath = Join-Path $PSScriptRoot 'examples\PL_synthetic_demo.plproj'
    }
    $plArguments += '"' + $plDemoPath + '"'
}
Start-Process -FilePath $plPython -ArgumentList $plArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
