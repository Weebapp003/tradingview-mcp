Dim py, wd, log, err, cmd
py  = "C:\Users\drrat\AppData\Local\Programs\Python\Python311\python.exe"
wd  = "C:\Users\drrat\tradingview-mcp\execution_lane"
log = wd & "\logs\scheduler_run.log"
err = wd & "\logs\scheduler_err.log"
cmd = "cmd.exe /c """ & py & """ -u """ & wd & "\scheduler.py"" >> """ & log & """ 2>> """ & err & """"

Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = wd
shell.Run cmd, 0, False
