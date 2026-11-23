@echo off
setlocal
cd /d "%~dp0"
rem Read this entire block before restoring removes this launcher.
(
  echo Restore code to the snapshot before the employment information center.
  echo Stop frontend, backend and the employment sync worker first.
  echo The current database, imports and collected announcements will be preserved.
  if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" ".local-backups\employment_hub_before_20261123\checkpoint.py" restore
  ) else (
    py -3 ".local-backups\employment_hub_before_20261123\checkpoint.py" restore
  )
  if errorlevel 1 (
    echo Restore failed. The checkpoint remains available.
    pause
    exit /b 1
  )
  echo Restored. Restart the project and refresh the browser.
  echo Rebuild dist if using a production frontend.
  pause
  exit /b 0
)
