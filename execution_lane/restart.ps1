$pyw = "C:\Users\drrat\AppData\Local\Programs\Python\Python311\pythonw.exe"
$wd  = "C:\Users\drrat\tradingview-mcp\execution_lane"
$log = "$wd\logs\scheduler_run.log"
$err = "$wd\logs\scheduler_err.log"

# Signal running scheduler to stop gracefully via flag file
$stopFlag = "$wd\logs\STOP"
"" | Set-Content $stopFlag -NoNewline
Write-Host "Stop flag written. Waiting for scheduler to exit (up to 90s)..."

# Wait up to 90 seconds for pythonw to release the log file
$waited = 0
while ($waited -lt 90) {
    Start-Sleep -Seconds 3
    $waited += 3
    $proc = Get-Process pythonw -ErrorAction SilentlyContinue
    if (-not $proc) { break }
    # Also try force-kill in case this session has permission
    try { $proc | Stop-Process -Force -ErrorAction Stop; break } catch {}
}

if (Get-Process pythonw -ErrorAction SilentlyContinue) {
    Write-Host "WARNING: Could not stop old process automatically."
    Write-Host "Please run Task Manager -> find pythonw.exe -> End Task, then re-run this script."
    exit 1
}

Write-Host "Old process stopped."
Start-Sleep -Seconds 1

# Append restart marker to log
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $log -Value "" -Encoding UTF8
Add-Content -Path $log -Value "=== RESTART $ts ===" -Encoding UTF8

Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c `"$pyw`" scheduler.py >> `"$log`" 2>> `"$err`"" `
    -WorkingDirectory $wd `
    -WindowStyle Hidden

Start-Sleep -Seconds 3
$p = Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object -Last 1
if ($p) {
    Write-Host "Scheduler restarted. PID: $($p.Id)"
    Write-Host "Watching log... (Ctrl+C to stop)"
    Get-Content $log -Wait -Tail 20 -Encoding UTF8
} else {
    Write-Host "Failed to start. Check errors:"
    Get-Content $err -ErrorAction SilentlyContinue
}
