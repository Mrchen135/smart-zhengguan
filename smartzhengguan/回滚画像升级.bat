@echo off
setlocal
cd /d "%~dp0"
rem Parse the whole block before restoring removes this new launcher.
(
  echo Restore portrait files to the exact pre-upgrade working snapshot.
  echo Please stop the frontend and backend services first.
  if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" ".local-backups\portrait_before_20261118\checkpoint.py" restore
  ) else (
    py -3 ".local-backups\portrait_before_20261118\checkpoint.py" restore
  )
  if errorlevel 1 (
    echo Restore failed. The checkpoint remains in .local-backups.
    pause
    exit /b 1
  )
  echo Restore finished. Restart the project and refresh the browser.
  echo If serving dist, rebuild it with npm run build.
  pause
  exit /b 0
)
