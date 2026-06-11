$pyw = "C:\Users\drrat\AppData\Local\Programs\Python\Python311\pythonw.exe"
$wd  = "C:\Users\drrat\tradingview-mcp\execution_lane"
$log = "$wd\logs\scheduler_run.log"
$err = "$wd\logs\scheduler_err.log"

Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Old process stopped."
Start-Sleep -Seconds 2

Start-Process -FilePath $pyw `
    -ArgumentList "scheduler.py" `
    -WorkingDirectory $wd `
    -RedirectStandardOutput $log `
    -RedirectStandardError  $err `
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
