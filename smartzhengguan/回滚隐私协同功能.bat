@echo off
setlocal
cd /d "%~dp0"
rem Parse this block before Python removes this newly-added launcher.
(
  echo Restore privacy feature files to the exact pre-change snapshot.
  echo Please stop the frontend and backend services first.
  if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" ".local-backups\privacy_collaboration_before_20261117\checkpoint.py" restore
  ) else (
    py -3 ".local-backups\privacy_collaboration_before_20261117\checkpoint.py" restore
  )
  if errorlevel 1 (
    echo Restore failed. The checkpoint is still available in .local-backups.
    pause
    exit /b 1
  )
  echo Restore finished. Restart the project and refresh your browser.
  pause
  exit /b 0
)
