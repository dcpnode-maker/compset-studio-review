$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\Users\astha\CompSetStudio'

$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Run Setup-CompSet.ps1 first — $python not found." }

Write-Host "`n=== CompSet Studio: forced restart ===`n" -ForegroundColor Cyan

# 1. Kill whatever owns 8765
Write-Host '[1/4] Releasing port 8765...'
$owners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty OwningProcess -Unique
if ($owners) {
    foreach ($procId in $owners) {
        try {
            $p = Get-Process -Id $procId -ErrorAction Stop
            Write-Host ("      stopping PID {0} ({1})" -f $procId, $p.ProcessName)
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Host ("      could not stop PID {0}: {1}" -f $procId, $_.Exception.Message) -ForegroundColor Yellow
        }
    }
} else {
    Write-Host '      nothing was listening'
}
Start-Sleep -Seconds 2

if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8765 is still busy after kill. Close the app holding it, then rerun.'
}
Write-Host '      port is free' -ForegroundColor Green

# 2. Start the new server in a visible window (so you can see logs / Ctrl+C)
Write-Host '[2/4] Starting server in a new window...'
$serveArgs = @('-NoExit','-NoProfile','-Command',"& '$python' -m compset serve")
Start-Process -FilePath 'powershell.exe' -ArgumentList $serveArgs -WorkingDirectory (Get-Location) | Out-Null

# 3. Wait for /api/workspace to come up (this is the route the old server 404'd on)
Write-Host '[3/4] Waiting for new routes (up to 30s)...'
$deadline = (Get-Date).AddSeconds(30)
$up = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 750
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:8765/api/workspace' -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch { }
}
if (-not $up) {
    Write-Host '      FAILED — check the server window for a traceback.' -ForegroundColor Red
    exit 1
}
Write-Host '      new routes are live' -ForegroundColor Green

# 4. Verify every route the old process was missing
Write-Host "`n[4/4] Verification:"
foreach ($path in @(
    '/api/status',
    '/api/workspace',
    '/api/intelligence',
    '/api/intelligence/hotel',
    '/dual-workspace.js',
    '/dual-workspace.css',
    '/rates-workspace.js',
    '/rates-workspace.css'
)) {
    try {
        $r = Invoke-WebRequest ("http://127.0.0.1:8765$path") -UseBasicParsing -TimeoutSec 5
        Write-Host ("      {0,-28} {1}" -f $path, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("      {0,-28} {1}" -f $path, $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host "`nDone. Hard-reload the browser (Ctrl+Shift+R) at http://127.0.0.1:8765.`n" -ForegroundColor Cyan