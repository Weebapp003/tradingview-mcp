@echo off
cd /d "C:\Users\drrat\tradingview-mcp\execution_lane"
python scheduler.py >> "logs\scheduler_run.log" 2>&1
