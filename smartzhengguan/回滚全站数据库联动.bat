@echo off
setlocal
cd /d "%~dp0"
rem Parse the complete block before restoring deletes this new launcher.
(
  echo Restore code to the snapshot before database linking.
  echo Please stop frontend and backend services first.
  echo The current database and later imports will be preserved.
  if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" ".local-backups\database_link_before_20261118\checkpoint.py" restore
  ) else (
    py -3 ".local-backups\database_link_before_20261118\checkpoint.py" restore
  )
  if errorlevel 1 (
    echo Restore failed. The checkpoint is retained in .local-backups.
    pause
    exit /b 1
  )
  echo Restore finished. Restart the project and refresh the browser.
  echo If serving dist, run npm run build again.
  pause
  exit /b 0
)
