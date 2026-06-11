# MCX Crudeoil Scheduler — Windows Task Scheduler installer
# Run once as Administrator:  Right-click PowerShell -> Run as Administrator
#   then:  .\execution_lane\install_task.ps1

$taskName = "MCX_CrudeoilScheduler"
$batPath  = "C:\Users\drrat\tradingview-mcp\execution_lane\start_scheduler.bat"

Write-Host ""
Write-Host "=== MCX Crudeoil Scheduler Installer ===" -ForegroundColor Cyan

# 1 ── Register the scheduled task
Write-Host "[1] Registering scheduled task '$taskName'..."

$action   = New-ScheduledTaskAction -Execute $batPath
$trigger  = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit        (New-TimeSpan -Hours 0) `
    -RestartCount              3 `
    -RestartInterval           (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable        `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable:$false `
    -Hidden

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host "    OK — runs at every logon, restarts on failure (3x, 5 min gap)" -ForegroundColor Green

# 2 ── Power plan: do nothing on lid close (keeps laptop awake)
Write-Host "[2] Setting lid-close action to 'Do Nothing'..."

$subgroup = "4f971e89-eebd-4455-a8de-9e59040e7347"
$setting  = "5ca83367-6e45-459f-a27b-476b1d01c936"

powercfg /setdcvalueindex SCHEME_CURRENT $subgroup $setting 0   # on battery
powercfg /setacvalueindex SCHEME_CURRENT $subgroup $setting 0   # on AC
powercfg /s SCHEME_CURRENT

Write-Host "    OK — laptop stays awake when lid closes (screen off, CPU on)" -ForegroundColor Green

# 3 ── Start immediately without waiting for reboot
Write-Host "[3] Starting task now..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3

$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "    Task state: $state" -ForegroundColor $(if ($state -eq "Running") {"Green"} else {"Yellow"})

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Scheduler is running in the background."
Write-Host "Log file:  C:\Users\drrat\tradingview-mcp\execution_lane\logs\scheduler_run.log"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  Check status:   Get-ScheduledTask -TaskName '$taskName'"
Write-Host "  Stop it:        Stop-ScheduledTask  -TaskName '$taskName'"
Write-Host "  Remove it:      Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
Write-Host "  Watch log:      Get-Content logs\scheduler_run.log -Wait -Tail 20"
Write-Host ""
