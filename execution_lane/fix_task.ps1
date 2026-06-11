# Simpler approach: Startup folder + pythonw.exe (no password, no UAC)

$pyDir   = "C:\Users\drrat\AppData\Local\Programs\Python\Python311"
$pyw     = "$pyDir\pythonw.exe"   # windowless Python -- no console, survives terminal close
$workDir = "C:\Users\drrat\tradingview-mcp\execution_lane"
$logFile = "$workDir\logs\scheduler_run.log"
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"

# 1 -- Kill any old Task Scheduler entry (cleanup)
schtasks /delete /tn "MCX_CrudeoilScheduler" /f 2>$null

# 2 -- Drop a VBScript in Startup folder (auto-runs silently on every login)
$vbsPath = "$startup\start_crudeoil_scheduler.vbs"
$vbs = @"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$workDir"
sh.Run "$pyw scheduler.py >> logs\scheduler_run.log 2>&1", 0, False
"@
$vbs | Out-File $vbsPath -Encoding ASCII
Write-Host "[1] Startup entry created: $vbsPath"

# 3 -- Start immediately in background (survives after this terminal closes)
$running = Get-Process pythonw -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like "*scheduler*" }
if ($running) {
    Write-Host "[2] Scheduler already running (PID $($running.Id)) -- skipping start"
} else {
    Start-Process -FilePath $pyw `
                  -ArgumentList "scheduler.py" `
                  -WorkingDirectory $workDir `
                  -RedirectStandardOutput $logFile `
                  -RedirectStandardError  "$workDir\logs\scheduler_err.log" `
                  -WindowStyle Hidden
    Start-Sleep -Seconds 6
    $proc = Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($proc) {
        Write-Host "[2] Scheduler started -- PID $($proc.Id)"
    } else {
        Write-Host "[2] Process not found -- check scheduler_err.log"
    }
}

# 4 -- Show log
Write-Host ""
if (Test-Path $logFile) {
    Write-Host "=== Log ==="
    Get-Content $logFile -Tail 20
} else {
    Start-Sleep -Seconds 4
    if (Test-Path $logFile) {
        Get-Content $logFile -Tail 20
    } else {
        Write-Host "Log not yet created. Check errors:"
        if (Test-Path "$workDir\logs\scheduler_err.log") {
            Get-Content "$workDir\logs\scheduler_err.log"
        }
    }
}

Write-Host ""
Write-Host "To watch live:  Get-Content '$logFile' -Wait -Tail 20"
Write-Host "To stop:        Get-Process pythonw | Stop-Process"
