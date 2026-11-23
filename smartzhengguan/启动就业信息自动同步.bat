@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Project Python environment is missing.
  exit /b 1
)
rem The worker owns a cross-process singleton lock. Repeated starts are safe.
powershell -NoProfile -Command "$root=(Get-Location).Path; $python=Join-Path $root 'backend\.venv\Scripts\python.exe'; $manage=Join-Path $root 'backend\manage.py'; Start-Process -FilePath $python -ArgumentList @(('"'+$manage+'"'),'sync_employment_sources','--watch','--interval','43200') -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden"
if errorlevel 1 exit /b 1
echo [INFO] Employment sync worker started. Interval: 12 hours.
endlocal
exit /b 0
