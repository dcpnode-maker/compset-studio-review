$ErrorActionPreference = 'Stop'
$appRoot = 'E:\YellowWorkspace\CompSetStudio'
$controlRoot = Join-Path $appRoot 'data\collection-control'
$pythonPath = Join-Path $appRoot '.venv\Scripts\python.exe'
# The Python watcher holds its own exclusive OS lock and checks exact collector identity.
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-B','-m','compset.collection_control') -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $controlRoot 'watcher.stdout.log') -RedirectStandardError (Join-Path $controlRoot 'watcher.stderr.log')
$receipt = [ordered]@{launcher_pid=$process.Id;launcher_start_utc_ticks=$process.StartTime.ToUniversalTime().Ticks;started_at=[DateTime]::UtcNow.ToString('o')}
$receiptPath = Join-Path $controlRoot 'WATCHER-PROCESS.json'
$receipt | ConvertTo-Json | Set-Content -LiteralPath ($receiptPath+'.tmp') -Encoding utf8
Move-Item -LiteralPath ($receiptPath+'.tmp') -Destination $receiptPath -Force
$process.WaitForExit()
exit $process.ExitCode
