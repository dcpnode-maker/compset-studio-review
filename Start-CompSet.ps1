$ErrorActionPreference = 'Stop'
$taskCompSetRoot = $PSScriptRoot
$taskCompSetPython = Join-Path $taskCompSetRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskCompSetPython)) {
    throw 'Run Setup-CompSet.ps1 once to create the local Python environment.'
}
try {
    $taskCompSetResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 2
} catch {
    Start-Process -FilePath $taskCompSetPython -ArgumentList '-m','compset','serve' -WorkingDirectory $taskCompSetRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskCompSetRoot 'data\server.log') -RedirectStandardError (Join-Path $taskCompSetRoot 'data\server-error.log')
    Start-Sleep -Milliseconds 1200
}
Start-Process 'http://127.0.0.1:8765'
