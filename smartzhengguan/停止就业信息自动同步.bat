@echo off
setlocal
cd /d "%~dp0"
"backend\.venv\Scripts\python.exe" backend\manage.py sync_employment_sources --stop
if errorlevel 1 exit /b 1
echo [INFO] Stop requested. The worker will finish its current bounded sync and exit.
endlocal
exit /b 0
