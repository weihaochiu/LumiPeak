$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$plPython = $null
$plLocalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $plLocalPython) {
    $plPython = $plLocalPython
} else {
    $plCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    $plCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($plCommand -and $plCommand.Source -notmatch 'WindowsApps') {
        $plCandidates = @($plCommand.Source) + $plCandidates
    }
    foreach ($plCandidate in $plCandidates) {
        if (Test-Path -LiteralPath $plCandidate) { $plPython = $plCandidate; break }
    }
    if (-not $plPython) {
        $plLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($plLauncher) {
            $plDetected = & $plLauncher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $plDetected) { $plPython = [string]$plDetected }
        }
    }
    if (-not $plPython) { throw 'Python 3.11+ was not found. Install Python from python.org, then run setup.ps1 again.' }
    & $plPython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    $plPython = $plLocalPython
}
& $plPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and pip output.' }
Write-Host 'PL Studio is ready. Double-click START_PL.bat.'
