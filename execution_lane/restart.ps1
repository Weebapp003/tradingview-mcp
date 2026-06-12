$py  = "C:\Users\drrat\AppData\Local\Programs\Python\Python311\python.exe"
$wd  = "C:\Users\drrat\tradingview-mcp\execution_lane"
$log = "$wd\logs\scheduler_run.log"
$err = "$wd\logs\scheduler_err.log"

# Signal running scheduler to stop gracefully via flag file
$stopFlag = "$wd\logs\STOP"
"" | Set-Content $stopFlag -Encoding ASCII
Write-Host "Stop flag written. Waiting for scheduler to exit (up to 90s)..."

$waited = 0
while ($waited -lt 90) {
    Start-Sleep -Seconds 3
    $waited += 3
    $proc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*Python311*" }
    if (-not $proc) { break }
    try { $proc | Stop-Process -Force -ErrorAction Stop; break } catch {}
}

if (Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*Python311*" }) {
    Write-Host "WARNING: Could not stop old process automatically."
    Write-Host "Open Task Manager -> Details -> python.exe -> End Task, then re-run this script."
    exit 1
}

Write-Host "Old process stopped."
Remove-Item $stopFlag -ErrorAction SilentlyContinue

# Archive old log with timestamp before overwrite
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path $log) {
    Copy-Item $log "$wd\logs\scheduler_run_$ts.log" -ErrorAction SilentlyContinue
}

# Start new scheduler — python.exe (not pythonw) so stdout handle is valid
# -WindowStyle Hidden keeps the console invisible
$proc = Start-Process -FilePath $py `
    -ArgumentList "-u scheduler.py" `
    -WorkingDirectory $wd `
    -WindowStyle Hidden `
    -RedirectStandardOutput $log `
    -RedirectStandardError  $err `
    -PassThru

Start-Sleep -Seconds 4
$p = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*Python311*" } | Select-Object -Last 1
if ($p) {
    Write-Host "Scheduler restarted. PID: $($p.Id)"
    Write-Host "Watching log... (Ctrl+C to stop)"
    Get-Content $log -Wait -Tail 20 -Encoding UTF8
} else {
    Write-Host "Failed to start. Check errors:"
    Get-Content $err -ErrorAction SilentlyContinue
}
